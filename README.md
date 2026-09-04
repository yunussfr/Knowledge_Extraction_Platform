<p align="center"><img src="docs/assets/knowledge-extraction-platform-brand.png" alt="Knowledge Extraction Platform gothic spider emblem connecting discovery, evaluation, schema design, extraction, enrichment, and dataset delivery" width="760"></p>

# 🕸️ Knowledge Extraction Agent

<p align="center"><strong>Turn the open web into evidence-backed knowledge.</strong><br>A friendly research spider for structured datasets, RAG, GraphRAG, and future knowledge applications.</p>

<p align="center"><img src="https://img.shields.io/badge/status-active%20engineering-22c55e?style=flat-square" alt="Active engineering"> <img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12"> <img src="https://img.shields.io/badge/orchestration-LangGraph-7c3aed?style=flat-square" alt="LangGraph"> <img src="https://img.shields.io/badge/web-Crawl4AI-0891b2?style=flat-square" alt="Crawl4AI"></p>

## The idea in one picture

This is not a chatbot. It is a research-to-knowledge pipeline: a domain request becomes a reviewed schema, selected sources become acquired documents, documents become verified records, and the same evidence can feed several output profiles.

<p align="center"><img src="docs/assets/pipeline-layers.svg" alt="Four architecture layers: discovery, acquisition, intelligence, and knowledge" width="900"></p>

## The architecture web

The platform is one connected evidence web rather than a chain of isolated agents. Every outer thread returns to the same center: source-backed knowledge with preserved provenance.

```mermaid
%%{init: {"theme":"dark","themeVariables":{"background":"#050608","primaryColor":"#171022","primaryTextColor":"#f5ead6","primaryBorderColor":"#9b87c7","lineColor":"#8f7cad","secondaryColor":"#082226","tertiaryColor":"#2a0d16","fontFamily":"Georgia, Times New Roman, serif"}}}%%
flowchart TB
    REQUEST[Domain request] --> PLAN[Research plan] --> SEARCH[Firecrawl discovery]
    SEARCH --> PREVIEW[Crawl4AI previews] --> EVALUATE[Policy-aware evaluation]
    EVALUATE --> SELECT[Source selection] --> SCHEMA[Draft target schema]
    SCHEMA --> APPROVAL{Human approval}

    APPROVAL --> ACQUIRE[Crawl4AI acquisition] --> CLEAN[Bronze → Silver cleaning]
    CLEAN --> CHUNK[Token-aware chunks] --> ROUTER{Extraction router}
    ROUTER -->|tables / CSS / XPath / regex| DET[Deterministic extraction]
    ROUTER -->|semantic text| LOCAL[Local model]
    LOCAL -->|invalid or unsupported output| GROQ[Groq fallback]
    DET --> EVIDENCE[Field evidence binding]
    LOCAL --> EVIDENCE
    GROQ --> EVIDENCE

    EVIDENCE --> VERIFY{Evidence validation + quality gate}
    VERIFY --> CORE((EVIDENCE-BACKED<br/>KNOWLEDGE))
    CORE --> RESOLVE[Resolve + deduplicate] --> ENRICH[Entities · facts · relations]
    ENRICH --> EXPORT[Profile export] --> STORE[(SQLite / PostgreSQL)]

    STORE --> STRUCTURED[Structured JSON]
    STORE --> RAG[RAG chunks]
    STORE --> GRAPH[Evidence-backed GraphRAG]
    STORE --> COVERAGE[Coverage state]
    COVERAGE --> TASKS[Bounded enrichment tasks]
    TASKS -. next research thread .-> SEARCH
    STORE -. inspect .-> DASH[Future dashboard]

    SELECT -. checkpoint .-> CHECKPOINTS[(Atomic checkpoints)]
    ACQUIRE -. checkpoint .-> CHECKPOINTS
    CHUNK -. checkpoint .-> CHECKPOINTS
    EVIDENCE -. checkpoint .-> CHECKPOINTS
    EXPORT -. checkpoint .-> CHECKPOINTS
    EXPORT --> MANIFEST[Run manifest]

    classDef hunt fill:#062326,stroke:#2dd4bf,color:#d9fffb,stroke-width:2px;
    classDef intelligence fill:#1c1028,stroke:#a78bfa,color:#f4eaff,stroke-width:2px;
    classDef blood fill:#260b12,stroke:#ef4444,color:#ffe4e6,stroke-width:2px;
    classDef core fill:#090b10,stroke:#f0d8a8,color:#fff7e6,stroke-width:4px;
    classDef store fill:#0c1720,stroke:#38bdf8,color:#e0f2fe,stroke-width:2px;
    class REQUEST,PLAN,SEARCH,PREVIEW,EVALUATE,SELECT hunt;
    class SCHEMA,APPROVAL,ACQUIRE,CLEAN,CHUNK,ROUTER,DET,LOCAL,GROQ,EVIDENCE intelligence;
    class VERIFY,RESOLVE,ENRICH,EXPORT blood;
    class CORE core;
    class STORE,STRUCTURED,RAG,GRAPH,COVERAGE,TASKS,DASH,CHECKPOINTS,MANIFEST store;
```

