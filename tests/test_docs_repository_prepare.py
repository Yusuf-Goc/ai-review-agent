import os
import tempfile
import unittest
from unittest.mock import patch

from agent.codebase_documenter import collect_docs_scan_input
from agent.repo_scanner import RepositorySourceFile


class DocsRepositoryPrepareTests(unittest.TestCase):
    def test_unlimited_prepare_includes_all_changed_files(self):
        reviewable_files = [
            RepositorySourceFile(
                path="src/first.py",
                language="python",
                line_count=1,
            ),
            RepositorySourceFile(
                path="src/second.py",
                language="python",
                line_count=1,
            ),
            RepositorySourceFile(
                path="src/third.py",
                language="python",
                line_count=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "src")
            os.makedirs(source_dir, exist_ok=True)

            for file_info in reviewable_files:
                with open(
                    os.path.join(temp_dir, file_info.path),
                    "w",
                    encoding="utf-8",
                ) as source_file:
                    source_file.write(
                        f"print({file_info.path!r})\n"
                    )

            empty_index = {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {},
            }

            with (
                patch(
                    "agent.codebase_documenter."
                    "find_reviewable_repo_files",
                    return_value=reviewable_files,
                ),
                patch(
                    "agent.codebase_documenter.load_index",
                    return_value=empty_index,
                ),
                patch(
                    "agent.codebase_documenter."
                    "remove_deleted_files_from_index",
                    return_value=[],
                ),
                patch(
                    "agent.codebase_documenter."
                    "should_document_file",
                    return_value=True,
                ),
                patch(
                    "agent.codebase_documenter."
                    "build_full_scan_plan",
                    return_value=[],
                ) as build_plan,
            ):
                prepared = collect_docs_scan_input(
                    root_dir=temp_dir,
                    max_files=None,
                )

            planned_items = build_plan.call_args.args[0]

            self.assertEqual(len(planned_items), 3)
            self.assertEqual(len(prepared["file_items"]), 3)
            self.assertEqual(prepared["repository_files"], 3)
            self.assertEqual(prepared["selected_files"], 3)
            self.assertEqual(prepared["changed_or_new_files"], 3)
            self.assertEqual(prepared["unchanged_files"], 0)
            self.assertEqual(prepared["skipped_by_limit"], 0)

    def test_prepare_applies_limit_after_change_detection(self):
        reviewable_files = [
            RepositorySourceFile(
                path="src/unchanged.py",
                language="python",
                line_count=1,
            ),
            RepositorySourceFile(
                path="src/changed-one.py",
                language="python",
                line_count=1,
            ),
            RepositorySourceFile(
                path="src/changed-two.py",
                language="python",
                line_count=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "src")
            os.makedirs(source_dir, exist_ok=True)

            for file_info in reviewable_files:
                with open(
                    os.path.join(temp_dir, file_info.path),
                    "w",
                    encoding="utf-8",
                ) as source_file:
                    source_file.write("print('example')\n")

            def should_document(_index, path, _content):
                return path != "src/unchanged.py"

            with (
                patch(
                    "agent.codebase_documenter."
                    "find_reviewable_repo_files",
                    return_value=reviewable_files,
                ),
                patch(
                    "agent.codebase_documenter.load_index",
                    return_value={
                        "schema_version": "1.0",
                        "generated_at": "",
                        "files": {},
                    },
                ),
                patch(
                    "agent.codebase_documenter."
                    "remove_deleted_files_from_index",
                    return_value=[],
                ),
                patch(
                    "agent.codebase_documenter."
                    "should_document_file",
                    side_effect=should_document,
                ),
                patch(
                    "agent.codebase_documenter."
                    "build_full_scan_plan",
                    return_value=[],
                ) as build_plan,
            ):
                prepared = collect_docs_scan_input(
                    root_dir=temp_dir,
                    max_files=1,
                )

            planned_items = build_plan.call_args.args[0]

            self.assertEqual(len(planned_items), 1)
            self.assertEqual(
                planned_items[0]["path"],
                "src/changed-one.py",
            )
            self.assertEqual(prepared["unchanged_files"], 1)
            self.assertEqual(prepared["selected_files"], 1)
            self.assertEqual(prepared["skipped_by_limit"], 1)


if __name__ == "__main__":
    unittest.main()
