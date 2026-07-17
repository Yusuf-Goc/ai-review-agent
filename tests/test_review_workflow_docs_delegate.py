from pathlib import Path
import unittest


class ReviewWorkflowDocsDelegateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = Path(
            ".github/workflows/review.yml"
        ).read_text(encoding="utf-8")

    def test_docs_mode_delegates_to_docs_workflow(self):
        self.assertIn(
            "  codebase-docs:",
            self.workflow,
        )
        self.assertIn(
            "if: ${{ inputs.scan_mode == 'docs' }}",
            self.workflow,
        )
        self.assertIn(
            "uses: ./.github/workflows/docs.yml",
            self.workflow,
        )
        self.assertIn(
            "agent_ref: ${{ inputs.agent_ref }}",
            self.workflow,
        )
        self.assertIn(
            "GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}",
            self.workflow,
        )

    def test_delegated_docs_job_preserves_write_permission(self):
        docs_section = self.workflow.split(
            "  codebase-docs:",
            1,
        )[1]

        self.assertIn(
            "permissions:\n      contents: write",
            docs_section,
        )

    def test_review_workflow_no_longer_runs_docs_directly(self):
        docs_section = self.workflow.split(
            "  codebase-docs:",
            1,
        )[1]

        self.assertNotIn(
            "--github-codebase-docs",
            docs_section,
        )
        self.assertNotIn(
            "runs-on:",
            docs_section,
        )


if __name__ == "__main__":
    unittest.main()
