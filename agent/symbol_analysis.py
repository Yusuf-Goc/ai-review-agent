import re
from pathlib import PurePosixPath
from typing import Any


SUPPORTED_EXTENSIONS = {".py", ".go", ".sql"}


def _python_symbol(line: str) -> tuple[str, str] | None:
    function_match = re.match(
        r"^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(",
        line,
    )
    if function_match:
        symbol_type = "method" if function_match.group(1) else "function"
        return function_match.group(2), symbol_type

    class_match = re.match(r"^\s*class\s+([A-Za-z_]\w*)\b", line)
    if class_match:
        return class_match.group(1), "class"

    variable_match = re.match(
        r"^([A-Za-z_]\w*)\s*(?::[^=]+)?=(?!=)",
        line,
    )
    if variable_match:
        return variable_match.group(1), "variable"

    return None


def _go_symbol(line: str) -> tuple[str, str] | None:
    function_match = re.match(
        r"^\s*func\s*(?P<receiver>\([^)]*\)\s*)?"
        r"(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]+\]\s*)?\(",
        line,
    )
    if function_match:
        symbol_type = "method" if function_match.group("receiver") else "function"
        return function_match.group("name"), symbol_type

    struct_match = re.match(
        r"^\s*type\s+([A-Za-z_]\w*)\s+struct\b",
        line,
    )
    if struct_match:
        return struct_match.group(1), "struct"

    variable_match = re.match(
        r"^\s*(?:var|const)\s+([A-Za-z_]\w*)\b",
        line,
    )
    if variable_match:
        return variable_match.group(1), "variable"

    return None


def _clean_sql_identifier(value: str) -> str:
    return value.strip('`"[]').rstrip(";,(")


def _sql_symbol(line: str) -> tuple[str, str] | None:
    object_match = re.match(
        r"^\s*(?:CREATE|ALTER|DROP)"
        r"(?:\s+OR\s+REPLACE)?\s+"
        r"(TABLE|VIEW|FUNCTION|PROCEDURE|TRIGGER)\s+"
        r"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
        r"([`\"\[\]A-Za-z_][`\"\[\]A-Za-z0-9_.$]*)",
        line,
        re.IGNORECASE,
    )
    if not object_match:
        return None

    object_type = object_match.group(1).lower()
    symbol = _clean_sql_identifier(object_match.group(2))
    symbol_type = {
        "table": "table",
        "view": "table",
        "function": "function",
        "procedure": "function",
        "trigger": "unknown",
    }[object_type]
    return symbol, symbol_type


def detect_symbol(path: str, line: str) -> tuple[str, str] | None:
    extension = PurePosixPath(path).suffix.lower()

    if extension == ".py":
        return _python_symbol(line)
    if extension == ".go":
        return _go_symbol(line)
    if extension == ".sql":
        return _sql_symbol(line)

    return None


def _changed_lines(hunk: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        line
        for line in hunk.get("lines", [])
        if line.get("kind") in {"added", "removed"}
    ]


def extract_changed_symbols(review_payload: dict[str, Any]) -> list[dict[str, Any]]:
    events: dict[tuple[str, str, str], dict[str, Any]] = {}

    for file_payload in review_payload.get("files", []):
        path = file_payload.get("path", "")
        extension = PurePosixPath(path).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            continue

        for hunk in file_payload.get("hunks", []):
            changed_lines = _changed_lines(hunk)
            if not changed_lines:
                continue

            section_header = hunk.get("section_header") or ""
            section_symbol = detect_symbol(path, section_header)
            if section_symbol:
                name, symbol_type = section_symbol
                key = (path, name, symbol_type)
                event = events.setdefault(
                    key,
                    {
                        "file": path,
                        "symbol": name,
                        "symbol_type": symbol_type,
                        "change_kinds": set(),
                        "source_lines": [],
                        "target_lines": [],
                        "detected_from": set(),
                    },
                )
                event["change_kinds"].update({"added", "removed"})
                event["detected_from"].add("hunk_header")
                if hunk.get("source_start") is not None:
                    event["source_lines"].append(hunk["source_start"])
                if hunk.get("target_start") is not None:
                    event["target_lines"].append(hunk["target_start"])

            for line in changed_lines:
                symbol = detect_symbol(path, line.get("content", ""))
                if not symbol:
                    continue

                name, symbol_type = symbol
                key = (path, name, symbol_type)
                event = events.setdefault(
                    key,
                    {
                        "file": path,
                        "symbol": name,
                        "symbol_type": symbol_type,
                        "change_kinds": set(),
                        "source_lines": [],
                        "target_lines": [],
                        "detected_from": set(),
                    },
                )
                kind = line.get("kind")
                event["change_kinds"].add(kind)
                event["detected_from"].add("changed_declaration")

                if line.get("source_line") is not None:
                    event["source_lines"].append(line["source_line"])
                if line.get("target_line") is not None:
                    event["target_lines"].append(line["target_line"])

    result = []
    for event in events.values():
        change_kinds = event.pop("change_kinds")
        if change_kinds == {"added"}:
            change_type = "added"
        elif change_kinds == {"removed"}:
            change_type = "deleted"
        else:
            change_type = "modified"

        event["change_type"] = change_type
        event["source_lines"] = sorted(set(event["source_lines"]))
        event["target_lines"] = sorted(set(event["target_lines"]))
        event["detected_from"] = sorted(event["detected_from"])
        result.append(event)

    return sorted(
        result,
        key=lambda item: (
            item["file"],
            item["symbol"],
            item["symbol_type"],
        ),
    )
