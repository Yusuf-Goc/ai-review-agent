import json
import subprocess
from pathlib import PurePosixPath
from typing import Any


SUMMARY_PATH = ".ai-review/codebase-summary.json"
MARKDOWN_SUFFIXES = {".md", ".markdown"}
SKIP_CONTEXT_PARTS = {
    ".git",
    ".ai-review",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "venv",
    ".venv",
}
DEFAULT_MARKDOWN_MAX_FILES = 5
DEFAULT_MARKDOWN_FILE_CHARS = 8_000
DEFAULT_MARKDOWN_TOTAL_CHARS = 24_000


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


def _run_git_list_files(ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref],
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


def load_main_branch_codebase_context(
    base_sha: str,
    summary_path: str = SUMMARY_PATH,
) -> dict:
    raw_json = _run_git_show(base_sha, summary_path)

    if not raw_json:
        return {}

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    files = parsed.get("files", [])
    if not isinstance(files, list):
        return {}

    return {
        item.get("path"): item
        for item in files
        if isinstance(item, dict) and item.get("path")
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


def _is_context_markdown(path: str) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    pure_path = PurePosixPath(normalized)
    parts = {part.lower() for part in pure_path.parts}

    if parts & SKIP_CONTEXT_PARTS:
        return False

    return pure_path.suffix.lower() in MARKDOWN_SUFFIXES


def _markdown_priority(path: str) -> tuple[int, str]:
    normalized = path.replace("\\", "/").strip("/")
    pure_path = PurePosixPath(normalized)
    lower_path = normalized.lower()
    name = pure_path.name.lower()
    parts = tuple(part.lower() for part in pure_path.parts)

    if len(parts) == 1 and name in {"readme.md", "readme.markdown"}:
        priority = 0
    elif name.startswith("readme."):
        priority = 1
    elif (
        parts
        and parts[0] == "docs"
        and any(
            keyword in lower_path
            for keyword in ("architecture", "design", "overview")
        )
    ):
        priority = 2
    elif parts and parts[0] == "docs":
        priority = 3
    elif len(parts) == 1:
        priority = 4
    else:
        priority = 5

    return priority, lower_path


def load_base_markdown_context(
    base_sha: str,
    max_files: int = DEFAULT_MARKDOWN_MAX_FILES,
    max_chars_per_file: int = DEFAULT_MARKDOWN_FILE_CHARS,
    max_total_chars: int = DEFAULT_MARKDOWN_TOTAL_CHARS,
) -> list[dict[str, str]]:
    candidates = sorted(
        (
            path
            for path in _run_git_list_files(base_sha)
            if _is_context_markdown(path)
        ),
        key=_markdown_priority,
    )

    documents: list[dict[str, str]] = []
    remaining_chars = max_total_chars

    for path in candidates:
        if len(documents) >= max_files or remaining_chars <= 0:
            break

        raw_text = _run_git_show(base_sha, path)
        if not raw_text or not raw_text.strip():
            continue

        content_limit = min(max_chars_per_file, remaining_chars)
        content = raw_text[:content_limit]

        if len(raw_text) > content_limit:
            content += "\n...[dokuman baglami kisaltildi]"

        documents.append(
            {
                "path": path,
                "content": content,
            }
        )
        remaining_chars -= len(content)

    return documents


def build_pr_file_context(base_sha: str, head_sha: str) -> dict:
    summary_by_path = load_main_branch_codebase_context(base_sha)
    changed_paths = get_changed_paths(base_sha, head_sha)

    return {
        path: summary_by_path[path]
        for path in changed_paths
        if path in summary_by_path
    }


def build_pr_context(base_sha: str, head_sha: str) -> dict[str, Any]:
    changed_paths = get_changed_paths(base_sha, head_sha)
    summary_by_path = load_main_branch_codebase_context(base_sha)

    if summary_by_path:
        file_context = {
            path: summary_by_path[path]
            for path in changed_paths
            if path in summary_by_path
        }

        return {
            "source_type": "codebase_summary",
            "changed_paths": changed_paths,
            "file_context": file_context,
            "project_documents": [],
            "context_sources": [SUMMARY_PATH],
        }

    project_documents = load_base_markdown_context(base_sha)

    if project_documents:
        return {
            "source_type": "markdown",
            "changed_paths": changed_paths,
            "file_context": {},
            "project_documents": project_documents,
            "context_sources": [
                document["path"]
                for document in project_documents
            ],
        }

    return {
        "source_type": "none",
        "changed_paths": changed_paths,
        "file_context": {},
        "project_documents": [],
        "context_sources": [],
    }
