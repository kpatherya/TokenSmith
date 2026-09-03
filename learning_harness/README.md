# TokenSmith Learning Harness

These standalone scripts observe existing TokenSmith behavior. They do not call indexing or migration commands, modify source code, or alter indexed records. Retrieval probes block `search_library()`'s migration and FAISS-rebuild fallbacks, so they fail rather than changing a missing or stale index. Run each from the repository root with the bundled interpreter when available:

```sh
app_runtime/python/bin/python learning_harness/01_retrieval_isolator.py --help
```

Scripts that query an indexed library require its existing `userDataPath` and the same embedding `LocalModel` JSON specification that was used for indexing. Supply JSON directly or point an argument at a JSON file.

| Script | Gaps observed | Real source functions or faithful port | Example |
| --- | --- | --- | --- |
| `01_retrieval_isolator.py` | Latency, provenance, cross-chunk reasoning | `tokensmith_engine.search_library`, `starter_sources`, `tokensmith_store.vector_search`, `fetch_sources`, plus the same raw-FAISS steps | `python learning_harness/01_retrieval_isolator.py "What does normalization remove?" /path/to/user-data --embedding-models-json /path/to/models.json` |
| `02_embedding_probe.py` | Latency | `resolve_embedding_provider`, `llama_embedding`, `ollama_embedding`, `remote_openai_embedding` | `python learning_harness/02_embedding_probe.py --model-spec /path/to/ollama-embedder.json` |
| `03_chunking_visualizer.py` | Provenance, cross-chunk reasoning | `extract_pdf_pages_pdfium`, `chunk_pdf_pages`, `chunk_text`, `section_headers_in_text`, `section_header_from_line` | `python learning_harness/03_chunking_visualizer.py /path/to/course.pdf --annotated-output /tmp/chunks.txt` |
| `04_latency_profiler.py` | Latency | `search_library`; ports Ollama's non-streaming `/api/chat` shape from `ollama-service.ts` and `/api/embed` shape from `tokensmith_engine.py` | `python learning_harness/04_latency_profiler.py "What is third normal form?" /path/to/user-data --model llama3.2 --embedding-model nomic-embed-text` |
| `05_context_bleed_harness.py` | Context bleed | Faithful port of `isContextualFollowUpPrompt`, truncation, and `mergeChatSources` from `src/shared/chat-context.ts` | `python learning_harness/05_context_bleed_harness.py learning_harness/fixtures/context_bleed_unrelated_follow_up.json` |
| `06_provenance_auditor.py` | Provenance, transparent reasoning | `source_from_sqlite_chunk`; faithful port of `stripSourceNumberPhrases` and `answerWithOrderedSources` from `study-chat-format.ts` | `python learning_harness/06_provenance_auditor.py --answer "According to Source 2, the answer is supported [Source 2]."` |
| `07_composition_stress_test.py` | Cross-chunk reasoning, provenance | `tokensmith_engine.search_library` | `python learning_harness/07_composition_stress_test.py learning_harness/fixtures/composition_queries.example.json /path/to/user-data --embedding-models-json /path/to/models.json` |
| `08_memory_gap_prober.py` | Agent memory | `tokensmith_store.db_path`, `connect`; reads `src/shared/engine.ts` | `python learning_harness/08_memory_gap_prober.py /path/to/user-data` |

## Fixtures

- `fixtures/context_bleed_unrelated_follow_up.json` demonstrates a topical switch phrased as “What about ...?” being classified as contextual, which injects the prior database answer and prioritizes its sources.
- `fixtures/composition_queries.example.json` is a template. Adapt its evidence terms to the exact vocabulary and section headers in the indexed PDF under observation.

## Ollama Requirements

Scripts `02_embedding_probe.py` and `04_latency_profiler.py` make real network calls. Start Ollama and ensure the named models are installed first. They report a connection failure clearly and never substitute a mock response.