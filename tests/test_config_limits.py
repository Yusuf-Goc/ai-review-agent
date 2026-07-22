import os
import unittest
from unittest.mock import patch

from agent.config import get_bounded_int_env


class ConfigLimitTests(unittest.TestCase):
    def test_uses_default_for_missing_or_invalid_value(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(20, get_bounded_int_env(
                "AI_REVIEW_MAX_TOOL_CALLS",
                20,
                minimum=1,
                maximum=100,
            ))

        with patch.dict(
            os.environ,
            {"AI_REVIEW_MAX_TOOL_CALLS": "not-an-integer"},
            clear=True,
        ):
            self.assertEqual(20, get_bounded_int_env(
                "AI_REVIEW_MAX_TOOL_CALLS",
                20,
                minimum=1,
                maximum=100,
            ))

    def test_clamps_environment_value_to_safe_range(self):
        with patch.dict(
            os.environ,
            {"AI_REVIEW_MAX_SOURCE_FILES": "500"},
            clear=True,
        ):
            self.assertEqual(200, get_bounded_int_env(
                "AI_REVIEW_MAX_SOURCE_FILES",
                30,
                minimum=1,
                maximum=200,
            ))


if __name__ == "__main__":
    unittest.main()
