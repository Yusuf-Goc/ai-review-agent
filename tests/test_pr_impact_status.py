import unittest
from unittest.mock import patch

from agent.review_batcher import ReviewBatch
from agent.reviewer import _load_bigquery_owner_hints, analyze_diff_in_batches


class PrImpactStatusTests(unittest.TestCase):
    @patch("agent.reviewer.get_bigquery_file_definitions")
    def test_loads_bigquery_owner_hints_for_sql_files_only(self, get_definitions):
        get_definitions.side_effect = [
            {"definitions": [{"qualified_name": "sales.customer_view"}]},
            {"definitions": [{"qualified_name": "sales.customer_view"}]},
        ]

        result = _load_bigquery_owner_hints(
            repo_root=".",
            base_sha="base",
            head_sha="head",
            files=[
                {"path": "views/customer_view.sql"},
                {"path": "service.py"},
            ],
        )

        self.assertEqual(
            {"views/customer_view.sql"},
            set(result),
        )
        self.assertEqual(2, get_definitions.call_count)
        self.assertEqual(
            "base",
            get_definitions.call_args_list[0].args[1],
        )
        self.assertEqual(
            "head",
            get_definitions.call_args_list[1].args[1],
        )

    def test_failed_impact_analysis_preserves_completed_pr_review(self):
        file_payload = {
            "path": "query.sql",
            "source_file": "query.sql",
            "target_file": "query.sql",
            "change_type": "modified",
            "added_lines": 1,
            "deleted_lines": 0,
            "is_binary": False,
            "hunks": [
                {
                    "source_start": 1,
                    "source_length": 1,
                    "target_start": 1,
                    "target_length": 1,
                    "section_header": "",
                    "lines": [
                        {
                            "kind": "added",
                            "source_line": None,
                            "target_line": 1,
                            "content": "SELECT country_code FROM sales.customers;",
                            "review_target": True,
                        }
                    ],
                }
            ],
        }

        parsed_payload = {
            "schema_version": "1.0",
            "input_type": "diff",
            "files": [file_payload],
            "limits": {},
        }

        changed_symbols = [
            {
                "file": "query.sql",
                "symbol": "sales.customers",
                "symbol_type": "table",
                "change_type": "modified",
            }
        ]

        failed_impact_result = {
            "status": "failed",
            "summary": "Repository etki analizi tamamlanamadi.",
            "impact_analysis": [],
            "errors": ["Etki analizi modeli gecersiz yanit dondu."],
            "tool_trace": [],
            "analysis_sources": [],
        }

        completed_batch_result = {
            "review_status": "completed",
            "summary": "Inceleme tamamlandi.",
            "changes": [],
            "findings": [],
            "errors": [],
        }

        with (
            patch(
                "agent.reviewer.parse_diff",
                return_value=parsed_payload,
            ),
            patch(
                "agent.reviewer.extract_changed_symbols",
                return_value=changed_symbols,
            ),
            patch(
                "agent.reviewer.analyze_repository_impact",
                return_value=failed_impact_result,
            ),
            patch(
                "agent.reviewer.make_review_batches",
                return_value=[
                    ReviewBatch(
                        files=[file_payload],
                        estimated_lines=1,
                    )
                ],
            ),
            patch(
                "agent.reviewer.analyze_payload",
                return_value=completed_batch_result,
            ),
        ):
            result = analyze_diff_in_batches(
                "diff content",
                client=object(),
                repo_root=".",
                base_sha="base-sha",
                head_sha="head-sha",
                pr_context={
                    "source_type": "none",
                    "file_context": {},
                    "project_documents": [],
                    "context_sources": [],
                },
            )

        self.assertEqual(
            "completed",
            result["review_status"],
        )
        self.assertEqual(
            "failed",
            result["impact_analysis_status"],
        )
        self.assertIn(
            "ana PR incelemesi sonucu korundu",
            result["summary"],
        )


if __name__ == "__main__":
    unittest.main()
