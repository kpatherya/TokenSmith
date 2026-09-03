"""Observe latency across TokenSmith's Ollama embedding, retrieval, answer, and suggestion stages."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any

from _common import materials_from_argument, read_only_search_guard, require_existing_path

from python_engine.tokensmith_engine import OLLAMA_EMBEDDING_TEXT_LIMIT, normalize_text, search_library

DEFAULT_SYSTEM_MESSAGE = "You are a source-backed study assistant. Answer directly and say when the supplied sources are insufficient."
DEFAULT_FOLLOW_UP_PROMPT = "Return concise study follow-up questions only, as a JSON array."


def ollama_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/") or "http://127.0.0.1:11434"
    return normalized[:-4] if normalized.endswith("/api") else normalized


def post_json(endpoint: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach Ollama at {endpoint}: {error}. Start Ollama and retry; this harness does not mock model calls.") from error
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Ollama returned HTTP {error.code} from {endpoint}: {detail}") from error
    return result, (time.perf_counter() - started) * 1000


def source_context(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return ""
    entries = []
    for source in sources:
        collection = source.get("collectionName") or source.get("documentTitle") or source.get("title") or "Library"
        section = f"Section: {source['sectionHeader']}\n" if source.get("sectionHeader") else ""
        entries.append(f"Collection: {collection}\nPath: {source.get('path') or source.get('title') or ''}\n{section}Text: {source.get('excerpt') or ''}")
    return "\n".join([
        "Use the context below only when it is relevant to the question.",
        "Answer directly. Do not quote the context before answering. Do not mention context labels, source labels, excerpt labels, locators, or page numbers.",
        "If the context does not contain the answer, say that plainly.",
        "",
        "### Context:",
        *entries,
    ])


def tokens_per_second(response: dict[str, Any]) -> float | None:
    count = response.get("eval_count")
    duration_ns = response.get("eval_duration")
    if not isinstance(count, (int, float)) or not isinstance(duration_ns, (int, float)) or duration_ns <= 0:
        return None
    return float(count) / (float(duration_ns) / 1_000_000_000)


def print_stage(name: str, elapsed_ms: float, response: dict[str, Any] | None = None) -> None:
    rate = tokens_per_second(response or {})
    suffix = f" | {rate:.2f} generated tokens/s" if rate is not None else ""
    print(f"{name:26} {elapsed_ms:>10.1f} ms{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile the real non-streaming Ollama shapes used by TokenSmith chat and embeddings.")
    parser.add_argument("query", help="Question for embedding, retrieval, and chat.")
    parser.add_argument("user_data_path", help="Existing TokenSmith user-data directory.")
    parser.add_argument("--model", required=True, help="Ollama chat model name.")
    parser.add_argument("--embedding-model", help="Ollama embedding model name; defaults to --model.")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434", help="Ollama base URL (default: http://127.0.0.1:11434).")
    parser.add_argument("--materials-json", help="JSON list or file of CourseMaterial records; defaults to ready active store materials.")
    parser.add_argument("--limit", type=int, default=4, help="Retrieval top-k (default: 4).")
    parser.add_argument("--skip-follow-up", action="store_true", help="Do not issue TokenSmith's optional second suggestion call.")
    args = parser.parse_args()

    user_data_path = str(require_existing_path(args.user_data_path, "user_data_path"))
    materials = materials_from_argument(user_data_path, args.materials_json)
    base_url = ollama_base_url(args.base_url)
    embedding_model = args.embedding_model or args.model
    normalized_query = normalize_text(args.query)
    stages: list[float] = []

    embedding_response, embedding_ms = post_json(
        f"{base_url}/api/embed",
        {"model": embedding_model, "input": normalized_query[:OLLAMA_EMBEDDING_TEXT_LIMIT], "truncate": True},
        45,
    )
    stages.append(embedding_ms)
    embedding_count = len((embedding_response.get("embeddings") or [[]])[0])
    print(f"Direct embedding dimensions: {embedding_count}; sent {len(normalized_query[:OLLAMA_EMBEDDING_TEXT_LIMIT])} of {len(normalized_query)} normalized characters.")
    print_stage("Ollama /api/embed", embedding_ms, embedding_response)

    embedding_spec = {"engine": "ollama", "role": "embedder", "ollamaBaseUrl": base_url, "ollamaModelName": embedding_model}
    retrieval_started = time.perf_counter()
    with read_only_search_guard():
        retrieval = search_library({"query": args.query, "userDataPath": user_data_path, "materials": materials, "limit": max(1, args.limit), "embeddingModels": [embedding_spec]})
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
    stages.append(retrieval_ms)
    print_stage("search_library (embed + FAISS)", retrieval_ms)
    print(f"Retrieved sources: {len(retrieval['sources'])}; reason={retrieval.get('reason')!r}")

    context = source_context(retrieval["sources"])
    user_content = f"{context}\n\nQuestion: {args.query}" if context else args.query
    messages = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}, {"role": "user", "content": user_content}]
    answer_response, answer_ms = post_json(
        f"{base_url}/api/chat",
        {"model": args.model, "messages": messages, "options": {"num_ctx": 2048, "num_predict": 4096, "temperature": 0.7, "top_p": 0.4, "top_k": 40, "min_p": 0, "repeat_penalty": 1.18}, "stream": False, "think": False},
        180,
    )
    stages.append(answer_ms)
    print_stage("Ollama /api/chat answer", answer_ms, answer_response)
    answer = ((answer_response.get("message") or {}).get("content") or "").strip()
    print(f"Answer preview: {answer[:300]}")

    if not args.skip_follow_up:
        suggestion_response, suggestion_ms = post_json(
            f"{base_url}/api/chat",
            {"model": args.model, "messages": [*messages, {"role": "assistant", "content": answer}, {"role": "user", "content": DEFAULT_FOLLOW_UP_PROMPT}], "options": {"num_ctx": 2048, "num_predict": 160, "temperature": 0.2, "top_p": 0.4, "top_k": 40, "min_p": 0, "repeat_penalty": 1.18}, "stream": False, "think": False},
            180,
        )
        stages.append(suggestion_ms)
        print_stage("Ollama /api/chat follow-up", suggestion_ms, suggestion_response)

    print(f"{'Total observed wall time':26} {sum(stages):>10.1f} ms")


if __name__ == "__main__":
    main()