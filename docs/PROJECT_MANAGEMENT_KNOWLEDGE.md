# PROJECT_MANAGEMENT_KNOWLEDGE.md

# Knowledge Extraction Platform — Project Management Knowledge

## 1. Dosyanın Amacı

Bu dosya projenin yaşayan teknik ve yönetim hafızasıdır.

Bu dosyanın görevi yalnızca:

```text
hangi dosyalar değişti?
```

sorusunu cevaplamak değildir.

Aynı zamanda:

```text
Neden değiştirildi?
Nasıl gerçekleştirildi?
Projeye ne kazandırdı?
Hangi problem çözüldü?
Hangi problem hâlâ duruyor?
Mimari nasıl değişti?
AI alınan karar hakkında ne düşünüyor?
Sonraki faza geçmek güvenli mi?
```

sorularını cevaplamalıdır.

Bu dosya her geliştirme fazından sonra güncellenir.

---

# 2. Source of Truth Sırası

AI geliştirme yapmadan önce aşağıdaki sırayı kullanmalıdır:

```text
1. docs/PROJECT_MANAGEMENT_KNOWLEDGE.md
2. docs/PHASES.md
3. docs/ARCHITECTURE.md
4. docs/RULES.md
5. docs/DEVELOPMENT_PROGRESS.md
6. ilgili kaynak kod
7. ilgili testler
```

`DEVELOPMENT_PROGRESS.md` Phase 0–27 için tarihsel implementasyon kaydıdır.

Yeni iterasyonun günlük mimari/proje hafızası bu dosyadır.

---

# 3. Projenin Nihai Vizyonu

Knowledge Extraction Platform'un nihai amacı:

> Kullanıcının tanımladığı bir araştırma alanı ve veri şemasına göre web üzerinde kaynak keşfedebilen, kaynakların gerçek içeriklerini mümkün olduğunca kapsamlı şekilde toplayan, kaynakları kalıcı biçimde saklayan, sıfır/bir/çok yapılandırılmış kayıt çıkaran, tüm bilgileri evidence ile bağlayan, bilgileri bir PostgreSQL knowledge store içerisinde birleştiren, eksik veya çelişkili alanları yeniden araştıran ve cloud LLM kullanımını yalnızca gerçekten gerekli semantic görevlerle sınırlayan bir Knowledge Acquisition Platform oluşturmaktır.

Platform bir chatbot değildir.

Platform yalnızca tek seferlik JSON generator değildir.

Platform:

```text
Research
+
Web Acquisition
+
Knowledge Extraction
+
Evidence
+
Persistence
+
Enrichment
+
Dataset Generation
```

sistemidir.

---

# 4. Mevcut Proje Durumu

## Current Iteration Baseline

```text
Previous Iteration:
Phase 0–27

Status:
COMPLETED

Canonical Orchestrator:
src/agents/graphs/phase2_pipeline.py

State:
src/state/state.py
```

Mevcut sistemin önemli yetenekleri:

```text
Request-aware research planning
Firecrawl source discovery
Candidate registry
URL normalization
Crawl4AI source preview
Source evaluation
Bounded site exploration
Source selection
Human-approved dataset schema
Multi-source acquisition
Bronze acquired document preservation
Deterministic content processing
Token-aware chunking
Extraction routing
CSS/XPath/Regex/Table extraction
Multi-record semantic extraction
StructuredGenerationProvider
Field evidence
Evidence validation
Record resolution
Deduplication
Structured export
RAG export
GraphRAG export
Run metrics
Manifest
Checkpoint/resume
Local-model evaluation boundary
Reliability hardening
```

Bu altyapı silinmemeli veya sebepsiz yeniden yazılmamalıdır.

Yeni mimari bunun üzerine kurulacaktır.

---

# 5. Mevcut Mimari

```text
configs/domains/<domain>/request.yaml
              |
              v
       run_domain_test.py
              |
              v
src/agents/graphs/phase2_pipeline.py
              |
              v
        ResearchPlanner
              |
              v
        Firecrawl Search
              |
              v
      Candidate Registry
              |
              v
    Crawl4AI SourcePreview
              |
              v
       SourceEvaluator
              |
              v
 Optional Site Exploration
              |
              v
       SourceSelector
              |
              v
   DatasetSchemaDesigner
              |
              v
 WAITING_FOR_SCHEMA_APPROVAL
              |
              v
        User Approval
              |
              v
    Crawl4AI Acquisition
              |
              v
        Processing
              |
              v
          Chunking
              |
              v
       ExtractionRouter
          /        \
         /          \
Deterministic     Semantic
 Extraction       Extraction
         \          /
          \        /
             |
             v
       Record Merge
             |
             v
       Field Evidence
             |
             v
    Evidence Validation
             |
             v
     Record Resolution
             |
             v
       Deduplication
             |
             v
 Structured / RAG / GraphRAG
```

---

# 6. Mevcut Mimarinin Güçlü Tarafları

## 6.1 Deterministic-first

Projede LLM her görev için zorunlu değildir.

Bu doğru bir mimari karardır.

Aşağıdakiler semantic extraction'dan önce kullanılabilir:

```text
CSS
XPath
Regex
Tables
ordinary parsing
```

Bu yaklaşım:

```text
token maliyetini azaltır
çıktıyı deterministik hale getirir
test edilebilirliği artırır
```

---

## 6.2 Multi-record Extraction

Chunk ve record birbirine eşit kabul edilmez.

Bir chunk:

```text
0
1
N
```

record üretebilir.

Bu yeni high-volume ingestion sistemi için önemli bir temel sağlar.

---

## 6.3 Evidence Preservation

Model çıktısının tek başına doğru kabul edilmemesi doğru bir tasarımdır.

Final knowledge:

```text
field
+
source
+
document
+
chunk
+
evidence
```

