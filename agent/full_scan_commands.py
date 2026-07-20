import json
import os
import tempfile
from typing import Any

from agent.docs_prepare import prepare_docs_execution
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
