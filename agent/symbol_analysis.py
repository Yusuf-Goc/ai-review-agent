import re
from pathlib import PurePosixPath
from typing import Any

from agent.bigquery_evidence import analyze_bigquery_sql


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
        r"(TABLE\s+FUNCTION|TABLE|VIEW|FUNCTION|PROCEDURE|TRIGGER)\s+"
        r"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
        r"(`[^`]+`|[A-Za-z_][A-Za-z0-9_.$-]*)",
        line,
        re.IGNORECASE,
    )
    if not object_match:
        return None

    object_type = re.sub(r"\s+", "_", object_match.group(1).lower())
    symbol = _clean_sql_identifier(object_match.group(2))
    symbol_type = {
        "table": "table",
        "view": "table",
        "function": "function",
        "table_function": "function",
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


def _is_comment_or_blank(path: str, line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True

    extension = PurePosixPath(path).suffix.lower()
    if extension == ".py":
        return stripped.startswith("#")
    if extension == ".go":
        return stripped.startswith(("//", "/*", "*", "*/"))
    if extension == ".sql":
        return stripped.startswith(("--", "/*", "*", "*/"))
    return False



def _event(
    events: dict[tuple[str, str, str], dict[str, Any]],
    *,
    path: str,
    symbol: str,
    symbol_type: str,
) -> dict[str, Any]:
    key = (path, symbol, symbol_type)
    return events.setdefault(
        key,
        {
            "file": path,
            "symbol": symbol,
            "symbol_type": symbol_type,
            "change_kinds": set(),
            "source_lines": [],
            "target_lines": [],
            "detected_from": set(),
        },
    )


def _record_event(
    events: dict[tuple[str, str, str], dict[str, Any]],
    *,
    path: str,
    symbol: str,
    symbol_type: str,
    change_type: str,
    source_lines: set[int],
    target_lines: set[int],
    detected_from: str,
) -> None:
    if not symbol:
        return

    event = _event(
        events,
        path=path,
        symbol=symbol,
        symbol_type=symbol_type,
    )
    if change_type == "added":
        event["change_kinds"].add("added")
    elif change_type == "deleted":
        event["change_kinds"].add("removed")
    else:
        event["change_kinds"].update({"added", "removed"})

    event["source_lines"].extend(source_lines)
    event["target_lines"].extend(target_lines)
    event["detected_from"].add(detected_from)


def _sql_fragment_side(
    path: str,
    hunk: dict[str, Any],
    *,
    side: str,
) -> tuple[str, dict[int, dict[str, Any]]]:
    if side not in {"base", "head"}:
        raise ValueError("side base veya head olmalidir.")

    selected: list[str] = []
    line_map: dict[int, dict[str, Any]] = {}
    excluded_kind = "added" if side == "base" else "removed"
    changed_kind = "removed" if side == "base" else "added"
    number_field = "source_line" if side == "base" else "target_line"

    section_header = hunk.get("section_header") or ""
    if detect_symbol(path, section_header):
        hunk_contents = {
            str(line.get("content", "")).strip()
            for line in hunk.get("lines", [])
        }
        if section_header.strip() not in hunk_contents:
            selected.append(section_header)
            fallback_line = hunk.get(
                "source_start" if side == "base" else "target_start"
            )
            line_map[len(selected)] = {
                "actual_line": fallback_line,
                "changed": False,
            }

    for line in hunk.get("lines", []):
        kind = line.get("kind")
        if kind in {excluded_kind, "truncated"}:
            continue

        selected.append(str(line.get("content", "")))
        line_map[len(selected)] = {
            "actual_line": line.get(number_field),
            "changed": kind == changed_kind,
        }

    return "\n".join(selected), line_map


def _sql_symbol_type(object_type: Any) -> str | None:
    normalized = str(object_type or "").casefold()
    if normalized in {"table", "view"}:
        return "table"
    if normalized == "column":
        return "column"
    if normalized in {"function", "table_function", "procedure"}:
        return "function"
    return None


def _sql_state(
    states: dict[tuple[str, str], dict[str, Any]],
    *,
    symbol: str,
    symbol_type: str,
    effect: str,
    line: int | None,
) -> None:
    if not symbol or effect not in {"present", "absent", "modified"}:
        return

    state = states.setdefault(
        (symbol, symbol_type),
        {"effects": set(), "lines": set()},
    )
    state["effects"].add(effect)
    if isinstance(line, int):
        state["lines"].add(line)


def _collapsed_sql_effect(state: dict[str, Any] | None) -> str | None:
    if not state:
        return None
    effects = set(state.get("effects", set()))
    if effects == {"present"}:
        return "present"
    if effects == {"absent"}:
        return "absent"
    if effects:
        return "modified"
    return None


def _sql_change_type(
    base_effect: str | None,
    head_effect: str | None,
) -> str | None:
    if base_effect == head_effect:
        if base_effect in {"present", "modified"}:
            return "modified"
        return None

    if "modified" in {base_effect, head_effect}:
        return "modified"

    if head_effect == "present":
        return "added" if base_effect in {None, "absent"} else "modified"
    if head_effect == "absent":
        return "deleted" if base_effect in {None, "present"} else "modified"

    if head_effect is None:
        if base_effect == "present":
            return "deleted"
        if base_effect == "absent":
            return "added"

    return None


def _collect_sql_side_states(
    *,
    path: str,
    sql_text: str,
    line_map: dict[int, dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    states: dict[tuple[str, str], dict[str, Any]] = {}
    if not sql_text.strip():
        return states

    analysis = analyze_bigquery_sql(sql_text, path=path)

    for definition in analysis.get("definitions", []):
        if not isinstance(definition, dict):
            continue
        location = line_map.get(definition.get("line"), {})
        if not location.get("changed"):
            continue

        symbol_type = _sql_symbol_type(definition.get("object_type"))
        symbol = definition.get("qualified_name")
        action = str(definition.get("action", "create")).casefold()
        if not symbol_type or not isinstance(symbol, str):
            continue

        effect = {
            "create": "present",
            "alter": "modified",
            "drop": "absent",
        }.get(action, "modified")
        actual_line = location.get("actual_line")
        _sql_state(
            states,
            symbol=symbol,
            symbol_type=symbol_type,
            effect=effect,
            line=actual_line,
        )

        if symbol_type == "column":
            parent = ".".join(symbol.split(".")[:-1])
            _sql_state(
                states,
                symbol=parent,
                symbol_type="table",
                effect="modified",
                line=actual_line,
            )

    for mutation in analysis.get("mutations", []):
        if not isinstance(mutation, dict):
            continue
        location = line_map.get(mutation.get("line"), {})
        if not location.get("changed"):
            continue

        table_symbol = mutation.get("qualified_name")
        actual_line = location.get("actual_line")
        if not isinstance(table_symbol, str) or not table_symbol:
            continue

        _sql_state(
            states,
            symbol=table_symbol,
            symbol_type="table",
            effect="modified",
            line=actual_line,
        )

        action = str(mutation.get("action", "")).casefold()
        column = mutation.get("column")
        if not isinstance(column, str) or not column:
            continue

        old_symbol = f"{table_symbol}.{column}"
        if action == "add_column":
            _sql_state(
                states,
                symbol=old_symbol,
                symbol_type="column",
                effect="present",
                line=actual_line,
            )
        elif action == "drop_column":
            _sql_state(
                states,
                symbol=old_symbol,
                symbol_type="column",
                effect="absent",
                line=actual_line,
            )
        elif action == "rename_column":
            _sql_state(
                states,
                symbol=old_symbol,
                symbol_type="column",
                effect="absent",
                line=actual_line,
            )
            new_column = mutation.get("new_column")
            if isinstance(new_column, str) and new_column:
                _sql_state(
                    states,
                    symbol=f"{table_symbol}.{new_column}",
                    symbol_type="column",
                    effect="present",
                    line=actual_line,
                )

    return states


def _collect_bigquery_hunk_events(
    events: dict[tuple[str, str, str], dict[str, Any]],
    *,
    path: str,
    hunk: dict[str, Any],
) -> None:
    base_text, base_map = _sql_fragment_side(path, hunk, side="base")
    head_text, head_map = _sql_fragment_side(path, hunk, side="head")
    base_states = _collect_sql_side_states(
        path=path,
        sql_text=base_text,
        line_map=base_map,
    )
    head_states = _collect_sql_side_states(
        path=path,
        sql_text=head_text,
        line_map=head_map,
    )

    for symbol_key in sorted(set(base_states) | set(head_states)):
        base_state = base_states.get(symbol_key)
        head_state = head_states.get(symbol_key)
        change_type = _sql_change_type(
            _collapsed_sql_effect(base_state),
            _collapsed_sql_effect(head_state),
        )
        if change_type is None:
            continue

        symbol, symbol_type = symbol_key
        _record_event(
            events,
            path=path,
            symbol=symbol,
            symbol_type=symbol_type,
            change_type=change_type,
            source_lines=set(base_state.get("lines", set())) if base_state else set(),
            target_lines=set(head_state.get("lines", set())) if head_state else set(),
            detected_from="bigquery_evidence",
        )

def extract_changed_symbols(review_payload: dict[str, Any]) -> list[dict[str, Any]]:
    events: dict[tuple[str, str, str], dict[str, Any]] = {}

    for file_payload in review_payload.get("files", []):
        path = file_payload.get("path", "")
        extension = PurePosixPath(path).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            continue

        if extension == ".sql":
            for hunk in file_payload.get("hunks", []):
                _collect_bigquery_hunk_events(
                    events,
                    path=path,
                    hunk=hunk,
                )
            continue

        for hunk in file_payload.get("hunks", []):
            changed_lines = _changed_lines(hunk)
            if not changed_lines:
                continue

            changed_declarations = {
                detected
                for line in changed_lines
                if (detected := detect_symbol(path, line.get("content", "")))
            }
            section_header = hunk.get("section_header") or ""
            section_symbol = detect_symbol(path, section_header)

            # Unified diff hunk basligi en yakin onceki fonksiyonu gosterebilir.
            # Hunk icinde baska bildirimler acikca degisiyorsa bu baslik yalnizca
            # konum baglamidir; onu degisen sembol saymak rapora gurultu ekler.
            # Bildirim bulunmayan body-only hunklarda ise baslik gercek sembol
            # baglamini sagladigi icin korunur.
            has_meaningful_body_change = any(
                not detect_symbol(path, line.get("content", ""))
                and not _is_comment_or_blank(
                    path,
                    line.get("content", ""),
                )
                for line in changed_lines
            )
            include_section_symbol = bool(
                section_symbol
                and (
                    section_symbol in changed_declarations
                    or (
                        not changed_declarations
                        and has_meaningful_body_change
                    )
                )
            )
            if include_section_symbol:
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
