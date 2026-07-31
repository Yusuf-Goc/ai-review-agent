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


if __name__ == "__main__":
    unittest.main()
