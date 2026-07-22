import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.function_calling import (
    DEFAULT_MAX_FILE_SECTION_LINES,
    DEFAULT_MAX_SOURCE_FILES,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_MAX_TOOL_RESULT_CHARS,
    RepositoryToolRuntime,
    _extract_function_calls,
    analyze_repository_impact,
)


class FakePart:
    def __init__(self, text=None, function_call=None, function_response=None):
        self.text = text
        self.function_call = function_call
        self.function_response = function_response

    @classmethod
    def from_function_response(cls, **kwargs):
        return cls(function_response=kwargs)


class FakeContent:
    def __init__(self, role, parts):
        self.role = role
        self.parts = parts


class FakeConfig:
    def __init__(self, **kwargs):
        self.values = kwargs


class FakeTypes:
    Part = FakePart
    Content = FakeContent
    GenerateContentConfig = FakeConfig
    Tool = FakeConfig
    ToolConfig = FakeConfig
    FunctionCallingConfig = FakeConfig
    AutomaticFunctionCallingConfig = FakeConfig


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def generate_content(self, *, model, contents, config):
        self.requests.append(
            {
                "model": model,
                "contents": contents,
                "config": config,
            }
        )
        return self.outcomes.pop(0)


class FakeClient:
    def __init__(self, outcomes):
        self.models = FakeModels(outcomes)


class FakeRuntime:
    def __init__(self):
        self.tool_trace = []
        self.source_files = set()
        self.calls = []

    def execute(self, name, args):
        self.calls.append((name, args))
        self.tool_trace.append(
            {
                "name": name,
                "args": args,
                "status": "completed",
            }
        )
        self.source_files.add("consumer.py")
        return {
            "ok": True,
            "result": {
                "symbol": args["symbol"],
                "references": [
                    {
                        "path": "consumer.py",
                        "line": 9,
                    }
                ],
            },
        }


def function_call_response(name="find_symbol_references"):
    call = SimpleNamespace(
        name=name,
        args={
            "symbol": "calculate_total",
            "revision": "head",
        },
        id="call-1",
    )
    content = FakeContent(
        role="model",
        parts=[FakePart(function_call=call)],
    )
    return SimpleNamespace(
        text=None,
        candidates=[SimpleNamespace(content=content)],
    )


def final_json_response():
    payload = {
        "summary": "Fonksiyonun diger dosya kullanimi incelendi.",
        "impact_analysis": [
            {
                "symbol": "calculate_total",
                "symbol_type": "function",
                "changed_file": "service.py",
                "change_type": "modified",
                "definition_files": ["service.py"],
                "reference_files_base": ["consumer.py"],
                "reference_files_head": ["consumer.py"],
                "impact": "consumer.py yeni hesaplama davranisindan etkilenir.",
                "evidence": ["consumer.py:9"],
            }
        ],
    }
    content = FakeContent(
        role="model",
        parts=[FakePart(text=json.dumps(payload))],
    )
    return SimpleNamespace(
        text=json.dumps(payload),
        candidates=[SimpleNamespace(content=content)],
    )


