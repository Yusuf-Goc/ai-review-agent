import argparse
import json
import os
import sys
from pathlib import Path

from agent.codebase_documenter import generate_codebase_documentation
from agent.docs_commands import (
    merge_codebase_docs_bundle,
    prepare_codebase_docs_bundle,
)
from agent.docs_worker import run_docs_worker
from agent.config import DEFAULT_MODEL, DEFAULT_RETRIES, DEFAULT_RETRY_DELAY, MAX_REVIEW_LINES, DependencyError, DiffParseError
from agent.diff_parser import demo_diff, parse_diff
from agent.full_scan_commands import prepare_full_scan_bundle
from agent.full_scan_worker import run_full_scan_worker
from agent.git_diff import GitDiffError, get_git_diff
from agent.github_reporter import (
    GitHubReporterError,
    post_full_scan_result_as_issue,
    post_review_result_to_pr,
)
from agent.payload_builder import attach_static_findings, build_code_payload
from agent.pr_context import build_pr_file_context
from agent.report_formatter import format_review_report
from agent.reviewer import analyze_diff_in_batches, analyze_full_repository, analyze_source_code


def read_from_stdin():
    if sys.stdin.isatty():
        return None
    return sys.stdin.read()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Gerekli environment degiskeni bulunamadi: {name}")
    return value


