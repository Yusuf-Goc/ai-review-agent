import json
import unittest

from agent.llm_client import call_model_with_retries, normalize_json_response
from agent.payload_builder import attach_static_findings, build_code_payload
from agent.reviewer import analyze_source_code


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.candidates = [object()]


class FakeModels:
    def __init__(self, response_text, failures_before_success=0):
        self.failures_before_success = failures_before_success
        self.last_call = None
        self.calls = 0
        self.response_text = response_text

    def generate_content(self, **kwargs):
        self.calls += 1
        self.last_call = kwargs
        if self.calls <= self.failures_before_success:
            raise RuntimeError("503 UNAVAILABLE. high demand")
        return FakeResponse(self.response_text)


class FakeClient:
    def __init__(self, response_payload, failures_before_success=0):
        self.models = FakeModels(json.dumps(response_payload), failures_before_success)


class PayloadBuilderTests(unittest.TestCase):
    def test_build_code_payload_supports_full_code_review(self):
        code = "SELECT * FROM users WHERE id = '" + "1" + "';"
        payload = build_code_payload(code, file_name="query.sql")

        self.assertEqual(payload["input_type"], "full_code")
        self.assertEqual(payload["files"][0]["language"], "sql")
        self.assertEqual(payload["files"][0]["hunks"][0]["lines"][0]["target_line"], 1)

    def test_analyze_source_code_uses_json_model_contract(self):
        fake_result = {
            "summary": "Risk bulundu.",
            "findings": [
                {
                    "file": "query.sql",
                    "line": 1,
                    "severity": "high",
                    "category": "security_risk",
                    "message": "String birlestirme SQL injection riski tasir.",
                    "suggestion": "Parametreli sorgu kullanin.",
                }
            ],
        }
        client = FakeClient(fake_result)

        result = analyze_source_code(
            "SELECT * FROM users WHERE id = '" + "1" + "';",
            file_name="query.sql",
            client=client,
            retry_delay=0,
        )

        self.assertEqual(result["findings"][0]["category"], "security_risk")
        self.assertEqual(client.models.last_call["config"]["response_mime_type"], "application/json")
        self.assertIn('"input_type": "full_code"', client.models.last_call["contents"])

    def test_invalid_model_json_is_kept_as_raw_response(self):
        result = normalize_json_response("not json")

        self.assertEqual(result["findings"], [])
        self.assertIn("raw_response", result)

    def test_transient_model_error_is_retried(self):
        fake_result = {
            "summary": "Retry sonrasi basarili.",
            "findings": [],
        }
        client = FakeClient(fake_result, failures_before_success=1)

        response = call_model_with_retries(
            client,
            "prompt",
            retries=2,
            retry_delay=0,
            sleep_func=lambda seconds: None,
        )

        self.assertEqual(response.text, json.dumps(fake_result))
        self.assertEqual(client.models.calls, 2)

    def test_local_findings_are_merged_with_model_result(self):
        code = "\n".join(
            [
                "public class Demo {",
                "    public void run() {",
                "        if(true);",
                "        System.out.println(\"always\")",
                "    }",
                "}",
            ]
        )
        client = FakeClient({"summary": "Model bulgu donmedi.", "findings": []})

        result = analyze_source_code(
            code,
            file_name="Demo.java",
            client=client,
            retry_delay=0,
        )

        self.assertTrue(any(finding["line"] == 3 for finding in result["findings"]))
        self.assertTrue(any(finding["line"] == 4 for finding in result["findings"]))

    def test_static_java_checks_find_syntax_before_model(self):
        code = "\n".join(
            [
                "public class StudentManagementSystem {",
                "    public void printInfo() {",
                "        System.out.println(\"hello\")",
                "    }",
                "}",
            ]
        )
        payload = build_code_payload(code, file_name="deneme1.java")
        attach_static_findings(payload)

        findings = payload["static_analysis_findings"]

        self.assertTrue(any(finding["line"] == 1 for finding in findings))
        self.assertTrue(any(finding["line"] == 3 for finding in findings))
        self.assertTrue(all(finding["source"] == "local_static_check" for finding in findings))

