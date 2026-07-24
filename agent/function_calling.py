import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.config import (
    DEFAULT_MODEL,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
    DependencyError,
    get_bounded_int_env,
)
from agent.llm_client import call_model_with_retries, extract_response_text
from agent.repository_tools import (
    RepositoryToolError,
    compare_symbol,
    find_symbol_definitions,
    read_file_section,
    search_project_docs,
    search_symbol,
)


DEFAULT_MAX_TOOL_TURNS = get_bounded_int_env(
    "AI_REVIEW_MAX_TOOL_TURNS",
    4,
    minimum=1,
    maximum=10,
)
DEFAULT_MAX_TOOL_CALLS = get_bounded_int_env(
    "AI_REVIEW_MAX_TOOL_CALLS",
    20,
    minimum=1,
    maximum=100,
)
DEFAULT_MAX_SOURCE_FILES = get_bounded_int_env(
    "AI_REVIEW_MAX_SOURCE_FILES",
    30,
    minimum=1,
    maximum=200,
)
DEFAULT_MAX_TOOL_RESULT_CHARS = get_bounded_int_env(
    "AI_REVIEW_MAX_TOOL_RESULT_CHARS",
    80_000,
    minimum=1_000,
    maximum=500_000,
)
DEFAULT_MAX_CHANGED_SYMBOLS = get_bounded_int_env(
    "AI_REVIEW_MAX_CHANGED_SYMBOLS",
    50,
    minimum=1,
    maximum=500,
)
DEFAULT_MAX_FILE_SECTION_LINES = get_bounded_int_env(
    "AI_REVIEW_MAX_FILE_SECTION_LINES",
    1_000,
    minimum=1,
    maximum=5_000,
)


TOOL_DECLARATIONS = [
    {
        "name": "search_symbol",
        "description": (
            "Bir sembolun base veya head revision icindeki tum kaynak kod "
            "eslesmelerini bulur. Tanim ve kullanim noktalarini kesfetmek icin kullan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Aranacak fonksiyon, method, class, struct, degisken veya SQL nesnesi.",
                },
                "revision": {
                    "type": "string",
                    "enum": ["base", "head"],
                    "description": "PR oncesi base veya PR sonrasi head revision.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "En fazla 1-50 eslesme.",
                },
            },
            "required": ["symbol", "revision"],
        },
    },
    {
        "name": "find_symbol_definitions",
        "description": (
            "Bir sembolun base veya head revision icindeki olasi tanim satirlarini bulur."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "revision": {
                    "type": "string",
                    "enum": ["base", "head"],
                },
                "max_results": {
                    "type": "integer",
                    "description": "En fazla 1-20 tanim.",
                },
            },
            "required": ["symbol", "revision"],
        },
    },
    {
        "name": "find_symbol_references",
        "description": (
            "Bir sembolun tanim satirlari haric diger dosya ve satirlardaki kullanimlarini bulur."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "revision": {
                    "type": "string",
                    "enum": ["base", "head"],
                },
                "max_results": {
                    "type": "integer",
                    "description": "En fazla 1-50 referans.",
                },
            },
            "required": ["symbol", "revision"],
        },
    },
    {
        "name": "compare_symbol",
        "description": (
            "Bir sembolun base ve head tanimlarini, kullanimlarini ve sinirli kod bolumlerini birlikte getirir."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "context_lines": {
                    "type": "integer",
                    "description": "Tanim etrafinda 0-50 baglam satiri.",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "read_file_section",
        "description": (
            "Base veya head revision icindeki desteklenen bir dosyanin sinirli satir araligini okur."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "revision": {
                    "type": "string",
                    "enum": ["base", "head"],
                },
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["revision", "path", "start_line", "end_line"],
        },
    },
    {
        "name": "search_project_docs",
        "description": (
            "PR oncesindeki README ve Markdown belgelerinde bir is kavrami veya mimari terim arar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {
                    "type": "integer",
                    "description": "En fazla 1-30 dokuman eslesmesi.",
                },
            },
            "required": ["query"],
        },
    },
]


class FunctionCallingError(RuntimeError):
    pass


