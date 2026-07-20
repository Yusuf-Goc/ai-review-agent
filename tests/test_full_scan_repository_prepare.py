from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.full_scan_planner import FullScanUnit
from agent.repo_scanner import RepositorySourceFile
from agent.reviewer import collect_full_scan_input


class FullScanRepositoryPrepareTests(unittest.TestCase):
    @staticmethod
    def create_source(
        root_dir: Path,
        relative_path: str,
        content: str,
    ) -> None:
        source_path = root_dir / relative_path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(content, encoding="utf-8")

    def test_prepare_reads_selected_files_from_root_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)

            self.create_source(
                root_dir,
                "src/alpha.py",
                "alpha = 1\n",
            )
            self.create_source(
                root_dir,
                "src/beta.py",
                "beta = 2\n",
            )
            self.create_source(
                root_dir,
                "src/gamma.py",
                "gamma = 3\n",
            )

            repository_files = [
                RepositorySourceFile(
                    path="src/alpha.py",
                    language="python",
                    line_count=1,
                ),
                RepositorySourceFile(
                    path="src/beta.py",
                    language="python",
                    line_count=1,
                ),
                RepositorySourceFile(
                    path="src/gamma.py",
                    language="python",
                    line_count=1,
                ),
            ]

            scan_plan = [
                FullScanUnit(
                    unit_id="unit-001",
                    kind="small_file_batch",
                    total_lines=2,
                    total_chars=20,
                    risk_score=0,
                )
            ]

            expected_file_items = [
                {
                    "path": "src/alpha.py",
                    "language": "python",
                    "line_count": 1,
                    "content": "alpha = 1\n",
                },
                {
                    "path": "src/beta.py",
                    "language": "python",
                    "line_count": 1,
                    "content": "beta = 2\n",
                },
            ]

            with (
                patch(
                    "agent.reviewer.find_reviewable_repo_files",
                    return_value=repository_files,
                ) as find_files,
                patch(
                    "agent.reviewer.build_full_scan_plan",
                    return_value=scan_plan,
                ) as build_plan,
            ):
                prepared = collect_full_scan_input(
                    root_dir=str(root_dir),
                    max_files=2,
                )

            find_files.assert_called_once_with(
                root_dir=str(root_dir),
            )
            build_plan.assert_called_once_with(
                expected_file_items,
            )

            self.assertEqual(
                prepared["file_items"],
                expected_file_items,
            )
            self.assertEqual(
                prepared["scan_plan"],
                scan_plan,
            )
            self.assertEqual(
                prepared["repository_files"],
                3,
            )
            self.assertEqual(
                prepared["selected_files"],
                2,
            )
            self.assertEqual(
                prepared["skipped_files"],
                1,
            )
            self.assertEqual(
                prepared["read_errors"],
                [],
            )

    def test_unlimited_prepare_selects_every_repository_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)

            self.create_source(
                root_dir,
                "first.py",
                "first = True\n",
            )
            self.create_source(
                root_dir,
                "second.py",
                "second = True\n",
            )

            repository_files = [
                RepositorySourceFile(
                    path="first.py",
                    language="python",
                    line_count=1,
                ),
                RepositorySourceFile(
                    path="second.py",
                    language="python",
                    line_count=1,
                ),
            ]

            with (
                patch(
                    "agent.reviewer.find_reviewable_repo_files",
                    return_value=repository_files,
                ),
                patch(
                    "agent.reviewer.build_full_scan_plan",
                    return_value=[],
                ) as build_plan,
            ):
                prepared = collect_full_scan_input(
                    root_dir=str(root_dir),
                    max_files=None,
                )

            self.assertEqual(
                prepared["selected_files"],
                2,
            )
            self.assertEqual(
                prepared["skipped_files"],
                0,
            )
            self.assertEqual(
                len(prepared["file_items"]),
                2,
            )
            build_plan.assert_called_once_with(
                prepared["file_items"],
            )


if __name__ == "__main__":
    unittest.main()
