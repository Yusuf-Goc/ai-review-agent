import unittest

from agent.symbol_analysis import detect_symbol, extract_changed_symbols


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

    def test_ignores_hunk_header_when_other_declarations_change(self):
        payload = {
            "files": [
                {
                    "path": "checkout.go",
                    "change_type": "modified",
                    "hunks": [
                        {
                            "section_header": (
                                "func AddCheckoutItem(session *CheckoutSession, "
                                "item CheckoutItem)"
                            ),
                            "source_start": 80,
                            "target_start": 80,
                            "lines": [
                                {
                                    "kind": "removed",
                                    "source_line": 84,
                                    "content": (
                                        "func NewCheckoutSession(id string, "
                                        "customerID string) CheckoutSession {"
                                    ),
                                },
                                {
                                    "kind": "added",
                                    "target_line": 84,
                                    "content": (
                                        "func NewCheckoutSession(id string, "
                                        "customerID string, locale string) "
                                        "CheckoutSession {"
                                    ),
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        result = extract_changed_symbols(payload)
        symbols = {item["symbol"] for item in result}

        self.assertEqual({"NewCheckoutSession"}, symbols)
        self.assertNotIn("AddCheckoutItem", symbols)

    def test_ignores_comment_only_hunk_header(self):
        payload = {
            "files": [
                {
                    "path": "pricing.go",
                    "change_type": "modified",
                    "hunks": [
                        {
                            "section_header": (
                                "func ApplyFixedDiscount(subtotal int, "
                                "discount int) int"
                            ),
                            "source_start": 118,
                            "target_start": 118,
                            "lines": [
                                {
                                    "kind": "removed",
                                    "source_line": 121,
                                    "content": (
                                        "// pricing.go test filler line 121"
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        self.assertEqual([], extract_changed_symbols(payload))

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


    def test_extracts_bigquery_rename_column_symbols(self):
        payload = {
            "files": [
                {
                    "path": "schema/customers.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "added",
                                    "target_line": 10,
                                    "content": (
                                        "ALTER TABLE `vestel-data.sales.customers`"
                                    ),
                                },
                                {
                                    "kind": "added",
                                    "target_line": 11,
                                    "content": (
                                        "RENAME COLUMN country TO country_code;"
                                    ),
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        result = extract_changed_symbols(payload)
        by_symbol = {item["symbol"]: item for item in result}

        self.assertEqual(
            "modified",
            by_symbol["vestel-data.sales.customers"]["change_type"],
        )
        self.assertEqual(
            "deleted",
            by_symbol["vestel-data.sales.customers.country"]["change_type"],
        )
        self.assertEqual(
            "added",
            by_symbol["vestel-data.sales.customers.country_code"]["change_type"],
        )
        self.assertEqual(
            [11],
            by_symbol["vestel-data.sales.customers.country"]["target_lines"],
        )
        self.assertEqual(
            ["bigquery_evidence"],
            by_symbol["vestel-data.sales.customers.country"]["detected_from"],
        )

    def test_extracts_bigquery_add_and_drop_column_symbols(self):
        payload = {
            "files": [
                {
                    "path": "schema/add_loyalty.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "added",
                                    "target_line": 1,
                                    "content": (
                                        "ALTER TABLE sales.customers "
                                        "ADD COLUMN loyalty_tier STRING;"
                                    ),
                                }
                            ],
                        }
                    ],
                },
                {
                    "path": "schema/drop_country.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "added",
                                    "target_line": 1,
                                    "content": (
                                        "ALTER TABLE sales.customers "
                                        "DROP COLUMN country;"
                                    ),
                                }
                            ],
                        }
                    ],
                },
            ]
        }

        result = extract_changed_symbols(payload)
        changes = {
            (item["file"], item["symbol"]): item["change_type"]
            for item in result
        }

        self.assertEqual(
            "added",
            changes[(
                "schema/add_loyalty.sql",
                "sales.customers.loyalty_tier",
            )],
        )
        self.assertEqual(
            "deleted",
            changes[(
                "schema/drop_country.sql",
                "sales.customers.country",
            )],
        )
        self.assertEqual(
            "modified",
            changes[("schema/add_loyalty.sql", "sales.customers")],
        )
        self.assertEqual(
            "modified",
            changes[("schema/drop_country.sql", "sales.customers")],
        )

    def test_extracts_modified_bigquery_create_table_column(self):
        payload = {
            "files": [
                {
                    "path": "schema/customers.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "context",
                                    "source_line": 1,
                                    "target_line": 1,
                                    "content": "CREATE TABLE sales.customers (",
                                },
                                {
                                    "kind": "context",
                                    "source_line": 2,
                                    "target_line": 2,
                                    "content": "    id INT64,",
                                },
                                {
                                    "kind": "removed",
                                    "source_line": 3,
                                    "target_line": None,
                                    "content": "    country VARCHAR(2),",
                                },
                                {
                                    "kind": "added",
                                    "source_line": None,
                                    "target_line": 3,
                                    "content": "    country STRING,",
                                },
                                {
                                    "kind": "context",
                                    "source_line": 4,
                                    "target_line": 4,
                                    "content": "    status STRING",
                                },
                                {
                                    "kind": "context",
                                    "source_line": 5,
                                    "target_line": 5,
                                    "content": ");",
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        result = extract_changed_symbols(payload)
        by_symbol = {item["symbol"]: item for item in result}

        self.assertEqual(
            "modified",
            by_symbol["sales.customers.country"]["change_type"],
        )
        self.assertEqual(
            [3],
            by_symbol["sales.customers.country"]["source_lines"],
        )
        self.assertEqual(
            [3],
            by_symbol["sales.customers.country"]["target_lines"],
        )
        self.assertEqual(
            "modified",
            by_symbol["sales.customers"]["change_type"],
        )

    def test_detects_bigquery_table_function_without_changing_other_languages(self):
        table_function = detect_symbol(
            "routine.sql",
            "CREATE OR REPLACE TABLE FUNCTION sales.export_country(",
        )
        python_symbol = detect_symbol(
            "service.py",
            "def calculate_total(items):",
        )
        go_symbol = detect_symbol(
            "service.go",
            "func CalculateTotal(items []int) int {",
        )

        self.assertEqual(
            ("sales.export_country", "function"),
            table_function,
        )
        self.assertEqual(("calculate_total", "function"), python_symbol)
        self.assertEqual(("CalculateTotal", "function"), go_symbol)


    def test_uses_repository_owner_hint_for_body_only_view_change(self):
        payload = {
            "files": [
                {
                    "path": "views/customer_summary.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "removed",
                                    "source_line": 8,
                                    "content": "  COUNT(*) AS customer_count",
                                },
                                {
                                    "kind": "added",
                                    "target_line": 8,
                                    "content": "  COUNTIF(c.status = 'active') AS customer_count",
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        hints = {
            "views/customer_summary.sql": {
                "base": {
                    "definitions": [
                        {
                            "object_type": "view",
                            "qualified_name": "sales.customer_summary",
                        }
                    ]
                },
                "head": {
                    "definitions": [
                        {
                            "object_type": "view",
                            "qualified_name": "sales.customer_summary",
                        }
                    ]
                },
            }
        }

        result = extract_changed_symbols(payload, sql_owner_hints=hints)

        self.assertEqual(1, len(result))
        self.assertEqual("sales.customer_summary", result[0]["symbol"])
        self.assertEqual("table", result[0]["symbol_type"])
        self.assertEqual("modified", result[0]["change_type"])
        self.assertEqual(
            ["repository_definition"],
            result[0]["detected_from"],
        )

    def test_uses_repository_owner_hint_for_body_only_procedure_change(self):
        payload = {
            "files": [
                {
                    "path": "procedures/refresh_customers.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "removed",
                                    "source_line": 12,
                                    "content": "  WHERE status = 'new';",
                                },
                                {
                                    "kind": "added",
                                    "target_line": 12,
                                    "content": "  WHERE status IN ('new', 'retry');",
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        definition = {
            "object_type": "procedure",
            "qualified_name": "sales.refresh_customers",
        }
        hints = {
            "procedures/refresh_customers.sql": {
                "base": {"definitions": [definition]},
                "head": {"definitions": [definition]},
            }
        }

        result = extract_changed_symbols(payload, sql_owner_hints=hints)

        self.assertEqual(1, len(result))
        self.assertEqual("sales.refresh_customers", result[0]["symbol"])
        self.assertEqual("function", result[0]["symbol_type"])
        self.assertEqual("modified", result[0]["change_type"])

    def test_ambiguous_repository_owner_hint_is_not_guessed(self):
        payload = {
            "files": [
                {
                    "path": "routines/multiple.sql",
                    "hunks": [
                        {
                            "section_header": "",
                            "lines": [
                                {
                                    "kind": "added",
                                    "target_line": 20,
                                    "content": "  SELECT 2;",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        definitions = [
            {
                "object_type": "procedure",
                "qualified_name": "sales.first_proc",
            },
            {
                "object_type": "procedure",
                "qualified_name": "sales.second_proc",
            },
        ]
        hints = {
            "routines/multiple.sql": {
                "base": {"definitions": definitions},
                "head": {"definitions": definitions},
            }
        }

        self.assertEqual(
            [],
            extract_changed_symbols(payload, sql_owner_hints=hints),
        )


if __name__ == "__main__":
    unittest.main()