bağlantısını korumalıdır.

---

## 6.4 Provider Boundary

Semantic extraction'ın belirli bir LLM sağlayıcısına tamamen bağlanmaması gelecekte local-first routing için doğru temeldir.

---

# 7. Mevcut Mimarinin Eksikleri

Mevcut sistem başarılı bir dataset-generation pipeline'dır ancak hedeflenen knowledge platform için aşağıdaki eksikler bulunmaktadır.

## 7.1 Kalıcı Knowledge Store Yok

Run sonucu dataset oluşturulmaktadır ancak bilgi platform seviyesinde uzun ömürlü olarak bir knowledge database içerisinde birikmemektedir.

---

## 7.2 Research Tek Seferlik

Mevcut akış genel olarak:

```text
plan
search
crawl
extract
finish
```

şeklindedir.

Sistem:

```text
Bu kayıtta ne eksik?
```

sorusuyla yeni research round üretmemektedir.

---

## 7.3 Entity Bazlı Knowledge Yok

Dataset record'ları vardır ancak platform genelinde kalıcı:

```text
Entity
Fact
Relation
```

katmanı henüz ana mimarinin parçası değildir.

---

## 7.4 Enrichment Queue Yok

Eksik bilgiler ayrı araştırma görevleri olarak saklanmamaktadır.

---

## 7.5 Cloud Intelligence Hâlâ Fazla Merkezi

Provider abstraction başlamış olsa da bütün intelligence katmanı henüz local-first değildir.

---

# 8. Hedef Mimari

Yeni sistem aşağıdaki mimariye dönüşecektir.

```text
                         USER REQUEST
                              |
                              v
                     Request / Schema
                              |
                              v
                       Local Planner
                              |
                              v
                      Source Discovery
                              |
                              v
                     Candidate Registry
                              |
                              v
                       Web Acquisition
                              |
                +-------------+-------------+
                |                           |
                v                           v
         RAW SOURCE STORE            Link Discovery
                |
                v
          DOCUMENT STORE
                |
                v
           CHUNK STORE
                |
                v
       Extraction Router
        /             \
       v               v
Deterministic      Local Semantic
 Extraction         Extraction
       \               /
        +------+-------+
               |
               v
          Records / Facts
               |
               v
        Evidence Validation
               |
               v
          Entity Resolution
               |
               v
      POSTGRES KNOWLEDGE STORE
               |
       +-------+--------+
       |                |
       v                v
 Coverage Ledger     Dataset Export
       |
       v
 Missing / Weak / Conflict?
       |
      YES
       |
       v
 Research Task Queue
       |
       v
   Local Planner
       |
       v
 Search / Crawl / Extract
       |
       v
 Knowledge Store Update
```

---

# 9. Veritabanı Mimari Kararı

## Database

Başlangıç canonical database:

```text
PostgreSQL
```

Önerilen erişim:

```text
SQLAlchemy 2.x
Alembic migrations
```

---

# 10. Data Layers

Platform dört mantıksal veri katmanına sahip olacaktır.

## Layer 1 — Source

```text
Source URL
Domain
Discovery origin
Retrieval information
```

## Layer 2 — Document

```text
Raw content
Processed content
HTML
Markdown
Chunks
```

## Layer 3 — Knowledge

```text
Entities
Facts
Relations
Evidence
Conflicts
```

## Layer 4 — Consumer Dataset

```text
Structured
RAG
GraphRAG
JSON
JSONL
DataFrame
```

Consumer dataset knowledge'in kendisi değildir.

Knowledge katmanından üretilen bir görünüm/artifact'tır.

---

# 11. Planned Database State

Aşağıdaki tablolar hedeflenmektedir:

```text
datasets
research_runs

sources
documents
document_chunks

dataset_records
field_evidence

entities
facts
relations
fact_evidence

coverage_states
research_tasks

provider_runs
```

---

# 12. Canonical Information Flow

```text
WEB
 |
 v
sources
 |
 v
documents
 |
 v
document_chunks
 |
 v
extraction
 |
 +-----> dataset_records
 |
 +-----> entities
           |
           +-----> facts
           |
           +-----> relations
                    |
                    v
                  evidence
                    |
                    v
               coverage_state
                    |
                    v
               research_tasks
```

---

# 13. AI'nin Rolü

AI:

```text
karar vermeli
anlam çıkarmalı
belirsizliği çözmeli
arama stratejisi üretmeli
semantic extraction yapmalı
```

AI:

```text
HTTP istemcisi olmamalı
crawler olmamalı
database transaction yöneticisi olmamalı
regex yerine kullanılmamalı
basit filtering yerine kullanılmamalı
schema validator yerine kullanılmamalı
```

Ana kural:

> AI intelligence sağlar. Sistem işlemleri deterministik araçlar gerçekleştirir.

---

# 14. Local-First Hedefi

Nihai routing:

```text
DETERMINISTIC
      |
 unresolved
      v
LOCAL MODEL
      |
      v
VALIDATION
   /       \
 PASS      FAIL
  |          |
SAVE     CLOUD MODEL
```

Cloud provider normal çalışma yolu değil, escalation yolu olmalıdır.

Bu geçiş yalnız benchmark sonucunda yapılacaktır.

---

# 15. Current Phase State

| Phase | Name                                    | Status      |
| ----- | --------------------------------------- | ----------- |
| 0–27  | Previous Dataset Generation Iteration   | COMPLETED   |
| 28    | Persistent Storage Foundation           | COMPLETED   |
| 29    | High-Volume Knowledge Ingestion         | COMPLETED   |
| 30    | Knowledge Model and Entity Resolution   | COMPLETED   |
| 31    | Coverage and Enrichment Research Loop   | COMPLETED   |
| 32    | Local-First Intelligence and Acceptance | COMPLETED   |

