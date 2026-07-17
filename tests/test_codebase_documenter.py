import os
import tempfile
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
