import os
import tempfile
import unittest
from unittest.mock import patch

from agent.repo_scanner import find_reviewable_repo_files


class RepoScannerTests(unittest.TestCase):
    def test_reviewable_files_are_returned_in_path_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            filenames = [
                "z_last.py",
                "a_first.py",
                "m_middle.sql",
            ]

            for filename in filenames:
                with open(
                    os.path.join(temp_dir, filename),
                    "w",
                    encoding="utf-8",
                ) as source_file:
                    source_file.write("line one\nline two\n")

            with patch(
                "agent.repo_scanner.os.walk",
                return_value=[
                    (
                        temp_dir,
                        [],
                        [
                            "z_last.py",
                            "a_first.py",
                            "m_middle.sql",
                        ],
                    )
                ],
            ):
                result = find_reviewable_repo_files(
                    root_dir=temp_dir,
                )

            self.assertEqual(
                [item.path for item in result],
                [
                    "a_first.py",
                    "m_middle.sql",
                    "z_last.py",
                ],
            )


if __name__ == "__main__":
    unittest.main()
