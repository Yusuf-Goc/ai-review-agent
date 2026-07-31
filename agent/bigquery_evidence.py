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
_TYPE_WORDS = {
    "ARRAY", "BIGNUMERIC", "BOOL", "BYTES", "DATE", "DATETIME",
    "FLOAT64", "GEOGRAPHY", "INT64", "INTERVAL", "JSON", "NUMERIC",
    "RANGE", "STRING", "STRUCT", "TIME", "TIMESTAMP",
}
_UNQUALIFIED_COLUMN_CLAUSES = {
    "select", "on", "where", "group", "order", "having", "qualify", "set",
}
_BIGQUERY_BUILTIN_FUNCTIONS = {
    "ABS", "ACOS", "ACOSH", "ANY_VALUE", "APPROX_COUNT_DISTINCT",
    "APPROX_QUANTILES", "APPROX_TOP_COUNT", "APPROX_TOP_SUM", "ARRAY",
    "ARRAY_AGG", "ARRAY_CONCAT", "ARRAY_LENGTH", "ARRAY_REVERSE",
    "ARRAY_TO_STRING", "ASCII", "ASIN", "ASINH", "ATAN", "ATAN2",
    "ATANH", "AVG", "BIT_AND", "BIT_COUNT", "BIT_OR", "BIT_XOR",
    "BYTE_LENGTH", "CAST", "CEIL", "CEILING", "CHAR_LENGTH",
    "CHARACTER_LENGTH", "CHR", "COALESCE", "CODE_POINTS_TO_BYTES",
    "CODE_POINTS_TO_STRING", "CONCAT", "CONTAINS_SUBSTR", "CORR",
    "COS", "COSH", "COUNT", "COUNTIF", "COVAR_POP", "COVAR_SAMP",
    "CURRENT_DATE", "CURRENT_DATETIME", "CURRENT_TIME",
    "CURRENT_TIMESTAMP", "DATE", "DATE_ADD", "DATE_DIFF", "DATE_SUB",
    "DATE_TRUNC", "DATETIME", "DATETIME_ADD", "DATETIME_DIFF",
    "DATETIME_SUB", "DATETIME_TRUNC", "DENSE_RANK", "DIV", "ENDS_WITH",
    "ERROR", "EXP", "EXTRACT", "FARM_FINGERPRINT", "FIRST_VALUE",
    "FLOOR", "FORMAT", "FORMAT_DATE", "FORMAT_DATETIME", "FORMAT_TIME",
    "FORMAT_TIMESTAMP", "FROM_BASE32", "FROM_BASE64", "GENERATE_ARRAY",
    "GENERATE_DATE_ARRAY", "GENERATE_TIMESTAMP_ARRAY", "GREATEST",
    "IEEE_DIVIDE", "IF", "IFNULL", "INITCAP", "INSTR", "IS_INF",
    "IS_NAN", "JSON_EXTRACT", "JSON_EXTRACT_ARRAY",
    "JSON_EXTRACT_SCALAR", "JSON_QUERY", "JSON_QUERY_ARRAY", "JSON_VALUE",
    "JSON_VALUE_ARRAY", "LAG", "LAST_DAY", "LAST_VALUE", "LEAD",
    "LEAST", "LEFT", "LENGTH", "LN", "LOG", "LOG10", "LOGICAL_AND",
    "LOGICAL_OR", "LOWER", "LPAD", "LTRIM", "MAX", "MD5", "MIN",
    "MOD", "NET_HOST", "NET_IP_FROM_STRING", "NET_IP_TO_STRING",
    "NET_PUBLIC_SUFFIX", "NET_REG_DOMAIN", "NORMALIZE",
    "NORMALIZE_AND_CASEFOLD", "NTH_VALUE", "NTILE", "NULLIF", "OCTET_LENGTH",
    "PARSE_DATE", "PARSE_DATETIME", "PARSE_JSON", "PARSE_NUMERIC",
    "PARSE_TIME", "PARSE_TIMESTAMP", "PERCENT_RANK", "POW", "POWER",
    "RANK", "REGEXP_CONTAINS", "REGEXP_EXTRACT", "REGEXP_EXTRACT_ALL",
    "REGEXP_INSTR", "REGEXP_REPLACE", "REPEAT", "REPLACE", "REVERSE",
    "RIGHT", "ROUND", "ROW_NUMBER", "RPAD", "RTRIM", "SAFE_CAST",
    "SHA1", "SHA256", "SHA512", "SIGN", "SIN", "SINH", "SOUNDEX",
    "SPLIT", "SQRT", "STARTS_WITH", "STDDEV", "STDDEV_POP", "STDDEV_SAMP",
    "STRING", "STRING_AGG", "STRPOS", "SUBSTR", "SUBSTRING", "SUM",
    "TAN", "TANH", "TIME", "TIME_ADD", "TIME_DIFF", "TIME_SUB",
    "TIME_TRUNC", "TIMESTAMP", "TIMESTAMP_ADD", "TIMESTAMP_DIFF",
    "TIMESTAMP_MICROS", "TIMESTAMP_MILLIS", "TIMESTAMP_SECONDS",
    "TIMESTAMP_SUB", "TIMESTAMP_TRUNC", "TO_BASE32", "TO_BASE64",
    "TO_CODE_POINTS", "TO_HEX", "TO_JSON", "TO_JSON_STRING", "TRANSLATE",
    "TRIM", "TRUNC", "UNICODE", "UNNEST", "UPPER", "VAR_POP", "VAR_SAMP",
    "VARIANCE",
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


def _query_like(tokens: list[_Token]) -> bool:
    return any(token.upper in {"SELECT", "WITH"} for token in tokens[:12])


def _collect_ctes(
    tokens: list[_Token],
    inherited_cte_names: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[int], list[dict[str, Any]]]:
    ctes: list[dict[str, Any]] = []
    consumed: set[int] = set()
    nested_scopes: list[dict[str, Any]] = []
    inherited = set(inherited_cte_names or set())

    depth = 0
    with_index = None
    for index, token in enumerate(tokens):
        if token.value == "(":
            depth += 1
        elif token.value == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token.upper == "WITH":
            with_index = index
            break

    if with_index is None:
        return ctes, consumed, nested_scopes

    index = with_index + 1
    consumed.add(with_index)
    if index < len(tokens) and tokens[index].upper == "RECURSIVE":
        consumed.add(index)
        index += 1

    visible_names = set(inherited)
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
        nested_scopes.append({
            "kind": "cte",
            "name": name,
            "start": index + 1,
            "end": close_index,
            "visible_cte_names": set(visible_names),
        })
        consumed.update({index, close_index})
        visible_names.add(name.casefold())
        index = close_index + 1

        if index < len(tokens) and tokens[index].value == ",":
            consumed.add(index)
            index += 1
            continue
        break

    return ctes, consumed, nested_scopes


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
    if token.upper in {"FROM", "JOIN", "UPDATE"}:
        return token.upper.lower(), index + 1
    if token.upper == "USING":
        if index + 1 < len(tokens) and tokens[index + 1].value == "(":
            return None, index
        return "using", index + 1
    if token.upper == "INTO" and index > 0 and tokens[index - 1].upper in {"INSERT", "MERGE"}:
        return f"{tokens[index - 1].upper.lower()}_into", index + 1
    return None, index


def _collect_sources(
    tokens: list[_Token],
    cte_names: set[str],
    *,
    excluded: set[int] | None = None,
) -> tuple[list[dict[str, Any]], set[int], list[dict[str, Any]]]:
    sources: list[dict[str, Any]] = []
    consumed: set[int] = set()
    nested_scopes: list[dict[str, Any]] = []
    excluded_indexes = set(excluded or set())
    index = 0

    while index < len(tokens):
        if index in excluded_indexes:
            index += 1
            continue
        clause, source_index = _source_clause(tokens, index)
        if clause is None:
            index += 1
            continue

        consumed.add(index)
        index = source_index
        if index >= len(tokens) or index in excluded_indexes:
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
                "reason": "UNNEST kaynaginin alan lineage'i kesin cozulmemektedir.",
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
                "reason": "Alt sorgu kolon lineage'i kesin cozulmemektedir.",
            })
            if _query_like(tokens[index + 1:close_index]):
                nested_scopes.append({
                    "kind": "subquery",
                    "name": alias or "subquery",
                    "start": index + 1,
                    "end": close_index,
                })
            index = next_index
            continue

        parts, next_index, identifier_indexes = _identifier_parts(tokens, index)
        if not parts:
            index += 1
            continue

        # BigQuery table-valued function source: FROM dataset.function(...)
        if next_index < len(tokens) and tokens[next_index].value == "(":
            close_index = _find_matching_paren(tokens, next_index)
            if close_index is None:
                index += 1
                continue
            alias, final_index, alias_indexes = _parse_alias(tokens, close_index + 1)
            consumed.update(identifier_indexes)
            consumed.update(range(next_index, close_index + 1))
            consumed.update(alias_indexes)
            normalized = _normalize_object(parts)
            confidence = "confirmed" if normalized["dataset"] else "possible"
            sources.append({
                "line": tokens[index].line,
                "clause": clause,
                "raw_name": ".".join(parts),
                **normalized,
                "alias": alias or normalized["object"],
                "source_type": "table_function",
                "confidence": confidence,
                "reason": "BigQuery table function kaynagi.",
            })
            index = final_index
            continue

        alias, final_index, alias_indexes = _parse_alias(tokens, next_index)
        consumed.update(identifier_indexes)
        consumed.update(alias_indexes)
        normalized = _normalize_object(parts)
        cte_match = len(parts) == 1 and parts[0].casefold() in cte_names

        if cte_match:
            source_type = "cte"
            confidence = "ignored"
            reason = "Kaynak fiziksel tablo degil, gorunur sorgu scope'undaki CTE'dir."
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

    return sources, consumed, nested_scopes

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


