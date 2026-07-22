import unittest
from unittest.mock import patch

from agent.pr_context import (
    build_pr_context,
    load_base_markdown_context,
)


class PrContextFallbackTests(unittest.TestCase):
    def test_summary_context_has_priority_over_markdown(self):
        summary = {
            "app.py": {
                "path": "app.py",
                "purpose": "Uygulama giris noktasi.",
            }
        }

        with (
            patch(
                "agent.pr_context.get_changed_paths",
                return_value=["app.py", "new.py"],
            ),
            patch(
                "agent.pr_context.load_main_branch_codebase_context",
                return_value=summary,
            ),
            patch(
                "agent.pr_context.load_base_markdown_context",
            ) as markdown_loader,
        ):
            context = build_pr_context("base", "head")

        self.assertEqual("codebase_summary", context["source_type"])
        self.assertEqual(
            {"app.py": summary["app.py"]},
            context["file_context"],
        )
        self.assertEqual(
            [".ai-review/codebase-summary.json"],
            context["context_sources"],
        )
        markdown_loader.assert_not_called()

    def test_markdown_is_used_when_summary_is_missing(self):
        documents = [
            {
                "path": "README.md",
                "content": "Proje siparis yonetimi yapar.",
            }
        ]

        with (
            patch(
                "agent.pr_context.get_changed_paths",
                return_value=["orders.go"],
            ),
            patch(
                "agent.pr_context.load_main_branch_codebase_context",
                return_value={},
            ),
            patch(
                "agent.pr_context.load_base_markdown_context",
                return_value=documents,
            ),
        ):
            context = build_pr_context("base", "head")

        self.assertEqual("markdown", context["source_type"])
        self.assertEqual(documents, context["project_documents"])
        self.assertEqual(["README.md"], context["context_sources"])

    def test_context_is_empty_when_summary_and_markdown_are_missing(self):
        with (
            patch(
                "agent.pr_context.get_changed_paths",
                return_value=["orders.go"],
            ),
            patch(
                "agent.pr_context.load_main_branch_codebase_context",
                return_value={},
            ),
            patch(
                "agent.pr_context.load_base_markdown_context",
                return_value=[],
            ),
        ):
            context = build_pr_context("base", "head")

        self.assertEqual("none", context["source_type"])
        self.assertEqual([], context["context_sources"])

    @patch(
        "agent.pr_context._run_git_list_files",
        return_value=[
            "notes/random.md",
            "docs/architecture.md",
            "node_modules/package/README.md",
            "README.md",
        ],
    )
    @patch("agent.pr_context._run_git_show")
    def test_markdown_context_prefers_readme_and_architecture(
        self,
        git_show_mock,
        _git_list_mock,
    ):
        git_show_mock.side_effect = (
            lambda _ref, path: f"content:{path}"
        )

        documents = load_base_markdown_context(
            "base",
            max_files=2,
        )

        self.assertEqual(
            ["README.md", "docs/architecture.md"],
            [document["path"] for document in documents],
        )


if __name__ == "__main__":
    unittest.main()
