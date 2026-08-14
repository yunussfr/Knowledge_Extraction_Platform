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

`AgentState` is the observable data contract between nodes. It holds the request, research plan, canonical source registry, candidate and selected sources, draft and approved schemas, scraped documents, extraction results, accepted/rejected records, errors, and pipeline status. This keeps a future UI independent of internal Python objects.

## Core Pipeline

```text
Topic and purpose
  -> ResearchPlanner
  -> Firecrawl Search
  -> Crawl4AI bounded SourcePreview
  -> SourceEvaluator
  -> optional bounded site exploration
  -> SourceSelector
  -> DatasetSchemaDesigner
  -> WAITING_FOR_SCHEMA_APPROVAL
  -> user approval
  -> Crawl4AI acquisition
  -> cleaning
  -> token-aware chunking
  -> ExtractionRouter
       -> reliable CSS / XPath / regex / table extraction
       -> per-chunk StructuredExtractor fallback
  -> record merge
  -> metadata, entity/relation enrichment, quality, validation, deduplication
  -> JSON or JSONL dataset
```

The source and extraction paths are deliberately separate. Firecrawl discovers candidate URLs; Crawl4AI retrieves selected pages; Groq plans, evaluates supplied candidates, designs a draft schema, and extracts records with an evidence-support score.

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

`DatasetSchemaDesigner` creates a `DraftDatasetSchema`, never a final schema. Its typed input includes the dataset topic and purpose, validated research plan, source policy, explicit schema constraints, and bounded successful previews only for sources chosen by `SourceSelector`. Unselected previews are excluded, and full page acquisition still waits for approval. Normal provenance fields such as source URL, retrieval time, schema version, and contributing chunk IDs are rejected from the domain schema because they belong under record metadata.

The graph then stops at `waiting_for_schema_approval`; it does not scrape or extract data. `DatasetGenerationPipeline.approve_schema()` validates the draft, creates an `ApprovedDatasetSchema` with `schema_version`, `approved_at`, and `approved_by`, then resumes the same graph from acquisition. The persisted review checkpoint retains the research plan, policy, registry, previews, evaluations, final selections/metrics, and exact schema-design input across an edit or process restart.

The terminal runner writes the draft to `knowledge/review/<domain>_draft_schema.json`. You can add, remove, rename, or edit fields there before choosing the reload-and-approve option. Every field supports `field_name`, `type`, `required`, `nullable`, `is_array`, `description`, and `extraction_instruction`. The valid types are `string`, `integer`, `number`, `boolean`, `array`, and `object`.

## Groq Tasks

Each task has an isolated system prompt in `src/agents/prompts/agents_prompts.py` and a structured Pydantic output model.

- `ResearchPlanner` creates the research strategy and queries; it does not search the web.
- `SourceEvaluator` characterizes and policy-evaluates only supplied candidate URLs; it cannot create or modify a URL.
- `SourceSelector` deterministically chooses eligible, useful, non-duplicate sources with bounded domain/type diversity preferences.
- `DatasetSchemaDesigner` creates a topic-specific draft schema; it does not approve it or extract data.
- `StructuredExtractor` uses only the approved schema and clean source content; it does not invent unsupported facts.

`src/tools/groq_client.py` owns reusable Groq connectivity, JSON parsing, timeout configuration, and bounded retries. Semantic record extraction does not import it directly: `StructuredGenerationProvider` is the application boundary, and `GroqStructuredProvider` is the initial adapter. Other pre-existing planning/evaluation/design nodes will remain direct Groq callers until their own provider migration is explicitly phased.

For semantic extraction, `GROQ_STRUCTURED_OUTPUT_MODE=auto` first submits the Pydantic JSON Schema in strict mode. It falls back to JSON-object mode only when the provider explicitly reports that JSON Schema/structured output is unsupported; authentication, invalid schema, timeout, validation, and other failures remain visible. Set the mode to `json_schema` to require strict support or `json_object` to skip the strict attempt. Pydantic validation remains mandatory in every mode.

## Web Provider Tasks

`FirecrawlDiscoveryProvider` performs real web search and normalizes results into provider-neutral discovered sources. It does not decide source quality or retrieve the selected pages.

