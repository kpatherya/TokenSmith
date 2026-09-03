"""Observe whether flat TokenSmith retrieval returns both sides of multi-hop, cross-chunk questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import embedding_models_from_argument, materials_from_argument, read_only_search_guard, require_existing_path, source_label

from python_engine.tokensmith_engine import search_library


def source_matches(source: dict[str, Any], terms: list[str]) -> bool:
    searchable = " ".join(str(source.get(field) or "") for field in ("excerpt", "sectionHeader", "documentTitle", "title")).lower()
    return any(term.lower() in searchable for term in terms)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-hop fixtures through real search_library() and report whether both required evidence regions appear in top-k.")
    parser.add_argument("fixture", help="JSON list or object with a queries list. Each query needs query, prerequisiteTerms, and consequenceTerms.")
    parser.add_argument("user_data_path", help="Existing TokenSmith user-data directory.")
    parser.add_argument("--embedding-models-json", required=True, help="JSON list or file of embedding LocalModel specs used for the selected collections.")
    parser.add_argument("--materials-json", help="JSON list or file of CourseMaterial records. Defaults to ready active materials from the store.")
    parser.add_argument("--limit", type=int, default=4, help="Top-k retrieval limit (default: 4).")
    args = parser.parse_args()

    user_data_path = str(require_existing_path(args.user_data_path, "user_data_path"))
    fixture = json.loads(Path(args.fixture).expanduser().read_text(encoding="utf-8"))
    cases = fixture.get("queries", []) if isinstance(fixture, dict) else fixture
    if not isinstance(cases, list):
        raise ValueError("The fixture must be a list or an object containing a queries list.")
    materials = materials_from_argument(user_data_path, args.materials_json)
    models = embedding_models_from_argument(args.embedding_models_json)
    both_hits = 0

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            continue
        query = str(case.get("query") or "")
        prerequisite_terms = [str(term) for term in case.get("prerequisiteTerms", [])]
        consequence_terms = [str(term) for term in case.get("consequenceTerms", [])]
        if not query or not prerequisite_terms or not consequence_terms:
            print(f"Case {index}: skipped; requires query, prerequisiteTerms, and consequenceTerms.")
            continue
        with read_only_search_guard():
            result = search_library({"query": query, "userDataPath": user_data_path, "materials": materials, "limit": max(1, args.limit), "embeddingModels": models})
        sources = result["sources"]
        prerequisite_hit = any(source_matches(source, prerequisite_terms) for source in sources)
        consequence_hit = any(source_matches(source, consequence_terms) for source in sources)
        complete = prerequisite_hit and consequence_hit
        both_hits += int(complete)
        print(f"\nCase {index}: {query}")
        print(f"Prerequisite terms {prerequisite_terms}: {'FOUND' if prerequisite_hit else 'MISSING'}")
        print(f"Consequence terms {consequence_terms}: {'FOUND' if consequence_hit else 'MISSING'}")
        print(f"Cross-chunk evidence in top-{args.limit}: {'YES' if complete else 'NO'}; reason={result.get('reason')!r}")
        for source_rank, source in enumerate(sources, start=1):
            print(f"  {source_rank}. score={source.get('score')} | {source_label(source)}")
            print(f"     {str(source.get('excerpt') or '')[:300]}")

    total = len([case for case in cases if isinstance(case, dict) and case.get("query")])
    print(f"\nSummary: {both_hits}/{total} cases returned both prerequisite and consequence evidence in the top-{args.limit} results.")


if __name__ == "__main__":
    main()