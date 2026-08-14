# RULES.md

# Knowledge Extraction Platform — Development Rules

## 1. Scope

The current goal is:

> Build a reliable, request-aware, evidence-backed source discovery and dataset extraction platform for AI projects.

Do not implement the future Research Intelligence Platform yet.

Deferred features:

- continuous research
- Domain Knowledge Map
- global research coverage loop
- repeated gap-focused research
- information-gain stopping
- advanced AdaptiveCrawler sufficiency
- general-purpose research reports
- stale-source monitoring
- living research projects

---

## 2. Preserve Core Architecture

Do not rewrite the repository from scratch.

Preserve and evolve:

- LangGraph
- AgentState
- human schema approval
- configuration-driven execution
- token-aware chunking
- CLI/resume behavior where possible

---

## 3. LangGraph Is the Orchestrator

LangGraph controls application flow.

Do not move orchestration into:

- Crawl4AI
- Firecrawl
- Groq
- utility classes
- provider wrappers

Tools expose capabilities. Nodes decide when and why to use them.

---

## 4. One Node, One Responsibility

Good:

```text
SourceDiscovery
SourcePreview
SourceEvaluator
SiteExploration
SourceSelector
Acquisition
StructuredExtractor
EvidenceValidator
```

Bad:

```text
one node searches + crawls + evaluates + extracts + validates + exports
```

---

## 5. SourcePolicy Is User-Driven

Never hard-code:

```text
official > university > independent > blog
```

Source quality must be evaluated relative to:

- topic
- downstream AI purpose
- requested content
- source preferences
- hard restrictions
- importance values

---

## 6. Optional Source-Type Fields

These are optional:

```text
preferred_source_types
allowed_source_types
blocked_source_types
```

Semantics:

```text
preferred_source_types absent/empty
    -> no source-type ranking preference

allowed_source_types absent/empty
    -> no source-type allowlist

blocked_source_types absent/empty
    -> no source-type blocklist
```

Never invent a restriction the user did not provide.

---

## 7. Hard vs Soft Rules

### Hard only when explicitly configured

- allowed_domains
- blocked_domains
- allowed_source_types
- blocked_source_types
- minimum_content_depth

### Soft

- preferred_domains
- preferred_source_types
- desired_content
- avoided_content
- importance values
- diversity contribution

Soft preferences must not behave as hard filters.

---

## 8. Seed URL Rule

A seed URL is a reference and starting point.

Never interpret it as an implicit allowlist or domain boundary.

---

## 9. `preferred_domains` Is Soft

Useful sources outside preferred domains remain eligible.

---

## 10. No Universal Authority Bias

Do not automatically reward a source only because it is:

- governmental
- academic
- university-hosted
- official
- institutional

Authority matters only when the request or evidence makes it important.

A deep independent source may outrank a shallow official source.

---

## 11. Classification vs Evaluation

Classification asks:

> What is this source?

Evaluation asks:

> How useful is this source for this request?

Keep these concepts separate in the data model.

---

## 12. No Separate SourceClassifier Agent Yet

Do not create an extra LLM call per candidate only to classify sources.

Current SourceEvaluator may output reusable source descriptors and request-specific scores in one execution.

A separate SourceClassifier may be added later only if classification is independently cached/reused or can be made significantly cheaper.

---

## 13. Source Evaluation Requires Real Evidence

Do not evaluate important candidates only from:

- URL
- title
- search snippet

Use bounded SourcePreview whenever possible.

If preview fails, record the limitation.

---

## 14. Preview Is Not Full Extraction

Preview is for:

- relevance
- source characterization
- policy alignment
- schema-design context

Full acquisition/extraction begins after schema approval.

---

## 15. ResearchPlanner Receives SourcePolicy

Research planning must have access to:

- desired content
- optional source preferences
- optional hard restrictions
- technical depth importance
- recency importance
- downstream AI purpose

Missing restrictions must stay missing.

---

## 16. Request Normalization Must Be Deterministic

Parse request YAML through typed validation.

Do not use an LLM merely to understand optional config fields.

---

## 17. Crawl4AI Role

Use Crawl4AI for:

- preview
- Markdown
- fit/relevant Markdown
- link extraction
- bounded site exploration
- best-first/deep crawl
- multi-URL acquisition
- deterministic CSS/XPath/Regex extraction
- dynamic page acquisition
- controlled concurrency/throttling