def _clause_at(
    tokens: list[_Token],
    index: int,
    *,
    excluded: set[int] | None = None,
) -> str:
    clause = "unknown"
    excluded_indexes = set(excluded or set())
    for cursor in range(index):
        if cursor in excluded_indexes:
            continue
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
    confidence_override: str | None = None,
    reason_override: str | None = None,
) -> dict[str, Any]:
    source_type = source.get("source_type")
    if source_type == "cte":
        confidence = "ignored"
        reason = "Referans fiziksel tablo yerine sorgu ici CTE aliasina baglidir."
    elif source_type in {"subquery", "unnest", "table_function"}:
        confidence = "possible"
        reason = "Alt sorgu, UNNEST veya table function kolon lineage'i kesin cozulmemektedir."
    else:
        confidence = source.get("confidence", "possible")
        reason = (
            "Alias veya tek kaynak, dataset ile nitelendirilmis BigQuery tablosuna baglidir."
            if confidence == "confirmed"
            else "Kaynak tablo baglantisi var ancak tam nesne kimligi veya kolon sahipligi kesin degildir."
        )

    if confidence_override is not None:
        confidence = confidence_override
    if reason_override is not None:
        reason = reason_override

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


def _output_aliases(
    tokens: list[_Token],
    excluded: set[int],
) -> tuple[set[str], set[int]]:
    aliases: set[str] = set()
    indexes: set[int] = set()
    for index, token in enumerate(tokens[:-1]):
        if index in excluded or token.upper != "AS":
            continue
        candidate_index = index + 1
        if candidate_index in excluded or not _is_identifier(tokens[candidate_index]):
            continue
        aliases.add(tokens[candidate_index].value.casefold())
        indexes.add(candidate_index)
    return aliases, indexes


