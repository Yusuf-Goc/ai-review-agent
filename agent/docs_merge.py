import json
from typing import Any

from agent.codebase_documenter import _merge_file_doc


MERGE_RESULT_SCHEMA_VERSION = "1.0"


def _load_worker_result(result_path: str) -> dict[str, Any]:
    try:
        with open(
            result_path,
            "r",
            encoding="utf-8",
        ) as result_file:
            payload = json.load(result_file)
    except FileNotFoundError as exc:
        raise ValueError(
            f"Worker sonuç dosyası bulunamadı: {result_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Worker sonuç dosyası geçerli JSON değil: {result_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"Worker sonucu JSON object olmalıdır: {result_path}"
        )

    shard_id = payload.get("shard_id")

    if not isinstance(shard_id, str) or not shard_id.strip():
        raise ValueError(
            f"Worker sonucunda geçerli shard_id yok: {result_path}"
        )

    files = payload.get("files")

    if not isinstance(files, list):
        raise ValueError(
            f"{shard_id} worker sonucunda files listesi bulunmalıdır."
        )

    failed_units = payload.get("failed_units", [])

    if not isinstance(failed_units, list):
        raise ValueError(
            f"{shard_id} worker sonucunda failed_units geçersiz."
        )

    return payload


def _validate_expected_shards(
    expected_shard_ids: list[str],
) -> set[str]:
    if len(expected_shard_ids) != len(set(expected_shard_ids)):
        raise ValueError(
            "Beklenen shard listesinde aynı shard_id birden fazla kez var."
        )

    for shard_id in expected_shard_ids:
        if not isinstance(shard_id, str) or not shard_id.strip():
            raise ValueError(
                "Beklenen shard listesinde geçersiz shard_id var."
            )

    return set(expected_shard_ids)


def merge_docs_worker_results(
    result_paths: list[str],
    expected_shard_ids: list[str],
) -> dict[str, Any]:
    """
    Documentation worker sonuçlarını deterministic biçimde birleştirir.

    Her beklenen shard'ın tam olarak bir sonucu bulunmalıdır. Eksik,
    tekrarlanan veya beklenmeyen shard sonuçları kabul edilmez.
    """
    expected_set = _validate_expected_shards(expected_shard_ids)

    results_by_shard: dict[str, dict[str, Any]] = {}

    for result_path in sorted(result_paths):
        payload = _load_worker_result(result_path)
        shard_id = payload["shard_id"]

        if shard_id in results_by_shard:
            raise ValueError(
                f"{shard_id} için birden fazla worker sonucu bulundu."
            )

        if shard_id not in expected_set:
            raise ValueError(
                f"Beklenmeyen shard sonucu bulundu: {shard_id}"
            )

        results_by_shard[shard_id] = payload

    completed_set = set(results_by_shard)
    missing_shards = sorted(expected_set - completed_set)

    if missing_shards:
        raise ValueError(
            "eksik shard sonuçları var: "
            + ", ".join(missing_shards)
        )

    merged_files_by_path: dict[str, dict] = {}
    failed_units: list[dict[str, Any]] = []
    processed_units = 0

    for shard_id in sorted(results_by_shard):
        payload = results_by_shard[shard_id]

        stats = payload.get("stats", {})

        if isinstance(stats, dict):
            processed_units += int(
                stats.get(
                    "processed_units",
                    payload.get("unit_count", 0),
                )
            )
        else:
            processed_units += int(payload.get("unit_count", 0))

        for file_doc in payload["files"]:
            if not isinstance(file_doc, dict):
                continue

            file_path = file_doc.get("path")

            if not isinstance(file_path, str) or not file_path:
                continue

            merged_files_by_path[file_path] = _merge_file_doc(
                merged_files_by_path.get(file_path, {}),
                file_doc,
            )

        for failed_unit in payload.get("failed_units", []):
            if not isinstance(failed_unit, dict):
                continue

            failure = dict(failed_unit)
            failure["shard_id"] = shard_id
            failed_units.append(failure)

    files = sorted(
        merged_files_by_path.values(),
        key=lambda item: item.get("path", ""),
    )

    failed_units.sort(
        key=lambda item: (
            item.get("shard_id", ""),
            item.get("unit_id", ""),
            item.get("reason", ""),
        )
    )

    completed_shards = sorted(results_by_shard)

    return {
        "schema_version": MERGE_RESULT_SCHEMA_VERSION,
        "shard_count": len(completed_shards),
        "completed_shards": completed_shards,
        "files": files,
        "failed_units": failed_units,
        "stats": {
            "processed_units": processed_units,
            "documented_files": len(files),
            "failed_units": len(failed_units),
        },
    }
