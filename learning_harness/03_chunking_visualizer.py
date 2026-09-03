"""Observe provenance and cross-chunk boundaries produced by TokenSmith PDF chunking."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _common import require_existing_path

from python_engine.tokensmith_cleaning import section_header_from_line
from python_engine.tokensmith_engine import chunk_pdf_pages, chunk_text, extract_pdf_pages_pdfium, section_headers_in_text


def boundary_note(previous: dict[str, Any] | None, current: dict[str, Any]) -> str:
    if previous is None:
        return "first chunk"
    previous_text = str(previous.get("text") or "").rstrip()
    current_text = str(current.get("text") or "").lstrip()
    if previous_text and current_text and previous_text[-1] not in ".!?" and current_text[0].islower():
        return "possible mid-sentence boundary"
    if current.get("sectionHeader") and current.get("sectionHeader") != previous.get("sectionHeader"):
        return "section transition"
    return "sentence-aware or paragraph boundary"


def annotated_text(chunks: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        sections.append(f"\n\n<<< CHUNK {index}: pages {chunk.get('pageStart')} - {chunk.get('pageEnd')} >>>\n{chunk.get('text', '')}")
    return "".join(sections).lstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize real TokenSmith PDF chunks, section headers, and possible boundary quality issues.")
    parser.add_argument("pdf_path", help="PDF to extract and chunk. The file is read but never modified.")
    parser.add_argument("--cleaning-profile", default="course", help="TokenSmith cleaning profile (default: course).")
    parser.add_argument("--annotated-output", help="Optional new text path for an annotated chunk display; the PDF and index remain read-only.")
    args = parser.parse_args()

    pdf_path = require_existing_path(args.pdf_path, "pdf_path")
    pages, page_count = extract_pdf_pages_pdfium(pdf_path, args.cleaning_profile)
    chunks = chunk_pdf_pages(pages)
    source_text = "\n\n".join(str(page.get("text") or "") for page in pages)
    print(f"PDF: {pdf_path}\nPages extracted: {page_count}\nChunks: {len(chunks)}\nChunk overlap: 0")
    print(f"Detected headers: {section_headers_in_text(source_text)}")
    print("\nindex  chars       pages     section                       boundary assessment")
    print("-----  ----------  --------  ----------------------------  -------------------")
    previous: dict[str, Any] | None = None
    cursor = 0
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text") or "")
        start = source_text.find(text, cursor)
        if start < 0:
            start = cursor
        end = start + len(text)
        cursor = end
        section = chunk.get("sectionHeader") or "-"
        inferred = section_header_from_line(text.splitlines()[0]) if text else None
        suffix = f"; first-line header={inferred}" if inferred and inferred != section else ""
        print(f"{index:>5}  {start:>5}-{end:<5}  {str(chunk.get('pageStart')):>3}-{str(chunk.get('pageEnd')):<3}  {str(section):28.28}  {boundary_note(previous, chunk)}{suffix}")
        print(text[:500] + ("..." if len(text) > 500 else ""))
        print("---")
        previous = chunk

    print(f"Generic chunk_text() would produce {len(chunk_text(source_text, page_count=page_count))} chunks from the same cleaned text.")
    if args.annotated_output:
        output_path = Path(args.annotated_output).expanduser()
        output_path.write_text(annotated_text(chunks), encoding="utf-8")
        print(f"Wrote annotated display to {output_path}")


if __name__ == "__main__":
    main()