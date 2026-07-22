import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_EXTENSIONS = {".py", ".go", ".sql"}
DOCUMENT_EXTENSIONS = {".md", ".markdown"}
READABLE_EXTENSIONS = SOURCE_EXTENSIONS | DOCUMENT_EXTENSIONS
SKIP_PATH_PARTS = {
    ".git",
    ".ai-review",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
}
MAX_SYMBOL_LENGTH = 160
MAX_SEARCH_RESULTS = 100
MAX_READ_LINES = 240


class RepositoryToolError(RuntimeError):
    pass


def _run_git(
    repo_root: str | Path,
    arguments: list[str],
    *,
    allow_no_matches: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode == 0:
        return result
    if allow_no_matches and result.returncode == 1:
        return result

    detail = result.stderr.strip() or result.stdout.strip()
    raise RepositoryToolError(
        f"Git komutu calistirilamadi: {detail or 'bilinmeyen hata'}"
    )


def _validate_ref(ref: str) -> str:
    if (
        not isinstance(ref, str)
        or not ref.strip()
        or ref.startswith("-")
        or "\x00" in ref
        or "\n" in ref
        or len(ref) > 200
    ):
        raise RepositoryToolError("Gecersiz Git revision degeri.")
    return ref.strip()


def resolve_revision(repo_root: str | Path, revision: str) -> str:
    safe_revision = _validate_ref(revision)
    result = _run_git(
        repo_root,
        ["rev-parse", "--verify", f"{safe_revision}^{{commit}}"],
    )
    return result.stdout.strip()


def _normalize_path(path: str, *, extensions: set[str]) -> str:
    if not isinstance(path, str) or not path.strip():
        raise RepositoryToolError("Dosya yolu bos olamaz.")

    normalized = path.replace("\\", "/").strip()
    pure_path = PurePosixPath(normalized)

    if (
        pure_path.is_absolute()
        or ".." in pure_path.parts
        or "\x00" in normalized
        or "\n" in normalized
        or ":" in normalized
    ):
        raise RepositoryToolError("Repository disina cikan dosya yolu reddedildi.")

    lowered_parts = {part.lower() for part in pure_path.parts}
    if lowered_parts & SKIP_PATH_PARTS:
        raise RepositoryToolError("Bu dosya yolu inceleme kapsami disindadir.")

    if pure_path.suffix.lower() not in extensions:
        raise RepositoryToolError("Desteklenmeyen dosya uzantisi.")

    return pure_path.as_posix()


def _validate_symbol(symbol: str) -> str:
    if (
        not isinstance(symbol, str)
        or not symbol.strip()
        or len(symbol) > MAX_SYMBOL_LENGTH
        or "\x00" in symbol
        or "\n" in symbol
    ):
        raise RepositoryToolError("Gecersiz sembol veya arama degeri.")
    return symbol.strip()


def list_repository_files(
    repo_root: str | Path,
    revision: str,
    *,
    extensions: set[str] | None = None,
) -> list[str]:
    commit = resolve_revision(repo_root, revision)
    result = _run_git(
        repo_root,
        ["ls-tree", "-r", "--name-only", commit],
    )
    allowed_extensions = extensions or READABLE_EXTENSIONS
    files = []

    for raw_path in result.stdout.splitlines():
        try:
            path = _normalize_path(raw_path, extensions=allowed_extensions)
        except RepositoryToolError:
            continue
        files.append(path)

    return files


def read_file_section(
    repo_root: str | Path,
    revision: str,
    path: str,
    *,
    start_line: int = 1,
    end_line: int | None = None,
    max_lines: int = MAX_READ_LINES,
) -> dict[str, Any]:
    if start_line < 1:
        raise RepositoryToolError("start_line en az 1 olmalidir.")
    if max_lines < 1 or max_lines > MAX_READ_LINES:
        raise RepositoryToolError(
            f"max_lines 1 ile {MAX_READ_LINES} arasinda olmalidir."
        )

    safe_path = _normalize_path(path, extensions=READABLE_EXTENSIONS)
    commit = resolve_revision(repo_root, revision)
    result = _run_git(repo_root, ["show", f"{commit}:{safe_path}"])
    file_lines = result.stdout.splitlines()
    total_lines = len(file_lines)

    requested_end = end_line if end_line is not None else start_line + max_lines - 1
    if requested_end < start_line:
        raise RepositoryToolError("end_line start_line degerinden kucuk olamaz.")

    effective_end = min(requested_end, start_line + max_lines - 1, total_lines)
    selected = file_lines[start_line - 1 : effective_end]

    return {
        "revision": commit,
        "path": safe_path,
        "start_line": start_line,
        "end_line": effective_end,
        "total_lines": total_lines,
        "truncated": requested_end > effective_end,
        "lines": [
            {
                "line": number,
                "content": content,
            }
            for number, content in enumerate(selected, start=start_line)
        ],
    }


def _parse_grep_output(
    output: str,
    *,
    commit: str,
    max_results: int,
) -> tuple[list[dict[str, Any]], bool]:
    matches = []
    prefix = f"{commit}:"

    for raw_line in output.splitlines():
        if not raw_line.startswith(prefix):
            continue

        remainder = raw_line[len(prefix) :]
        try:
            path, line_number, content = remainder.split(":", 2)
            normalized_path = _normalize_path(
                path,
                extensions=READABLE_EXTENSIONS,
            )
            parsed_line_number = int(line_number)
        except (ValueError, RepositoryToolError):
            continue

        matches.append(
            {
                "path": normalized_path,
                "line": parsed_line_number,
                "content": content,
            }
        )
        if len(matches) > max_results:
            return matches[:max_results], True

    return matches, False


def _git_grep(
    repo_root: str | Path,
    revision: str,
    query: str,
    *,
    pathspecs: list[str],
    max_results: int,
) -> dict[str, Any]:
    if max_results < 1 or max_results > MAX_SEARCH_RESULTS:
        raise RepositoryToolError(
            f"max_results 1 ile {MAX_SEARCH_RESULTS} arasinda olmalidir."
        )

    safe_query = _validate_symbol(query)
    commit = resolve_revision(repo_root, revision)
    result = _run_git(
        repo_root,
        [
            "grep",
            "-n",
            "-I",
            "-F",
            "-e",
            safe_query,
            commit,
            "--",
            *pathspecs,
        ],
        allow_no_matches=True,
    )
    matches, truncated = _parse_grep_output(
        result.stdout,
        commit=commit,
        max_results=max_results,
    )

    return {
        "revision": commit,
        "query": safe_query,
        "matches": matches,
        "truncated": truncated,
    }


def search_symbol(
    repo_root: str | Path,
    revision: str,
    symbol: str,
    *,
    max_results: int = 50,
) -> dict[str, Any]:
    return _git_grep(
        repo_root,
        revision,
        symbol,
        pathspecs=["*.py", "*.go", "*.sql"],
        max_results=max_results,
    )


def search_project_docs(
    repo_root: str | Path,
    revision: str,
    query: str,
    *,
    max_results: int = 30,
) -> dict[str, Any]:
    return _git_grep(
        repo_root,
        revision,
        query,
        pathspecs=["*.md", "*.markdown"],
        max_results=max_results,
    )


def _line_defines_symbol(path: str, line: str, symbol: str) -> bool:
    escaped = re.escape(symbol)
    extension = PurePosixPath(path).suffix.lower()

    if extension == ".py":
        return bool(
            re.search(
                rf"^\s*(?:(?:async\s+)?def|class)\s+{escaped}\b",
                line,
            )
            or re.search(rf"^{escaped}\s*(?::[^=]+)?=(?!=)", line)
        )

    if extension == ".go":
        return bool(
            re.search(
                rf"^\s*func\s*(?:\([^)]*\)\s*)?{escaped}\s*"
                rf"(?:\[[^\]]+\]\s*)?\(",
                line,
            )
            or re.search(
                rf"^\s*(?:type|var|const)\s+{escaped}\b",
                line,
            )
        )

    if extension == ".sql":
        return bool(
            re.search(
                rf"^\s*(?:CREATE|ALTER|DROP)"
                rf"(?:\s+OR\s+REPLACE)?\s+"
                rf"(?:TABLE|VIEW|FUNCTION|PROCEDURE|TRIGGER)\s+"
                rf"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
                rf"[`\"\[]?{escaped}[`\"\]]?\b",
                line,
                re.IGNORECASE,
            )
        )

    return False


def find_symbol_definitions(
    repo_root: str | Path,
    revision: str,
    symbol: str,
    *,
    max_results: int = 20,
) -> dict[str, Any]:
    if max_results < 1 or max_results > MAX_SEARCH_RESULTS:
        raise RepositoryToolError(
            f"max_results 1 ile {MAX_SEARCH_RESULTS} arasinda olmalidir."
        )

    occurrence_result = search_symbol(
        repo_root,
        revision,
        symbol,
        max_results=MAX_SEARCH_RESULTS,
    )
    definitions = [
        match
        for match in occurrence_result["matches"]
        if _line_defines_symbol(
            match["path"],
            match["content"],
            symbol,
        )
    ]

    return {
        "revision": occurrence_result["revision"],
        "symbol": symbol,
        "definitions": definitions[:max_results],
        "truncated": len(definitions) > max_results,
    }


def _symbol_snapshot(
    repo_root: str | Path,
    revision: str,
    symbol: str,
    *,
    context_lines: int,
) -> dict[str, Any]:
    definitions = find_symbol_definitions(
        repo_root,
        revision,
        symbol,
        max_results=10,
    )
    occurrences = search_symbol(
        repo_root,
        revision,
        symbol,
        max_results=50,
    )

    sections = []
    for definition in definitions["definitions"][:3]:
        sections.append(
            read_file_section(
                repo_root,
                revision,
                definition["path"],
                start_line=max(1, definition["line"] - context_lines),
                end_line=definition["line"] + context_lines,
                max_lines=min(MAX_READ_LINES, context_lines * 2 + 1),
            )
        )

    return {
        "revision": definitions["revision"],
        "definitions": definitions["definitions"],
        "occurrences": occurrences["matches"],
        "sections": sections,
    }


def compare_symbol(
    repo_root: str | Path,
    base_revision: str,
    head_revision: str,
    symbol: str,
    *,
    context_lines: int = 20,
) -> dict[str, Any]:
    if context_lines < 0 or context_lines > 100:
        raise RepositoryToolError(
            "context_lines 0 ile 100 arasinda olmalidir."
        )

    safe_symbol = _validate_symbol(symbol)
    return {
        "symbol": safe_symbol,
        "base": _symbol_snapshot(
            repo_root,
            base_revision,
            safe_symbol,
            context_lines=context_lines,
        ),
        "head": _symbol_snapshot(
            repo_root,
            head_revision,
            safe_symbol,
            context_lines=context_lines,
        ),
    }