`Crawl4AIAcquisitionProvider` is the primary page-level acquisition engine. Before source selection, it returns a bounded `SourcePreview`; after schema approval, it returns `AcquiredDocument` with raw Markdown, fit Markdown when available, HTML, title, domain, internal/external links, retrieval metadata, a SHA-256 content hash, and preserved failure details. Crawl4AI's async browser lifecycle and SDK result objects remain behind this internal boundary. Page timeout, cache mode, headless behavior, pruning threshold, preview word limit, and the runtime cache directory are configured through `.env.example`.

After approval, the acquisition node sends all final selected URLs through the provider's `acquire_many` contract. Crawl4AI uses one browser lifecycle, bounded concurrency (`CRAWL4AI_BATCH_CONCURRENCY`, default 4), and a configurable request-start delay (`CRAWL4AI_BATCH_DELAY_SECONDS`, default 0.25). Results return in request order. A failed source remains a full failed `AcquiredDocument` with its URL/error while other successful pages continue; the pipeline stops only if the entire batch fails.

Full normalized documents are preserved in `acquired_documents` as the Bronze layer. Only successful documents enter the existing `raw_data`/`scraped_documents` processing projection. `acquisition_metrics` records requested, successful, failed, and cache-hit URL counts plus batch duration. This is provider-neutral state; no Crawl4AI crawler/session object crosses the boundary.

## Deterministic Content Processing

`processing_node.py` creates a separate Silver `ProcessedDocument` for every successful Bronze input. Processing normalizes Unicode/newlines, repeated spaces, and excess blank lines; removes only conservative whole-line boilerplate such as cookie controls, navigation-only labels, and copyright footers; and preserves Markdown headings, list indentation, table rows, fenced-code whitespace, and source evidence text. The transformation is deterministic and idempotent—no LLM summarizes or rewrites source content.

Each Silver record retains Bronze raw content and its original content hash, plus processed content, a separate processed hash, word count, removed-boilerplate count, metadata, and an `usable`/`thin`/`empty` status. `CONTENT_MIN_WORDS` (default 30, overridable by request `processing.minimum_words`) marks short documents as `thin` without discarding them. Empty documents are recorded and excluded from chunking; other sources continue. Bronze `acquired_documents` are never overwritten.

Neither web provider determines dataset fields, evidence confidence, or final record validity.

## Extraction Routing

`extraction_router_node.py` makes one observable decision per processed source before semantic extraction. A complete Markdown table can be selected automatically only when its headers map uniquely to the approved schema's required fields and the page does not contain substantial prose outside the table. CSS, XPath, and regex routes require explicit request rules; the application never guesses selectors or regexes from a few examples.

Explicit CSS/XPath rules run through Crawl4AI's non-LLM extraction strategies against preserved Bronze HTML. Regex rules run through Crawl4AI against Silver text. Every deterministic record must contain the approved required fields, pass deterministic type conversion, contain no unknown fields, and have exact source evidence for every populated value. An empty, incomplete, ill-typed, or unsupported result is not accepted: the route records `fallback_from` and the source's chunks go to semantic extraction.

State exposes `extraction_routes`, `deterministic_extraction_results`, and `extraction_routing_metrics`, including route reasons, rule IDs, method counts, fallbacks, deterministic record count, and avoided model calls. `extraction_method` survives chunk output and merge into final `_metadata.extraction_methods`. Successful deterministic records have evidence-support `1.0` because their typed values are exact source substrings; this is not a provider probability.

An optional explicit CSS rule is configured like this:

```yaml
extraction:
  router:
    enabled: true
    auto_table: true
    rules:
      - id: catalog-cards
        method: css
        url_pattern: /catalog/
        schema:
          name: catalog_cards
          baseSelector: .card
          fields:
            - {name: item_name, selector: h2, type: text}
            - {name: description, selector: p, type: text}
```

XPath uses the same schema shape with XPath selectors. Regex rules use `patterns`, keyed only by approved field names. Rule order is deterministic and the first URL match wins.

## Multi-Record Extraction

The canonical extraction output is `ExtractionBatch`, not one `ExtractionResult` per chunk. Each batch identifies its source, segment, and chunk and contains `records[]` plus batch warnings. A record carries a stable local record ID, dynamic `data`, confidence, field confidence/evidence, source/chunk identifiers, and extraction method. Empty pages may validly return zero records; a chunk may return one or any number of records. There is no hidden first-record slice or implicit record limit.

