import unittest

from agent import llm_client


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.call_count = 0

    def generate_content(self, *, model, contents, config):
        self.call_count += 1
        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.models = FakeModels(outcomes)


class LlmClientRetryTests(unittest.TestCase):
    def test_daily_quota_error_is_not_retried(self):
        daily_quota_error = RuntimeError(
            "429 RESOURCE_EXHAUSTED "
            "'quotaId': "
            "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', "
            "'retryDelay': '28s'"
        )

        client = FakeClient(
            [
                daily_quota_error,
                daily_quota_error,
                daily_quota_error,
                daily_quota_error,
            ]
        )
        sleep_calls = []

        with self.assertRaises(RuntimeError) as raised:
            llm_client.call_model_with_retries(
                client=client,
                prompt="test prompt",
                model="test-model",
                retries=3,
                retry_delay=2,
                sleep_func=sleep_calls.append,
            )

        self.assertEqual(
            1,
            client.models.call_count,
            "Günlük kota dolduğunda tekrar istek gönderilmemeli.",
        )
        self.assertEqual(
            [],
            sleep_calls,
            "Günlük kota hatasında bekleyip retry yapılmamalı.",
        )
        self.assertEqual(
            "ModelDailyQuotaExceededError",
            type(raised.exception).__name__,
        )

    def test_minute_rate_limit_uses_server_retry_delay(self):
        minute_quota_error = RuntimeError(
            "429 RESOURCE_EXHAUSTED "
            "'quotaId': "
            "'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', "
            "'retryDelay': '28s'"
        )
        expected_response = object()

        client = FakeClient(
            [
                minute_quota_error,
                expected_response,
            ]
        )
        sleep_calls = []

        response = llm_client.call_model_with_retries(
            client=client,
            prompt="test prompt",
            model="test-model",
            retries=1,
            retry_delay=2,
            sleep_func=sleep_calls.append,
        )

        self.assertIs(expected_response, response)
        self.assertEqual(2, client.models.call_count)
        self.assertEqual(
            [28.0],
            sleep_calls,
            "API retryDelay süresi exponential backoff yerine kullanılmalı.",
        )

    def test_service_error_keeps_exponential_backoff(self):
        service_error = RuntimeError("503 service unavailable")
        expected_response = object()

        client = FakeClient(
            [
                service_error,
                expected_response,
            ]
        )
        sleep_calls = []

        response = llm_client.call_model_with_retries(
            client=client,
            prompt="test prompt",
            model="test-model",
            retries=1,
            retry_delay=2,
            sleep_func=sleep_calls.append,
        )

        self.assertIs(expected_response, response)
        self.assertEqual([2], sleep_calls)


if __name__ == "__main__":
    unittest.main()