---

# 16. Implementation History

Bu tablo AI tarafından her faz sonunda güncellenmelidir.

| Phase | Tarih      | Yapılan İş                                                 | Nasıl Yapıldı                                                                              | Değişen Ana Dosyalar      | Test / Kanıt          | Projeye Katkısı                                 |
| ----- | ---------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------- | --------------------- | ----------------------------------------------- |
| 0–27  | Historical | Request-aware evidence-backed dataset pipeline oluşturuldu | LangGraph + Firecrawl + Crawl4AI + deterministic/semantic extraction + validation + export | Mevcut canonical codebase | Historical test suite | Güvenilir dataset-generation temelini oluşturdu |
| 28    | 2026-08-31 | Persistent storage foundation tamamlandı; pipeline storage node'u eklendi | SQLAlchemy modelleri, PostgreSQL JSONB varyantları, Alembic migration'ı, idempotent pipeline mapper/repository ve opt-in storage node oluşturuldu; Bronze/Silver aynı URL için tek document kaydında korunuyor | `src/storage/`; `alembic/`; `src/agents/nodes/storage_node.py`; `src/agents/graphs/phase2_pipeline.py`; `requirements-baseline.txt`; `.env.example`; `src/state/state.py`; `src/core/tokenization.py`; `src/agents/nodes/manifest_node.py` | Storage tests `4 passed`; full suite `272 passed, 13 skipped`; Alembic clean SQLite ve PostgreSQL upgrade `0001_persistent_storage (head)`; PostgreSQL pipeline `completed` ile 1 run/source/document/chunk/record/evidence; repeat persistence `0` yeni record/evidence; compileall, pip check, diff-check geçti | JSON export korunurken source/document/chunk/record/evidence bilgileri artık transaction ve idempotency ile kalıcı knowledge altyapısına aktarılıyor |
| 29    | —          | —                                                          | —                                                                                          | —                         | —                     | —                                               |
| 29    | 2026-08-31 | High-volume ingestion metrikleri ve 25-kayıt gold acceptance tamamlandı | Existing multi-record `records[]` akışı korunarak source/chunk dağılımı, knowledge-yield ve kalıcı traceability doğrulandı; eski validation kuralları gevşetilmedi | `src/agents/nodes/manifest_node.py`; `tests/evaluation/fixtures/phase29_high_volume.json`; `tests/evaluation/test_phase29_high_volume.py` | Gold: 25 extracted, 25 accepted, 50 supported fields, evidence support rate 1.0; SQLite DB: 25 records + 25 evidence; full suite `283 passed, 13 skipped` | Kaynaklardan özet yerine mümkün olan tüm evidence-backed bağımsız kayıtların ölçülebilir ve kalıcı işlenmesini sağladı |
| 30    | 2026-08-31 | Knowledge model, deterministic entity resolution ve conflict-preserving writer tamamlandı | Entity/fact/relation/evidence tabloları ve migration eklendi; dataset records identity linkleriyle canonical entity'lere bağlandı; aynı predicate için farklı değerler conflict olarak korundu; yalnız açık evidence-backed relation yazıldı | `src/storage/models/knowledge.py`; `src/knowledge/entity_resolution.py`; `src/knowledge/knowledge_writer.py`; `src/storage/repositories/pipeline_repository.py`; `alembic/versions/0001_persistent_storage.py`; `tests/unit/test_knowledge_writer.py` | 3 source → 1 canonical entity, 4 fact, 6 knowledge evidence, 2 conflict; explicit relation test; clean PostgreSQL migration head; focused `9 passed`; full suite `283 passed, 13 skipped`; compileall geçti | Dataset record ile kalıcı knowledge entity/fact/relation katmanını ayırdı; provenance ve çelişki kaybını engelledi |
| 31    | 2026-08-31 | Coverage ledger ve bounded enrichment research loop tamamlandı | `coverage_states` ve `research_tasks` kalıcı modelleri, missing/conflicting/supported analizi, priority, `max_tasks_per_round` ve `max_rounds` sınırları eklendi; knowledge write sonrasına coverage ve enrichment planner bağlandı; ikinci fixture turu task completion ile doğrulandı | `src/storage/models/coverage.py`; `src/knowledge/coverage.py`; `src/agents/nodes/coverage_analysis_node.py`; `src/agents/nodes/enrichment_planner_node.py`; `src/agents/graphs/phase2_pipeline.py`; `alembic/versions/0001_persistent_storage.py`; `tests/unit/test_phase31_coverage.py` | Acceptance: missing → task pending → second source/evidence → supported → task completed; focused `5 passed`; full suite `283 passed, 13 skipped`; clean PostgreSQL migration head; compileall geçti | Sistem artık coverage sonucu task üretip bütçeli enrichment round planlayabiliyor; tek-run generator sınırı aşıldı |
| 32    | 2026-08-31 | Benchmark-gated local-first routing ve final acceptance tamamlandı | Ollama local adapter ve local-first/cloud fallback router eklendi; local-first yalnız benchmark onayıyla deneniyor; evidence/structured-output kalite kapısından geçmeyen batch Groq’a devrediliyor; Groq structured-schema uyumsuzluğu JSON-object fallback ile ele alınıyor | `src/tools/structured_generation/ollama_provider.py`; `src/tools/structured_generation/routing_provider.py`; `src/tools/structured_generation/groq_provider.py`; `src/tools/structured_generation/__init__.py`; `scripts/run_phase24_local_model_evaluation.py`; `src/state/state.py`; `src/knowledge/knowledge_writer.py`; `.env`; `.env.example`; `tests/evaluation/test_phase32_final_acceptance.py`; `tests/unit/test_local_first_routing.py` | Routing tests `15 passed`; final end-to-end test passed; full suite `283 passed, 13 skipped`; routed gold: 8 local calls, 2 cloud fallbacks, fallback rate `0.25`, record recall `0.9167`, field precision `0.9697`, field recall `0.9143`, unsupported `0.0`, schema validity `1.0`, latency `83.54s`; `.env` local-first enabled | Local model artık normal semantic yol olarak deneniyor; yalnız kalite/evidence sorunu olduğunda Groq escalation yapılıyor; Crawl4AI, database ve transaction sınırları modele devredilmedi |

