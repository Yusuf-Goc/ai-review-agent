import json
import os
import tempfile
from typing import Any

from agent.codebase_documenter import process_docs_scan_units
from agent.config import (
    DEFAULT_MODEL,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
)
from agent.full_scan_planner import FullScanSlice, FullScanUnit


WORKER_RESULT_SCHEMA_VERSION = "1.0"


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
            f"Shard payload dosyası bulunamadı: {payload_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Shard payload geçerli JSON değil: {payload_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError("Shard payload JSON object olmalıdır.")

    shard_id = payload.get("shard_id")

    if not isinstance(shard_id, str) or not shard_id.strip():
        raise ValueError(
            "Shard payload içinde geçerli shard_id bulunmalıdır."
        )

    units = payload.get("units")

    if not isinstance(units, list):
        raise ValueError(
            "Shard payload içinde units listesi bulunmalıdır."
        )

    expected_unit_count = payload.get("unit_count")

    if (
        expected_unit_count is not None
        and expected_unit_count != len(units)
    ):
        raise ValueError(
            "Shard payload unit_count değeri units listesiyle uyuşmuyor."
        )

    return payload


def _slice_from_payload(
    payload: dict[str, Any],
) -> FullScanSlice:
    if not isinstance(payload, dict):
        raise ValueError(
            "Shard içindeki slice kaydı JSON object olmalıdır."
        )

    path = payload.get("path")

    if not isinstance(path, str) or not path:
        raise ValueError(
            "Shard slice kaydında geçerli path bulunmalıdır."
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
            "Shard içindeki unit kaydı JSON object olmalıdır."
        )

    unit_id = payload.get("unit_id")

    if not isinstance(unit_id, str) or not unit_id:
        raise ValueError(
            "Shard unit kaydında geçerli unit_id bulunmalıdır."
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
            _slice_from_payload(file_slice)
            for file_slice in slices_payload
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
            prefix=".docs-worker-result-",
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


def run_docs_worker(
    payload_path: str,
    output_path: str,
    model: str = DEFAULT_MODEL,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> dict[str, Any]:
    """
    Tek bir documentation shard payload'ını işler.

    Worker yalnızca kendi sonuç dosyasını yazar. Merkezi index, summary ve
    Markdown raporu daha sonraki merge aşaması tarafından güncellenir.
    """
    payload = _load_payload(payload_path)

    scan_units = [
        _unit_from_payload(unit_payload)
        for unit_payload in payload["units"]
    ]

    merged_files_by_path, failed_units = process_docs_scan_units(
        scan_units=scan_units,
        model=model,
        retries=retries,
        retry_delay=retry_delay,
    )

    files = sorted(
        merged_files_by_path.values(),
        key=lambda item: item.get("path", ""),
    )

    result = {
        "schema_version": WORKER_RESULT_SCHEMA_VERSION,
        "shard_id": payload["shard_id"],
        "unit_count": len(scan_units),
        "files": files,
        "failed_units": failed_units,
        "stats": {
            "processed_units": len(scan_units),
            "documented_files": len(files),
            "failed_units": len(failed_units),
        },
    }

    _atomic_write_json(
        payload=result,
        output_path=output_path,
    )

    return result
