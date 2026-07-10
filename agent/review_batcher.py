from dataclasses import dataclass, field


SUPPORTED_EXTENSIONS = {".py", ".sql", ".go"}

SKIP_PATH_PARTS = {
    "vendor",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}

SKIP_FILE_SUFFIXES = {
    ".lock",
    ".min.js",
}


@dataclass
class ReviewBatch:
    files: list[dict] = field(default_factory=list)
    estimated_lines: int = 0


def should_skip_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = set(normalized.split("/"))

    if parts & SKIP_PATH_PARTS:
        return True

    return any(normalized.endswith(suffix) for suffix in SKIP_FILE_SUFFIXES)


def file_extension(path: str) -> str:
    if "." not in path:
        return ""
    return "." + path.rsplit(".", 1)[-1].lower()


def count_file_review_lines(file_payload: dict) -> int:
    count = 0

    for hunk in file_payload.get("hunks", []):
        for line in hunk.get("lines", []):
            if line.get("kind") in {"added", "removed", "context"}:
                count += 1

    return count


def filter_reviewable_files(files: list[dict]) -> list[dict]:
    reviewable = []

    for file_payload in files:
        path = file_payload.get("path", "")

        if file_payload.get("is_binary"):
            continue

        if should_skip_file(path):
            continue

        if file_extension(path) not in SUPPORTED_EXTENSIONS:
            continue

        reviewable.append(file_payload)

    return reviewable


def make_review_batches(
    files: list[dict],
    max_files_per_batch: int = 5,
    max_lines_per_batch: int = 1200,
) -> list[ReviewBatch]:
    batches: list[ReviewBatch] = []
    current = ReviewBatch()

    for file_payload in files:
        file_line_count = count_file_review_lines(file_payload)

        batch_full_by_file_count = len(current.files) >= max_files_per_batch
        batch_full_by_line_count = (
            current.estimated_lines + file_line_count > max_lines_per_batch
        )

        if current.files and (batch_full_by_file_count or batch_full_by_line_count):
            batches.append(current)
            current = ReviewBatch()

        current.files.append(file_payload)
        current.estimated_lines += file_line_count

    if current.files:
        batches.append(current)

    return batches
