"""Observe the exact context-bleed heuristic and carried-source priority used by TokenSmith."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from _common import source_label


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate_text(text: str, max_chars: int) -> str:
    compact = compact_text(text)
    return compact if len(compact) <= max_chars else f"{compact[:max(0, max_chars - 1)].strip()}\u2026"


def is_contextual_follow_up_prompt(prompt: str) -> bool:
    normalized = re.sub(r"[?.!]+$", "", compact_text(prompt).lower())
    if not normalized:
        return False
    if re.fullmatch(r"(?:be\s+)?more\s+specific", normalized):
        return True
    if re.fullmatch(r"(?:explain|elaborate|expand)(?:\s+(?:that|this|it|more))?", normalized):
        return True
    if re.fullmatch(r"(?:tell me more|go deeper|more details|give(?: me)? more details|be precise|be clearer)", normalized):
        return True
    if re.fullmatch(r"(?:why|how so|what do you mean)", normalized) or re.match(r"^what about\b", normalized):
        return True
    return len(normalized.split()) <= 6 and bool(re.search(r"\b(?:that|this|it|they|them|those|above|previous|same)\b", normalized))


def source_key(source: dict[str, Any]) -> str:
    chunk_id = source.get("chunkRowid") if source.get("chunkRowid") is not None else source.get("chunkId")
    return "|".join(str(part if part is not None else "") for part in [
        source.get("materialId"), source.get("documentId"), chunk_id,
        source.get("path"), source.get("pageStart"), source.get("pageEnd"), str(source.get("excerpt") or "")[:120],
    ])


def merge_chat_sources(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for source in [*primary, *secondary]:
        key = source_key(source)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
        if len(merged) >= limit:
            break
    return merged


def build_retrieval_context(question_a: str, answer_a: str, question_b: str, prior_sources: list[dict[str, Any]], carried_limit: int) -> tuple[str, list[dict[str, Any]], bool]:
    query = compact_text(question_b)
    contextual = is_contextual_follow_up_prompt(query)
    if not contextual:
        return query, [], False
    return "\n".join([
        f"Previous question: {compact_text(question_a)}",
        f"Previous answer: {truncate_text(answer_a, 900)}",
        f"Follow-up: {query}",
    ]), prior_sources[:max(0, carried_limit)], True


def main() -> None:
    parser = argparse.ArgumentParser(description="Port chat-context.ts to display B's retrieval query and source-priority behavior.")
    parser.add_argument("fixture", help="JSON fixture with questionA, answerA, questionB, priorSources, and retrievedSources.")
    parser.add_argument("--carried-source-limit", type=int, default=2, help="Maximum carried A sources (default: 2).")
    parser.add_argument("--max-sources", type=int, default=4, help="Final source budget after merge (default: 4).")
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).expanduser().read_text(encoding="utf-8"))
    question_a = str(fixture["questionA"])
    answer_a = str(fixture["answerA"])
    question_b = str(fixture["questionB"])
    prior_sources = [source for source in fixture.get("priorSources", []) if isinstance(source, dict)]
    retrieved_sources = [source for source in fixture.get("retrievedSources", []) if isinstance(source, dict)]
    query, carried, contextual = build_retrieval_context(question_a, answer_a, question_b, prior_sources, args.carried_source_limit)
    merged = merge_chat_sources(carried, retrieved_sources, max(1, args.max_sources))

    print(f"Question A: {question_a}\nQuestion B: {question_b}")
    print(f"B classified as contextual follow-up: {contextual}")
    print("\nExact retrieval query sent for B:\n" + query)
    print("\nCarried sources from A, placed before B results:")
    for source in carried:
        print(f"  - {source_label(source)}")
    print("\nFinal merge order:")
    for index, source in enumerate(merged, start=1):
        origin = "carried from A" if source in carried else "retrieved for B"
        print(f"  {index}. [{origin}] {source_label(source)}")


if __name__ == "__main__":
    main()