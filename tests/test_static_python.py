import unittest

from agent.payload_builder import attach_static_findings, build_code_payload


class StaticPythonTests(unittest.TestCase):
    def test_static_python_checks_use_ast(self):
        payload = build_code_payload("def broken(:\n    pass", file_name="broken.py")
        attach_static_findings(payload)

        findings = payload["static_analysis_findings"]

        self.assertEqual(findings[0]["category"], "syntax_error")
        self.assertEqual(findings[0]["file"], "broken.py")

