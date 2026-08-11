# Development Progress

## Purpose

This file records implementation progress for the real-source dataset pipeline.
The required roadmap is `Future_progress_of_the_ project.md`.

## Baseline — 2026-08-08

- Existing Phase 1/2 LangGraph pipeline is present and mock-driven.
- `run_domain_test.py` injects mock configuration and mock source content.
- `acquisition_node.py` appends a fixed mock document.
- Domain `sources.yaml` files exist but are not loaded by the runner.
- `src/tools/` is reserved for integrations but currently empty.
- Existing graph nodes cover processing, classification, metadata, entities,
  relations, quality, normalization, validation, and JSON export.
- Current output is written to `knowledge/datasets/<domain>_latest.json`.

## Implementation Order

1. Add structured request, source, schema, and extraction models.
2. Expand LangGraph state and explicit pipeline statuses.
3. Add centralized settings, Groq client, Firecrawl client, and prompts.
4. Add planning, source search/evaluation, and schema-design nodes.
5. Add draft-schema review, approval, and resume support.
6. Connect acquisition to approved real sources and structured extraction.
7. Extend metadata, quality, validation, deduplication, and export.
8. Add mock-based tests, `.env.example`, `.gitignore`, and README.

## Current Work

- Status: real-source dataset pipeline implemented and verified in mock mode.
- Active phase: integration checkpoint complete; live-provider execution needs user credentials.

## Long-Document Chunking Progress — 2026-08-11

| Status | Phase | Goal | Expected Result | Files Changed | Completion Notes |
|---|---|---|---|---|---|
| [x] | Phase 01 | Analysis & Design | Existing architecture analyzed and integration plan confirmed | `src/agents/graphs/phase2_pipeline.py`, `src/agents/nodes/processing_node.py`, `src/agents/nodes/structured_extraction_node.py`, `src/agents/nodes/metadata_enrichment_node.py`, `src/agents/nodes/deduplication_node.py`, `src/state/state.py`, `src/schemas/models.py`, `src/core/settings.py`, `tests/` | Cleaning currently writes `processed_data`; structured extraction sends each full cleaned document in one Groq request; there is no chunk/token utility. Chunking will be inserted after cleaning, extraction will run per chunk, merge will precede metadata, and existing final deduplication/validation/export will remain in the graph. |
| [x] | Phase 02 | Chunking Foundation | Token-aware structural chunking with overlap and provenance | `src/core/tokenization.py`, `src/schemas/models.py`, `src/agents/nodes/chunking_node.py`, `src/core/settings.py`, `.env.example`, domain request configs, `tests/test_chunking_node.py` | Uses `tiktoken` BPE when available and a conservative Unicode fallback otherwise. Markdown headings/paragraphs are preserved where possible; oversized sections split only after structural boundaries; every chunk records source provenance, token count, index, total, and bounded overlap. `4 passed` for the new chunking tests. |
| [x] | Phase 03 | LangGraph Integration | Cleaning → Chunking → Extraction connected through state | `src/state/state.py`, `src/agents/graphs/phase2_pipeline.py` | Added `clean_documents`, `document_chunks`, `chunk_extraction_results`, and `merged_records` to LangGraph state. The approved-schema route is now `Cleaning → Chunking → Structured Extraction → Merge → existing enrichment stages`; the topic-less legacy/mock fallback remains unchanged. |
| [x] | Phase 04 | Per-Chunk Extraction | Groq extracts structured data + confidence from each chunk | `src/agents/nodes/structured_extraction_node.py`, `src/schemas/models.py`, `src/agents/prompts/agents_prompts.py` | Each Groq request receives only one `DocumentChunk`, approved schema, source metadata, and chunk metadata. Extraction results contain `source_chunk_id`, index, and total. The prompt makes top-level `confidence` mandatory. If Groq omits only that summary while returning valid model-generated `field_confidence` values, `ExtractionResult` uses the arithmetic mean for fields populated in `data`; omitted optional fields do not lower that fallback. An explicit top-level value is preserved, and responses with no usable confidence evidence remain invalid. A failed chunk records source/chunk context without discarding other successful chunks. |
| [x] | Phase 05 | Merge & Deduplication | Partial records safely merged with provenance and final confidence | `src/agents/nodes/record_merge_node.py`, `src/agents/nodes/deduplication_node.py` | Uses a deterministic approved-schema name/id/title field when available; unrelated same-source records remain separate. Arrays are unioned, scalar conflicts are logged and resolved by field confidence, merged confidence is the minimum contributor confidence, and final duplicate data retains merged source/chunk provenance. |
| [x] | Phase 06 | Quality & Pipeline Integration | Metadata, quality, validation and final LangGraph flow completed | `src/agents/nodes/metadata_enrichment_node.py`, existing quality/validation/export nodes | Metadata now transports merged confidence plus `contributing_chunk_ids` and merge conflicts. Existing quality, ApprovedDatasetSchema validation, final deduplication, and JSON/JSONL export remain in use. The long-document mock integration test reaches completed export. |
| [x] | Phase 07 | Testing & Reliability | Unit, regression and long-document tests pass | `tests/test_chunking_node.py`, `tests/test_long_document_pipeline.py`, `tests/test_dataset_generation_pipeline.py` | Covers small/large documents, structural boundaries, token budgets, overlap, chunk IDs/provenance, tokenizer failure, per-chunk calls/confidence, partial merge, non-merge of distinct entities, array/scalar conflict rules, all-chunk failure, duplicate provenance, and final export. Full suite: `41 passed, 1 skipped`. |
| [x] | Phase 08 | Documentation & Final Verification | README/progress updated and repository fully verified | `README.md`, `docs/DEVELOPMENT_PROGRESS.md` | README documents context budgeting, chunking configuration, structural splitting, overlap, per-chunk extraction, conservative merge confidence, provenance, actual graph order, and validation. `git diff --check`, `compileall`, and the full local test suite completed successfully. |

