import unittest
from unittest.mock import patch

from agent.codebase_documenter import process_docs_scan_units
from agent.full_scan_planner import FullScanUnit


class DocsProcessorTests(unittest.TestCase):
    @staticmethod
    def make_unit(unit_id: str) -> FullScanUnit:
        return FullScanUnit(
            unit_id=unit_id,
            kind="single_file",
            total_lines=10,
            total_chars=100,
            risk_score=0,
        )

    def test_processor_merges_results_from_multiple_units(self):
        units = [
            self.make_unit("unit-001"),
            self.make_unit("unit-002"),
        ]

        parsed_responses = [
            {
                "files": [
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
                ]
            },
            {
                "files": [
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
                    }
                ]
            },
        ]

        with (
            patch(
                "agent.codebase_documenter._build_docs_prompt",
                side_effect=["prompt-1", "prompt-2"],
            ),
            patch(
                "agent.codebase_documenter._call_model_json",
                side_effect=[object(), object()],
            ),
            patch(
                "agent.codebase_documenter._extract_response_text",
                side_effect=["response-1", "response-2"],
            ),
            patch(
                "agent.codebase_documenter._safe_parse_docs_response",
                side_effect=parsed_responses,
            ),
        ):
            merged_files, failed_units = process_docs_scan_units(
                scan_units=units,
                model="test-model",
                retries=0,
                retry_delay=0,
            )

        self.assertEqual(failed_units, [])
        self.assertIn("src/example.py", merged_files)

        merged = merged_files["src/example.py"]

        self.assertIn("İlk açıklama", merged["purpose"])
        self.assertIn("İkinci açıklama", merged["purpose"])
        self.assertEqual(len(merged["main_components"]), 2)

    def test_processor_records_empty_model_response_as_failure(self):
        unit = self.make_unit("unit-empty")

        with (
            patch(
                "agent.codebase_documenter._build_docs_prompt",
                return_value="prompt",
            ),
            patch(
                "agent.codebase_documenter._call_model_json",
                return_value=object(),
            ),
            patch(
                "agent.codebase_documenter._extract_response_text",
                return_value=None,
            ),
        ):
            merged_files, failed_units = process_docs_scan_units(
                scan_units=[unit],
                model="test-model",
                retries=0,
                retry_delay=0,
            )

        self.assertEqual(merged_files, {})
        self.assertEqual(
            failed_units,
            [
                {
                    "unit_id": "unit-empty",
                    "reason": "Model boş yanıt döndü.",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
