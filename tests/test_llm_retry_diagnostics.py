import io
import unittest
from contextlib import redirect_stderr

from agent.llm_client import (
    GEMINI_HTTP_TIMEOUT_MS,
    call_model_with_retries,
)


class TemporaryModelError(Exception):
    status_code = 503


class FailingModels:
    def __init__(self):
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        raise TemporaryModelError(
            "503 UNAVAILABLE: model is experiencing high demand"
        )


class FailingClient:
    def __init__(self):
        self.models = FailingModels()


class LlmRetryDiagnosticsTests(unittest.TestCase):
    def test_http_timeout_is_bounded(self):
        self.assertEqual(90_000, GEMINI_HTTP_TIMEOUT_MS)

    def test_retry_log_contains_error_details_and_call_id(self):
        client = FailingClient()
        stderr = io.StringIO()

        with (
            redirect_stderr(stderr),
            self.assertRaises(TemporaryModelError),
        ):
            call_model_with_retries(
                client,
                prompt="review this code",
                retries=1,
                retry_delay=0,
                sleep_func=lambda _seconds: None,
            )

        output = stderr.getvalue()

        self.assertEqual(2, client.models.calls)
        self.assertIn("call_id=", output)
        self.assertIn("attempt=1/2", output)
        self.assertIn("attempt=2/2", output)
        self.assertIn("error_type=TemporaryModelError", output)
        self.assertIn("status=503", output)
        self.assertIn("will_retry=true", output)
        self.assertIn("will_retry=false", output)
        self.assertIn("elapsed_seconds=", output)
        self.assertIn("high demand", output)


if __name__ == "__main__":
    unittest.main()
