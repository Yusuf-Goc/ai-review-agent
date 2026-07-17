import json
import os
import tempfile
from typing import Any

from agent.codebase_documenter import collect_docs_scan_input
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
