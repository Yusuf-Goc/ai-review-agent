import unittest
from unittest.mock import call, patch

from agent.full_scan_planner import FullScanUnit
from agent.reviewer import process_full_scan_units


class FullScanProcessorTests(unittest.TestCase):
    @staticmethod
    def make_unit(unit_id: str) -> FullScanUnit:
        return FullScanUnit(
            unit_id=unit_id,
            kind="single_file",
            total_lines=100,
            total_chars=2_000,
            risk_score=1,
        )

    def test_processor_runs_units_and_deduplicates_findings(self):
        first_unit = self.make_unit("unit-001")
        second_unit = self.make_unit("unit-002")

        duplicate_finding = {
            "file": "src/example.py",
            "line": 10,
            "severity": "high",
            "category": "logic_error",
            "message": "Aynı bulgu",
            "suggestion": "Kontrol ekleyin.",
        }

        second_finding = {
            "file": "src/other.py",
            "line": 20,
            "severity": "medium",
            "category": "security_risk",
            "message": "İkinci bulgu",
            "suggestion": "Girdiyi doğrulayın.",
        }

        with (
            patch(
                "agent.reviewer._analyze_full_scan_unit",
                side_effect=[
                    {
                        "success": True,
                        "findings": [duplicate_finding],
                        "summary": "İlk unit tamamlandı.",
                    },
                    {
                        "success": True,
                        "findings": [
                            duplicate_finding,
                            second_finding,
                        ],
                        "summary": "İkinci unit tamamlandı.",
                    },
                ],
            ) as analyze_unit,
            patch("agent.reviewer.time.sleep") as sleep,
        ):
            result = process_full_scan_units(
                scan_units=[first_unit, second_unit],
                client="test-client",
                model="test-model",
                max_review_lines=500,
                retries=0,
                retry_delay=0,
            )

        analyze_unit.assert_has_calls(
            [
                call(
                    first_unit,
                    client="test-client",
                    model="test-model",
                    max_review_lines=500,
                    retries=0,
                    retry_delay=0,
                ),
                call(
                    second_unit,
                    client="test-client",
                    model="test-model",
                    max_review_lines=500,
                    retries=0,
                    retry_delay=0,
                ),
            ]
        )

        sleep.assert_not_called()

        self.assertEqual(
            result["findings"],
            [
                duplicate_finding,
                second_finding,
            ],
        )
        self.assertEqual(result["failed_units"], [])
        self.assertEqual(
            result["stats"],
            {
                "planned_units": 2,
                "first_pass_success": 2,
                "first_pass_failed": 0,
                "second_pass_success": 0,
                "second_pass_failed": 0,
                "fallback_units": 0,
                "fallback_pass_success": 0,
                "final_failed_units": 0,
                "total_successful_units": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
