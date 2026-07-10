import unittest

from agent.payload_builder import attach_static_findings, build_code_payload


class StaticSqlTests(unittest.TestCase):
    def test_static_sql_checks_find_unbalanced_quotes(self):
        payload = build_code_payload("SELECT * FROM users WHERE name = 'Ali;", file_name="query.sql")
        attach_static_findings(payload)

        findings = payload["static_analysis_findings"]

        self.assertTrue(any("tek tirnaklar" in finding["message"] for finding in findings))

    def test_static_sql_checks_find_trailing_comma_before_from(self):
        sql = "\n".join(
            [
                "SELECT",
                "    p.sku,",
                "    SUM(oi.quantity) AS units_sold,",
                "FROM products p;",
            ]
        )
        payload = build_code_payload(sql, file_name="query.sql")
        attach_static_findings(payload)

        findings = payload["static_analysis_findings"]

        self.assertTrue(any(finding["line"] == 3 for finding in findings))
