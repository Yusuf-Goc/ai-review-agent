from pathlib import Path
import unittest


class ReadmeDocsScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = Path("README.md").read_text(
            encoding="utf-8"
        )

    def test_readme_describes_documentation_workflows(self):
        self.assertIn(
            "## GitHub Actions ve Codebase Dokumantasyonu",
            self.readme,
        )
        self.assertIn(
            ".github/workflows/docs.yml",
            self.readme,
        )
        self.assertIn(
            ".github/workflows/review.yml",
            self.readme,
        )

    def test_readme_describes_small_and_large_repository_paths(self):
        self.assertIn(
            "Kucuk repository",
            self.readme,
        )
        self.assertIn(
            "Buyuk repository",
            self.readme,
        )
        self.assertIn(
            "prepare -> matrix workers -> merge",
            self.readme,
        )
        self.assertIn(
            "max-parallel: 8",
            self.readme,
        )

    def test_readme_lists_generated_documentation_files(self):
        for output_path in [
            ".ai-review/index.json",
            ".ai-review/summaries/",
            ".ai-review/codebase-summary.json",
            "docs/ai-codebase-report.md",
        ]:
            with self.subTest(output_path=output_path):
                self.assertIn(output_path, self.readme)

    def test_readme_mentions_documentation_safety_checks(self):
        self.assertIn(
            "eksik shard",
            self.readme,
        )
        self.assertIn(
            "stale bundle",
            self.readme,
        )

    def test_readme_no_longer_claims_integrations_are_missing(self):
        self.assertNotIn(
            (
                "Su anki surum GitHub/GitLab entegrasyonu "
                "yerine agent cekirdegine odaklanir"
            ),
            self.readme,
        )


if __name__ == "__main__":
    unittest.main()
