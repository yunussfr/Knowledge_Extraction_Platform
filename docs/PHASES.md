# PHASES.md

# Knowledge Extraction Platform — Current Iteration Development Phases

## 1. Objective

This plan evolves the existing platform into a request-aware, Crawl4AI-enabled, evidence-backed dataset generation system for AI projects.

System prompt wording is intentionally managed separately and is not part of these phases.

---

# Phase 0 — Environment and Baseline

## Goal

Establish a runnable baseline.

## Tasks

- [ ] confirm supported Python version
- [ ] create clean environment
- [ ] make offline tests runnable
- [ ] record canonical test command
- [ ] run current mock pipeline
- [ ] run one opt-in real pipeline if keys are available
- [ ] save baseline metrics

Record:

```text
queries
candidate URLs
selected URLs
unique domains
scraped sources
chunks
extraction results
accepted records
rejected records
errors
runtime
model calls if measurable
```

## Acceptance Gate

- [ ] tests run in a clean environment
- [ ] baseline is reproducible
- [ ] existing failures are documented

---

# Phase 1 — Policy-Aware Gold Evaluation Set

## Goal

Create a fixed benchmark for source evaluation and extraction.

This is not a model-training dataset.

---

## 1.1 Source Evaluation Set

Prepare 20–30 candidates containing:

```text
high-authority + deep + relevant
high-authority + shallow + relevant
high-authority + irrelevant

independent + deep + relevant
independent + shallow

university + useful
university + irrelevant

official + useful
official + shallow

thin page
duplicate page
useful non-seed domain

candidate matching optional allowed source type
candidate matching optional blocked source type
```

Source type must not imply quality by itself.

---

## 1.2 Multiple SourcePolicy Fixtures

Evaluate the same candidate set under at least two policies.

### Policy A

```yaml
source_policy:
  desired_content:
    - technical_explanation
    - implementation_details

  importance:
    authority: low
    technical_depth: high
    information_density: high
```

No hard source-type restrictions.

### Policy B

```yaml
source_policy:
  allowed_source_types:
    - academic
    - government
    - university

  importance:
    authority: high
    technical_depth: medium
```

The same source may legitimately receive different outcomes.

---

## 1.3 Extraction Gold Set

Prepare 5–10 representative pages with manually known expected records and evidence.

Must include:

```text
zero-record page
single-record page
many-record page
repeated DOM cards
table
long prose
missing optional fields
duplicate information
```

---

## 1.4 Metrics

Implement:

```text
source precision@5
source precision@10
policy-alignment accuracy
hard-policy violation rate

record precision
record recall
field precision
field recall

schema-valid rate
unsupported-field rate
duplicate rate
```

## Acceptance Gate

- [ ] evaluation results are reproducible
- [ ] baseline is saved
- [ ] same source can be evaluated under multiple SourcePolicies

---

# Phase 2 — SourcePolicy and Request Configuration

## Goal

Make source requirements explicit, optional, and user-controlled.

---

## 2.1 Add SourcePolicy Models

Suggested:

```python
class SourceImportance(BaseModel):
    authority: str = "medium"
    technical_depth: str = "medium"
    information_density: str = "medium"
    recency: str = "medium"
    extractability: str = "medium"


class SourcePolicy(BaseModel):
    preferred_source_types: list[str] = Field(default_factory=list)

    allowed_source_types: list[str] | None = None
    blocked_source_types: list[str] | None = None

    desired_content: list[str] = Field(default_factory=list)
    avoided_content: list[str] = Field(default_factory=list)

    minimum_content_depth: str | None = None

    importance: SourceImportance = Field(default_factory=SourceImportance)
```

---

## 2.2 Semantics

Implement exactly:

```text
preferred_source_types absent/empty
    -> no source-type preference

allowed_source_types absent/empty
    -> no allowlist

blocked_source_types absent/empty
    -> no blocklist

desired_content absent/empty
    -> no desired-content preference

avoided_content absent/empty
    -> no avoided-content preference

minimum_content_depth absent
    -> no hard depth minimum
```

---

## 2.3 Domain Semantics

Ensure request config separates:

```text
seed_urls
preferred_domains
allowed_domains
blocked_domains
```

with:

```text
seed_urls -> references
preferred_domains -> soft
allowed_domains -> optional hard
blocked_domains -> optional hard
```

---

