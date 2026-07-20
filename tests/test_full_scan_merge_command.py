import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.full_scan_commands import merge_full_scan_bundle
from agent.full_scan_planner import FullScanUnit


class FullScanMergeCommandTests(unittest.TestCase):
    @staticmethod
    def make_unit(unit_id: str) -> FullScanUnit:
        return FullScanUnit(
            unit_id=unit_id,
            kind="small_file_batch",
            total_lines=100,
            total_chars=2_000,
            risk_score=1,
        )

    @staticmethod
    def write_manifest(
        bundle_dir: str,
        unit_ids: list[str],
    ) -> None:
        shards = []

        for index, unit_id in enumerate(
            unit_ids,
            start=1,
        ):
            shard_id = f"docs-shard-{index:03d}"

            shards.append(
                {
                    "shard_id": shard_id,
                    "payload_file": (
                        f"shards/{shard_id}.json"
                    ),
                    "unit_ids": [unit_id],
                    "unit_count": 1,
                    "total_lines": 100,
                    "total_chars": 2_000,
                    "total_risk_score": 1,
                }
            )

        manifest = {
            "schema_version": "1.0",
            "unit_count": len(unit_ids),
            "shard_count": len(shards),
            "matrix": {
                "include": [
                    {
                        "shard_id": shard["shard_id"],
                        "payload_file": shard[
                            "payload_file"
                        ],
                    }
                    for shard in shards
                ]
            },
            "shards": shards,
        }

        with open(
            os.path.join(bundle_dir, "manifest.json"),
            "w",
            encoding="utf-8",
        ) as manifest_file:
            json.dump(manifest, manifest_file)

    def test_merge_bundle_returns_single_review_result(self):
        scan_units = [
            self.make_unit("unit-001"),
            self.make_unit("unit-002"),
        ]

        prepared = {
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

        finding = {
            "file": "src/example.py",
            "line": 15,
            "severity": "high",
            "category": "logic_error",
            "message": "Kontrolsüz bölme işlemi.",
            "suggestion": "Böleni doğrulayın.",
        }

        failed_unit = {
            "unit_id": "unit-002-fallback-1",
            "affected_files": "src/other.py",
            "summary": "Model yanıt vermedi.",
        }

        merged_result = {
            "completed_shards": [
                "docs-shard-001",
                "docs-shard-002",
            ],
            "findings": [finding],
            "failed_units": [failed_unit],
            "stats": {
                "planned_units": 2,
                "first_pass_success": 1,
                "first_pass_failed": 1,
                "second_pass_success": 0,
                "second_pass_failed": 1,
                "fallback_units": 1,
                "fallback_pass_success": 0,
                "final_failed_units": 1,
                "total_successful_units": 1,
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_manifest(
                temp_dir,
                unit_ids=["unit-001", "unit-002"],
            )

            result_paths = [
                "/results/docs-shard-001.json",
                "/results/docs-shard-002.json",
            ]

            with (
                patch(
                    "agent.full_scan_commands.collect_full_scan_input",
                    return_value=prepared,
                ) as collect_input,
                patch(
                    (
                        "agent.full_scan_commands."
                        "merge_full_scan_worker_results"
                    ),
                    return_value=merged_result,
                    create=True,
                ) as merge_results,
            ):
                review_result = merge_full_scan_bundle(
                    root_dir="/repo",
                    bundle_dir=temp_dir,
                    result_paths=result_paths,
                    max_files=None,
                )

            collect_input.assert_called_once_with(
                root_dir="/repo",
                max_files=None,
            )

            merge_results.assert_called_once_with(
                result_paths=result_paths,
                expected_shard_ids=[
                    "docs-shard-001",
                    "docs-shard-002",
                ],
            )

            self.assertEqual(
                review_result["findings"],
                [finding],
            )
            self.assertEqual(
                review_result["failed_units"],
                [failed_unit],
            )

            stats = review_result["full_scan_stats"]

            self.assertEqual(
                stats["repository_files"],
                120,
            )
            self.assertEqual(
                stats["selected_files"],
                100,
            )
            self.assertEqual(
                stats["planned_units"],
                2,
            )
            self.assertEqual(
                stats["shard_count"],
                2,
            )
            self.assertEqual(
                stats["completed_shards"],
                2,
            )
            self.assertEqual(
                stats["skipped_files"],
                20,
            )
            self.assertEqual(
                stats["read_errors"],
                1,
            )
            self.assertEqual(
                stats["final_failed_units"],
                1,
            )

            self.assertIn(
                "100 dosya",
                review_result["summary"],
            )
            self.assertIn(
                "2 shard",
                review_result["summary"],
            )
            self.assertIn(
                "1 bulgu",
                review_result["summary"],
            )

    def test_merge_rejects_repository_changed_after_prepare(self):
        prepared = {
            "scan_plan": [
                self.make_unit("unit-999"),
            ],
            "repository_files": 1,
            "selected_files": 1,
            "skipped_files": 0,
            "file_items": [],
            "read_errors": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_manifest(
                temp_dir,
                unit_ids=["unit-001"],
            )

            with (
                patch(
                    "agent.full_scan_commands.collect_full_scan_input",
                    return_value=prepared,
                ),
                patch(
                    (
                        "agent.full_scan_commands."
                        "merge_full_scan_worker_results"
                    ),
                    create=True,
                ) as merge_results,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "değişti",
                ):
                    merge_full_scan_bundle(
                        root_dir="/repo",
                        bundle_dir=temp_dir,
                        result_paths=[],
                        max_files=None,
                    )

            merge_results.assert_not_called()


if __name__ == "__main__":
    unittest.main()
