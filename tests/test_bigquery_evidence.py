import unittest

from agent.bigquery_evidence import analyze_bigquery_sql


class BigQueryEvidenceTests(unittest.TestCase):
    def _references(self, sql):
        return analyze_bigquery_sql(sql, path="query.sql")["references"]

    def test_resolves_alias_column_to_qualified_table(self):
        refs = self._references(
            """
            SELECT c.id, c.country
            FROM `vestel-data.sales.customers` AS c
            WHERE c.country = @country;
            """
        )
        country_refs = [r for r in refs if r["raw_reference"] == "c.country"]
        self.assertEqual(2, len(country_refs))
        self.assertTrue(all(r["confidence"] == "confirmed" for r in country_refs))
        self.assertTrue(all(r["resolved_object"] == "vestel-data.sales.customers" for r in country_refs))
        self.assertTrue(all(r["resolved_column"] == "country" for r in country_refs))

    def test_ignores_comment_string_and_named_parameter(self):
        refs = self._references(
            """
            -- country and sales.customers.country are noise
            SELECT 'country' AS label, r.country
            FROM reference.countries AS r
            WHERE r.country = @country;
            """
        )
        self.assertEqual(["r.country", "r.country"], [r["raw_reference"] for r in refs])
        self.assertTrue(all(r["resolved_object"] == "reference.countries" for r in refs))

    def test_distinguishes_same_named_columns_by_alias(self):
        refs = self._references(
            """
            SELECT c.country, s.country
            FROM sales.customers AS c
            JOIN procurement.suppliers AS s ON s.country = c.country;
            """
        )
        resolved = {(r["raw_reference"], r["resolved_object"]) for r in refs}
        self.assertIn(("c.country", "sales.customers"), resolved)
        self.assertIn(("s.country", "procurement.suppliers"), resolved)

    def test_marks_unqualified_table_source_as_possible(self):
        result = analyze_bigquery_sql(
            "SELECT c.country FROM customers AS c WHERE c.country = @country;",
            path="query.sql",
        )
        self.assertEqual("possible", result["sources"][0]["confidence"])
        self.assertTrue(all(r["confidence"] == "possible" for r in result["references"]))
        self.assertTrue(all(r["resolved_object"] == "customers" for r in result["references"]))

    def test_cte_reference_is_ignored_but_table_alias_is_confirmed(self):
        refs = self._references(
            """
            WITH country AS (
              SELECT CAST('TR' AS STRING) AS code
            )
            SELECT c.country, country.code
            FROM sales.customers AS c
            CROSS JOIN country
            WHERE c.country = country.code;
            """
        )
        cte_refs = [r for r in refs if r["raw_reference"] == "country.code"]
        customer_refs = [r for r in refs if r["raw_reference"] == "c.country"]
        self.assertTrue(cte_refs)
        self.assertTrue(all(r["confidence"] == "ignored" for r in cte_refs))
        self.assertTrue(customer_refs)
        self.assertTrue(all(r["confidence"] == "confirmed" for r in customer_refs))

    def test_extracts_bigquery_table_and_column_definitions(self):
        result = analyze_bigquery_sql(
            """
            CREATE TABLE IF NOT EXISTS `vestel-data.sales.customers` (
              id INT64 NOT NULL,
              full_name STRING NOT NULL,
              country STRING NOT NULL,
              CONSTRAINT customer_pk PRIMARY KEY(id) NOT ENFORCED
            );
            """,
            path="schema/customers.sql",
        )
        definitions = result["definitions"]
        table = next(item for item in definitions if item["object_type"] == "table")
        self.assertEqual("vestel-data.sales.customers", table["qualified_name"])
        columns = {
            item["qualified_name"]
            for item in definitions
            if item["object_type"] == "column"
        }
        self.assertEqual(
            {
                "vestel-data.sales.customers.id",
                "vestel-data.sales.customers.full_name",
                "vestel-data.sales.customers.country",
            },
            columns,
        )

    def test_extracts_alter_table_column_mutations(self):
        result = analyze_bigquery_sql(
            """
            ALTER TABLE sales.customers RENAME COLUMN country TO country_code;
            ALTER TABLE sales.customers ADD COLUMN region STRING;
            ALTER TABLE sales.customers DROP COLUMN status;
            """,
            path="schema/customers.sql",
        )
        mutations = result["mutations"]
        self.assertEqual(
            ["rename_column", "add_column", "drop_column"],
            [item["action"] for item in mutations],
        )
        self.assertEqual("country", mutations[0]["column"])
        self.assertEqual("country_code", mutations[0]["new_column"])

    def test_table_function_parameter_is_not_column_reference(self):
        result = analyze_bigquery_sql(
            """
            CREATE OR REPLACE TABLE FUNCTION sales.export_customer_country(
              p_country STRING
            )
            AS
            SELECT c.id, c.country
            FROM sales.customers AS c
            WHERE c.country = p_country;
            """,
            path="routines/export_customer_country.sql",
        )
        routine = next(item for item in result["definitions"] if item["object_type"] == "table_function")
        self.assertEqual("sales.export_customer_country", routine["qualified_name"])
        self.assertFalse(any(r["raw_reference"].startswith("p_country") for r in result["references"]))

    def test_unnest_source_is_possible(self):
        result = analyze_bigquery_sql(
            "SELECT item.country FROM sales.orders o CROSS JOIN UNNEST(o.items) AS item;",
            path="query.sql",
        )
        item_ref = next(r for r in result["references"] if r["raw_reference"] == "item.country")
        self.assertEqual("possible", item_ref["confidence"])


    def test_unqualified_column_resolves_to_single_qualified_source(self):
        refs = self._references(
            "SELECT country FROM sales.customers WHERE status = 'active';"
        )
        by_name = {r["raw_reference"]: r for r in refs}
        self.assertEqual("confirmed", by_name["country"]["confidence"])
        self.assertEqual("sales.customers", by_name["country"]["resolved_object"])
        self.assertEqual("country", by_name["country"]["resolved_column"])
        self.assertEqual("sales.customers", by_name["status"]["resolved_object"])

    def test_unqualified_column_with_multiple_sources_is_possible_for_each(self):
        refs = self._references(
            """
            SELECT country
            FROM sales.customers c
            JOIN procurement.suppliers s ON c.id = s.id;
            """
        )
        country_refs = [r for r in refs if r["raw_reference"] == "country"]
        self.assertEqual(
            {"sales.customers", "procurement.suppliers"},
            {r["resolved_object"] for r in country_refs},
        )
        self.assertTrue(all(r["confidence"] == "possible" for r in country_refs))

    def test_join_using_column_references_both_tables(self):
        refs = self._references(
            """
            SELECT c.id
            FROM sales.customers c
            JOIN procurement.suppliers s USING (country);
            """
        )
        using_refs = [r for r in refs if r["clause"] == "using"]
        self.assertEqual(
            {"sales.customers", "procurement.suppliers"},
            {r["resolved_object"] for r in using_refs},
        )
        self.assertTrue(all(r["resolved_column"] == "country" for r in using_refs))

    def test_nested_field_path_is_preserved(self):
        refs = self._references(
            "SELECT c.address.country FROM sales.customers c;"
        )
        ref = next(r for r in refs if r["raw_reference"] == "c.address.country")
        self.assertEqual(["address", "country"], ref["column_path"])
        self.assertEqual("address.country", ref["resolved_column"])

    def test_nested_subquery_alias_shadowing_uses_local_scope(self):
        refs = self._references(
            """
            SELECT c.country
            FROM sales.customers c
            WHERE EXISTS (
              SELECT 1
              FROM procurement.suppliers c
              WHERE c.country = 'TR'
            );
            """
        )
        country_refs = [r for r in refs if r["raw_reference"] == "c.country"]
        self.assertEqual(
            {"sales.customers", "procurement.suppliers"},
            {r["resolved_object"] for r in country_refs},
        )
        self.assertEqual(2, len({r["scope"] for r in country_refs}))

    def test_cte_body_and_outer_query_keep_separate_scopes(self):
        result = analyze_bigquery_sql(
            """
            WITH current_country AS (
              SELECT c.country
              FROM sales.customers c
            )
            SELECT c.country
            FROM procurement.suppliers c
            JOIN current_country cc ON cc.country = c.country;
            """,
            path="query.sql",
        )
        country_refs = [
            r for r in result["references"]
            if r["raw_reference"] == "c.country"
        ]
        self.assertEqual(
            {"sales.customers", "procurement.suppliers"},
            {r["resolved_object"] for r in country_refs},
        )
        cte_ref = next(r for r in result["references"] if r["raw_reference"] == "cc.country")
        self.assertEqual("ignored", cte_ref["confidence"])


    def test_collects_qualified_scalar_function_and_procedure_calls(self):
        result = analyze_bigquery_sql(
            """
            SELECT sales.calculate_country(c.country)
            FROM sales.customers c;
            CALL sales.refresh_customers(@country);
            """,
            path="routine_consumer.sql",
        )
        by_name = {
            item["raw_reference"]: item
            for item in result["routine_references"]
        }
        self.assertEqual(
            "confirmed",
            by_name["sales.calculate_country"]["confidence"],
        )
        self.assertEqual(
            "function",
            by_name["sales.calculate_country"]["routine_kind"],
        )
        self.assertEqual(
            "procedure",
            by_name["sales.refresh_customers"]["routine_kind"],
        )

    def test_collects_table_function_source_as_routine_reference(self):
        result = analyze_bigquery_sql(
            "SELECT * FROM sales.customer_report(@country);",
            path="table_function_consumer.sql",
        )
        reference = next(
            item
            for item in result["routine_references"]
            if item["raw_reference"] == "sales.customer_report"
        )
        self.assertEqual("table_function", reference["routine_kind"])
        self.assertEqual("confirmed", reference["confidence"])

    def test_unqualified_udf_is_possible_but_builtin_is_ignored(self):
        result = analyze_bigquery_sql(
            "SELECT calculate_country(country), COUNT(*) "
            "FROM sales.customers;",
            path="routine_consumer.sql",
        )
        names = {
            item["raw_reference"]: item
            for item in result["routine_references"]
        }
        self.assertEqual("possible", names["calculate_country"]["confidence"])
        self.assertNotIn("COUNT", names)

    def test_routine_definition_name_is_not_reported_as_call(self):
        result = analyze_bigquery_sql(
            """
            CREATE OR REPLACE FUNCTION sales.calculate_country(value STRING)
            AS (UPPER(value));
            """,
            path="routine.sql",
        )
        self.assertEqual([], result["routine_references"])


if __name__ == "__main__":
    unittest.main()
