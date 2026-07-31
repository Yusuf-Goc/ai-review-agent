import json
import unittest

from agent.github_reporter import format_github_markdown_report
from agent.llm_client import build_review_prompt, normalize_json_response
from agent.reviewer import (
    apply_repository_relevance_evidence,
    ensure_deterministic_sql_changes,
)


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

    def test_same_pr_only_sql_column_usage_stays_unclear(self):
        changes = [
            {
                "file": "sql_agent_test/schema/customers.sql",
                "symbol": "sales.customers.country_code",
                "symbol_type": "column",
                "change_type": "added",
                "repository_relevance": "related",
            },
            {
                "file": (
                    "sql_agent_test/queries/"
                    "new_customer_country_report.sql"
                ),
                "symbol": "dosya geneli",
                "symbol_type": "file",
                "change_type": "added",
            },
        ]
        impact_analysis = [
            {
                "symbol": "sales.customers.country_code",
                "symbol_type": "column",
                "changed_file": (
                    "sql_agent_test/schema/customers.sql"
                ),
                "reference_files_base": [],
                "reference_files_head": [
                    (
                        "sql_agent_test/queries/"
                        "new_customer_country_report.sql"
                    )
                ],
            }
        ]

        result = apply_repository_relevance_evidence(
            changes,
            impact_analysis,
            "completed",
        )

        column_change = result[0]
        self.assertEqual(
            "unclear",
            column_change["repository_relevance"],
        )
        self.assertIn(
            "Yalnizca ayni PR'da eklenen dosyalarda",
            column_change["relevance_reason"],
        )
        self.assertIn(
            "new_customer_country_report.sql",
            column_change["relevance_reason"],
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


    def test_deterministic_sql_changes_fill_model_omissions(self):
        changes = [
            {
                "file": (
                    "sql_agent_test/queries/"
                    "new_customer_country_report.sql"
                ),
                "symbol": "dosya geneli",
                "symbol_type": "file",
                "change_type": "added",
                "after": "Model tarafindan aciklanan yeni dosya.",
            },
            {
                "file": "sql_agent_test/schema/customers.sql",
                "symbol": "sales.customers",
                "symbol_type": "table",
                "change_type": "modified",
                "behavior_change": "Model tablo aciklamasi korunmali.",
            },
        ]
        changed_symbols = [
            {
                "file": "sql_agent_test/schema/customers.sql",
                "symbol": "sales.customers",
                "symbol_type": "table",
                "change_type": "modified",
            },
            {
                "file": "sql_agent_test/schema/customers.sql",
                "symbol": "sales.customers.country",
                "symbol_type": "column",
                "change_type": "deleted",
            },
            {
                "file": "sql_agent_test/schema/customers.sql",
                "symbol": "sales.customers.country_code",
                "symbol_type": "column",
                "change_type": "added",
            },
        ]
        files = [
            {
                "path": (
                    "sql_agent_test/queries/"
                    "new_customer_country_report.sql"
                ),
                "change_type": "added",
                "hunks": [
                    {
                        "lines": [
                            {
                                "kind": "added",
                                "content": (
                                    "SELECT c.country_code "
                                    "FROM `sales.customers` AS c;"
                                ),
                            }
                        ]
                    }
                ],
            },
            {
                "path": "sql_agent_test/schema/customers.sql",
                "change_type": "modified",
                "hunks": [
                    {
                        "lines": [
                            {
                                "kind": "removed",
                                "content": "country STRING NOT NULL,",
                            },
                            {
                                "kind": "added",
                                "content": "country_code STRING NOT NULL,",
                            },
                        ]
                    }
                ],
            },
        ]

        result = ensure_deterministic_sql_changes(
            changes,
            changed_symbols,
            files,
        )
        by_key = {
            (
                item["file"],
                item["symbol"],
                item["change_type"],
            ): item
            for item in result
        }

        self.assertEqual(5, len(result))
        self.assertIn(
            (
                "sql_agent_test/queries/"
                "new_customer_country_report.sql",
                "new_customer_country_report",
                "added",
            ),
            by_key,
        )
        self.assertIn(
            (
                "sql_agent_test/schema/customers.sql",
                "sales.customers.country",
                "deleted",
            ),
            by_key,
        )
        self.assertIn(
            (
                "sql_agent_test/schema/customers.sql",
                "sales.customers.country_code",
                "added",
            ),
            by_key,
        )
        self.assertEqual(
            "Model tablo aciklamasi korunmali.",
            by_key[
                (
                    "sql_agent_test/schema/customers.sql",
                    "sales.customers",
                    "modified",
                )
            ]["behavior_change"],
        )

    def test_same_pr_only_deterministic_sql_column_stays_unclear(self):
        query_path = (
            "sql_agent_test/queries/"
            "new_customer_country_report.sql"
        )
        schema_path = "sql_agent_test/schema/customers.sql"
        changes = ensure_deterministic_sql_changes(
            [],
            [
                {
                    "file": schema_path,
                    "symbol": "sales.customers.country_code",
                    "symbol_type": "column",
                    "change_type": "added",
                }
            ],
            [
                {
                    "path": query_path,
                    "change_type": "added",
                    "hunks": [
                        {
                            "lines": [
                                {
                                    "kind": "added",
                                    "content": (
                                        "SELECT c.country_code "
                                        "FROM `sales.customers` AS c;"
                                    ),
                                }
                            ]
                        }
                    ],
                },
                {
                    "path": schema_path,
                    "change_type": "modified",
                    "hunks": [],
                },
            ],
        )

        result = apply_repository_relevance_evidence(
            changes,
            [
                {
                    "symbol": "sales.customers.country_code",
                    "symbol_type": "column",
                    "changed_file": schema_path,
                    "reference_files_base": [],
                    "reference_files_head": [query_path],
                }
            ],
            "completed",
        )
        by_symbol = {
            item["symbol"]: item
            for item in result
        }

        column = by_symbol["sales.customers.country_code"]
        self.assertEqual(
            "unclear",
            column["repository_relevance"],
        )
        self.assertIn(
            "Yalnizca ayni PR'da eklenen dosyalarda",
            column["relevance_reason"],
        )
        self.assertIn(query_path, column["relevance_reason"])

    def test_deterministic_sql_completion_leaves_python_and_go_unchanged(self):
        changes = [
            {
                "file": "service.py",
                "symbol": "calculate_total",
                "symbol_type": "function",
                "change_type": "modified",
                "behavior_change": "Model aciklamasi.",
            }
        ]

        result = ensure_deterministic_sql_changes(
            changes,
            [
                {
                    "file": "service.py",
                    "symbol": "calculate_total",
                    "symbol_type": "function",
                    "change_type": "modified",
                },
                {
                    "file": "service.go",
                    "symbol": "CalculateTotal",
                    "symbol_type": "function",
                    "change_type": "modified",
                },
            ],
            [
                {
                    "path": "service.py",
                    "change_type": "modified",
                    "hunks": [],
                },
                {
                    "path": "service.go",
                    "change_type": "modified",
                    "hunks": [],
                },
            ],
        )

        self.assertEqual(changes, result)


if __name__ == "__main__":
    unittest.main()
