import json
import os
import tempfile
import unittest

from agent.full_scan_merge import (
    merge_full_scan_worker_results,
)


class FullScanMergeTests(unittest.TestCase):
    @staticmethod
    def write_result(
        result_path: str,
        shard_id: str,
        findings: list[dict],
        failed_units: list[dict] | None = None,
        stats: dict | None = None,
    ) -> None:
        os.makedirs(
            os.path.dirname(result_path),
            exist_ok=True,
        )

        payload = {
            "schema_version": "1.0",
            "mode": "full_repository_scan",
            "shard_id": shard_id,
            "unit_count": (
                stats or {}
            ).get("planned_units", 0),
            "findings": findings,
            "failed_units": failed_units or [],
            "stats": stats or {},
        }

        with open(
            result_path,
            "w",
            encoding="utf-8",
        ) as result_file:
            json.dump(payload, result_file)

    def test_merge_combines_deduplicates_and_sums_results(self):
        duplicate_finding = {
            "file": "src/example.py",
            "line": 10,
            "severity": "high",
            "category": "logic_error",
            "message": "Aynı bulgu",
            "suggestion": "Kontrol ekleyin.",
        }

        unique_finding = {
            "file": "src/security.py",
            "line": 20,
            "severity": "critical",
            "category": "security_risk",
            "message": "Doğrulanmamış komut girdisi.",
            "suggestion": "Girdiyi doğrulayın.",
        }

        first_stats = {
            "planned_units": 2,
            "first_pass_success": 2,
            "first_pass_failed": 0,
            "second_pass_success": 0,
            "second_pass_failed": 0,
            "fallback_units": 0,
            "fallback_pass_success": 0,
            "final_failed_units": 0,
            "total_successful_units": 2,
        }

        second_stats = {
            "planned_units": 1,
            "first_pass_success": 0,
            "first_pass_failed": 1,
            "second_pass_success": 1,
            "second_pass_failed": 0,
            "fallback_units": 0,
            "fallback_pass_success": 0,
            "final_failed_units": 0,
            "total_successful_units": 1,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = os.path.join(
                temp_dir,
                "docs-shard-001.json",
            )
            second_path = os.path.join(
                temp_dir,
                "docs-shard-002.json",
            )

            self.write_result(
                first_path,
                shard_id="docs-shard-001",
                findings=[duplicate_finding],
                stats=first_stats,
            )
            self.write_result(
                second_path,
                shard_id="docs-shard-002",
                findings=[
                    duplicate_finding,
                    unique_finding,
                ],
                failed_units=[
                    {
                        "unit_id": "unit-003-fallback-1",
                        "affected_files": "src/other.py",
                        "summary": "Model yanıt vermedi.",
                    }
                ],
                stats=second_stats,
            )

            merged = merge_full_scan_worker_results(
                result_paths=[
                    second_path,
                    first_path,
                ],
                expected_shard_ids=[
                    "docs-shard-001",
                    "docs-shard-002",
                ],
            )

        self.assertEqual(
            merged["completed_shards"],
            [
                "docs-shard-001",
                "docs-shard-002",
            ],
        )
        self.assertEqual(
            merged["findings"],
            [
                duplicate_finding,
                unique_finding,
            ],
        )
        self.assertEqual(
            merged["failed_units"],
            [
                {
                    "unit_id": "unit-003-fallback-1",
                    "affected_files": "src/other.py",
                    "summary": "Model yanıt vermedi.",
                }
            ],
        )
        self.assertEqual(
            merged["stats"],
            {
                "planned_units": 3,
                "first_pass_success": 2,
                "first_pass_failed": 1,
                "second_pass_success": 1,
                "second_pass_failed": 0,
                "fallback_units": 0,
                "fallback_pass_success": 0,
                "final_failed_units": 0,
                "total_successful_units": 3,
            },
        )

    def test_merge_rejects_missing_shard_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = os.path.join(
                temp_dir,
                "docs-shard-001.json",
            )

            self.write_result(
                result_path,
                shard_id="docs-shard-001",
                findings=[],
            )

            with self.assertRaisesRegex(
                ValueError,
                "eksik",
            ):
                merge_full_scan_worker_results(
                    result_paths=[result_path],
                    expected_shard_ids=[
                        "docs-shard-001",
                        "docs-shard-002",
                    ],
                )

    def test_merge_rejects_duplicate_shard_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = os.path.join(
                temp_dir,
                "first.json",
            )
            second_path = os.path.join(
                temp_dir,
                "second.json",
            )

            self.write_result(
                first_path,
                shard_id="docs-shard-001",
                findings=[],
            )
            self.write_result(
                second_path,
                shard_id="docs-shard-001",
                findings=[],
            )

            with self.assertRaisesRegex(
                ValueError,
                "birden fazla",
            ):
                merge_full_scan_worker_results(
                    result_paths=[
                        first_path,
                        second_path,
                    ],
                    expected_shard_ids=[
                        "docs-shard-001",
                    ],
                )


if __name__ == "__main__":
    unittest.main()