## Phase 28 Progress Record — 2026-08-31

Status: `COMPLETED`

Goal: Preserve the existing JSON pipeline while adding an idempotent relational persistence boundary for datasets, runs, sources, documents, chunks, records, and field evidence.

Implemented:

- Added SQLAlchemy 2.x models with PostgreSQL `JSONB` variants and SQLite-compatible test support.
- Added Alembic configuration and the `0001_persistent_storage` migration.
- Added a repository mapper that writes JSON-safe pipeline state in one transaction, upserts canonical sources, reuses one document per source/run, and prevents duplicate records/evidence on repeat persistence.
- Added an opt-in `storage` graph node after export; existing JSON/JSONL export remains active when storage is enabled.
- Added baseline dependencies and `DATABASE_URL`/`STORAGE_ENABLED` examples.
- Hardened token-counter initialization so an unavailable tiktoken cache falls back deterministically during offline runs.

Tests and evidence:

- `tests/storage/test_database_persistence.py`: `4 passed`.
- `tests/storage/test_database_persistence.py tests/unit/test_run_manifest.py`: `4 passed`.
- Full offline suite: `271 passed, 13 skipped`.
- `compileall`, `pip check`, and `git diff --check`: passed.
- Alembic clean SQLite upgrade reached `0001_persistent_storage (head)`.
- Manifest now exposes storage persistence counts under `run_metrics.storage`.
- Transaction rollback is covered for JSON serialization failures; no partial run/source rows remain after the failed transaction.
- PostgreSQL offline SQL generation produced `JSONB` columns, but a live clean PostgreSQL migration has not yet been executed because no local PostgreSQL server is available.

Architecture decision: storage is opt-in and isolated behind `storage_node.py` and `pipeline_repository.py`; LangGraph nodes do not execute SQL directly, and Pydantic models remain the application contracts. The database removes the limitation that run knowledge exists only in transient state and export files, while preserving the existing consumer artifacts.

Known problem: the Turkish-culture request currently combines a folk-culture topic with a traditional-dishes constraint and a Malatya food seed URL. This is a request-quality issue, not a storage failure, and should be corrected before a production run.

Next Phase Readiness: `READY` for Phase 29. All Phase 28 acceptance criteria passed on a clean PostgreSQL 16 test database and the full offline regression remains green.

# Phase 28 Completion Record

Status: `COMPLETED`

Date: `2026-08-31`

Goal: Add persistent, evidence-preserving storage without changing the existing dataset-generation behavior.

Implemented: SQLAlchemy 2.x engine/session boundary, PostgreSQL JSONB-capable models, Alembic migration, idempotent source/document/record/evidence repository, opt-in LangGraph storage node, observable storage metrics, baseline dependencies, and offline tiktoken fallback.

Files Added: `src/storage/__init__.py`; `src/storage/database.py`; `src/storage/models/`; `src/storage/repositories/`; `src/agents/nodes/storage_node.py`; `alembic.ini`; `alembic/env.py`; `alembic/script.py.mako`; `alembic/versions/0001_persistent_storage.py`; `tests/storage/test_database_persistence.py`.

Files Modified: `src/agents/graphs/phase2_pipeline.py`; `src/agents/nodes/manifest_node.py`; `src/state/state.py`; `src/core/tokenization.py`; `.env.example`; `requirements-baseline.txt`; `configs/domains/turkish_culture/request.yaml`; this management record.

Database Changes: Added `datasets`, `research_runs`, `sources`, `documents`, `document_chunks`, `dataset_records`, and `field_evidence` with foreign keys, indexes, uniqueness constraints, JSONB payloads on PostgreSQL, and Alembic revision `0001_persistent_storage`.

Architecture Changes: Persistence is behind a repository and mapper boundary; LangGraph invokes one storage node after export; Pydantic remains the application contract; crawler/provider objects never enter state; JSON artifacts remain available.

Tests Executed: `pytest tests/storage/test_database_persistence.py -q`; `pytest -q`; `alembic upgrade head` on clean SQLite and PostgreSQL 16; PostgreSQL mock-pipeline persistence and repeat-write check; `compileall`; `pip check`; `git diff --check`.

Test Results: Storage `4 passed`; full offline suite `272 passed, 13 skipped`; PostgreSQL migration reached `0001_persistent_storage (head)`; pipeline produced 1 run, 1 source, 1 document, 1 chunk, 1 record, and 1 evidence; repeat persistence inserted 0 records and 0 evidence.

Benchmark Results: Phase 28 is a persistence/reliability phase; no model quality benchmark was required. Storage repeat-write and clean-database counts are the acceptance measurements.

What Worked: Atomic writes, canonical source upsert, one document per source/run, evidence foreign keys, JSON export compatibility, PostgreSQL JSONB migration, and idempotent repeat persistence.

What Did Not Work: The first run-key implementation created a new run when the same post-manifest state was persisted; this was corrected by prioritizing the existing `storage_metrics.run_key`. Docker Engine was initially unavailable but the acceptance was later completed after starting Docker Desktop.

Contribution to Project: Database persistence removes the limitation that knowledge exists only in transient LangGraph state and exported JSON files. Sources, raw/processed documents, chunks, validated records, and evidence can now survive runs and be queried by later knowledge/enrichment phases.

