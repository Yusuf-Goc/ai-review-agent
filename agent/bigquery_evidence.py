from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Token:
    value: str
    upper: str
    kind: str
    line: int


_IDENTIFIER_KINDS = {"word", "quoted_identifier"}
_SOURCE_KEYWORDS = {"FROM", "JOIN", "UPDATE", "INTO", "USING"}
_RESERVED_WORDS = {
    "ALL", "AND", "ANY", "ARRAY", "AS", "ASC", "ASSERT_ROWS_MODIFIED",
    "AT", "BETWEEN", "BY", "CASE", "CAST", "CLUSTER", "COLLATE",
    "CONTAINS", "CREATE", "CROSS", "CUBE", "CURRENT", "DEFAULT",
    "DEFINE", "DESC", "DISTINCT", "ELSE", "END", "ENUM", "ESCAPE",
    "EXCEPT", "EXCLUDE", "EXISTS", "EXTRACT", "FALSE", "FETCH",
    "FOLLOWING", "FOR", "FROM", "FULL", "GROUP", "GROUPING", "GROUPS",
    "HASH", "HAVING", "IF", "IGNORE", "IN", "INNER", "INTERSECT",
    "INTERVAL", "INTO", "IS", "JOIN", "LATERAL", "LEFT", "LIKE",
    "LIMIT", "LOOKUP", "MERGE", "NATURAL", "NEW", "NO", "NOT", "NULL",
    "NULLS", "OF", "ON", "OR", "ORDER", "OUTER", "OVER", "PARTITION",
    "PRECEDING", "PROTO", "QUALIFY", "RANGE", "RECURSIVE", "RESPECT",
    "RIGHT", "ROLLUP", "ROWS", "SELECT", "SET", "SOME", "STRUCT",
    "TABLESAMPLE", "THEN", "TO", "TREAT", "TRUE", "UNBOUNDED", "UNION",
    "UNNEST", "USING", "WHEN", "WHERE", "WINDOW", "WITH", "WITHIN",
}
_CONSTRAINT_PREFIXES = {
    "CHECK", "CLUSTER", "CONSTRAINT", "FOREIGN", "OPTIONS", "PARTITION",
    "PRIMARY", "UNIQUE",
}
_CLAUSE_KEYWORDS = {
    "SELECT", "FROM", "JOIN", "ON", "WHERE", "GROUP", "ORDER", "HAVING",
    "QUALIFY", "UPDATE", "SET", "INSERT", "MERGE", "USING", "DELETE",
}


