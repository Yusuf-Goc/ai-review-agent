import unittest
from unittest.mock import patch

from agent import codebase_documenter


class DocsLlmIntegrationTests(unittest.TestCase):
    @patch("agent.codebase_documenter.call_model_with_retries")
    def test_docs_model_call_uses_shared_retry_logic(
        self,
        call_model_with_retries,
    ):
        client = object()
        expected_response = object()
        call_model_with_retries.return_value = expected_response

        response = codebase_documenter._call_model_json(
            prompt="documentation prompt",
            model="test-model",
            retries=3,
            retry_delay=7,
            client=client,
        )

        self.assertIs(expected_response, response)
        call_model_with_retries.assert_called_once_with(
            client=client,
            prompt="documentation prompt",
            model="test-model",
            retries=3,
            retry_delay=7,
        )


if __name__ == "__main__":
    unittest.main()
