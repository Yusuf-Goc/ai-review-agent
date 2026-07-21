import unittest
from unittest.mock import patch

from agent.llm_client import create_gemini_client


class GeminiClientTimeoutTests(unittest.TestCase):
    @patch("agent.llm_client.get_api_key", return_value="test-api-key")
    @patch("google.genai.Client")
    def test_client_uses_five_minute_request_timeout(
        self,
        client_mock,
        _get_api_key_mock,
    ):
        result = create_gemini_client()

        client_mock.assert_called_once_with(
            api_key="test-api-key",
            http_options={"timeout": 300_000},
        )
        self.assertIs(result, client_mock.return_value)


if __name__ == "__main__":
    unittest.main()
