import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