Do not make Crawl4AI the global orchestrator.

---

## 18. Firecrawl Role

Use Firecrawl primarily for global source discovery.

Do not let it decide final source quality or dataset validity.

---

## 19. AdaptiveCrawler Is Deferred

Do not implement research-sufficiency AdaptiveCrawler logic now.

Current crawling must be bounded by explicit limits.

---

## 20. Site Exploration Must Be Bounded

Every site exploration requires:

- max depth
- max pages
- domain scope
- URL filtering

Never perform unbounded crawling.

---

## 21. Provider Abstraction Is Mandatory

Use interfaces such as:

```text
SourceDiscoveryProvider
WebAcquisitionProvider
StructuredGenerationProvider
```

Initial implementations:

```text
FirecrawlDiscoveryProvider
Crawl4AIAcquisitionProvider
GroqStructuredProvider
```

---

## 22. Wrap Crawl4AI

Do not scatter Crawl4AI setup throughout the graph.

Centralize crawler configuration in a provider layer.

---

## 23. Crawler Limits Must Be Explicit

Important limits must be configurable:

- max depth
- max pages
- timeout
- cache behavior
- content filtering
- concurrency
- rate limiting
- same-domain policy
- excluded patterns

---

## 24. Human Schema Approval Must Remain

Required flow:

```text
research
-> preview/evaluation
-> draft schema
-> wait
-> user approve/edit
-> acquisition/extraction
```

Do not bypass approval.

---

## 25. Deterministic First

Before semantic extraction, check:

- CSS
- XPath
- JSON-LD
- tables
- repeated DOM
- metadata
- regex
- ordinary parsing

Use an LLM only when semantic reasoning is needed.

---

## 26. Crawl4AI LLM Extraction Is Not the Default Semantic Layer

Crawl4AI may do deterministic extraction.

Semantic structured extraction stays behind `StructuredGenerationProvider`.

---

## 27. Chunk Is Not Record

Never assume:

```text
1 chunk = 1 record
```

Support:

```text
0
1
N
```

records.

---

## 28. No Hidden Record Limit

Any record limit must be explicit, configurable, and visible in metrics.

Never silently truncate to one record.

---

## 29. Multi-Record Contract Is Mandatory

Use:

```text
ExtractionBatch.records[]
```

or equivalent.

Downstream nodes process records individually.

---

## 30. Structured Generation Must Be Provider-Neutral

Core semantic extraction must not depend directly on Groq.

Use `StructuredGenerationProvider`.

---

## 31. Groq Is Not the Only JSON Path

JSON may come from deterministic extraction or semantic model extraction.

Do not treat Groq as mandatory for all records.

---

## 32. Strict Structured Output Where Supported

Where provider/model supports JSON Schema constrained output, use it.

Pydantic validation still remains required.

---

## 33. Pydantic Is the Application Contract

Core structured outputs must map to typed Pydantic models.

---

## 34. No Fabrication

Never invent:

- source URLs
- source titles
- records
- field values
- evidence
- provenance
- relations
- citations

Unsupported optional data follows schema null/omit rules.

Unsupported required data rejects/quarantines the candidate.

---

## 35. Evidence Must Be Traceable

Evidence must point to:

- source URL
- chunk/segment
- supporting text

Do not fabricate evidence strings.

---

## 36. Self-Confidence Is Not Verification

Do not accept data because the extractor says it is confident.

Use:

- schema validity
- evidence
- source score
- completeness
- provenance
- duplicate status

---

## 37. Extraction and Verification Are Separate

Extractor creates candidates.

EvidenceValidator and QualityGate decide acceptance.

---

## 38. Model Changes Require Benchmarking

Never choose a model only because it is:

- newer
- larger
- cheaper
- open-source
- popular

Use the same frozen evaluation set.

---

## 39. Local Models Are Optional Later

Do not add a local model before baseline/evaluation infrastructure exists.

When added, it must use the same structured provider interface.

---

## 40. Source Diversity Matters

Do not blindly select top-N from one domain.

Selection should consider:

- hard eligibility
- topic relevance
- policy alignment
- information density
- technical depth when relevant
- duplication
- domain diversity

---

## 41. No Research-Completeness Claim

The pipeline may say dataset generation completed.

It must not claim the topic was comprehensively researched.

---

## 42. State Must Stay Serializable

Do not store network clients, crawler instances, locks, or callbacks in AgentState.

---

