import unittest
from unittest.mock import patch

from agent.github_reporter import format_github_markdown_report
from agent.review_batcher import ReviewBatch
from agent.reviewer import analyze_diff_in_batches


class PrImpactIntegrationTests(unittest.TestCase):
    def _payload(self):
        file_payload = {
            "path": "service.py",
            "change_type": "modified",
            "is_binary": False,
            "hunks": [
                {
                    "section_header": "def calculate_total(items):",
                    "source_start": 1,
                    "target_start": 1,
                    "lines": [
                        {
                            "kind": "removed",
                            "source_line": 2,
                            "target_line": None,
                            "content": "    return sum(items)",
                        },
                        {
                            "kind": "added",
                            "source_line": None,
                            "target_line": 2,
                            "content": "    return sum(items) * 0.9",
                        },
                    ],
                }
            ],
        }
        return {
            "schema_version": "1.0",
            "input_type": "diff",
            "files": [file_payload],
            "limits": {},
        }, file_payload

    def test_tool_impact_context_reaches_review_batch(self):
        payload, file_payload = self._payload()
        impact = {
            "symbol": "calculate_total",
            "symbol_type": "function",
            "changed_file": "service.py",
            "change_type": "modified",
            "definition_files": ["service.py"],
            "reference_files_base": ["consumer.py"],
            "reference_files_head": ["consumer.py"],
            "impact": "consumer.py yeni toplam davranisindan etkilenir.",
            "evidence": ["consumer.py:9"],
        }

        with (
            patch("agent.reviewer.parse_diff", return_value=payload),
            patch(
                "agent.reviewer.make_review_batches",
                return_value=[ReviewBatch(files=[file_payload], estimated_lines=2)],
            ),
            patch(
                "agent.reviewer.analyze_repository_impact",
                return_value={
                    "status": "completed",
                    "summary": "Etki incelendi.",
                    "impact_analysis": [impact],
                    "errors": [],
                    "analysis_sources": ["consumer.py", "service.py"],
                    "tool_trace": [{"name": "compare_symbol"}],
                },
            ) as impact_mock,
            patch(
                "agent.reviewer.analyze_payload",
                return_value={
                    "review_status": "completed",
                    "summary": "Batch tamamlandi.",
                    "changes": [],
                    "findings": [],
                },
            ) as analyze_mock,
        ):
            result = analyze_diff_in_batches(
                "diff",
                client=object(),
                pr_context={
                    "source_type": "markdown",
                    "file_context": {},
                    "project_documents": [],
                    "context_sources": ["README.md"],
                    "changed_paths": ["service.py"],
                },
                repo_root=".",
                base_sha="base",
                head_sha="head",
            )

        impact_mock.assert_called_once()
        batch_payload = analyze_mock.call_args.args[0]
        self.assertEqual("calculate_total", batch_payload["changed_symbols"][0]["symbol"])
        self.assertEqual([impact], batch_payload["repository_impact_context"])
        self.assertEqual([impact], result["impact_analysis"])
        self.assertEqual(["consumer.py", "service.py"], result["analysis_sources"])
        self.assertEqual("completed", result["review_status"])

    def test_impact_failure_marks_otherwise_completed_review_partial(self):
        payload, file_payload = self._payload()

        with (
            patch("agent.reviewer.parse_diff", return_value=payload),
            patch(
                "agent.reviewer.make_review_batches",
                return_value=[ReviewBatch(files=[file_payload], estimated_lines=2)],
            ),
            patch(
                "agent.reviewer.analyze_repository_impact",
                return_value={
                    "status": "failed",
                    "summary": "Tool analizi tamamlanamadi.",
                    "impact_analysis": [],
                    "errors": ["Tool analizi tamamlanamadi."],
                    "analysis_sources": [],
                    "tool_trace": [],
                },
            ),
            patch(
                "agent.reviewer.analyze_payload",
                return_value={
                    "review_status": "completed",
                    "summary": "Batch tamamlandi.",
                    "changes": [],
                    "findings": [],
                },
            ),
        ):
            result = analyze_diff_in_batches(
                "diff",
                client=object(),
                pr_context={
                    "source_type": "none",
                    "file_context": {},
                    "project_documents": [],
                    "context_sources": [],
                    "changed_paths": ["service.py"],
                },
                repo_root=".",
                base_sha="base",
                head_sha="head",
            )

        self.assertEqual("partial", result["review_status"])
        self.assertIn("Tool analizi tamamlanamadi.", result["errors"])

    def test_github_report_renders_cross_file_impact(self):
        report = format_github_markdown_report(
            {
                "review_status": "completed",
                "summary": "Etki incelendi.",
                "changes": [],
                "findings": [],
                "impact_analysis": [
                    {
                        "symbol": "calculate_total",
                        "changed_file": "service.py",
                        "impact": "consumer.py yeni davranistan etkilenir.",
                        "definition_files": ["service.py"],
                        "reference_files_base": ["consumer.py"],
                        "reference_files_head": ["consumer.py"],
                        "evidence": ["consumer.py:9"],
                    }
                ],
                "context_source_type": "markdown",
                "context_sources": ["README.md"],
                "analysis_sources": ["consumer.py", "service.py"],
            }
        )

        self.assertIn("Çapraz Dosya Etkisi", report)
        self.assertIn("calculate_total", report)
        self.assertIn("consumer.py yeni davranistan etkilenir", report)
        self.assertIn("Repository analiz kaynakları", report)


if __name__ == "__main__":
    unittest.main()