def _using_column_references(
    tokens: list[_Token],
    *,
    path: str,
    sources: list[dict[str, Any]],
    excluded: set[int],
) -> tuple[list[dict[str, Any]], set[int]]:
    references: list[dict[str, Any]] = []
    consumed: set[int] = set()
    physical_sources = [item for item in sources if item.get("source_type") == "table"]
    for index, token in enumerate(tokens):
        if index in excluded or token.upper != "USING":
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].value != "(":
            continue
        close_index = _find_matching_paren(tokens, index + 1)
        if close_index is None:
            continue
        consumed.update(range(index, close_index + 1))
        for cursor in range(index + 2, close_index):
            if not _is_identifier(tokens[cursor]):
                continue
            column = tokens[cursor].value
            for source in physical_sources:
                references.append(
                    _reference_from_source(
                        path=path,
                        token=tokens[cursor],
                        raw_reference=column,
                        column_path=[column],
                        source=source,
                        clause="using",
                        reason_override="JOIN USING kolonu her iki fiziksel tablo kaynaginda da kullanilir.",
                    )
                )
    return references, consumed



def _parse_wildcard_modifiers(
    tokens: list[_Token],
    start: int,
    *,
    excluded: set[int],
) -> tuple[set[str], set[str], set[int]]:
    """SELECT wildcard arkasindaki EXCEPT/REPLACE hedeflerini cikarir."""
    excluded_columns: set[str] = set()
    replaced_columns: set[str] = set()
    consumed: set[int] = set()
    index = start

    while index < len(tokens):
        if index in excluded:
            index += 1
            continue
        token = tokens[index]
        if token.upper not in {"EXCEPT", "REPLACE"}:
            break
        if index + 1 >= len(tokens) or tokens[index + 1].value != "(":
            break
        close_index = _find_matching_paren(tokens, index + 1)
        if close_index is None:
            break

        consumed.add(index)
        if token.upper == "EXCEPT":
            consumed.update(range(index + 1, close_index + 1))
            for cursor in range(index + 2, close_index):
                if _is_identifier(tokens[cursor]):
                    excluded_columns.add(tokens[cursor].value.casefold())
        else:
            # REPLACE ifadelerindeki kaynak kolonlar normal kolon evidence'i
            # olarak kalir. Yalnizca cikti aliaslarini kaydederiz.
            consumed.update({index, index + 1, close_index})
            depth = 0
            for cursor in range(index + 2, close_index):
                value = tokens[cursor].value
                if value == "(":
                    depth += 1
                elif value == ")":
                    depth = max(0, depth - 1)
                elif (
                    depth == 0
                    and tokens[cursor].upper == "AS"
                    and cursor + 1 < close_index
                    and _is_identifier(tokens[cursor + 1])
                ):
                    replaced_columns.add(tokens[cursor + 1].value.casefold())
                    consumed.update({cursor, cursor + 1})
        index = close_index + 1

    return excluded_columns, replaced_columns, consumed


