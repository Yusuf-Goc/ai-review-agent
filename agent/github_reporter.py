import json
import os
import urllib.error
import urllib.request


class GitHubReporterError(Exception):
    pass


MAX_COMMENT_LENGTH = 60000


def _shorten_text(text: str, max_length: int = MAX_COMMENT_LENGTH) -> str:
    if len(text) <= max_length:
        return text

    return (
        text[: max_length - 300]
        + "\n\n---\n"
        + "Rapor GitHub yorum limiti nedeniyle kısaltıldı. "
        + "Tam sonuç için workflow loglarını kontrol edin."
    )


def _context_type_label(source_type: str) -> str:
    labels = {
        "codebase_summary": "Codebase Summary JSON",
        "markdown": "README / Markdown dokümanları",
        "none": "Yalnızca PR diff'i",
    }
    return labels.get(source_type, source_type or "Bilinmeyen")


def format_github_markdown_report(review_result: dict) -> str:
    changes = [
        item
        for item in review_result.get("changes", [])
        if isinstance(item, dict)
    ]
    findings = [
        item
        for item in review_result.get("findings", [])
        if isinstance(item, dict)
    ]
    impact_analysis = [
        item
        for item in review_result.get("impact_analysis", [])
        if isinstance(item, dict)
    ]
    summary = review_result.get("summary", "İnceleme tamamlandı.")
    review_status = review_result.get("review_status", "completed")
    failed_batches = review_result.get("failed_batches", [])
    errors = [
        error
        for error in review_result.get("errors", [])
        if isinstance(error, str) and error
    ]
    context_source_type = review_result.get("context_source_type", "none")
    context_sources = [
        source
        for source in review_result.get("context_sources", [])
        if isinstance(source, str) and source
    ]
    analysis_sources = [
        source
        for source in review_result.get("analysis_sources", [])
        if isinstance(source, str) and source
    ]

    severity_counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
    }

    for finding in findings:
        severity = finding.get("severity", "medium")
        if severity in severity_counts:
            severity_counts[severity] += 1

    lines = [
        "## Vestel AI Code Review",
        "",
        f"**Özet:** {summary}",
        "",
        "### Bulgu Sayısı",
        "",
        f"- Critical: {severity_counts['critical']}",
        f"- High: {severity_counts['high']}",
        f"- Medium: {severity_counts['medium']}",
        "",
    ]

    if review_status != "completed":
        status_text = (
            "İnceleme kısmen tamamlandı."
            if review_status == "partial"
            else "İnceleme tamamlanamadı."
        )
        lines.extend(
            [
                "### İnceleme Durumu",
                "",
                f"⚠️ **{status_text}** Bu sonuç temiz bir PR onayı olarak değerlendirilmemelidir.",
            ]
        )

        displayed_errors = set()
        for item in failed_batches:
            reason = item.get('reason', 'Bilinmeyen hata')
            displayed_errors.add(reason)
            lines.append(
                f"- Batch {item.get('batch', '?')}: {reason}"
            )

        for error in errors:
            if error not in displayed_errors:
                lines.append(f"- {error}")

        lines.append("")

    if changes:
        lines.extend(["### PR'da Ne Değişti?", ""])

        for index, change in enumerate(changes, start=1):
            file_name = change.get("file", "bilinmeyen dosya")
            symbol = change.get("symbol") or "dosya geneli"
            symbol_type = change.get("symbol_type", "unknown")
            change_type = change.get("change_type", "modified")
            before = change.get("before", "")
            after = change.get("after", "")
            behavior_change = change.get("behavior_change", "")

            lines.extend(
                [
                    f"#### {index}. `{file_name}` — `{symbol}`",
                    "",
                    f"- **Tür:** `{symbol_type}` / `{change_type}`",
                ]
            )
            if before:
                lines.append(f"- **Önce:** {before}")
            if after:
                lines.append(f"- **Sonra:** {after}")
            if behavior_change:
                lines.append(f"- **Davranış etkisi:** {behavior_change}")
            lines.append("")

    if impact_analysis:
        lines.extend(["### Çapraz Dosya Etkisi", ""])

        for index, impact_item in enumerate(impact_analysis, start=1):
            symbol = impact_item.get("symbol", "bilinmeyen sembol")
            changed_file = impact_item.get("changed_file", "bilinmeyen dosya")
            impact_text = impact_item.get("impact", "Etki açıklaması yok.")
            definition_files = impact_item.get("definition_files", [])
            base_refs = impact_item.get("reference_files_base", [])
            head_refs = impact_item.get("reference_files_head", [])
            evidence = impact_item.get("evidence", [])

            lines.extend(
                [
                    f"#### {index}. `{symbol}` — `{changed_file}`",
                    "",
                    f"- **Etki:** {impact_text}",
                ]
            )
            if definition_files:
                lines.append(
                    "- **Tanım dosyaları:** "
                    + ", ".join(f"`{item}`" for item in definition_files)
                )
            if base_refs:
                lines.append(
                    "- **Base kullanımları:** "
                    + ", ".join(f"`{item}`" for item in base_refs)
                )
            if head_refs:
                lines.append(
                    "- **Head kullanımları:** "
                    + ", ".join(f"`{item}`" for item in head_refs)
                )
            if evidence:
                lines.append(
                    "- **Kanıt:** "
                    + ", ".join(f"`{item}`" for item in evidence)
                )
            lines.append("")

    lines.extend(
        [
            "### Kullanılan Bağlam",
            "",
            f"- **Bağlam türü:** {_context_type_label(context_source_type)}",
        ]
    )
    if context_sources:
        lines.append(
            "- **Kaynaklar:** "
            + ", ".join(f"`{source}`" for source in context_sources)
        )
    if analysis_sources:
        lines.append(
            "- **Repository analiz kaynakları:** "
            + ", ".join(f"`{source}`" for source in analysis_sources)
        )
    elif context_source_type == "none":
        lines.append("- Ek proje özeti bulunamadığı için inceleme PR diff'i üzerinden yapıldı.")
    lines.append("")

    if not findings:
        lines.extend(
            [
                "### Sonuç",
                "",
                (
                    "Kritik hata bulunamadı."
                    if review_status == "completed"
                    else "Güvenilir bir ‘hata bulunamadı’ sonucu üretilemedi."
                ),
            ]
        )
        return _shorten_text("\n".join(lines))

    lines.extend(["### Bulgular", ""])

    for index, finding in enumerate(findings, start=1):
        file_name = finding.get("file", "bilinmeyen dosya")
        line = finding.get("line", "bilinmeyen satır")
        severity = finding.get("severity", "unknown")
        category = finding.get("category", "unknown")
        message = finding.get("message", "")
        suggestion = finding.get("suggestion", "")

        lines.extend(
            [
                f"#### {index}. `{file_name}:{line}`",
                "",
                f"- **Seviye:** `{severity}`",
                f"- **Kategori:** `{category}`",
                f"- **Problem:** {message}",
            ]
        )

        if suggestion:
            lines.append(f"- **Öneri:** {suggestion}")

        lines.append("")

    return _shorten_text("\n".join(lines))


def post_pr_comment(repo: str, pr_number: str, body: str, token: str) -> None:
    if not repo:
        raise GitHubReporterError("GitHub repo bilgisi boş olamaz.")

    if not pr_number:
        raise GitHubReporterError("PR number bilgisi boş olamaz.")

    if not token:
        raise GitHubReporterError("GitHub token boş olamaz.")

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"

    payload = json.dumps({"body": body}).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in {200, 201}:
                raise GitHubReporterError(
                    f"GitHub yorum isteği başarısız oldu. Status: {response.status}"
                )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise GitHubReporterError(
            f"GitHub PR yorumu gönderilemedi. HTTP {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise GitHubReporterError(
            f"GitHub PR yorumu gönderilemedi: {exc}"
        ) from exc


def post_review_result_to_pr(
    review_result: dict,
    repo: str | None = None,
    pr_number: str | None = None,
    token: str | None = None,
) -> None:
    repo = repo or os.getenv("GITHUB_REPOSITORY")
    pr_number = pr_number or os.getenv("PR_NUMBER")
    token = token or os.getenv("GITHUB_TOKEN")

    body = format_github_markdown_report(review_result)
    post_pr_comment(repo=repo, pr_number=pr_number, body=body, token=token)
