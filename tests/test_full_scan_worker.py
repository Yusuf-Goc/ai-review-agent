import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.full_scan_planner import FullScanUnit
from agent.full_scan_worker import run_full_scan_worker


class FullScanWorkerTests(unittest.TestCase):
    @staticmethod
    def write_payload(payload_path: str) -> None:
        payload = {
            "schema_version": "1.0",
            "shard_id": "docs-shard-001",
            "unit_count": 1,
            "total_lines": 2,
            "total_chars": 20,
            "total_risk_score": 3,
            "units": [
                {
                    "unit_id": "unit-001",
                    "kind": "single_file",
                    "total_lines": 2,
                    "total_chars": 20,
                    "risk_score": 3,
                    "slices": [
                        {
                            "path": "src/example.py",
                            "language": "python",
                            "start_line": 1,
                            "end_line": 2,
                            "content": (
                                "value = 10\n"
                                "result = value / 0\n"
                            ),
                            "line_count": 2,
                            "char_count": 30,
                            "part_label": "full-file",
                        }
                    ],
                }
            ],
        }

        with open(
            payload_path,
            "w",
            encoding="utf-8",
        ) as payload_file:
            json.dump(payload, payload_file)

    def test_worker_processes_review_payload_and_writes_result(self):
        finding = {
            "file": "src/example.py",
            "line": 2,
            "severity": "high",
            "category": "logic_error",
            "message": "Sıfıra bölme hatası.",
            "suggestion": "Böleni işlemden önce doğrulayın.",
        }

        processor_result = {
            "findings": [finding],
            "failed_units": [],
            "stats": {
                "planned_units": 1,
                "first_pass_success": 1,
                "first_pass_failed": 0,
                "second_pass_success": 0,
                "second_pass_failed": 0,
                "fallback_units": 0,
                "fallback_pass_success": 0,
                "final_failed_units": 0,
                "total_successful_units": 1,
            },
        }

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

            with patch(
                "agent.full_scan_worker.process_full_scan_units",
                return_value=processor_result,
            ) as processor:
                result = run_full_scan_worker(
                    payload_path=payload_path,
                    output_path=output_path,
                    model="test-model",
                    max_review_lines=500,
                    retries=0,
                    retry_delay=0,
                )

            self.assertTrue(os.path.isfile(output_path))

            scan_units = processor.call_args.kwargs[
                "scan_units"
            ]

            self.assertEqual(len(scan_units), 1)
            self.assertIsInstance(
                scan_units[0],
                FullScanUnit,
            )
            self.assertEqual(
                scan_units[0].unit_id,
                "unit-001",
            )
            self.assertEqual(
                scan_units[0].slices[0].path,
                "src/example.py",
            )

            processor.assert_called_once_with(
                scan_units=scan_units,
                client=None,
                model="test-model",
                max_review_lines=500,
                retries=0,
                retry_delay=0,
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
            self.assertEqual(
                saved_result["unit_count"],
                1,
            )
            self.assertEqual(
                saved_result["findings"],
                [finding],
            )
            self.assertEqual(
                saved_result["failed_units"],
                [],
            )
            self.assertEqual(
                saved_result["stats"],
                processor_result["stats"],
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

            with self.assertRaisesRegex(
                ValueError,
                "shard_id",
            ):
                run_full_scan_worker(
                    payload_path=payload_path,
                    output_path=output_path,
                    model="test-model",
                    max_review_lines=500,
                    retries=0,
                    retry_delay=0,
                )

            self.assertFalse(
                os.path.exists(output_path)
            )


if __name__ == "__main__":
    unittest.main()
