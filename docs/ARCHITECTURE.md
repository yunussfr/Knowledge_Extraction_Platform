# ARCHITECTURE.md

# Knowledge Extraction Platform — Current Iteration Architecture

## 1. Purpose

The Knowledge Extraction Platform is an evidence-backed web data acquisition and dataset generation platform for AI projects.

Its current purpose is to take a user-defined data request and produce a trustworthy AI-ready dataset by:

1. understanding the requested topic and downstream AI purpose,
2. discovering useful sources beyond optional seed URLs,
3. evaluating sources according to the user's own source requirements,
4. inspecting real source content before selection,
5. acquiring pages through Crawl4AI,
6. extracting deterministically whenever possible,
7. using semantic LLM extraction only when required,
8. extracting zero, one, or many records from each source segment,
9. preserving evidence and provenance,
10. validating, resolving, and deduplicating records,
11. exporting structured or RAG-oriented outputs.

Current primary use cases:

- RAG systems
- structured knowledge bases
- AI agents
- ML datasets
- fine-tuning preparation
- GraphRAG preparation
- other evidence-backed AI data workflows

The platform is not yet a general-purpose autonomous research product.

---

## 2. Current Iteration Scope

### Included

- request-driven source policy
- research planning
- web-wide source discovery
- optional seed URLs
- optional domain restrictions
- optional source-type preferences and restrictions
- desired content characteristics
- real source preview
- source characterization
- request-specific source evaluation
- bounded Crawl4AI site exploration
- diverse source selection
- human-approved dataset schema
- Crawl4AI acquisition
- clean/fit Markdown
- deterministic extraction
- multi-record semantic extraction
- provider-neutral structured generation
- evidence validation
- provenance
- record resolution
- deduplication
- structured and RAG export
- benchmark-driven model/provider selection
- optional later local-model comparison

### Deferred

Do not implement in this iteration:

- continuous research
- persistent Domain Knowledge Map
- global coverage loops
- repeated gap-focused research rounds
- information-gain research stopping
- advanced AdaptiveCrawler research sufficiency
- general-purpose research reports
- stale-source monitoring
- living research workspaces
- ChatGPT/Manus-style consumer research workflows

---

## 3. Core Architectural Principles

### 3.1 LangGraph remains the orchestrator

LangGraph controls:

- node sequencing
- state transitions
- schema approval pause/resume
- conditional execution
- failures
- future extension

Crawl4AI, Firecrawl, and model providers expose capabilities; they do not control the global pipeline.

### 3.2 AgentState remains serializable

`AgentState` contains data and status only.

Do not store active crawler objects, HTTP clients, callbacks, or locks inside state.

### 3.3 User intent defines source value

Never hard-code:

```text
official > university > independent > blog
```

A source is valuable only relative to:

- dataset topic
- downstream AI purpose
- requested content
- source policy
- hard restrictions
- ranking importance

Example:

```text
authority importance = low
technical depth = high
```

A deep independent technical article may outrank a shallow official page.

### 3.4 Source classification is not source evaluation

Classification answers:

> What is this source?

Evaluation answers:

> How useful is this source for this request?

In the current iteration both are handled inside `SourceEvaluator` to avoid a second LLM call.

There is no separate SourceClassifier agent yet.

### 3.5 Seed URLs are references, not boundaries

A seed URL is a starting point.

Hard restrictions must be explicit.

### 3.6 Deterministic before probabilistic

Prefer:

- CSS
- XPath
- JSON-LD
- tables
- repeated DOM structures
- metadata
- regex
- ordinary parsing

before calling an LLM.

### 3.7 Chunk is not record

A chunk may produce:

```text
0 records
1 record
N records
```

### 3.8 Evidence is stronger than self-confidence

Final quality must come from observable signals, not extractor-generated confidence values.

---

## 4. High-Level Pipeline

