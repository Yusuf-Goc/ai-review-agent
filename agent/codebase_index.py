import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INDEX_SCHEMA_VERSION = "1.0"


def _empty_index() -> dict[str, Any]:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at": "",
        "files": {},
    }


def calculate_sha256_text(content: str) -> str:
    """Metin içeriği için deterministic SHA-256 değeri üretir."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def safe_summary_filename(path: str) -> str:
    """Repository yolunu güvenli ve deterministic bir JSON dosya adına çevirir."""
    normalized = path.replace("\\", "/").strip("/")
    basename = Path(normalized).name or "file"

    safe_basename = re.sub(r"[^A-Za-z0-9._-]+", "_", basename)
    safe_basename = safe_basename[:80] or "file"

    path_digest = hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()[:16]

    return f"{safe_basename}.{path_digest}.json"


def load_index(index_path: str) -> dict[str, Any]:
    """Index yoksa veya okunamıyorsa kontrollü boş index döndürür."""
    if not os.path.exists(index_path):
        return _empty_index()

    try:
        with open(index_path, "r", encoding="utf-8") as index_file:
            parsed = json.load(index_file)
    except (OSError, json.JSONDecodeError, TypeError):
        return _empty_index()

    if not isinstance(parsed, dict):
        return _empty_index()

    files = parsed.get("files")
    if not isinstance(files, dict):
        parsed["files"] = {}

    if not isinstance(parsed.get("schema_version"), str):
        parsed["schema_version"] = INDEX_SCHEMA_VERSION

    if not isinstance(parsed.get("generated_at"), str):
        parsed["generated_at"] = ""

    return parsed


def save_index(index: dict[str, Any], index_path: str) -> None:
    """Index'i geçici dosya üzerinden atomic biçimde kaydeder."""
    parent_directory = os.path.dirname(index_path)
    target_directory = parent_directory or "."

    if parent_directory:
        os.makedirs(parent_directory, exist_ok=True)

    index_to_save = dict(index)
    index_to_save.setdefault("schema_version", INDEX_SCHEMA_VERSION)
    index_to_save.setdefault("files", {})
    index_to_save["generated_at"] = datetime.now(timezone.utc).isoformat()

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_directory,
            prefix=".index-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name

            json.dump(
                index_to_save,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, index_path)
        temporary_path = None

    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def should_document_file(
    index: dict[str, Any],
    path: str,
    content: str,
) -> bool:
    """Yeni veya içeriği değişmiş dosyalar için True döndürür."""
    files = index.get("files", {})
    if not isinstance(files, dict):
        return True

    existing_entry = files.get(path)
    if not isinstance(existing_entry, dict):
        return True

    existing_hash = existing_entry.get("sha256")
    current_hash = calculate_sha256_text(content)

    return existing_hash != current_hash


def remove_deleted_files_from_index(
    index: dict[str, Any],
    current_paths: set[str],
) -> list[str]:
    """
    Tam repository envanterinde bulunmayan dosyaları index'ten kaldırır.

    current_paths parametresi yalnızca işlenen dosyaları değil,
    repository taramasında bulunan bütün desteklenen dosyaları içermelidir.
    """
    files = index.get("files")

    if not isinstance(files, dict):
        index["files"] = {}
        return []

    existing_paths = set(files)
    deleted_paths = sorted(existing_paths - current_paths)

    for path in deleted_paths:
        entry = files.pop(path, None)

        if not isinstance(entry, dict):
            continue

        summary_path = entry.get("summary_path")

        if not isinstance(summary_path, str) or not summary_path:
            continue

        try:
            if os.path.isfile(summary_path):
                os.remove(summary_path)
        except OSError:
            # Index kaydı kaldırılır; summary temizleme hatası ana akışı durdurmaz.
            continue

    return deleted_paths
