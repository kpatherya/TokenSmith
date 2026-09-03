"""Observe latency, provenance, and cross-chunk retrieval behavior without calling chat."""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from _common import embedding_models_from_argument, materials_from_argument, read_only_search_guard, require_existing_path

from python_engine.tokensmith_engine import resolve_embedding_provider_for_key, search_library, starter_sources
from python_engine.tokensmith_store import (
    embedding_models_by_collection_ids,
    ensure_faiss,
    fetch_sources,
    get_chunks_by_rowids,
    normalize_matrix,
    vector_search,
)


def raw_candidates(
    user_data_path: str,
    active_ids: list[str],
    limit: int,
    model_specs: list[dict[str, Any]],
    query: str,
) -> tuple[list[tuple[int, float, str]], dict[str, int]]:
    """Mirror search_library's raw FAISS search before active-material filtering."""
    model_keys = embedding_models_by_collection_ids(user_data_path, active_ids)
    grouped_ids: dict[str, list[str]] = defaultdict(list)
    for material_id in active_ids:
        model_key = model_keys.get(str(material_id))
        if model_key:
            grouped_ids[model_key].append(str(material_id))

    candidates: list[tuple[int, float, str]] = []
    stats = {"requested": 0, "raw": 0, "survived": 0, "vector_search_returned": 0}
    for model_key, material_ids in grouped_ids.items():
        embed_text, reason = resolve_embedding_provider_for_key(model_key, model_specs)
        if embed_text is None:
            print(f"Skipping embedding model {model_key}: {reason}")
            continue
        index = ensure_faiss(user_data_path, model_key)
        if index is None:
            print(f"No FAISS index available for {model_key}.")
            continue

        requested = max(limit * 8, limit)
        query_embedding = normalize_matrix([embed_text(query)])
        distances, labels = index.search(query_embedding, requested)
        raw = [(int(rowid), float(score)) for rowid, score in zip(labels[0], distances[0]) if int(rowid) >= 0]
        allowed = {
            int(row["rowid"])
            for row in get_chunks_by_rowids(user_data_path, [rowid for rowid, _score in raw], material_ids)
        }
        candidates.extend((rowid, score, model_key) for rowid, score in raw if rowid in allowed)
        stats["vector_search_returned"] += len(vector_search(user_data_path, query_embedding[0], material_ids, limit, model_key))
        stats["requested"] += requested
        stats["raw"] += len(raw)
        stats["survived"] += sum(1 for rowid, _score in raw if rowid in allowed)

    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates, stats


def print_rows(user_data_path: str, candidates: list[tuple[int, float, str]], active_ids: list[str], limit: int) -> None:
    rows = fetch_sources(user_data_path, [(rowid, score) for rowid, score, _key in candidates], active_ids)
    by_rowid = {int(row["rowid"]): row for row in rows}
    print("\nFinal candidates after active-material filtering:")
    print("rank  chunk_id  score       pages       section                 path")
    print("----  --------  ----------  ----------  ----------------------  ----")
    for rank, (rowid, score, model_key) in enumerate(candidates[:limit], start=1):
        row = by_rowid.get(rowid, {})
        page_start = row.get("page_start")
        page_end = row.get("page_end")
        pages = f"{page_start}-{page_end}" if page_start and page_end and page_start != page_end else str(page_start or "-")
        print(
            f"{rank:>4}  {rowid:>8}  {score:>10.6f}  {pages:<10}  "
            f"{str(row.get('section_header') or '-'):22.22}  {row.get('path') or '-'}\n"
            f"      embedding model: {model_key}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Show TokenSmith's raw FAISS-to-source retrieval funnel without chat.")
    parser.add_argument("query", help="Question or search query to embed and retrieve.")
    parser.add_argument("user_data_path", help="Existing TokenSmith user-data directory containing tokensmith.sqlite.")
    parser.add_argument("--limit", type=int, default=4, help="Final top-k limit (default: 4).")
    parser.add_argument("--materials-json", help="JSON list or file of CourseMaterial records. Defaults to ready active materials from the store.")
    parser.add_argument("--embedding-models-json", required=True, help="JSON list or file of embedding LocalModel specs used for the selected collections.")
    parser.add_argument("--show-starter-sources", action="store_true", help="Also call starter_sources() to show its non-vector fallback samples.")
    args = parser.parse_args()

    user_data_path = str(require_existing_path(args.user_data_path, "user_data_path"))
    materials = materials_from_argument(user_data_path, args.materials_json)
    model_specs = embedding_models_from_argument(args.embedding_models_json)
    active_ids = [str(material["id"]) for material in materials if material.get("id") and material.get("status") == "ready" and material.get("isActive") is not False]
    if not active_ids:
        print("No ready, active materials were supplied or found.")
        return

    limit = max(1, args.limit)
    print(f"Query: {args.query}\nActive materials: {', '.join(active_ids)}")
    with read_only_search_guard():
        candidates, stats = raw_candidates(user_data_path, active_ids, limit, model_specs, args.query)
        result = search_library({"query": args.query, "userDataPath": user_data_path, "materials": materials, "limit": limit, "embeddingModels": model_specs})
    print(f"FAISS candidate request count: {stats['requested']} (limit * 8 per embedding index)")
    print(f"Raw FAISS labels returned: {stats['raw']}")
    print(f"Candidates surviving active-material filtering: {stats['survived']}")
    print(f"vector_search() returned before cross-model merge: {stats['vector_search_returned']}")
    print_rows(user_data_path, candidates, active_ids, limit)

    print(f"\nsearch_library() returned {len(result['sources'])} sources; reason={result.get('reason')!r}.")
    if args.show_starter_sources:
        starter = starter_sources({"userDataPath": user_data_path, "materials": materials, "limit": limit})
        print(f"starter_sources() returned {len(starter['sources'])} sources; reason={starter.get('reason')!r}.")


if __name__ == "__main__":
    main()