def main():
    parser = argparse.ArgumentParser(description="Structured AI code review agent")
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--diff-file", help="Okunacak unified diff dosyasi")
    input_group.add_argument("--code-file", help="Commit diff olmadan incelenecek kod dosyasi")
    input_group.add_argument("--demo", action="store_true", help="Ornek diff ile calistir")
    input_group.add_argument(
        "--github-pr",
        action="store_true",
        help="GitHub Actions pull request modunda calistir",
    )
    input_group.add_argument(
        "--github-full-scan",
        action="store_true",
        help="GitHub Actions ortaminda tum repo kodlarini analiz eder ve issue olusturur",
    )
    input_group.add_argument(
        "--prepare-full-scan",
        action="store_true",
        help=(
            "Büyük repository full scan işlemi için "
            "matrix shard bundle'ı hazırlar"
        ),
    )
    input_group.add_argument(
        "--run-full-scan-shard",
        action="store_true",
        help=(
            "Tek bir full repository scan shard "
            "payload'ını işler"
        ),
    )
    input_group.add_argument(
        "--github-codebase-docs",
        action="store_true",
        help="GitHub Actions ortamında codebase dokümantasyonu üretir",
    )
    input_group.add_argument(
        "--prepare-codebase-docs",
        action="store_true",
        help=(
            "Büyük repository dokümantasyonu için "
            "matrix shard bundle'ı hazırlar"
        ),
    )
    input_group.add_argument(
        "--run-codebase-docs-shard",
        action="store_true",
        help=(
            "Tek bir codebase documentation shard "
            "payload'ını işler"
        ),
    )
    input_group.add_argument(
        "--merge-codebase-docs-shards",
        action="store_true",
        help=(
            "Documentation shard worker sonuçlarını "
            "birleştirip nihai raporları üretir"
        ),
    )
    parser.add_argument("--base", help="Karsilastirma icin base commit/ref")
    parser.add_argument("--head", help="Karsilastirma icin head commit/ref")
    parser.add_argument("--language", help="Kod dili. Verilmezse dosya uzantisindan tahmin edilir")
    parser.add_argument(
        "--dump-payload",
        action="store_true",
        help="Model cagirmadan parserin uretecegi JSON payload'u yazdir",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Kullanilacak Gemini modeli")
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help="Gecici Gemini hatalarinda tekrar deneme sayisi",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_DELAY,
        help="Ilk tekrar denemeden once beklenecek saniye",
    )
    parser.add_argument(
        "--full-scan-payload-file",
        help=(
            "Full scan worker tarafından okunacak "
            "shard payload JSON dosyası"
        ),
    )
    parser.add_argument(
        "--full-scan-result-file",
        help=(
            "Full scan worker sonucunun yazılacağı "
            "JSON dosyası"
        ),
    )
    parser.add_argument(
        "--full-scan-output-dir",
        default=".ai-review/full-scan-execution",
        help=(
            "Full scan shard manifest ve payload "
            "dosyalarının yazılacağı klasör"
        ),
    )
    parser.add_argument(
        "--docs-output-dir",
        default=".ai-review/docs-execution",
        help=(
            "Documentation shard manifest ve payload "
            "dosyalarının yazılacağı klasör"
        ),
    )
    parser.add_argument(
        "--docs-payload-file",
        help="İşlenecek documentation shard payload JSON dosyası",
    )
    parser.add_argument(
        "--docs-result-file",
        help="Worker sonucunun yazılacağı JSON dosyası",
    )
    parser.add_argument(
        "--docs-bundle-dir",
        default=".ai-review/docs-execution",
        help=(
            "Prepare aşamasında üretilen documentation "
            "bundle klasörü"
        ),
    )
    parser.add_argument(
        "--docs-results-dir",
        default=".ai-review/docs-results",
        help=(
            "İndirilen shard worker sonuçlarının "
            "bulunduğu ana klasör"
        ),
    )
    parser.add_argument(
        "--max-review-lines",
        type=int,
        default=MAX_REVIEW_LINES,
        help="Modele gonderilecek maksimum diff satiri",
    )
    args = parser.parse_args()

    if args.run_full_scan_shard:
        if not args.full_scan_payload_file:
            print(
                "Hata: --full-scan-payload-file "
                "zorunludur.",
                file=sys.stderr,
            )
            return 1

        if not args.full_scan_result_file:
            print(
                "Hata: --full-scan-result-file "
                "zorunludur.",
                file=sys.stderr,
            )
            return 1

        try:
            result = run_full_scan_worker(
                payload_path=args.full_scan_payload_file,
                output_path=args.full_scan_result_file,
                model=args.model,
                max_review_lines=args.max_review_lines,
                retries=args.retries,
                retry_delay=args.retry_delay,
            )

            print("[AI Full Repository Scan Worker]")
            print("-" * 50)
            print(
                f"Shard: {result.get('shard_id', 'unknown')}"
            )
            print(
                f"Analiz birimi: "
                f"{result.get('unit_count', 0)}"
            )
            print(
                f"Bulgu: "
                f"{len(result.get('findings', []))}"
            )
            print(
                f"Sonuç dosyası: "
                f"{args.full_scan_result_file}"
            )
            print("-" * 50)
            return 0

        except Exception as exc:
            print(
                "Hata: Full repository scan worker "
                f"başarısız oldu: {exc}",
                file=sys.stderr,
            )
            return 1

    if args.prepare_full_scan:
        try:
            prepared = prepare_full_scan_bundle(
                root_dir=".",
                output_dir=args.full_scan_output_dir,
                max_files=None,
            )

            manifest = prepared["manifest"]
            state = prepared["state"]

            print("[AI Full Repository Scan Prepare]")
            print("-" * 50)
            print(
                f"{state.get('repository_files', 0)} repository dosyası, "
                f"{state.get('selected_files', 0)} seçilen dosya, "
                f"{state.get('planned_units', 0)} analiz birimi ve "
                f"{manifest.get('shard_count', 0)} shard hazırlandı."
            )
            print(
                f"Bundle klasörü: "
                f"{args.full_scan_output_dir}"
            )
            print("-" * 50)
            return 0

        except Exception as exc:
            print(
                "Hata: Full repository scan shard "
                f"hazırlığı başarısız oldu: {exc}",
                file=sys.stderr,
            )
            return 1

    if args.merge_codebase_docs_shards:
        results_directory = Path(args.docs_results_dir)

        if not results_directory.is_dir():
            print(
                "Hata: Documentation worker sonuç klasörü "
                f"bulunamadı: {args.docs_results_dir}",
                file=sys.stderr,
            )
            return 2

        result_paths = sorted(
            str(result_path)
            for result_path in results_directory.rglob("*.json")
            if result_path.is_file()
        )

        try:
            summary = merge_codebase_docs_bundle(
                root_dir=".",
                bundle_dir=args.docs_bundle_dir,
                result_paths=result_paths,
                repository=os.getenv("GITHUB_REPOSITORY", ""),
                output_json=".ai-review/codebase-summary.json",
                output_markdown="docs/ai-codebase-report.md",
                max_files=None,
            )

            print("[AI Codebase Documentation Shard Merge]")
            print("-" * 50)
            print(
                f"{summary.get('stats', {}).get('documented_files', 0)} "
                "dosya dokümante edildi, "
                f"{summary.get('stats', {}).get('failed_units', 0)} "
                "analiz birimi başarısız oldu."
            )
            print("Çıktılar:")
            print("- .ai-review/codebase-summary.json")
            print("- docs/ai-codebase-report.md")
            print("-" * 50)
            return 0

        except Exception as exc:
            print(
                "Hata: Codebase documentation shard "
                f"sonuçları birleştirilemedi: {exc}",
                file=sys.stderr,
            )
            return 1

    if args.run_codebase_docs_shard:
        if not args.docs_payload_file or not args.docs_result_file:
            print(
                "Hata: --run-codebase-docs-shard için "
                "--docs-payload-file ve --docs-result-file gereklidir.",
                file=sys.stderr,
            )
            return 2

        try:
            result = run_docs_worker(
                payload_path=args.docs_payload_file,
                output_path=args.docs_result_file,
                model=args.model,
                retries=args.retries,
                retry_delay=args.retry_delay,
            )

            print("[AI Codebase Documentation Shard Worker]")
            print("-" * 50)
            print(
                f"{result.get('shard_id', '')}: "
                f"{result.get('unit_count', 0)} analiz birimi işlendi, "
                f"{len(result.get('files', []))} dosya sonucu üretildi, "
                f"{len(result.get('failed_units', []))} birim başarısız oldu."
            )
            print(f"Sonuç dosyası: {args.docs_result_file}")
            print("-" * 50)
            return 0

        except Exception as exc:
            print(
                "Hata: Codebase documentation shard "
                f"işlenemedi: {exc}",
                file=sys.stderr,
            )
            return 1

    if args.prepare_codebase_docs:
        try:
            prepared = prepare_codebase_docs_bundle(
                root_dir=".",
                output_dir=args.docs_output_dir,
                max_files=None,
            )

            manifest = prepared["manifest"]
            state = prepared["state"]

            print("[AI Codebase Documentation Prepare]")
            print("-" * 50)
            print(
                f"{state.get('repository_files', 0)} repository dosyası, "
                f"{state.get('selected_files', 0)} değişen/yeni dosya, "
                f"{state.get('planned_units', 0)} analiz birimi ve "
                f"{manifest.get('shard_count', 0)} shard hazırlandı."
            )
            print(f"Bundle klasörü: {args.docs_output_dir}")
            print("-" * 50)
            return 0

        except Exception as exc:
            print(
                "Hata: Codebase documentation shard "
                f"hazırlığı başarısız oldu: {exc}",
                file=sys.stderr,
            )
            return 1

    if args.github_codebase_docs:
        try:
            summary = generate_codebase_documentation(
                root_dir=".",
                repository=os.getenv("GITHUB_REPOSITORY", ""),
                model=args.model,
                retries=args.retries,
                retry_delay=args.retry_delay,
                output_json=".ai-review/codebase-summary.json",
                output_markdown="docs/ai-codebase-report.md",
            )

            print("[AI Codebase Documentation Sonuc Raporu]")
            print("-" * 50)
            print(
                f"{summary.get('stats', {}).get('documented_files', 0)} dosya dokümante edildi. "
                f"{summary.get('stats', {}).get('failed_units', 0)} analiz birimi başarısız oldu."
            )
            print("Çıktılar:")
            print("- .ai-review/codebase-summary.json")
            print("- docs/ai-codebase-report.md")
            print("-" * 50)
            return 0

        except Exception as exc:
            print(f"Hata: Codebase dokümantasyonu üretilemedi: {exc}", file=sys.stderr)
            return 1

    if args.github_full_scan:
        review_result = analyze_full_repository(
            root_dir=".",
            model=args.model,
            max_review_lines=args.max_review_lines,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )

        print("[AI Full Repository Review Sonuc Raporu]")
        print("-" * 50)
        print(format_review_report(review_result))
        print("-" * 50)

        try:
            post_full_scan_result_as_issue(review_result)
            print("GitHub issue basariyla olusturuldu.")
        except GitHubReporterError as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            return 1

        return 0

    if (args.base and not args.head) or (args.head and not args.base):
        print("Hata: --base ve --head birlikte kullanilmalidir.", file=sys.stderr)
        return 2

    manual_input_selected = args.demo or args.diff_file or args.code_file or args.github_pr
    git_diff_selected = args.base and args.head

    if manual_input_selected and git_diff_selected:
        print(
            "Hata: --base/--head; --demo, --diff-file veya --code-file ile birlikte kullanilamaz.",
            file=sys.stderr,
        )
        return 2

    input_mode = "diff"
    file_name = "stdin.diff"
    language = args.language
    main_branch_file_context = None

    if args.demo:
        input_text = demo_diff()
        file_name = "demo.diff"
    elif args.diff_file:
        with open(args.diff_file, "r", encoding="utf-8") as diff_file:
            input_text = diff_file.read()
        file_name = args.diff_file
    elif args.code_file:
        with open(args.code_file, "r", encoding="utf-8") as code_file:
            input_text = code_file.read()
        input_mode = "full_code"
        file_name = args.code_file
    elif args.github_pr:
        try:
            base_sha = require_env("BASE_SHA")
            head_sha = require_env("HEAD_SHA")

            input_text = get_git_diff(base_sha, head_sha)
            main_branch_file_context = build_pr_file_context(base_sha, head_sha)
            input_mode = "diff"
            file_name = f"{base_sha}..{head_sha}"
        except Exception as exc:
            print(f"Hata: GitHub PR diff alinamadi: {exc}", file=sys.stderr)
            return 1
    elif args.base and args.head:
        try:
            input_text = get_git_diff(args.base, args.head)
            input_mode = "diff"
            file_name = f"{args.base}..{args.head}"
        except GitDiffError as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            return 1
    else:
        input_text = read_from_stdin()
        if language:
            input_mode = "full_code"
            file_name = "stdin_code"

    if not input_text:
        print(
            "Girdi bulunamadi. `--demo`, `--diff-file path.diff`, `--code-file file.py` veya stdin kullanin.",
            file=sys.stderr,
        )
        return 2

    if args.dump_payload:
        try:
            if input_mode == "full_code":
                payload = build_code_payload(
                    input_text,
                    file_name=file_name,
                    language=language,
                    max_review_lines=args.max_review_lines,
                )
                attach_static_findings(payload)
            else:
                payload = parse_diff(input_text, max_review_lines=args.max_review_lines)
        except (DependencyError, DiffParseError) as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if input_mode == "full_code":
        review_result = analyze_source_code(
            input_text,
            file_name=file_name,
            language=language,
            model=args.model,
            max_review_lines=args.max_review_lines,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
    else:
        review_result = analyze_diff_in_batches(
            input_text,
            model=args.model,
            max_review_lines=args.max_review_lines,
            retries=args.retries,
            retry_delay=args.retry_delay,
            main_branch_file_context=main_branch_file_context,
        )
    print("[AI Code Reviewer Sonuc Raporu]")
    print("-" * 50)
    print(format_review_report(review_result))
    print("-" * 50)

    if args.github_pr:
        try:
            post_review_result_to_pr(review_result)
            print("GitHub PR yorumu basariyla gonderildi.")
        except GitHubReporterError as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