Both router branches produce the same batch contract. Deterministic tables/cards can emit every matched row/card; semantic generation is explicitly asked for zero, one, or every distinct supported record. A malformed item in a provider batch becomes an extraction warning while other valid records remain available. The transitional `chunk_extraction_results` projection exists only for compatibility with older checkpoints/callers.

Downstream merge, metadata, quality, validation, deduplication, and export process records individually. Records without a schema identity field remain distinct through `local_record_id`; same-identity candidates merge while retaining all contributing record/chunk IDs and unique field evidence. The frozen eight-page/12-record contract benchmark round-trips all records with no truncation; it is a representation-capacity test, not a live-provider quality claim.

## Field Evidence Contract

`field_evidence_node.py` runs after extraction and before record merge. Raw provider/deterministic candidates remain in `extraction_batches`; the node writes a separate `evidenced_extraction_batches` Silver layer containing only source-bound candidates. Every retained evidence reference contains the canonical source URL, the actual chunk ID, and an exact text slice from supplied chunk content. Deterministic source-level records may bind a value to another chunk from the same source; semantic records may derive missing literal evidence only from the chunk supplied to that model call.

If a populated optional field has no traceable evidence, it becomes `null` only when the approved field is nullable and is otherwise omitted. A missing or unsupported required field quarantines the whole candidate before merge and records the reason under `evidence_rejections` and `rejected_records`. Evidence is retained through merge, metadata, exact-data deduplication, validation, and JSON/JSONL export. The frozen Phase 17 benchmark proves all 12 gold records and all 35 populated fields retain source-traceable evidence; this does not yet assign the Phase 18 support statuses or final evidence quality score.

## Evidence Validation and Quality Gate