def _wildcard_reference_from_source(
    *,
    path: str,
    token: _Token,
    raw_reference: str,
    source: dict[str, Any],
    excluded_columns: set[str],
    replaced_columns: set[str],
) -> dict[str, Any]:
    source_type = source.get("source_type")
    if source_type == "cte":
        confidence = "ignored"
        reason = "Wildcard fiziksel tablo yerine sorgu ici CTE kaynagina aittir."
    elif source_type in {"subquery", "unnest", "table_function"}:
        confidence = "possible"
        reason = "Wildcard kaynaginin cikti kolon lineage'i kesin cozulmemektedir."
    else:
        confidence = source.get("confidence", "possible")
        reason = (
            "SELECT wildcard bu BigQuery tablosunun kolon sozlesmesini ciktiya tasir."
            if confidence == "confirmed"
            else "Wildcard tablo kaynagina baglidir ancak default dataset bilinmemektedir."
        )

    return {
        "path": path,
        "line": token.line,
        "raw_reference": raw_reference,
        "reference_type": "column_contract",
        "confidence": confidence,
        "project": source.get("project"),
        "dataset": source.get("dataset"),
        "object": source.get("object"),
        "resolved_object": source.get("qualified_name") or None,
        "column_path": ["*"],
        "resolved_column": "*",
        "excluded_columns": sorted(excluded_columns),
        "replaced_columns": sorted(replaced_columns),
        "clause": "select",
        "reason": reason,
    }


