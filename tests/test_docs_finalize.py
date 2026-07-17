import json
import os
import tempfile
import unittest
from unittest.mock import patch

from agent.codebase_documenter import finalize_docs_results
from agent.full_scan_planner import FullScanUnit


class DocsFinalizeTests(unittest.TestCase):
    def test_finalize_updates_index_and_writes_reports(self):
        scan_unit = FullScanUnit(
            unit_id="unit-001",
            kind="single_file",
            total_lines=2,
            total_chars=12,
            risk_score=0,
        )

        file_doc = {
            "path": "src/example.py",
            "language": "python",
            "purpose": "Örnek dosya",
            "main_components": [],
            "important_variables": [],
            "external_dependencies": [],
            "side_effects": [],
            "risks_or_notes": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
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
            index_path = os.path.join(
                temp_dir,
                ".ai-review",
                "index.json",
            )
            expected_summary_path = os.path.join(
                temp_dir,
                ".ai-review",
                "summaries",
                "example-summary.json",
            )

            index = {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {},
            }

            prepared = {
                "index": index,
                "index_path": index_path,
                "file_items": [
                    {
                        "path": "src/example.py",
                        "language": "python",
                        "line_count": 2,
                        "content": "a = 1\nb = 2\n",
                    }
                ],
                "deleted_paths": ["src/deleted.py"],
                "repository_files": 5,
                "selected_files": 1,
                "changed_or_new_files": 1,
                "unchanged_files": 4,
                "skipped_by_limit": 0,
                "scan_plan": [scan_unit],
            }

            with (
                patch(
                    "agent.codebase_documenter.save_file_summary",
                    return_value=expected_summary_path,
                ) as save_summary,
                patch(
                    "agent.codebase_documenter.update_index_entry",
                ) as update_index,
                patch(
                    "agent.codebase_documenter.save_index",
                ) as save_index,
                patch(
                    "agent.codebase_documenter."
                    "load_all_file_summaries",
                    return_value=[file_doc],
                ),
                patch(
                    "agent.codebase_documenter."
                    "_build_markdown_report",
                    return_value="# Generated report\n",
                ),
            ):
                summary = finalize_docs_results(
                    prepared=prepared,
                    merged_files_by_path={
                        "src/example.py": file_doc,
                    },
                    failed_units=[
                        {
                            "unit_id": "unit-002",
                            "reason": "Geçici hata",
                        }
                    ],
                    root_dir=temp_dir,
                    repository="example/repository",
                    output_json=output_json,
                    output_markdown=output_markdown,
                )

            save_summary.assert_called_once_with(
                path="src/example.py",
                file_doc=file_doc,
                summary_dir=os.path.join(
                    temp_dir,
                    ".ai-review",
                    "summaries",
                ),
            )

            update_index.assert_called_once_with(
                index=index,
                path="src/example.py",
                language="python",
                content="a = 1\nb = 2\n",
                line_count=2,
                summary_path=expected_summary_path,
            )

            save_index.assert_called_once_with(
                index=index,
                index_path=index_path,
            )

            self.assertEqual(
                summary["repository"],
                "example/repository",
            )
            self.assertEqual(
                summary["deleted_files"],
                ["src/deleted.py"],
            )
            self.assertEqual(
                summary["stats"]["repository_files"],
                5,
            )
            self.assertEqual(
                summary["stats"]["planned_units"],
                1,
            )
            self.assertEqual(
                summary["stats"]["documented_files"],
                1,
            )
            self.assertEqual(
                summary["stats"]["failed_units"],
                1,
            )

            self.assertTrue(os.path.isfile(output_json))
            self.assertTrue(os.path.isfile(output_markdown))

            with open(
                output_json,
                "r",
                encoding="utf-8",
            ) as json_file:
                saved_summary = json.load(json_file)

            self.assertEqual(
                saved_summary["repository"],
                "example/repository",
            )

            with open(
                output_markdown,
                "r",
                encoding="utf-8",
            ) as markdown_file:
                self.assertEqual(
                    markdown_file.read(),
                    "# Generated report\n",
                )


if __name__ == "__main__":
    unittest.main()