## Roadmap Evidence — Steps 5–25 — 2026-08-10

| Roadmap step | Status | Implemented in | Evidence |
|---|---|---|---|
| 5. Reusable Groq client | Complete in mock-tested code | `src/tools/groq_client.py`, `src/core/retry.py` | Shared JSON completion, timeout, bounded retry, provider-key errors, and non-retryable auth/schema/configuration classification are isolated from node logic. |
| 6. Four separated prompts | Complete | `src/agents/prompts/agents_prompts.py` | Research planning, source evaluation, schema design, and structured extraction use independent system prompts. |
| 7. ResearchPlanner node | Complete | `src/agents/nodes/research_planner_node.py` | Reads topic, purpose, research constraints, and max-query settings; writes `research_plan`. |
| 8. Firecrawl tool | Complete in mock-tested code | `src/tools/firecrawl_tool.py`, `src/core/retry.py` | Owns only `search()` and `scrape()` with API-key checks, transient-only retry handling, and metadata normalization. |
| 9. SourceSearch node | Complete | `src/agents/nodes/source_search_node.py` | Uses plan queries, normalizes/deduplicates URLs, honors preferred domains, and keeps explicit `reference_urls`. |
| 10. SourceEvaluator node | Complete | `src/agents/nodes/source_evaluator_node.py` | Evaluates only candidate URLs and stores selected/rejected sources. Explicit user references are a documented fallback only when nothing is selected. |
| 11. DatasetSchemaDesigner node | Complete | `src/agents/nodes/dataset_schema_designer_node.py` | Creates `draft_dataset_schema`, then always enters `waiting_for_schema_approval`; it never starts extraction. |
| 12. Editable terminal review | Complete | `run_domain_test.py`, `knowledge/review/` | Prints the draft schema and writes an editable JSON file. |
| 13. Domain approval operation | Complete | `DatasetGenerationPipeline.approve_schema()` in `src/agents/graphs/phase2_pipeline.py` | Validates edited schema, creates versioned approval data, preserves waiting state on invalid input, and resumes the same graph. |
| 14. Existing LangGraph integration | Complete | `src/agents/graphs/phase2_pipeline.py` | The existing Phase 2 graph contains planning, approval pause, acquisition, existing enrichment nodes, validation, deduplication, and export. |
| 15. Approved-source acquisition | Complete | `src/agents/nodes/acquisition_node.py` | Blocks scraping without approval and uses `FirecrawlTool.scrape()` in live mode. |
| 16. Structured extraction | Complete in mock-tested code | `src/agents/nodes/structured_extraction_node.py` | Uses only approved schema plus cleaned content and returns data with overall/field confidence. |
| 17. Confidence flow | Complete | `structured_extraction_node.py`, `metadata_enrichment_node.py`, `validation_node.py` | Confidence is produced at extraction, carried to metadata, and threshold-checked without recomputation. |
| 18. Existing metadata node | Complete | `src/agents/nodes/metadata_enrichment_node.py` | Adds URL, title, domain, provider, search query, topic, timestamps, schema version, and confidence. |
| 19. Entity and relation nodes | Preserved and integrated | `entity_extraction_node.py`, `relation_extraction_node.py` | Existing enrichment stages remain after metadata and before quality/validation. |
| 20. Quality and validation nodes | Complete | `quality_analysis_node.py`, `validation_node.py` | Quality reports include confidence; validation checks approved-schema fields, types, and the configured confidence threshold. |
| 21. Existing export node | Complete | `src/agents/nodes/export_node.py` | Writes accepted dynamic records to `knowledge/datasets/<dataset-name>.json` or `.jsonl`; legacy output remains supported. |
| 22. File-order integration | Complete | `models.py` through `README.md` | The implementation follows the roadmap dependency order; this table provides the explicit trace that was previously missing. |
| 23. Per-stage output contracts | Complete | `src/state/state.py`, `src/schemas/models.py`, the pipeline nodes | State exposes the output of every stage; `ResearchPlan`, `CandidateSource`, source evaluation, draft/approved schema, and extraction-result contracts validate dynamic pipeline data. |
| 24. No frontend in this phase | Complete by design | `run_domain_test.py`, `DatasetGenerationPipeline.approve_schema()` | The terminal is only the presentation layer. Approval remains a reusable pipeline operation for a future UI; no separate frontend or duplicated approval logic was introduced. |
| 25. First-version user workflow | Complete in mock-tested code | `configs/domains/*/request.yaml`, `run_domain_test.py`, `README.md` | Topic/purpose input, terminal draft review, optional edited-file reload, approval, resume, extraction, validation, and named JSON/JSONL output are documented and exercised by tests. |

