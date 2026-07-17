import json
import os
import tempfile
from typing import Any

from agent.docs_manifest import build_docs_manifest
from agent.docs_sharding import DocsShard
from agent.full_scan_planner import FullScanSlice, FullScanUnit


PAYLOAD_SCHEMA_VERSION = "1.0"


def _atomic_write_json(
    payload: dict[str, Any],
    output_path: str,
) -> None:
    """
    JSON dosyasını hedef klasörde geçici dosya üzerinden atomic yazar.
    """
    parent_directory = os.path.dirname(output_path)
    target_directory = parent_directory or "."

    if parent_directory:
        os.makedirs(parent_directory, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_directory,
            prefix=".docs-payload-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name

            json.dump(
                payload,
                temporary_file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, output_path)
        temporary_path = None

    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def _slice_to_payload(
    file_slice: FullScanSlice,
) -> dict[str, Any]:
    return {
        "path": file_slice.path,
        "language": file_slice.language,
        "start_line": file_slice.start_line,
        "end_line": file_slice.end_line,
        "content": file_slice.content,
        "line_count": file_slice.line_count,
        "char_count": file_slice.char_count,
        "part_label": file_slice.part_label,
    }


def _unit_to_payload(
    unit: FullScanUnit,
) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "kind": unit.kind,
        "total_lines": unit.total_lines,
        "total_chars": unit.total_chars,
        "risk_score": unit.risk_score,
        "slices": [
            _slice_to_payload(file_slice)
            for file_slice in unit.slices
        ],
    }


def write_docs_payload_bundle(
    scan_units: list[FullScanUnit],
    shards: list[DocsShard],
    output_dir: str,
) -> dict[str, Any]:
    """
    Matrix worker'larının okuyacağı shard payload bundle'ını oluşturur.

    Her scan unit tam olarak bir shard payload'ında yer alır. Shard dosyaları
    önce yazılır, manifest en son yazılarak eksik bundle'ın hazır görünmesi
    engellenir.
    """
    manifest = build_docs_manifest(
        scan_units=scan_units,
        shards=shards,
    )

    unit_by_id = {
        unit.unit_id: unit
        for unit in scan_units
    }

    for shard_entry in manifest["shards"]:
        unit_ids = shard_entry["unit_ids"]

        payload = {
            "schema_version": PAYLOAD_SCHEMA_VERSION,
            "shard_id": shard_entry["shard_id"],
            "unit_count": len(unit_ids),
            "total_lines": shard_entry["total_lines"],
            "total_chars": shard_entry["total_chars"],
            "total_risk_score": shard_entry[
                "total_risk_score"
            ],
            "units": [
                _unit_to_payload(unit_by_id[unit_id])
                for unit_id in unit_ids
            ],
        }

        payload_path = os.path.join(
            output_dir,
            shard_entry["payload_file"],
        )

        _atomic_write_json(
            payload=payload,
            output_path=payload_path,
        )

    manifest_path = os.path.join(
        output_dir,
        "manifest.json",
    )

    _atomic_write_json(
        payload=manifest,
        output_path=manifest_path,
    )

    return manifest
