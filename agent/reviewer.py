from copy import deepcopy
from pathlib import PurePosixPath

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
from agent.function_calling import analyze_repository_impact
from agent.llm_client import (
    build_review_prompt,
    call_model_with_retries,
    create_gemini_client,
    extract_response_text,
    is_transient_model_error,
    normalize_json_response,
)
from agent.payload_builder import attach_static_findings, build_code_payload
from agent.repository_tools import (
    RepositoryToolError,
    get_bigquery_file_definitions,
)
from agent.review_batcher import filter_reviewable_files, make_review_batches
from agent.symbol_analysis import extract_changed_symbols


def _load_bigquery_owner_hints(
    *,
    repo_root,
    base_sha,
    head_sha,
    files,
):
    if not repo_root or not base_sha or not head_sha:
        return {}

    hints = {}
    for file_payload in files:
        path = file_payload.get("path", "")
        if PurePosixPath(path).suffix.lower() != ".sql":
            continue
        try:
            hints[path] = {
                "base": get_bigquery_file_definitions(
                    repo_root,
                    base_sha,
                    path,
                ),
                "head": get_bigquery_file_definitions(
                    repo_root,
                    head_sha,
                    path,
                ),
            }
        except (RepositoryToolError, TypeError, ValueError):
            continue
    return hints


def _failed_review(summary, findings=None, changes=None):
    return {
        "review_status": "failed",
        "summary": summary,
        "changes": list(changes or []),
        "findings": list(findings or []),
        "errors": [summary],
    }