## Reliability and Observability Additions

- `src/core/retry.py` prevents retries for authentication, authorization,
  invalid-schema, configuration, and other non-transient provider failures.
  Transient errors such as rate limits can use bounded exponential backoff.
- `src/core/logging.py` is now used by research planning, source search,
  source evaluation, schema design, structured extraction, and schema approval.
  Logs report counts and state transitions without logging secrets.
- New mock tests cover domain config loading, missing provider keys,
  retry classification, empty source content, JSONL serialization, and durable
  approval resume in addition to the existing pipeline tests.
- Central settings now actively supply fallback values for research limits and
  low-confidence handling. Optional `SAVE_RAW_CONTENT` and
  `SAVE_CLEAN_CONTENT` configuration writes separate debug artifacts only when
  explicitly enabled; final validated output remains the default behavior.
- `tests/test_live_integration.py` is an opt-in live smoke test. It is skipped
  by default and runs only when `RUN_INTEGRATION_TESTS=true`, both provider
  keys exist, and the source provider is Firecrawl.

## Durable Approval Checkpoint

- `write_draft_review_file()` now writes both the editable schema and a pending
  pipeline state checkpoint under `knowledge/review/`.
- `python run_domain_test.py --domain <domain> --resume` reloads that pending
  state and continues at schema approval without rerunning planning or search.
- `tests/test_dataset_generation_pipeline.py` verifies that an edited schema
  can be approved after creating a new pipeline instance.

## Pipeline Checkpoint

```text
Dataset request
  -> ResearchPlanner
  -> SourceSearch
  -> SourceEvaluator
  -> DatasetSchemaDesigner
  -> WAITING_FOR_SCHEMA_APPROVAL
  -> approve_schema()
  -> Acquisition and cleaning
  -> StructuredExtractor
  -> Metadata, quality, validation, deduplication, and export
```

Draft schemas are written to `knowledge/review/<dataset-name>_draft_schema.json`.
Scraping and structured extraction cannot start before schema approval.

## Verification Record

- 2026-08-11: The missing top-level confidence fallback now averages valid
  field-confidence scores only for populated extracted fields. Full local suite:
  `45 passed, 1 skipped` using the installed Python 3.11 runtime and
  `python -m pytest -q`.
- 2026-08-10: `compileall` completed successfully and `34 passed, 1 skipped`
  using the
  installed Python 3.11 runtime and `python -m pytest -q`.
- Tests use `DATA_SOURCE_PROVIDER=mock`; they do not require API keys or a
  network connection.
- Live Firecrawl and Groq execution remains unverified because it requires
  user credentials and makes external network calls.

## Remaining External Verification

- The source code and mock workflow are complete for steps 5–22, but a
  successful real Firecrawl plus Groq dataset run is still required to prove
  provider-account access, live response formats, source availability, and
  output quality for a chosen topic.

## Pending Language Cleanup

- Existing Turkish text remains in legacy documentation and older source files
  outside the files changed for this integration.
- Newly written source code, prompts, configuration comments, README, tests,
  and this progress record are in English.
