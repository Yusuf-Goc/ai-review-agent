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


def format_github_markdown_report(review_result: dict) -> str:
    findings = review_result.get("findings", [])
    summary = review_result.get("summary", "İnceleme tamamlandı.")
    review_status = review_result.get("review_status", "completed")
    failed_batches = review_result.get("failed_batches", [])

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

        for item in failed_batches:
            lines.append(
                f"- Batch {item.get('batch', '?')}: "
                f"{item.get('reason', 'Bilinmeyen hata')}"
            )

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

    lines.append("### Bulgular")
    lines.append("")

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
