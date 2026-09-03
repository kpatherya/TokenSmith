"""Observe provenance loss caused by TokenSmith's TypeScript answer-source cleanup logic."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any

from _common import json_argument, source_label

from python_engine.tokensmith_engine import source_from_sqlite_chunk

CITATION_LABEL_PATTERN = r"(?:source|excerpt|passage|context|citation|evidence|reference)"


def normalize_for_source_match(text: str) -> str:
    return " ".join("".join(character if character.isalnum() else " " for character in text.lower()).split())


def first_referenced_source_index(text: str, source_count: int) -> int | None:
    for match in re.finditer(rf"\b{CITATION_LABEL_PATTERN}\s+(\d+)\b", text, flags=re.IGNORECASE):
        index = int(match.group(1)) - 1
        if 0 <= index < source_count:
            return index
    return None


def first_quoted_context_source_index(text: str, sources: list[dict[str, Any]]) -> int | None:
    match = re.match(r'^\s*["\u201c]([^"\u201d]{40,1000})["\u201d]', text)
    quoted = normalize_for_source_match(match.group(1) if match else "")
    if not quoted:
        return None
    for index, source in enumerate(sources):
        excerpt = normalize_for_source_match(str(source.get("excerpt") or ""))
        if excerpt and (excerpt.find(quoted) >= 0 or quoted.find(excerpt) >= 0):
            return index
    return None


def strip_source_number_phrases(text: str) -> str:
    citation_prefix = rf"^\s*(?:according to|as (?:stated|noted|shown|reported) in|per|from)\s+(?:the\s+)?{CITATION_LABEL_PATTERN}\s+\d+\s*,?\s*"
    citation_subject = rf"^\s*(?:the\s+)?{CITATION_LABEL_PATTERN}\s+\d+\s+(?:states|says|notes|indicates|mentions|reports)\s+(?:that\s+)?"
    bracket_citation = rf"\s*[([](?:{CITATION_LABEL_PATTERN})\s+\d+[)\]]"
    inline_citation_prefix = rf"\b(?:according to|as (?:stated|noted|shown|reported) in|per|from)\s+(?:the\s+)?{CITATION_LABEL_PATTERN}\s+\d+\s*,?\s*"
    generic_prefix = r"^\s*(?:so,\s*)?(?:according to|as (?:stated|noted|shown|reported) in|from|based on)\s+(?:this|the)\s+(?:excerpt|context|source|text)\s*,?\s*"
    inline_generic_prefix = r"\b(?:so,\s*)?(?:according to|as (?:stated|noted|shown|reported) in|from|based on)\s+(?:this|the)\s+(?:excerpt|context|source|text)\s*,?\s*"
    quoted_preamble = r"^\s*[\"\u201c][^\"\u201d]{40,1000}[\"\u201d]\s*(?:so,\s*)?(?:according to|as (?:stated|noted|shown|reported) in|from|based on)\s+(?:this|the)\s+(?:excerpt|context|source|text)\s*,?\s*"
    leaked_instruction = r"\s*[^.!?]*(?:source numbers?|excerpt labels?|excerpts?\s+label(?:led|ed)|phrases like\s+[\"']?according to)[^.!?]*[.!?]"
    for pattern, flags in [
        (quoted_preamble, re.IGNORECASE), (citation_prefix, re.IGNORECASE), (citation_subject, re.IGNORECASE),
        (generic_prefix, re.IGNORECASE), (bracket_citation, re.IGNORECASE), (inline_citation_prefix, re.IGNORECASE),
        (inline_generic_prefix, re.IGNORECASE), (leaked_instruction, re.IGNORECASE),
    ]:
        text = re.sub(pattern, "", text, flags=flags)
    return re.sub(r"\s{2,}", " ", text).strip()


def answer_with_ordered_sources(text: str, sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    referenced = first_referenced_source_index(text, len(sources))
    if referenced is None:
        referenced = first_quoted_context_source_index(text, sources)
    ordered = sources if referenced is None else [sources[referenced], *sources[:referenced], *sources[referenced + 1:]]
    return strip_source_number_phrases(text), ordered


def main() -> None:
    parser = argparse.ArgumentParser(description="Port study-chat-format.ts cleanup and show provenance text removed from a synthetic answer.")
    parser.add_argument("--answer", default="According to Source 2, normalization removes duplicated data [Source 2]. According to page 14, it also reduces update anomalies.", help="Synthetic model answer to audit.")
    parser.add_argument("--sources-json", help="JSON list or file of ChatSource objects.")
    parser.add_argument("--sqlite-row-json", help="Optional JSON row or file; converts it using real source_from_sqlite_chunk().")
    parser.add_argument("--query-tokens", default="normalization,data", help="Comma-separated query tokens for --sqlite-row-json.")
    args = parser.parse_args()

    sources = json_argument(args.sources_json) if args.sources_json else [
        {"title": "Source 1", "excerpt": "Primary keys uniquely identify rows."},
        {"title": "Source 2", "excerpt": "Normalization reduces duplicated data and update anomalies."},
    ]
    if not isinstance(sources, list):
        raise ValueError("--sources-json must contain a list.")
    sources = [source for source in sources if isinstance(source, dict)]
    if args.sqlite_row_json:
        row = json_argument(args.sqlite_row_json)
        if not isinstance(row, dict):
            raise ValueError("--sqlite-row-json must contain one source row object.")
        sources.append(source_from_sqlite_chunk(row, [token.strip() for token in args.query_tokens.split(",") if token.strip()]))

    cleaned, ordered = answer_with_ordered_sources(args.answer, sources)
    print("Before:\n" + args.answer + "\n\nAfter stripSourceNumberPhrases():\n" + cleaned)
    print("\nUnified diff:")
    print("\n".join(difflib.unified_diff(args.answer.splitlines(), cleaned.splitlines(), fromfile="model answer", tofile="returned answer", lineterm="")) or "(No text changed: this marker is not recognized by the TypeScript cleanup patterns.)")
    print("\nSource order returned by answerWithOrderedSources():")
    for index, source in enumerate(ordered, start=1):
        print(f"  {index}. {source_label(source)}")


if __name__ == "__main__":
    main()