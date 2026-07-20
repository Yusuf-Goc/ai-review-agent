import json
import os
import tempfile
from typing import Any

from agent.docs_prepare import prepare_docs_execution
from agent.full_scan_merge import merge_full_scan_worker_results
from agent.reviewer import collect_full_scan_input


FULL_SCAN_PREPARE_STATE_SCHEMA_VERSION = "1.0"


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
            prefix=".full-scan-prepare-state-",
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


def prepare_full_scan_bundle(
    root_dir: str,
    output_dir: str,
    max_files: int | None = None,
) -> dict[str, Any]:
    """
    Repository full-scan matrix çalışması için manifest ve payload üretir.

    Bu aşama yalnızca dosyaları toplar ve scan unit'lerini shard'lara ayırır.
    Gemini çağrısı veya GitHub issue oluşturma işlemi yapmaz.
    """
    prepared_input = collect_full_scan_input(
        root_dir=root_dir,
        max_files=max_files,
    )

    manifest = prepare_docs_execution(
        scan_units=prepared_input["scan_plan"],
        output_dir=output_dir,
    )

    state = {
        "schema_version": FULL_SCAN_PREPARE_STATE_SCHEMA_VERSION,
        "mode": "full_repository_scan",
        "repository_files": prepared_input["repository_files"],
        "selected_files": prepared_input["selected_files"],
        "skipped_files": prepared_input["skipped_files"],
        "read_errors": prepared_input["read_errors"],
        "planned_units": len(prepared_input["scan_plan"]),
        "shard_count": manifest["shard_count"],
    }

    state_path = os.path.join(
        output_dir,
        "prepare-state.json",
    )

    _atomic_write_json(
        payload=state,
        output_path=state_path,
    )

    return {
        "manifest": manifest,
        "state": state,
        "state_path": state_path,
    }

def _load_json_object(
    input_path: str,
    description: str,
) -> dict[str, Any]:
    try:
        with open(
            input_path,
            "r",
            encoding="utf-8",
        ) as input_file:
            payload = json.load(input_file)

    except FileNotFoundError as exc:
        raise ValueError(
            f"{description} bulunamadı: {input_path}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{description} geçerli JSON değil: "
            f"{input_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"{description} JSON object olmalıdır."
        )

    return payload


def _manifest_unit_ids(
    manifest: dict[str, Any],
) -> list[str]:
    shards = manifest.get("shards")

    if not isinstance(shards, list):
        raise ValueError(
            "Full scan manifestinde shards listesi "
            "bulunmalıdır."
        )

    unit_ids = []

    for shard in shards:
        if not isinstance(shard, dict):
            raise ValueError(
                "Full scan manifestinde geçersiz "
                "shard kaydı var."
            )

        shard_unit_ids = shard.get("unit_ids")

        if not isinstance(shard_unit_ids, list):
            raise ValueError(
                "Full scan shard kaydında unit_ids "
                "listesi bulunmalıdır."
            )

        for unit_id in shard_unit_ids:
            if not isinstance(unit_id, str) or not unit_id:
                raise ValueError(
                    "Full scan manifestinde geçersiz "
                    "unit_id var."
                )

            unit_ids.append(unit_id)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError(
            "Full scan manifestinde aynı unit_id "
            "birden fazla kez bulunuyor."
        )

    return sorted(unit_ids)


def _manifest_shard_ids(
    manifest: dict[str, Any],
) -> list[str]:
    matrix = manifest.get("matrix")

    if not isinstance(matrix, dict):
        raise ValueError(
            "Full scan manifestinde matrix object "
            "bulunmalıdır."
        )

    include = matrix.get("include")

    if not isinstance(include, list):
        raise ValueError(
            "Full scan manifestinde matrix.include "
            "listesi bulunmalıdır."
        )

    shard_ids = []

    for entry in include:
        if not isinstance(entry, dict):
            raise ValueError(
                "Full scan matrix kaydı geçersiz."
            )

        shard_id = entry.get("shard_id")

        if not isinstance(shard_id, str) or not shard_id:
            raise ValueError(
                "Full scan matrix kaydında geçerli "
                "shard_id bulunmalıdır."
            )

        shard_ids.append(shard_id)

    if len(shard_ids) != len(set(shard_ids)):
        raise ValueError(
            "Full scan matrix içinde aynı shard_id "
            "birden fazla kez bulunuyor."
        )

    return sorted(shard_ids)


def merge_full_scan_bundle(
    root_dir: str,
    bundle_dir: str,
    result_paths: list[str],
    max_files: int | None = None,
) -> dict[str, Any]:
    """
    Full-scan shard sonuçlarını doğrular ve tek review sonucu üretir.

    Prepare sonrasında repository scan planı değişmişse eski worker
    sonuçlarının güncel repository için raporlanmasına izin verilmez.
    """
    manifest_path = os.path.join(
        bundle_dir,
        "manifest.json",
    )

    manifest = _load_json_object(
        input_path=manifest_path,
        description="Full scan manifesti",
    )

    prepared = collect_full_scan_input(
        root_dir=root_dir,
        max_files=max_files,
    )

    expected_unit_ids = _manifest_unit_ids(
        manifest
    )
    current_unit_ids = sorted(
        unit.unit_id
        for unit in prepared["scan_plan"]
    )

    if current_unit_ids != expected_unit_ids:
        raise ValueError(
            "Repository scan planı prepare aşamasından "
            "sonra değişti. Full scan shard bundle "
            "yeniden hazırlanmalıdır."
        )

    expected_shard_ids = _manifest_shard_ids(
        manifest
    )

    merged = merge_full_scan_worker_results(
        result_paths=result_paths,
        expected_shard_ids=expected_shard_ids,
    )

    findings = merged["findings"]
    merged_stats = merged["stats"]

    summary = (
        "Paralel full repository scan tamamlandı. "
        f"{prepared['selected_files']} dosya, "
        f"{merged_stats['planned_units']} analiz birimi ve "
        f"{len(expected_shard_ids)} shard işlendi. "
        f"{merged_stats['first_pass_success']} birim ilk "
        "denemede, "
        f"{merged_stats['second_pass_success']} birim ikinci "
        "denemede, "
        f"{merged_stats['fallback_pass_success']} birim küçük "
        "parçalara bölündükten sonra başarıyla incelendi. "
        f"{merged_stats['final_failed_units']} birim tüm "
        "denemelere rağmen başarısız oldu."
    )

    if prepared["skipped_files"]:
        summary += (
            f" Limit nedeniyle "
            f"{prepared['skipped_files']} dosya atlandı."
        )

    if findings:
        summary += (
            f" Toplam {len(findings)} bulgu üretildi."
        )
    else:
        summary += " Kritik bulgu bulunamadı."

    full_scan_stats = {
        "repository_files": prepared[
            "repository_files"
        ],
        "selected_files": prepared[
            "selected_files"
        ],
        "skipped_files": prepared[
            "skipped_files"
        ],
        "read_errors": len(
            prepared["read_errors"]
        ),
        "shard_count": len(
            expected_shard_ids
        ),
        "completed_shards": len(
            merged["completed_shards"]
        ),
        **merged_stats,
    }

    return {
        "summary": summary,
        "findings": findings,
        "failed_units": merged[
            "failed_units"
        ],
        "full_scan_stats": full_scan_stats,
    }

