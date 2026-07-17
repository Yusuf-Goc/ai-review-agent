from pathlib import Path
import unittest


class DocsWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow_path = Path(
            ".github/workflows/docs.yml"
        )
        cls.workflow = cls.workflow_path.read_text(
            encoding="utf-8"
        )

    def test_workflow_has_prepare_small_worker_and_merge_jobs(self):
        for job_name in [
            "prepare:",
            "codebase-docs-small:",
            "docs-workers:",
            "docs-merge:",
        ]:
            with self.subTest(job_name=job_name):
                self.assertIn(job_name, self.workflow)

    def test_small_repository_keeps_simple_documentation_command(self):
        self.assertIn(
            "fromJSON(needs.prepare.outputs.shard_count) <= 1",
            self.workflow,
        )
        self.assertIn(
            "--github-codebase-docs",
            self.workflow,
        )

    def test_large_repository_uses_matrix_workers(self):
        self.assertIn(
            "fromJSON(needs.prepare.outputs.matrix)",
            self.workflow,
        )
        self.assertIn(
            "--run-codebase-docs-shard",
            self.workflow,
        )
        self.assertIn(
            "${{ matrix.payload_file }}",
            self.workflow,
        )
        self.assertIn(
            "${{ matrix.shard_id }}",
            self.workflow,
        )

    def test_large_repository_downloads_and_merges_results(self):
        self.assertIn(
            "pattern: docs-result-*",
            self.workflow,
        )
        self.assertIn(
            "--merge-codebase-docs-shards",
            self.workflow,
        )
        self.assertIn(
            "--docs-results-dir",
            self.workflow,
        )

    def test_prepare_bundle_is_passed_as_artifact(self):
        self.assertIn(
            "--prepare-codebase-docs",
            self.workflow,
        )
        self.assertIn(
            "name: codebase-docs-bundle",
            self.workflow,
        )
        self.assertIn(
            "manifest.json",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
