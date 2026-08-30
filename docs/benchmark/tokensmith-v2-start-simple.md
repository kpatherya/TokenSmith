# Proposal (v2): A Staged, Evidence-Gated Path to Better Indexing in TokenSmith
**Prepared for:** Joy Arulraj, Kexin, Steve
**Scope:** CS 7001 mini-project / independent offshoot of TokenSmith
**Author:** [Your name]

## 0. Why This Version Is Different

The first draft of this proposal jumped straight to "build a hierarchical + graph index." That is not well-supported as a default choice. Evidence from recent retrieval literature shows graph-based RAG is a bet that pays off only under specific conditions (multi-hop, cross-document, high-entity-count queries) and can actively *underperform* plain vector retrieval on self-contained content — which is close to what a course PDF looks like. In one study on a math textbook, standard embedding-based retrieval outperformed graph-based retrieval; in another, GraphRAG scored 13.4% *lower* than vanilla RAG on a standard factual-QA benchmark.

Hierarchical summarization, by contrast, has broader and cheaper support: it improves retrieval focus and reduces cost with fewer failure modes than full graph construction, and outperforms both naive and graph-based baselines across multiple domains in recent work.

So this revision restructures the project as a **staged, falsifiable pipeline**: cheap and low-risk first, escalating only where the data justifies it. Each stage produces its own artifact and evaluation, so the project has a publishable outcome even if we stop after Stage 1.

## 1. Stage 0 — Safety Net: Automated Answer-Quality Monitoring

**Goal:** Catch bad answers cheaply, and generate the labeled failure dataset every later stage depends on.

**What it is:** A lightweight, scheduled job (not a new model) that runs after generation:
- Checks entailment between each generated claim and its cited passage (flag unsupported claims).
- Flags low similarity between the question and its retrieved chunks (a proxy for weak retrieval).
- Logs cases where paraphrased versions of the same question retrieve different evidence.
- Surfaces flagged cases for manual review, similar in spirit to the recorded "quirky response" issue already open in the repo.

**Why first:** This is reactive rather than architectural, cheap to build in days rather than weeks, and directly targets the "keep the system safe" goal without betting on any indexing redesign. Crucially, it produces the dataset of *real* failure cases needed to justify (or rule out) every subsequent stage — we should not build hierarchy or graph structure speculatively when we can measure what's actually failing first.

**Deliverable:** A monitoring script + a labeled set of N real failure cases, categorized by failure type (retrieval miss, contradiction, paraphrase inconsistency, multi-hop miss, etc.).

## 2. Stage 1 — Hierarchical Summarization (No Graph)

**Goal:** Test whether organizing the corpus into a navigable tree — without any graph relations — already fixes most observed failures.

**What it is:** A larger model, run once offline per document, produces short summaries at each level of the document (book → chapter → section), stored alongside the existing FAISS chunk index and SQLite metadata store. No entity/relation extraction yet.

**Why this is well-supported:** Hierarchical RAG methods consistently improve retrieval precision and reduce irrelevant context versus flat retrieval, and document-level summarization alone has shown double-digit retrieval gains at much lower construction cost than a full graph. This is also the most direct fit for the maintainers' existing "Centralized Index Manager" request — the hierarchy can be implemented as a new index type inside that manager rather than a parallel system.

**Evaluation:** Re-run the Stage 0 failure set through the new hierarchical pipeline. Measure:
- Reduction in retrieval-miss and contradiction rates from Stage 0's failure categories.
- Paraphrase robustness: do differently-worded versions of the same question now localize to the same section?
- Latency and index-build cost versus the flat baseline.

**Decision gate:** If Stage 1 resolves the majority of observed failures (especially contradiction and paraphrase-inconsistency cases), the project can stop here with a clean, low-risk, well-supported contribution: a hierarchical index manager for TokenSmith, benchmarked against the flat baseline, deliverable as a PR against issue #122.

## 3. Stage 2 — Concept Graph, Scoped to a Specific Failure Class

**Goal:** Only build graph structure for the failure category that hierarchy alone cannot fix.

**Trigger condition:** Proceed to this stage only if Stage 0's failure log shows a *recurring, identifiable* pattern of:
- Multi-hop questions that require connecting facts across chapters or documents, or
- Questions involving many co-occurring entities where vector similarity alone retrieves the wrong passage.