```text
User Request
    |
    v
Request Validation + SourcePolicy
    |
    v
ResearchPlanner
    |
    v
Global Source Discovery
(Firecrawl)
    |
    v
Candidate Registry
    |
    v
Crawl4AI Source Preview
    |
    v
SourceEvaluator
    |
    +--> Source Characterization
    |      source_type
    |      content_characteristics
    |      content_depth
    |      authority_signals
    |      technical_depth
    |      information_density
    |      extractability
    |
    +--> Request-Specific Evaluation
           topic_relevance
           policy_alignment
           final_score
           decision
    |
    v
Optional Bounded Site Exploration
(Crawl4AI Best-First / Deep Crawl)
    |
    v
Candidate Registry Update
    |
    v
Source Selector
    |
    v
Dataset Schema Designer
    |
    v
WAITING_FOR_SCHEMA_APPROVAL
    |
    v
User Approves / Edits
    |
    v
Crawl4AI Multi-Source Acquisition
    |
    v
Content Processing
    |
    v
Extraction Router
    |
    +----------------------------+
    |                            |
    v                            v
Deterministic Extraction     Semantic Extraction
CSS/XPath/Regex/Table        StructuredGenerationProvider
    |                            |
    +-------------+--------------+
                  |
                  v
          ExtractionBatch
             records[]
                  |
                  v
           Evidence Validation
                  |
                  v
           Record Resolution
                  |
                  v
             Quality Gate
                  |
                  v
            Deduplication
                  |
                  v
        Structured / RAG Export
```

There is no continuous global research loop in this iteration.

---

## 5. Request Configuration

Recommended request structure:

```yaml
dataset:
  name: "transformer_architecture_dataset"

  topic: "Transformer architectures and attention mechanisms"

  purpose: >
    Build an evidence-backed technical dataset for a RAG system
    used by AI engineers and students.

  profile: "structured"


research:
  max_queries: 10
  max_sources: 40


sources:

  seed_urls:
    - "https://example.com/reference"

  preferred_domains: []

  # OPTIONAL HARD DOMAIN CONTROLS
  #
  # allowed_domains:
  #   - "example.edu"
  #
  # blocked_domains:
  #   - "spam.example"


  source_policy:

    # OPTIONAL SOFT PREFERENCE
    preferred_source_types:
      - "academic"
      - "technical_documentation"
      - "independent_technical"

    # OPTIONAL HARD ALLOWLIST
    #
    # If omitted or empty, there is no source-type allowlist.
    #
    # allowed_source_types:
    #   - "academic"
    #   - "technical_documentation"

    # OPTIONAL HARD BLOCKLIST
    #
    # If omitted or empty, no source type is automatically blocked.
    #
    # blocked_source_types:
    #   - "social_media"

    desired_content:
      - "technical_explanation"
      - "mathematical_derivation"
      - "implementation_details"
      - "benchmarks"

    avoided_content:
      - "marketing"
      - "shallow_summary"
      - "opinion_only"

    # OPTIONAL HARD MINIMUM
    # If omitted, depth is only a ranking signal.
    minimum_content_depth: "medium"

    importance:
      authority: "low"
      technical_depth: "high"
      information_density: "high"
      recency: "medium"
      extractability: "medium"


  site_exploration:
    enabled: true
    max_seed_domains: 5
    max_depth: 2
    max_pages_per_domain: 25
    same_domain_only: true


schema:
  require_user_approval: true


extraction:
  deterministic_first: true

  chunking:
    enabled: true
    target_tokens: 6000
    overlap_tokens: 300


quality:
  require_evidence: true
  minimum_record_score: 0.75


output:
  format: "json"
```

---

## 6. SourcePolicy Contract

Suggested model:

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

Semantics:

```text
preferred_source_types absent/empty
    -> no source-type ranking preference

allowed_source_types absent/empty
    -> no source-type allowlist

blocked_source_types absent/empty
    -> no source-type blocklist

desired_content absent/empty
    -> no desired-content preference

avoided_content absent/empty
    -> no avoided-content preference

minimum_content_depth absent
    -> no hard minimum
```

Do not invent constraints that the user did not provide.

---

## 7. Domain Policy

Domain policy is separate from source-type policy.

```text
seed_urls
    references / starting points

preferred_domains
    soft ranking preference

allowed_domains
    optional hard allowlist

blocked_domains
    optional hard blocklist
```

`preferred_domains` must never become a hidden hard filter.

---

## 8. ResearchPlanner

ResearchPlanner receives:

