from copy import deepcopy

from agent.config import (
    DEFAULT_MODEL,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
    MAX_REVIEW_LINES,
    ConfigurationError,
    DependencyError,
    DiffParseError,
)
from agent.diff_parser import parse_diff
from agent.llm_client import (
    build_review_prompt,
    call_model_with_retries,
    create_gemini_client,
    extract_response_text,
    is_transient_model_error,
    normalize_json_response,
)
from agent.payload_builder import attach_static_findings, build_code_payload
from agent.review_batcher import filter_reviewable_files, make_review_batches


def _failed_review(summary, findings=None):
    return {
        "review_status": "failed",
        "summary": summary,
        "findings": list(findings or []),
        "errors": [summary],
    }


def _completed_review(summary, findings=None):
    return {
        "review_status": "completed",
        "summary": summary,
        "findings": list(findings or []),
        "errors": [],
    }


def merge_findings(model_findings, local_findings):
    merged = []
    seen = set()

    for finding in local_findings + model_findings:
        key = (
            finding.get("file"),
            finding.get("line"),
            finding.get("category"),
            finding.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(finding)

    return merged


def analyze_payload(
    review_payload,
    client=None,
    model=DEFAULT_MODEL,
    retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
):
    local_findings = review_payload.get("static_analysis_findings", [])

    if not any(file_item["hunks"] or file_item["is_binary"] for file_item in review_payload["files"]):
        return _completed_review(
            "Analiz edilecek gecerli kod degisikligi bulunamadi.",
            local_findings,
        )

    if client is None:
        try:
            client = create_gemini_client()
        except (ConfigurationError, DependencyError) as exc:
            return _failed_review(
                f"Inceleme baslatilamadi: {exc}",
                local_findings,
            )
        except Exception as exc:
            return _failed_review(
                f"Gemini client baslatilamadi: {exc}",
                local_findings,
            )

    prompt = build_review_prompt(review_payload)

    try:
        response = call_model_with_retries(
            client,
            prompt,
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )
    except Exception as exc:
        if is_transient_model_error(exc):
            return _failed_review(
                (
                    "Gemini modeli gecici olarak yogun veya erisilemez durumda. "
                    "Biraz sonra tekrar deneyin ya da `--model` ile baska bir modeli deneyin. "
                    f"Son hata: {exc}"
                ),
                local_findings,
            )
        return _failed_review(
            f"Model cagrisi basarisiz oldu: {exc}",
            local_findings,
        )

    ai_output = extract_response_text(response)
    if not ai_output:
        return _failed_review(
            "Yapay zekadan bos veya cozumlenemeyen yanit dondu.",
            local_findings,
        )

    normalized = normalize_json_response(ai_output)
    normalized["findings"] = merge_findings(normalized.get("findings", []), local_findings)

    if normalized.get("raw_response") is not None:
        return _failed_review(
            normalized.get("summary", "Model yaniti dogrulanamadi."),
            normalized["findings"],
        )

    normalized["review_status"] = "completed"
    normalized["errors"] = []

    if local_findings and "Yerel syntax on kontrolu" not in normalized.get("summary", ""):
        normalized["summary"] = (
            f"{normalized.get('summary', 'Inceleme tamamlandi.')} "
            f"Yerel syntax on kontrolu {len(local_findings)} ek bulgu uretti."
        )
    return normalized


def analyze_code(diff_text, client=None, model=DEFAULT_MODEL, max_review_lines=MAX_REVIEW_LINES, retries=DEFAULT_RETRIES, retry_delay=DEFAULT_RETRY_DELAY):
    print("Vestel AI Agent (Structured Diff Review Modu) calisiyor...\n")

    try:
        review_payload = parse_diff(diff_text, max_review_lines=max_review_lines)
    except (DependencyError, DiffParseError) as exc:
        return _failed_review(f"Inceleme baslatilamadi: {exc}")

    return analyze_payload(review_payload, client=client, model=model, retries=retries, retry_delay=retry_delay)


def analyze_diff_in_batches(
    diff_text,
    client=None,
    model=DEFAULT_MODEL,
    max_review_lines=MAX_REVIEW_LINES,
    retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
    main_branch_file_context=None,
):
    try:
        base_payload = parse_diff(diff_text, max_review_lines=None)
    except (DependencyError, DiffParseError) as exc:
        return _failed_review(f"Inceleme baslatilamadi: {exc}")

    if main_branch_file_context:
        base_payload["main_branch_file_context"] = main_branch_file_context

    reviewable_files = filter_reviewable_files(base_payload.get("files", []))

    if not reviewable_files:
        return _completed_review(
            "Incelenebilir Python, SQL veya Go dosya degisikligi bulunamadi."
        )

    batches = make_review_batches(
        reviewable_files,
        max_lines_per_batch=max_review_lines,
    )

    all_findings = []
    summaries = []
    failed_batches = []
    completed_batch_count = 0

    for index, batch in enumerate(batches, start=1):
        batch_payload = deepcopy(base_payload)
        batch_payload["files"] = batch.files
        batch_payload["batch"] = {
            "index": index,
            "total": len(batches),
            "file_count": len(batch.files),
            "estimated_lines": batch.estimated_lines,
        }
        batch_payload["limits"] = {
            "max_review_lines_per_batch": max_review_lines,
            "truncated": False,
        }

        if main_branch_file_context:
            batch_paths = {
                file_payload.get("path")
                for file_payload in batch.files
            }

            batch_payload["main_branch_file_context"] = {
                path: context
                for path, context in main_branch_file_context.items()
                if path in batch_paths
            }

        result = analyze_payload(
            batch_payload,
            client=client,
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )

        summaries.append(
            f"Batch {index}/{len(batches)}: {result.get('summary', 'Ozet yok')}"
        )
        all_findings.extend(result.get("findings", []))

        if result.get("review_status") == "completed":
            completed_batch_count += 1
        else:
            failed_batches.append(
                {
                    "batch": index,
                    "reason": result.get(
                        "summary",
                        "Batch incelemesi tamamlanamadi.",
                    ),
                }
            )

    if not failed_batches:
        review_status = "completed"
    elif completed_batch_count:
        review_status = "partial"
    else:
        review_status = "failed"

    return {
        "review_status": review_status,
        "summary": (
            f"{len(reviewable_files)} dosya {len(batches)} batch halinde planlandi. "
            f"{completed_batch_count} batch tamamlandi, "
            f"{len(failed_batches)} batch tamamlanamadi. "
            + " ".join(summaries)
        ),
        "findings": all_findings,
        "errors": [item["reason"] for item in failed_batches],
        "failed_batches": failed_batches,
    }


def analyze_source_code(
    code_text,
    file_name="submitted_code",
    language=None,
    client=None,
    model=DEFAULT_MODEL,
    max_review_lines=MAX_REVIEW_LINES,
    retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
):
    print("Vestel AI Agent (Full Code Review Modu) calisiyor...\n")

    try:
        review_payload = build_code_payload(
            code_text,
            file_name=file_name,
            language=language,
            max_review_lines=max_review_lines,
        )
        attach_static_findings(review_payload)
    except DiffParseError as exc:
        return _failed_review(f"Inceleme baslatilamadi: {exc}")

    return analyze_payload(review_payload, client=client, model=model, retries=retries, retry_delay=retry_delay)
