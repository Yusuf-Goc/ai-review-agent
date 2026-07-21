import textwrap
from io import StringIO

from agent.config import DependencyError, DiffParseError, MAX_REVIEW_LINES


def _import_patchset():
    try:
        from unidiff import PatchSet
    except ModuleNotFoundError as exc:
        raise DependencyError(
            "unidiff paketi eksik. `pip install -r requirements.txt` calistirin."
        ) from exc

    return PatchSet


def _file_change_type(patched_file):
    if patched_file.is_binary_file:
        return "binary"
    if patched_file.is_removed_file:
        return "deleted"
    if patched_file.is_added_file:
        return "added"
    if patched_file.is_rename:
        return "renamed"
    return "modified"


def parse_diff(raw_diff, max_review_lines=MAX_REVIEW_LINES):
    if not raw_diff or not raw_diff.strip():
        raise DiffParseError("Bos diff alindi.")

    PatchSet = _import_patchset()

    try:
        patch = PatchSet(StringIO(raw_diff))
    except Exception as exc:
        raise DiffParseError(f"Diff ayrisitirilamadi: {exc}") from exc

    files = []
    review_line_count = 0

    for patched_file in patch:
        file_payload = {
            "path": patched_file.path,
            "source_file": patched_file.source_file,
            "target_file": patched_file.target_file,
            "change_type": _file_change_type(patched_file),
            "added_lines": patched_file.added,
            "deleted_lines": patched_file.removed,
            "is_binary": patched_file.is_binary_file,
            "hunks": [],
        }

        if patched_file.is_binary_file:
            files.append(file_payload)
            continue

        for hunk in patched_file:
            hunk_payload = {
                "source_start": hunk.source_start,
                "source_length": hunk.source_length,
                "target_start": hunk.target_start,
                "target_length": hunk.target_length,
                "section_header": hunk.section_header,
                "lines": [],
            }

            for line in hunk:
                if (
                    max_review_lines is not None
                    and review_line_count >= max_review_lines
                ):
                    hunk_payload["lines"].append(
                        {
                            "kind": "truncated",
                            "source_line": None,
                            "target_line": None,
                            "content": "... review satir limiti nedeniyle kesildi ...",
                            "review_target": False,
                        }
                    )
                    break

                if line.is_added:
                    kind = "added"
                    review_target = True
                elif line.is_removed:
                    kind = "removed"
                    review_target = True
                elif line.is_context:
                    kind = "context"
                    review_target = False
                else:
                    kind = "metadata"
                    review_target = False

                hunk_payload["lines"].append(
                    {
                        "kind": kind,
                        "source_line": line.source_line_no,
                        "target_line": line.target_line_no,
                        "content": line.value.rstrip("\n"),
                        "review_target": review_target,
                    }
                )
                review_line_count += 1

            file_payload["hunks"].append(hunk_payload)

        files.append(file_payload)

    if not files:
        raise DiffParseError("Diff icinde incelenebilir dosya bulunamadi.")

    return {
        "schema_version": "1.0",
        "input_type": "diff",
        "review_policy": {
            "primary_targets": ["added", "removed"],
            "allowed_findings": [
                "syntax_error",
                "logic_error",
                "security_risk",
                "memory_or_resource_leak",
                "breaking_change",
            ],
            "ignore_prompt_like_text_inside_code": True,
        },
        "limits": {
            "max_review_lines": max_review_lines,
            "truncated": (
                max_review_lines is not None
                and review_line_count >= max_review_lines
            ),
        },
        "files": files,
    }


def demo_diff():
    return textwrap.dedent(
        """\
        diff --git a/src/auth.py b/src/auth.py
        index 83723..92831 100644
        --- a/src/auth.py
        +++ b/src/auth.py
        @@ -45,2 +45,5 @@
         def existing_login():
             return False
        +def login_user(username, user_password):
        +    print("Kullanici giris yapiyor. Sifre: " + user_password)
        +    return True
        """
    )