- dataset topic
- downstream AI purpose
- SourcePolicy
- seed URLs
- domain constraints
- research limits
- user constraints

It produces:

- non-duplicate search queries
- useful topic subareas
- query families
- source search strategy

Its search planning must reflect requested content characteristics.

Example:

```text
desired_content:
  mathematical_derivation
  implementation_details

technical_depth:
  high
```

may justify queries targeting:

- mathematical explanations
- implementation documentation
- papers
- benchmarks
- technical engineering articles

If no source type is preferred, the plan must remain source-type neutral.

---

## 9. Global Source Discovery

Firecrawl remains the initial global search provider.

Primary responsibility:

```text
query
    -> search results
    -> candidate URLs
```

Firecrawl does not decide:

- final source quality
- policy alignment
- schema design
- extraction correctness

---

## 10. Candidate Registry

Suggested models:

```python
class DiscoveryOrigin(BaseModel):
    method: str
    query: str | None = None
    seed_url: str | None = None


class SourceCandidate(BaseModel):
    canonical_url: str
    original_urls: list[str]
    domain: str

    title: str | None = None
    description: str | None = None

    discovery_origins: list[DiscoveryOrigin]

    user_seed: bool = False

    preview_status: str = "pending"

    selected: bool = False
    rejection_reasons: list[str] = []
```

One URL discovered by several queries remains one canonical candidate with multiple origins.

---

## 11. Crawl4AI Role

Crawl4AI is the page-level Web Intelligence and Acquisition engine.

Use it for:

- bounded source preview
- raw Markdown
- fit/relevant Markdown
- heading extraction
- internal/external links
- dynamic-page acquisition where needed
- bounded deep crawl
- best-first site exploration
- multi-URL acquisition
- deterministic CSS/XPath/Regex extraction
- controlled concurrency and throttling

Crawl4AI must not replace LangGraph orchestration.

---

## 12. Provider Abstraction

Suggested structure:

```text
src/tools/web/
├── __init__.py
├── models.py
├── discovery_provider.py
├── acquisition_provider.py
├── firecrawl_provider.py
└── crawl4ai_provider.py
```

Conceptual interfaces:

```python
class SourceDiscoveryProvider(Protocol):
    async def search(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[SourceCandidate]:
        ...


class WebAcquisitionProvider(Protocol):
    async def preview(
        self,
        url: str,
        *,
        query: str | None = None,
    ) -> SourcePreview:
        ...

    async def acquire(
        self,
        url: str,
    ) -> AcquiredDocument:
        ...

    async def acquire_many(
        self,
        urls: list[str],
    ) -> list[AcquiredDocument]:
        ...

    async def explore_site(
        self,
        start_url: str,
        *,
        query_terms: list[str],
        max_depth: int,
        max_pages: int,
    ) -> list[DiscoveredPage]:
        ...
```

Initial implementations:

```text
FirecrawlDiscoveryProvider
Crawl4AIAcquisitionProvider
```

---

## 13. Source Preview

Important source decisions require real page evidence.

```text
Candidate URL
    |
    v
Crawl4AI
    |
    v
Clean / Fit Markdown
    |
    v
SourcePreview
    |
    v
SourceEvaluator
```

Suggested model:

```python
class SourcePreview(BaseModel):
    url: str
    title: str | None
    domain: str

    headings: list[str]
    relevant_text: str

    approximate_word_count: int | None
    preview_word_count: int

    internal_links: list[str]
    external_links: list[str]

    language: str | None

    publication_date: str | None = None
    updated_date: str | None = None

    structure_hints: list[str] = []

    fetch_success: bool
    error: str | None = None
```

Preview must be bounded.

Preview is not full extraction.

---

## 14. Source Characterization

Do not create a separate SourceClassifier agent yet.

SourceEvaluator produces a reusable source profile.

Suggested model:

```python
class SourceProfile(BaseModel):
    source_type: str

    content_characteristics: list[str]

    content_depth: str

    authority_signals: list[str]

    information_density_score: float
    technical_depth_score: float

    recency_score: float | None

    extractability_score: float
```

Possible source types:

```text
government
university
academic_paper
official_documentation
independent_technical
news
blog
forum
social_media
dataset
documentation
unknown
```

Possible content characteristics:

```text
technical_explanation
mathematical_derivation
implementation_details
benchmark
statistics
historical_context
primary_facts
tutorial
marketing
shallow_summary
opinion
reference_document
```

These labels must remain extensible.

---

## 15. Request-Specific Source Evaluation

The same source may legitimately score differently under different SourcePolicies.

Suggested result:

```python
class EvaluatedSource(BaseModel):
    url: str

    source_profile: SourceProfile

    topic_relevance_score: float
    policy_alignment_score: float

    final_score: float

    hard_policy_rejected: bool

    decision: str

    reasons: list[str]
```

Example:

```text
Source:
independent technical article
high technical depth
high information density
medium authority
```

Policy A:

```text
authority = low
technical_depth = high
```

Result:

```text
high alignment
```

Policy B:

```text
allowed_source_types = [government, university]
```

Result:

```text
hard reject
```

---

## 16. Hard vs Soft Source Rules

### Hard rules only when explicitly configured

- allowed_domains
- blocked_domains
- allowed_source_types
- blocked_source_types
- minimum_content_depth

### Soft ranking signals

- preferred_domains
- preferred_source_types
- desired_content
- avoided_content
- importance values
- diversity contribution

A soft preference must never silently become a hard filter.

---

## 17. Bounded Site Exploration

Current iteration supports controlled site expansion.

```text
Seed / High-Value Source
    |
    v
Crawl4AI Best-First / Deep Crawl
    |
    v
max_depth
max_pages
same-domain rule
URL filters
    |
    v
Discovered Pages
    |
    v
Candidate Registry
```

This is not continuous research.

Advanced AdaptiveCrawler sufficiency is deferred.

---

## 18. Source Selector

SourceSelector should consider:

- hard-policy eligibility
- topic relevance
- policy alignment
- information density
- technical depth when relevant
- source quality
- extractability
- duplicate status
- domain diversity
- source-type diversity where useful

Do not blindly select top-N candidates from one domain.

---

## 19. Dataset Schema Designer

Inputs:

- dataset topic
- AI purpose
- ResearchPlan
- SourcePolicy
- representative selected SourcePreviews
- explicit user schema constraints

Schema design should reflect:

- downstream AI needs
- requested content
- information available in real sources

Normal provenance fields belong in metadata rather than domain schema.

---

## 20. Human Schema Approval

Full acquisition/extraction waits for approval.

```text
DraftDatasetSchema
    |
    v
WAITING_FOR_SCHEMA_APPROVAL
    |
    +--> edit
    |
    +--> approve
            |
            v
       acquisition
```

Research state must survive editing/resume.

---

## 21. Acquisition

After approval:

```text
Selected Sources
    |
    v
Crawl4AIAcquisitionProvider
    |
    +--> acquire
    +--> acquire_many
    +--> cache
    +--> throttle
    +--> isolate failures
    |
    v
AcquiredDocument[]
```

Suggested model:

```python
class AcquiredDocument(BaseModel):
    source_url: str
    canonical_url: str | None

    title: str | None
    domain: str

    raw_markdown: str
    fit_markdown: str | None

    html: str | None = None

    internal_links: list[str] = []
    external_links: list[str] = []

    retrieved_at: str
    source_provider: str

    content_hash: str

    success: bool
    error: str | None = None
```

---

## 22. Content Processing

Content processing should be deterministic.

Responsibilities:

- normalize whitespace
- preserve headings
- preserve lists
- preserve tables
- reduce obvious boilerplate
- detect empty/thin pages
- preserve source metadata
- preserve content hashes
- keep raw and processed content separate

---

## 23. Extraction Router

```text
Processed Source
    |
    v
ExtractionRouter
    |
    +--------------------------+
    |                          |
    v                          v
Deterministic               Semantic
Extraction                  Extraction
    |                          |
CSS/XPath/Table/Regex       Structured LLM
    |                          |
    +------------+-------------+
                 |
                 v
          ExtractionBatch
```

Deterministic extraction is preferred when structure is reliable.

---

## 24. Crawl4AI Deterministic Extraction

