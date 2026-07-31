import re
import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from agent.bigquery_evidence import analyze_bigquery_sql
from agent.config import get_bounded_int_env


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
MAX_READ_LINES = get_bounded_int_env(
    "AI_REVIEW_MAX_FILE_SECTION_LINES",
    1_000,
    minimum=1,
    maximum=5_000,
)
MAX_BIGQUERY_SCAN_FILES = get_bounded_int_env(
    "AI_REVIEW_MAX_BIGQUERY_SCAN_FILES",
    500,
    minimum=1,
    maximum=5_000,
)
MAX_BIGQUERY_FILE_CHARS = get_bounded_int_env(
    "AI_REVIEW_MAX_BIGQUERY_FILE_CHARS",
    1_000_000,
    minimum=1_000,
    maximum=5_000_000,
)


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



def _bigquery_identifier_parts(value: str) -> list[str]:
    stripped = _validate_symbol(value).strip("`")
    return [part.strip("`").casefold() for part in stripped.split(".") if part]


def _bigquery_object_match(
    target_parts: list[str],
    candidate: dict[str, Any],
) -> str | None:
    candidate_parts = [
        str(part).casefold()
        for part in (
            candidate.get("project"),
            candidate.get("dataset"),
            candidate.get("object"),
        )
        if isinstance(part, str) and part
    ]
    if not target_parts or not candidate_parts:
        return None

    if len(target_parts) >= 3:
        return "confirmed" if candidate_parts[-3:] == target_parts[-3:] else None
    if len(target_parts) == 2:
        if len(candidate_parts) >= 2 and candidate_parts[-2:] == target_parts:
            return "confirmed"
        if candidate_parts[-1] == target_parts[-1] and len(candidate_parts) == 1:
            return "possible"
        return None

    if candidate_parts[-1] != target_parts[-1]:
        return None
    return "possible"


def _bigquery_reference_match(
    *,
    symbol: str,
    symbol_type: str,
    candidate: dict[str, Any],
) -> str | None:
    target_parts = _bigquery_identifier_parts(symbol)
    normalized_type = str(symbol_type or "unknown").casefold()

    if normalized_type == "column" and (
        candidate.get("reference_type") == "column_contract"
        or candidate.get("resolved_column") == "*"
    ):
        candidate_object_parts = [
            str(part).casefold()
            for part in (
                candidate.get("project"),
                candidate.get("dataset"),
                candidate.get("object"),
            )
            if isinstance(part, str) and part
        ]
        target_object_parts: list[str] = []
        target_column_parts = list(target_parts)
        for length in (3, 2, 1):
            if len(target_parts) <= length:
                continue
            object_candidate = target_parts[:length]
            if _bigquery_object_match(object_candidate, candidate) is not None:
                target_object_parts = object_candidate
                target_column_parts = target_parts[length:]
                break

        # SELECT * tablo seviyesindeki kolon sozlesmesini tasir. Nested STRUCT
        # alanlari bagimsiz top-level kolon olarak genisletilmez.
        if len(target_column_parts) != 1:
            return None
        target_column = target_column_parts[0].casefold()
        excluded_columns = {
            str(value).casefold()
            for value in candidate.get("excluded_columns", [])
            if isinstance(value, str)
        }
        replaced_columns = {
            str(value).casefold()
            for value in candidate.get("replaced_columns", [])
            if isinstance(value, str)
        }
        if target_column in excluded_columns or target_column in replaced_columns:
            return None

        if not target_object_parts:
            if not candidate_object_parts:
                return None
            return "possible"
        object_match = _bigquery_object_match(target_object_parts, candidate)
        if object_match is None:
            return None
        if candidate.get("confidence") != "confirmed":
            return "possible"
        return object_match

    if normalized_type == "column":
        candidate_column = candidate.get("resolved_column")
        if not isinstance(candidate_column, str) or not candidate_column:
            return None
        column_parts = [
            part.casefold()
            for part in candidate_column.split(".")
            if part
        ]
        if not column_parts:
            return None

        candidate_object_parts = [
            str(part).casefold()
            for part in (
                candidate.get("project"),
                candidate.get("dataset"),
                candidate.get("object"),
            )
            if isinstance(part, str) and part
        ]

        target_object_parts: list[str] = []
        target_column_parts = list(target_parts)
        for length in (3, 2, 1):
            if len(target_parts) <= length:
                continue
            object_candidate = target_parts[:length]
            if _bigquery_object_match(object_candidate, candidate) is not None:
                target_object_parts = object_candidate
                target_column_parts = target_parts[length:]
                break

        if not target_object_parts:
            if len(candidate_object_parts) >= 2 and len(target_parts) > len(column_parts):
                possible_object = target_parts[:-len(column_parts)]
                if _bigquery_object_match(possible_object, candidate) is not None:
                    target_object_parts = possible_object
                    target_column_parts = target_parts[len(possible_object):]
            elif len(target_parts) == len(column_parts):
                target_column_parts = target_parts

        if [part.casefold() for part in target_column_parts] != column_parts:
            return None

        if not target_object_parts:
            return "possible"

        object_match = _bigquery_object_match(target_object_parts, candidate)
        if object_match is None:
            return None
        if candidate.get("confidence") != "confirmed":
            return "possible"
        return object_match

    object_match = _bigquery_object_match(target_parts, candidate)
    if object_match is None:
        return None
    if candidate.get("confidence") != "confirmed":
        return "possible"
    return object_match


