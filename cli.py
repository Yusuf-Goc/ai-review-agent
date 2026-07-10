import argparse
import json
import sys

from agent.config import DEFAULT_MODEL, DEFAULT_RETRIES, DEFAULT_RETRY_DELAY, MAX_REVIEW_LINES, DependencyError, DiffParseError
from agent.diff_parser import demo_diff, parse_diff
from agent.git_diff import GitDiffError, get_git_diff
from agent.payload_builder import attach_static_findings, build_code_payload
from agent.report_formatter import format_review_report
from agent.reviewer import analyze_diff_in_batches, analyze_source_code


def read_from_stdin():
    if sys.stdin.isatty():
        return None
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(description="Structured AI code review agent")
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--diff-file", help="Okunacak unified diff dosyasi")
    input_group.add_argument("--code-file", help="Commit diff olmadan incelenecek kod dosyasi")
    input_group.add_argument("--demo", action="store_true", help="Ornek diff ile calistir")
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
        "--max-review-lines",
        type=int,
        default=MAX_REVIEW_LINES,
        help="Modele gonderilecek maksimum diff satiri",
    )
    args = parser.parse_args()

    if (args.base and not args.head) or (args.head and not args.base):
        print("Hata: --base ve --head birlikte kullanilmalidir.", file=sys.stderr)
        return 2

    manual_input_selected = args.demo or args.diff_file or args.code_file
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
        )
    print("[AI Code Reviewer Sonuc Raporu]")
    print("-" * 50)
    print(format_review_report(review_result))
    print("-" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
