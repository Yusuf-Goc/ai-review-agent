import unittest

from agent.docs_manifest import build_docs_manifest
from agent.docs_sharding import DocsShard, build_docs_shards
from agent.full_scan_planner import FullScanUnit


class DocsManifestTests(unittest.TestCase):
    @staticmethod
    def make_unit(unit_id: str, lines: int = 500) -> FullScanUnit:
        return FullScanUnit(
            unit_id=unit_id,
            kind="single_file",
            total_lines=lines,
            total_chars=lines * 50,
            risk_score=0,
        )

    def test_small_repository_manifest_has_one_matrix_entry(self):
        units = [
            self.make_unit("unit-001"),
            self.make_unit("unit-002"),
        ]

        shards = build_docs_shards(units)
        manifest = build_docs_manifest(units, shards)

        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["shard_count"], 1)
        self.assertEqual(
            manifest["matrix"],
            {
                "include": [
                    {
                        "shard_id": "docs-shard-001",
                        "payload_file": (
                            "shards/docs-shard-001.json"
                        ),
                    }
                ]
            },
        )

    def test_manifest_contains_every_unit_exactly_once(self):
        units = [
            self.make_unit(
                unit_id=f"unit-{index:03d}",
                lines=1_000,
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

        manifest = build_docs_manifest(units, shards)

        assigned = [
            unit_id
            for shard in manifest["shards"]
            for unit_id in shard["unit_ids"]
        ]

        self.assertCountEqual(
            assigned,
            [unit.unit_id for unit in units],
        )
        self.assertEqual(len(assigned), len(set(assigned)))

    def test_manifest_rejects_duplicate_unit_assignment(self):
        units = [
            self.make_unit("unit-001"),
        ]

        shards = [
            DocsShard(
                shard_id="docs-shard-001",
                unit_ids=["unit-001"],
            ),
            DocsShard(
                shard_id="docs-shard-002",
                unit_ids=["unit-001"],
            ),
        ]

        with self.assertRaisesRegex(
            ValueError,
            "birden fazla shard",
        ):
            build_docs_manifest(units, shards)

    def test_manifest_rejects_missing_unit_assignment(self):
        units = [
            self.make_unit("unit-001"),
            self.make_unit("unit-002"),
        ]

        shards = [
            DocsShard(
                shard_id="docs-shard-001",
                unit_ids=["unit-001"],
            ),
        ]

        with self.assertRaisesRegex(
            ValueError,
            "eksik",
        ):
            build_docs_manifest(units, shards)


if __name__ == "__main__":
    unittest.main()
