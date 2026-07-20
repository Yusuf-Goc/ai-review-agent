from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from agent.codebase_documenter import process_docs_scan_units
from agent.full_scan_planner import FullScanSlice, FullScanUnit


class FakeModels:
    def __init__(self):
        self.call_count = 0

    def generate_content(self, *, model, contents, config):
        self.call_count += 1
        return SimpleNamespace(
            text='{"files": []}',
        )


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


def make_unit(index: int) -> FullScanUnit:
    content = f"print({index})"

    return FullScanUnit(
        unit_id=f"full-scan-unit-{index}",
        kind="single_file",
        slices=[
            FullScanSlice(
                path=f"example_{index}.py",
                language="python",
                start_line=1,
                end_line=1,
                content=content,
                line_count=1,
                char_count=len(content),
                part_label="full-file",
            )
        ],
        total_lines=1,
        total_chars=len(content),
        risk_score=0,
    )


class DocsClientReuseTests(TestCase):
    @patch("agent.codebase_documenter._create_client")
    def test_process_reuses_one_client_for_all_units(
        self,
        create_client,
    ):
        fake_client = FakeClient()
        create_client.return_value = fake_client

        merged_files, failed_units = process_docs_scan_units(
            scan_units=[
                make_unit(1),
                make_unit(2),
            ],
            retries=0,
        )

        self.assertEqual({}, merged_files)
        self.assertEqual([], failed_units)

        self.assertEqual(
            1,
            create_client.call_count,
            "Gemini client worker başına yalnızca bir kez oluşturulmalı.",
        )
        self.assertEqual(
            2,
            fake_client.models.call_count,
            "Her unit için bağımsız model isteği gönderilmeli.",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
