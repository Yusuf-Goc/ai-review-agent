import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import cli


class CliDocsModesTests(unittest.TestCase):
    def test_prepare_docs_mode_creates_unlimited_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared_result = {
                "manifest": {
                    "shard_count": 2,
                    "matrix": {
                        "include": [
                            {
                                "shard_id": "docs-shard-001",
                                "payload_file": (
                                    "shards/docs-shard-001.json"
                                ),
                            },
                            {
                                "shard_id": "docs-shard-002",
                                "payload_file": (
                                    "shards/docs-shard-002.json"
                                ),
                            },
                        ]
                    },
                },
                "state": {
                    "repository_files": 1_500,
                    "selected_files": 1_200,
                    "planned_units": 80,
                    "shard_count": 2,
                },
                "state_path": (
                    f"{temp_dir}/prepare-state.json"
                ),
            }

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "cli.py",
                        "--prepare-codebase-docs",
                        "--docs-output-dir",
                        temp_dir,
                    ],
                ),
                patch(
                    "cli.prepare_codebase_docs_bundle",
                    return_value=prepared_result,
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

    def test_existing_small_repository_docs_mode_is_preserved(self):
        summary = {
            "stats": {
                "documented_files": 3,
                "failed_units": 0,
            }
        }

        with (
            patch.object(
                sys,
                "argv",
                [
                    "cli.py",
                    "--github-codebase-docs",
                    "--retries",
                    "0",
                    "--retry-delay",
                    "0",
                ],
            ),
            patch(
                "cli.generate_codebase_documentation",
                return_value=summary,
            ) as generate_docs,
            patch("builtins.print"),
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        generate_docs.assert_called_once()

        call_kwargs = generate_docs.call_args.kwargs

        self.assertEqual(call_kwargs["root_dir"], ".")
        self.assertEqual(
            call_kwargs["output_json"],
            ".ai-review/codebase-summary.json",
        )
        self.assertEqual(
            call_kwargs["output_markdown"],
            "docs/ai-codebase-report.md",
        )


    def test_worker_mode_processes_one_shard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = (
                f"{temp_dir}/docs-shard-001.json"
            )
            result_path = (
                f"{temp_dir}/results/docs-shard-001.json"
            )

            worker_result = {
                "shard_id": "docs-shard-001",
                "unit_count": 4,
                "files": [],
                "failed_units": [],
            }

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "cli.py",
                        "--run-codebase-docs-shard",
                        "--docs-payload-file",
                        payload_path,
                        "--docs-result-file",
                        result_path,
                        "--model",
                        "test-model",
                        "--retries",
                        "0",
                        "--retry-delay",
                        "0",
                    ],
                ),
                patch(
                    "cli.run_docs_worker",
                    return_value=worker_result,
                    create=True,
                ) as run_worker,
                patch("builtins.print"),
            ):
                exit_code = cli.main()

            self.assertEqual(exit_code, 0)

            run_worker.assert_called_once_with(
                payload_path=payload_path,
                output_path=result_path,
                model="test-model",
                retries=0,
                retry_delay=0.0,
            )


    def test_merge_mode_finalizes_downloaded_worker_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_dir = f"{temp_dir}/bundle"
            results_dir = f"{temp_dir}/results"

            Path(bundle_dir).mkdir(parents=True)
            Path(results_dir, "worker-002").mkdir(parents=True)
            Path(results_dir, "worker-001").mkdir(parents=True)

            first_result = Path(
                results_dir,
                "worker-001",
                "docs-shard-001.json",
            )
            second_result = Path(
                results_dir,
                "worker-002",
                "docs-shard-002.json",
            )

            first_result.write_text("{}", encoding="utf-8")
            second_result.write_text("{}", encoding="utf-8")

            expected_summary = {
                "stats": {
                    "documented_files": 12,
                    "failed_units": 1,
                }
            }

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "cli.py",
                        "--merge-codebase-docs-shards",
                        "--docs-bundle-dir",
                        bundle_dir,
                        "--docs-results-dir",
                        results_dir,
                    ],
                ),
                patch.dict(
                    "os.environ",
                    {
                        "GITHUB_REPOSITORY": (
                            "example/repository"
                        ),
                    },
                    clear=False,
                ),
                patch(
                    "cli.merge_codebase_docs_bundle",
                    return_value=expected_summary,
                    create=True,
                ) as merge_bundle,
                patch("builtins.print"),
            ):
                exit_code = cli.main()

            self.assertEqual(exit_code, 0)

            merge_bundle.assert_called_once_with(
                root_dir=".",
                bundle_dir=bundle_dir,
                result_paths=[
                    str(first_result),
                    str(second_result),
                ],
                repository="example/repository",
                output_json=(
                    ".ai-review/codebase-summary.json"
                ),
                output_markdown=(
                    "docs/ai-codebase-report.md"
                ),
                max_files=None,
            )


    def test_merge_mode_allows_empty_results_for_zero_shards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_dir = Path(temp_dir, "bundle")
            results_dir = Path(temp_dir, "results")

            bundle_dir.mkdir(parents=True)
            results_dir.mkdir(parents=True)

            expected_summary = {
                "stats": {
                    "documented_files": 0,
                    "failed_units": 0,
                }
            }

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "cli.py",
                        "--merge-codebase-docs-shards",
                        "--docs-bundle-dir",
                        str(bundle_dir),
                        "--docs-results-dir",
                        str(results_dir),
                    ],
                ),
                patch.dict(
                    "os.environ",
                    {
                        "GITHUB_REPOSITORY": (
                            "example/repository"
                        ),
                    },
                    clear=False,
                ),
                patch(
                    "cli.merge_codebase_docs_bundle",
                    return_value=expected_summary,
                ) as merge_bundle,
                patch("builtins.print"),
            ):
                exit_code = cli.main()

            self.assertEqual(exit_code, 0)

            merge_bundle.assert_called_once_with(
                root_dir=".",
                bundle_dir=str(bundle_dir),
                result_paths=[],
                repository="example/repository",
                output_json=(
                    ".ai-review/codebase-summary.json"
                ),
                output_markdown=(
                    "docs/ai-codebase-report.md"
                ),
                max_files=None,
            )


if __name__ == "__main__":
    unittest.main()
