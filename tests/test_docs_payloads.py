import json
import os
import tempfile
import unittest

from agent.docs_payloads import write_docs_payload_bundle
from agent.docs_sharding import DocsShard
from agent.full_scan_planner import FullScanSlice, FullScanUnit


class DocsPayloadTests(unittest.TestCase):
    @staticmethod
    def make_unit(
        unit_id: str,
        path: str,
        content: str,
    ) -> FullScanUnit:
        file_slice = FullScanSlice(
            path=path,
            language="python",
            start_line=1,
            end_line=2,
            content=content,
            line_count=2,
            char_count=len(content),
            part_label="full-file",
        )

        return FullScanUnit(
            unit_id=unit_id,
            kind="single_file",
            slices=[file_slice],
            total_lines=2,
            total_chars=len(content),
            risk_score=3,
        )

    def test_bundle_writes_manifest_and_shard_payload(self):
        unit = self.make_unit(
            unit_id="unit-001",
            path="src/example.py",
            content="a = 1\nb = 2\n",
        )

        shard = DocsShard(
            shard_id="docs-shard-001",
            unit_ids=["unit-001"],
            total_lines=unit.total_lines,
            total_chars=unit.total_chars,
            total_risk_score=unit.risk_score,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = write_docs_payload_bundle(
                scan_units=[unit],
                shards=[shard],
                output_dir=temp_dir,
            )

            manifest_path = os.path.join(
                temp_dir,
                "manifest.json",
            )
            payload_path = os.path.join(
                temp_dir,
                "shards",
                "docs-shard-001.json",
            )

            self.assertTrue(os.path.isfile(manifest_path))
            self.assertTrue(os.path.isfile(payload_path))

            with open(
                payload_path,
                "r",
                encoding="utf-8",
            ) as payload_file:
                payload = json.load(payload_file)

            self.assertEqual(payload["schema_version"], "1.0")
            self.assertEqual(payload["shard_id"], "docs-shard-001")
            self.assertEqual(payload["unit_count"], 1)
            self.assertEqual(payload["units"][0]["unit_id"], "unit-001")

            file_slice = payload["units"][0]["slices"][0]

            self.assertEqual(file_slice["path"], "src/example.py")
            self.assertEqual(file_slice["content"], "a = 1\nb = 2\n")

            self.assertEqual(manifest["shard_count"], 1)
            self.assertEqual(
                manifest["matrix"]["include"][0]["payload_file"],
                "shards/docs-shard-001.json",
            )

    def test_payload_contains_only_units_assigned_to_shard(self):
        first_unit = self.make_unit(
            unit_id="unit-001",
            path="src/first.py",
            content="first = 1\nvalue = 2\n",
        )
        second_unit = self.make_unit(
            unit_id="unit-002",
            path="src/second.py",
            content="second = 1\nvalue = 2\n",
        )

        shards = [
            DocsShard(
                shard_id="docs-shard-001",
                unit_ids=["unit-001"],
                total_lines=first_unit.total_lines,
                total_chars=first_unit.total_chars,
                total_risk_score=first_unit.risk_score,
            ),
            DocsShard(
                shard_id="docs-shard-002",
                unit_ids=["unit-002"],
                total_lines=second_unit.total_lines,
                total_chars=second_unit.total_chars,
                total_risk_score=second_unit.risk_score,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            write_docs_payload_bundle(
                scan_units=[second_unit, first_unit],
                shards=shards,
                output_dir=temp_dir,
            )

            first_payload_path = os.path.join(
                temp_dir,
                "shards",
                "docs-shard-001.json",
            )
            second_payload_path = os.path.join(
                temp_dir,
                "shards",
                "docs-shard-002.json",
            )

            with open(
                first_payload_path,
                "r",
                encoding="utf-8",
            ) as payload_file:
                first_payload = json.load(payload_file)

            with open(
                second_payload_path,
                "r",
                encoding="utf-8",
            ) as payload_file:
                second_payload = json.load(payload_file)

            self.assertEqual(
                [unit["unit_id"] for unit in first_payload["units"]],
                ["unit-001"],
            )
            self.assertEqual(
                [unit["unit_id"] for unit in second_payload["units"]],
                ["unit-002"],
            )


if __name__ == "__main__":
    unittest.main()
