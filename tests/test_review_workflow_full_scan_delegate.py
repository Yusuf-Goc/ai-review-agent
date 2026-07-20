from pathlib import Path
import unittest


class ReviewWorkflowFullScanDelegateTests(unittest.TestCase):
    def test_full_scan_uses_reusable_matrix_workflow(self):
        workflow = Path(
            ".github/workflows/review.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "full-repository-scan:",
            workflow,
        )
        self.assertIn(
            "if: ${{ inputs.scan_mode == 'full' }}",
            workflow,
        )
        self.assertIn(
            "uses: ./.github/workflows/full-scan.yml",
            workflow,
        )
        self.assertIn(
            "agent_ref: ${{ inputs.agent_ref }}",
            workflow,
        )
        self.assertIn(
            "GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}",
            workflow,
        )

    def test_ai_review_job_is_only_used_for_pr_mode(self):
        workflow = Path(
            ".github/workflows/review.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "if: ${{ inputs.scan_mode == 'pr' }}",
            workflow,
        )
        self.assertNotIn(
            "inputs.scan_mode == 'pr' || "
            "inputs.scan_mode == 'full'",
            workflow,
        )
        self.assertNotIn(
            "--github-full-scan",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