`evidence_validation_node.py` treats extraction output as candidate data and independently checks approved-schema fields, source/chunk existence, exact evidence traceability, required-field completeness, and value types. Each candidate receives `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, or `CONTRADICTED`; field-level results explain the decision. Literal checks resolve deterministic cases. Traceable evidence that cannot establish literal support is marked for semantic review rather than being silently accepted; optional semantic verification remains disabled until its owner-managed prompt is approved.

`quality_gate_node.py` computes a final evidence-quality score from schema validity, required-field completeness, evidence support rate, source score, provenance completeness, and the currently explicit `not_evaluated` duplicate status. Extractor confidence is deliberately absent from these components. By default, only `SUPPORTED` records scoring at least `MINIMUM_EVIDENCE_QUALITY` continue to merge; `ALLOW_PARTIALLY_SUPPORTED=false` keeps ambiguous records out of Gold. Phase 20 will upgrade duplicate assessment, so Phase 18 does not claim unevaluated candidates are unique.

## Cross-Source Record Resolution

`record_resolution_node.py` runs after the evidence quality gate. The human-approved schema may declare `identity_fields`; one field uses explicit identity resolution and multiple fields form a composite identity. Identity values are normalized conservatively with Unicode NFKC, case folding, and whitespace collapse. When no explicit identity is configured, only generic scalar ID/code/SKU/name/title field conventions are eligible for normalized matching. If no reliable identity exists—or any configured identity component is absent—the candidate remains distinct by its source-scoped local record ID.

A resolved record retains `source_urls`, source titles, globally scoped contributor objects, all unique field evidence, all contributing chunk/local IDs, quality assessments, and unresolved scalar conflicts. Conflict selection still follows the existing field-confidence rule; Phase 19 does not change confidence fallback or merge thresholds. The saved Phase 19 benchmark resolves two sources for one item while preserving both evidence paths and the conflicting alternative value.

## Staged Deduplication

Final accepted records pass through three deterministic stages in order: canonical source URL/content hash plus normalized record, exact normalized record across sources, and compatible schema-identity subset removal. String normalization uses Unicode NFKC, case folding, and whitespace collapse; array order remains significant. A shared page or content hash never collapses different record data, so multi-record pages remain intact.

When duplicate records are found, the stronger evidence-quality/completeness representative is retained while every URL, title, content hash, contributor, chunk/record ID, evidence reference, quality assessment, and prior conflict is merged into its metadata. Same-identity records with conflicting values are retained as identity conflicts rather than losing data. Semantic/vector near-duplicate detection is intentionally not included. `deduplication_metrics` reports each stage, retained identity conflicts, and the remaining exact duplicate rate; the frozen Phase 20 benchmark reaches `0.00`.

## Candidate Registry

`source_registry` is keyed by a conservative canonical URL. The registry lowercases only scheme/host, removes default ports and fragments, normalizes an empty root path, and preserves differences that may change server behavior: HTTP versus HTTPS, path case, query values/order, and trailing slashes on non-root paths. The first discovered title/description can be completed by later discoveries without losing any original URL.

Every canonical candidate retains all search queries, seed origin, providers, preview/evaluation status, selection state, and rejection reasons. `candidate_sources` is a compatibility projection of that registry, so candidate counts and source metrics count canonical resources rather than repeated query hits. A completed preview remains completed when another query discovers the same URL.

## Bounded Source Preview

`source_preview_node.py` runs between discovery and source evaluation. In live mode it asks Crawl4AI for query-aware fit Markdown, falls back to raw Markdown when needed, and exposes only a bounded preview (400 words by default). Headings and structure hints come from raw page structure even when the relevance filter removes Markdown markers. The preview also carries full-page approximate word count, internal/external links, observable language/publication dates, and per-source fetch status.

Preview results are cached in serializable pipeline state by canonical URL. One failed page produces a failed `SourcePreview` and the remaining candidates continue; the evaluator receives that limitation rather than a fabricated success. Preview is evidence for relevance and policy decisions, not full extraction, and full acquired content still enters state only after schema approval.

## Bounded Site Exploration

Optional site exploration runs after initial source evaluation and is disabled by default. When enabled in `site_exploration`, Crawl4AI uses Best-First traversal from at most `max_seed_domains`, with explicit `max_depth`, `max_pages_per_domain`, and `same_domain_only` limits. Both the SDK configuration and the provider's normalized output enforce the page/depth/domain bounds; non-page asset URLs, repeated fragments, cycles, and already explored starts are discarded.

New internal pages enter only the canonical source registry with their start URL, parent URL, and depth recorded as a `site_exploration` discovery origin. They remain pending—not automatically evaluated, selected, scraped, or extracted. This stage is bounded source expansion, not continuous research or AdaptiveCrawler sufficiency logic.

## Policy-Aware Source Evaluation

`SourceEvaluator` now separates reusable characterization from request-specific evaluation. A `SourceProfile` describes observed source type, content characteristics/depth, authority signals, and bounded density/technical/recency/extractability scores. `EvaluatedSource` then records topic relevance, policy alignment, final score, explicit hard-policy status, decision, reasons, and whether preview evidence was available.

The model proposes only evidence-based profiles and topic relevance for every supplied URL. Application code recomputes policy alignment, final score, explicit hard-rule rejection, and decision. Allowed/blocked domains and source types plus minimum content depth are hard only when configured. Preferred domains/types, desired/avoided content, and importance weights adjust ranking without rejecting alternatives. No source gets an automatic government, academic, official, or independent-source bonus.

The same frozen 24-candidate, two-policy benchmark improved from `0.520833` to `0.75` policy-alignment accuracy and from `0.25` to `0.0` hard-policy violation rate. Average P@5 improved from `0.40` to `0.90`, and P@10 from `0.35` to `0.70`. These are deterministic fixture results, not a claim about live-provider quality.

## Policy-Aware Source Selection

`SourceSelector` is a separate deterministic graph node after optional site exploration. It accepts only evaluated sources whose decision is `select`, whose preview succeeded, and which were not hard-rejected. It ranks them from final policy score, information density, extractability, and request-weighted technical depth. Preferred source types remain soft signals; they never become an eligibility filter.

Selection favors a new domain or useful source type only when its request-specific quality remains within a bounded band of the best remaining source. This prevents blind top-N domination without forcing weak sources to satisfy a quota. Identical successful preview text is treated as an exact duplicate, with the stronger representative retained. State records rank, selection score, reasons, selected counts, unique domains, domain/type distributions, and duplicate counts.

On the same frozen 24-candidate/two-policy set at a five-source limit, selection precision improved from `0.90` to `1.00`, duplicate selection fell from `0.10` to `0.00`, average maximum-domain share fell from `0.40` to `0.30`, and hard-policy violations remained `0.00`. Site-exploration pages discovered after initial evaluation remain pending and therefore cannot bypass evaluation or selection in the current pass.

## Confidence, Validation, and Metadata

Confidence is not a native Groq probability. It is an extractor diagnostic: a reliable deterministic route uses `1.0` only after every typed value is proven as exact source evidence; semantic extraction preserves the score returned by `StructuredExtractor`. If a provider omits only the summary but returns valid `field_confidence` values, the extraction boundary uses the arithmetic mean for populated fields; omitted optional fields do not affect that fallback. This does not change conflict/merge behavior. Once the Phase 18 evidence quality gate has run, final acceptance excludes extractor confidence and later schema validation does not reapply the legacy confidence threshold. Direct legacy callers that bypass the evidence gate retain their existing `minimum_confidence` behavior.

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
  router:
    enabled: true
    auto_table: true
    rules: []
  chunking:
    enabled: true
    target_tokens: 6000
    overlap_tokens: 300
quality:
  minimum_confidence: 0.70
  minimum_evidence_quality: 0.70
  allow_partially_supported: false
output:
  format: json
  profiles: [structured, rag, graphrag]
```

