import json
import os
import tempfile
import unittest

from agent.codebase_index import (
    calculate_sha256_text,
    load_index,
    remove_deleted_files_from_index,
    safe_summary_filename,
    save_index,
    should_document_file,
)


class CodebaseIndexTests(unittest.TestCase):
    def test_sha256_is_deterministic(self):
        first = calculate_sha256_text("print('hello')")
        second = calculate_sha256_text("print('hello')")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_new_file_should_be_documented(self):
        index = {
            "schema_version": "1.0",
            "generated_at": "",
            "files": {},
        }

        self.assertTrue(
            should_document_file(
                index=index,
                path="src/example.py",
                content="print('hello')",
            )
        )

    def test_unchanged_file_should_be_skipped(self):
        content = "print('hello')"
        index = {
            "schema_version": "1.0",
            "generated_at": "",
            "files": {
                "src/example.py": {
                    "sha256": calculate_sha256_text(content),
                }
            },
        }

        self.assertFalse(
            should_document_file(
                index=index,
                path="src/example.py",
                content=content,
            )
        )

    def test_changed_file_should_be_documented(self):
        index = {
            "schema_version": "1.0",
            "generated_at": "",
            "files": {
                "src/example.py": {
                    "sha256": calculate_sha256_text("old content"),
                }
            },
        }

        self.assertTrue(
            should_document_file(
                index=index,
                path="src/example.py",
                content="new content",
            )
        )

    def test_summary_filename_is_deterministic_and_path_safe(self):
        first = safe_summary_filename("src/services/user.py")
        second = safe_summary_filename("src/services/user.py")
        different = safe_summary_filename("src/services/order.py")

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertNotIn("/", first)
        self.assertNotIn("\\", first)
        self.assertTrue(first.endswith(".json"))

    def test_index_can_be_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = os.path.join(temp_dir, "index.json")
            index = {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {
                    "src/example.py": {
                        "sha256": calculate_sha256_text("content"),
                        "language": "python",
                    }
                },
            }

            save_index(index, index_path=index_path)
            loaded = load_index(index_path=index_path)

            self.assertEqual(
                loaded["files"]["src/example.py"]["language"],
                "python",
            )

            with open(index_path, "r", encoding="utf-8") as index_file:
                raw_index = json.load(index_file)

            self.assertEqual(raw_index["schema_version"], "1.0")
            self.assertTrue(raw_index["generated_at"])

    def test_existing_inventory_path_is_not_removed(self):
        index = {
            "schema_version": "1.0",
            "generated_at": "",
            "files": {
                "src/first.py": {
                    "sha256": "first-hash",
                    "summary_path": "",
                },
                "src/still_exists.py": {
                    "sha256": "second-hash",
                    "summary_path": "",
                },
            },
        }

        deleted_paths = remove_deleted_files_from_index(
            index=index,
            current_paths={
                "src/first.py",
                "src/still_exists.py",
            },
        )

        self.assertEqual(deleted_paths, [])
        self.assertIn("src/still_exists.py", index["files"])

    def test_deleted_file_and_its_summary_are_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = os.path.join(temp_dir, "deleted-summary.json")

            with open(summary_path, "w", encoding="utf-8") as summary_file:
                json.dump({"path": "src/deleted.py"}, summary_file)

            index = {
                "schema_version": "1.0",
                "generated_at": "",
                "files": {
                    "src/existing.py": {
                        "sha256": "existing-hash",
                        "summary_path": "",
                    },
                    "src/deleted.py": {
                        "sha256": "deleted-hash",
                        "summary_path": summary_path,
                    },
                },
            }

            deleted_paths = remove_deleted_files_from_index(
                index=index,
                current_paths={"src/existing.py"},
            )

            self.assertEqual(deleted_paths, ["src/deleted.py"])
            self.assertNotIn("src/deleted.py", index["files"])
            self.assertFalse(os.path.exists(summary_path))

    def test_corrupted_index_returns_safe_empty_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = os.path.join(temp_dir, "index.json")

            with open(index_path, "w", encoding="utf-8") as index_file:
                index_file.write("{broken json")

            loaded = load_index(index_path=index_path)

            self.assertEqual(loaded["schema_version"], "1.0")
            self.assertEqual(loaded["files"], {})

    def test_index_can_be_saved_without_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_directory = os.getcwd()

            try:
                os.chdir(temp_dir)

                save_index(
                    {
                        "schema_version": "1.0",
                        "generated_at": "",
                        "files": {},
                    },
                    index_path="index.json",
                )

                self.assertTrue(os.path.isfile("index.json"))
                self.assertEqual(load_index("index.json")["files"], {})
            finally:
                os.chdir(previous_directory)

    def test_atomic_save_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = os.path.join(temp_dir, "index.json")

            save_index(
                {
                    "schema_version": "1.0",
                    "generated_at": "",
                    "files": {},
                },
                index_path=index_path,
            )

            remaining_files = os.listdir(temp_dir)

            self.assertEqual(remaining_files, ["index.json"])


if __name__ == "__main__":
    unittest.main()
