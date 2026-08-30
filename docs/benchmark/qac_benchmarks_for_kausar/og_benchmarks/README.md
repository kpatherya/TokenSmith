# Claude-Verified Benchmarks

Two ready-to-use QA benchmarks for evaluating a RAG / question-answering system on the
textbook *Database System Concepts (7th edition)*. Both files have been machine-generated
and/or hand-curated, then put through a multi-agent correctness audit (see the audit trail
in `../CLAUDE_AUDIT_REPORT.md`). **These are the canonical, cleaned versions — use these.**

```
claude_verified_benchmarks/
├── exercise_qa_benchmark.json     # 40 records — textbook exercise questions (rubric-only)
└── synthetic_qac_benchmark.json   # 55 records — generated Q/A with verbatim gold chunks
```

| | Exercise QA | Synthetic QAC |
|---|---|---|
| Records | 40 | 55 |
| Origin | Hand-picked textbook end-of-chapter exercises | LLM-generated from textbook pages, then human-reviewed |
| Has gold chunks? | ❌ No | ✅ Yes (verbatim-ish textbook sentences) |
| Can measure retrieval? | ❌ No (answer/rubric quality only) | ✅ Yes (retrieval coverage + answer quality) |
| Reference answer trustworthy? | ⚠️ Treat as a hint, not ground truth (see below) | ✅ Reviewed |
| Difficulty labels? | ❌ No | ✅ easy/medium/hard |

---

## ⚠️ Read this first: what is "ground truth" in each benchmark

**The RUBRIC is the source of truth for grading — not the reference answer.**

- **Exercise QA:** the `answer` field was taken from an online **solutions guide** and may contain
  errors, omissions, or shortcuts. It has intentionally **not** been edited. Do **not** grade a
  system by comparing to `answer`. Grade against `must_rubric` (and optionally `optional_rubric`),
  which have been reviewed to be **clear and correct on their own**. Each question is a
  **self-contained island** — no question, answer, or rubric refers to any other exercise.
- **Synthetic QAC:** the `answer` (a model-written reference answer) has been reviewed and is
  reliable, but here too the **rubric + gold chunks** are the primary grading signal. Every rubric
  item is consistent with the gold/optional chunks.

**Gold chunks are "verbatim-ish", not byte-exact.** They were copied from a PDF-extracted markdown
of the textbook, so a chunk may differ from the printed book by whitespace, hyphenation
(`shared-mode` vs `sharedmode`), math-symbol rendering (`⋈`, `σ`, `Π`), or stray artifacts. This is
**expected and fine**. When matching retrieved text against gold chunks, use **normalized / fuzzy**
comparison (see the retrieval-scoring recipe below), never strict `==`.

---

## Field reference

### `exercise_qa_benchmark.json` — array of 40 objects
| Field | Type | Meaning / how to use |
|---|---|---|
| `id` | str | Book exercise number, e.g. `"7.1"`. Unique. |
| `question` | str | The exercise question. Self-contained; feed this to the system under test. |
| `answer` | str | Reference answer from a solutions guide. **Hint only — may be faulty. Do not grade against it.** |
| `must_rubric` | list[str] | Required criteria. **This is the grading target.** Score = fraction met. |
| `optional_rubric` | list[str] | Bonus criteria. Score separately; do **not** fold into the primary score. |

### `synthetic_qac_benchmark.json` — array of 55 objects
| Field | Type | Meaning / how to use |
|---|---|---|
| `id` | str | Clean id `"{chapter}.{n}"`, e.g. `"18.1"`. Unique. |
| `chapter` | int | Source chapter (use for slicing/reporting by chapter). |
| `difficulty` | str | `easy` / `medium` / `hard`. For `hard`, the answer requires **reasoning over** chunks, not a direct quote — grade accordingly. |
| `question` | str | Self-contained question. Feed to the system. |
| `answer` | str | Reviewed reference answer. Usable for reference-based correctness / BLEU-style signals. |
| `must_rubric` | list[str] | Required criteria — primary grading target. |
| `optional_rubric` | list[str] | Bonus criteria — score separately. |
| `gold_chunks` | list[str] | Verbatim-ish textbook sentences **required** to answer. **Retrieval ground truth.** |
| `optional_chunks` | list[str] | Supporting sentences (helpful but not required). Count as partial/bonus for retrieval. |
| `example_analogy_chunks` | list[str] | *Present only when non-empty (12 records).* **Overlay tag:** each string here ALSO appears in `gold_chunks` or `optional_chunks`; it flags that chunk as an illustrative example/analogy. Use only if you want to treat examples specially. |
| `example_analogy_rubric` | list[str] | *Present only when non-empty (3 records).* Same overlay idea, for rubric items. |
| `confusing_chunks` | list[str] | Defined for completeness; **empty in every record** currently. Would overlay-tag a chunk the reviewer found confusing. |
| `chunk_relationships` | obj | *Present only when non-empty (39 records).* `composites` = groups where **ALL** listed chunks are needed together; `substitutes` = groups where **ANY ONE** suffices. Use for smarter retrieval scoring (see below). |
| `source_id` | str | Traceability back to the raw record (`c{ch}_w{start}_{end}_q{idx}`). Not needed for evaluation. |