Use Crawl4AI non-LLM strategies for:

- repeated HTML cards
- tables
- predictable sections
- XPath-addressable content
- regex-compatible identifiers
- structured lists
- stable labeled fields

The goal is to avoid unnecessary LLM calls.

---

## 25. Multi-Record Extraction

Replace single-record output contracts.

```python
class ExtractionBatch(BaseModel):
    source_url: str
    segment_id: str
    chunk_id: str

    records: list[ExtractedRecord]

    warnings: list[str] = []
```

```python
class ExtractedRecord(BaseModel):
    local_record_id: str

    data: dict

    field_evidence: dict[str, list[EvidenceRef]]

    extraction_method: str
```

```python
class EvidenceRef(BaseModel):
    source_url: str
    chunk_id: str
    evidence_text: str
```

Valid outputs:

```text
records = []
records = [record]
records = [record1, record2, ...]
```

---

## 26. StructuredGenerationProvider

Semantic extraction must not depend directly on Groq.

Suggested structure:

```text
src/tools/structured_generation/
├── __init__.py
├── base.py
├── groq_provider.py
└── local_provider.py       # optional later
```

Conceptual interface:

```python
class StructuredGenerationProvider(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[BaseModel],
        task_name: str,
    ) -> BaseModel:
        ...
```

Initial provider:

```text
GroqStructuredProvider
```

Future optional provider:

```text
LocalStructuredProvider
```

Where supported:

```text
Pydantic
    ->
JSON Schema
    ->
strict structured generation
    ->
Pydantic validation
```

---

## 27. Groq Is Not the Only JSON Path

JSON can be produced by:

```text
Crawl4AI deterministic extraction
    -> Pydantic
    -> JSON
```

or:

```text
semantic source content
    -> StructuredGenerationProvider
    -> Pydantic
    -> JSON
```

Groq is one semantic provider, not the mandatory JSON generator.

---

## 28. Optional Local Model Integration

Local models are not required for early phases.

After benchmark infrastructure exists, compare:

- current Groq baseline
- strict-output-capable Groq model
- stronger cloud fallback
- local structured model

Potential later routing:

```text
Deterministic extraction
    |
    v
Local structured model
    |
valid + supported?
   /        \
 yes         no
 save        cloud fallback
```

The same provider interface must be used.

---

## 29. Evidence Validation

Extraction output is candidate data.

Validate:

- source exists
- chunk exists
- evidence exists
- evidence is traceable to supplied content
- required fields are present
- field types are valid

Suggested statuses:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTED
```

---

## 30. Quality Gate

Final quality should use measurable components:

- schema validity
- required-field completeness
- evidence support rate
- source score
- provenance completeness
- duplicate status

Do not rely on extractor self-confidence.

---

## 31. Record Resolution

Resolution stages:

1. explicit schema identity
2. normalized identity
3. composite schema-aware identity
4. semantic similarity only if later proven necessary

Do not hard-code domain-specific identities into generic nodes.

---

## 32. Provenance

Merging must preserve all contributing sources.

```text
Final Record
├── Source A
│   └── Evidence A
├── Source B
│   └── Evidence B
└── Source C
    └── Evidence C
```

---

## 33. Deduplication

Stages:

1. canonical URL / content hash
2. exact normalized record fingerprint
3. schema-aware identity
4. optional future semantic near-duplicate detection

Do not add a vector database solely for deduplication in this iteration.

---

## 34. Data Layers

### Bronze

Acquired source material.

### Silver

Processed content, chunks, extraction candidates, evidence.

### Gold

Validated records with evidence, provenance, and quality metadata.

---

## 35. Output Profiles

### Structured

For topic-specific records and knowledge bases.

### RAG

Suggested fields:

```text
text
title
source_url
section_path
chunk_id
language
content_hash
quality_score
```

### GraphRAG Preparation

Only evidence-backed entities/claims/relations.

No co-occurrence-only relations.

---

## 36. AgentState Evolution

```python
class AgentState(TypedDict, total=False):
    request_config: dict
    source_policy: SourcePolicy

    research_plan: ResearchPlan

    source_registry: dict[str, SourceCandidate]
    source_previews: list[SourcePreview]
    source_evaluations: list[EvaluatedSource]
    selected_sources: list[SelectedSource]

    draft_dataset_schema: DraftDatasetSchema
    approved_dataset_schema: ApprovedDatasetSchema

    raw_data: list[AcquiredDocument]
    processed_data: list[ProcessedDocument]
    document_chunks: list[DocumentChunk]

    extraction_batches: list[ExtractionBatch]
    verified_records: list[VerifiedRecord]

    accepted_records: list[FinalRecord]
    rejected_records: list[RejectedRecord]

    metrics: RunMetrics
    errors: list[PipelineError]

    status: str
