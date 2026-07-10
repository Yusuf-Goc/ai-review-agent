import re
import shutil
import subprocess


def check_go(file_name, source_text, make_finding):
    gofmt_path = shutil.which("gofmt")
    if not gofmt_path:
        return []

    result = subprocess.run(
        [gofmt_path, "-e"],
        input=source_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return []

    match = re.search(r":(\d+):\d+:\s*(.+)", result.stderr)
    line_number = int(match.group(1)) if match else 1
    message = match.group(2).strip() if match else result.stderr.strip()

    return [
        make_finding(
            file_name,
            line_number,
            "critical",
            "syntax_error",
            f"Go syntax hatasi: {message}",
            "`gofmt` hatasinda belirtilen satirdaki Go sozdizimini duzeltin.",
        )
    ]