def _collect_wildcard_references(
    tokens: list[_Token],
    *,
    path: str,
    sources: list[dict[str, Any]],
    excluded: set[int],
) -> tuple[list[dict[str, Any]], set[int]]:
    """SELECT *, alias.*, EXCEPT ve REPLACE cikti sozlesmesini toplar."""
    references: list[dict[str, Any]] = []
    consumed: set[int] = set()
    aliases: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        alias = source.get("alias")
        if isinstance(alias, str) and alias:
            aliases.setdefault(alias.casefold(), []).append(source)

    physical_sources = [
        source for source in sources
        if source.get("source_type") in {"table", "cte", "subquery", "unnest", "table_function"}
    ]

    for index, token in enumerate(tokens):
        if index in excluded or token.value != "*":
            continue
        if _clause_at(tokens, index, excluded=excluded) != "select":
            continue

        raw_reference = "*"
        matched_sources = physical_sources
        prefix_indexes: set[int] = set()
        if (
            index >= 2
            and tokens[index - 1].value == "."
            and _is_identifier(tokens[index - 2])
        ):
            alias = tokens[index - 2].value
            raw_reference = f"{alias}.*"
            matched_sources = aliases.get(alias.casefold(), [])
            prefix_indexes.update({index - 2, index - 1})

        excluded_columns, replaced_columns, modifier_consumed = (
            _parse_wildcard_modifiers(
                tokens,
                index + 1,
                excluded=excluded,
            )
        )
        consumed.update(prefix_indexes | {index} | modifier_consumed)

        for source in matched_sources:
            references.append(
                _wildcard_reference_from_source(
                    path=path,
                    token=token,
                    raw_reference=raw_reference,
                    source=source,
                    excluded_columns=excluded_columns,
                    replaced_columns=replaced_columns,
                )
            )

    return references, consumed