```

---

## 37. Target Node Layout

```text
src/agents/nodes/
├── research_planner_node.py
├── source_discovery_node.py
├── candidate_registry_node.py
├── source_preview_node.py
├── source_evaluator_node.py
├── site_exploration_node.py
├── source_selector_node.py
├── dataset_schema_designer_node.py
├── acquisition_node.py
├── processing_node.py
├── chunking_node.py
├── extraction_router_node.py
├── structured_extraction_node.py
├── evidence_validation_node.py
├── record_resolution_node.py
├── quality_gate_node.py
├── deduplication_node.py
└── export_node.py
```

No separate `SourceClassifierNode` is required now.

---

## 38. Metrics

### Source Discovery

```text
queries_generated
raw_search_results
unique_candidates
seed_candidates
unique_candidate_domains
```

### Source Policy / Evaluation

```text
source_types_observed
content_characteristics_observed
policy_alignment_score_distribution
hard_policy_rejections
preferred_type_selection_rate
desired_content_match_rate
selected_sources_by_type
selected_sources
unique_selected_domains
```

### Preview / Exploration

```text
preview_successes
preview_failures
site_exploration_pages
site_exploration_domains
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

### Extraction

```text
documents
chunks
deterministic_extractions
semantic_extractions
records_extracted
records_per_chunk
structured_output_failures
```

### Validation

```text
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

---

## 39. Evaluation Strategy

The source benchmark must test request-specific behavior.

Include:

- high-authority + deep + relevant
- high-authority + shallow + relevant
- high-authority + irrelevant
- independent + deep + relevant
- independent + shallow
- university + useful
- university + irrelevant
- thin page
- duplicate page
- useful non-seed source
- blocked source type
- allowed source type

Evaluate the same candidates under multiple SourcePolicies.

Example:

### Policy A

```text
authority = low
technical_depth = high
no source-type allowlist
```

### Policy B

```text
authority = high
allowed_source_types = academic, government, university
```

The same source may legitimately receive different final decisions.

---

## 40. Initial Engineering Gates

Suggested initial targets:

```text
source precision@10 >= 0.80
record recall >= 0.85
unsupported accepted field rate < 0.05
exact duplicate rate < 0.03
hard policy violation rate = 0
```

These are engineering targets, not universal guarantees.

---

## 41. Future Iteration

Future Research Intelligence features may include:

- Domain Knowledge Map
- Coverage Map
- Claim/Evidence Graph
- Conflict Map
- Research Gaps
- Information Gain
- AdaptiveCrawler sufficiency
- repeated gap-focused research
- persistent research projects
- general research reports
- continuous updates

These remain explicitly deferred.

---

## 42. Current Definition of Success

A request such as:

```text
"Create a high-quality dataset about X for my AI project.
I care about deep implementation details.
Official sources are not required.
Here is one useful reference URL."
```

should produce this behavior:

```text
request validation
    |
    v
SourcePolicy
    |
    v
request-aware research planning
    |
    v
seed + non-seed discovery
    |
    v
Crawl4AI source previews
    |
    v
source characterization
    |
    v
request-specific evaluation
    |
    v
bounded site exploration
    |
    v
source selection
    |
    v
schema design
    |
    v
human approval
    |
    v
Crawl4AI acquisition
    |
    v
deterministic extraction where possible
    |
    v
semantic extraction where necessary
    |
    v
multi-record ExtractionBatch
    |
    v
field evidence
    |
    v
validation and resolution
    |
    v
deduplication
    |
    v
AI-ready output
```

This is the canonical architecture for the current iteration.
