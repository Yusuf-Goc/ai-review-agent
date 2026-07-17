from typing import Any

from agent.docs_payloads import write_docs_payload_bundle
from agent.docs_sharding import (
    DEFAULT_MAX_SHARDS,
    DEFAULT_TARGET_CHARS_PER_SHARD,
    DEFAULT_TARGET_LINES_PER_SHARD,
    DEFAULT_TARGET_UNITS_PER_SHARD,
    build_docs_shards,
)
from agent.full_scan_planner import FullScanUnit


def prepare_docs_execution(
    scan_units: list[FullScanUnit],
    output_dir: str,
    target_lines_per_shard: int = DEFAULT_TARGET_LINES_PER_SHARD,
    target_chars_per_shard: int = DEFAULT_TARGET_CHARS_PER_SHARD,
    target_units_per_shard: int = DEFAULT_TARGET_UNITS_PER_SHARD,
    max_shards: int = DEFAULT_MAX_SHARDS,
) -> dict[str, Any]:
    """
    Documentation çalışması için shard manifesti ve payload bundle'ı üretir.

    Küçük scan planları tek shard olarak kalır. Büyük planlar satır,
    karakter ve unit yüküne göre deterministic biçimde bölünür.
    """
    shards = build_docs_shards(
        scan_units=scan_units,
        target_lines_per_shard=target_lines_per_shard,
        target_chars_per_shard=target_chars_per_shard,
        target_units_per_shard=target_units_per_shard,
        max_shards=max_shards,
    )

    return write_docs_payload_bundle(
        scan_units=scan_units,
        shards=shards,
        output_dir=output_dir,
    )
