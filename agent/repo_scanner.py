import os
from dataclasses import dataclass


SUPPORTED_EXTENSIONS = {".py", ".sql", ".go"}

SKIP_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "ai-review-agent",
}

SKIP_FILE_SUFFIXES = {
    ".lock",
    ".min.js",
}


@dataclass
class RepositorySourceFile:
    path: str
    language: str
    line_count: int


def infer_language_from_path(path: str) -> str:
    lowered = path.lower()

    if lowered.endswith(".py"):
        return "python"
    if lowered.endswith(".sql"):
        return "sql"
    if lowered.endswith(".go"):
        return "go"

    return "unknown"


def should_skip_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = set(normalized.split("/"))

    if parts & SKIP_DIRS:
        return True

    return any(normalized.endswith(suffix) for suffix in SKIP_FILE_SUFFIXES)


def is_supported_file(path: str) -> bool:
    _, extension = os.path.splitext(path.lower())
    return extension in SUPPORTED_EXTENSIONS


def find_reviewable_repo_files(root_dir: str = ".") -> list[RepositorySourceFile]:
    files: list[RepositorySourceFile] = []

    for current_root, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [
            dirname for dirname in dirnames
            if dirname not in SKIP_DIRS
        ]

        for filename in filenames:
            full_path = os.path.join(current_root, filename)
            relative_path = os.path.relpath(full_path, root_dir)

            if should_skip_path(relative_path):
                continue

            if not is_supported_file(relative_path):
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as source_file:
                    line_count = sum(1 for _ in source_file)
            except UnicodeDecodeError:
                continue

            files.append(
                RepositorySourceFile(
                    path=relative_path,
                    language=infer_language_from_path(relative_path),
                    line_count=line_count,
                )
            )

    files.sort(
        key=lambda file_info: file_info.path.replace("\\", "/")
    )

    return files
