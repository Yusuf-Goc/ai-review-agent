import math
from dataclasses import dataclass, field

from agent.full_scan_planner import FullScanUnit


DEFAULT_TARGET_LINES_PER_SHARD = 6_000
DEFAULT_TARGET_CHARS_PER_SHARD = 300_000
DEFAULT_TARGET_UNITS_PER_SHARD = 24
DEFAULT_MAX_SHARDS = 20


@dataclass
class DocsShard:
    shard_id: str
    unit_ids: list[str] = field(default_factory=list)
    total_lines: int = 0
    total_chars: int = 0
    total_risk_score: int = 0


def _positive_limit(value: int, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} sıfırdan büyük olmalıdır.")

    return value


def _calculate_shard_count(
    scan_units: list[FullScanUnit],
    target_lines_per_shard: int,
    target_chars_per_shard: int,
    target_units_per_shard: int,
    max_shards: int,
) -> int:
    total_lines = sum(max(0, unit.total_lines) for unit in scan_units)
    total_chars = sum(max(0, unit.total_chars) for unit in scan_units)

    line_shards = math.ceil(total_lines / target_lines_per_shard)
    char_shards = math.ceil(total_chars / target_chars_per_shard)
    unit_shards = math.ceil(len(scan_units) / target_units_per_shard)

    required_shards = max(
        1,
        line_shards,
        char_shards,
        unit_shards,
    )

    return min(
        required_shards,
        max_shards,
        len(scan_units),
    )


def _unit_sort_key(unit: FullScanUnit) -> tuple:
    """
    Büyük birimleri önce yerleştirerek shard yüklerinin dengelenmesini sağlar.

    unit_id son anahtar olduğu için sonuç giriş sırasından bağımsızdır.
    """
    return (
        -max(0, unit.total_lines),
        -max(0, unit.total_chars),
        -max(0, unit.risk_score),
        unit.unit_id,
    )


def _projected_load_key(
    shard: DocsShard,
    unit: FullScanUnit,
    target_lines_per_shard: int,
    target_chars_per_shard: int,
    target_units_per_shard: int,
    shard_index: int,
) -> tuple:
    projected_lines = shard.total_lines + max(0, unit.total_lines)
    projected_chars = shard.total_chars + max(0, unit.total_chars)
    projected_units = len(shard.unit_ids) + 1
    projected_risk = shard.total_risk_score + max(0, unit.risk_score)

    return (
        max(
            projected_lines / target_lines_per_shard,
            projected_chars / target_chars_per_shard,
            projected_units / target_units_per_shard,
        ),
        projected_lines / target_lines_per_shard,
        projected_chars / target_chars_per_shard,
        projected_units / target_units_per_shard,
        projected_risk,
        shard_index,
    )


def build_docs_shards(
    scan_units: list[FullScanUnit],
    target_lines_per_shard: int = DEFAULT_TARGET_LINES_PER_SHARD,
    target_chars_per_shard: int = DEFAULT_TARGET_CHARS_PER_SHARD,
    target_units_per_shard: int = DEFAULT_TARGET_UNITS_PER_SHARD,
    max_shards: int = DEFAULT_MAX_SHARDS,
) -> list[DocsShard]:
    """
    Full scan birimlerini deterministic ve ağırlık dengeli shard'lara ayırır.

    Küçük planlar tek shard üretir. Büyük planlarda shard sayısı toplam satır,
    karakter ve analiz birimi sayısına göre hesaplanır.
    """
    if not scan_units:
        return []

    target_lines_per_shard = _positive_limit(
        target_lines_per_shard,
        "target_lines_per_shard",
    )
    target_chars_per_shard = _positive_limit(
        target_chars_per_shard,
        "target_chars_per_shard",
    )
    target_units_per_shard = _positive_limit(
        target_units_per_shard,
        "target_units_per_shard",
    )
    max_shards = _positive_limit(max_shards, "max_shards")

    shard_count = _calculate_shard_count(
        scan_units=scan_units,
        target_lines_per_shard=target_lines_per_shard,
        target_chars_per_shard=target_chars_per_shard,
        target_units_per_shard=target_units_per_shard,
        max_shards=max_shards,
    )

    shards = [
        DocsShard(shard_id=f"docs-shard-{index:03d}")
        for index in range(1, shard_count + 1)
    ]

    for unit in sorted(scan_units, key=_unit_sort_key):
        shard_index = min(
            range(len(shards)),
            key=lambda index: _projected_load_key(
                shard=shards[index],
                unit=unit,
                target_lines_per_shard=target_lines_per_shard,
                target_chars_per_shard=target_chars_per_shard,
                target_units_per_shard=target_units_per_shard,
                shard_index=index,
            ),
        )

        selected_shard = shards[shard_index]
        selected_shard.unit_ids.append(unit.unit_id)
        selected_shard.total_lines += max(0, unit.total_lines)
        selected_shard.total_chars += max(0, unit.total_chars)
        selected_shard.total_risk_score += max(0, unit.risk_score)

    for shard in shards:
        shard.unit_ids.sort()

    return shards
