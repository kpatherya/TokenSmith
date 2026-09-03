"""Shared read-only utilities for the TokenSmith learning harness."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

HARNESS_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = HARNESS_DIR.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def load_json(value: str) -> Any:
    """Load JSON from either a literal string or a file path."""
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(value)


def json_argument(value: str) -> Any:
    try:
        return load_json(value)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Expected JSON text or a JSON file path, got {value!r}: {error}") from error


def require_existing_path(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def ready_materials_from_store(user_data_path: str) -> list[dict[str, Any]]:
    from python_engine.tokensmith_store import list_materials

    return [
        material
        for material in list_materials(user_data_path)
        if material.get("status") == "ready" and material.get("isActive") is not False
    ]


def materials_from_argument(user_data_path: str, raw_materials: str | None) -> list[dict[str, Any]]:
    if raw_materials:
        value = json_argument(raw_materials)
        if not isinstance(value, list):
            raise ValueError("--materials-json must contain a JSON list.")
        return [item for item in value if isinstance(item, dict)]
    return ready_materials_from_store(user_data_path)


def embedding_models_from_argument(raw_models: str | None) -> list[dict[str, Any]]:
    if not raw_models:
        raise ValueError(
            "--embedding-models-json is required. Pass a JSON list or a JSON file path containing the LocalModel specs used to index the selected materials."
        )
    value = json_argument(raw_models)
    if not isinstance(value, list):
        raise ValueError("--embedding-models-json must contain a JSON list.")
    return [item for item in value if isinstance(item, dict)]


def source_label(source: dict[str, Any]) -> str:
    return " | ".join(
        str(value)
        for value in (
            source.get("chunkRowid") or source.get("chunkId") or "?",
            source.get("documentTitle") or source.get("title") or "Untitled",
            source.get("locator") or "unknown location",
            source.get("sectionHeader") or "no section",
        )
    )


@contextmanager
def read_only_search_guard() -> Iterator[None]:
    """Call real search_library() without allowing its migration or rebuild fallbacks."""
    from python_engine import tokensmith_engine as engine
    from python_engine import tokensmith_store as store

    original_init_db = engine.init_db
    original_rebuild_faiss = store.rebuild_faiss

    def blocked_rebuild(_user_data_path: str, embedding_model: str) -> None:
        raise RuntimeError(
            f"Read-only harness refused to rebuild the missing or stale FAISS index for {embedding_model}. Reindex outside learning_harness, then rerun this observation."
        )

    engine.init_db = lambda _user_data_path: None
    store.rebuild_faiss = blocked_rebuild
    try:
        yield
    finally:
        engine.init_db = original_init_db
        store.rebuild_faiss = original_rebuild_faiss