import unittest

from agent.diff_parser import demo_diff, parse_diff


class DiffParserTests(unittest.TestCase):
    def test_parse_diff_keeps_context_and_added_lines(self):
        payload = parse_diff(demo_diff())
        lines = payload["files"][0]["hunks"][0]["lines"]

        self.assertEqual(payload["input_type"], "diff")
        self.assertEqual(lines[0]["kind"], "context")
        self.assertEqual(lines[2]["kind"], "added")
        self.assertEqual(lines[2]["target_line"], 47)

    def test_parse_diff_can_disable_global_line_truncation(self):
        raw_diff = """\
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,1 +1,5 @@
 old_line = True
+line_1 = 1
+line_2 = 2
+line_3 = 3
+line_4 = 4
"""

        payload = parse_diff(raw_diff, max_review_lines=None)
        lines = payload["files"][0]["hunks"][0]["lines"]

        self.assertEqual(5, len(lines))
        self.assertFalse(payload["limits"]["truncated"])
        self.assertNotIn(
            "truncated",
            {line["kind"] for line in lines},
        )