## What can you build with it?

| Use case | What the spider delivers |
| --- | --- |
| **Structured datasets** | Validated records with field-level evidence and provenance |
| **RAG ingestion** | Retrieval documents made directly from evidence-preserving chunks |
| **GraphRAG foundations** | Entities, claims, and relations traceable to supplied text |
| **Research automation** | Bounded discovery, preview, acquisition, and enrichment |
| **Evaluation** | Frozen gold fixtures, quality metrics, provider comparisons, and checkpoints |
| **Future dashboard** | A visual run console for sources, coverage, evidence, tasks, cost, and latency |

## Why the web metaphor matters

Every “thread” has a job and a boundary:

```text
🕷️ Research      plans the hunt; it does not browse
🕸️ Firecrawl     discovers candidates; it does not decide truth
🧭 Crawl4AI      previews and acquires selected pages
🧪 Extraction    prefers deterministic rules before probabilistic models
🔎 Evidence      binds every accepted value to supplied source text
🗃️ Knowledge     stores records, entities, facts, relations, and provenance
📦 Profiles      export the same run as Structured, RAG, or GraphRAG output
```

### Crawl4AI, explained simply

[Crawl4AI](https://github.com/unclecode/crawl4ai) is the page-acquisition layer. In this project it provides browser-based previews, controlled page retrieval, Markdown/HTML content, links, caching, bounded concurrency, and local-fixture testing. It is deliberately not the “brain”: it does not choose dataset fields, invent facts, assign final confidence, or write knowledge records.

[Firecrawl](https://www.firecrawl.dev/) is used at the discovery boundary to search for candidate URLs. The application evaluates those candidates against the user’s explicit source policy and sends only selected pages to the acquisition provider.

## Quality is a gate, not a feeling

```mermaid
%%{init: {"theme":"dark","themeVariables":{"background":"#050608","primaryColor":"#171022","primaryTextColor":"#f5ead6","primaryBorderColor":"#a78bfa","lineColor":"#907cad","secondaryColor":"#071f21","tertiaryColor":"#2a0d16"}}}%%
flowchart TD
    S[Supplied source text] --> X[Candidate value] --> E{Exact evidence binding?}
    E -->|no| R[Reject or quarantine]
    E -->|yes| V{Schema + type + quality valid?}
    V -->|no| R
    V -->|yes| P[Preserve URL, chunk, field evidence, and provenance]
    P --> D[Resolve conflicts conservatively] --> O[Export]
```

The core rules are intentionally strict:

- no fabricated values;
- no hidden source allowlists when policy fields are omitted;
- no co-occurrence-only GraphRAG relations;
- no destructive deduplication that loses evidence;
- no local-model promotion without comparable benchmark evidence.

## Current build

The implementation has moved beyond a simple scraper into a resumable knowledge pipeline:

| Layer | Current capability |
| --- | --- |
| **Configuration** | Domain-specific YAML requests, source policy, schema constraints, and output profiles |
| **Web** | Firecrawl discovery boundary plus Crawl4AI preview/acquisition boundary |
| **Processing** | Bronze acquisition → deterministic Silver cleaning → token-aware chunks |
| **Extraction** | CSS/XPath/regex/table routes first, structured generation as fallback |
| **Knowledge** | Persistent sources, documents, chunks, records, entities, facts, relations, and evidence |
| **Reliability** | Manifest metrics, atomic checkpoints, schema approval, resume, bounded retries |
| **AI routing** | Benchmark-gated local-first path with Groq fallback when configured |

## The persistence web

The database is not the orchestrator and never owns crawler or model clients. LangGraph passes JSON-safe state into `storage_node`; `PipelineRepository` maps that state through SQLAlchemy to the configured database while checkpoints and manifests remain explicit resumable artifacts.

<p align="center"><img src="docs/assets/gothic-persistence-web.svg" alt="Gothic persistence web connecting LangGraph state, SQLAlchemy, SQLite, PostgreSQL, evidence tables, outputs, checkpoints, manifests, coverage, and dashboard views" width="1000"></p>

```text
DATABASE_URL absent
    → sqlite:///knowledge/knowledge.db

storage.database_url or DATABASE_URL configured
    → PostgreSQL for production deployments

Both backends preserve
    → datasets · runs · sources · documents · chunks
    → records · field evidence · entities · facts · relations · coverage
```

SQLite is the zero-configuration local default. PostgreSQL uses the same repository contract, PostgreSQL-native JSONB variants, and Alembic migrations for production evolution. Database sessions stay inside `src/storage/`; only serializable identifiers, counts, and metrics return to graph state.

### Recent milestones

```text
✅ Phase 28  Persistent storage with PostgreSQL / SQLite and migrations
✅ Phase 29  High-volume multi-record ingestion and yield metrics
✅ Phase 30  Entity resolution, facts, relations, and conflict preservation
✅ Phase 31  Coverage analysis and bounded enrichment task planning
✅ Phase 32  Local-first routing with benchmark evidence and cloud fallback
🚧 Next      Dashboard, larger real-world gold sets, and benchmark expansion
```

### Benchmark snapshot

The current routed extraction benchmark is an offline/frozen engineering comparison, not a live-web quality promise.

| Metric | Routed local-first | Groq-only comparison |
| --- | ---: | ---: |
| Record recall | 0.9167 | 0.8333 |
| Field precision | 0.9697 | 0.7586 |
| Field recall | 0.9143 | 0.6286 |
| Unsupported accepted fields | 0.0000 | 0.0000 |
| Schema validity | 1.0000 | — |
| Cloud fallback rate | 0.25 | — |

The harness makes model or provider changes visible. It does not imply that every domain, language, website, or live provider will produce the same result.

## Future dashboard: from terminal spider to research cockpit

The terminal runner is the current presentation layer. A future dashboard will sit on the same serializable `AgentState` and checkpoint contracts, so the UI can visualize a run without rewriting the pipeline:

```mermaid
%%{init: {"theme":"dark","themeVariables":{"background":"#050608","primaryColor":"#171022","primaryTextColor":"#f5ead6","primaryBorderColor":"#a78bfa","lineColor":"#907cad","secondaryColor":"#071f21","tertiaryColor":"#2a0d16"}}}%%
flowchart LR
    R[Research run] --> G[Source web]
    R --> C[Coverage heatmap]
    R --> E[Evidence inspector]
    R --> T[Enrichment task queue]
    R --> M[Cost + latency metrics]
    R --> B[Benchmark lab]
```

Planned views include source eligibility and diversity, schema approval, crawl health, evidence inspection, unresolved coverage, enrichment rounds, provider routing, token/cost usage, and benchmark deltas.

## Quick start

The repository uses the dedicated `.venv` interpreter for every command.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-baseline.txt
Copy-Item .env.example .env
```

Run the offline mock domain:

```powershell
.\.venv\Scripts\python.exe run_domain_test.py --domain turkish_culture --approve-schema
```

For the human-in-the-loop flow, remove `--approve-schema`. Review `knowledge/review/`, then approve it in the terminal. To continue a saved checkpoint:

```powershell
.\.venv\Scripts\python.exe run_domain_test.py --domain turkish_culture --resume
```

Other example domain: `space_science`.

Create a new domain by copying `configs/domains/turkish_culture/request.yaml` into `configs/domains/<your_domain>/request.yaml` and changing the topic, purpose, source policy, schema, and output settings. The `--domain` value is the directory name under `configs/domains/`.

## Run modes and outputs

```mermaid
%%{init: {"theme":"dark","themeVariables":{"background":"#050608","primaryColor":"#171022","primaryTextColor":"#f5ead6","primaryBorderColor":"#a78bfa","lineColor":"#907cad","secondaryColor":"#071f21","tertiaryColor":"#2a0d16"}}}%%
flowchart LR
    A[request.yaml] --> B{DATA_SOURCE_PROVIDER}
    B -->|mock| C[offline fixtures]
    B -->|firecrawl| D[real discovery] --> E[Crawl4AI selected-page acquisition]
    C --> F[shared processing + validation]
    E --> F --> G[knowledge/datasets]
```

Mock mode needs no provider key. Real mode needs credentials and network access. Local-model routing is optional and benchmark-gated; it does not silently replace Groq unless the local backend is enabled and approved.

The output profiles are independent views over shared evidence:

- `structured`: accepted records, metadata, quality, field evidence, and provenance;
- `rag`: one retrieval document per evidence-preserving chunk;
- `graphrag`: traceable entities, claims, and relations only.

Each run can also write a manifest and resumable checkpoint beside the dataset. Keep checkpoints when using `--resume`.

## Project map

```text
configs/domains/                 domain requests and schemas
run_domain_test.py                terminal entry point
src/agents/graphs/                canonical LangGraph orchestration
src/agents/nodes/                 planning, crawling, extraction, evidence, knowledge
src/tools/web/                    Firecrawl and Crawl4AI provider boundaries
src/tools/structured_generation/  local and Groq adapters + router
src/storage/                      persistent models and repositories
src/schemas/                      Pydantic contracts
tests/evaluation/                 frozen gold sets and benchmark gates
docs/                             architecture, rules, phases, and progress records
knowledge/datasets/               generated outputs and manifests
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

The last recorded offline acceptance run passed `283` tests with `13` opt-in skips. Local-browser Crawl4AI checks are separate from the offline suite; live Firecrawl/Groq checks are opt-in and credential-dependent.

## Design documents

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — intended system and data contracts
- [`docs/RULES.md`](docs/RULES.md) — engineering and safety rules
- [`docs/PHASES.md`](docs/PHASES.md) — ordered roadmap and acceptance gates
- [`docs/DEVELOPMENT_PROGRESS.md`](docs/DEVELOPMENT_PROGRESS.md) — verified implementation journal

## Project status

This is an actively evolving research and engineering project. Provider SDK behavior, model availability, and live-site rendering can change; use frozen fixtures and manifests for reproducible comparisons, and treat live runs as provider-dependent experiments.