def _collect_references(
    tokens: list[_Token],
    *,
    path: str,
    sources: list[dict[str, Any]],
    cte_names: set[str],
    consumed: set[int],
    parameters: set[str],
    excluded: set[int] | None = None,
    inherited_sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    excluded_indexes = set(excluded or set())
    inherited = list(inherited_sources or [])
    local_aliases: dict[str, list[dict[str, Any]]] = {}
    inherited_aliases: dict[str, list[dict[str, Any]]] = {}
    for source, target in [
        *[(item, local_aliases) for item in sources],
        *[(item, inherited_aliases) for item in inherited],
    ]:
        alias = source.get("alias")
        if isinstance(alias, str) and alias:
            target.setdefault(alias.casefold(), []).append(source)

    local_physical = [item for item in sources if item.get("source_type") == "table"]
    inherited_physical = [item for item in inherited if item.get("source_type") == "table"]
    physical_sources = local_physical or inherited_physical
    references, using_consumed = _using_column_references(
        tokens,
        path=path,
        sources=sources,
        excluded=excluded_indexes,
    )
    consumed = set(consumed) | using_consumed
    output_alias_names, output_alias_indexes = _output_aliases(tokens, excluded_indexes)
    consumed.update(output_alias_indexes)
    source_alias_names = set(local_aliases) | set(inherited_aliases)
    index = 0

    while index < len(tokens):
        if index in excluded_indexes or index in consumed or not _is_identifier(tokens[index]):
            index += 1
            continue

        parts, next_index, indexes = _identifier_parts(tokens, index)
        if not parts or indexes & (consumed | excluded_indexes):
            index = max(index + 1, next_index)
            continue

        first_key = parts[0].casefold()
        raw_reference = ".".join(parts)
        clause = _clause_at(tokens, index, excluded=excluded_indexes)

        if first_key in parameters:
            index = next_index
            continue

        if len(parts) >= 2:
            alias_sources = local_aliases.get(first_key)
            if alias_sources is None:
                alias_sources = inherited_aliases.get(first_key, [])
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
                for source in alias_sources:
                    references.append(
                        _reference_from_source(
                            path=path,
                            token=tokens[index],
                            raw_reference=raw_reference,
                            column_path=parts[1:],
                            source=source,
                            clause=clause,
                            confidence_override="possible",
                            reason_override="Ayni alias birden fazla gorunur kaynaga baglandigi icin referans kesin cozulmedi.",
                        )
                    )
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
                    "reason": "Referans gorunur sorgu scope'undaki CTE'ye aittir.",
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
                    if prefix and folded_parts[:len(prefix)] == prefix and len(parts) > len(prefix):
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
                        source=physical_sources[0],
                        clause=clause,
                        confidence_override="possible",
                        reason_override="Nitelikli referans tek gorunur tabloya adaydir ancak alias baglantisi kesin degildir.",
                    )
                )
            index = next_index
            continue

        # Unqualified column reference.
        token = tokens[index]
        previous = tokens[index - 1] if index > 0 else None
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if (
            token.upper in _RESERVED_WORDS
            or token.upper in _TYPE_WORDS
            or first_key in cte_names
            or first_key in source_alias_names
            or (previous is not None and previous.value == ".")
            or (following is not None and following.value in {".", "("})
            or (previous is not None and previous.upper in {"AS", "TABLE", "VIEW", "FUNCTION", "PROCEDURE", "SCHEMA", "COLUMN", "TO", "ADD", "DROP", "RENAME", "ALTER", "CREATE"})
            or clause not in _UNQUALIFIED_COLUMN_CLAUSES
            or (clause in {"group", "order", "having", "qualify"} and first_key in output_alias_names)
        ):
            index += 1
            continue

        if len(physical_sources) == 1:
            references.append(
                _reference_from_source(
                    path=path,
                    token=token,
                    raw_reference=token.value,
                    column_path=[token.value],
                    source=physical_sources[0],
                    clause=clause,
                    reason_override="Nitelendirilmemis kolon, bu scope'taki tek fiziksel tablo kaynagina baglidir.",
                )
            )
        elif len(physical_sources) > 1:
            for source in physical_sources:
                references.append(
                    _reference_from_source(
                        path=path,
                        token=token,
                        raw_reference=token.value,
                        column_path=[token.value],
                        source=source,
                        clause=clause,
                        confidence_override="possible",
                        reason_override="Nitelendirilmemis kolon birden fazla gorunur tablo kaynagindan gelebilir.",
                    )
                )
        index += 1

    return references


def _routine_reference_from_parts(
    *,
    path: str,
    token: _Token,
    parts: list[str],
    routine_kind: str,
    clause: str,
    confidence_override: str | None = None,
    reason_override: str | None = None,
) -> dict[str, Any]:
    normalized = _normalize_object(parts)
    confidence = confidence_override or (
        "confirmed" if normalized["dataset"] else "possible"
    )
    reason = reason_override or (
        "Dataset veya project ile nitelendirilmis BigQuery routine cagrisi."
        if confidence == "confirmed"
        else "Routine adi nitelendirilmemis; default dataset bilinmedigi icin kesin cozumlenemedi."
    )
    return {
        "path": path,
        "line": token.line,
        "raw_reference": ".".join(parts),
        "reference_type": "routine",
        "routine_kind": routine_kind,
        **normalized,
        "resolved_object": normalized["qualified_name"],
        "clause": clause,
        "confidence": confidence,
        "reason": reason,
    }


