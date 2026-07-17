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


def _normalize_loaded_index(parsed: Any) -> dict[str, Any] | None:
    """Okunan JSON verisini geçerli index yapısına dönüştürür."""
    if not isinstance(parsed, dict):
        return None

    normalized = dict(parsed)

    if not isinstance(normalized.get("files"), dict):
        normalized["files"] = {}

    if not isinstance(normalized.get("schema_version"), str):
        normalized["schema_version"] = INDEX_SCHEMA_VERSION

    if not isinstance(normalized.get("generated_at"), str):
        normalized["generated_at"] = ""

    return normalized


def _load_index_file(index_path: str) -> dict[str, Any] | None:
    """Tek bir index dosyasını kontrollü biçimde okumaya çalışır."""
    if not os.path.isfile(index_path):
        return None

    try:
        with open(index_path, "r", encoding="utf-8") as index_file:
            parsed = json.load(index_file)
    except (OSError, json.JSONDecodeError, TypeError):
        return None

    return _normalize_loaded_index(parsed)


def load_index(index_path: str) -> dict[str, Any]:
    """
    Ana index'i yükler.

    Ana dosya yoksa veya bozuksa `.bak` yedeği denenir.
    İki dosya da kullanılamıyorsa güvenli boş index döndürülür.
    """
    loaded = _load_index_file(index_path)

    if loaded is not None:
        return loaded

    backup_path = index_path + ".bak"
    recovered = _load_index_file(backup_path)

    if recovered is not None:
        return recovered

    return _empty_index()


def _atomic_write_json(
    payload: dict[str, Any],
    output_path: str,
    temporary_prefix: str,
) -> None:
    """JSON verisini aynı klasörde geçici dosya üzerinden atomic yazar."""
    parent_directory = os.path.dirname(output_path)
    target_directory = parent_directory or "."

    if parent_directory:
        os.makedirs(parent_directory, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_directory,
            prefix=temporary_prefix,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name

            json.dump(
                payload,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, output_path)
        temporary_path = None

    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def save_index(index: dict[str, Any], index_path: str) -> None:
    """
    Index'i atomic biçimde kaydeder.

    Mevcut ana index geçerliyse, yeni sürüm yazılmadan önce önceki
    sürüm `<index_path>.bak` yolunda korunur. Bozuk bir ana index,
    mevcut sağlam yedeğin üzerine yazılmaz.
    """
    index_to_save = dict(index)
    index_to_save.setdefault("schema_version", INDEX_SCHEMA_VERSION)
    index_to_save.setdefault("files", {})
    index_to_save["generated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    previous_index = _load_index_file(index_path)

    if previous_index is not None:
        _atomic_write_json(
            payload=previous_index,
            output_path=index_path + ".bak",
            temporary_prefix=".index-backup-",
        )

    _atomic_write_json(
        payload=index_to_save,
        output_path=index_path,
        temporary_prefix=".index-",
    )


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


def summary_path_for_file(
    path: str,
    summary_dir: str = ".ai-review/summaries",
) -> str:
    """Dosya için deterministic per-file summary yolunu oluşturur."""
    return os.path.join(
        summary_dir,
        safe_summary_filename(path),
    )


def save_file_summary(
    path: str,
    file_doc: dict[str, Any],
    summary_dir: str = ".ai-review/summaries",
) -> str:
    """Dosya dokümantasyonunu atomic biçimde ayrı JSON dosyasına kaydeder."""
    output_path = summary_path_for_file(
        path=path,
        summary_dir=summary_dir,
    )

    parent_directory = os.path.dirname(output_path)
    target_directory = parent_directory or "."

    if parent_directory:
        os.makedirs(parent_directory, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_directory,
            prefix=".summary-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name

            json.dump(
                file_doc,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, output_path)
        temporary_path = None

    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

    return output_path


def update_index_entry(
    index: dict[str, Any],
    path: str,
    language: str,
    content: str,
    line_count: int,
    summary_path: str,
) -> None:
    """Başarıyla dokümante edilen dosyanın index kaydını günceller."""
    files = index.get("files")

    if not isinstance(files, dict):
        files = {}
        index["files"] = files

    files[path] = {
        "sha256": calculate_sha256_text(content),
        "language": language,
        "line_count": line_count,
        "summary_path": summary_path,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_all_file_summaries(
    index: dict[str, Any],
) -> list[dict[str, Any]]:
    """Index içindeki geçerli per-file summary kayıtlarını yükler."""
    files = index.get("files")

    if not isinstance(files, dict):
        return []

    summaries: list[dict[str, Any]] = []

    for _, entry in sorted(files.items()):
        if not isinstance(entry, dict):
            continue

        summary_path = entry.get("summary_path")

        if not isinstance(summary_path, str) or not summary_path:
            continue

        if not os.path.isfile(summary_path):
            continue

        try:
            with open(summary_path, "r", encoding="utf-8") as summary_file:
                parsed = json.load(summary_file)
        except (OSError, json.JSONDecodeError, TypeError):
            continue

        if not isinstance(parsed, dict):
            continue

        summaries.append(parsed)

    return summaries
