# Proposal: Multi-Level & Graph-Augmented Indexing for TokenSmith
**Prepared for:** Joy Arulraj, Kexin, Steve
**Scope:** CS 7001 mini-project / independent offshoot of TokenSmith
**Author:** [Your name]

## 1. Problem Statement

TokenSmith currently answers course questions with a **single flat retrieval pipeline**: PDFs are chunked at a fixed size (1000 characters, 0 overlap), embedded, and stored in one FAISS vector index per corpus, with one local Ollama model used for *both* retrieval-adjacent tasks and answer generation. There is no chapter/section/concept structure attached to chunks, no graph representation of entities or relations, and the cross-encoder reranker the team currently relies on is being removed for platform-compatibility reasons rather than extended. This flat design already produces observable failures — one open issue documents a self-contradictory answer despite retrieving seemingly relevant passages, and the maintainers have separately requested a "Centralized Index Manager" to handle multiple named indexes, which has no design yet for anything beyond flat, per-corpus FAISS stores.

This is a well-scoped gap: TokenSmith needs an index structure that is *richer than one flat vector store* but still cheap enough to query from a small, resource-constrained local model. That is precisely the offshoot I want to build.

## 2. Proposed Contribution

**Build a hierarchical, graph-augmented index for TokenSmith, constructed offline by a larger model and queried at runtime by the existing small local model (SLM).** Concretely:

1. **Hierarchical index (book → chapter → section → chunk).** A larger model (run once per document, offline, possibly cloud-side or a stronger local model) reads the document and produces short structured summaries at each level of granularity, plus tags linking child nodes to parent topics. This becomes a small navigable tree stored alongside the existing FAISS chunk index — not a replacement for it.
2. **Concept graph layer.** The same offline pass extracts key entities/concepts per chapter and the relations between them (e.g., "two-phase locking" → "used by" → "strict 2PL"), producing a lightweight graph (nodes = concepts, edges = relations) that sits beside the hierarchy.
3. **SLM-facing query interface.** At query time, the small local model does **not** read the whole corpus or the whole graph. It performs a cheap, staged lookup: first localize to the right chapter/section via the hierarchy (a handful of summary tokens, not full text), optionally hop across 1–2 graph edges if the question spans concepts, and only then retrieve fine-grained chunks from FAISS within that narrowed scope.
4. **Evaluation against the current flat baseline** using paraphrased question sets (to test robustness to phrasing/"language shifts") and multi-hop questions (to test whether the graph hop helps where flat retrieval fails), directly using the existing "quirky response" bug as a documented before/after case.

## 3. How the SLM Interacts With the Larger Model's Index

This split is the core systems idea, and it maps directly onto a **build-time / query-time separation of labor**:

| Phase | Actor | What happens |
|---|---|---|
| **Index construction (offline, once per corpus)** | Larger model | Reads full chapters, writes hierarchical summaries per section, extracts concept nodes and relations, writes everything to a compact tree + graph structure on disk (alongside the existing SQLite + FAISS store) |
| **Query time (every question)** | SLM (existing local Ollama chat model) | Never re-reads raw chapters. It is handed a *small, structured menu*: top-level chapter summaries, then the summaries of the 2–3 most relevant sections, then optionally 1–2 graph-neighbor concepts, then the FAISS-retrieved chunks from the narrowed scope |
| **Answer generation** | SLM | Synthesizes the answer strictly from the narrowed evidence set, attaching the same page-source citation cards TokenSmith already shows, now traceable to a specific tree node/graph path |

The key point for the proposal: **the SLM never has to reason over the whole book or the whole graph.** It reasons over a small, pre-organized subset that the larger model prepared in advance. This is what makes the approach viable on-device — the expensive reasoning (organizing the corpus) happens once, offline, and the cheap reasoning (answering a specific question) happens repeatedly, at inference time, on a model small enough to run on a laptop or phone. This also gives us a natural mechanism for **query-plan reuse** (à la EvaDB): if a paraphrased question maps to the same tree path and graph nodes as a previous question, the SLM can reuse the prior retrieval scope directly, cutting latency and improving consistency across rephrasings.

## 4. Everyday Edge AI Use Cases

The course-tutor framing is the vehicle, but the underlying pattern — *a small on-device model navigating an index that a larger model organized in advance* — generalizes to any setting where a resource-constrained device must reason over a large personal or local corpus without cloud access:

- **On-device personal knowledge assistant.** A phone or laptop assistant that answers questions over a user's own notes, emails, and PDFs entirely offline. A cloud model builds the hierarchical/graph index once (e.g., overnight, or when new documents are added); the on-device SLM answers questions instantly and privately using that pre-built structure.
- **Field/enterprise technician support tools.** A technician on a factory floor or job site with no reliable connectivity needs an assistant that can answer questions against equipment manuals or compliance documents. The index is built once (in the cloud, before deployment) and shipped to the device; the SLM on a ruggedized tablet queries it locally.
- **In-vehicle or embedded assistants.** Cars, appliances, or IoT hubs increasingly ship a small local model for latency and privacy reasons but cannot afford to keep large manuals or logs in raw form on-device. A hierarchical/graph index compresses that knowledge into a form a tiny model can navigate cheaply.
- **Healthcare or legal edge deployments with strict privacy constraints.** Clinics or small firms that cannot send documents to the cloud at inference time can still use a cloud/larger model *once*, at ingestion time, to build the index, then run all subsequent queries fully locally.

In every case, the pattern matches the framing in your note: this is squarely a **databases-for-AI** contribution — the "database" being built is not a generic vector store but a structured, multi-level, provenance-carrying index specifically engineered so that a small, context-limited model can use it effectively. This is the same reasoning motivating agent-memory startups like Cognee and graph-database vendors like Neo4j, and it has a direct publication venue in the VLDB/SIGMOD data-agent tracks.

## 5. Proposed Scope for a Mini-Project Semester

1. **Weeks 1–3:** Implement offline hierarchical summarization pass (chapter/section) using a larger model; store as a lightweight tree alongside existing SQLite/FAISS store.
2. **Weeks 4–6:** Add concept-graph extraction (entities + relations per chapter) and a simple graph-hop retrieval step.
3. **Weeks 7–9:** Wire the SLM's retrieval call to consult the hierarchy/graph before FAISS; add plan caching for repeated/paraphrased queries.
4. **Weeks 10–12:** Build paraphrase and multi-hop evaluation sets; benchmark against the current flat baseline, using the existing "quirky response" issue as a qualitative case study.
5. **Weeks 13–15:** Write up as a workshop/short paper draft targeting a VLDB or SIGMOD data-agents track, positioned as a database-systems contribution to agent memory.

This scoping keeps the project shippable within a semester while producing a concrete artifact (a PR against TokenSmith's index manager) and a defensible research claim for an independent paper.
