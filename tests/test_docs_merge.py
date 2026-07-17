import json
import os
import tempfile
import unittest

from agent.docs_merge import merge_docs_worker_results


class DocsMergeTests(unittest.TestCase):
    @staticmethod
    def write_result(
        output_path: str,
        shard_id: str,
        files: list[dict],
        failed_units: list[dict] | None = None,
        processed_units: int = 1,
    ) -> None:
        failed_units = failed_units or []

        payload = {
            "schema_version": "1.0",
            "shard_id": shard_id,
            "unit_count": processed_units,
            "files": files,
            "failed_units": failed_units,
            "stats": {
                "processed_units": processed_units,
                "documented_files": len(files),
                "failed_units": len(failed_units),
            },
        }

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as result_file:
            json.dump(
                payload,
                result_file,
                ensure_ascii=False,
            )

    def test_merge_combines_files_from_multiple_shards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = os.path.join(temp_dir, "first.json")
            second_path = os.path.join(temp_dir, "second.json")

            self.write_result(
                output_path=first_path,
                shard_id="docs-shard-001",
                files=[
                    {
                        "path": "src/example.py",
                        "purpose": "İlk açıklama",
                        "main_components": [
                            {
                                "name": "first",
                                "type": "function",
                                "description": "İlk fonksiyon",
                                "important_logic": "",
                            }
                        ],
                    }
                ],
            )

            self.write_result(
                output_path=second_path,
                shard_id="docs-shard-002",
                files=[
                    {
                        "path": "src/example.py",
                        "purpose": "İkinci açıklama",
                        "main_components": [
                            {
                                "name": "second",
                                "type": "function",
                                "description": "İkinci fonksiyon",
                                "important_logic": "",
                            }
                        ],
                    },
                    {
                        "path": "src/other.py",
                        "purpose": "Diğer dosya",
                        "main_components": [],
                    },
                ],
            )

            merged = merge_docs_worker_results(
                result_paths=[
                    second_path,
                    first_path,
                ],
                expected_shard_ids=[
                    "docs-shard-001",
                    "docs-shard-002",
                ],
            )

            self.assertEqual(merged["shard_count"], 2)
            self.assertEqual(
                merged["completed_shards"],
                [
                    "docs-shard-001",
                    "docs-shard-002",
                ],
            )

            self.assertEqual(
                [file_doc["path"] for file_doc in merged["files"]],
                [
                    "src/example.py",
                    "src/other.py",
                ],
            )

            example_doc = merged["files"][0]

            self.assertIn(
                "İlk açıklama",
                example_doc["purpose"],
            )
            self.assertIn(
                "İkinci açıklama",
                example_doc["purpose"],
            )
            self.assertEqual(
                len(example_doc["main_components"]),
                2,
            )

            self.assertEqual(
                merged["stats"]["processed_units"],
                2,
            )
            self.assertEqual(
                merged["stats"]["documented_files"],
                2,
            )
            self.assertEqual(
                merged["stats"]["failed_units"],
                0,
            )

    def test_merge_preserves_failed_units(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = os.path.join(temp_dir, "result.json")

            self.write_result(
                output_path=result_path,
                shard_id="docs-shard-001",
                files=[],
                failed_units=[
                    {
                        "unit_id": "unit-001",
                        "reason": "Geçici model hatası",
                    }
                ],
            )

            merged = merge_docs_worker_results(
                result_paths=[result_path],
                expected_shard_ids=["docs-shard-001"],
            )

            self.assertEqual(
                merged["failed_units"],
                [
                    {
                        "unit_id": "unit-001",
                        "reason": "Geçici model hatası",
                        "shard_id": "docs-shard-001",
                    }
                ],
            )
            self.assertEqual(
                merged["stats"]["failed_units"],
                1,
            )

    def test_merge_rejects_missing_shard_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = os.path.join(temp_dir, "result.json")

            self.write_result(
                output_path=result_path,
                shard_id="docs-shard-001",
                files=[],
            )

            with self.assertRaisesRegex(ValueError, "eksik"):
                merge_docs_worker_results(
                    result_paths=[result_path],
                    expected_shard_ids=[
                        "docs-shard-001",
                        "docs-shard-002",
                    ],
                )

    def test_merge_rejects_duplicate_shard_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = os.path.join(temp_dir, "first.json")
            duplicate_path = os.path.join(
                temp_dir,
                "duplicate.json",
            )

            self.write_result(
                output_path=first_path,
                shard_id="docs-shard-001",
                files=[],
            )
            self.write_result(
                output_path=duplicate_path,
                shard_id="docs-shard-001",
                files=[],
            )

            with self.assertRaisesRegex(
                ValueError,
                "birden fazla",
            ):
                merge_docs_worker_results(
                    result_paths=[
                        first_path,
                        duplicate_path,
                    ],
                    expected_shard_ids=["docs-shard-001"],
                )


if __name__ == "__main__":
    unittest.main()
