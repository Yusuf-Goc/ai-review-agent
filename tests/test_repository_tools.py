import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.repository_tools import (
    RepositoryToolError,
    _bigquery_reference_match,
    compare_symbol,
    find_bigquery_references,
    find_symbol_definitions,
    get_bigquery_file_definitions,
    read_file_section,
    search_project_docs,
    search_symbol,
)


class RepositoryToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        self._git("init")
        self._git("config", "user.email", "tests@example.com")
        self._git("config", "user.name", "Tests")

        (self.repo / "README.md").write_text(
            "# Price service\n\ncalculate_total computes the basket total.\n",
            encoding="utf-8",
        )
        (self.repo / "service.py").write_text(
            "def calculate_total(items):\n"
            "    return sum(items)\n",
            encoding="utf-8",
        )
        (self.repo / "consumer.py").write_text(
            "from service import calculate_total\n\n"
            "result = calculate_total([10, 20])\n",
            encoding="utf-8",
        )
        (self.repo / "schema.sql").write_text(
            "CREATE TABLE sales.customers (\n"
            "  id INT64 NOT NULL,\n"
            "  country STRING NOT NULL\n"
            ");\n",
            encoding="utf-8",
        )
        (self.repo / "active_customers.sql").write_text(
            "SELECT c.id, c.country\n"
            "FROM sales.customers AS c\n"
            "WHERE c.country = @country;\n",
            encoding="utf-8",
        )
        (self.repo / "supplier_country.sql").write_text(
            "SELECT s.country\n"
            "FROM procurement.suppliers AS s\n"
            "WHERE s.country = @country;\n",
            encoding="utf-8",
        )
        (self.repo / "unqualified_customers.sql").write_text(
            "SELECT c.country FROM customers AS c;\n",
            encoding="utf-8",
        )
        (self.repo / "country_noise.sql").write_text(
            "-- sales.customers.country is only a comment\n"
            "SELECT 'country' AS label;\n",
            encoding="utf-8",
        )
        (self.repo / "routines.sql").write_text(
            "CREATE OR REPLACE FUNCTION sales.calculate_country(value STRING)\n"
            "AS (UPPER(value));\n"
            "CREATE OR REPLACE PROCEDURE sales.refresh_customers()\n"
            "BEGIN\n"
            "  SELECT 1;\n"
            "END;\n"
            "CREATE OR REPLACE TABLE FUNCTION sales.customer_report(p STRING)\n"
            "AS (SELECT p AS country);\n",
            encoding="utf-8",
        )
        (self.repo / "routine_consumer.sql").write_text(
            "SELECT sales.calculate_country('TR');\n"
            "CALL sales.refresh_customers();\n"
            "SELECT * FROM sales.customer_report(@country);\n",
            encoding="utf-8",
        )
        (self.repo / "other_routine_consumer.sql").write_text(
            "SELECT procurement.calculate_country('TR');\n",
            encoding="utf-8",
        )
        (self.repo / "unqualified_routine.sql").write_text(
            "SELECT calculate_country('TR');\n",
            encoding="utf-8",
        )
        (self.repo / "routine_noise.sql").write_text(
            "-- sales.calculate_country(country)\n"
            "SELECT 'sales.calculate_country(country)' AS label;\n",
            encoding="utf-8",
        )
        self._git("add", ".")
        self._git("commit", "-m", "base")
        self.base = self._git("rev-parse", "HEAD").stdout.strip()

        (self.repo / "service.py").write_text(
            "def calculate_total(items):\n"
            "    subtotal = sum(items)\n"
            "    return subtotal * 0.9\n",
            encoding="utf-8",
        )
        self._git("add", "service.py")
        self._git("commit", "-m", "head")
        self.head = self._git("rev-parse", "HEAD").stdout.strip()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _git(self, *arguments):
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_search_symbol_finds_definition_and_references(self):
        result = search_symbol(
            self.repo,
            self.head,
            "calculate_total",
        )

        paths = {match["path"] for match in result["matches"]}
        self.assertEqual(
            {"service.py", "consumer.py"},
            paths,
        )
        self.assertFalse(result["truncated"])

    def test_find_symbol_definitions_filters_call_sites(self):
        result = find_symbol_definitions(
            self.repo,
            self.head,
            "calculate_total",
        )

        self.assertEqual(1, len(result["definitions"]))
        self.assertEqual("service.py", result["definitions"][0]["path"])
        self.assertEqual(1, result["definitions"][0]["line"])

    def test_read_file_section_is_revision_aware_and_bounded(self):
        base = read_file_section(
            self.repo,
            self.base,
            "service.py",
            start_line=1,
            end_line=10,
            max_lines=2,
        )
        head = read_file_section(
            self.repo,
            self.head,
            "service.py",
            start_line=1,
            end_line=10,
            max_lines=3,
        )

        self.assertEqual(2, len(base["lines"]))
        self.assertTrue(base["truncated"])
        self.assertEqual(
            "    return sum(items)",
            base["lines"][1]["content"],
        )
        self.assertEqual(
            "    return subtotal * 0.9",
            head["lines"][2]["content"],
        )

    def test_compare_symbol_returns_base_and_head_sections(self):
        result = compare_symbol(
            self.repo,
            self.base,
            self.head,
            "calculate_total",
            context_lines=3,
        )

        base_contents = [
            line["content"]
            for section in result["base"]["sections"]
            for line in section["lines"]
        ]
        head_contents = [
            line["content"]
            for section in result["head"]["sections"]
            for line in section["lines"]
        ]

        self.assertIn("    return sum(items)", base_contents)
        self.assertIn("    return subtotal * 0.9", head_contents)
        self.assertEqual(3, len(result["head"]["occurrences"]))

    def test_bigquery_table_references_use_dataset_and_alias_evidence(self):
        result = find_bigquery_references(
            self.repo,
            self.head,
            "sales.customers",
            symbol_type="table",
        )

        confirmed_paths = {item["path"] for item in result["references"]}
        possible_paths = {
            item["path"] for item in result["possible_references"]
        }

        self.assertEqual({"active_customers.sql"}, confirmed_paths)
        self.assertEqual({"unqualified_customers.sql"}, possible_paths)
        self.assertNotIn("supplier_country.sql", confirmed_paths | possible_paths)
        self.assertNotIn("country_noise.sql", confirmed_paths | possible_paths)

    def test_bigquery_column_references_ignore_same_named_other_tables(self):
        result = find_bigquery_references(
            self.repo,
            self.head,
            "sales.customers.country",
            symbol_type="column",
        )

        confirmed = result["references"]
        possible = result["possible_references"]

        self.assertEqual(
            {"active_customers.sql"},
            {item["path"] for item in confirmed},
        )
        self.assertTrue(
            all(item["resolved_object"] == "sales.customers" for item in confirmed)
        )
        self.assertEqual(
            {"unqualified_customers.sql"},
            {item["path"] for item in possible},
        )
        self.assertFalse(
            any(item["path"] == "supplier_country.sql" for item in confirmed + possible)
        )


    def test_bigquery_nested_field_does_not_match_top_level_column(self):
        candidate = {
            "project": None,
            "dataset": "sales",
            "object": "customers",
            "resolved_column": "address.country",
            "confidence": "confirmed",
        }

        self.assertIsNone(
            _bigquery_reference_match(
                symbol="sales.customers.country",
                symbol_type="column",
                candidate=candidate,
            )
        )
        self.assertEqual(
            "confirmed",
            _bigquery_reference_match(
                symbol="sales.customers.address.country",
                symbol_type="column",
                candidate=candidate,
            ),
        )

    def test_bigquery_routine_references_use_semantic_identity(self):
        result = find_bigquery_references(
            self.repo,
            self.head,
            "sales.calculate_country",
            symbol_type="function",
        )

        self.assertEqual(
            {"routine_consumer.sql"},
            {item["path"] for item in result["references"]},
        )
        self.assertEqual(
            {"unqualified_routine.sql"},
            {item["path"] for item in result["possible_references"]},
        )
        all_paths = {
            item["path"]
            for item in result["references"] + result["possible_references"]
        }
        self.assertNotIn("other_routine_consumer.sql", all_paths)
        self.assertNotIn("routine_noise.sql", all_paths)
        self.assertNotIn("routines.sql", all_paths)

    def test_bigquery_procedure_and_table_function_references_are_found(self):
        procedure = find_bigquery_references(
            self.repo,
            self.head,
            "sales.refresh_customers",
            symbol_type="function",
        )
        table_function = find_bigquery_references(
            self.repo,
            self.head,
            "sales.customer_report",
            symbol_type="function",
        )

        self.assertEqual(
            {"routine_consumer.sql"},
            {item["path"] for item in procedure["references"]},
        )
        self.assertEqual(
            {"routine_consumer.sql"},
            {item["path"] for item in table_function["references"]},
        )

    def test_reads_full_file_bigquery_owner_definitions(self):
        result = get_bigquery_file_definitions(
            self.repo,
            self.head,
            "routines.sql",
        )

        self.assertTrue(result["exists"])
        self.assertEqual(
            {
                "sales.calculate_country",
                "sales.refresh_customers",
                "sales.customer_report",
            },
            {
                item["qualified_name"]
                for item in result["definitions"]
            },
        )


    def test_bigquery_select_star_matches_column_contract_but_except_does_not(self):
        (self.repo / "wildcard.sql").write_text(
            "SELECT * FROM sales.customers;\n",
            encoding="utf-8",
        )
        (self.repo / "wildcard_except.sql").write_text(
            "SELECT * EXCEPT(country) FROM sales.customers;\n",
            encoding="utf-8",
        )
        (self.repo / "wildcard_replace.sql").write_text(
            "SELECT * REPLACE(UPPER(country) AS country) "
            "FROM sales.customers;\n",
            encoding="utf-8",
        )
        self._git("add", ".")
        self._git("commit", "-m", "add wildcard consumers")
        revision = self._git("rev-parse", "HEAD").stdout.strip()

        result = find_bigquery_references(
            self.repo,
            revision,
            "sales.customers.country",
            symbol_type="column",
        )
        by_path = {item["path"]: item for item in result["references"]}

        self.assertEqual(
            "column_contract",
            by_path["wildcard.sql"]["reference_type"],
        )
        self.assertNotIn("wildcard_except.sql", by_path)
        self.assertEqual("column", by_path["wildcard_replace.sql"]["reference_type"])

    def test_bigquery_wildcard_does_not_match_nested_struct_field(self):
        candidate = {
            "project": None,
            "dataset": "sales",
            "object": "customers",
            "resolved_column": "*",
            "reference_type": "column_contract",
            "excluded_columns": [],
            "replaced_columns": [],
            "confidence": "confirmed",
        }
        self.assertIsNone(
            _bigquery_reference_match(
                symbol="sales.customers.address.country",
                symbol_type="column",
                candidate=candidate,
            )
        )

    def test_bigquery_transitive_view_dependency_chain_is_returned(self):
        files = {
            "customer_view.sql": (
                "CREATE VIEW sales.customer_view AS "
                "SELECT * FROM sales.customers;\n"
            ),
            "customer_summary.sql": (
                "CREATE VIEW analytics.customer_summary AS "
                "SELECT * FROM sales.customer_view;\n"
            ),
            "customer_dashboard.sql": (
                "SELECT * FROM analytics.customer_summary;\n"
            ),
        }
        for name, content in files.items():
            (self.repo / name).write_text(content, encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-m", "add view dependency chain")
        revision = self._git("rev-parse", "HEAD").stdout.strip()

        result = find_bigquery_references(
            self.repo,
            revision,
            "sales.customers.country",
            symbol_type="column",
        )
        by_path = {item["path"]: item for item in result["references"]}

        self.assertEqual("direct", by_path["customer_view.sql"]["dependency_kind"])
        self.assertEqual(
            [
                "sales.customers.country",
                "sales.customer_view",
                "analytics.customer_summary",
            ],
            by_path["customer_summary.sql"]["dependency_path"],
        )
        self.assertEqual(1, by_path["customer_summary.sql"]["dependency_depth"])
        self.assertEqual(2, by_path["customer_dashboard.sql"]["dependency_depth"])
        self.assertEqual("transitive", by_path["customer_dashboard.sql"]["dependency_kind"])
        self.assertGreaterEqual(result["transitive_reference_count"], 2)

    def test_bigquery_transitive_routine_dependency_chain_is_returned(self):
        (self.repo / "country_label_view.sql").write_text(
            "CREATE VIEW sales.country_label_view AS "
            "SELECT sales.calculate_country('TR') AS label;\n",
            encoding="utf-8",
        )
        (self.repo / "country_label_dashboard.sql").write_text(
            "SELECT * FROM sales.country_label_view;\n",
            encoding="utf-8",
        )
        self._git("add", ".")
        self._git("commit", "-m", "add routine dependency chain")
        revision = self._git("rev-parse", "HEAD").stdout.strip()

        result = find_bigquery_references(
            self.repo,
            revision,
            "sales.calculate_country",
            symbol_type="function",
        )
        by_path = {item["path"]: item for item in result["references"]}

        self.assertEqual("direct", by_path["country_label_view.sql"]["dependency_kind"])
        self.assertEqual(
            "transitive",
            by_path["country_label_dashboard.sql"]["dependency_kind"],
        )
        self.assertEqual(
            "sales.country_label_view",
            by_path["country_label_dashboard.sql"]["via_object"],
        )

    def test_search_project_docs_uses_markdown_only(self):
        result = search_project_docs(
            self.repo,
            self.base,
            "basket total",
        )

        self.assertEqual(1, len(result["matches"]))
        self.assertEqual("README.md", result["matches"][0]["path"])

    def test_rejects_path_traversal_and_unsupported_files(self):
        with self.assertRaises(RepositoryToolError):
            read_file_section(
                self.repo,
                self.head,
                "../secret.py",
            )

        with self.assertRaises(RepositoryToolError):
            read_file_section(
                self.repo,
                self.head,
                "binary.exe",
            )

    def test_rejects_invalid_revision_and_unbounded_limit(self):
        with self.assertRaises(RepositoryToolError):
            search_symbol(self.repo, "--bad-ref", "calculate_total")

        with self.assertRaises(RepositoryToolError):
            search_symbol(
                self.repo,
                self.head,
                "calculate_total",
                max_results=1000,
            )


if __name__ == "__main__":
    unittest.main()
