import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.docs_commands import merge_codebase_docs_bundle
from agent.full_scan_planner import FullScanUnit


class DocsMergeCommandTests(unittest.TestCase):
    @staticmethod
    def make_unit(unit_id: str) -> FullScanUnit:
        return FullScanUnit(
            unit_id=unit_id,
            kind="single_file",
            total_lines=10,
            total_chars=100,
            risk_score=0,
        )

    @staticmethod
    def write_manifest(
        bundle_dir: str,
        unit_id: str = "unit-001",
    ) -> None:
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
            "shards": [
                {
                    "shard_id": "docs-shard-001",
                    "payload_file": (
                        "shards/docs-shard-001.json"
                    ),
                    "unit_ids": [unit_id],
                    "unit_count": 1,
                    "total_lines": 10,
                    "total_chars": 100,
                    "total_risk_score": 0,
                }
            ],
        }

        with open(
            os.path.join(bundle_dir, "manifest.json"),
            "w",
            encoding="utf-8",
        ) as manifest_file:
            json.dump(manifest, manifest_file)

    def test_merge_bundle_finalizes_worker_results(self):
        file_doc = {
            "path": "src/example.py",
            "language": "python",
            "purpose": "Örnek dosya",
        }

        prepared = {
            "scan_plan": [self.make_unit("unit-001")],
            "index": {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {},
            },
            "index_path": "/repo/.ai-review/index.json",
            "file_items": [
                {
                    "path": "src/example.py",
                    "language": "python",
                    "line_count": 1,
                    "content": "print('example')\n",
                }
            ],
            "deleted_paths": [],
            "repository_files": 1,
            "selected_files": 1,
            "changed_or_new_files": 1,
            "unchanged_files": 0,
            "skipped_by_limit": 0,
        }

        merged_result = {
            "files": [file_doc],
            "failed_units": [],
            "completed_shards": ["docs-shard-001"],
        }

        expected_summary = {
            "repository": "example/repository",
            "files": [file_doc],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_manifest(temp_dir)

            result_path = os.path.join(
                temp_dir,
                "results",
                "docs-shard-001.json",
            )

            with (
                patch(
                    "agent.docs_commands.collect_docs_scan_input",
                    return_value=prepared,
                ) as collect_input,
                patch(
                    "agent.docs_commands.merge_docs_worker_results",
                    return_value=merged_result,
                    create=True,
                ) as merge_results,
                patch(
                    "agent.docs_commands.finalize_docs_results",
                    return_value=expected_summary,
                    create=True,
                ) as finalize_results,
            ):
                summary = merge_codebase_docs_bundle(
                    root_dir="/repo",
                    bundle_dir=temp_dir,
                    result_paths=[result_path],
                    repository="example/repository",
                    output_json=(
                        "/repo/.ai-review/"
                        "codebase-summary.json"
                    ),
                    output_markdown=(
                        "/repo/docs/"
                        "ai-codebase-report.md"
                    ),
                    max_files=None,
                )

            collect_input.assert_called_once_with(
                root_dir="/repo",
                max_files=None,
            )

            merge_results.assert_called_once_with(
                result_paths=[result_path],
                expected_shard_ids=["docs-shard-001"],
            )

            finalize_results.assert_called_once_with(
                prepared=prepared,
                merged_files_by_path={
                    "src/example.py": file_doc,
                },
                failed_units=[],
                root_dir="/repo",
                repository="example/repository",
                output_json=(
                    "/repo/.ai-review/"
                    "codebase-summary.json"
                ),
                output_markdown=(
                    "/repo/docs/"
                    "ai-codebase-report.md"
                ),
            )

            self.assertEqual(summary, expected_summary)

    def test_merge_rejects_scan_plan_changed_after_prepare(self):
        prepared = {
            "scan_plan": [self.make_unit("unit-002")],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_manifest(
                temp_dir,
                unit_id="unit-001",
            )

            with (
                patch(
                    "agent.docs_commands.collect_docs_scan_input",
                    return_value=prepared,
                ),
                patch(
                    "agent.docs_commands.merge_docs_worker_results",
                    create=True,
                ) as merge_results,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "değişti",
                ):
                    merge_codebase_docs_bundle(
                        root_dir="/repo",
                        bundle_dir=temp_dir,
                        result_paths=[],
                        repository="example/repository",
                        output_json="summary.json",
                        output_markdown="report.md",
                        max_files=None,
                    )

            merge_results.assert_not_called()


if __name__ == "__main__":
    unittest.main()
