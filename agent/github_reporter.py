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
        + "The report was shortened because of GitHub's comment limit. "
        + "Check the workflow logs for the complete result."
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
        f"Changes across {file_count} {'file' if file_count == 1 else 'files'} in this PR"
        if file_count
        else "The PR changes"
    )

    if review_status == "completed":
        result = (
            f"A total of {finding_count} important findings were detected; "
            "the effects of changed functions and variables on usages in "
            "other files are summarized below."
            if finding_count
            else "No critical, high, or medium severity findings were detected."
        )
        return f"{scope} were reviewed. {result}"

    if review_status == "partial":
        return (
            f"{scope} were partially reviewed. The {finding_count} findings "
            "obtained are listed below; because part of the analysis could "
            "not be completed, this report must not be treated as a clean PR approval."
        )

    return (
        "The PR review could not be completed. A reliable clean result was "
        "not produced; check the workflow logs."
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
        "### Summary",
        "",
        _build_pr_summary(review_result, len(findings)),
        "",
        "### Changes",
        "",
    ]

    relevance_labels = {
        "related": "Related",
        "unclear": "Unclear",
        "unrelated": "Unrelated",
    }

    if changes:
        for index, change in enumerate(changes, start=1):
            file_name = change.get("file", "unknown file")
            symbol = change.get("symbol") or "entire file"
            symbol_type = change.get("symbol_type", "unknown")
            change_type = change.get("change_type", "modified")

            lines.extend(
                [
                    f"#### {index}. `{file_name}` — `{symbol}`",
                    "",
                    f"- **Type:** `{symbol_type}` / `{change_type}`",
                ]
            )

            if change.get("before"):
                lines.append(f"- **Before:** {change['before']}")
            if change.get("after"):
                lines.append(f"- **After:** {change['after']}")
            if change.get("behavior_change"):
                lines.append(
                    f"- **Behavior impact:** {change['behavior_change']}"
                )

            relevance = change.get("repository_relevance")
            if relevance in relevance_labels:
                lines.append(
                    "- **Repository relevance:** "
                    f"`{relevance_labels[relevance]}`"
                )
            if change.get("relevance_reason"):
                lines.append(
                    "- **Relevance evidence:** "
                    f"{change['relevance_reason']}"
                )

            lines.append("")
    else:
        lines.extend(
            [
                "The model did not produce a meaningful change summary.",
                "",
            ]
        )

    lines.extend(["### Findings", ""])

    if not findings:
        lines.append(
            "No critical, high, or medium severity findings were detected."
            if review_status == "completed"
            else "A reliable 'no issues found' result could not be produced."
        )
        return _shorten_text("\n".join(lines))

    for index, finding in enumerate(findings, start=1):
        file_name = finding.get("file", "unknown file")
        line = finding.get("line", "unknown line")
        impact = _matching_impact(finding, impact_analysis)
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
                f"- **Severity:** `{finding.get('severity', 'unknown')}`",
                f"- **Category:** `{finding.get('category', 'unknown')}`",
            ]
        )

        usage_files = _usage_files(impact)
        if usage_files:
            lines.append(
                "- **Other usages:** "
                + ", ".join(f"`{item}`" for item in usage_files)
            )

        lines.append(f"- **Problem:** {finding.get('message', '')}")
        if finding.get("suggestion"):
            lines.append(f"- **Suggestion:** {finding['suggestion']}")
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