def _bigquery_reference_item(
    *,
    path: str,
    file_lines: list[str],
    candidate: dict[str, Any],
    confidence: str,
    reference_type: str,
) -> dict[str, Any]:
    line = candidate.get("line")
    content = ""
    if isinstance(line, int) and 1 <= line <= len(file_lines):
        content = file_lines[line - 1]

    return {
        "path": path,
        "line": line,
        "content": content,
        "confidence": confidence,
        "reference_type": reference_type,
        "raw_reference": (
            candidate.get("raw_reference")
            or candidate.get("raw_name")
            or ""
        ),
        "resolved_object": (
            candidate.get("resolved_object")
            or candidate.get("qualified_name")
            or None
        ),
        "resolved_column": candidate.get("resolved_column"),
        "clause": candidate.get("clause"),
        "statement": candidate.get("statement"),
        "scope": candidate.get("scope"),
        "source_type": candidate.get("source_type"),
        "routine_kind": candidate.get("routine_kind"),
        "excluded_columns": list(candidate.get("excluded_columns", [])),
        "replaced_columns": list(candidate.get("replaced_columns", [])),
        "reason": candidate.get("reason", ""),
    }


def _bigquery_owner_definitions(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    owners = []
    for definition in analysis.get("definitions", []):
        if not isinstance(definition, dict):
            continue
        if str(definition.get("action", "create")).casefold() != "create":
            continue
        if str(definition.get("object_type", "")).casefold() not in {
            "view", "function", "table_function", "procedure",
        }:
            continue
        qualified_name = definition.get("qualified_name")
        if not isinstance(qualified_name, str) or not qualified_name:
            continue
        owners.append(definition)
    return owners


def _bigquery_candidate_owner(
    file_item: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    statement = candidate.get("statement")
    owners = [
        owner
        for owner in file_item.get("owners", [])
        if owner.get("statement") == statement
    ]
    return owners[0] if len(owners) == 1 else None


def _bigquery_owner_consumers(
    repository_index: dict[str, Any],
    owner: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    owner_name = owner.get("qualified_name")
    owner_type = str(owner.get("object_type", "")).casefold()
    if not isinstance(owner_name, str) or not owner_name:
        return []

    results: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for file_item in repository_index.get("files", []):
        analysis = file_item.get("analysis", {})
        if owner_type in {"function", "table_function", "procedure"}:
            candidates = analysis.get("routine_references", [])
            symbol_type = "function"
        else:
            candidates = [
                candidate
                for candidate in analysis.get("sources", [])
                if isinstance(candidate, dict)
                and candidate.get("source_type") == "table"
            ]
            symbol_type = "table"
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("confidence") == "ignored":
                continue
            confidence = _bigquery_reference_match(
                symbol=owner_name,
                symbol_type=symbol_type,
                candidate=candidate,
            )
            if confidence is not None:
                results.append((file_item, candidate, confidence))
    return results


def _bigquery_transitive_references(
    repository_index: dict[str, Any],
    *,
    target_symbol: str,
    direct_confirmed: list[dict[str, Any]],
    direct_possible: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Dogrudan etkilenen view/routine sahiplerinden downstream zinciri izler."""
    file_lookup = {item.get("path"): item for item in repository_index.get("files", [])}
    queue: list[tuple[dict[str, Any], str, int, list[str]]] = []
    best_owner_confidence: dict[tuple[str, str], str] = {}

    def enqueue_from_reference(item: dict[str, Any], confidence: str) -> None:
        file_item = file_lookup.get(item.get("path"))
        if not isinstance(file_item, dict):
            return
        owner = _bigquery_candidate_owner(file_item, item)
        if owner is None:
            return
        owner_name = str(owner.get("qualified_name", ""))
        owner_type = str(owner.get("object_type", ""))
        key = (owner_type.casefold(), owner_name.casefold())
        previous = best_owner_confidence.get(key)
        if previous == "confirmed" or previous == confidence:
            return
        best_owner_confidence[key] = confidence
        queue.append((owner, confidence, 0, [target_symbol, owner_name]))

    for item in direct_confirmed:
        enqueue_from_reference(item, "confirmed")
    for item in direct_possible:
        enqueue_from_reference(item, "possible")

    confirmed: list[dict[str, Any]] = []
    possible: list[dict[str, Any]] = []
    processed: set[tuple[str, str, str]] = set()

    while queue:
        owner, path_confidence, depth, dependency_path = queue.pop(0)
        owner_name = str(owner.get("qualified_name", ""))
        owner_type = str(owner.get("object_type", "")).casefold()
        process_key = (owner_type, owner_name.casefold(), path_confidence)
        if process_key in processed:
            continue
        processed.add(process_key)

        for file_item, candidate, edge_confidence in _bigquery_owner_consumers(
            repository_index, owner
        ):
            confidence = (
                "confirmed"
                if path_confidence == "confirmed" and edge_confidence == "confirmed"
                else "possible"
            )
            consumer_owner = _bigquery_candidate_owner(file_item, candidate)
            endpoint = (
                str(consumer_owner.get("qualified_name"))
                if consumer_owner is not None
                else str(file_item.get("path", ""))
            )
            next_path = [*dependency_path, endpoint]
            item = _bigquery_reference_item(
                path=str(file_item.get("path", "")),
                file_lines=list(file_item.get("lines", [])),
                candidate=candidate,
                confidence=confidence,
                reference_type="transitive",
            )
            item.update({
                "dependency_kind": "transitive",
                "dependency_depth": depth + 1,
                "dependency_path": next_path,
                "via_object": owner_name,
                "reason": (
                    f"{owner_name} nesnesi uzerinden dolayli BigQuery bagimliligi bulundu."
                ),
            })
            (confirmed if confidence == "confirmed" else possible).append(item)

            if consumer_owner is None:
                continue
            next_owner_name = str(consumer_owner.get("qualified_name", ""))
            next_key = (
                str(consumer_owner.get("object_type", "")).casefold(),
                next_owner_name.casefold(),
            )
            previous = best_owner_confidence.get(next_key)
            if previous == "confirmed" or previous == confidence:
                continue
            best_owner_confidence[next_key] = confidence
            queue.append((consumer_owner, confidence, depth + 1, next_path))

    return confirmed, possible


@lru_cache(maxsize=8)
def _build_bigquery_repository_index(
    repo_root: str,
    commit: str,
) -> dict[str, Any]:
    sql_files = list_repository_files(
        repo_root,
        commit,
        extensions={".sql"},
    )
    analyzed_files = []
    parse_errors = []
    skipped_files = []

    for path in sql_files[:MAX_BIGQUERY_SCAN_FILES]:
        result = _run_git(repo_root, ["show", f"{commit}:{path}"])
        source_text = result.stdout
        if len(source_text) > MAX_BIGQUERY_FILE_CHARS:
            skipped_files.append({
                "path": path,
                "reason": "SQL dosyasi BigQuery evidence karakter limitini asti.",
            })
            continue

        analysis = analyze_bigquery_sql(source_text, path=path)
        analyzed_files.append({
            "path": path,
            "lines": source_text.splitlines(),
            "analysis": analysis,
            "owners": _bigquery_owner_definitions(analysis),
        })
        for error in analysis.get("errors", []):
            parse_errors.append({"path": path, **error})

    return {
        "files": analyzed_files,
        "parse_errors": parse_errors,
        "skipped_files": skipped_files,
        "scanned_file_count": min(len(sql_files), MAX_BIGQUERY_SCAN_FILES),
        "requested_file_count": len(sql_files),
        "truncated": len(sql_files) > MAX_BIGQUERY_SCAN_FILES,
    }


def get_bigquery_file_definitions(
    repo_root: str | Path,
    revision: str,
    path: str,
) -> dict[str, Any]:
    """Bir SQL dosyasinin tam revision icerigindeki BigQuery nesnelerini getirir.

    Bu yardimci diff hunk'inda DDL basligi gorunmeyen view veya routine govde
    degisikliklerini dosyanin gercek CREATE tanimiyla eslestirmek icin kullanilir.
    Dosya ilgili revision'da yoksa ``exists`` false ve definitions bos doner.
    """
    safe_path = _normalize_path(path, extensions={".sql"})
    commit = resolve_revision(repo_root, revision)
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{safe_path}"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if exists.returncode != 0:
        return {
            "revision": commit,
            "path": safe_path,
            "exists": False,
            "definitions": [],
            "errors": [],
            "skipped": False,
        }

    result = _run_git(repo_root, ["show", f"{commit}:{safe_path}"])
    source_text = result.stdout
    if len(source_text) > MAX_BIGQUERY_FILE_CHARS:
        return {
            "revision": commit,
            "path": safe_path,
            "exists": True,
            "definitions": [],
            "errors": [],
            "skipped": True,
            "skip_reason": "SQL dosyasi BigQuery evidence karakter limitini asti.",
        }

    analysis = analyze_bigquery_sql(source_text, path=safe_path)
    owners = []
    for definition in analysis.get("definitions", []):
        if not isinstance(definition, dict):
            continue
        if str(definition.get("action", "create")).casefold() != "create":
            continue
        if str(definition.get("object_type", "")).casefold() not in {
            "view", "function", "table_function", "procedure",
        }:
            continue
        owners.append(dict(definition))

    return {
        "revision": commit,
        "path": safe_path,
        "exists": True,
        "definitions": owners,
        "errors": list(analysis.get("errors", [])),
        "skipped": False,
    }


def find_bigquery_references(
    repo_root: str | Path,
    revision: str,
    symbol: str,
    *,
    symbol_type: str = "table",
    max_results: int = 50,
) -> dict[str, Any]:
    """BigQuery SQL referanslarini alias/dataset kanitiyla siniflandirir.

    ``references`` yalnizca kesin cozulmus kanitlari, ``possible_references``
    ise default dataset veya lineage bilgisi gerektiren adaylari icerir.
    Python ve Go sembol aramasi bu fonksiyondan etkilenmez.
    """
    if max_results < 1 or max_results > MAX_SEARCH_RESULTS:
        raise RepositoryToolError(
            f"max_results 1 ile {MAX_SEARCH_RESULTS} arasinda olmalidir."
        )

    safe_symbol = _validate_symbol(symbol)
    commit = resolve_revision(repo_root, revision)
    resolved_root = str(Path(repo_root).resolve())
    repository_index = _build_bigquery_repository_index(
        resolved_root,
        commit,
    )

    confirmed: list[dict[str, Any]] = []
    possible: list[dict[str, Any]] = []
    ignored_count = 0
    total_candidates = 0

    for file_item in repository_index["files"]:
        path = file_item["path"]
        analysis = file_item["analysis"]
        file_lines = file_item["lines"]

        normalized_type = str(symbol_type or "unknown").casefold()
        if normalized_type == "column":
            candidates = [
                *analysis.get("references", []),
                *analysis.get("wildcard_references", []),
            ]
            reference_type = "column"
        elif normalized_type == "function":
            candidates = analysis.get("routine_references", [])
            reference_type = "routine"
        else:
            candidates = [
                candidate
                for candidate in analysis.get("sources", [])
                if isinstance(candidate, dict)
                and candidate.get("source_type") == "table"
            ]
            reference_type = "object"

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("confidence") == "ignored":
                ignored_count += 1
                continue

            confidence = _bigquery_reference_match(
                symbol=safe_symbol,
                symbol_type=normalized_type,
                candidate=candidate,
            )
            if confidence is None:
                continue

            total_candidates += 1
            item = _bigquery_reference_item(
                path=path,
                file_lines=file_lines,
                candidate=candidate,
                confidence=confidence,
                reference_type=(
                    str(candidate.get("reference_type"))
                    if candidate.get("reference_type")
                    else reference_type
                ),
            )
            if confidence == "confirmed":
                confirmed.append(item)
            else:
                possible.append(item)

    for item in confirmed:
        item.setdefault("dependency_kind", "direct")
        item.setdefault("dependency_depth", 0)
        item.setdefault("dependency_path", [safe_symbol])
    for item in possible:
        item.setdefault("dependency_kind", "direct")
        item.setdefault("dependency_depth", 0)
        item.setdefault("dependency_path", [safe_symbol])

    transitive_confirmed, transitive_possible = _bigquery_transitive_references(
        repository_index,
        target_symbol=safe_symbol,
        direct_confirmed=confirmed,
        direct_possible=possible,
    )
    confirmed.extend(transitive_confirmed)
    possible.extend(transitive_possible)

    def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in items:
            key = (
                item.get("path"),
                item.get("line"),
                item.get("raw_reference"),
                item.get("resolved_object"),
                item.get("resolved_column"),
            )
            existing = unique.get(key)
            if existing is None:
                unique[key] = item
            elif (
                existing.get("dependency_kind") == "transitive"
                and item.get("dependency_kind") == "direct"
            ):
                unique[key] = item
        return sorted(
            unique.values(),
            key=lambda item: (
                str(item.get("path", "")),
                int(item.get("line") or 0),
                str(item.get("raw_reference", "")),
            ),
        )

    confirmed = deduplicate(confirmed)
    possible = deduplicate(possible)
    combined_count = len(confirmed) + len(possible)
    truncated = (
        repository_index["truncated"]
        or combined_count > max_results
    )

    confirmed = confirmed[:max_results]
    remaining = max(0, max_results - len(confirmed))
    possible = possible[:remaining]

    return {
        "revision": commit,
        "dialect": "bigquery",
        "symbol": safe_symbol,
        "symbol_type": symbol_type,
        "references": confirmed,
        "possible_references": possible,
        "direct_reference_count": sum(
            1 for item in confirmed + possible
            if item.get("dependency_kind") == "direct"
        ),
        "transitive_reference_count": sum(
            1 for item in confirmed + possible
            if item.get("dependency_kind") == "transitive"
        ),
        "ignored_count": ignored_count,
        "scanned_file_count": repository_index["scanned_file_count"],
        "requested_file_count": repository_index["requested_file_count"],
        "parse_errors": repository_index["parse_errors"],
        "skipped_files": repository_index["skipped_files"],
        "candidate_count": total_candidates,
        "truncated": truncated,
    }

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
