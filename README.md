# Knowledge Extraction Agent

## Vision

This project generates evidence-backed, structured datasets from web sources for downstream RAG, GraphRAG, knowledge-base, machine-learning, fine-tuning, and agent applications. It is not a chatbot or a RAG application. A user supplies a dataset topic, purpose, and optional constraints; the pipeline plans research, discovers and evaluates real sources, proposes a dataset schema, waits for human approval, extracts records, validates them, and writes JSON or JSONL output.

## Architecture

The existing application path is preserved:

```text
configs/domains/<domain>/request.yaml
  -> run_domain_test.py
  -> src/agents/graphs/phase2_pipeline.py
  -> src/agents/nodes/*
  -> src/state/state.py
  -> knowledge/datasets/<dataset-name>.json
```

`AgentState` is the observable data contract between nodes. It holds the request, research plan, candidate and selected sources, draft and approved schemas, scraped documents, extraction results, accepted/rejected records, errors, and pipeline status. This keeps a future UI independent of internal Python objects.

## Core Pipeline

```text
Topic and purpose
  -> ResearchPlanner
  -> Firecrawl Search
  -> SourceEvaluator
  -> DatasetSchemaDesigner
  -> WAITING_FOR_SCHEMA_APPROVAL
  -> user approval
  -> Firecrawl Scrape
  -> cleaning
  -> token-aware chunking
  -> per-chunk StructuredExtractor
  -> record merge
  -> metadata, entity/relation enrichment, quality, validation, deduplication
  -> JSON or JSONL dataset
```

The source and extraction paths are deliberately separate. Firecrawl finds and retrieves pages; Groq plans, evaluates supplied candidates, designs a draft schema, and extracts records with an evidence-support score.

## Long-Document Chunking

A scraped document is never sent blindly to Groq as one request. A page can be much larger than the selected model's usable request budget even when its nominal context window is large: the request also contains the system prompt, approved schema, field instructions, source metadata, expected JSON output, and a safety margin. Changing to a larger-context model alone is therefore not a permanent solution.

After cleaning, `chunking_node.py` converts each source into `DocumentChunk` objects. It uses `tiktoken` BPE counts when available and a conservative Unicode-aware fallback otherwise. The configurable source-content target defaults to 6,000 tokens; it is a safe starting point, not a universal model limit. A chunk also records its source URL/title, source metadata, heading, index, total count, token count, and overlap count.

The chunker prefers Markdown headings and paragraphs, accumulates those structural units up to the token budget, and splits inside a paragraph only when that paragraph alone exceeds the budget. Adjacent chunks can retain a small bounded overlap so facts at a boundary are not lost. For a 100K-token source, this produces many bounded requests rather than one failing request.

```text
Large source document
        ↓
Cleaning
        ↓
Token-aware structural chunking
        ↓
┌─────────┬─────────┬─────────┐
│ Chunk 1 │ Chunk 2 │ Chunk N │
└────┬────┴────┬────┴────┬────┘
     ↓         ↓         ↓
Per-chunk structured extraction
     ↓         ↓         ↓
Chunk extraction results
            ↓
           Merge
            ↓
Metadata, quality, and validation
            ↓
      Deduplication
            ↓
          Dataset
```

`structured_extraction_node.py` sends the approved schema, source/chunk metadata, and one chunk's content to Groq for each call. Groq still creates confidence per chunk; chunking, merging, metadata, and validation never invent a confidence value. A failed chunk is recorded with its source URL and chunk ID while successful chunks continue.

`record_merge_node.py` conservatively combines chunk results only when an approved string field provides a deterministic name, title, or identifier match. Array values are unioned; a missing value is filled from evidence; conflicting scalar values are retained according to field confidence and recorded in `merge_conflicts`. Merged confidence is the minimum confidence among contributors that supplied factual fields. `contributing_chunk_ids` remain in final `_metadata`. Final exact-data deduplication also combines source/chunk provenance instead of discarding it.

The existing graph keeps final deduplication after schema/confidence validation, rather than moving it in front of metadata. This preserves the project’s established quality gate: only valid final records are deduplicated. Chunk-level overlap is already handled earlier by conservative record merging.

## Human-in-the-Loop Schema Approval

`DatasetSchemaDesigner` creates a `DraftDatasetSchema`, never a final schema. The graph then stops at `waiting_for_schema_approval`; it does not scrape or extract data. `DatasetGenerationPipeline.approve_schema()` validates the draft, creates an `ApprovedDatasetSchema` with `schema_version`, `approved_at`, and `approved_by`, then resumes the same graph from acquisition.

The terminal runner writes the draft to `knowledge/review/<domain>_draft_schema.json`. You can add, remove, rename, or edit fields there before choosing the reload-and-approve option. Every field supports `field_name`, `type`, `required`, `nullable`, `is_array`, `description`, and `extraction_instruction`. The valid types are `string`, `integer`, `number`, `boolean`, `array`, and `object`.

## Groq Tasks

Each task has an isolated system prompt in `src/agents/prompts/agents_prompts.py` and a structured Pydantic output model.

- `ResearchPlanner` creates the research strategy and queries; it does not search the web.
- `SourceEvaluator` evaluates only URLs returned by Firecrawl; it cannot create or modify a URL.
- `DatasetSchemaDesigner` creates a topic-specific draft schema; it does not approve it or extract data.
- `StructuredExtractor` uses only the approved schema and clean source content; it does not invent unsupported facts.