def _collect_routine_references(
    tokens: list[_Token],
    *,
    path: str,
    sources: list[dict[str, Any]],
    consumed: set[int],
    excluded: set[int] | None = None,
) -> tuple[list[dict[str, Any]], set[int]]:
    references: list[dict[str, Any]] = []
    routine_consumed: set[int] = set()
    excluded_indexes = set(excluded or set())

    for source in sources:
        if source.get("source_type") != "table_function":
            continue
        parts = [
            str(part)
            for part in (
                source.get("project"),
                source.get("dataset"),
                source.get("object"),
            )
            if isinstance(part, str) and part
        ]
        if not parts:
            continue
        references.append(
            _routine_reference_from_parts(
                path=path,
                token=_Token(
                    str(source.get("raw_name") or parts[-1]),
                    str(source.get("raw_name") or parts[-1]).upper(),
                    "word",
                    int(source.get("line") or 1),
                ),
                parts=parts,
                routine_kind="table_function",
                clause=str(source.get("clause") or "from"),
                confidence_override=str(source.get("confidence") or "possible"),
                reason_override=str(source.get("reason") or "BigQuery table function kaynagi."),
            )
        )

    index = 0
    while index < len(tokens):
        if index in excluded_indexes or index in consumed:
            index += 1
            continue

        token = tokens[index]
        if token.upper == "CALL":
            parts, next_index, identifier_indexes = _identifier_parts(tokens, index + 1)
            if parts:
                references.append(
                    _routine_reference_from_parts(
                        path=path,
                        token=tokens[index + 1],
                        parts=parts,
                        routine_kind="procedure",
                        clause="call",
                    )
                )
                routine_consumed.add(index)
                routine_consumed.update(identifier_indexes)
                index = max(next_index, index + 1)
                continue

        if not _is_identifier(token):
            index += 1
            continue

        parts, next_index, identifier_indexes = _identifier_parts(tokens, index)
        if (
            not parts
            or identifier_indexes & (consumed | excluded_indexes)
            or next_index >= len(tokens)
            or tokens[next_index].value != "("
        ):
            index = max(index + 1, next_index)
            continue

        previous = tokens[index - 1] if index > 0 else None
        if previous is not None and previous.value == ".":
            index = next_index
            continue

        first_upper = parts[0].upper()
        if len(parts) == 1 and (
            first_upper in _BIGQUERY_BUILTIN_FUNCTIONS
            or first_upper in _RESERVED_WORDS
            or first_upper in _TYPE_WORDS
        ):
            index = next_index
            continue

        references.append(
            _routine_reference_from_parts(
                path=path,
                token=token,
                parts=parts,
                routine_kind="function",
                clause=_clause_at(tokens, index, excluded=excluded_indexes),
            )
        )
        routine_consumed.update(identifier_indexes)
        index = next_index

    return references, routine_consumed


def _find_scalar_query_scopes(
    tokens: list[_Token],
    excluded: set[int],
) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    index = 0
    while index < len(tokens):
        if index in excluded or tokens[index].value != "(":
            index += 1
            continue
        close_index = _find_matching_paren(tokens, index)
        if close_index is None:
            index += 1
            continue
        if not any(cursor in excluded for cursor in range(index, close_index + 1)) and _query_like(tokens[index + 1:close_index]):
            scopes.append({
                "kind": "scalar_subquery",
                "name": "scalar_subquery",
                "start": index + 1,
                "end": close_index,
            })
            index = close_index + 1
            continue
        index += 1
    return scopes


