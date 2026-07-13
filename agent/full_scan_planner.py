from dataclasses import dataclass, field


SMALL_FILE_MAX_LINES = 250
SMALL_FILE_MAX_CHARS = 12_000

MAX_UNIT_LINES = 900
MAX_UNIT_CHARS = 45_000
MAX_FILES_PER_UNIT = 8

CHUNK_TARGET_LINES = 750
CHUNK_TARGET_CHARS = 35_000
CHUNK_OVERLAP_LINES = 25


@dataclass
class FullScanSlice:
    path: str
    language: str
    start_line: int
    end_line: int
    content: str
    line_count: int
    char_count: int
    part_label: str = ""


@dataclass
class FullScanUnit:
    unit_id: str
    kind: str
    slices: list[FullScanSlice] = field(default_factory=list)
    total_lines: int = 0
    total_chars: int = 0
    risk_score: int = 0


def calculate_risk_score(path: str, content: str) -> int:
    lowered_path = path.lower()
    lowered_content = content.lower()

    score = 0

    path_keywords = [
        "auth",
        "login",
        "password",
        "passwd",
        "token",
        "secret",
        "payment",
        "invoice",
        "order",
        "user",
        "admin",
        "permission",
        "role",
        "migration",
        "security",
        "session",
    ]

    risky_keywords = [
        "drop table",
        "truncate table",
        "delete from",
        "update ",
        "alter table",
        "grant ",
        "revoke ",
        "eval(",
        "exec(",
        "subprocess",
        "os.system",
        "password",
        "secret",
        "token",
        "panic(",
    ]

    for keyword in path_keywords:
        if keyword in lowered_path:
            score += 3

    for keyword in risky_keywords:
        if keyword in lowered_content:
            score += 5

    if len(content) > 45_000:
        score += 4
    elif len(content) > 20_000:
        score += 2

    return score


def _make_slice(
    path: str,
    language: str,
    lines: list[str],
    start_line: int,
    end_line: int,
    part_label: str = "",
) -> FullScanSlice:
    content = "\n".join(lines)

    return FullScanSlice(
        path=path,
        language=language,
        start_line=start_line,
        end_line=end_line,
        content=content,
        line_count=max(0, end_line - start_line + 1),
        char_count=len(content),
        part_label=part_label,
    )


def _split_very_long_line(
    path: str,
    language: str,
    line: str,
    line_number: int,
) -> list[FullScanSlice]:
    slices = []
    start = 0
    part_index = 1

    while start < len(line):
        end = min(start + CHUNK_TARGET_CHARS, len(line))
        chunk_text = line[start:end]

        slices.append(
            FullScanSlice(
                path=path,
                language=language,
                start_line=line_number,
                end_line=line_number,
                content=chunk_text,
                line_count=1,
                char_count=len(chunk_text),
                part_label=f"line-{line_number}-chars-{start + 1}-{end}-part-{part_index}",
            )
        )

        start = end
        part_index += 1

    return slices


def split_large_file_into_slices(
    path: str,
    language: str,
    content: str,
) -> list[FullScanSlice]:
    lines = content.splitlines()

    if not lines:
        return [
            FullScanSlice(
                path=path,
                language=language,
                start_line=1,
                end_line=1,
                content="",
                line_count=0,
                char_count=0,
                part_label="empty-file",
            )
        ]

    result: list[FullScanSlice] = []
    current_lines: list[str] = []
    current_start_line = 1
    current_chars = 0
    part_index = 1

    line_index = 0

    while line_index < len(lines):
        line = lines[line_index]
        line_number = line_index + 1

        if len(line) > CHUNK_TARGET_CHARS:
            if current_lines:
                end_line = current_start_line + len(current_lines) - 1
                result.append(
                    _make_slice(
                        path,
                        language,
                        current_lines,
                        current_start_line,
                        end_line,
                        part_label=f"part-{part_index}",
                    )
                )
                part_index += 1
                current_lines = []
                current_chars = 0

            result.extend(
                _split_very_long_line(
                    path=path,
                    language=language,
                    line=line,
                    line_number=line_number,
                )
            )

            line_index += 1
            current_start_line = line_index + 1
            continue

        would_exceed_lines = len(current_lines) >= CHUNK_TARGET_LINES
        would_exceed_chars = current_chars + len(line) + 1 > CHUNK_TARGET_CHARS

        if current_lines and (would_exceed_lines or would_exceed_chars):
            end_line = current_start_line + len(current_lines) - 1

            result.append(
                _make_slice(
                    path,
                    language,
                    current_lines,
                    current_start_line,
                    end_line,
                    part_label=f"part-{part_index}",
                )
            )
            part_index += 1

            overlap_start = max(0, len(current_lines) - CHUNK_OVERLAP_LINES)
            overlap_lines = current_lines[overlap_start:]

            current_start_line = end_line - len(overlap_lines) + 1
            current_lines = overlap_lines[:]
            current_chars = sum(len(item) + 1 for item in current_lines)

        current_lines.append(line)
        current_chars += len(line) + 1
        line_index += 1

    if current_lines:
        end_line = current_start_line + len(current_lines) - 1

        result.append(
            _make_slice(
                path,
                language,
                current_lines,
                current_start_line,
                end_line,
                part_label=f"part-{part_index}",
            )
        )

    return result