## 2.4 Request Examples

Update example request YAML files to show optional fields as optional.

Do not force users to write `allowed_source_types` or `blocked_source_types`.

---

## 2.5 Deterministic Validation

Parse request policy with typed config validation.

Do not use an LLM for YAML semantics.

---

## 2.6 Tests

Add:

```text
neutral policy
preferred types only
allowed types only
blocked types only
desired content only
avoided content only
technical-depth-heavy policy
minimum depth omitted
allowed/blocked conflict
all optional source-type fields omitted
```

## Acceptance Gate

A request can omit all source-type restrictions without hidden filtering.

---

# Phase 3 — ResearchPlanner Contract Integration

## Goal

Pass SourcePolicy and dataset purpose into planner inputs/outputs.

System prompt wording is not part of this phase.

## Tasks

- [ ] add SourcePolicy to planner input
- [ ] preserve optional fields exactly
- [ ] support non-duplicate query families
- [ ] preserve seed URL semantics
- [ ] preserve hard domain restrictions
- [ ] ensure absent source restrictions remain absent

## Tests

- [ ] neutral policy survives planner boundary
- [ ] technical-depth policy is available
- [ ] strict source-type restrictions are available
- [ ] absent blocklist is not synthesized

## Acceptance Gate

ResearchPlanner has all request context needed for policy-aware planning.

---

# Phase 4 — Web Provider Abstraction

## Goal

Add Crawl4AI without coupling graph nodes directly to it.

## Suggested Structure

```text
src/tools/web/
├── __init__.py
├── models.py
├── discovery_provider.py
├── acquisition_provider.py
├── firecrawl_provider.py
└── crawl4ai_provider.py
```

## Tasks

Create:

```text
SourceDiscoveryProvider
WebAcquisitionProvider
```

Initial implementations:

```text
FirecrawlDiscoveryProvider
Crawl4AIAcquisitionProvider
```

Keep legacy adapters until migration is proven safe.

## Acceptance Gate

Graph nodes depend on internal contracts, not provider-specific result objects.

---

# Phase 5 — Crawl4AI Single-Page Acquisition

## Goal

Make Crawl4AI the primary page-level acquisition engine.

## Tasks

- [ ] add Crawl4AI dependency
- [ ] document setup
- [ ] implement `acquire`
- [ ] normalize into `AcquiredDocument`
- [ ] preserve raw Markdown
- [ ] preserve fit/clean Markdown
- [ ] preserve title/domain/link metadata
- [ ] compute content hash
- [ ] preserve fetch failures
- [ ] configure timeout/cache

## Tests

Use local HTML fixtures for:

```text
normal page
empty page
noisy page
Turkish/Unicode content
headings
lists
tables
duplicate content
provider failure
```

## Acceptance Gate

Downstream nodes never need Crawl4AI-specific result types.

---

# Phase 6 — Candidate Registry and URL Normalization

## Goal

Deduplicate candidate work and preserve discovery history.

## Tasks

Create canonical registry preserving:

```text
canonical URL
original URLs
domain
search origins
seed origin
preview state
evaluation state
selection state
rejection reasons
```

Normalize conservatively.

## Tests

- [ ] same URL from multiple queries becomes one candidate
- [ ] origins survive
- [ ] seed + search origin survive
- [ ] duplicate preview work is avoided

## Acceptance Gate

Metrics represent canonical candidates.

---

# Phase 7 — Crawl4AI SourcePreview

## Goal

Provide real bounded source evidence to SourceEvaluator.

## SourcePreview Fields

```text
url
title
domain
headings
bounded relevant text
approximate word count
preview word count
internal links
external links
language
publication/update date when observable
structure hints
fetch status
```

## Tasks

- [ ] use clean/fit Markdown
- [ ] bound preview size
- [ ] cache preview result
- [ ] continue gracefully on preview failure

## Acceptance Gate

SourceEvaluator receives real page evidence.

---

# Phase 8 — Bounded Crawl4AI Site Exploration

## Goal

Discover related internal pages from useful seed/selected domains.

Use bounded Best-First / Deep Crawl.

Do not implement AdaptiveCrawler research sufficiency.

## Config

```yaml
site_exploration:
  enabled: true
  max_seed_domains: 5
  max_depth: 2
  max_pages_per_domain: 25
  same_domain_only: true
```

## Tasks

