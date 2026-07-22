import unittest
from unittest.mock import patch

from agent.llm_client import build_review_prompt
from agent.review_batcher import ReviewBatch
from agent.reviewer import analyze_diff_in_batches


class PrContextIntegrationTests(unittest.TestCase):
    def _file(self, path):
        return {
            "path": path,
            "is_binary": False,
            "hunks": [
                {
                    "lines": [
                        {
                            "kind": "added",
                            "content": "changed line",
                        }
                    ]
                }
            ],
        }

    def test_markdown_context_reaches_batch_payload(self):
        file_payload = self._file("service.py")
        parsed_payload = {
            "schema_version": "1.0",
            "input_type": "diff",
            "files": [file_payload],
            "limits": {},
        }
        context = {
            "source_type": "markdown",
            "file_context": {},
            "project_documents": [
                {
                    "path": "README.md",
                    "content": "Siparis servisi proje aciklamasi.",
                }
            ],
            "context_sources": ["README.md"],
        }

        with (
            patch("agent.reviewer.parse_diff", return_value=parsed_payload),
            patch(
                "agent.reviewer.make_review_batches",
                return_value=[
                    ReviewBatch(files=[file_payload], estimated_lines=1)
                ],
            ),
            patch(
                "agent.reviewer.analyze_payload",
                return_value={
                    "review_status": "completed",
                    "summary": "Inceleme tamamlandi.",
                    "findings": [],
                    "errors": [],
                },
            ) as analyze_mock,
        ):
            result = analyze_diff_in_batches(
                "diff",
                client=object(),
                pr_context=context,
            )

        batch_payload = analyze_mock.call_args.args[0]
        self.assertEqual(
            "markdown",
            batch_payload["project_context"]["source_type"],
        )
        self.assertEqual(
            context["project_documents"],
            batch_payload["project_context"]["project_documents"],
        )
        self.assertNotIn("main_branch_file_context", batch_payload)
        self.assertEqual("markdown", result["context_source_type"])
        self.assertEqual(["README.md"], result["context_sources"])

    def test_summary_context_is_filtered_to_current_batch(self):
        first_file = self._file("first.go")
        second_file = self._file("second.go")
        parsed_payload = {
            "schema_version": "1.0",
            "input_type": "diff",
            "files": [first_file, second_file],
            "limits": {},
        }
        context = {
            "source_type": "codebase_summary",
            "file_context": {
                "first.go": {"purpose": "Birinci dosya"},
                "second.go": {"purpose": "Ikinci dosya"},
            },
            "project_documents": [],
            "context_sources": [".ai-review/codebase-summary.json"],
        }

        with (
            patch("agent.reviewer.parse_diff", return_value=parsed_payload),
            patch(
                "agent.reviewer.make_review_batches",
                return_value=[
                    ReviewBatch(files=[first_file], estimated_lines=1),
                    ReviewBatch(files=[second_file], estimated_lines=1),
                ],
            ),
            patch(
                "agent.reviewer.analyze_payload",
                return_value={
                    "review_status": "completed",
                    "summary": "Inceleme tamamlandi.",
                    "findings": [],
                    "errors": [],
                },
            ) as analyze_mock,
        ):
            analyze_diff_in_batches(
                "diff",
                client=object(),
                pr_context=context,
            )

        first_payload = analyze_mock.call_args_list[0].args[0]
        second_payload = analyze_mock.call_args_list[1].args[0]

        self.assertEqual(
            {"first.go": {"purpose": "Birinci dosya"}},
            first_payload["main_branch_file_context"],
        )
        self.assertEqual(
            {"second.go": {"purpose": "Ikinci dosya"}},
            second_payload["main_branch_file_context"],
        )

    def test_prompt_explains_markdown_context_priority(self):
        prompt = build_review_prompt(
            {
                "input_type": "diff",
                "files": [],
                "project_context": {
                    "source_type": "markdown",
                    "project_documents": [],
                    "context_sources": ["README.md"],
                },
            }
        )

        self.assertIn("`project_context`", prompt)
        self.assertIn("destekleyici bağlamdır", prompt)
        self.assertIn("diff ve kaynak kod teknik gerçekliktir", prompt)


if __name__ == "__main__":
    unittest.main()