New Technical Debt: The storage node is opt-in for backward compatibility; production PostgreSQL credentials and operational backup/retention policy remain deployment concerns. The Turkish-culture request still has a folk-culture topic combined with a traditional-dishes constraint and food seed URL.

Known Risks: Source/document history currently stores one document per source/run and does not yet provide cross-run document version querying; entity/fact/relation tables are intentionally deferred to Phase 30.

Why Acceptance Gate Passed: Existing JSON output and full regression passed; clean PostgreSQL 16 migration succeeded; the enabled mock pipeline completed and wrote all required relational records; a second persistence of the same state created no duplicate source, run, record, or evidence.

Next Phase Readiness: `READY`

---

# 17. AI Contribution Assessment

Her faz sonunda AI bu bölüme yeni kayıt eklemelidir.

Şablon:

```text
## Phase XX Contribution Assessment

### Problem Before

Bu fazdan önce sistemdeki problem neydi?

### Implementation

Problem teknik olarak nasıl çözüldü?

### Architectural Contribution

Bu değişiklik mimarinin hangi özelliğini iyileştirdi?

### User Value

Kullanıcı açısından ne değişti?

### Quality Impact

Kalite arttı mı?
Nasıl ölçüldü?

### Cost Impact

Token/API/compute maliyetinde nasıl bir değişiklik oldu?

### Complexity Cost

Yeni mimari hangi ek karmaşıklığı getirdi?

### AI Assessment

Bu kararın projenin uzun vadeli hedefleri açısından doğru olup olmadığına dair teknik değerlendirme.

### Remaining Risk

Hangi risk devam ediyor?
```

AI'nın değerlendirmesi yalnız:

```text
"Bu iyi oldu."
```

şeklinde olamaz.

Somut mimari gerekçe yazmalıdır.

---

# 18. Architecture Decision Log

Her önemli karar buraya eklenmelidir.

| ID      | Karar                                        | Alternatif                  | Neden Seçildi                                                               | Sonuç   |
| ------- | -------------------------------------------- | --------------------------- | --------------------------------------------------------------------------- | ------- |
| ADR-001 | LangGraph orchestrator olarak korunacak      | Custom orchestration        | Mevcut pipeline ve state sistemi zaten bunun üzerinde                       | KEEP    |
| ADR-002 | Deterministic-first korunacak                | LLM-first                   | Daha düşük maliyet ve daha yüksek test edilebilirlik                        | KEEP    |
| ADR-003 | Evidence final bilginin zorunlu parçası      | Model confidence'a güvenmek | Kaynak izlenebilirliği gerekir                                              | KEEP    |
| ADR-004 | PostgreSQL persistent store kullanılacak     | Yalnız JSON files           | Kalıcı, sorgulanabilir, ilişkisel ve JSONB destekli knowledge store gerekli | PLANNED |
| ADR-005 | Dataset record ve knowledge entity ayrılacak | Tek generic JSON tablosu    | Aynı knowledge farklı datasetlere dönüştürülebilmeli                        | PLANNED |
| ADR-006 | Research enrichment loop eklenecek           | Tek-pass research           | Eksik kayıtların zamanla zenginleşmesi gerekli                              | PLANNED |
| ADR-007 | Local-first AI routing kullanılacak          | Cloud-only                  | Cloud token ve API maliyetini azaltmak                                      | PLANNED |

---

# 19. Database State

AI Phase 28'den itibaren bu tabloyu güncellemelidir.

| Component       | Status      | Migration | Repository | Tests |
| --------------- | ----------- | --------- | ---------- | ----- |
| datasets        | TESTED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite + PostgreSQL tested |
| research_runs   | TESTED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite + PostgreSQL tested |
| sources         | TESTED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite + PostgreSQL tested |
| documents       | TESTED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite + PostgreSQL tested |
| document_chunks | TESTED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite + PostgreSQL tested |
| dataset_records | TESTED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite + PostgreSQL tested |
| field_evidence  | TESTED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite + PostgreSQL tested |
| entities        | TESTED | `0001_persistent_storage` | `pipeline_repository.py` + `knowledge_writer.py` | SQLite + PostgreSQL tested |
| facts           | TESTED | `0001_persistent_storage` | `pipeline_repository.py` + `knowledge_writer.py` | SQLite + PostgreSQL tested |
| relations       | TESTED | `0001_persistent_storage` | `pipeline_repository.py` + `knowledge_writer.py` | SQLite + PostgreSQL tested |
| fact_evidence   | TESTED | `0001_persistent_storage` | `pipeline_repository.py` + `knowledge_writer.py` | SQLite + PostgreSQL tested |
| dataset_record_entities | TESTED | `0001_persistent_storage` | `pipeline_repository.py` + `knowledge_writer.py` | SQLite + PostgreSQL tested |
| coverage_states | TESTED | `0001_persistent_storage` | `coverage.py` | SQLite acceptance tested |
| research_tasks  | TESTED | `0001_persistent_storage` | `coverage.py` | SQLite acceptance tested |

Allowed statuses:

```text
NOT_CREATED
IN_PROGRESS
CREATED
TESTED
PRODUCTION_READY
```

---

# 20. Research Loop State

| Capability                    | Status      | Notes            |
| ----------------------------- | ----------- | ---------------- |
| Initial ResearchPlanner       | EXISTS      | Existing system  |
| Source discovery              | EXISTS      | Firecrawl        |
| Site exploration              | EXISTS      | Bounded Crawl4AI |
| Coverage Ledger               | NOT_CREATED | Phase 31         |
| Missing-field detection       | NOT_CREATED | Phase 31         |
| Research task queue           | NOT_CREATED | Phase 31         |
| Gap-specific query generation | NOT_CREATED | Phase 31         |
| Repeated research rounds      | NOT_CREATED | Phase 31         |
| Information gain stop         | NOT_CREATED | Phase 31         |

