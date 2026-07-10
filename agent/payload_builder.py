import os

from agent.config import DiffParseError, MAX_REVIEW_LINES
from agent.static_checks.c_style_check import check_c_style
from agent.static_checks.go_check import check_go
from agent.static_checks.python_check import check_python
from agent.static_checks.sql_check import check_sql


def infer_language(file_name, fallback="unknown"):
    extension_map = {
        ".py": "python",
        ".sql": "sql",
        ".c": "c",
        ".h": "c/c++",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".java": "java",
        ".js": "javascript",
        ".ts": "typescript",
        ".go": "go",
        ".rb": "ruby",
        ".php": "php",
        ".rs": "rust",
        ".kt": "kotlin",
        ".swift": "swift",
    }

    _, extension = os.path.splitext(file_name.lower())
    return extension_map.get(extension, fallback)


def build_code_payload(code_text, file_name="submitted_code", language=None, max_review_lines=MAX_REVIEW_LINES):
    if not code_text or not code_text.strip():
        raise DiffParseError("Bos kod alindi.")

    detected_language = language or infer_language(file_name)
    raw_lines = code_text.splitlines()
    truncated = len(raw_lines) > max_review_lines
    selected_lines = raw_lines[:max_review_lines]

    line_payload = [
        {
            "kind": "full_code",
            "source_line": None,
            "target_line": index,
            "content": content,
            "review_target": True,
        }
        for index, content in enumerate(selected_lines, start=1)
    ]

    if truncated:
        line_payload.append(
            {
                "kind": "truncated",
                "source_line": None,
                "target_line": None,
                "content": "... review satir limiti nedeniyle kesildi ...",
                "review_target": False,
            }
        )

    return {
        "schema_version": "1.0",
        "input_type": "full_code",
        "review_policy": {
            "primary_targets": ["full_code"],
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
            "truncated": truncated,
        },
        "files": [
            {
                "path": file_name,
                "language": detected_language,
                "source_file": None,
                "target_file": file_name,
                "change_type": "full_code_review",
                "added_lines": len(selected_lines),
                "deleted_lines": 0,
                "is_binary": False,
                "hunks": [
                    {
                        "source_start": None,
                        "source_length": None,
                        "target_start": 1,
                        "target_length": len(selected_lines),
                        "section_header": f"full {detected_language} code review",
                        "lines": line_payload,
                    }
                ],
            }
        ],
    }


def make_finding(file_name, line, severity, category, message, suggestion):
    return {
        "file": file_name,
        "line": line,
        "severity": severity,
        "category": category,
        "message": message,
        "suggestion": suggestion,
        "source": "local_static_check",
    }


def payload_source_text(file_payload):
    lines = []
    for hunk in file_payload.get("hunks", []):
        for line in hunk.get("lines", []):
            if line.get("kind") == "truncated":
                continue
            lines.append(line.get("content", ""))
    return "\n".join(lines)


def run_static_syntax_checks(review_payload):
    findings = []

    if review_payload.get("input_type") != "full_code":
        return findings

    for file_payload in review_payload.get("files", []):
        file_name = file_payload.get("path", "submitted_code")
        language = file_payload.get("language") or infer_language(file_name)
        source_text = payload_source_text(file_payload)

        if language == "python":
            findings.extend(check_python(file_name, source_text, make_finding))
        elif language in {"java", "c", "cpp", "csharp"}:
            findings.extend(check_c_style(file_name, language, source_text, make_finding))
        elif language == "go":
            findings.extend(check_go(file_name, source_text, make_finding))
        elif language == "sql":
            findings.extend(check_sql(file_name, source_text, make_finding))

    return findings


def attach_static_findings(review_payload):
    review_payload["static_analysis_findings"] = run_static_syntax_checks(review_payload)
    return review_payload

