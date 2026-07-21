import os
import sys
import unittest
from unittest.mock import patch

import cli


class CliPrReviewStatusTests(unittest.TestCase):
    def test_github_pr_posts_warning_then_fails_when_review_is_partial(self):
        review_result = {
            "review_status": "partial",
            "summary": "Bir batch tamamlanamadi.",
            "findings": [],
            "failed_batches": [
                {
                    "batch": 2,
                    "reason": "Model yaniti alinamadi.",
                }
            ],
        }

        with (
            patch.object(sys, "argv", ["cli.py", "--github-pr"]),
            patch.dict(
                os.environ,
                {
                    "BASE_SHA": "base-sha",
                    "HEAD_SHA": "head-sha",
                },
                clear=False,
            ),
            patch("cli.get_git_diff", return_value="diff content"),
            patch("cli.build_pr_file_context", return_value={}),
            patch(
                "cli.analyze_diff_in_batches",
                return_value=review_result,
            ),
            patch("cli.post_review_result_to_pr") as post_result,
            patch("builtins.print"),
        ):
            exit_code = cli.main()

        self.assertEqual(1, exit_code)
        post_result.assert_called_once_with(review_result)


if __name__ == "__main__":
    unittest.main()
