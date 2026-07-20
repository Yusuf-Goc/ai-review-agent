import json
import os
import tempfile
from typing import Any

from agent.config import (
    DEFAULT_MODEL,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
    MAX_REVIEW_LINES,
)
from agent.full_scan_planner import FullScanSlice, FullScanUnit
from agent.reviewer import process_full_scan_units


FULL_SCAN_WORKER_RESULT_SCHEMA_VERSION = "1.0"


def _load_payload(payload_path: str) -> dict[str, Any]:
    try:
        with open(
            payload_path,
            "r",
            encoding="utf-8",
        ) as payload_file:
            payload = json.load(payload_file)

    except FileNotFoundError as exc:
        raise ValueError(
            f"Full scan shard payload dosyası bulunamadı: "
            f"{payload_path}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Full scan shard payload geçerli JSON değil: "
            f"{payload_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Full scan shard payload JSON object olmalıdır."
        )

    shard_id = payload.get("shard_id")

    if not isinstance(shard_id, str) or not shard_id.strip():
        raise ValueError(
            "Full scan shard payload içinde geçerli "
            "shard_id bulunmalıdır."
        )

    units = payload.get("units")

    if not isinstance(units, list):
        raise ValueError(
            "Full scan shard payload içinde units listesi "
            "bulunmalıdır."
        )

    expected_unit_count = payload.get("unit_count")

    if (
        expected_unit_count is not None
        and expected_unit_count != len(units)
    ):
        raise ValueError(
            "Full scan shard payload unit_count değeri "
            "units listesiyle uyuşmuyor."
        )

    return payload


def _slice_from_payload(
    payload: dict[str, Any],
) -> FullScanSlice:
    if not isinstance(payload, dict):
        raise ValueError(
            "Full scan shard içindeki slice kaydı "
            "JSON object olmalıdır."
        )

    path = payload.get("path")

    if not isinstance(path, str) or not path:
        raise ValueError(
            "Full scan shard slice kaydında geçerli "
            "path bulunmalıdır."
        )

    return FullScanSlice(
        path=path,
        language=str(payload.get("language", "unknown")),
        start_line=int(payload.get("start_line", 1)),
        end_line=int(payload.get("end_line", 1)),
        content=str(payload.get("content", "")),
        line_count=int(payload.get("line_count", 0)),
        char_count=int(payload.get("char_count", 0)),
        part_label=str(payload.get("part_label", "")),
    )


def _unit_from_payload(
    payload: dict[str, Any],
) -> FullScanUnit:
    if not isinstance(payload, dict):
        raise ValueError(
            "Full scan shard içindeki unit kaydı "
            "JSON object olmalıdır."
        )

    unit_id = payload.get("unit_id")

    if not isinstance(unit_id, str) or not unit_id:
        raise ValueError(
            "Full scan shard unit kaydında geçerli "
            "unit_id bulunmalıdır."
        )

    slices_payload = payload.get("slices", [])

    if not isinstance(slices_payload, list):
        raise ValueError(
            f"{unit_id} için slices listesi geçersiz."
        )

    return FullScanUnit(
        unit_id=unit_id,
        kind=str(payload.get("kind", "unknown")),
        slices=[
            _slice_from_payload(slice_payload)
            for slice_payload in slices_payload
        ],
        total_lines=int(payload.get("total_lines", 0)),
        total_chars=int(payload.get("total_chars", 0)),
        risk_score=int(payload.get("risk_score", 0)),
    )


def _atomic_write_json(
    payload: dict[str, Any],
    output_path: str,
) -> None:
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
            prefix=".full-scan-worker-result-",
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


def run_full_scan_worker(
    payload_path: str,
    output_path: str,
    client=None,
    model: str = DEFAULT_MODEL,
    max_review_lines: int = MAX_REVIEW_LINES,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> dict[str, Any]:
    """
    Tek bir full-repository scan shard payload'ını işler.

    Worker GitHub issue oluşturmaz ve diğer shard sonuçlarını değiştirmez.
    Yalnızca kendi JSON artifact'ini atomik olarak yazar.
    """
    payload = _load_payload(payload_path)

    scan_units = [
        _unit_from_payload(unit_payload)
        for unit_payload in payload["units"]
    ]

    processed = process_full_scan_units(
        scan_units=scan_units,
        client=client,
        model=model,
        max_review_lines=max_review_lines,
        retries=retries,
        retry_delay=retry_delay,
    )

    result = {
        "schema_version": (
            FULL_SCAN_WORKER_RESULT_SCHEMA_VERSION
        ),
        "mode": "full_repository_scan",
        "shard_id": payload["shard_id"],
        "unit_count": len(scan_units),
        "findings": processed.get("findings", []),
        "failed_units": processed.get(
            "failed_units",
            [],
        ),
        "stats": processed.get("stats", {}),
    }

    _atomic_write_json(
        payload=result,
        output_path=output_path,
    )

    return result
