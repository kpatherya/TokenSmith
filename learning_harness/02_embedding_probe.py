"""Observe latency and truncation across TokenSmith local, Ollama, and remote embedding calls."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Callable

from _common import json_argument

from python_engine.tokensmith_engine import (
    LLAMA_EMBEDDING_TEXT_LIMIT,
    OLLAMA_EMBEDDING_TEXT_LIMIT,
    REMOTE_EMBEDDING_TEXT_LIMIT,
    llama_embedding,
    normalize_text,
    ollama_embedding,
    remote_openai_embedding,
    resolve_embedding_provider,
)


def read_samples(args: argparse.Namespace) -> list[str]:
    samples = list(args.text or [])
    if args.samples_file:
        samples.extend(Path(args.samples_file).expanduser().read_text(encoding="utf-8").splitlines())
    return samples or ["short TokenSmith embedding sample", "word " * 2_100]


def backend_for_spec(spec: dict[str, Any]) -> tuple[str, int, Callable[[str], list[float]]]:
    engine = spec.get("engine")
    if engine == "ollama":
        return "ollama", OLLAMA_EMBEDDING_TEXT_LIMIT, lambda text: ollama_embedding(text, spec)
    if engine == "remote":
        return "remote-openai", REMOTE_EMBEDDING_TEXT_LIMIT, lambda text: remote_openai_embedding(text, spec)

    model_path = str(spec.get("embeddingPath") or spec.get("path") or "")
    key, provider, reason = resolve_embedding_provider(model_path)
    if provider is None:
        raise RuntimeError(reason or f"Could not resolve local provider {key}.")
    return "local-gguf", LLAMA_EMBEDDING_TEXT_LIMIT, lambda text: llama_embedding(text, model_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Time real TokenSmith embedding backends and show their text truncation limits.")
    parser.add_argument("--model-spec", action="append", required=True, help="JSON object or file path for a LocalModel embedding spec. Repeat for multiple backends.")
    parser.add_argument("--text", action="append", help="Text sample. Repeat for multiple samples; a >8,000-char default sample is used if omitted.")
    parser.add_argument("--samples-file", help="UTF-8 text file; each line is one additional sample.")
    args = parser.parse_args()

    samples = read_samples(args)
    print("backend       input_chars  sent_chars  latency_ms  dimensions  timeout_observation")
    print("------------  -----------  ----------  ----------  ----------  -------------------")
    for raw_spec in args.model_spec:
        spec = json_argument(raw_spec)
        if not isinstance(spec, dict):
            raise ValueError("Every --model-spec must describe one JSON object.")
        backend, limit, embed = backend_for_spec(spec)
        for sample in samples:
            normalized = normalize_text(sample)
            try:
                started = time.perf_counter()
                vector = embed(sample)
                latency_ms = (time.perf_counter() - started) * 1000
                observation = "approached 45s" if latency_ms >= 40_000 else "under 45s"
                print(f"{backend:12}  {len(sample):>11}  {len(normalized[:limit]):>10}  {latency_ms:>10.1f}  {len(vector):>10}  {observation}")
            except Exception as error:
                print(f"{backend:12}  {len(sample):>11}  {len(normalized[:limit]):>10}  {'ERROR':>10}  {'-':>10}  {error}")


if __name__ == "__main__":
    main()