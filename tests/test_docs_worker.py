import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.docs_worker import run_docs_worker
from agent.full_scan_planner import FullScanUnit


class DocsWorkerTests(unittest.TestCase):
    @staticmethod
    def write_payload(payload_path: str) -> None:
        payload = {
            "schema_version": "1.0",
            "shard_id": "docs-shard-001",
            "unit_count": 1,
            "total_lines": 2,
            "total_chars": 12,
            "total_risk_score": 3,
            "units": [
                {
                    "unit_id": "unit-001",
                    "kind": "single_file",
                    "total_lines": 2,
                    "total_chars": 12,
                    "risk_score": 3,
                    "slices": [
                        {
                            "path": "src/example.py",
                            "language": "python",
                            "start_line": 1,
                            "end_line": 2,
                            "content": "a = 1\nb = 2\n",
                            "line_count": 2,
                            "char_count": 12,
                            "part_label": "full-file",
                        }
                    ],
                }
            ],
        }

        with open(payload_path, "w", encoding="utf-8") as payload_file:
            json.dump(payload, payload_file)

    def test_worker_processes_payload_and_writes_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = os.path.join(
                temp_dir,
                "docs-shard-001.json",
            )
            output_path = os.path.join(
                temp_dir,
                "results",
                "docs-shard-001.json",
            )

            self.write_payload(payload_path)

            processor_result = (
                {
                    "src/example.py": {
                        "path": "src/example.py",
                        "language": "python",
                        "purpose": "Örnek Python dosyası",
                    }
                },
                [],
            )

            with patch(
                "agent.docs_worker.process_docs_scan_units",
                return_value=processor_result,
            ) as processor:
                result = run_docs_worker(
                    payload_path=payload_path,
                    output_path=output_path,
                    model="test-model",
                    retries=0,
                    retry_delay=0,
                )

            self.assertTrue(os.path.isfile(output_path))

            scan_units = processor.call_args.kwargs["scan_units"]

            self.assertEqual(len(scan_units), 1)
            self.assertIsInstance(scan_units[0], FullScanUnit)
            self.assertEqual(scan_units[0].unit_id, "unit-001")
            self.assertEqual(
                scan_units[0].slices[0].content,
                "a = 1\nb = 2\n",
            )

            with open(
                output_path,
                "r",
                encoding="utf-8",
            ) as result_file:
                saved_result = json.load(result_file)

            self.assertEqual(result, saved_result)
            self.assertEqual(
                saved_result["shard_id"],
                "docs-shard-001",
            )
            self.assertEqual(saved_result["unit_count"], 1)
            self.assertEqual(saved_result["failed_units"], [])
            self.assertEqual(
                saved_result["files"][0]["path"],
                "src/example.py",
            )

    def test_worker_rejects_payload_without_shard_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = os.path.join(
                temp_dir,
                "invalid.json",
            )
            output_path = os.path.join(
                temp_dir,
                "result.json",
            )

            with open(
                payload_path,
                "w",
                encoding="utf-8",
            ) as payload_file:
                json.dump(
                    {
                        "schema_version": "1.0",
                        "units": [],
                    },
                    payload_file,
                )

            with self.assertRaisesRegex(ValueError, "shard_id"):
                run_docs_worker(
                    payload_path=payload_path,
                    output_path=output_path,
                    model="test-model",
                    retries=0,
                    retry_delay=0,
                )

            self.assertFalse(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