---

# 21. Local Model State

| Capability                            | Status          |
| ------------------------------------- | --------------- |
| StructuredGenerationProvider boundary | EXISTS          |
| Local provider abstraction            | EXISTS / VERIFY |
| Real local backend                    | NOT_CONNECTED   |
| Local semantic extraction             | NOT_PRODUCTION  |
| Local research planning               | NOT_IMPLEMENTED |
| Local gap planning                    | NOT_IMPLEMENTED |
| Groq benchmark                        | REQUIRED        |
| Local-first routing                   | DISABLED        |
| Cloud fallback                        | PLANNED         |

AI burada gerçek kodu kontrol etmeden `EXISTS` veya `COMPLETED` yazmamalıdır.

---

# 22. Quality Metrics

Her benchmark/run sonrasında mümkün olan metrikler yazılmalıdır.

```text
sources_discovered
sources_selected
documents_acquired
total_words
total_chunks

records_extracted
accepted_records
rejected_records
records_per_source
records_per_chunk

supported_fields
unsupported_fields
evidence_support_rate

entities_created
entities_merged
facts_created
relations_created

missing_fields
resolved_missing_fields
conflicts
resolved_conflicts

research_rounds
new_information_per_round

local_calls
cloud_calls
fallback_rate

input_tokens
output_tokens
estimated_cloud_cost
latency
```

---

# 23. Known Problems

Başlangıç problemleri:

## KP-001 — Bilgi Hacmi

Kaynaklar bulunmasına rağmen database seviyesinde yeterli bilgi hacmi oluşmayabilir.

Çözüm yönü:

```text
multi-record extraction
high-volume ingestion
knowledge-yield metrics
```

---

## KP-002 — Tek Seferlik Araştırma

Eksik alanlar yeni araştırma tetiklememektedir.

Çözüm:

```text
CoverageLedger
ResearchTask
EnrichmentQueue
```

---

## KP-003 — Kalıcı Knowledge Yok

Run sonuçları reusable global knowledge olarak saklanmamaktadır.

Çözüm:

```text
PostgreSQL Knowledge Store
```

---

## KP-004 — Cloud Token Kullanımı

Semantic intelligence cloud provider üzerinde gereğinden pahalı olabilir.

Çözüm:

```text
deterministic
→ local
→ cloud fallback
```

---

# 24. Technical Debt

AI yeni teknik borçları bu tabloya eklemelidir.

| ID     | Teknik Borç                                                | Ortaya Çıktığı Faz  | Risk                                | Çözüm                                                             |
| ------ | ---------------------------------------------------------- | ------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| TD-001 | Historical docs oldukça büyük                              | Existing            | AI context maliyeti                 | Yeni PM knowledge dosyasını compact canonical state olarak kullan |
| TD-002 | Direct provider dependencies bulunabilir                   | Existing            | Local-first migration zorlaşabilir  | Phase 32 provider migration                                       |
| TD-003 | Production PostgreSQL operasyonel backup/retention politikası tanımlı değil | Phase 28 | Deployment reliability remains environment-dependent | Define deployment runbook and backup/retention policy |

---

# 25. Phase Completion Record Template

AI her faz sonunda aşağıdaki kaydı eklemelidir.

```text
# Phase XX Completion Record

Status:
COMPLETED / BLOCKED

Date:

Goal:

Implemented:

Files Added:

Files Modified:

Database Changes:

Architecture Changes:

Tests Executed:

Test Results:

Benchmark Results:

What Worked:

What Did Not Work:

Contribution to Project:

New Technical Debt:

Known Risks:

Why Acceptance Gate Passed:

Next Phase Readiness:
READY / NOT_READY
```

---

# 26. AI İçin Yasaklar

AI:

* önceki Phase 0–27 kodunu sebepsiz yeniden yazamaz,
* kanıt olmadan bir özelliği `COMPLETED` yazamaz,
* başarısız testleri gizleyemez,
* kullanıcı artifact'larını silemez,
* database migration'larını geriye dönük kontrol etmeden değiştiremez,
* evidence bağlantısını kaldırarak optimizasyon yapamaz,
* token azaltmak için veri kalitesini sessizce düşüremez,
* local model JSON üretti diye sonucu doğru kabul edemez,
* benchmark olmadan local-first'i production default yapamaz,
* araştırma loop'unu limitsiz çalıştıramaz.

---

# 27. AI İçin Faz Sonu Düşünme Soruları

Her faz sonunda AI kendi implementasyonunu şu sorularla değerlendirmelidir:

```text
1. Bu faz hangi gerçek problemi çözdü?

2. Çözüm mevcut mimarinin üzerine mi kuruldu,
   yoksa gereksiz duplicate sistem mi oluşturuldu?

3. Yapılan değişiklik bilgi kalitesini artırdı mı?

4. Yapılan değişiklik bilgi hacmini artırdı mı?

5. Evidence/provenance korundu mu?

6. Yeni sistem test edilebilir mi?

7. Bu iş deterministic yapılabilecekken LLM kullandım mı?

8. Cloud model gereksiz kullanılıyor mu?

9. Database idempotent çalışıyor mu?

10. Aynı bilgi tekrar geldiğinde ne oluyor?

11. Çelişkili bilgi geldiğinde ne oluyor?

12. Pipeline yarıda kesilirse ne oluyor?

13. Bu faz kullanıcıya somut olarak ne kazandırdı?

14. Sonraki faza geçmek için gerçekten hazır mıyız?
```

Bu soruların önemli cevapları bu dosyaya kaydedilmelidir.

---

# 28. Nihai Sistem Tanımı

Projenin başarılı son hali:

