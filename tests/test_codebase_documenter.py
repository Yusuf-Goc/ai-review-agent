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


    def test_successful_documentation_updates_file_summary_and_index(self):
        reviewable_files = [
            RepositorySourceFile(
                path="src/example.py",
                language="python",
                line_count=1,
            ),
        ]

        file_doc = {
            "path": "src/example.py",
            "language": "python",
            "purpose": "Example module",
            "main_components": [],
            "important_variables": [],
            "data_flow": "",
            "algorithm_flow": "",
            "external_dependencies": [],
            "side_effects": [],
            "risks_or_notes": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "src")
            os.makedirs(source_dir, exist_ok=True)

            source_content = "print('hello')\n"

            with open(
                os.path.join(source_dir, "example.py"),
                "w",
                encoding="utf-8",
            ) as source_file:
                source_file.write(source_content)

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
            expected_summary_dir = os.path.join(
                temp_dir,
                ".ai-review",
                "summaries",
            )
            expected_summary_path = os.path.join(
                expected_summary_dir,
                "example-summary.json",
            )

            index = {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {},
            }

            file_slice = Mock()
            file_slice.path = "src/example.py"
            file_slice.language = "python"
            file_slice.start_line = 1
            file_slice.end_line = 1
            file_slice.part_label = "full-file"
            file_slice.content = source_content

            scan_unit = Mock()
            scan_unit.unit_id = "full-scan-unit-1"
            scan_unit.kind = "single_file"
            scan_unit.slices = [file_slice]

            response = Mock()
            response.text = (
                '{"files": ['
                '{"path": "src/example.py", '
                '"language": "python", '
                '"purpose": "Example module", '
                '"main_components": [], '
                '"important_variables": [], '
                '"data_flow": "", '
                '"algorithm_flow": "", '
                '"external_dependencies": [], '
                '"side_effects": [], '
                '"risks_or_notes": []}'
                ']}'
            )

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
                    return_value=True,
                ),
                patch.object(
                    codebase_documenter,
                    "build_full_scan_plan",
                    return_value=[scan_unit],
                ),
                patch.object(
                    codebase_documenter,
                    "_call_model_json",
                    return_value=response,
                ),
                patch.object(
                    codebase_documenter,
                    "save_file_summary",
                    return_value=expected_summary_path,
                    create=True,
                ) as save_summary,
                patch.object(
                    codebase_documenter,
                    "update_index_entry",
                    create=True,
                ) as update_entry,
                patch.object(
                    codebase_documenter,
                    "load_all_file_summaries",
                    return_value=[file_doc],
                    create=True,
                ) as load_summaries,
                patch.object(
                    codebase_documenter,
                    "save_index",
                ) as save_index_mock,
            ):
                summary = (
                    codebase_documenter.generate_codebase_documentation(
                        root_dir=temp_dir,
                        repository="example/repository",
                        output_json=output_json,
                        output_markdown=output_markdown,
                    )
                )

            save_summary.assert_called_once_with(
                path="src/example.py",
                file_doc=file_doc,
                summary_dir=expected_summary_dir,
            )
            update_entry.assert_called_once_with(
                index=index,
                path="src/example.py",
                language="python",
                content=source_content,
                line_count=1,
                summary_path=expected_summary_path,
            )
            load_summaries.assert_called_once_with(index)
            save_index_mock.assert_called_once()

            self.assertEqual(summary["files"], [file_doc])
            self.assertEqual(
                summary["stats"]["documented_files"],
                1,
            )

    def test_file_missing_from_model_response_is_not_added_to_index(self):
        reviewable_files = [
            RepositorySourceFile(
                path="src/failed.py",
                language="python",
                line_count=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "src")
            os.makedirs(source_dir, exist_ok=True)

            with open(
                os.path.join(source_dir, "failed.py"),
                "w",
                encoding="utf-8",
            ) as source_file:
                source_file.write("print('failed')\n")

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
                "files": {},
            }

            file_slice = Mock()
            file_slice.path = "src/failed.py"
            file_slice.language = "python"
            file_slice.start_line = 1
            file_slice.end_line = 1
            file_slice.part_label = "full-file"
            file_slice.content = "print('failed')\n"

            scan_unit = Mock()
            scan_unit.unit_id = "full-scan-unit-1"
            scan_unit.kind = "single_file"
            scan_unit.slices = [file_slice]

            response = Mock()
            response.text = '{"files": []}'

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
                    return_value=True,
                ),
                patch.object(
                    codebase_documenter,
                    "build_full_scan_plan",
                    return_value=[scan_unit],
                ),
                patch.object(
                    codebase_documenter,
                    "_call_model_json",
                    return_value=response,
                ),
                patch.object(
                    codebase_documenter,
                    "save_file_summary",
                ) as save_summary,
                patch.object(
                    codebase_documenter,
                    "update_index_entry",
                ) as update_entry,
                patch.object(
                    codebase_documenter,
                    "load_all_file_summaries",
                    return_value=[],
                ),
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

            save_summary.assert_not_called()
            update_entry.assert_not_called()
            self.assertNotIn("src/failed.py", index["files"])
            self.assertEqual(summary["stats"]["documented_files"], 0)


    def test_files_over_limit_are_reported_as_skipped(self):
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

            index = {
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
                    return_value=True,
                ),
                patch.object(
                    codebase_documenter,
                    "build_full_scan_plan",
                    return_value=[],
                ),
                patch.object(
                    codebase_documenter,
                    "save_index",
                ),
                patch.object(
                    codebase_documenter,
                    "load_all_file_summaries",
                    return_value=[],
                ),
            ):
                summary = (
                    codebase_documenter.generate_codebase_documentation(
                        root_dir=temp_dir,
                        repository="example/repository",
                        output_json=output_json,
                        output_markdown=output_markdown,
                        max_files=1,
                    )
                )

            self.assertEqual(summary["stats"]["repository_files"], 3)
            self.assertEqual(summary["stats"]["selected_files"], 1)
            self.assertEqual(summary["stats"]["skipped_by_limit"], 2)


    def test_changed_files_are_selected_before_file_limit_is_applied(self):
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
                "files": {},
            }

            def should_document(_index, path, _content):
                return path == "src/changed.py"

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
                    side_effect=should_document,
                ),
                patch.object(
                    codebase_documenter,
                    "build_full_scan_plan",
                    return_value=[],
                ) as build_plan,
                patch.object(
                    codebase_documenter,
                    "save_index",
                ),
                patch.object(
                    codebase_documenter,
                    "load_all_file_summaries",
                    return_value=[],
                ),
            ):
                summary = (
                    codebase_documenter.generate_codebase_documentation(
                        root_dir=temp_dir,
                        repository="example/repository",
                        output_json=output_json,
                        output_markdown=output_markdown,
                        max_files=1,
                    )
                )

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
                summary["stats"]["skipped_by_limit"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
