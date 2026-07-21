import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.github_reporter import format_github_markdown_report
from agent.review_batcher import ReviewBatch
from agent.reviewer import analyze_diff_in_batches, analyze_payload


class PrReviewReliabilityTests(unittest.TestCase):
    def test_invalid_model_json_marks_review_failed(self):
        payload = {
            "files": [
                {
                    "path": "app.py",
                    "is_binary": False,
                    "hunks": [{"lines": []}],
                }
            ]
        }
        response = SimpleNamespace(
            text="gecerli json degil",
            candidates=[object()],
        )

        with patch(
            "agent.reviewer.call_model_with_retries",
            return_value=response,
        ):
            result = analyze_payload(payload, client=object())

        self.assertEqual("failed", result["review_status"])
        self.assertEqual([], result["findings"])
        self.assertTrue(result["errors"])

    def test_failed_report_never_claims_no_critical_error(self):
        report = format_github_markdown_report(
            {
                "review_status": "failed",
                "summary": "Model cagrisi basarisiz oldu.",
                "findings": [],
            }
        )

        self.assertIn("İnceleme tamamlanamadı", report)
        self.assertIn("Güvenilir bir ‘hata bulunamadı’ sonucu üretilemedi", report)
        self.assertNotIn("\nKritik hata bulunamadı.", report)

    def test_batched_review_parses_full_diff_and_marks_partial_result(self):
        files = [
            {
                "path": "first.py",
                "is_binary": False,
                "hunks": [{"lines": [{"kind": "added"}]}],
            },
            {
                "path": "second.py",
                "is_binary": False,
                "hunks": [{"lines": [{"kind": "added"}]}],
            },
        ]
        payload = {
            "schema_version": "1.0",
            "input_type": "diff",
            "files": files,
            "limits": {},
        }
        batches = [
            ReviewBatch(files=[files[0]], estimated_lines=1),
            ReviewBatch(files=[files[1]], estimated_lines=1),
        ]

        with (
            patch("agent.reviewer.parse_diff", return_value=payload) as parse_mock,
            patch("agent.reviewer.make_review_batches", return_value=batches) as batch_mock,
            patch(
                "agent.reviewer.analyze_payload",
                side_effect=[
                    {
                        "review_status": "completed",
                        "summary": "Tamamlandi.",
                        "findings": [],
                    },
                    {
                        "review_status": "failed",
                        "summary": "Model yaniti alinamadi.",
                        "findings": [],
                    },
                ],
            ),
        ):
            result = analyze_diff_in_batches(
                "diff content",
                max_review_lines=500,
            )

        parse_mock.assert_called_once_with(
            "diff content",
            max_review_lines=None,
        )
        batch_mock.assert_called_once_with(
            files,
            max_lines_per_batch=500,
        )
        self.assertEqual("partial", result["review_status"])
        self.assertEqual(1, len(result["failed_batches"]))


if __name__ == "__main__":
    unittest.main()
