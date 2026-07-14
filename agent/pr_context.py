import json
import os
import subprocess


def _run_git_show(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        return None

    return result.stdout


def load_main_branch_codebase_context(
    base_sha: str,
    summary_path: str = ".ai-review/codebase-summary.json",
) -> dict:
    raw_json = _run_git_show(base_sha, summary_path)

    if not raw_json:
        return {}

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}

    files = parsed.get("files", [])

    return {
        item.get("path"): item
        for item in files
        if item.get("path")
    }


def get_changed_paths(base_sha: str, head_sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha],
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        return []

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def build_pr_file_context(base_sha: str, head_sha: str) -> dict:
    summary_by_path = load_main_branch_codebase_context(base_sha)
    changed_paths = get_changed_paths(base_sha, head_sha)

    context = {}

    for path in changed_paths:
        if path in summary_by_path:
            context[path] = summary_by_path[path]

    return context