Notes:
- `must_rubric` + `optional_rubric` = the full rubric; `gold_chunks` + `optional_chunks` = the full
  chunk set (a complete partition — nothing is dropped).
- Overlay fields (`example_analogy_*`) are **not** a separate bucket; an item tagged there is still
  counted in gold/optional. They are omitted from a record when empty to keep records clean.

---

## How to run an evaluation

Both benchmarks share the same core loop. For each record:

1. **Ask the system** the `question` (with retrieval enabled).
2. **Capture** the system's answer, and (synthetic only) the chunks it retrieved.
3. **Score** with the metrics below.
4. **Aggregate** across records (and, for synthetic, by `difficulty` and `chapter`).

### A. Answer quality — both benchmarks (rubric-based; recommended primary metric)

Use an LLM judge (or a human) to decide, **for each `must_rubric` item**, whether the system's
answer satisfies it: `met` / `partial` / `not_met`.

```
must_rubric_score(record) = (# must items met) / (len(must_rubric))
overall_must_score        = mean over records
```

- Score `optional_rubric` the same way but report it **separately** — it is a bonus signal, never
  part of the headline number.
- **Do not** require the answer to match the reference `answer`. The rubric is authoritative.
- For synthetic `hard` items, instruct the judge that correct **inference** over the chunks counts
  as met (the answer need not be a verbatim restatement).

### B. Reference-based correctness — optional

If you want a second signal, ask a judge to rate the answer `-1 / 0 / 1` for correctness:
- **Synthetic:** you may pass `answer` as a reference (it is reviewed).
- **Exercise:** prefer the **no-reference** variant (judge against `must_rubric` only), because the
  reference `answer` may be wrong. If you do pass it, treat disagreements as inconclusive, not as
  system errors.

### C. Retrieval coverage — synthetic only (needs `gold_chunks`)

Measures whether the system retrieved the sentences actually needed to answer.

1. For each `gold_chunk`, check whether it is "present" in the concatenation of the system's
   retrieved chunks, using a **normalized** match (do **not** use exact `==`):
   - lowercase, collapse all whitespace to single spaces, strip punctuation at ends;
   - optionally also strip page-marker artifacts and hyphenation;
   - a chunk counts as covered if the normalized gold chunk is a substring of the normalized
     retrieved text (or passes a high fuzzy-ratio / ROUGE-L threshold).
2. Compute:
```
gold_coverage(record)     = (# gold_chunks matched) / (len(gold_chunks))
overall_gold_coverage     = mean over records
```
3. **Optional chunks:** compute the same coverage over `optional_chunks` and report as a secondary
   number; do not penalize a system for missing them.
4. **Respect `chunk_relationships` when present:**
   - `composites`: the group is only "covered" if **every** chunk in the group is matched.
   - `substitutes`: the group is "covered" if **any one** chunk in the group is matched (credit the
     group once; don't require all).
   A simple correct approach: replace the members of each relationship group with a single
   group-level covered/not-covered result before computing coverage.

### D. Retrieval precision / relevance — synthetic (optional)

Judge each **retrieved** chunk as relevant / not-relevant to the question (LLM or human), and
report the relevant fraction. Gold chunks give recall; this gives precision.

### E. Faithfulness — both (optional)

Judge whether the system's answer is supported by the chunks it retrieved
(`faithful` / `partially` / `unfaithful`). Useful for catching hallucination independent of rubric.

---

## Suggested reporting

- **Headline:** `overall_must_score` (rubric coverage) for each benchmark.
- **Synthetic extras:** `overall_gold_coverage`, plus `must_score` and `gold_coverage`
  broken down by `difficulty` (easy/medium/hard) and by `chapter`.
- **Secondary:** optional-rubric score, optional-chunk coverage, retrieval precision, faithfulness.
- Always state dataset size (40 / 55) so the numbers are read at the right scale.

---

## Provenance & caveats (summary)

- **Exercise QA:** hand-selected book exercises; reference answers from a solutions guide
  (may be faulty — rubric is authoritative); one duplicate exercise (`6.5`) was removed.
- **Synthetic QAC:** generated by `google/gemini-2.5-pro-preview` from textbook page windows,
  self-critiqued and dual-model verified, then **human-reviewed** (approved/edited with per-chunk
  and per-rubric flags), then Claude-audited for correctness. Chapters covered: 1, 3, 7, 12, 16, 17,
  18, 19. One record (`16.6`) was removed during audit; `1.1` rubric split confirmed.
- **Scale:** small, curated benchmarks — excellent for controlled A/B and regression testing of a
  RAG pipeline; not large enough for headline accuracy claims without noting the size.
- **Source text:** derived from a copyrighted textbook. Clear any licensing questions before
  redistributing these files externally.
- Full change log of the audit: `../CLAUDE_AUDIT_REPORT.md`.
