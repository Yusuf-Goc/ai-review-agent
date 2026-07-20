import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.full_scan_commands import prepare_full_scan_bundle
from agent.full_scan_planner import FullScanUnit


class FullScanCommandsTests(unittest.TestCase):
    def test_prepare_bundle_writes_full_scan_execution_state(self):
        scan_units = [
            FullScanUnit(
                unit_id="unit-001",
                kind="small_file_batch",
                total_lines=500,
                total_chars=25_000,
                risk_score=2,
            ),
            FullScanUnit(
                unit_id="unit-002",
                kind="large_file_slice",
                total_lines=700,
                total_chars=32_000,
                risk_score=8,
            ),
        ]

        prepared_input = {
            "scan_plan": scan_units,
            "repository_files": 120,
            "selected_files": 100,
            "skipped_files": 20,
            "file_items": [],
            "read_errors": [
                {
                    "path": "src/unreadable.py",
                    "error": "decode error",
                }
            ],
        }

        manifest = {
            "schema_version": "1.0",
            "unit_count": 2,
            "shard_count": 2,
            "matrix": {
                "include": [
                    {
                        "shard_id": "docs-shard-001",
                        "payload_file": (
                            "shards/docs-shard-001.json"
                        ),
                    },
                    {
                        "shard_id": "docs-shard-002",
                        "payload_file": (
                            "shards/docs-shard-002.json"
                        ),
                    },
                ]
            },
            "shards": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch(
                    "agent.full_scan_commands.collect_full_scan_input",
                    return_value=prepared_input,
                ) as collect_input,
                patch(
                    "agent.full_scan_commands.prepare_docs_execution",
                    return_value=manifest,
                    create=True,
                ) as prepare_execution,
            ):
                result = prepare_full_scan_bundle(
                    root_dir="/repo",
                    output_dir=temp_dir,
                    max_files=None,
                )

            collect_input.assert_called_once_with(
                root_dir="/repo",
                max_files=None,
            )

            prepare_execution.assert_called_once_with(
                scan_units=scan_units,
                output_dir=temp_dir,
            )

            state_path = os.path.join(
                temp_dir,
                "prepare-state.json",
            )

            self.assertTrue(os.path.isfile(state_path))

            with open(
                state_path,
                "r",
                encoding="utf-8",
            ) as state_file:
                state = json.load(state_file)

            self.assertEqual(state["schema_version"], "1.0")
            self.assertEqual(
                state["mode"],
                "full_repository_scan",
            )
            self.assertEqual(state["repository_files"], 120)
            self.assertEqual(state["selected_files"], 100)
            self.assertEqual(state["skipped_files"], 20)
            self.assertEqual(state["planned_units"], 2)
            self.assertEqual(state["shard_count"], 2)
            self.assertEqual(
                state["read_errors"],
                prepared_input["read_errors"],
            )

            self.assertEqual(result["manifest"], manifest)
            self.assertEqual(result["state"], state)
            self.assertEqual(
                result["state_path"],
                state_path,
            )


if __name__ == "__main__":
    unittest.main()
