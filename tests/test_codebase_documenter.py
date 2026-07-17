import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent import codebase_documenter
from agent.repo_scanner import RepositorySourceFile


class CodebaseDocumenterTests(unittest.TestCase):
    def test_deleted_file_cleanup_uses_full_repository_inventory(self):
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
                source_path = os.path.join(temp_dir, file_info.path)

                with open(source_path, "w", encoding="utf-8") as source_file:
                    source_file.write("print('hello')\n")

            output_json = os.path.join(
                temp_dir,
                ".ai-review",
                "codebase-summary.json",
            )
            output_markdown = os.path.join(
                temp_dir,
                "docs",
                "ai-codebase-report.md",
            )

            empty_index = {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {},
            }

            with (
                patch.object(
                    codebase_documenter,
                    "find_reviewable_repo_files",
                    return_value=reviewable_files,
                ),
                patch.object(
                    codebase_documenter,
                    "build_full_scan_plan",
                    return_value=[],
                ),
                patch.object(
                    codebase_documenter,
                    "load_index",
                    return_value=empty_index,
                    create=True,
                ) as load_index_mock,
                patch.object(
                    codebase_documenter,
                    "remove_deleted_files_from_index",
                    return_value=[],
                    create=True,
                ) as remove_deleted,
                patch.object(
                    codebase_documenter,
                    "should_document_file",
                    return_value=True,
                    create=True,
                ),
                patch.object(
                    codebase_documenter,
                    "save_index",
                    create=True,
                ) as save_index_mock,
                patch.object(
                    codebase_documenter,
                    "load_all_file_summaries",
                    return_value=[],
                    create=True,
                ),
            ):
                codebase_documenter.generate_codebase_documentation(
                    root_dir=temp_dir,
                    repository="example/repository",
                    output_json=output_json,
                    output_markdown=output_markdown,
                    max_files=1,
                )

            expected_index_path = os.path.join(
                temp_dir,
                ".ai-review",
                "index.json",
            )

            load_index_mock.assert_called_once_with(
                index_path=expected_index_path,
            )
            save_index_mock.assert_called_once_with(
                index=empty_index,
                index_path=expected_index_path,
            )
            remove_deleted.assert_called_once()

            current_paths = remove_deleted.call_args.kwargs[
                "current_paths"
            ]

            self.assertEqual(
                current_paths,
                {
                    "src/first.py",
                    "src/second.py",
                    "src/third.py",
                },
            )

    def test_unchanged_files_are_not_sent_to_scan_planner(self):
        reviewable_files = [
            RepositorySourceFile(
                path="src/unchanged.py",
                language="python",
                line_count=1,
            ),
            RepositorySourceFile(
                path="src/changed.py",
                language="python",
                line_count=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "src")
            os.makedirs(source_dir, exist_ok=True)

            with open(
                os.path.join(source_dir, "unchanged.py"),
                "w",
                encoding="utf-8",
            ) as source_file:
                source_file.write("print('unchanged')\n")

            with open(
                os.path.join(source_dir, "changed.py"),
                "w",
                encoding="utf-8",
            ) as source_file:
                source_file.write("print('changed')\n")

            output_json = os.path.join(
                temp_dir,
                ".ai-review",
                "codebase-summary.json",
            )
            output_markdown = os.path.join(
                temp_dir,
                "docs",
                "ai-codebase-report.md",
            )

            index = {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {
                    "src/unchanged.py": {
                        "sha256": "existing-hash",
                        "summary_path": "",
                    },
                    "src/changed.py": {
                        "sha256": "old-hash",
                        "summary_path": "",
                    },
                },
            }

            with (
                patch.object(
                    codebase_documenter,
                    "find_reviewable_repo_files",
                    return_value=reviewable_files,
                ),
                patch.object(
                    codebase_documenter,
                    "load_index",
                    return_value=index,
                ),
                patch.object(
                    codebase_documenter,
                    "remove_deleted_files_from_index",
                    return_value=[],
                ),
                patch.object(
                    codebase_documenter,
                    "should_document_file",
                    side_effect=lambda current_index, path, content: (
                        path == "src/changed.py"
                    ),
                    create=True,
                ) as should_document,
                patch.object(
                    codebase_documenter,
                    "build_full_scan_plan",
                    return_value=[],
                ) as build_plan,
                patch.object(
                    codebase_documenter,
                    "save_index",
                ),
            ):
                summary = (
                    codebase_documenter.generate_codebase_documentation(
                        root_dir=temp_dir,
                        repository="example/repository",
                        output_json=output_json,
                        output_markdown=output_markdown,
                    )
                )

            self.assertEqual(should_document.call_count, 2)
            build_plan.assert_called_once()

            planned_items = build_plan.call_args.args[0]

            self.assertEqual(len(planned_items), 1)
            self.assertEqual(
                planned_items[0]["path"],
                "src/changed.py",
            )
            self.assertEqual(
                summary["stats"]["changed_or_new_files"],
                1,
            )
            self.assertEqual(
                summary["stats"]["unchanged_files"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