def _load_genai_types():
    try:
        from google.genai import types
    except ModuleNotFoundError as exc:
        raise DependencyError(
            "google-genai function calling tipleri yuklenemedi. "
            "`pip install -r requirements.txt` calistirin."
        ) from exc
    return types


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _collect_paths(value: Any) -> set[str]:
    paths: set[str] = set()

    if isinstance(value, dict):
        for key, item in value.items():
            if key == "path" and isinstance(item, str):
                paths.add(item)
            else:
                paths.update(_collect_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.update(_collect_paths(item))

    return paths


def _bounded_result(value: Any, max_chars: int) -> Any:
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) <= max_chars:
        return value
    return {
        "truncated": True,
        "result_preview": encoded[:max_chars],
        "message": "Tool sonucu baglam limiti nedeniyle kisaltildi.",
    }


@dataclass
class RepositoryToolRuntime:
    repo_root: str | Path
    base_sha: str
    head_sha: str
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    max_source_files: int = DEFAULT_MAX_SOURCE_FILES
    max_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    source_files: set[str] = field(default_factory=set)

    def _revision(self, alias: str) -> str:
        if alias == "base":
            return self.base_sha
        if alias == "head":
            return self.head_sha
        raise RepositoryToolError("revision yalnizca base veya head olabilir.")

    def _references(self, symbol: str, revision: str, max_results: int) -> dict[str, Any]:
        occurrences = search_symbol(
            self.repo_root,
            revision,
            symbol,
            max_results=max_results,
        )
        definitions = find_symbol_definitions(
            self.repo_root,
            revision,
            symbol,
            max_results=min(max_results, 20),
        )
        definition_keys = {
            (item.get("path"), item.get("line"))
            for item in definitions.get("definitions", [])
        }
        references = [
            item
            for item in occurrences.get("matches", [])
            if (item.get("path"), item.get("line")) not in definition_keys
        ]
        return {
            "revision": occurrences.get("revision"),
            "symbol": symbol,
            "references": references,
            "truncated": occurrences.get("truncated", False),
        }

    def _execute(self, name: str, args: dict[str, Any]) -> Any:
        if name == "search_symbol":
            return search_symbol(
                self.repo_root,
                self._revision(args.get("revision")),
                args.get("symbol"),
                max_results=_clamp_int(args.get("max_results"), 30, 1, 50),
            )
        if name == "find_symbol_definitions":
            return find_symbol_definitions(
                self.repo_root,
                self._revision(args.get("revision")),
                args.get("symbol"),
                max_results=_clamp_int(args.get("max_results"), 10, 1, 20),
            )
        if name == "find_symbol_references":
            return self._references(
                args.get("symbol"),
                self._revision(args.get("revision")),
                _clamp_int(args.get("max_results"), 30, 1, 50),
            )
        if name == "compare_symbol":
            return compare_symbol(
                self.repo_root,
                self.base_sha,
                self.head_sha,
                args.get("symbol"),
                context_lines=_clamp_int(args.get("context_lines"), 12, 0, 50),
            )
        if name == "read_file_section":
            start_line = _clamp_int(args.get("start_line"), 1, 1, 1_000_000)
            end_line = _clamp_int(
                args.get("end_line"),
                start_line + 80,
                start_line,
                start_line + DEFAULT_MAX_FILE_SECTION_LINES - 1,
            )
            return read_file_section(
                self.repo_root,
                self._revision(args.get("revision")),
                args.get("path"),
                start_line=start_line,
                end_line=end_line,
                max_lines=min(
                    DEFAULT_MAX_FILE_SECTION_LINES,
                    end_line - start_line + 1,
                ),
            )
        if name == "search_project_docs":
            return search_project_docs(
                self.repo_root,
                self.base_sha,
                args.get("query"),
                max_results=_clamp_int(args.get("max_results"), 20, 1, 30),
            )
        raise RepositoryToolError(f"Bilinmeyen repository tool: {name}")

    def execute(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        if len(self.tool_trace) >= self.max_tool_calls:
            raise FunctionCallingError("Repository tool cagrisi limiti asildi.")

        safe_args = dict(args or {})
        trace = {
            "name": name,
            "args": safe_args,
            "status": "failed",
        }

        try:
            result = self._execute(name, safe_args)
            result_paths = _collect_paths(result)
            new_sources = self.source_files | result_paths
            if len(new_sources) > self.max_source_files:
                raise FunctionCallingError(
                    "Repository kaynak dosyasi limiti asildi. Daha dar bir arama yapin."
                )
            self.source_files = new_sources
            trace["status"] = "completed"
            trace["source_files"] = sorted(result_paths)
            bounded = _bounded_result(result, self.max_result_chars)
            trace["result_truncated"] = bool(
                isinstance(bounded, dict) and bounded.get("truncated")
            )
            return {"ok": True, "result": bounded}
        except (RepositoryToolError, FunctionCallingError, TypeError, ValueError) as exc:
            trace["error"] = str(exc)
            return {"ok": False, "error": str(exc)}
        finally:
            self.tool_trace.append(trace)


def build_repository_impact_prompt(
    changed_symbols: list[dict[str, Any]],
    changed_paths: list[str],
    context_source_type: str,
    context_sources: list[str],
) -> str:
    payload = {
        "changed_symbols": changed_symbols[:DEFAULT_MAX_CHANGED_SYMBOLS],
        "changed_symbol_count": len(changed_symbols),
        "changed_symbols_truncated": len(changed_symbols) > DEFAULT_MAX_CHANGED_SYMBOLS,
        "changed_paths": changed_paths,
        "context_source_type": context_source_type,
        "context_sources": context_sources,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

    return f"""
Sen kidemli bir repository etki analizi ajanisin. Asagidaki PR sembollerinin
base ve head durumlarini repository tool'lariyla arastir.

Kurallar:
1. Degisen her anlamli sembol icin tanim ve kullanim noktalarini base ve head revisionlarda kontrol et.
2. Fonksiyon veya degiskenin baska dosyalardaki kullanimlarini kanit olmadan uydurma.
3. Gerekirse compare_symbol, find_symbol_references, read_file_section ve search_project_docs kullan.
4. README ve Markdown destekleyici baglamdir; kaynak kod teknik gercekliktir.
5. Yalnizca PR degisikliginin capraz dosya etkisini acikla.
6. Tool arastirmasi tamamlandiginda yalnizca gecerli JSON don.
7. Tum aciklama metinleri Turkce olsun.

Beklenen JSON semasi:
{{
  "summary": "Capraz dosya etki analizinin Turkce ozeti",
  "impact_analysis": [
    {{
      "symbol": "sembol_adi",
      "symbol_type": "function|method|class|struct|variable|table|query|unknown",
      "changed_file": "degisen/dosya.py",
      "change_type": "added|modified|deleted|renamed|behavior_changed",
      "definition_files": ["tanim/dosyasi.py"],
      "reference_files_base": ["eski/kullanim.py"],
      "reference_files_head": ["yeni/kullanim.py"],
      "impact": "Degisikligin diger dosyalara etkisi",
      "evidence": ["dosya.py:42"]
    }}
  ]
}}

PR sembol verisi:
```json
{payload_json}
```
"""


def _extract_function_calls(response: Any) -> list[Any]:
    if not response or not getattr(response, "candidates", None):
        return []

    content = getattr(response.candidates[0], "content", None)
    calls = []
    for part in getattr(content, "parts", None) or []:
        function_call = getattr(part, "function_call", None)
        if function_call:
            calls.append(function_call)
    return calls


def _build_function_response_part(
    types_module: Any,
    *,
    name: str,
    response: dict[str, Any],
    call_id: str | None = None,
):
    response_kwargs = {
        "name": name,
        "response": response,
    }
    if call_id:
        response_kwargs["id"] = call_id

    function_response_type = getattr(types_module, "FunctionResponse", None)
    if function_response_type is not None:
        try:
            function_response = function_response_type(**response_kwargs)
            return types_module.Part(function_response=function_response)
        except (TypeError, ValueError):
            pass

    return types_module.Part.from_function_response(
        name=name,
        response=response,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise TypeError("Model yaniti metin degil.")

    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(candidate[start : end + 1])

    if not isinstance(parsed, dict):
        raise TypeError("Model JSON nesnesi donmedi.")
    return parsed


def _normalize_impact_response(text: str) -> dict[str, Any]:
    try:
        parsed = _parse_json_object(text)
    except (json.JSONDecodeError, TypeError):
        return {
            "status": "failed",
            "summary": "Repository etki modeli gecerli JSON donmedi.",
            "impact_analysis": [],
            "errors": ["Repository etki modeli gecerli JSON donmedi."],
        }

    summary = parsed.get("summary")
    if not isinstance(summary, str):
        summary = "Repository etki analizi tamamlandi."

    impacts = parsed.get("impact_analysis", [])
    if not isinstance(impacts, list):
        impacts = []

    return {
        "status": "completed",
        "summary": summary,
        "impact_analysis": [item for item in impacts if isinstance(item, dict)],
        "errors": [],
    }


def _tool_config(types_module: Any, mode: str):
    return types_module.GenerateContentConfig(
        temperature=0,
        tools=[types_module.Tool(function_declarations=TOOL_DECLARATIONS)],
        tool_config=types_module.ToolConfig(
            function_calling_config=types_module.FunctionCallingConfig(
                mode=mode,
            )
        ),
        automatic_function_calling=types_module.AutomaticFunctionCallingConfig(
            disable=True,
        ),
    )


def _json_config(types_module: Any):
    return types_module.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
    )


def analyze_repository_impact(
    *,
    client: Any,
    repo_root: str | Path,
    base_sha: str,
    head_sha: str,
    changed_symbols: list[dict[str, Any]],
    changed_paths: list[str],
    context_source_type: str,
    context_sources: list[str],
    model: str = DEFAULT_MODEL,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    max_tool_turns: int = DEFAULT_MAX_TOOL_TURNS,
    runtime: RepositoryToolRuntime | None = None,
    types_module: Any | None = None,
) -> dict[str, Any]:
    if not changed_symbols:
        return {
            "status": "skipped",
            "summary": "Diff icinde repository sembol analizi gerektiren bildirim bulunamadi.",
            "impact_analysis": [],
            "errors": [],
            "tool_trace": [],
            "analysis_sources": [],
        }

    types_module = types_module or _load_genai_types()
    runtime = runtime or RepositoryToolRuntime(
        repo_root=repo_root,
        base_sha=base_sha,
        head_sha=head_sha,
    )
    prompt = build_repository_impact_prompt(
        changed_symbols,
        changed_paths,
        context_source_type,
        context_sources,
    )
    contents = [
        types_module.Content(
            role="user",
            parts=[types_module.Part(text=prompt)],
        )
    ]

    try:
        for turn_index in range(max_tool_turns):
            mode = "ANY" if turn_index == 0 else "AUTO"
            response = call_model_with_retries(
                client=client,
                prompt=None,
                contents=contents,
                config=_tool_config(types_module, mode),
                model=model,
                retries=retries,
                retry_delay=retry_delay,
            )
            function_calls = _extract_function_calls(response)

            if not function_calls:
                text = extract_response_text(response)
                normalized = _normalize_impact_response(text)
                normalized["tool_trace"] = runtime.tool_trace
                normalized["analysis_sources"] = sorted(runtime.source_files)
                return normalized

            model_content = response.candidates[0].content
            contents.append(model_content)
            response_parts = []

            for function_call in function_calls:
                name = getattr(function_call, "name", "")
                args = dict(getattr(function_call, "args", None) or {})
                result = runtime.execute(name, args)
                response_parts.append(
                    _build_function_response_part(
                        types_module,
                        name=name,
                        response=result,
                        call_id=getattr(function_call, "id", None),
                    )
                )

            contents.append(
                types_module.Content(
                    role="tool",
                    parts=response_parts,
                )
            )

        contents.append(
            types_module.Content(
                role="user",
                parts=[
                    types_module.Part(
                        text=(
                            "Tool turu limiti doldu. Simdi mevcut kanitlarla beklenen "
                            "JSON semasinda nihai etki analizini don."
                        )
                    )
                ],
            )
        )
        final_response = call_model_with_retries(
            client=client,
            prompt=None,
            contents=contents,
            config=_json_config(types_module),
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )
        normalized = _normalize_impact_response(
            extract_response_text(final_response)
        )
    except Exception as exc:
        normalized = {
            "status": "failed",
            "summary": f"Repository etki analizi tamamlanamadi: {exc}",
            "impact_analysis": [],
            "errors": [f"Repository etki analizi tamamlanamadi: {exc}"],
        }

    normalized["tool_trace"] = runtime.tool_trace
    normalized["analysis_sources"] = sorted(runtime.source_files)
    return normalized
