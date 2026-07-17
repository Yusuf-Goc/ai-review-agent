import unittest

from agent.docs_sharding import build_docs_shards
from agent.full_scan_planner import FullScanUnit


class DocsShardingTests(unittest.TestCase):
    @staticmethod
    def make_unit(
        unit_id: str,
        total_lines: int,
        total_chars: int,
        risk_score: int = 0,
    ) -> FullScanUnit:
        return FullScanUnit(
            unit_id=unit_id,
            kind="single_file",
            total_lines=total_lines,
            total_chars=total_chars,
            risk_score=risk_score,
        )

    def test_empty_scan_plan_produces_no_shards(self):
        self.assertEqual(build_docs_shards([]), [])

    def test_small_repository_stays_in_one_shard(self):
        units = [
            self.make_unit(
                unit_id="full-scan-unit-1",
                total_lines=700,
                total_chars=35_000,
                risk_score=2,
            ),
            self.make_unit(
                unit_id="full-scan-unit-2",
                total_lines=600,
                total_chars=30_000,
                risk_score=1,
            ),
            self.make_unit(
                unit_id="full-scan-unit-3",
                total_lines=500,
                total_chars=25_000,
            ),
        ]

        shards = build_docs_shards(
            units,
            target_lines_per_shard=6_000,
            target_chars_per_shard=300_000,
            target_units_per_shard=24,
            max_shards=20,
        )

        self.assertEqual(len(shards), 1)
        self.assertEqual(shards[0].shard_id, "docs-shard-001")
        self.assertCountEqual(
            shards[0].unit_ids,
            [unit.unit_id for unit in units],
        )

    def test_large_repository_is_split_without_missing_units(self):
        units = [
            self.make_unit(
                unit_id=f"full-scan-unit-{index}",
                total_lines=1_000,
                total_chars=50_000,
                risk_score=index % 3,
            )
            for index in range(1, 13)
        ]

        shards = build_docs_shards(
            units,
            target_lines_per_shard=3_000,
            target_chars_per_shard=150_000,
            target_units_per_shard=4,
            max_shards=8,
        )

        self.assertEqual(len(shards), 4)

        assigned_unit_ids = [
            unit_id
            for shard in shards
            for unit_id in shard.unit_ids
        ]

        expected_unit_ids = [unit.unit_id for unit in units]

        self.assertCountEqual(assigned_unit_ids, expected_unit_ids)
        self.assertEqual(
            len(assigned_unit_ids),
            len(set(assigned_unit_ids)),
        )

        shard_line_counts = [
            shard.total_lines
            for shard in shards
        ]

        self.assertLessEqual(
            max(shard_line_counts) - min(shard_line_counts),
            1_000,
        )

    def test_shard_manifest_is_independent_of_input_order(self):
        units = [
            self.make_unit(
                unit_id=f"full-scan-unit-{index}",
                total_lines=300 + (index * 100),
                total_chars=15_000 + (index * 5_000),
                risk_score=index % 4,
            )
            for index in range(1, 11)
        ]

        options = {
            "target_lines_per_shard": 2_000,
            "target_chars_per_shard": 100_000,
            "target_units_per_shard": 4,
            "max_shards": 8,
        }

        forward = build_docs_shards(units, **options)
        reversed_input = build_docs_shards(
            list(reversed(units)),
            **options,
        )

        forward_manifest = [
            (
                shard.shard_id,
                shard.unit_ids,
                shard.total_lines,
                shard.total_chars,
                shard.total_risk_score,
            )
            for shard in forward
        ]

        reversed_manifest = [
            (
                shard.shard_id,
                shard.unit_ids,
                shard.total_lines,
                shard.total_chars,
                shard.total_risk_score,
            )
            for shard in reversed_input
        ]

        self.assertEqual(forward_manifest, reversed_manifest)


if __name__ == "__main__":
    unittest.main()
