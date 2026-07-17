from typing import Any

from agent.docs_sharding import DocsShard
from agent.full_scan_planner import FullScanUnit


MANIFEST_SCHEMA_VERSION = "1.0"


def _validate_unit_ids(
    scan_units: list[FullScanUnit],
    shards: list[DocsShard],
) -> None:
    expected_unit_ids = [unit.unit_id for unit in scan_units]

    if len(expected_unit_ids) != len(set(expected_unit_ids)):
        raise ValueError(
            "Scan plan içinde aynı unit_id birden fazla kez bulunuyor."
        )

    expected_set = set(expected_unit_ids)
    assigned_unit_ids = [
        unit_id
        for shard in shards
        for unit_id in shard.unit_ids
    ]

    duplicate_assignments = sorted(
        {
            unit_id
            for unit_id in assigned_unit_ids
            if assigned_unit_ids.count(unit_id) > 1
        }
    )

    if duplicate_assignments:
        raise ValueError(
            "Bir analiz birimi birden fazla shard içine atanmış: "
            + ", ".join(duplicate_assignments)
        )

    assigned_set = set(assigned_unit_ids)

    missing_unit_ids = sorted(expected_set - assigned_set)

    if missing_unit_ids:
        raise ValueError(
            "Shard manifestinde eksik analiz birimleri var: "
            + ", ".join(missing_unit_ids)
        )

    unknown_unit_ids = sorted(assigned_set - expected_set)

    if unknown_unit_ids:
        raise ValueError(
            "Shard manifestinde scan planında bulunmayan birimler var: "
            + ", ".join(unknown_unit_ids)
        )


def build_docs_manifest(
    scan_units: list[FullScanUnit],
    shards: list[DocsShard],
) -> dict[str, Any]:
    """
    GitHub Actions matrix'i ve shard metadata'sını içeren manifest üretir.

    Manifest, her scan unit'in tam olarak bir shard içinde bulunduğunu
    doğrular ve shard sırasını shard_id üzerinden deterministic tutar.
    """
    _validate_unit_ids(scan_units, shards)

    ordered_shards = sorted(
        shards,
        key=lambda shard: shard.shard_id,
    )

    shard_entries = []

    for shard in ordered_shards:
        shard_entries.append(
            {
                "shard_id": shard.shard_id,
                "payload_file": (
                    f"shards/{shard.shard_id}.json"
                ),
                "unit_ids": sorted(shard.unit_ids),
                "unit_count": len(shard.unit_ids),
                "total_lines": shard.total_lines,
                "total_chars": shard.total_chars,
                "total_risk_score": shard.total_risk_score,
            }
        )

    matrix_entries = [
        {
            "shard_id": shard["shard_id"],
            "payload_file": shard["payload_file"],
        }
        for shard in shard_entries
    ]

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "unit_count": len(scan_units),
        "shard_count": len(shard_entries),
        "matrix": {
            "include": matrix_entries,
        },
        "shards": shard_entries,
    }
