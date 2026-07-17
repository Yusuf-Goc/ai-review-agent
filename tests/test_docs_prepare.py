import os
import tempfile
import unittest

from agent.docs_prepare import prepare_docs_execution
from agent.full_scan_planner import FullScanUnit


class DocsPrepareTests(unittest.TestCase):
    @staticmethod
    def make_unit(
        unit_id: str,
        total_lines: int,
        total_chars: int,
    ) -> FullScanUnit:
        return FullScanUnit(
            unit_id=unit_id,
            kind="single_file",
            total_lines=total_lines,
            total_chars=total_chars,
            risk_score=0,
        )

    def test_small_repository_prepares_single_shard(self):
        units = [
            self.make_unit(
                unit_id="unit-001",
                total_lines=500,
                total_chars=25_000,
            ),
            self.make_unit(
                unit_id="unit-002",
                total_lines=400,
                total_chars=20_000,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = prepare_docs_execution(
                scan_units=units,
                output_dir=temp_dir,
            )

            self.assertEqual(manifest["shard_count"], 1)
            self.assertEqual(
                manifest["matrix"]["include"],
                [
                    {
                        "shard_id": "docs-shard-001",
                        "payload_file": (
                            "shards/docs-shard-001.json"
                        ),
                    }
                ],
            )

            self.assertTrue(
                os.path.isfile(
                    os.path.join(temp_dir, "manifest.json")
                )
            )
            self.assertTrue(
                os.path.isfile(
                    os.path.join(
                        temp_dir,
                        "shards",
                        "docs-shard-001.json",
                    )
                )
            )

    def test_large_repository_prepares_multiple_shards(self):
        units = [
            self.make_unit(
                unit_id=f"unit-{index:03d}",
                total_lines=1_000,
                total_chars=50_000,
            )
            for index in range(1, 13)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = prepare_docs_execution(
                scan_units=units,
                output_dir=temp_dir,
                target_lines_per_shard=3_000,
                target_chars_per_shard=150_000,
                target_units_per_shard=4,
                max_shards=8,
            )

            self.assertEqual(manifest["shard_count"], 4)
            self.assertEqual(
                len(manifest["matrix"]["include"]),
                4,
            )

            assigned_unit_ids = [
                unit_id
                for shard in manifest["shards"]
                for unit_id in shard["unit_ids"]
            ]

            self.assertCountEqual(
                assigned_unit_ids,
                [unit.unit_id for unit in units],
            )

            for matrix_entry in manifest["matrix"]["include"]:
                payload_path = os.path.join(
                    temp_dir,
                    matrix_entry["payload_file"],
                )
                self.assertTrue(os.path.isfile(payload_path))

    def test_empty_scan_plan_writes_empty_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = prepare_docs_execution(
                scan_units=[],
                output_dir=temp_dir,
            )

            self.assertEqual(manifest["shard_count"], 0)
            self.assertEqual(
                manifest["matrix"],
                {"include": []},
            )
            self.assertTrue(
                os.path.isfile(
                    os.path.join(temp_dir, "manifest.json")
                )
            )


if __name__ == "__main__":
    unittest.main()
