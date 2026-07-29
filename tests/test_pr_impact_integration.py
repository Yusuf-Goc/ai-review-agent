import unittest
from unittest.mock import patch

from agent.github_reporter import format_github_markdown_report
from agent.review_batcher import ReviewBatch
from agent.reviewer import (
    analyze_diff_in_batches,
    apply_breaking_change_severity_policy,
)


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

    def test_breaking_change_severity_requires_external_reference(self):
        changed_symbols = [
            {
                "file": "checkout.go",
                "symbol": "NewCheckoutSession",
                "source_lines": [83],
                "target_lines": [84],
            },
            {
                "file": "pricing.go",
                "symbol": "CalculateTotal",
                "source_lines": [68],
                "target_lines": [69],
            },
        ]
        impacts = [
            {
                "symbol": "NewCheckoutSession",
                "symbol_type": "function",
                "changed_file": "checkout.go",
                "reference_files_base": ["checkout.go"],
                "reference_files_head": ["checkout.go"],
                "external_reference_files": [],
            },
            {
                "symbol": "CalculateTotal",
                "symbol_type": "function",
                "changed_file": "pricing.go",
                "reference_files_base": ["checkout.go"],
                "reference_files_head": ["checkout.go"],
                "external_reference_files": ["checkout.go"],
            },
        ]
        findings = [
            {
                "file": "checkout.go",
                "line": 84,
                "severity": "critical",
                "category": "breaking_change",
                "message": "NewCheckoutSession imzasi degisti.",
            },
            {
                "file": "pricing.go",
                "line": 69,
                "severity": "critical",
                "category": "breaking_change",
                "message": "CalculateTotal checkout.go cagrisini kiriyor.",
            },
        ]

        normalized = apply_breaking_change_severity_policy(
            findings,
            impacts,
            changed_symbols,
        )

        self.assertEqual("high", normalized[0]["severity"])
        self.assertEqual("critical", normalized[1]["severity"])

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

    def test_github_finding_includes_change_and_usage_context(self):
        report = format_github_markdown_report(
            {
                "review_status": "completed",
                "summary": "Etki incelendi.",
                "changes": [
                    {
                        "file": "service.py",
                        "symbol": "calculate_total",
                        "symbol_type": "function",
                        "change_type": "modified",
                        "before": "Tek parametre aliyordu.",
                        "after": "Yeni discount parametresi aliyor.",
                        "behavior_change": "Eski cagrilar uyumsuz hale gelir.",
                    }
                ],
                "findings": [
                    {
                        "file": "service.py",
                        "line": 2,
                        "severity": "critical",
                        "category": "breaking_change",
                        "message": (
                            "calculate_total imzasi consumer.py "
                            "cagrisini kiriyor."
                        ),
                        "suggestion": "Eski imzayi koruyun.",
                    }
                ],
                "changed_symbols": [
                    {
                        "file": "service.py",
                        "symbol": "calculate_total",
                    }
                ],
                "impact_analysis": [
                    {
                        "symbol": "calculate_total",
                        "changed_file": "service.py",
                        "impact": "consumer.py yeni davranistan etkilenir.",
                        "definition_files": ["service.py"],
                        "reference_files_base": ["consumer.py"],
                        "reference_files_head": ["consumer.py"],
                        "evidence": ["service.py:2", "consumer.py:9"],
                    }
                ],
                "context_source_type": "markdown",
                "context_sources": ["README.md"],
                "analysis_sources": ["consumer.py", "service.py"],
            }
        )

        self.assertIn("### Özet", report)
        self.assertIn("### Bulgular", report)
        self.assertIn("`calculate_total` — `service.py:2`", report)
        self.assertIn("Önce: Tek parametre aliyordu.", report)
        self.assertIn("Sonra: Yeni discount parametresi aliyor.", report)
        self.assertIn("Diğer kullanımlar:** `consumer.py`", report)
        self.assertNotIn("Çapraz Dosya Etkisi", report)
        self.assertNotIn("Repository analiz kaynakları", report)


if __name__ == "__main__":
    unittest.main()
