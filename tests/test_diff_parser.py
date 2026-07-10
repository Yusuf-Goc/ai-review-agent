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