- [ ] implement `explore_site`
- [ ] enforce limits
- [ ] normalize discovered URLs
- [ ] preserve site-exploration origin
- [ ] avoid repeated exploration

## Tests

Verify:

```text
max depth
max pages
same domain
URL filtering
duplicate links
no infinite loops
```

## Acceptance Gate

A useful seed can discover related pages without unbounded crawling.

---

# Phase 9 — Policy-Aware Source Evaluation and Characterization

## Goal

Make source evaluation request-specific.

Do not create a separate SourceClassifier node.

---

## 9.1 SourceProfile

Add fields such as:

```text
source_type
content_characteristics
content_depth
authority_signals
information_density_score
technical_depth_score
recency_score
extractability_score
```

---

## 9.2 Request-Specific Evaluation

Add:

```text
topic_relevance_score
policy_alignment_score
final_score
hard_policy_rejected
decision
reasons
```

---

## 9.3 Hard Rules

Enforce only when configured:

```text
allowed_source_types
blocked_source_types
minimum_content_depth
allowed_domains
blocked_domains
```

---

## 9.4 Soft Signals

Use for ranking:

```text
preferred_source_types
preferred_domains
desired_content
avoided_content
importance values
```

---

## 9.5 Tests

Verify:

- [ ] shallow official can lose to deep independent under technical-depth-heavy policy
- [ ] independent source is not penalized under neutral policy
- [ ] allowed types apply only when provided
- [ ] blocked types apply only when provided
- [ ] preferred types do not hard-reject alternatives
- [ ] same source may score differently under different policies
- [ ] preview failure is visible

## Acceptance Gate

Source evaluation reflects the request rather than a universal hierarchy.

---

# Phase 10 — Source Selection and Diversity

## Goal

Select useful, eligible, diverse sources.

## Inputs

Consider:

```text
hard eligibility
topic relevance
policy alignment
information density
technical depth when relevant
extractability
duplicate status
domain diversity
source-type diversity when useful
```

## Tests

- [ ] one domain does not dominate blindly
- [ ] hard-rejected sources are never selected
- [ ] preferred type is not treated as mandatory
- [ ] unique-domain metrics are correct

## Acceptance Gate

Selection is explainable and policy-aware.

---

# Phase 11 — Evidence-Aware Dataset Schema Design

## Goal

Use request policy and representative source previews during draft schema creation.

System prompt wording is managed separately.

## Inputs

```text
dataset topic
AI purpose
ResearchPlan
SourcePolicy
selected SourcePreviews
user schema constraints
```

## Tasks

- [ ] keep provenance metadata outside normal domain schema
- [ ] preserve human approval
- [ ] preserve research state during edit/resume

## Acceptance Gate

Schema design uses real source evidence and request context.

---

# Phase 12 — Crawl4AI Multi-Source Acquisition

## Goal

Acquire selected sources efficiently after approval.

## Tasks

Implement `acquire_many` with:

- bounded concurrency
- throttling
- failure isolation
- caching
- per-source provenance

## Metrics

```text
requested_urls
successful_urls
failed_urls
cache_hits
acquisition_duration
```

## Acceptance Gate

Batch acquisition is provider-abstracted.

---

# Phase 13 — Deterministic Content Processing

## Goal

Reduce noise while preserving evidence.

## Tasks

- [ ] normalize whitespace
- [ ] preserve headings
- [ ] preserve lists
- [ ] preserve tables
- [ ] reduce boilerplate
- [ ] detect empty/thin pages
- [ ] keep raw and processed versions
- [ ] preserve content hash

## Acceptance Gate

Processed content is cleaner without losing benchmark evidence.

---

# Phase 14 — Extraction Router

## Goal

Avoid unnecessary LLM calls.

## Routes

```text
CSS
XPath
Regex
table
semantic structured model
```

## Tasks

- [ ] use Crawl4AI deterministic extraction when reliable
- [ ] fall back to semantic extraction when necessary
- [ ] record extraction method

## Tests

Use fixtures for repeated cards, tables, XPath, regex, and prose.

## Acceptance Gate

At least one benchmark source is extracted correctly without an LLM.

---

# Phase 15 — Multi-Record Extraction Contract

## Goal

Remove one-record-per-chunk behavior.

## Contract

Use:

```text
ExtractionBatch.records[]
```

Each record carries:

