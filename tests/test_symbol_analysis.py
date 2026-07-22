import unittest

from agent.symbol_analysis import extract_changed_symbols


class SymbolAnalysisTests(unittest.TestCase):
    def test_extracts_modified_python_function_from_hunk_header(self):
        payload = {
            "files": [
                {
                    "path": "service.py",
                    "change_type": "modified",
                    "hunks": [
                        {
                            "section_header": "def calculate_total(items):",
                            "source_start": 10,
                            "target_start": 10,
                            "lines": [
                                {
                                    "kind": "removed",
                                    "source_line": 11,
                                    "target_line": None,
                                    "content": "    return sum(items)",
                                },
                                {
                                    "kind": "added",
                                    "source_line": None,
                                    "target_line": 11,
                                    "content": "    return sum(items) * 0.9",
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        result = extract_changed_symbols(payload)

        self.assertEqual(1, len(result))
        self.assertEqual("calculate_total", result[0]["symbol"])
        self.assertEqual("function", result[0]["symbol_type"])
        self.assertEqual("modified", result[0]["change_type"])
        self.assertEqual(["hunk_header"], result[0]["detected_from"])

    def test_merges_removed_and_added_go_method_declaration(self):
        payload = {
            "files": [
                {
                    "path": "orders.go",
                    "change_type": "modified",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "removed",
                                    "source_line": 20,
                                    "target_line": None,
                                    "content": "func (s *Service) Reserve(order ID) error {",
                                },
                                {
                                    "kind": "added",
                                    "source_line": None,
                                    "target_line": 20,
                                    "content": "func (s *Service) Reserve(order Order) error {",
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        result = extract_changed_symbols(payload)

        self.assertEqual(1, len(result))
        self.assertEqual("Reserve", result[0]["symbol"])
        self.assertEqual("method", result[0]["symbol_type"])
        self.assertEqual("modified", result[0]["change_type"])
        self.assertEqual([20], result[0]["source_lines"])
        self.assertEqual([20], result[0]["target_lines"])

    def test_extracts_python_class_variable_and_sql_object(self):
        payload = {
            "files": [
                {
                    "path": "config.py",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "added",
                                    "target_line": 1,
                                    "content": "MAX_RETRIES = 4",
                                },
                                {
                                    "kind": "added",
                                    "target_line": 3,
                                    "content": "class RetryPolicy:",
                                },
                            ],
                        }
                    ],
                },
                {
                    "path": "schema.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "added",
                                    "target_line": 1,
                                    "content": "CREATE TABLE order_items (",
                                }
                            ],
                        }
                    ],
                },
            ]
        }

        result = extract_changed_symbols(payload)
        symbols = {
            (item["file"], item["symbol"], item["symbol_type"])
            for item in result
        }

        self.assertIn(("config.py", "MAX_RETRIES", "variable"), symbols)
        self.assertIn(("config.py", "RetryPolicy", "class"), symbols)
        self.assertIn(("schema.sql", "order_items", "table"), symbols)

    def test_ignores_supported_file_body_without_symbol_context(self):
        payload = {
            "files": [
                {
                    "path": "service.py",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "added",
                                    "target_line": 4,
                                    "content": "    total += item.price",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        self.assertEqual([], extract_changed_symbols(payload))


if __name__ == "__main__":
    unittest.main()