def make_whole_file_slice(path: str, language: str, content: str) -> FullScanSlice:
    lines = content.splitlines()
    line_count = len(lines)

    return FullScanSlice(
        path=path,
        language=language,
        start_line=1,
        end_line=max(1, line_count),
        content=content,
        line_count=line_count,
        char_count=len(content),
        part_label="full-file",
    )


def _can_add_to_unit(unit: FullScanUnit, file_slice: FullScanSlice) -> bool:
    if len(unit.slices) >= MAX_FILES_PER_UNIT:
        return False

    if unit.total_lines + file_slice.line_count > MAX_UNIT_LINES:
        return False

    if unit.total_chars + file_slice.char_count > MAX_UNIT_CHARS:
        return False

    return True


def _build_small_file_units(slices: list[FullScanSlice]) -> list[FullScanUnit]:
    units: list[FullScanUnit] = []

    for file_slice in slices:
        placed = False

        for unit in units:
            same_language = all(
                existing_slice.language == file_slice.language
                for existing_slice in unit.slices
            )

            if same_language and _can_add_to_unit(unit, file_slice):
                unit.slices.append(file_slice)
                unit.total_lines += file_slice.line_count
                unit.total_chars += file_slice.char_count
                unit.risk_score += calculate_risk_score(
                    file_slice.path,
                    file_slice.content,
                )
                placed = True
                break

        if not placed:
            units.append(
                FullScanUnit(
                    unit_id="",
                    kind="small_file_batch",
                    slices=[file_slice],
                    total_lines=file_slice.line_count,
                    total_chars=file_slice.char_count,
                    risk_score=calculate_risk_score(file_slice.path, file_slice.content),
                )
            )

    return units


def build_full_scan_plan(file_items: list[dict]) -> list[FullScanUnit]:
    small_slices: list[FullScanSlice] = []
    units: list[FullScanUnit] = []

    for item in file_items:
        path = item["path"]
        language = item["language"]
        content = item["content"]
        line_count = item["line_count"]
        char_count = len(content)

        is_small = (
            line_count <= SMALL_FILE_MAX_LINES
            and char_count <= SMALL_FILE_MAX_CHARS
        )

        is_medium = (
            line_count <= MAX_UNIT_LINES
            and char_count <= MAX_UNIT_CHARS
        )

        if is_small:
            small_slices.append(
                make_whole_file_slice(path, language, content)
            )
        elif is_medium:
            file_slice = make_whole_file_slice(path, language, content)

            units.append(
                FullScanUnit(
                    unit_id="",
                    kind="single_file",
                    slices=[file_slice],
                    total_lines=file_slice.line_count,
                    total_chars=file_slice.char_count,
                    risk_score=calculate_risk_score(path, content),
                )
            )
        else:
            chunks = split_large_file_into_slices(path, language, content)

            for chunk in chunks:
                units.append(
                    FullScanUnit(
                        unit_id="",
                        kind="file_chunk",
                        slices=[chunk],
                        total_lines=chunk.line_count,
                        total_chars=chunk.char_count,
                        risk_score=calculate_risk_score(path, chunk.content),
                    )
                )

    units.extend(_build_small_file_units(small_slices))

    units.sort(key=lambda unit: unit.risk_score, reverse=True)

    for index, unit in enumerate(units, start=1):
        unit.unit_id = f"full-scan-unit-{index}"

    return units