def _completed_review(summary, findings=None, changes=None):
    return {
        "review_status": "completed",
        "summary": summary,
        "changes": list(changes or []),
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


def merge_changes(changes):
    merged = []
    seen = set()

    for change in changes:
        if not isinstance(change, dict):
            continue

        key = (
            change.get("file"),
            change.get("symbol"),
            change.get("change_type"),
            change.get("after"),
            change.get("behavior_change"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(change)

    return merged



_SQL_DETERMINISTIC_SYMBOL_TYPES = {
    "table",
    "column",
    "function",
}


def _normalized_change_type(value):
    if value in {"added", "modified", "deleted"}:
        return value
    return "modified"


def _has_meaningful_sql_diff(file_payload):
    in_block_comment = False

    for hunk in file_payload.get("hunks", []):
        for line in hunk.get("lines", []):
            if line.get("kind") not in {"added", "removed"}:
                continue

            content = str(line.get("content", ""))
            index = 0

            while index < len(content):
                if in_block_comment:
                    end = content.find("*/", index)
                    if end < 0:
                        index = len(content)
                        continue
                    in_block_comment = False
                    index = end + 2
                    continue

                if content.startswith("--", index):
                    break
                if content.startswith("/*", index):
                    in_block_comment = True
                    index += 2
                    continue
                if content[index].isspace():
                    index += 1
                    continue
                return True

    return False


def _deterministic_sql_change(
    *,
    path,
    symbol,
    symbol_type,
    change_type,
):
    change = {
        "file": path,
        "symbol": symbol,
        "symbol_type": symbol_type,
        "change_type": change_type,
    }

    if symbol_type == "file":
        change["after"] = "A new BigQuery SQL file was added."
        change["behavior_change"] = (
            "The file's SQL content is now part of the repository."
        )
        return change

    labels = {
        "query": "BigQuery query",
        "table": "BigQuery table or view definition",
        "column": "BigQuery column",
        "function": "BigQuery routine definition",
    }
    label = labels.get(symbol_type, "BigQuery SQL symbol")

    if change_type == "added":
        change["after"] = f"{label} was added: `{symbol}`."
        change["behavior_change"] = (
            f"`{symbol}` introduces new SQL behavior in the repository."
        )
    elif change_type == "deleted":
        change["before"] = f"{label} was removed: `{symbol}`."
        change["behavior_change"] = (
            f"`{symbol}` is no longer present in the new revision."
        )
    else:
        change["before"] = f"{label} existed in the previous revision."
        change["after"] = f"{label} was modified: `{symbol}`."
        change["behavior_change"] = (
            f"The BigQuery SQL definition or behavior of `{symbol}` changed."
        )

    return change


def ensure_deterministic_sql_changes(
    changes,
    changed_symbols,
    files,
):
    completed = merge_changes(changes)
    existing = {
        (
            item.get("file"),
            item.get("symbol"),
            item.get("change_type"),
        )
        for item in completed
        if isinstance(item, dict)
    }

    def append_missing(change):
        key = (
            change.get("file"),
            change.get("symbol"),
            change.get("change_type"),
        )
        if key in existing:
            return
        existing.add(key)
        completed.append(change)

    sql_symbols_by_file = {}
    deterministic_symbols = []

    for item in changed_symbols:
        if not isinstance(item, dict):
            continue

        path = item.get("file")
        symbol = item.get("symbol")
        symbol_type = item.get("symbol_type")

        if (
            not isinstance(path, str)
            or PurePosixPath(path).suffix.lower() != ".sql"
            or not isinstance(symbol, str)
            or not symbol
            or symbol_type not in _SQL_DETERMINISTIC_SYMBOL_TYPES
        ):
            continue

        normalized = dict(item)
        normalized["change_type"] = _normalized_change_type(
            item.get("change_type")
        )
        deterministic_symbols.append(normalized)
        sql_symbols_by_file.setdefault(path, []).append(normalized)

    for file_payload in files:
        if not isinstance(file_payload, dict):
            continue

        path = file_payload.get("path")
        if (
            not isinstance(path, str)
            or PurePosixPath(path).suffix.lower() != ".sql"
        ):
            continue

        file_change_type = _normalized_change_type(
            file_payload.get("change_type")
        )

        if file_change_type == "added":
            append_missing(
                _deterministic_sql_change(
                    path=path,
                    symbol="entire file",
                    symbol_type="file",
                    change_type="added",
                )
            )

        if (
            path not in sql_symbols_by_file
            and _has_meaningful_sql_diff(file_payload)
        ):
            append_missing(
                _deterministic_sql_change(
                    path=path,
                    symbol=PurePosixPath(path).stem,
                    symbol_type="query",
                    change_type=file_change_type,
                )
            )

    for item in deterministic_symbols:
        append_missing(
            _deterministic_sql_change(
                path=item["file"],
                symbol=item["symbol"],
                symbol_type=item["symbol_type"],
                change_type=item["change_type"],
            )
        )

    return completed

def _string_values(value):
    if not isinstance(value, list):
        return set()
    return {
        item
        for item in value
        if isinstance(item, str) and item
    }


def _external_reference_files(impact):
    changed_file = impact.get("changed_file")
    references = _string_values(
        impact.get("external_reference_files", [])
    )
    references.update(
        _string_values(impact.get("reference_files_base", []))
    )
    references.update(
        _string_values(impact.get("reference_files_head", []))
    )
    references.discard(changed_file)
    return references


def _finding_matches_symbol(finding, impact, changed_symbols):
    symbol = impact.get("symbol")
    changed_file = impact.get("changed_file")
    if not symbol or finding.get("file") != changed_file:
        return False

    message = finding.get("message", "")
    if isinstance(message, str) and symbol in message:
        return True

    finding_line = finding.get("line")
    if not isinstance(finding_line, int):
        return False

    for changed_symbol in changed_symbols:
        if (
            changed_symbol.get("file") == changed_file
            and changed_symbol.get("symbol") == symbol
            and finding_line
            in set(changed_symbol.get("source_lines", []))
            | set(changed_symbol.get("target_lines", []))
        ):
            return True

    return False


def apply_breaking_change_severity_policy(
    findings,
    impact_analysis,
    changed_symbols,
):
    normalized = []
    impacts = [
        impact
        for impact in impact_analysis
        if isinstance(impact, dict)
        and impact.get("symbol_type") in {"function", "method"}
    ]

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        updated = dict(finding)
        if (
            updated.get("category") == "breaking_change"
            and updated.get("severity") == "critical"
        ):
            matching_impact = next(
                (
                    impact
                    for impact in impacts
                    if _finding_matches_symbol(
                        updated,
                        impact,
                        changed_symbols,
                    )
                ),
                None,
            )
            if (
                matching_impact is not None
                and not _external_reference_files(matching_impact)
            ):
                updated["severity"] = "high"

        normalized.append(updated)

    return normalized



def _relevance_reference_files(impact, field):
    changed_file = impact.get("changed_file")
    values = impact.get(field, [])

    if not isinstance(values, list):
        return set()

    files = {
        value
        for value in values
        if isinstance(value, str) and value
    }

    if isinstance(changed_file, str):
        files.discard(changed_file)

    return files


def _added_files_from_changes(changes):
    return {
        item.get("file")
        for item in changes
        if (
            isinstance(item, dict)
            and item.get("change_type") == "added"
            and item.get("symbol_type") == "file"
            and isinstance(item.get("file"), str)
            and item.get("file")
        )
    }


def apply_repository_relevance_evidence(
    changes,
    impact_analysis,
    impact_status,
):
    relevance_symbol_types = {
        "file",
        "function",
        "method",
        "class",
        "struct",
        "table",
        "query",
        "column",
    }

    change_items = [
        item
        for item in changes
        if isinstance(item, dict)
    ]
    added_files = _added_files_from_changes(change_items)

    impacts = [
        item
        for item in impact_analysis
        if isinstance(item, dict)
    ]

    normalized = []

    for change in change_items:
        updated = dict(change)

        if (
            updated.get("change_type") != "added"
            or updated.get("symbol_type") not in relevance_symbol_types
        ):
            normalized.append(updated)
            continue

        changed_file = updated.get("file")
        symbol = updated.get("symbol")
        symbol_type = updated.get("symbol_type")

        matching_impacts = []

        for impact in impacts:
            if impact.get("changed_file") != changed_file:
                continue

            if (
                symbol_type != "file"
                and impact.get("symbol") != symbol
            ):
                continue

            matching_impacts.append(impact)

        base_reference_files = {
            reference_file
            for impact in matching_impacts
            for reference_file in _relevance_reference_files(
                impact,
                "reference_files_base",
            )
        }
        head_reference_files = {
            reference_file
            for impact in matching_impacts
            for reference_file in _relevance_reference_files(
                impact,
                "reference_files_head",
            )
        }

        external_files = (
            base_reference_files
            | head_reference_files
        )

        repository_files = sorted(
            external_files - added_files
        )
        same_pr_added_files = sorted(
            external_files & added_files
        )

        if repository_files:
            rendered_files = ", ".join(
                f"`{reference_file}`"
                for reference_file in repository_files
            )
            updated["repository_relevance"] = "related"
            updated["relevance_reason"] = (
                "Usage evidence was found in files that existed in the "
                f"repository before this PR: {rendered_files}."
            )

        elif same_pr_added_files:
            rendered_files = ", ".join(
                f"`{reference_file}`"
                for reference_file in same_pr_added_files
            )
            updated["repository_relevance"] = "unclear"
            updated["relevance_reason"] = (
                "Usage evidence was found only in files added by this PR: "
                f"{rendered_files}. A connection to pre-existing repository "
                "files was not established."
            )

        else:
            updated["repository_relevance"] = "unclear"

            if impact_status == "failed":
                updated["relevance_reason"] = (
                    "Repository impact analysis could not be completed, so "
                    "the repository relevance of this new file or symbol "
                    "could not be established."
                )
            elif impact_status == "skipped":
                updated["relevance_reason"] = (
                    "Repository impact analysis did not run, so the repository "
                    "relevance of this new file or symbol could not be established."
                )
            else:
                updated["relevance_reason"] = (
                    "No import, call, or usage evidence was found outside the "
                    "changed file; file path and naming alone were not treated "
                    "as repository relevance evidence."
                )

        normalized.append(updated)

    return normalized


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
    normalized["changes"] = merge_changes(normalized.get("changes", []))
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
    pr_context=None,
    repo_root=None,
    base_sha=None,
    head_sha=None,
):
    try:
        base_payload = parse_diff(diff_text, max_review_lines=None)
    except (DependencyError, DiffParseError) as exc:
        return _failed_review(f"Inceleme baslatilamadi: {exc}")

    if pr_context is None:
        pr_context = {
            "source_type": (
                "codebase_summary"
                if main_branch_file_context
                else "none"
            ),
            "file_context": main_branch_file_context or {},
            "project_documents": [],
            "context_sources": [],
        }

    file_context = pr_context.get("file_context", {})
    if not isinstance(file_context, dict):
        file_context = {}

    project_documents = pr_context.get("project_documents", [])
    if not isinstance(project_documents, list):
        project_documents = []

    context_sources = pr_context.get("context_sources", [])
    if not isinstance(context_sources, list):
        context_sources = []

    project_context = {
        "source_type": pr_context.get("source_type", "none"),
        "project_documents": project_documents,
        "context_sources": context_sources,
    }
    base_payload["project_context"] = project_context

    sql_owner_hints = _load_bigquery_owner_hints(
        repo_root=repo_root,
        base_sha=base_sha,
        head_sha=head_sha,
        files=base_payload.get("files", []),
    )
    changed_symbols = extract_changed_symbols(
        base_payload,
        sql_owner_hints=sql_owner_hints,
    )
    base_payload["changed_symbols"] = changed_symbols
    impact_result = {
        "status": "skipped",
        "summary": "Repository revision bilgisi bulunmadigi icin capraz dosya analizi atlandi.",
        "impact_analysis": [],
        "errors": [],
        "tool_trace": [],
        "analysis_sources": [],
    }

    impact_enabled = bool(
        changed_symbols and repo_root and base_sha and head_sha
    )
    if impact_enabled:
        if client is None:
            try:
                client = create_gemini_client()
            except (ConfigurationError, DependencyError) as exc:
                return _failed_review(
                    f"Inceleme baslatilamadi: {exc}",
                )
            except Exception as exc:
                return _failed_review(
                    f"Gemini client baslatilamadi: {exc}",
                )

        impact_result = analyze_repository_impact(
            client=client,
            repo_root=repo_root,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_symbols=changed_symbols,
            changed_paths=pr_context.get("changed_paths", []),
            context_source_type=project_context["source_type"],
            context_sources=context_sources,
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )

    base_payload["repository_impact_context"] = impact_result.get(
        "impact_analysis",
        [],
    )

    if file_context:
        base_payload["main_branch_file_context"] = file_context

    reviewable_files = filter_reviewable_files(base_payload.get("files", []))

    if not reviewable_files:
        result = _completed_review(
            "Incelenebilir Python, SQL veya Go dosya degisikligi bulunamadi."
        )
        result["context_source_type"] = project_context["source_type"]
        result["context_sources"] = context_sources
        result["changed_symbols"] = changed_symbols
        result["impact_analysis"] = impact_result.get("impact_analysis", [])
        result["impact_analysis_status"] = impact_result.get("status", "skipped")
        result["analysis_sources"] = impact_result.get("analysis_sources", [])
        result["tool_trace"] = impact_result.get("tool_trace", [])
        return result

    batches = make_review_batches(
        reviewable_files,
        max_lines_per_batch=max_review_lines,
    )

    all_changes = []
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

        batch_changed_symbols = extract_changed_symbols(
            {"files": batch.files},
            sql_owner_hints=sql_owner_hints,
        )
        batch_payload["changed_symbols"] = batch_changed_symbols
        batch_symbol_names = {
            item.get("symbol")
            for item in batch_changed_symbols
            if item.get("symbol")
        }
        batch_paths = {
            file_payload.get("path")
            for file_payload in batch.files
        }
        batch_payload["repository_impact_context"] = [
            item
            for item in impact_result.get("impact_analysis", [])
            if (
                item.get("changed_file") in batch_paths
                or item.get("symbol") in batch_symbol_names
            )
        ]

        if file_context:
            batch_payload["main_branch_file_context"] = {
                path: context
                for path, context in file_context.items()
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
        all_changes.extend(result.get("changes", []))
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

    impact_errors = impact_result.get("errors", [])
    if impact_result.get("status") == "failed":
        summaries.append(
            "Repository capraz dosya analizi tamamlanamadi; "
            "ana PR incelemesi sonucu korundu."
        )

    return {
        "review_status": review_status,
        "summary": (
            f"{len(reviewable_files)} dosya {len(batches)} batch halinde planlandi. "
            f"{completed_batch_count} batch tamamlandi, "
            f"{len(failed_batches)} batch tamamlanamadi. "
            + " ".join(summaries)
        ),
        "changes": apply_repository_relevance_evidence(
            ensure_deterministic_sql_changes(
                all_changes,
                changed_symbols,
                reviewable_files,
            ),
            impact_result.get("impact_analysis", []),
            impact_result.get("status", "skipped"),
        ),
        "findings": apply_breaking_change_severity_policy(
            all_findings,
            impact_result.get("impact_analysis", []),
            changed_symbols,
        ),
        "errors": (
            [item["reason"] for item in failed_batches]
            + list(impact_errors)
        ),
        "failed_batches": failed_batches,
        "context_source_type": project_context["source_type"],
        "context_sources": context_sources,
        "changed_symbols": changed_symbols,
        "impact_analysis": impact_result.get("impact_analysis", []),
        "impact_analysis_status": impact_result.get("status", "skipped"),
        "impact_analysis_summary": impact_result.get("summary", ""),
        "analysis_sources": impact_result.get("analysis_sources", []),
        "tool_trace": impact_result.get("tool_trace", []),
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