```text
data
field evidence
source identifiers
chunk/segment identifiers
extraction method
```

## Tests

```text
0 records
1 record
2 records
many records
mixed valid/invalid
missing optional
missing required
wrong type
repeated evidence
duplicate candidate
```

## Downstream Migration

Update:

```text
merge
metadata
validation
quality
dedup
export
metrics
```

## Acceptance Gate

No code path caps a chunk to one record.

---

# Phase 16 — StructuredGenerationProvider

## Goal

Remove direct Groq dependency from semantic extraction.

## Suggested Structure

```text
src/tools/structured_generation/
├── __init__.py
├── base.py
└── groq_provider.py
```

Future optional:

```text
local_provider.py
```

## Tasks

- [ ] define provider interface
- [ ] adapt Groq
- [ ] keep Pydantic output contract
- [ ] use strict JSON Schema where supported
- [ ] preserve application validation
- [ ] isolate unsupported-model fallback

## Acceptance Gate

Semantic extractor depends on provider interface, not Groq directly.

---

# Phase 17 — Field Evidence Contract

## Goal

Make factual output traceable.

## Evidence

Include:

```text
source_url
chunk_id
evidence_text
```

## Required Behavior

- [ ] evidence must originate from supplied content
- [ ] unsupported optional follows schema null/omit policy
- [ ] unsupported required field prevents valid emission
- [ ] evidence survives downstream processing

## Acceptance Gate

Gold records preserve usable evidence.

---

# Phase 18 — Evidence Validation and Quality Gate

## Goal

Separate extraction from acceptance.

## Deterministic Checks

```text
schema validity
source existence
chunk existence
evidence traceability
required-field completeness
field types
```

Optional semantic verification only where deterministic checks are insufficient.

## Statuses

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTED
```

## Quality Components

```text
required-field completeness
evidence support rate
source score
provenance completeness
duplicate status
```

Do not use extractor self-confidence as final quality.

## Acceptance Gate

Suggested:

```text
unsupported accepted field rate < 0.05
```

---

# Phase 19 — Cross-Source Record Resolution

## Goal

Merge records representing the same real-world item without destroying provenance.

## Identity Stages

```text
explicit schema identity
normalized identity
composite identity
```

Preserve:

```text
all source URLs
field evidence
conflicting values
contributor IDs
```

## Acceptance Gate

A resolved record may preserve support from multiple sources.

---

# Phase 20 — Deduplication Upgrade

## Goal

Remove repeated data safely.

## Stages

```text
canonical URL/content hash
exact normalized record
schema-aware identity
```

Semantic near-duplicate detection remains optional later.

## Acceptance Gate

Suggested:

```text
exact duplicate rate < 0.03
```

---

# Phase 21 — AI Output Profiles

## Goal

Produce downstream-specific output.

### Structured

```text
data
evidence
provenance
quality
schema metadata
```

### RAG

```text
text
title
source URL
section path
chunk ID
language
content hash
quality score
```

### GraphRAG Preparation

Only evidence-backed claims/entities/relations.

Do not implement Domain Knowledge Map.

## Acceptance Gate

Structured and RAG outputs are intentionally different.

---

# Phase 22 — Run Metrics and Manifest

## Goal

Make behavior observable.

### SourcePolicy Metrics

```text
source_types_observed
content_characteristics_observed
policy_alignment_score_distribution
hard_policy_rejections
preferred_type_selection_rate
desired_content_match_rate
selected_sources_by_type
```

### Source Metrics

```text
queries_generated
raw_search_results
unique_candidates
unique_candidate_domains
preview_successes
preview_failures
selected_sources
unique_selected_domains
site_exploration_pages
```

### Acquisition

```text
requested_urls
successful_urls
failed_urls
cache_hits
total_words
total_content_tokens
```

### Extraction / Validation

```text
deterministic_extractions
semantic_extractions
records_extracted
records_per_chunk
schema_valid_records
supported_fields
unsupported_fields
accepted_records
rejected_records
duplicate_records
```

### Cost / Performance

```text
model_calls
input_tokens
output_tokens
latency
estimated_cost
```

## Acceptance Gate

A run can be diagnosed without reading low-level debug logs.

---

# Phase 23 — Cost and Token Optimization

## Goal

Reduce model usage after correctness is established.

Measure:

```text
average preview size
average extraction input tokens
LLM calls per source
accepted records per LLM call
cost per accepted record
```

Potential optimizations:

- stronger fit Markdown
- more deterministic extraction
- smaller models for simple tasks
- safe batching
- model routing

Do not reduce benchmark quality blindly.

---

# Phase 24 — Optional Local Model Evaluation

## Goal

Determine whether local semantic extraction is useful.

## Preconditions

- provider abstraction exists
- gold benchmark exists
- cloud baseline exists
- evidence validation exists

## Architecture

```text
Deterministic Extraction
        |
        v
