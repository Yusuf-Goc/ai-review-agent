import subprocess


class GitDiffError(Exception):
    pass


def get_git_diff(base_ref: str, head_ref: str) -> str:
    """
    Iki git ref/commit arasindaki unified diff ciktisini dondurur.
    Ornek:
        get_git_diff("HEAD~1", "HEAD")
    """

    if not base_ref or not head_ref:
        raise GitDiffError("Base ve head ref bos olamaz.")

    command = [
        "git",
        "diff",
        "--unified=3",
        base_ref,
        head_ref,
        "--",
        "*.py",
        "*.sql",
        "*.go",
    ]

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise GitDiffError(
            f"git diff calistirilamadi:\n{result.stderr.strip()}"
        )

    if not result.stdout.strip():
        raise GitDiffError(
            "Bu iki ref arasinda incelenebilir .py, .sql veya .go degisikligi bulunamadi."
        )

    return result.stdout