def _tokenize(sql_text: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    line = 1
    length = len(sql_text)

    while index < length:
        char = sql_text[index]

        if char.isspace():
            if char == "\n":
                line += 1
            index += 1
            continue

        if sql_text.startswith("--", index):
            index += 2
            while index < length and sql_text[index] != "\n":
                index += 1
            continue

        if sql_text.startswith("/*", index):
            index += 2
            while index < length and not sql_text.startswith("*/", index):
                if sql_text[index] == "\n":
                    line += 1
                index += 1
            index = min(length, index + 2)
            continue

        if char in {"'", '"'}:
            quote = char
            index += 1
            while index < length:
                if sql_text[index] == "\n":
                    line += 1
                if sql_text[index] == quote:
                    if index + 1 < length and sql_text[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                if sql_text[index] == "\\" and index + 1 < length:
                    index += 2
                    continue
                index += 1
            continue

        if char == "`":
            token_line = line
            index += 1
            value_chars: list[str] = []
            while index < length:
                if sql_text[index] == "\n":
                    line += 1
                if sql_text[index] == "`":
                    index += 1
                    break
                if sql_text[index] == "\\" and index + 1 < length:
                    value_chars.append(sql_text[index + 1])
                    index += 2
                    continue
                value_chars.append(sql_text[index])
                index += 1
            value = "".join(value_chars)
            tokens.append(_Token(value, value.upper(), "quoted_identifier", token_line))
            continue

        if char == "@" and index + 1 < length:
            token_line = line
            start = index
            index += 1
            while index < length and (sql_text[index].isalnum() or sql_text[index] in {"_", "$"}):
                index += 1
            value = sql_text[start:index]
            tokens.append(_Token(value, value.upper(), "parameter", token_line))
            continue

        if char.isalpha() or char == "_":
            token_line = line
            start = index
            index += 1
            while index < length and (sql_text[index].isalnum() or sql_text[index] in {"_", "$"}):
                index += 1
            value = sql_text[start:index]
            tokens.append(_Token(value, value.upper(), "word", token_line))
            continue

        if char.isdigit():
            token_line = line
            start = index
            index += 1
            while index < length and (sql_text[index].isalnum() or sql_text[index] in {"_", "."}):
                index += 1
            value = sql_text[start:index]
            tokens.append(_Token(value, value.upper(), "number", token_line))
            continue

        tokens.append(_Token(char, char, "symbol", line))
        index += 1

    return tokens


def _split_statements(tokens: list[_Token]) -> list[list[_Token]]:
    statements: list[list[_Token]] = []
    current: list[_Token] = []
    depth = 0

    for token in tokens:
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth = max(0, depth - 1)

        if token.value == ";" and depth == 0:
            if current:
                statements.append(current)
                current = []
            continue

        current.append(token)

    if current:
        statements.append(current)
    return statements


def _is_identifier(token: _Token | None) -> bool:
    return token is not None and token.kind in _IDENTIFIER_KINDS


def _identifier_parts(
    tokens: list[_Token],
    start: int,
) -> tuple[list[str], int, set[int]]:
    if start >= len(tokens) or not _is_identifier(tokens[start]):
        return [], start, set()

    token = tokens[start]
    indexes = {start}
    if token.kind == "quoted_identifier":
        parts = [part for part in token.value.split(".") if part]
        return parts, start + 1, indexes

    parts = [token.value]
    index = start + 1
    while (
        index + 1 < len(tokens)
        and tokens[index].value == "."
        and _is_identifier(tokens[index + 1])
    ):
        indexes.update({index, index + 1})
        next_token = tokens[index + 1]
        if next_token.kind == "quoted_identifier":
            parts.extend(part for part in next_token.value.split(".") if part)
        else:
            parts.append(next_token.value)
        index += 2

    return parts, index, indexes


def _normalize_object(parts: list[str]) -> dict[str, Any]:
    project = None
    dataset = None
    object_name = None

    if len(parts) == 1:
        object_name = parts[0]
    elif len(parts) == 2:
        dataset, object_name = parts
    elif len(parts) >= 3:
        project, dataset, object_name = parts[-3:]

    qualified = ".".join(
        part for part in (project, dataset, object_name) if part
    )
    return {
        "project": project,
        "dataset": dataset,
        "object": object_name,
        "qualified_name": qualified,
    }


def _find_matching_paren(tokens: list[_Token], open_index: int) -> int | None:
    if open_index >= len(tokens) or tokens[open_index].value != "(":
        return None
    depth = 0
    for index in range(open_index, len(tokens)):
        if tokens[index].value == "(":
            depth += 1
        elif tokens[index].value == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _collect_ctes(tokens: list[_Token]) -> tuple[list[dict[str, Any]], set[int]]:
    ctes: list[dict[str, Any]] = []
    consumed: set[int] = set()

    for with_index, token in enumerate(tokens):
        if token.upper != "WITH":
            continue

        index = with_index + 1
        if index < len(tokens) and tokens[index].upper == "RECURSIVE":
            consumed.add(index)
            index += 1

        while index < len(tokens):
            if not _is_identifier(tokens[index]):
                break

            name = tokens[index].value
            name_line = tokens[index].line
            consumed.add(index)
            index += 1

            if index < len(tokens) and tokens[index].value == "(":
                close_index = _find_matching_paren(tokens, index)
                if close_index is None:
                    break
                consumed.update(range(index, close_index + 1))
                index = close_index + 1

            if index >= len(tokens) or tokens[index].upper != "AS":
                break
            consumed.add(index)
            index += 1

            if index >= len(tokens) or tokens[index].value != "(":
                break
            close_index = _find_matching_paren(tokens, index)
            if close_index is None:
                break

            ctes.append({
                "name": name,
                "line": name_line,
                "confidence": "ignored",
                "reason": "CTE sorgu ici bir kaynaktir; fiziksel BigQuery tablosu degildir.",
            })
            consumed.update({with_index, index, close_index})
            index = close_index + 1

            if index < len(tokens) and tokens[index].value == ",":
                consumed.add(index)
                index += 1
                continue
            break

    unique: dict[str, dict[str, Any]] = {}
    for item in ctes:
        unique.setdefault(item["name"].casefold(), item)
    return list(unique.values()), consumed


def _parse_alias(tokens: list[_Token], index: int) -> tuple[str | None, int, set[int]]:
    consumed: set[int] = set()
    if index < len(tokens) and tokens[index].upper == "AS":
        consumed.add(index)
        index += 1
        if index < len(tokens) and _is_identifier(tokens[index]):
            consumed.add(index)
            return tokens[index].value, index + 1, consumed
        return None, index, consumed

    if (
        index < len(tokens)
        and _is_identifier(tokens[index])
        and tokens[index].upper not in _RESERVED_WORDS
    ):
        consumed.add(index)
        return tokens[index].value, index + 1, consumed

    return None, index, consumed


def _source_clause(tokens: list[_Token], index: int) -> tuple[str | None, int]:
    token = tokens[index]
    if token.upper in {"FROM", "JOIN", "UPDATE", "USING"}:
        return token.upper.lower(), index + 1
    if token.upper == "INTO" and index > 0 and tokens[index - 1].upper in {"INSERT", "MERGE"}:
        return f"{tokens[index - 1].upper.lower()}_into", index + 1
    return None, index


def _collect_sources(
    tokens: list[_Token],
    cte_names: set[str],
) -> tuple[list[dict[str, Any]], set[int]]:
    sources: list[dict[str, Any]] = []
    consumed: set[int] = set()
    index = 0

    while index < len(tokens):
        clause, source_index = _source_clause(tokens, index)
        if clause is None:
            index += 1
            continue

        consumed.add(index)
        index = source_index
        if index >= len(tokens):
            continue

        if tokens[index].upper == "UNNEST" and index + 1 < len(tokens) and tokens[index + 1].value == "(":
            open_index = index + 1
            close_index = _find_matching_paren(tokens, open_index)
            if close_index is None:
                index += 1
                continue
            alias, next_index, alias_indexes = _parse_alias(tokens, close_index + 1)
            consumed.update(range(index, close_index + 1))
            consumed.update(alias_indexes)
            sources.append({
                "line": tokens[index].line,
                "clause": clause,
                "raw_name": "UNNEST",
                "project": None,
                "dataset": None,
                "object": None,
                "qualified_name": "",
                "alias": alias,
                "source_type": "unnest",
                "confidence": "possible",
                "reason": "UNNEST kaynaginin alan lineage'i ilk surumde kesin cozulmemektedir.",
            })
            index = next_index
            continue

        if tokens[index].value == "(":
            close_index = _find_matching_paren(tokens, index)
            if close_index is None:
                index += 1
                continue
            alias, next_index, alias_indexes = _parse_alias(tokens, close_index + 1)
            consumed.update(range(index, close_index + 1))
            consumed.update(alias_indexes)
            sources.append({
                "line": tokens[index].line,
                "clause": clause,
                "raw_name": "subquery",
                "project": None,
                "dataset": None,
                "object": None,
                "qualified_name": "",
                "alias": alias,
                "source_type": "subquery",
                "confidence": "possible",
                "reason": "Alt sorgu kolon lineage'i ilk surumde kesin cozulmemektedir.",
            })
            index = next_index
            continue

        parts, next_index, identifier_indexes = _identifier_parts(tokens, index)
        if not parts:
            index += 1
            continue

        alias, final_index, alias_indexes = _parse_alias(tokens, next_index)
        consumed.update(identifier_indexes)
        consumed.update(alias_indexes)
        normalized = _normalize_object(parts)
        cte_match = len(parts) == 1 and parts[0].casefold() in cte_names

        if cte_match:
            source_type = "cte"
            confidence = "ignored"
            reason = "Kaynak fiziksel tablo degil, ayni sorguda tanimlanan CTE'dir."
        else:
            source_type = "table"
            confidence = "confirmed" if normalized["dataset"] else "possible"
            reason = (
                "Dataset veya project ile nitelendirilmis BigQuery tablo kaynagi."
                if confidence == "confirmed"
                else "Tablo adi nitelendirilmemis; default dataset bilinmedigi icin kesin cozumlenemedi."
            )

        sources.append({
            "line": tokens[index].line,
            "clause": clause,
            "raw_name": ".".join(parts),
            **normalized,
            "alias": alias or normalized["object"],
            "source_type": source_type,
            "confidence": confidence,
            "reason": reason,
        })
        index = final_index

    return sources, consumed


def _parse_create_definition(
    tokens: list[_Token],
    start: int,
) -> tuple[list[dict[str, Any]], set[int], set[str]]:
    definitions: list[dict[str, Any]] = []
    consumed: set[int] = {start}
    parameters: set[str] = set()
    index = start + 1

    if index + 1 < len(tokens) and tokens[index].upper == "OR" and tokens[index + 1].upper == "REPLACE":
        consumed.update({index, index + 1})
        index += 2

    if index < len(tokens) and tokens[index].upper in {"TEMP", "TEMPORARY"}:
        consumed.add(index)
        index += 1

    object_type = None
    if index + 1 < len(tokens) and tokens[index].upper == "TABLE" and tokens[index + 1].upper == "FUNCTION":
        object_type = "table_function"
        consumed.update({index, index + 1})
        index += 2
    elif index < len(tokens) and tokens[index].upper in {"TABLE", "VIEW", "FUNCTION", "PROCEDURE", "SCHEMA"}:
        object_type = tokens[index].upper.lower()
        consumed.add(index)
        index += 1
    else:
        return definitions, consumed, parameters

    if index + 2 < len(tokens) and tokens[index].upper == "IF" and tokens[index + 1].upper == "NOT" and tokens[index + 2].upper == "EXISTS":
        consumed.update({index, index + 1, index + 2})
        index += 3

    parts, next_index, object_indexes = _identifier_parts(tokens, index)
    if not parts:
        return definitions, consumed, parameters
    consumed.update(object_indexes)
    normalized = _normalize_object(parts)
    definitions.append({
        "line": tokens[index].line,
        "action": "create",
        "object_type": object_type,
        "raw_name": ".".join(parts),
        **normalized,
    })

    index = next_index
    if object_type in {"function", "table_function", "procedure"} and index < len(tokens) and tokens[index].value == "(":
        close_index = _find_matching_paren(tokens, index)
        if close_index is not None:
            depth = 0
            segment_start = index + 1
            for cursor in range(index + 1, close_index + 1):
                value = tokens[cursor].value if cursor < close_index else ","
                if value == "(":
                    depth += 1
                elif value == ")":
                    depth = max(0, depth - 1)
                elif value == "," and depth == 0:
                    if segment_start < cursor and _is_identifier(tokens[segment_start]):
                        parameters.add(tokens[segment_start].value.casefold())
                    segment_start = cursor + 1
            consumed.update(range(index, close_index + 1))
            index = close_index + 1

    if object_type == "table" and index < len(tokens) and tokens[index].value == "(":
        close_index = _find_matching_paren(tokens, index)
        if close_index is not None:
            depth = 0
            segment_start = index + 1
            for cursor in range(index + 1, close_index + 1):
                value = tokens[cursor].value if cursor < close_index else ","
                if value == "(":
                    depth += 1
                elif value == ")":
                    depth = max(0, depth - 1)
                elif value == "," and depth == 0:
                    if segment_start < cursor:
                        first = tokens[segment_start]
                        if _is_identifier(first) and first.upper not in _CONSTRAINT_PREFIXES:
                            column_name = first.value
                            definitions.append({
                                "line": first.line,
                                "action": "create",
                                "object_type": "column",
                                "raw_name": column_name,
                                "project": normalized["project"],
                                "dataset": normalized["dataset"],
                                "object": normalized["object"],
                                "column_path": [column_name],
                                "qualified_name": ".".join(
                                    part
                                    for part in (
                                        normalized["project"],
                                        normalized["dataset"],
                                        normalized["object"],
                                        column_name,
                                    )
                                    if part
                                ),
                            })
                    segment_start = cursor + 1
            consumed.update(range(index, close_index + 1))

    return definitions, consumed, parameters


def _parse_alter_or_drop(
    tokens: list[_Token],
    start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    definitions: list[dict[str, Any]] = []
    mutations: list[dict[str, Any]] = []
    consumed: set[int] = {start}
    action = tokens[start].upper.lower()
    index = start + 1

    if index >= len(tokens) or tokens[index].upper not in {"TABLE", "VIEW", "FUNCTION", "PROCEDURE", "SCHEMA"}:
        return definitions, mutations, consumed
    object_type = tokens[index].upper.lower()
    consumed.add(index)
    index += 1

    if index + 1 < len(tokens) and tokens[index].upper == "IF" and tokens[index + 1].upper == "EXISTS":
        consumed.update({index, index + 1})
        index += 2

    parts, next_index, object_indexes = _identifier_parts(tokens, index)
    if not parts:
        return definitions, mutations, consumed
    consumed.update(object_indexes)
    normalized = _normalize_object(parts)
    definitions.append({
        "line": tokens[index].line,
        "action": action,
        "object_type": object_type,
        "raw_name": ".".join(parts),
        **normalized,
    })
    index = next_index

    if action != "alter" or object_type != "table":
        return definitions, mutations, consumed

    while index < len(tokens):
        current = tokens[index].upper
        if current == "RENAME" and index + 3 < len(tokens) and tokens[index + 1].upper == "COLUMN":
            old_name = tokens[index + 2].value if _is_identifier(tokens[index + 2]) else None
            if old_name and tokens[index + 3].upper == "TO" and index + 4 < len(tokens) and _is_identifier(tokens[index + 4]):
                new_name = tokens[index + 4].value
                mutations.append({
                    "line": tokens[index].line,
                    "action": "rename_column",
                    **normalized,
                    "column": old_name,
                    "new_column": new_name,
                })
                consumed.update(range(index, index + 5))
                index += 5
                continue
        if current in {"ADD", "DROP"}:
            mutation_action = "add_column" if current == "ADD" else "drop_column"
            cursor = index + 1
            if cursor < len(tokens) and tokens[cursor].upper == "COLUMN":
                cursor += 1
            if cursor + 1 < len(tokens) and tokens[cursor].upper == "IF" and tokens[cursor + 1].upper in {"EXISTS", "NOT"}:
                if tokens[cursor + 1].upper == "NOT" and cursor + 2 < len(tokens) and tokens[cursor + 2].upper == "EXISTS":
                    cursor += 3
                else:
                    cursor += 2
            if cursor < len(tokens) and _is_identifier(tokens[cursor]):
                mutations.append({
                    "line": tokens[index].line,
                    "action": mutation_action,
                    **normalized,
                    "column": tokens[cursor].value,
                })
                consumed.update(range(index, cursor + 1))
                index = cursor + 1
                continue
        index += 1

    return definitions, mutations, consumed


def _collect_definitions(
    tokens: list[_Token],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int], set[str]]:
    definitions: list[dict[str, Any]] = []
    mutations: list[dict[str, Any]] = []
    consumed: set[int] = set()
    parameters: set[str] = set()

    for index, token in enumerate(tokens):
        if token.upper == "CREATE":
            parsed, used, routine_parameters = _parse_create_definition(tokens, index)
            definitions.extend(parsed)
            consumed.update(used)
            parameters.update(routine_parameters)
        elif token.upper in {"ALTER", "DROP"}:
            parsed, parsed_mutations, used = _parse_alter_or_drop(tokens, index)
            definitions.extend(parsed)
            mutations.extend(parsed_mutations)
            consumed.update(used)

    return definitions, mutations, consumed, parameters


def _clause_at(tokens: list[_Token], index: int) -> str:
    clause = "unknown"
    for cursor in range(index):
        upper = tokens[cursor].upper
        if upper in _CLAUSE_KEYWORDS:
            clause = upper.lower()
    return clause


def _reference_from_source(
    *,
    path: str,
    token: _Token,
    raw_reference: str,
    column_path: list[str],
    source: dict[str, Any],
    clause: str,
) -> dict[str, Any]:
    source_type = source.get("source_type")
    if source_type == "cte":
        confidence = "ignored"
        reason = "Referans fiziksel tablo yerine sorgu ici CTE aliasina baglidir."
    elif source_type in {"subquery", "unnest"}:
        confidence = "possible"
        reason = "Alt sorgu veya UNNEST kolon lineage'i ilk surumde kesin cozulmemektedir."
    else:
        confidence = source.get("confidence", "possible")
        reason = (
            "Alias, dataset ile nitelendirilmis BigQuery tablo kaynagina baglidir."
            if confidence == "confirmed"
            else "Alias bir tabloya baglidir ancak default dataset bilinmedigi icin tam nesne kimligi kesin degildir."
        )

    return {
        "path": path,
        "line": token.line,
        "raw_reference": raw_reference,
        "reference_type": "column",
        "confidence": confidence,
        "project": source.get("project"),
        "dataset": source.get("dataset"),
        "object": source.get("object"),
        "resolved_object": source.get("qualified_name") or None,
        "column_path": column_path,
        "resolved_column": ".".join(column_path),
        "clause": clause,
        "reason": reason,
    }


def _collect_references(
    tokens: list[_Token],
    *,
    path: str,
    sources: list[dict[str, Any]],
    cte_names: set[str],
    consumed: set[int],
    parameters: set[str],
) -> list[dict[str, Any]]:
    aliases: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        alias = source.get("alias")
        if isinstance(alias, str) and alias:
            aliases.setdefault(alias.casefold(), []).append(source)

    physical_sources = [item for item in sources if item.get("source_type") == "table"]
    references: list[dict[str, Any]] = []
    index = 0

    while index < len(tokens):
        if index in consumed or not _is_identifier(tokens[index]):
            index += 1
            continue

        parts, next_index, indexes = _identifier_parts(tokens, index)
        if len(parts) < 2:
            index += 1
            continue

        if indexes & consumed:
            index = max(index + 1, next_index)
            continue

        first_key = parts[0].casefold()
        raw_reference = ".".join(parts)
        clause = _clause_at(tokens, index)

        if first_key in parameters:
            index = next_index
            continue

        alias_sources = aliases.get(first_key, [])
        if len(alias_sources) == 1:
            references.append(
                _reference_from_source(
                    path=path,
                    token=tokens[index],
                    raw_reference=raw_reference,
                    column_path=parts[1:],
                    source=alias_sources[0],
                    clause=clause,
                )
            )
            index = next_index
            continue
        if len(alias_sources) > 1:
            references.append({
                "path": path,
                "line": tokens[index].line,
                "raw_reference": raw_reference,
                "reference_type": "column",
                "confidence": "possible",
                "project": None,
                "dataset": None,
                "object": None,
                "resolved_object": None,
                "column_path": parts[1:],
                "resolved_column": ".".join(parts[1:]),
                "clause": clause,
                "reason": "Ayni alias birden fazla kaynaga baglandigi icin referans kesin cozulmedi.",
            })
            index = next_index
            continue

        if first_key in cte_names:
            references.append({
                "path": path,
                "line": tokens[index].line,
                "raw_reference": raw_reference,
                "reference_type": "column",
                "confidence": "ignored",
                "project": None,
                "dataset": None,
                "object": None,
                "resolved_object": None,
                "column_path": parts[1:],
                "resolved_column": ".".join(parts[1:]),
                "clause": clause,
                "reason": "Referans sorgu ici CTE'ye aittir; fiziksel tablo kaniti sayilmaz.",
            })
            index = next_index
            continue

        matched_source = None
        matched_prefix_length = 0
        folded_parts = [part.casefold() for part in parts]
        for source in physical_sources:
            source_parts = [
                part.casefold()
                for part in (
                    source.get("project"),
                    source.get("dataset"),
                    source.get("object"),
                )
                if isinstance(part, str) and part
            ]
            candidate_prefixes = [source_parts]
            if source.get("object"):
                candidate_prefixes.append([str(source["object"]).casefold()])
            if source.get("dataset") and source.get("object"):
                candidate_prefixes.append([
                    str(source["dataset"]).casefold(),
                    str(source["object"]).casefold(),
                ])
            for prefix in candidate_prefixes:
                if prefix and folded_parts[: len(prefix)] == prefix and len(parts) > len(prefix):
                    if len(prefix) > matched_prefix_length:
                        matched_source = source
                        matched_prefix_length = len(prefix)

        if matched_source is not None:
            references.append(
                _reference_from_source(
                    path=path,
                    token=tokens[index],
                    raw_reference=raw_reference,
                    column_path=parts[matched_prefix_length:],
                    source=matched_source,
                    clause=clause,
                )
            )
        elif len(physical_sources) == 1:
            references.append(
                _reference_from_source(
                    path=path,
                    token=tokens[index],
                    raw_reference=raw_reference,
                    column_path=parts,
                    source={**physical_sources[0], "confidence": "possible"},
                    clause=clause,
                )
            )

        index = next_index

    return references


def analyze_bigquery_sql(
    sql_text: str,
    *,
    path: str,
) -> dict[str, Any]:
    """BigQuery GoogleSQL icin deterministik tanim ve referans kaniti cikarir.

    Bu katman tam bir SQL parser degildir. Kesin cozumlenebilen alias/tablo
    baglantilarini ``confirmed``, default dataset veya lineage gerektiren
    durumlari ``possible``, CTE gibi fiziksel tablo olmayan eslesmeleri ise
    ``ignored`` olarak isaretler.
    """
    if not isinstance(sql_text, str):
        raise TypeError("sql_text metin olmalidir.")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path bos olamaz.")

    all_definitions: list[dict[str, Any]] = []
    all_mutations: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []
    all_references: list[dict[str, Any]] = []
    all_ctes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    tokens = _tokenize(sql_text)
    statements = _split_statements(tokens)

    for statement_index, statement in enumerate(statements, start=1):
        try:
            ctes, cte_consumed = _collect_ctes(statement)
            cte_names = {item["name"].casefold() for item in ctes}
            definitions, mutations, definition_consumed, parameters = _collect_definitions(statement)
            sources, source_consumed = _collect_sources(statement, cte_names)
            references = _collect_references(
                statement,
                path=path,
                sources=sources,
                cte_names=cte_names,
                consumed=cte_consumed | definition_consumed | source_consumed,
                parameters=parameters,
            )

            for collection in (ctes, definitions, mutations, sources, references):
                for item in collection:
                    item["statement"] = statement_index

            all_ctes.extend(ctes)
            all_definitions.extend(definitions)
            all_mutations.extend(mutations)
            all_sources.extend(sources)
            all_references.extend(references)
        except (IndexError, TypeError, ValueError) as exc:
            errors.append({
                "statement": statement_index,
                "message": str(exc),
            })

    return {
        "dialect": "bigquery",
        "path": path,
        "definitions": all_definitions,
        "mutations": all_mutations,
        "sources": all_sources,
        "references": all_references,
        "ctes": all_ctes,
        "errors": errors,
    }