Local Structured Provider
        |
supported + valid?
    /          \
  yes           no
  save          cloud fallback
```

Compare on the same benchmark:

- record precision/recall
- field precision/recall
- unsupported-field rate
- schema validity
- latency
- cost

## Acceptance Gate

Use local-first routing only if benchmark results justify it.

---

# Phase 25 — Reliability Hardening

## Goal

Make larger runs resumable and robust.

## Tasks

- [ ] source-level checkpoint
- [ ] chunk-level retry
- [ ] bounded provider retries
- [ ] timeouts
- [ ] acquisition cache
- [ ] idempotent resume
- [ ] failure isolation
- [ ] memory-pressure tests
- [ ] Crawl4AI concurrency tuning
- [ ] rate-limit handling

## Acceptance Gate

Interrupted runs resume without duplicating accepted records or repeating all completed work.

---

# Phase 26 — Documentation and Cleanup

## Goal

Make the new architecture canonical.

## Tasks

- [ ] update README
- [ ] document SourcePolicy semantics
- [ ] document optional source-type fields
- [ ] document Firecrawl vs Crawl4AI responsibilities
- [ ] document provider abstraction
- [ ] document benchmark command
- [ ] document output profiles
- [ ] mark obsolete docs historical/superseded
- [ ] audit legacy directories before deletion
- [ ] curate dependencies carefully

## Acceptance Gate

A new developer/agent can identify the canonical system without guessing.

---

# Phase 27 — Current Iteration Final Acceptance

The iteration is complete when:

```text
AI dataset topic
    +
downstream AI purpose
    +
optional seed URL
    +
optional source requirements
    +
optional content requirements
        |
        v
SourcePolicy
        |
        v
ResearchPlanner
        |
        v
Firecrawl global discovery
        |
        v
CandidateRegistry
        |
        v
Crawl4AI SourcePreview
        |
        v
SourceEvaluator
        |
        +--> source characterization
        +--> request-specific policy evaluation
        |
        v
bounded site exploration
        |
        v
SourceSelector
        |
        v
evidence-aware schema design
        |
        v
human approval
        |
        v
Crawl4AI acquisition
        |
        v
deterministic processing
        |
        v
ExtractionRouter
        |
        v
deterministic or semantic extraction
        |
        v
ExtractionBatch.records[]
        |
        v
field evidence
        |
        v
evidence validation
        |
        v
record resolution
        |
        v
deduplication
        |
        v
structured / RAG export
```

Required final behaviors:

- [ ] seed URLs are references, not boundaries
- [ ] useful non-seed sources can be discovered
- [ ] preferred_domains is soft
- [ ] preferred_source_types is soft
- [ ] allowed_source_types is optional
- [ ] blocked_source_types is optional
- [ ] missing restrictions create no hidden restrictions
- [ ] source evaluation uses real preview content
- [ ] source evaluation is request-specific
- [ ] deep independent source can outrank shallow official source when policy requires it
- [ ] same source can score differently under different SourcePolicies
- [ ] Crawl4AI handles preview/acquisition/bounded exploration
- [ ] deterministic extraction avoids unnecessary LLM use
- [ ] one chunk may produce many records
- [ ] semantic extraction is provider-neutral
- [ ] Groq is not required for every JSON record
- [ ] field evidence is preserved
- [ ] provenance is preserved
- [ ] structured and RAG outputs are usable
- [ ] evaluation and run metrics are visible

---

# Deferred Product Iteration

Do not implement during current phases:

```text
Research Intelligence Platform
Domain Knowledge Map
global coverage controller
information gain
repeated gap-focused research
adaptive research continuation
advanced AdaptiveCrawler sufficiency
conflict map
general research reports
non-AI research workflows
living knowledge projects
```

The current architecture should remain compatible with those later directions.
