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


def _reviewed_file_count(review_result: dict) -> int:
    paths = set()
    field_pairs = (
        ("changes", "file"),
        ("findings", "file"),
        ("changed_symbols", "file"),
        ("impact_analysis", "changed_file"),
    )

    for field_name, path_key in field_pairs:
        for item in review_result.get(field_name, []):
            if isinstance(item, dict) and item.get(path_key):
                paths.add(item[path_key])

    return len(paths)


def _build_pr_summary(review_result: dict, finding_count: int) -> str:
    review_status = review_result.get("review_status", "completed")
    file_count = _reviewed_file_count(review_result)
    scope = (
        f"PR kapsamında {file_count} dosyadaki değişiklikler"
        if file_count
        else "PR değişiklikleri"
    )

    if review_status == "completed":
        result = (
            f"Toplam {finding_count} önemli bulgu tespit edildi; değişen "
            "fonksiyon ve değişkenlerin diğer dosyalardaki kullanımlara "
            "etkisi aşağıda özetlenmiştir."
            if finding_count
            else "Kritik, yüksek veya orta seviyede bulgu tespit edilmedi."
        )
        return f"{scope} incelendi. {result}"

    if review_status == "partial":
        return (
            f"{scope} kısmen incelendi. Elde edilen {finding_count} bulgu "
            "aşağıda listelenmiştir; tamamlanamayan analiz nedeniyle bu "
            "rapor temiz bir PR onayı olarak değerlendirilmemelidir."
        )

    return (
        "PR incelemesi tamamlanamadı. Güvenilir bir temiz sonuç "
        "üretilemedi; workflow logları kontrol edilmelidir."
    )


def _matching_impact(finding: dict, impact_analysis: list[dict]):
    finding_file = finding.get("file")
    finding_symbol = finding.get("symbol")
    message = finding.get("message", "")
    same_file = [
        item
        for item in impact_analysis
        if item.get("changed_file") == finding_file
    ]

    for impact in same_file:
        symbol = impact.get("symbol")
        if symbol and (
            symbol == finding_symbol
            or (isinstance(message, str) and symbol in message)
        ):
            return impact

    return same_file[0] if len(same_file) == 1 else None


def _matching_change(finding: dict, impact, changes: list[dict]):
    file_name = impact.get("changed_file") if impact else finding.get("file")
    symbol = impact.get("symbol") if impact else finding.get("symbol")

    for change in changes:
        if change.get("file") == file_name and change.get("symbol") == symbol:
            return change

    return None


def _usage_files(impact) -> list[str]:
    if not impact:
        return []

    files = set()
    for field_name in (
        "external_reference_files",
        "reference_files_base",
        "reference_files_head",
    ):
        files.update(
            item
            for item in impact.get(field_name, [])
            if isinstance(item, str) and item
        )

    files.discard(impact.get("changed_file"))
    return sorted(files)


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
    review_status = review_result.get("review_status", "completed")

    lines = [
        "## Vestel AI Code Review",
        "",
        "### Özet",
        "",
        _build_pr_summary(review_result, len(findings)),
        "",
        "### Bulgular",
        "",
    ]

    if not findings:
        lines.append(
            "Kritik, yüksek veya orta seviyede bulgu tespit edilmedi."
            if review_status == "completed"
            else "Güvenilir bir ‘hata bulunamadı’ sonucu üretilemedi."
        )
        return _shorten_text("\n".join(lines))

    for index, finding in enumerate(findings, start=1):
        file_name = finding.get("file", "bilinmeyen dosya")
        line = finding.get("line", "bilinmeyen satır")
        impact = _matching_impact(finding, impact_analysis)
        change = _matching_change(finding, impact, changes)
        symbol = impact.get("symbol") if impact else finding.get("symbol")
        title = (
            f"#### {index}. `{symbol}` — `{file_name}:{line}`"
            if symbol
            else f"#### {index}. `{file_name}:{line}`"
        )

        lines.extend(
            [
                title,
                "",
                f"- **Seviye:** `{finding.get('severity', 'unknown')}`",
                f"- **Kategori:** `{finding.get('category', 'unknown')}`",
            ]
        )

        if change:
            detail = []
            if change.get("before"):
                detail.append(f"Önce: {change['before']}")
            if change.get("after"):
                detail.append(f"Sonra: {change['after']}")
            if change.get("behavior_change"):
                detail.append(f"Etki: {change['behavior_change']}")
            if detail:
                lines.append(f"- **Değişiklik:** {' '.join(detail)}")
        elif impact and impact.get("impact"):
            lines.append(f"- **Değişiklik ve etki:** {impact['impact']}")

        usage_files = _usage_files(impact)
        if usage_files:
            lines.append(
                "- **Diğer kullanımlar:** "
                + ", ".join(f"`{item}`" for item in usage_files)
            )

        lines.append(f"- **Problem:** {finding.get('message', '')}")
        if finding.get("suggestion"):
            lines.append(f"- **Öneri:** {finding['suggestion']}")
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