The editable approved-schema JSON can optionally declare identity fields:

```json
{
  "identity_fields": ["manufacturer", "model_code"]
}
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

`DATA_SOURCE_PROVIDER=mock` is the default offline mode. It uses configured sources and deterministic extraction, so unit tests never need API keys or network access. Set `DATA_SOURCE_PROVIDER=firecrawl` and provide both `FIRECRAWL_API_KEY` and `GROQ_API_KEY` to use live Firecrawl discovery, Crawl4AI acquisition, and Groq calls.

## Installation and Usage (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-baseline.txt
$env:CRAWL4_AI_BASE_DIRECTORY=(Join-Path (Get-Location) ".runtime")
.\.venv\Scripts\crawl4ai-setup.exe
.\.venv\Scripts\crawl4ai-doctor.exe
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run_domain_test.py --domain turkish_culture
```

`crawl4ai-setup` installs the Playwright browser runtime required for real page acquisition. Crawl4AI's database and cache default to the repository-local, gitignored `.runtime/.crawl4ai` directory rather than an implicit user-home directory. The legacy broad `requirements.txt` is retained for later dependency cleanup; `requirements-baseline.txt` is the current reproducible project environment.

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

The browser-backed Crawl4AI acceptance test uses only local HTML fixtures. After
running `crawl4ai-setup`, enable it explicitly:

```powershell
$env:RUN_CRAWL4AI_BROWSER_TESTS="true"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_crawl4ai_local_browser.py -q
```

## Example Workflow

For the topic `Traditional Turkish coffee culture`, ResearchPlanner proposes historical, preparation, and social-tradition queries. Firecrawl finds candidate sources. SourceEvaluator selects trustworthy candidates. DatasetSchemaDesigner proposes fields, for example `content` or topic-specific fields such as `preparation_method`. The user edits and approves the draft. Crawl4AI acquires selected pages, StructuredExtractor produces only source-supported field values and confidence, validation rejects weak records, and export writes the accepted records.

## Structured Output Example

```json
{
  "data": {
    "content": "Source-supported factual content."
  },
  "evidence": {
    "content": [
      {
        "source_url": "https://example.org/source",
        "chunk_id": "source_001_chunk_001",
        "evidence_text": "Source-supported factual content."
      }
    ]
  },
  "provenance": {
    "source_url": "https://example.org/source",
    "source_urls": ["https://example.org/source"],
    "resolution_method": "explicit_identity"
  },
  "quality": {
    "evidence_quality_score": 0.88,
    "support_statuses": ["SUPPORTED"]
  },
  "schema": {
    "name": "example_records",
    "schema_version": 1,
    "identity_fields": ["content"]
  },
  "_metadata": {
    "source_url": "https://example.org/source",
    "source_urls": ["https://example.org/source"],
    "source_title": "Example source",
    "source_provider": "crawl4ai",
    "schema_version": "1",
    "confidence_score": 0.94,
    "evidence_quality_score": 0.88,
    "evidence_support_statuses": ["SUPPORTED"],
    "resolution_method": "explicit_identity",
    "contributors": [
      {
        "source_url": "https://example.org/source",
        "local_record_id": "source_001_chunk_001:record:0001",
        "chunk_id": "source_001_chunk_001",
        "extraction_method": "semantic"
      }
    ],
    "field_evidence": {}
  }
}
```

## Future UI

No frontend is included. A future interface can observe `pipeline_status` and state fields to show the research plan, candidate and selected sources, draft schema editor, approval action, scraping and extraction progress, validation decisions, errors, and final dataset. The same `approve_schema()` domain operation can be called from an Approve button instead of the current terminal interaction.
