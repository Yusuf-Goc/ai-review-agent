import json
import unittest

from agent.github_reporter import format_github_markdown_report
from agent.llm_client import build_review_prompt, normalize_json_response
from agent.reviewer import apply_repository_relevance_evidence


class PrChangeReportingTests(unittest.TestCase):
    def test_prompt_requires_added_files_symbols_and_relevance(self):
        prompt = build_review_prompt(
            {
                "input_type": "diff",
                "files": [],
            }
        )

        self.assertIn("Diff yeni bir dosya ekliyorsa", prompt)
        self.assertIn("Yeni eklenen her önemli function", prompt)
        self.assertIn('"repository_relevance"', prompt)
        self.assertIn('"relevance_reason"', prompt)
        self.assertIn("otomatik olarak `unrelated` sayma", prompt)

    def test_added_symbol_relevance_defaults_to_unclear(self):
        result = normalize_json_response(
            json.dumps(
                {
                    "summary": "Temiz değişiklik.",
                    "changes": [
                        {
                            "file": "function_test/value_utils.py",
                            "symbol": "clamp",
                            "symbol_type": "function",
                            "change_type": "added",
                            "after": "Yeni clamp fonksiyonu eklendi.",
                        }
                    ],
                    "findings": [],
                }
            )
        )

        self.assertEqual(
            "unclear",
            result["changes"][0]["repository_relevance"],
        )
        self.assertEqual("", result["changes"][0]["relevance_reason"])

    def test_clean_added_file_and_function_are_rendered(self):
        report = format_github_markdown_report(
            {
                "review_status": "completed",
                "changes": [
                    {
                        "file": "function_test/value_utils.py",
                        "symbol": "dosya geneli",
                        "symbol_type": "file",
                        "change_type": "added",
                        "after": "Yeni yardımcı modül eklendi.",
                        "behavior_change": "Sınırlandırma yardımcıları sağlar.",
                        "repository_relevance": "related",
                        "relevance_reason": "Test yardımcılarıyla aynı dizindedir.",
                    },
                    {
                        "file": "function_test/value_utils.py",
                        "symbol": "clamp",
                        "symbol_type": "function",
                        "change_type": "added",
                        "after": "Yeni clamp fonksiyonu eklendi.",
                        "behavior_change": "Sayısal değeri verilen aralıkta tutar.",
                        "repository_relevance": "related",
                        "relevance_reason": "Modülün yardımcı fonksiyon amacını karşılar.",
                    },
                ],
                "findings": [],
            }
        )

        self.assertIn("### Değişiklikler", report)
        self.assertIn("`function_test/value_utils.py` — `dosya geneli`", report)
        self.assertIn("`function_test/value_utils.py` — `clamp`", report)
        self.assertIn("Repository ilişkisi:** `İlgili`", report)
        self.assertIn("### Bulgular", report)
        self.assertIn(
            "Kritik, yüksek veya orta seviyede bulgu tespit edilmedi",
            report,
        )

    def test_change_context_is_not_repeated_inside_findings(self):
        marker = "TEK_KERE_GORUNMELI"
        report = format_github_markdown_report(
            {
                "review_status": "completed",
                "changes": [
                    {
                        "file": "service.py",
                        "symbol": "calculate_total",
                        "symbol_type": "function",
                        "change_type": "modified",
                        "after": marker,
                    }
                ],
                "findings": [
                    {
                        "file": "service.py",
                        "line": 12,
                        "severity": "high",
                        "category": "logic_error",
                        "message": "Hesaplama yanlış sonuç üretiyor.",
                        "suggestion": "Formülü düzeltin.",
                    }
                ],
                "impact_analysis": [
                    {
                        "symbol": "calculate_total",
                        "changed_file": "service.py",
                        "external_reference_files": ["consumer.py"],
                    }
                ],
            }
        )

        self.assertEqual(1, report.count(marker))
        self.assertNotIn("- **Değişiklik:**", report)
        self.assertIn("Diğer kullanımlar:** `consumer.py`", report)
        self.assertIn("Problem:** Hesaplama yanlış sonuç üretiyor.", report)


    def test_path_and_function_role_are_not_relevance_evidence(self):
        changes = [
            {
                "file": "function_test/value_utils.py",
                "symbol": "dosya geneli",
                "symbol_type": "file",
                "change_type": "added",
                "repository_relevance": "related",
                "relevance_reason": (
                    "Yardimci araclar dizininde oldugu icin ilgilidir."
                ),
            },
            {
                "file": "function_test/value_utils.py",
                "symbol": "clamp",
                "symbol_type": "function",
                "change_type": "added",
                "repository_relevance": "related",
                "relevance_reason": (
                    "Dosyanin ana fonksiyonu oldugu icin ilgilidir."
                ),
            },
        ]

        result = apply_repository_relevance_evidence(
            changes,
            [],
            "completed",
        )

        self.assertEqual("unclear", result[0]["repository_relevance"])
        self.assertEqual("unclear", result[1]["repository_relevance"])
        self.assertIn(
            "tek basina iliski kaniti sayilmadi",
            result[0]["relevance_reason"],
        )
        self.assertIn(
            "tek basina iliski kaniti sayilmadi",
            result[1]["relevance_reason"],
        )

    def test_external_repository_usage_marks_added_items_related(self):
        changes = [
            {
                "file": "function_test/value_utils.py",
                "symbol": "dosya geneli",
                "symbol_type": "file",
                "change_type": "added",
            },
            {
                "file": "function_test/value_utils.py",
                "symbol": "clamp",
                "symbol_type": "function",
                "change_type": "added",
            },
        ]

        impact_analysis = [
            {
                "symbol": "clamp",
                "symbol_type": "function",
                "changed_file": "function_test/value_utils.py",
                "reference_files_base": [],
                "reference_files_head": [
                    "service/pricing.py",
                ],
                "evidence": [
                    "service/pricing.py:12",
                ],
            }
        ]

        result = apply_repository_relevance_evidence(
            changes,
            impact_analysis,
            "completed",
        )

        self.assertEqual("related", result[0]["repository_relevance"])
        self.assertEqual("related", result[1]["repository_relevance"])
        self.assertIn(
            "service/pricing.py",
            result[0]["relevance_reason"],
        )
        self.assertIn(
            "service/pricing.py",
            result[1]["relevance_reason"],
        )


    def test_same_pr_added_usage_stays_unclear(self):
        changes = [
            {
                "file": "function_test/use_value_utils.py",
                "symbol": "dosya geneli",
                "symbol_type": "file",
                "change_type": "added",
            },
            {
                "file": "function_test/use_value_utils.py",
                "symbol": "normalize_score",
                "symbol_type": "function",
                "change_type": "added",
            },
            {
                "file": "function_test/value_utils.py",
                "symbol": "dosya geneli",
                "symbol_type": "file",
                "change_type": "added",
            },
            {
                "file": "function_test/value_utils.py",
                "symbol": "clamp",
                "symbol_type": "function",
                "change_type": "added",
            },
        ]

        impact_analysis = [
            {
                "symbol": "clamp",
                "symbol_type": "function",
                "changed_file": "function_test/value_utils.py",
                "reference_files_base": [],
                "reference_files_head": [
                    "function_test/use_value_utils.py",
                ],
            }
        ]

        result = apply_repository_relevance_evidence(
            changes,
            impact_analysis,
            "completed",
        )

        by_symbol = {
            (item["file"], item["symbol"]): item
            for item in result
        }

        file_change = by_symbol[
            (
                "function_test/value_utils.py",
                "dosya geneli",
            )
        ]
        function_change = by_symbol[
            (
                "function_test/value_utils.py",
                "clamp",
            )
        ]

        self.assertEqual(
            "unclear",
            file_change["repository_relevance"],
        )
        self.assertEqual(
            "unclear",
            function_change["repository_relevance"],
        )

        self.assertIn(
            "ayni PR'da eklenen",
            file_change["relevance_reason"],
        )
        self.assertIn(
            "function_test/use_value_utils.py",
            file_change["relevance_reason"],
        )
        self.assertIn(
            "Mevcut repository dosyalarina baglanti kanitlanmadi",
            function_change["relevance_reason"],
        )


if __name__ == "__main__":
    unittest.main()
