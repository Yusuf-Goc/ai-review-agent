import sys
import tempfile
import unittest
from unittest.mock import patch

import cli


class CliFullScanModesTests(unittest.TestCase):
    def test_existing_single_job_full_scan_mode_is_preserved(self):
        expected_result = {
            "summary": "Tarama tamamlandı.",
            "findings": [],
        }

        with (
            patch.object(
                sys,
                "argv",
                [
                    "cli.py",
                    "--github-full-scan",
                ],
            ),
            patch.dict(
                "os.environ",
                {
                    "GITHUB_REPOSITORY": (
                        "example/repository"
                    ),
                    "GITHUB_TOKEN": "test-token",
                },
                clear=False,
            ),
            patch(
                "cli.analyze_full_repository",
                return_value=expected_result,
            ) as analyze_repository,
            patch(
                "cli.post_full_scan_result_as_issue",
            ) as post_issue,
            patch("builtins.print"),
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        analyze_repository.assert_called_once()
        post_issue.assert_called_once_with(
            expected_result,
        )

    def test_prepare_full_scan_mode_creates_unlimited_bundle(self):
        expected_result = {
            "manifest": {
                "shard_count": 3,
                "unit_count": 12,
            },
            "state": {
                "repository_files": 100,
                "selected_files": 100,
                "planned_units": 12,
                "shard_count": 3,
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "cli.py",
                        "--prepare-full-scan",
                        "--full-scan-output-dir",
                        temp_dir,
                    ],
                ),
                patch(
                    "cli.prepare_full_scan_bundle",
                    return_value=expected_result,
                    create=True,
                ) as prepare_bundle,
                patch("builtins.print"),
            ):
                exit_code = cli.main()

        self.assertEqual(exit_code, 0)

        prepare_bundle.assert_called_once_with(
            root_dir=".",
            output_dir=temp_dir,
            max_files=None,
        )


    def test_run_full_scan_shard_mode_writes_worker_result(self):
        expected_result = {
            "shard_id": "docs-shard-001",
            "unit_count": 2,
            "findings": [],
            "failed_units": [],
            "stats": {
                "planned_units": 2,
            },
        }

        with (
            patch.object(
                sys,
                "argv",
                [
                    "cli.py",
                    "--run-full-scan-shard",
                    "--full-scan-payload-file",
                    "/bundle/shards/docs-shard-001.json",
                    "--full-scan-result-file",
                    "/results/docs-shard-001.json",
                    "--model",
                    "test-model",
                    "--max-review-lines",
                    "450",
                    "--retries",
                    "2",
                    "--retry-delay",
                    "3",
                ],
            ),
            patch(
                "cli.run_full_scan_worker",
                return_value=expected_result,
                create=True,
            ) as run_worker,
            patch("builtins.print"),
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)

        run_worker.assert_called_once_with(
            payload_path=(
                "/bundle/shards/docs-shard-001.json"
            ),
            output_path=(
                "/results/docs-shard-001.json"
            ),
            model="test-model",
            max_review_lines=450,
            retries=2,
            retry_delay=3.0,
        )


if __name__ == "__main__":
    unittest.main()