```text
Web üzerinde araştırma yapan
+
kaynak keşfeden
+
site içeriğini derinlemesine alan
+
raw içeriği kaybetmeden saklayan
+
çok sayıda structured bilgi çıkaran
+
evidence doğrulayan
+
aynı entity'leri birleştiren
+
fact ve relation üreten
+
PostgreSQL'e yazan
+
eksik alanları tespit eden
+
yeni araştırma görevi oluşturan
+
bilgiyi zaman içerisinde zenginleştiren
+
local modeli normal intelligence motoru kullanan
+
yalnız gerekli durumda cloud modele çıkan
+
aynı knowledge'dan JSON / JSONL / DataFrame / RAG / GraphRAG üretebilen
```

bir sistemdir.

Kısaca:

```text
Knowledge Extraction Platform
        ↓
Knowledge Acquisition Platform
        ↓
Persistent Evidence-Backed Knowledge System
```

dönüşümü hedeflenmektedir.

# Phase 29 Completion Record

Status: `COMPLETED`

Date: `2026-08-31`

Goal: Increase information volume without collapsing records, weakening evidence validation, or losing source/chunk provenance.

Implemented: Added observable `records_per_source`, `records_per_chunk`, and per-source `knowledge_yield` metrics to the run manifest. Preserved the existing zero/one/many `ExtractionBatch.records[]` contract and validated a 25-record gold source through evidence binding and the quality gate. Verified persistence of all 25 records and their 25 traceable evidence entries.

Files Added: `tests/evaluation/fixtures/phase29_high_volume.json`; `tests/evaluation/test_phase29_high_volume.py`.

Files Modified: `src/agents/nodes/manifest_node.py`; this management record.

Database Changes: No new tables; Phase 28 storage persists the high-volume records, chunks, and evidence without truncation.

Architecture Changes: Knowledge yield is computed from extracted records, populated fields, supported fields, accepted records, and source word counts. It is an observable metric rather than a model self-report. Existing deterministic-first routing, evidence validation, resolution, and deduplication remain unchanged.

Tests Executed: `pytest tests/evaluation/test_phase29_high_volume.py -q`; `pytest -q`; `compileall`; `pip check`; `git diff --check`.

Test Results: Gold tests `3 passed`; full suite `277 passed, 13 skipped`; gold acceptance measured 25 extracted, 25 accepted, 50 populated fields, 50 supported fields, and evidence support rate `1.0`; persistence measured 25 dataset records and 25 field-evidence rows.

Benchmark Results: The 25-record fixture demonstrates capacity and evidence preservation; it is not a live-provider quality claim. No truncation or hidden first-record limit was observed.

What Worked: A single chunk retained all 25 independent records; field evidence binding located supplied content; quality gate accepted only supported records; source/chunk metrics and database persistence remained traceable.

What Did Not Work: The first acceptance test initially measured supported fields from an empty verification list; the fixture was corrected to pass the complete 25-record evidence-validation result. No production code was weakened to make the test pass.

Contribution to Project: The platform now exposes whether higher output volume represents real evidence-backed knowledge rather than merely more model output. Downstream operators can compare source yield and accepted knowledge per source/chunk.

New Technical Debt: Knowledge-yield weighting is intentionally descriptive rather than a single normalized score; future phases may use it in coverage prioritization. Provider-side pagination remains bounded by each provider contract and is not silently inferred as completeness.

Known Risks: A high record count can still increase model latency and storage size; budgets and retry limits remain necessary. Cross-entity knowledge modeling is deferred to Phase 30.

Why Acceptance Gate Passed: The 25-record gold source produced measurable extraction/acceptance/evidence results, all records survived the quality gate, and the storage test wrote every record and evidence row with source/chunk traceability. Full regression remained green.

Next Phase Readiness: `READY`

# Phase 30 Completion Record

Status: `COMPLETED`

Date: `2026-08-31`

Goal: Convert accepted dataset records into deterministic, evidence-backed canonical entities, facts, and relations while preserving conflicts and provenance.

Implemented: Added entity, fact, relation, fact-evidence, and dataset-record/entity association models; deterministic identity normalization and resolution; a transactional knowledge writer; conflict-preserving fact upserts; and an explicit evidence requirement for relation writes. Legacy co-occurrence relations are not persisted as knowledge relations.

Files Added: `src/storage/models/knowledge.py`; `src/knowledge/__init__.py`; `src/knowledge/entity_resolution.py`; `src/knowledge/knowledge_writer.py`; `tests/unit/test_knowledge_writer.py`.

Files Modified: `src/storage/models/__init__.py`; `src/storage/database.py`; `src/storage/repositories/pipeline_repository.py`; `alembic/versions/0001_persistent_storage.py`; `tests/storage/test_database_persistence.py`; this management record.

Database Changes: Extended migration `0001_persistent_storage` with `entities`, `facts`, `relations`, `fact_evidence`, and `dataset_record_entities`, including foreign keys, deterministic uniqueness constraints, indexes, and PostgreSQL JSONB-compatible payload columns.

Architecture Changes: Dataset records remain the extraction/export contract; canonical knowledge is a separate persistent layer. Three records from three sources can resolve to one entity while each fact and evidence reference remains source-traceable. A different value for the same entity/predicate is preserved as a conflict rather than overwriting the prior fact.

Tests Executed: `pytest tests/unit/test_knowledge_writer.py tests/evaluation/test_phase29_high_volume.py tests/storage/test_database_persistence.py -q`; full `pytest -q`; `compileall`; clean PostgreSQL 16 Alembic migration and PostgreSQL knowledge-writer acceptance test.

Test Results: Focused tests `9 passed`; full offline suite `277 passed, 13 skipped`; clean PostgreSQL migration reached `0001_persistent_storage (head)`; three source records produced 1 canonical entity, 4 facts, 6 knowledge-evidence rows, and 2 preserved conflicts; an explicit relation was written and an un evidenced co-occurrence relation was ignored.