`src/tools/groq_client.py` owns reusable API connectivity, structured JSON parsing, timeout configuration, and bounded retries. It contains no task-specific prompt logic.

## Firecrawl Tasks

`src/tools/firecrawl_tool.py` exposes `search(query)` and `scrape(url)`. Search output is normalized into candidate sources with URL, title, description, domain, and search query. Scrape output preserves source metadata and clean Markdown when available. Firecrawl does not determine source quality, dataset fields, confidence, or final record validity.

## Confidence, Validation, and Metadata

Confidence is not a native Groq probability. It is an evidence-support score returned by `StructuredExtractor`: 1.0 means the source clearly supports the extracted data, while lower values indicate weak or incomplete support. The extractor requests a required top-level `confidence`; an explicitly returned value is preserved. If a provider omits only that summary but returns valid model-generated `field_confidence` values, the extraction boundary uses the arithmetic mean of scores for populated fields in `data`; omitted optional fields do not affect that fallback. A response with no usable confidence evidence remains invalid. This extraction fallback does not change record merging: `record_merge_node.py` still uses the minimum contributor confidence. `validation_node.py` checks the approved schema, required fields, value types, and the configured `minimum_confidence` threshold. Low-confidence or invalid records are written to `rejected_records`; valid records become `accepted_records`. `deduplication_node.py` then removes repeated structured data before export and records duplicate rejections.

Metadata is separate from the dynamic dataset schema. Each accepted output record keeps provenance such as source URL, title, domain, retrieval time, provider, search query, dataset topic, schema version, and confidence under `_metadata`.

## Configuration

Each domain has a request at `configs/domains/<domain>/request.yaml`:

```yaml
dataset:
  topic: Traditional Turkish coffee culture
  purpose: Evidence-backed records for RAG and knowledge-base systems.
research:
  max_queries: 10
  max_sources: 20
schema:
  require_user_approval: true
extraction:
  chunking:
    enabled: true
    target_tokens: 6000
    overlap_tokens: 300
quality:
  minimum_confidence: 0.70
output:
  format: json
```

`dataset.name` is the final dataset filename. For example, `malatya_dishes`
creates `knowledge/datasets/malatya_dishes.json` and a review file named
`knowledge/review/malatya_dishes_draft_schema.json`.

Set `output.save_raw_content` or `output.save_clean_content` to `true` only
when debugging a run. They create separate `_raw.json` and `_clean.json`
artifacts; the default remains `false` to keep the final dataset directory
focused on validated records.

The request represents user intent, not a provider prompt. Prompts are assembled inside the corresponding nodes. See `.env.example` for provider keys, timeouts, retry count, confidence threshold, and output defaults. Never commit a real `.env` file.

## Mock and Real Modes

`DATA_SOURCE_PROVIDER=mock` is the default offline mode. It uses configured sources and deterministic extraction, so unit tests never need API keys or network access. Set `DATA_SOURCE_PROVIDER=firecrawl` and provide both `FIRECRAWL_API_KEY` and `GROQ_API_KEY` to use live source discovery, scraping, and Groq calls.

## Installation and Usage (Windows PowerShell)

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run_domain_test.py --domain turkish_culture
```

The interactive run pauses after draft-schema generation. Review the displayed JSON file, then choose:

```text
1 - Approve the current draft
2 - Reload the edited schema file and approve it
3 - Cancel the run
```

The pending research plan, selected sources, and draft schema are also saved in
`knowledge/review/<dataset-name>_pipeline_state.json`. If the terminal closes,
resume the same approval checkpoint without rerunning planning or search:

```powershell
python run_domain_test.py --domain turkish_culture --resume
```

For a non-interactive mock demonstration, use:

```powershell
python run_domain_test.py --domain turkish_culture --approve-schema
```

The normal test suite is fully offline. To run the opt-in live smoke test that
stops at schema approval (and therefore does not scrape or extract records), set
`RUN_INTEGRATION_TESTS=true`, configure both provider keys, and run:

```powershell
python -m pytest tests/test_live_integration.py -q
```

## Example Workflow

For the topic `Traditional Turkish coffee culture`, ResearchPlanner proposes historical, preparation, and social-tradition queries. Firecrawl finds candidate sources. SourceEvaluator selects trustworthy candidates. DatasetSchemaDesigner proposes fields, for example `content` or topic-specific fields such as `preparation_method`. The user edits and approves the draft. Firecrawl scrapes selected pages, StructuredExtractor produces only source-supported field values and confidence, validation rejects weak records, and export writes the accepted records.

## Output Format

```json
{
  "data": {
    "content": "Source-supported factual content."
  },
  "_metadata": {
    "source_url": "https://example.org/source",
    "source_title": "Example source",
    "source_provider": "firecrawl",
    "schema_version": "1",
    "confidence_score": 0.94
  }
}
```

## Future UI

No frontend is included. A future interface can observe `pipeline_status` and state fields to show the research plan, candidate and selected sources, draft schema editor, approval action, scraping and extraction progress, validation decisions, errors, and final dataset. The same `approve_schema()` domain operation can be called from an Approve button instead of the current terminal interaction.
