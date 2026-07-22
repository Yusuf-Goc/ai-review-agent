import json
import unittest
from unittest.mock import patch

from agent.github_reporter import format_github_markdown_report
from agent.llm_client import build_review_prompt, normalize_json_response
from agent.report_formatter import format_review_report
from agent.review_batcher import ReviewBatch
from agent.reviewer import analyze_diff_in_batches


class PrReviewOutputSchemaTests(unittest.TestCase):
    def _file(self, path):
        return {
            "path": path,
            "is_binary": False,
            "hunks": [{"lines": [{"kind": "added", "content": "change"}]}],
        }

    def test_prompt_requests_change_explanations(self):
        prompt = build_review_prompt(
            {
                "input_type": "diff",
                "files": [],
            }
        )

        self.assertIn('"changes"', prompt)
        self.assertIn('"behavior_change"', prompt)
        self.assertIn("repository genelinde", prompt)
        self.assertIn("uydurma", prompt)

    def test_normalizer_defaults_and_filters_extended_schema(self):
        result = normalize_json_response(
            json.dumps(
                {
                    "summary": "Tamamlandi.",
                    "changes": [
                        {"file": "service.py", "change_type": "modified"},
                        "gecersiz",
                    ],
                    "findings": [
                        {"file": "service.py", "line": 5},
                        42,
                    ],
                }
            )
        )

        self.assertEqual(1, len(result["changes"]))
        self.assertEqual(1, len(result["findings"]))

        missing = normalize_json_response('{"summary": "Tamamlandi."}')
        self.assertEqual([], missing["changes"])
        self.assertEqual([], missing["findings"])

    def test_batched_review_merges_and_deduplicates_changes(self):
        first_file = self._file("first.go")
        second_file = self._file("second.go")
        payload = {
            "schema_version": "1.0",
            "input_type": "diff",
            "files": [first_file, second_file],
            "limits": {},
        }
        duplicate_change = {
            "file": "shared.go",
            "symbol": "Calculate",
            "symbol_type": "function",
            "change_type": "modified",
            "before": "Eski hesaplama.",
            "after": "Yeni hesaplama.",
            "behavior_change": "Hesaplama davranisi degisti.",
        }

        with (
            patch("agent.reviewer.parse_diff", return_value=payload),
            patch(
                "agent.reviewer.make_review_batches",
                return_value=[
                    ReviewBatch(files=[first_file], estimated_lines=1),
                    ReviewBatch(files=[second_file], estimated_lines=1),
                ],
            ),
            patch(
                "agent.reviewer.analyze_payload",
                side_effect=[
                    {
                        "review_status": "completed",
                        "summary": "Birinci batch.",
                        "changes": [duplicate_change],
                        "findings": [],
                    },
                    {
                        "review_status": "completed",
                        "summary": "Ikinci batch.",
                        "changes": [
                            duplicate_change,
                            {
                                "file": "second.go",
                                "symbol": "Run",
                                "symbol_type": "function",
                                "change_type": "added",
                                "before": "",
                                "after": "Yeni fonksiyon eklendi.",
                                "behavior_change": "Yeni calisma akisi eklendi.",
                            },
                        ],
                        "findings": [],
                    },
                ],
            ),
        ):
            result = analyze_diff_in_batches("diff", client=object())

        self.assertEqual("completed", result["review_status"])
        self.assertEqual(2, len(result["changes"]))

    def test_github_report_renders_changes_and_context(self):
        report = format_github_markdown_report(
            {
                "review_status": "completed",
                "summary": "Davranis degisikligi incelendi.",
                "changes": [
                    {
                        "file": "service.py",
                        "symbol": "calculate_total",
                        "symbol_type": "function",
                        "change_type": "modified",
                        "before": "Indirim uygulanmiyordu.",
                        "after": "Indirim uygulanıyor.",
                        "behavior_change": "Toplam fiyat azalabilir.",
                    }
                ],
                "findings": [],
                "context_source_type": "markdown",
                "context_sources": ["README.md", "docs/architecture.md"],
            }
        )

        self.assertIn("PR'da Ne Değişti?", report)
        self.assertIn("calculate_total", report)
        self.assertIn("Toplam fiyat azalabilir", report)
        self.assertIn("Kullanılan Bağlam", report)
        self.assertIn("README.md", report)
        self.assertIn("Kritik hata bulunamadı", report)

    def test_console_failed_report_does_not_claim_clean_result(self):
        report = format_review_report(
            {
                "review_status": "failed",
                "summary": "Model yaniti alinamadi.",
                "changes": [],
                "findings": [],
            }
        )

        self.assertIn("guvenilir", report)
        self.assertNotIn("Bulgu: Kritik hata bulunamadi.", report)


if __name__ == "__main__":
    unittest.main()
