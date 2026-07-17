import json
import os
import tempfile
from typing import Any

from agent.codebase_documenter import (
    collect_docs_scan_input,
    finalize_docs_results,
)
from agent.docs_merge import merge_docs_worker_results
from agent.docs_prepare import prepare_docs_execution


PREPARE_STATE_SCHEMA_VERSION = "1.0"


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
            prefix=".docs-prepare-state-",
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


def prepare_codebase_docs_bundle(
    root_dir: str,
    output_dir: str,
    max_files: int | None = None,
) -> dict[str, Any]:
    """
    Repository taraması yapar ve matrix çalışması için bundle hazırlar.

    Bundle:
    - manifest.json
    - shards/*.json
    - prepare-state.json

    dosyalarını içerir.
    """
    prepared_input = collect_docs_scan_input(
        root_dir=root_dir,
        max_files=max_files,
    )

    manifest = prepare_docs_execution(
        scan_units=prepared_input["scan_plan"],
        output_dir=output_dir,
    )

    state = {
        "schema_version": PREPARE_STATE_SCHEMA_VERSION,
        "repository_files": prepared_input["repository_files"],
        "selected_files": prepared_input["selected_files"],
        "changed_or_new_files": prepared_input[
            "changed_or_new_files"
        ],
        "detected_changed_or_new_files": prepared_input[
            "detected_changed_or_new_files"
        ],
        "unchanged_files": prepared_input["unchanged_files"],
        "skipped_by_limit": prepared_input["skipped_by_limit"],
        "deleted_paths": sorted(
            prepared_input["deleted_paths"]
        ),
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
            f"{description} geçerli JSON değil: {input_path}"
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
            "Documentation manifestinde shards listesi bulunmalıdır."
        )

    unit_ids = []

    for shard in shards:
        if not isinstance(shard, dict):
            raise ValueError(
                "Documentation manifestinde geçersiz shard kaydı var."
            )

        shard_unit_ids = shard.get("unit_ids")

        if not isinstance(shard_unit_ids, list):
            raise ValueError(
                "Documentation shard kaydında unit_ids listesi yok."
            )

        for unit_id in shard_unit_ids:
            if not isinstance(unit_id, str) or not unit_id:
                raise ValueError(
                    "Documentation manifestinde geçersiz unit_id var."
                )

            unit_ids.append(unit_id)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError(
            "Documentation manifestinde aynı unit_id "
            "birden fazla kez bulunuyor."
        )

    return sorted(unit_ids)


def _manifest_shard_ids(
    manifest: dict[str, Any],
) -> list[str]:
    matrix = manifest.get("matrix")

    if not isinstance(matrix, dict):
        raise ValueError(
            "Documentation manifestinde matrix object bulunmalıdır."
        )

    include = matrix.get("include")

    if not isinstance(include, list):
        raise ValueError(
            "Documentation manifestinde matrix.include listesi bulunmalıdır."
        )

    shard_ids = []

    for entry in include:
        if not isinstance(entry, dict):
            raise ValueError(
                "Documentation matrix kaydı geçersiz."
            )

        shard_id = entry.get("shard_id")

        if not isinstance(shard_id, str) or not shard_id:
            raise ValueError(
                "Documentation matrix kaydında geçerli shard_id yok."
            )

        shard_ids.append(shard_id)

    if len(shard_ids) != len(set(shard_ids)):
        raise ValueError(
            "Documentation matrix içinde aynı shard_id "
            "birden fazla kez bulunuyor."
        )

    return sorted(shard_ids)


def merge_codebase_docs_bundle(
    root_dir: str,
    bundle_dir: str,
    result_paths: list[str],
    repository: str | None,
    output_json: str,
    output_markdown: str,
    max_files: int | None = None,
) -> dict[str, Any]:
    """
    Worker artifact'lerini doğrular, birleştirir ve raporları finalize eder.

    Repository scan planı prepare aşamasından sonra değiştiyse eski worker
    sonuçlarının güncel index'e yazılmasına izin verilmez.
    """
    manifest_path = os.path.join(
        bundle_dir,
        "manifest.json",
    )

    manifest = _load_json_object(
        input_path=manifest_path,
        description="Documentation manifesti",
    )

    prepared = collect_docs_scan_input(
        root_dir=root_dir,
        max_files=max_files,
    )

    expected_unit_ids = _manifest_unit_ids(manifest)
    current_unit_ids = sorted(
        unit.unit_id
        for unit in prepared["scan_plan"]
    )

    if current_unit_ids != expected_unit_ids:
        raise ValueError(
            "Repository scan planı prepare aşamasından sonra değişti. "
            "Shard bundle yeniden hazırlanmalıdır."
        )

    expected_shard_ids = _manifest_shard_ids(manifest)

    merged_result = merge_docs_worker_results(
        result_paths=result_paths,
        expected_shard_ids=expected_shard_ids,
    )

    merged_files_by_path = {}

    for file_doc in merged_result.get("files", []):
        if not isinstance(file_doc, dict):
            continue

        file_path = file_doc.get("path")

        if not isinstance(file_path, str) or not file_path:
            continue

        merged_files_by_path[file_path] = file_doc

    return finalize_docs_results(
        prepared=prepared,
        merged_files_by_path=merged_files_by_path,
        failed_units=merged_result.get("failed_units", []),
        root_dir=root_dir,
        repository=repository,
        output_json=output_json,
        output_markdown=output_markdown,
    )
