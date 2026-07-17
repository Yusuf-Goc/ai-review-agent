import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.docs_commands import prepare_codebase_docs_bundle
from agent.full_scan_planner import FullScanUnit


class DocsCommandsTests(unittest.TestCase):
    def test_prepare_bundle_writes_reusable_execution_state(self):
        scan_unit = FullScanUnit(
            unit_id="unit-001",
            kind="single_file",
            total_lines=500,
            total_chars=25_000,
            risk_score=2,
        )

        prepared_input = {
            "scan_plan": [scan_unit],
            "repository_files": 10,
            "selected_files": 2,
            "changed_or_new_files": 2,
            "detected_changed_or_new_files": 3,
            "unchanged_files": 7,
            "skipped_by_limit": 1,
            "deleted_paths": ["src/deleted.py"],
            "index_path": "/repo/.ai-review/index.json",
        }

        manifest = {
            "schema_version": "1.0",
            "unit_count": 1,
            "shard_count": 1,
            "matrix": {
                "include": [
                    {
                        "shard_id": "docs-shard-001",
                        "payload_file": (
                            "shards/docs-shard-001.json"
                        ),
                    }
                ]
            },
            "shards": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch(
                    "agent.docs_commands.collect_docs_scan_input",
                    return_value=prepared_input,
                ) as collect_input,
                patch(
                    "agent.docs_commands.prepare_docs_execution",
                    return_value=manifest,
                ) as prepare_execution,
            ):
                result = prepare_codebase_docs_bundle(
                    root_dir="/repo",
                    output_dir=temp_dir,
                    max_files=None,
                )

            collect_input.assert_called_once_with(
                root_dir="/repo",
                max_files=None,
            )
            prepare_execution.assert_called_once_with(
                scan_units=[scan_unit],
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
            self.assertEqual(state["repository_files"], 10)
            self.assertEqual(state["selected_files"], 2)
            self.assertEqual(
                state["detected_changed_or_new_files"],
                3,
            )
            self.assertEqual(state["skipped_by_limit"], 1)
            self.assertEqual(
                state["deleted_paths"],
                ["src/deleted.py"],
            )
            self.assertEqual(state["planned_units"], 1)
            self.assertEqual(state["shard_count"], 1)

            self.assertEqual(result["manifest"], manifest)
            self.assertEqual(
                result["state_path"],
                state_path,
            )


if __name__ == "__main__":
    unittest.main()
