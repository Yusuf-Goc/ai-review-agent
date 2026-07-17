import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.docs_commands import (
    merge_codebase_docs_bundle,
    prepare_codebase_docs_bundle,
)
from agent.docs_worker import run_docs_worker


class DocsPipelineSmokeTests(unittest.TestCase):
    @staticmethod
    def fake_process_docs_scan_units(
        *,
        scan_units,
        model,
        retries,
        retry_delay,
    ):
        del model, retries, retry_delay

        merged_files_by_path = {}

        for scan_unit in scan_units:
            for file_slice in scan_unit.slices:
                path = file_slice.path

                merged_files_by_path[path] = {
                    "path": path,
                    "language": file_slice.language,
                    "purpose": (
                        f"{path} için smoke-test dokümantasyonu"
                    ),
                    "main_components": [
                        {
                            "name": "generated_component",
                            "type": "module",
                            "description": (
                                "Smoke test tarafından üretilen bileşen"
                            ),
                            "important_logic": (
                                "Prepare, worker ve merge veri akışını "
                                "doğrular."
                            ),
                        }
                    ],
                    "important_variables": [],
                    "data_flow": (
                        "Kaynak dosya shard payload'ına, ardından "
                        "worker sonucuna aktarılır."
                    ),
                    "algorithm_flow": (
                        "Prepare, worker, merge ve finalize sırasıyla "
                        "çalışır."
                    ),
                    "external_dependencies": [],
                    "side_effects": [],
                    "risks_or_notes": [],
                }

        return merged_files_by_path, []

    @staticmethod
    def create_repository(root_dir: Path) -> list[str]:
        source_dir = root_dir / "src"
        source_dir.mkdir(parents=True)

        expected_paths = []

        # Her dosya 500 satırdır. Toplam 7.000 satır,
        # varsayılan 6.000 satırlık shard hedefini aşarak
        # gerçek birden fazla shard oluşturur.
        for file_index in range(14):
            relative_path = (
                f"src/module_{file_index:02d}.py"
            )
            source_path = root_dir / relative_path

            content = "".join(
                (
                    f"value_{file_index:02d}_{line_index:03d} "
                    f"= {line_index}\n"
                )
                for line_index in range(500)
            )

            source_path.write_text(
                content,
                encoding="utf-8",
            )
            expected_paths.append(relative_path)

        return expected_paths

    def test_prepare_workers_merge_and_finalize_real_repository(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            expected_paths = self.create_repository(root_dir)

            bundle_dir = (
                root_dir
                / ".ai-review"
                / "docs-execution"
            )
            results_dir = (
                root_dir
                / ".ai-review"
                / "docs-results"
            )

            prepared = prepare_codebase_docs_bundle(
                root_dir=str(root_dir),
                output_dir=str(bundle_dir),
                max_files=None,
            )

            manifest = prepared["manifest"]

            self.assertGreater(
                manifest["shard_count"],
                1,
            )
            self.assertEqual(
                manifest["unit_count"],
                14,
            )

            result_paths = []

            with patch(
                "agent.docs_worker.process_docs_scan_units",
                side_effect=self.fake_process_docs_scan_units,
            ) as processor:
                for matrix_entry in manifest["matrix"]["include"]:
                    shard_id = matrix_entry["shard_id"]
                    payload_path = (
                        bundle_dir
                        / matrix_entry["payload_file"]
                    )
                    result_path = (
                        results_dir
                        / f"{shard_id}.json"
                    )

                    run_docs_worker(
                        payload_path=str(payload_path),
                        output_path=str(result_path),
                        model="smoke-test-model",
                        retries=0,
                        retry_delay=0,
                    )

                    result_paths.append(str(result_path))

            self.assertEqual(
                processor.call_count,
                manifest["shard_count"],
            )

            output_json = (
                root_dir
                / ".ai-review"
                / "codebase-summary.json"
            )
            output_markdown = (
                root_dir
                / "docs"
                / "ai-codebase-report.md"
            )

            summary = merge_codebase_docs_bundle(
                root_dir=str(root_dir),
                bundle_dir=str(bundle_dir),
                result_paths=result_paths,
                repository="example/smoke-repository",
                output_json=str(output_json),
                output_markdown=str(output_markdown),
                max_files=None,
            )

            documented_paths = [
                file_doc["path"]
                for file_doc in summary["files"]
            ]

            self.assertEqual(
                documented_paths,
                expected_paths,
            )
            self.assertEqual(
                summary["repository"],
                "example/smoke-repository",
            )
            self.assertEqual(
                summary["failed_units"],
                [],
            )
            self.assertEqual(
                summary["stats"]["documented_files"],
                14,
            )
            self.assertEqual(
                summary["stats"]["failed_units"],
                0,
            )

            self.assertTrue(output_json.is_file())
            self.assertTrue(output_markdown.is_file())

            saved_summary = json.loads(
                output_json.read_text(encoding="utf-8")
            )
            self.assertEqual(saved_summary, summary)

            index_path = (
                root_dir
                / ".ai-review"
                / "index.json"
            )
            saved_index = json.loads(
                index_path.read_text(encoding="utf-8")
            )

            self.assertEqual(
                sorted(saved_index["files"]),
                expected_paths,
            )

            summary_files = list(
                (
                    root_dir
                    / ".ai-review"
                    / "summaries"
                ).rglob("*.json")
            )
            self.assertEqual(len(summary_files), 14)

            markdown = output_markdown.read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "# AI Codebase Report",
                markdown,
            )
            self.assertIn(
                "`src/module_00.py`",
                markdown,
            )
            self.assertIn(
                "`src/module_13.py`",
                markdown,
            )


if __name__ == "__main__":
    unittest.main()