Benchmark Results: Phase 30 is a deterministic persistence and knowledge-model acceptance phase; no live-provider quality claim is made. The acceptance measurements are canonical entity count, fact/conflict preservation, relation evidence gating, and PostgreSQL migration compatibility.

What Worked: Identity normalization, idempotent entity/fact/evidence writes, dataset-record links, conflict preservation, and evidence-gated relation persistence worked on SQLite and PostgreSQL.

What Did Not Work: No blocking implementation defect remained after acceptance. The first PostgreSQL verification invocation used the wrong environment variable for Alembic and therefore targeted SQLite; the command was corrected to `DATABASE_URL` and the clean PostgreSQL migration was then verified.

Contribution to Project: The platform is now able to retain a separate, queryable knowledge representation rather than stopping at dataset records. This is the foundation for coverage analysis, enrichment tasks, and later RAG/GraphRAG projections.

New Technical Debt: Relation evidence is currently stored with the relation attributes; a future phase can normalize relation-evidence rows if relation-level querying requires it. Entity identity depends on the approved schema identity fields and does not yet include fuzzy or alias resolution.

Known Risks: Incorrect schema identity fields can merge or split entities deterministically but incorrectly; this remains a schema-quality concern and must be monitored during enrichment.

Why Acceptance Gate Passed: Three sources resolved to one canonical entity with all source evidence retained, conflicts remained queryable, relations required explicit evidence, clean PostgreSQL migration succeeded, and the full offline regression stayed green.

Next Phase Readiness: `READY` for Phase 31.

# Phase 31 Completion Record

Status: `COMPLETED`

Date: `2026-08-31`

Goal: Detect incomplete or conflicting entity fields and create bounded, resumable enrichment work.

Implemented: Added persistent coverage ledger and research-task models, deterministic field status calculation, priority-based task creation, gap-focused query generation, task completion when evidence-backed facts arrive, and a graph branch that starts another discovery round only when the configured loop is enabled and the round budget remains.

Tests Executed: `pytest tests/unit/test_phase31_coverage.py tests/storage/test_database_persistence.py -q`; full `pytest -q`; `compileall`; clean PostgreSQL migration including coverage tables.

Test Results: Acceptance fixture measured missing field → pending task → second source/evidence → supported field → completed task; focused tests `5 passed`; full offline suite `281 passed, 13 skipped`; PostgreSQL Alembic reached `0001_persistent_storage (head)`.

Research Loop State: `coverage_analysis` runs after knowledge persistence; `enrichment_planner` emits gap queries; `_enrichment_route` enforces `research_loop.enabled` and `max_rounds`; `max_tasks_per_round` limits task creation and planning. Existing runs without loop configuration retain the prior finish behavior.

Coverage State: `supported`, `missing`, and `conflicting` statuses are persisted per dataset/entity/field with evidence counts. Existing canonical entities are updated through the knowledge writer, so enrichment does not create a duplicate identity.

Observed Improvement: The system now answers what is known, what is missing, and what requires conflict resolution, and can carry the answer into a later research round.

Known Failure Modes: A provider may return no new evidence; the loop then remains bounded by `max_rounds`. Identity-field mistakes still deterministically merge or split entities incorrectly and require schema review.

Why Acceptance Gate Passed: The fixture produced a missing coverage state and task, the second source supplied field evidence, coverage increased to supported, and the persisted task became completed without a duplicate entity. Full regression and clean migration remained green.

Next Phase Readiness: `READY`; Phase 32 local-first routing and final acceptance are complete.

# Phase 32 Completion Record — 2026-08-31

Status: `COMPLETED`

Implemented: Added an Ollama HTTP structured-generation adapter and a benchmark-gated local-first router. The router keeps the existing Groq provider as the default, attempts local generation only when both `LOCAL_FIRST_ENABLED` and `LOCAL_FIRST_BENCHMARK_APPROVED` are true, and escalates to cloud when the local call fails or the structured batch reports rejected records. Database, crawling, parsing, schema validation, and transaction responsibilities remain outside the model provider.

Benchmark Evidence: Ollama HTTP was reachable with `gemma4:e4b-it-qat` and `qwen2.5:3b`. The final routed benchmark used Gemma plus Groq fallback: 8 local calls, 2 cloud fallbacks, fallback rate `0.25`, record recall `0.9167`, field recall `0.9143`, field precision `0.9697`, schema-valid rate `1.0`, unsupported field rate `0.0`, and latency `83.53831` seconds. Groq-only comparison used `openai/gpt-oss-120b`: record recall `0.8333`, field recall `0.6286`, precision `0.758621`, unsupported field rate `0.0`, and latency `16.618852` seconds. The routed quality result justifies local-first with controlled escalation.

Known Failure Mode: The local model initially returned flat record fields instead of the required `records[].data` plus field-evidence contract; supplying Ollama’s output JSON Schema and routing non-traceable batches to Groq corrected the final quality result. This is correctly treated as a quality failure, not silently accepted as knowledge.

Current Decision: Set `LOCAL_FIRST_ENABLED=true`, `LOCAL_FIRST_BENCHMARK_APPROVED=true`, and `LOCAL_MODEL=gemma4:e4b-it-qat` in `.env`. The router preserves Groq as the quality fallback and the benchmark evidence gate prevents unsupported local knowledge from being accepted.

Why Acceptance Gate Passed: The local-first + fallback route produced valid Pydantic batches, zero unsupported fields after routing, higher record/field quality than the Groq-only comparison, and explicit fallback counts. Database writing, crawling, parsing, deduplication, schema validation, and transaction management remain outside the AI provider.

Next Phase Readiness: `READY`; all five requested phases are implemented and acceptance evidence is recorded.