def _analyze_scope(
    tokens: list[_Token],
    *,
    path: str,
    scope: str,
    parameters: set[str],
    inherited_cte_names: set[str] | None = None,
    inherited_sources: list[dict[str, Any]] | None = None,
    base_consumed: set[int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    inherited_ctes = set(inherited_cte_names or set())
    ctes, cte_consumed, cte_scopes = _collect_ctes(tokens, inherited_ctes)
    local_cte_names = inherited_ctes | {item["name"].casefold() for item in ctes}
    excluded: set[int] = set()
    for item in cte_scopes:
        excluded.update(range(item["start"] - 1, item["end"] + 1))

    sources, source_consumed, source_scopes = _collect_sources(
        tokens,
        local_cte_names,
        excluded=excluded,
    )
    nested_scopes = cte_scopes + source_scopes
    for item in source_scopes:
        excluded.update(range(item["start"] - 1, item["end"] + 1))

    scalar_scopes = _find_scalar_query_scopes(tokens, excluded)
    nested_scopes.extend(scalar_scopes)
    for item in scalar_scopes:
        excluded.update(range(item["start"] - 1, item["end"] + 1))

    base_reference_consumed = (
        set(base_consumed or set()) | cte_consumed | source_consumed
    )
    wildcard_references, wildcard_consumed = _collect_wildcard_references(
        tokens,
        path=path,
        sources=sources,
        excluded=excluded,
    )
    routine_references, routine_consumed = _collect_routine_references(
        tokens,
        path=path,
        sources=sources,
        consumed=base_reference_consumed,
        excluded=excluded,
    )
    references = _collect_references(
        tokens,
        path=path,
        sources=sources,
        cte_names=local_cte_names,
        consumed=base_reference_consumed | wildcard_consumed | routine_consumed,
        parameters=parameters,
        excluded=excluded,
        inherited_sources=inherited_sources,
    )

    for collection in (ctes, sources, references, wildcard_references, routine_references):
        for item in collection:
            item["scope"] = scope

    result = {
        "ctes": list(ctes),
        "sources": list(sources),
        "references": list(references),
        "wildcard_references": list(wildcard_references),
        "routine_references": list(routine_references),
    }
    visible_sources = list(sources) + list(inherited_sources or [])
    for nested_index, nested in enumerate(nested_scopes, start=1):
        child_tokens = tokens[nested["start"]:nested["end"]]
        child_scope = f"{scope}/{nested['kind']}:{nested['name']}:{nested_index}"
        child_inherited_sources = [] if nested["kind"] == "cte" else visible_sources
        child_ctes = set(nested.get("visible_cte_names", local_cte_names)) | local_cte_names
        child = _analyze_scope(
            child_tokens,
            path=path,
            scope=child_scope,
            parameters=parameters,
            inherited_cte_names=child_ctes,
            inherited_sources=child_inherited_sources,
        )
        for key in result:
            result[key].extend(child[key])

    return result

def analyze_bigquery_sql(
    sql_text: str,
    *,
    path: str,
) -> dict[str, Any]:
    """BigQuery GoogleSQL icin deterministik tanim ve referans kaniti cikarir.

    Scope-aware analiz CTE ve alt sorgu aliaslarini birbirinden ayirir.
    Kesin cozumlenebilen kaynaklar ``confirmed``, birden fazla olasi kaynak
    veya default dataset gerektiren durumlar ``possible``, fiziksel tablo
    olmayan CTE eslesmeleri ise ``ignored`` olarak isaretlenir.
    """
    if not isinstance(sql_text, str):
        raise TypeError("sql_text metin olmalidir.")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path bos olamaz.")

    all_definitions: list[dict[str, Any]] = []
    all_mutations: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []
    all_references: list[dict[str, Any]] = []
    all_wildcard_references: list[dict[str, Any]] = []
    all_routine_references: list[dict[str, Any]] = []
    all_ctes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    tokens = _tokenize(sql_text)
    statements = _split_statements(tokens)

    for statement_index, statement in enumerate(statements, start=1):
        try:
            definitions, mutations, definition_consumed, parameters = _collect_definitions(statement)
            scoped = _analyze_scope(
                statement,
                path=path,
                scope=f"statement:{statement_index}",
                parameters=parameters,
                base_consumed=definition_consumed,
            )

            for collection in (
                definitions,
                mutations,
                scoped["ctes"],
                scoped["sources"],
                scoped["references"],
                scoped["wildcard_references"],
                scoped["routine_references"],
            ):
                for item in collection:
                    item["statement"] = statement_index

            all_definitions.extend(definitions)
            all_mutations.extend(mutations)
            all_ctes.extend(scoped["ctes"])
            all_sources.extend(scoped["sources"])
            all_references.extend(scoped["references"])
            all_wildcard_references.extend(scoped["wildcard_references"])
            all_routine_references.extend(scoped["routine_references"])
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
        "wildcard_references": all_wildcard_references,
        "routine_references": all_routine_references,
        "ctes": all_ctes,
        "errors": errors,
    }