class FunctionCallingTests(unittest.TestCase):
    def test_extracts_function_calls_from_all_parts(self):
        response = function_call_response()
        calls = _extract_function_calls(response)

        self.assertEqual(1, len(calls))
        self.assertEqual("find_symbol_references", calls[0].name)

    def test_manual_loop_executes_tool_and_preserves_call_id(self):
        client = FakeClient(
            [
                function_call_response(),
                final_json_response(),
            ]
        )
        runtime = FakeRuntime()

        result = analyze_repository_impact(
            client=client,
            repo_root=".",
            base_sha="base",
            head_sha="head",
            changed_symbols=[
                {
                    "file": "service.py",
                    "symbol": "calculate_total",
                    "symbol_type": "function",
                    "change_type": "modified",
                }
            ],
            changed_paths=["service.py"],
            context_source_type="markdown",
            context_sources=["README.md"],
            runtime=runtime,
            types_module=FakeTypes,
            retries=0,
        )

        self.assertEqual("completed", result["status"])
        self.assertEqual(1, len(result["impact_analysis"]))
        self.assertEqual(
            [("find_symbol_references", {
                "symbol": "calculate_total",
                "revision": "head",
            })],
            runtime.calls,
        )
        self.assertEqual(["consumer.py"], result["analysis_sources"])

        response_content = client.models.requests[1]["contents"][-1]
        function_response = response_content.parts[0].function_response
        self.assertEqual("call-1", function_response["id"])
        self.assertEqual(
            "find_symbol_references",
            function_response["name"],
        )

    def test_accepts_json_inside_markdown_fence(self):
        fenced_payload = (
            "```json\n"
            + json.dumps({"summary": "Tamamlandi.", "impact_analysis": []})
            + "\n```"
        )
        response = SimpleNamespace(
            text=fenced_payload,
            candidates=[
                SimpleNamespace(
                    content=FakeContent(
                        role="model",
                        parts=[FakePart(text=fenced_payload)],
                    )
                )
            ],
        )
        client = FakeClient([response])

        result = analyze_repository_impact(
            client=client,
            repo_root=".",
            base_sha="base",
            head_sha="head",
            changed_symbols=[
                {
                    "file": "service.py",
                    "symbol": "calculate_total",
                    "symbol_type": "function",
                    "change_type": "modified",
                }
            ],
            changed_paths=["service.py"],
            context_source_type="none",
            context_sources=[],
            runtime=FakeRuntime(),
            types_module=FakeTypes,
            retries=0,
        )

        self.assertEqual("completed", result["status"])

    def test_invalid_final_json_marks_impact_failed(self):
        invalid = SimpleNamespace(
            text="not-json",
            candidates=[
                SimpleNamespace(
                    content=FakeContent(
                        role="model",
                        parts=[FakePart(text="not-json")],
                    )
                )
            ],
        )
        client = FakeClient([invalid])

        result = analyze_repository_impact(
            client=client,
            repo_root=".",
            base_sha="base",
            head_sha="head",
            changed_symbols=[
                {
                    "file": "service.py",
                    "symbol": "calculate_total",
                    "symbol_type": "function",
                    "change_type": "modified",
                }
            ],
            changed_paths=["service.py"],
            context_source_type="none",
            context_sources=[],
            runtime=FakeRuntime(),
            types_module=FakeTypes,
            retries=0,
        )

        self.assertEqual("failed", result["status"])
        self.assertTrue(result["errors"])

    def test_skips_model_when_no_changed_symbols(self):
        client = FakeClient([])

        result = analyze_repository_impact(
            client=client,
            repo_root=".",
            base_sha="base",
            head_sha="head",
            changed_symbols=[],
            changed_paths=[],
            context_source_type="none",
            context_sources=[],
            types_module=FakeTypes,
        )

        self.assertEqual("skipped", result["status"])
        self.assertEqual([], client.models.requests)


class RepositoryRuntimeTests(unittest.TestCase):
    def test_default_runtime_limits_allow_broader_repository_analysis(self):
        runtime = RepositoryToolRuntime(
            repo_root=".",
            base_sha="base",
            head_sha="head",
        )

        self.assertEqual(20, DEFAULT_MAX_TOOL_CALLS)
        self.assertEqual(30, DEFAULT_MAX_SOURCE_FILES)
        self.assertEqual(80_000, DEFAULT_MAX_TOOL_RESULT_CHARS)
        self.assertEqual(1_000, DEFAULT_MAX_FILE_SECTION_LINES)
        self.assertEqual(20, runtime.max_tool_calls)
        self.assertEqual(30, runtime.max_source_files)
        self.assertEqual(80_000, runtime.max_result_chars)

    @patch("agent.function_calling.read_file_section")
    def test_read_file_section_is_capped_at_one_thousand_lines(self, read_section):
        read_section.return_value = {"path": "service.py", "lines": []}
        runtime = RepositoryToolRuntime(
            repo_root=".",
            base_sha="base",
            head_sha="head",
        )

        runtime._execute(
            "read_file_section",
            {
                "revision": "head",
                "path": "service.py",
                "start_line": 50,
                "end_line": 50_000,
            },
        )

        read_section.assert_called_once_with(
            ".",
            "head",
            "service.py",
            start_line=50,
            end_line=1_049,
            max_lines=1_000,
        )

    def test_unknown_tool_returns_controlled_error(self):
        runtime = RepositoryToolRuntime(
            repo_root=".",
            base_sha="base",
            head_sha="head",
        )

        result = runtime.execute("delete_repository", {})

        self.assertFalse(result["ok"])
        self.assertIn("Bilinmeyen repository tool", result["error"])
        self.assertEqual("failed", runtime.tool_trace[0]["status"])


if __name__ == "__main__":
    unittest.main()