This is exactly the regime where graph-based retrieval has demonstrated large, reproducible gains — e.g., 86% vs. 32% accuracy on multi-hop enterprise benchmarks, and 77.1 vs. 67.6 on 2WikiMultiHopQA — while vector-only retrieval accuracy has been shown to collapse once a query involves many entities simultaneously.

**What it is, if triggered:** A lightweight concept graph (entities per chapter, relations between them extracted by the offline larger model) added as a *second, narrow retrieval path* used only when the SLM's query is classified as multi-hop or high-entity-count — not a replacement for the hierarchy or FAISS index.

**Why scoped, not general:** Building graph structure for the whole corpus by default is exactly the mistake the literature warns against — expensive to construct, and prone to hurting simple lookup queries. Scoping it to a diagnosed failure class keeps the cost proportional to the demonstrated benefit.

## 4. How the SLM Interacts With the Larger Model's Index (Updated)

The build-time / query-time split from the original proposal still holds, but now it's staged:

| Stage | Offline (larger model) | Runtime (SLM) |
|---|---|---|
| **0** | — | Answers as today; a separate monitoring job checks its outputs after the fact |
| **1** | Produces chapter/section summaries once per corpus | Localizes to the right section via summaries before running the existing FAISS lookup — a shallow, cheap navigation step |
| **2 (if triggered)** | Additionally extracts entities/relations for the diagnosed failure class only | For questions classified as multi-hop/high-entity, hops 1–2 edges in the concept graph *in addition to* the Stage 1 hierarchy, before falling back to FAISS |

At every stage, the SLM is handed a small, pre-organized subset of the corpus rather than raw text or a full graph — the expensive organizing work happens once, offline; the SLM's job at query time stays cheap and bounded. This is what keeps the approach viable for constrained, on-device deployment, and it's also what enables **query-plan reuse**: if a paraphrased question maps to the same tree path (and, if applicable, the same graph nodes) as a prior question, the SLM can reuse the earlier retrieval scope directly.

## 5. Everyday Edge AI Use Cases (Unchanged in Spirit, Staged in Practice)

The generalizable pattern is the same as before, but now explicitly framed as "hierarchy by default, graph only where diagnosed":

- **On-device personal knowledge assistant.** Cloud/larger model builds a hierarchy over a user's notes/PDFs periodically; on-device SLM answers most questions from that hierarchy alone, escalating to a graph hop only for cross-document questions.
- **Field/enterprise technician tools.** Manuals are hierarchically indexed once before deployment; a graph layer is added only for equipment domains where technicians' questions are known to span multiple manual sections (a diagnosable failure class, same as Stage 2's trigger).
- **In-vehicle or embedded assistants.** Latency and memory budgets favor the cheap hierarchy-only path by default; graph structure is reserved for specific multi-entity diagnostic scenarios (e.g., cross-referencing multiple warning codes).
- **Privacy-constrained healthcare/legal deployments.** A larger model builds the index once, offline, before any local, fully private inference — with graph structure added only where audit requirements demand explicit relationship traceability, matching the literature's finding that graph earns its cost in explainability-heavy regulated settings.

## 6. Revised Timeline

1. **Weeks 1–2:** Build Stage 0 monitoring script; collect and categorize real failure cases from current TokenSmith usage/testing.
2. **Weeks 3–6:** Implement Stage 1 hierarchical summarization and section-localized retrieval; integrate as a new index type under the "Centralized Index Manager" issue.
3. **Weeks 7–8:** Evaluate Stage 1 against the Stage 0 failure set and the flat baseline; make the go/no-go call on Stage 2 based on whether multi-hop/high-entity failures persist.
4. **Weeks 9–12 (conditional):** If triggered, implement the scoped concept graph and multi-hop query classifier; re-evaluate on the same failure set.
5. **Weeks 13–15:** Write up results — framed as an evidence-gated indexing pipeline for edge-deployed RAG — targeting a VLDB/SIGMOD data-agents track submission.

This keeps the project shippable and defensible at every stage: Stage 0 alone is a useful contribution, Stage 1 is a well-supported architectural improvement with a natural landing spot in the codebase (issue #122), and Stage 2 is pursued only when the data — not intuition — calls for it.
