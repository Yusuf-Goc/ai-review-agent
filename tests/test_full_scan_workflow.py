from pathlib import Path
import unittest


class FullScanWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow_path = Path(
            ".github/workflows/full-scan.yml"
        )

    def test_full_scan_workflow_has_prepare_worker_and_merge_jobs(self):
        self.assertTrue(
            self.workflow_path.is_file(),
            "full-scan.yml workflow dosyası bulunamadı.",
        )

        workflow = self.workflow_path.read_text(
            encoding="utf-8",
        )

        required_fragments = [
            "workflow_call:",
            "prepare:",
            "full-scan-small:",
            "full-scan-workers:",
            "full-scan-merge:",
            "--prepare-full-scan",
            "--run-full-scan-shard",
            "--merge-full-scan-shards",
            "full-scan-bundle",
            "full-scan-result-${{ matrix.shard_id }}",
            "matrix: ${{ fromJSON(needs.prepare.outputs.matrix) }}",
            "fail-fast: false",
            "issues: write",
        ]

        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, workflow)

    def test_small_and_matrix_paths_are_mutually_selected(self):
        workflow = self.workflow_path.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "fromJSON(needs.prepare.outputs.shard_count) <= 1",
            workflow,
        )
        self.assertIn(
            "fromJSON(needs.prepare.outputs.shard_count) > 1",
            workflow,
        )

    def test_merge_runs_even_when_a_worker_fails(self):
        workflow = self.workflow_path.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "always() && needs.prepare.result == 'success'",
            workflow,
        )
        self.assertIn(
            "continue-on-error: true",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
