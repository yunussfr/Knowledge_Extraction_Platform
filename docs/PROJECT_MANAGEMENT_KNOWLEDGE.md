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
| 28    | Persistent Storage Foundation           | IN_PROGRESS |
| 29    | High-Volume Knowledge Ingestion         | NOT_STARTED |
| 30    | Knowledge Model and Entity Resolution   | NOT_STARTED |
| 31    | Coverage and Enrichment Research Loop   | NOT_STARTED |
| 32    | Local-First Intelligence and Acceptance | NOT_STARTED |

---

# 16. Implementation History

Bu tablo AI tarafından her faz sonunda güncellenmelidir.

| Phase | Tarih      | Yapılan İş                                                 | Nasıl Yapıldı                                                                              | Değişen Ana Dosyalar      | Test / Kanıt          | Projeye Katkısı                                 |
| ----- | ---------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------- | --------------------- | ----------------------------------------------- |
| 0–27  | Historical | Request-aware evidence-backed dataset pipeline oluşturuldu | LangGraph + Firecrawl + Crawl4AI + deterministic/semantic extraction + validation + export | Mevcut canonical codebase | Historical test suite | Güvenilir dataset-generation temelini oluşturdu |
| 28    | 2026-08-31 | Persistent storage foundation başlatıldı; pipeline storage node'u eklendi | SQLAlchemy modelleri, Alembic migration'ı, idempotent pipeline mapper/repository ve opt-in storage node oluşturuldu; Bronze/Silver aynı URL için tek document kaydında korunuyor | `src/storage/`; `alembic/`; `src/agents/nodes/storage_node.py`; `src/agents/graphs/phase2_pipeline.py`; `requirements-baseline.txt`; `.env.example`; `src/state/state.py`; `src/core/tokenization.py` | `tests/storage/test_database_persistence.py`: 3 passed; Alembic SQLite clean upgrade `0001_persistent_storage (head)`; compileall ve diff-check geçti; PostgreSQL/full regression henüz bekliyor | JSON export korunurken source/document/chunk/record/evidence bilgilerinin kalıcı ve tekrar çalıştırmada idempotent saklanması için temel atıldı |
| 29    | —          | —                                                          | —                                                                                          | —                         | —                     | —                                               |
| 30    | —          | —                                                          | —                                                                                          | —                         | —                     | —                                               |
| 31    | —          | —                                                          | —                                                                                          | —                         | —                     | —                                               |
| 32    | —          | —                                                          | —                                                                                          | —                         | —                     | —                                               |

## Phase 28 Progress Record — 2026-08-31

Status: `IN_PROGRESS`

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

Next Phase Readiness: `NOT_READY` until a clean PostgreSQL instance proves the migration and persistence integration gate. Phase 29 must not be marked started before that evidence is obtained.

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
| datasets        | CREATED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite tested |
| research_runs   | CREATED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite tested |
| sources         | CREATED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite tested |
| documents       | CREATED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite tested |
| document_chunks | CREATED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite tested |
| dataset_records | CREATED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite tested |
| field_evidence  | CREATED | `0001_persistent_storage` | `pipeline_repository.py` | SQLite tested |
| entities        | NOT_CREATED | —         | —          | —     |
| facts           | NOT_CREATED | —         | —          | —     |
| relations       | NOT_CREATED | —         | —          | —     |
| coverage_states | NOT_CREATED | —         | —          | —     |
| research_tasks  | NOT_CREATED | —         | —          | —     |

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
| TD-003 | PostgreSQL migration ve production connection henüz doğrulanmadı | Phase 28 | Database acceptance gate kanıtı eksik | Run clean PostgreSQL migration/integration gate before Phase 28 completion |

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