## 43. Resume Compatibility

State/config changes must consider persisted pipeline-state compatibility.

Fail clearly when incompatible.

---

## 44. Preserve Raw Evidence

Maintain:

```text
Bronze
Silver
Gold
```

Do not overwrite raw content with processed content.

---

## 45. Merge Must Preserve Provenance

Cross-source merge must keep:

- all contributing URLs
- evidence
- unresolved conflicts

---

## 46. Deduplication Is Staged

Use:

```text
URL/content hash
-> exact record
-> schema-aware identity
```

Semantic near-duplicate detection is later and optional.

---

## 47. GraphRAG Relations Require Evidence

Never emit a relation only because entities co-occur.

---

## 48. Generic Pipeline Only

Do not hard-code domain-specific fields or identities in generic nodes.

---

## 49. Offline Unit Tests

Normal unit tests must not require:

- Firecrawl API
- Groq API
- live internet
- real web crawling

Use fixtures/mocks.

---

## 50. Live Tests Are Separate

Separate:

```text
tests/unit/
tests/integration/
tests/evaluation/
```

Live-provider evaluation must be opt-in.

---

## 51. Required SourcePolicy Tests

Test:

- neutral policy
- preferred only
- allowed only
- blocked only
- desired-content only
- avoided-content only
- technical-depth-heavy policy
- allowed/blocked conflict
- all source-type fields omitted

---

## 52. Required Policy-Aware Evaluation Tests

Verify:

- official shallow can lose to independent deep
- independent source is neutral under neutral source-type policy
- allowed types are enforced only when supplied
- blocked types are enforced only when supplied
- preferred types influence ranking but not eligibility
- same source can score differently under different policies

---

## 53. Required Multi-Record Tests

Test:

```text
0 records
1 record
multiple records
many records
missing optional field
missing required field
wrong type
duplicate record
repeated evidence
```

---

## 54. No Hidden Truncation

Any limit reducing dataset scale must be named and observable.

---

## 55. Metrics Must Reflect Policy Behavior

Track:

- source types observed
- content characteristics observed
- policy alignment distribution
- hard policy rejections
- desired-content match rate
- selected sources by type

---

## 56. No Premature Infrastructure

Do not introduce distributed queues, Kubernetes, or complex orchestration until single-process bounded concurrency is proven insufficient.

---

## 57. Secret Safety

Never commit or print API keys.

---

## 58. User Artifact Safety

Do not delete or overwrite user datasets/review artifacts unless explicitly requested.

---

## 59. Git Safety

Before changes:

```text
git status
```

After changes:

```text
git diff
tests
git status
```

Do not reset or remove unrelated user changes.

---

## 60. Legacy Cleanup Requires Proof

Before deleting old files:

1. search imports
2. inspect tests
3. inspect CLI references
4. inspect docs
5. run tests

---

## 61. Small Coherent Changes

Do not combine multiple major migrations in one giant patch.

Follow `PHASES.md`.

---

## 62. Documentation Must Stay Canonical

When config semantics or architecture change, update canonical docs.

---

## 63. System Prompt Wording Is Managed Separately

`PHASES.md` intentionally does not contain system-prompt rewrite tasks.

Prompt wording is maintained separately by the project owner.

Prompt behavior must still remain compatible with typed architecture contracts.

---

## 64. Definition of Done

A task is complete only when:

- behavior exists
- state/contracts remain coherent
- tests exist
- unrelated files are untouched
- SourcePolicy semantics are respected
- provenance is preserved
- failures/statuses are truthful
- docs/config examples are updated when needed

---

## 65. Absolute Prohibitions

Never:

- treat seed URL as allowlist
- make preferred_domains hard
- make preferred_source_types hard
- invent allowed_source_types
- invent blocked_source_types
- use universal authority-first ranking
- assume one chunk equals one record
- fabricate evidence
- fabricate missing data
- use extractor self-confidence as final verification
- create co-occurrence-only GraphRAG relations
- bypass schema approval
- implement continuous research now
- implement AdaptiveCrawler sufficiency now
- replace LangGraph
- rewrite the repository wholesale
- hide failed tests
- delete user data artifacts
- choose a model without benchmark evidence

---

## 66. Engineering Principle

Every current change should answer:

> Does this improve quality, breadth, request alignment, evidence traceability, reliability, or cost-efficiency for downstream AI datasets?

If not, it is likely outside the current iteration.
