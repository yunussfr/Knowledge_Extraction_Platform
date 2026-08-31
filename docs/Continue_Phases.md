# PHASES.md

# Knowledge Extraction Platform — Next Iteration Phases

## 1. Bu Dosyanın Amacı

Bu dosya, Knowledge Extraction Platform'un mevcut çalışan yapısını bozmadan bir sonraki mimariye taşımak için uygulanacak geliştirme fazlarını tanımlar.

Önceki iterasyondaki Phase 0–27 tamamlanmış kabul edilir.

Bu fazlar yeniden uygulanmayacaktır.

Önceki çalışmaların tarihsel kaydı:

* `docs/DEVELOPMENT_PROGRESS.md`
* `docs/ARCHITECTURE.md`
* Git geçmişi

üzerinden korunur.

Bu dosyanın kapsadığı yeni iterasyonun temel amacı:

> Sistemi yalnızca JSON/JSONL dataset üreten tek seferlik bir pipeline olmaktan çıkarıp web'den sürekli yapılandırılmış bilgi toplayabilen, kaynakları saklayan, kayıtları veritabanına yazan, eksikleri tekrar araştıran ve yapay zekâyı mümkün olduğunca yalnızca karar verme/anlam çıkarma görevlerinde kullanan bir Knowledge Acquisition Platform haline getirmek.

---

# 2. Hedef Sistem

Yeni iterasyon tamamlandığında sistem aşağıdaki yapıya ulaşmalıdır:

```text
USER REQUEST
     |
     v
Request / Schema
     |
     v
Research Planner
     |
     v
Source Discovery
     |
     v
Candidate Registry
     |
     v
Crawl4AI
Preview / Exploration / Acquisition
     |
     v
RAW SOURCE STORAGE
     |
     v
Document Processing
     |
     v
Chunk Storage
     |
     +--------------------------+
     |                          |
     v                          v
Deterministic Extraction   Local Semantic Extraction
     |                          |
     +------------+-------------+
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
       PostgreSQL Knowledge Store
                  |
        +---------+----------+
        |                    |
        v                    v
Completeness / Coverage   Export Layer
        |                    |
        v                    +--> JSON
Missing Knowledge?             JSONL
        |                       DataFrame
        YES                     RAG
        |                       GraphRAG
        v
Research Task Queue
        |
        v
Local Planner
        |
        v
Search / Crawl / Extract
        |
        +-----------> Knowledge Store
```

Sistemin çalışma biçimi artık:

```text
ARA
→ BUL
→ KAYNAĞI SAKLA
→ BİLGİYİ ÇIKAR
→ DOĞRULA
→ VERİTABANINA YAZ
→ EKSİKLERİ BUL
→ YENİDEN ARAŞTIR
→ KAYDI ZENGİNLEŞTİR
```

olmalıdır.

---

# 3. Temel Geliştirme Kuralları

Her faz başlamadan önce AI aşağıdaki dosyaları okumalıdır:

```text
docs/PROJECT_MANAGEMENT_KNOWLEDGE.md
docs/PHASES.md
docs/ARCHITECTURE.md
docs/RULES.md
docs/DEVELOPMENT_PROGRESS.md
```

Ancak `DEVELOPMENT_PROGRESS.md` tarihsel referanstır.

Yeni iterasyonun aktif proje hafızası:

```text
docs/PROJECT_MANAGEMENT_KNOWLEDGE.md
```

dosyasıdır.

Her faz sonunda AI bu dosyayı güncellemeden fazı `COMPLETED` olarak işaretleyemez.

---

# 4. Faz Durumları

Yalnız şu durumlar kullanılmalıdır:

```text
NOT_STARTED
IN_PROGRESS
BLOCKED
COMPLETED
```

Bir faz yalnız Acceptance Gate geçildikten sonra `COMPLETED` olabilir.

---

# PHASE 28 — Persistent Storage Foundation

## Amaç

Mevcut pipeline'ın ürettiği bilgileri yalnızca JSON dosyasına yazmak yerine kalıcı bir PostgreSQL veritabanına yazabilecek temel altyapıyı oluşturmak.

Bu faz araştırma davranışını değiştirmez.

İlk olarak yalnız storage katmanı eklenir.

---

## Neden Gerekiyor?

Şu anda pipeline'ın değerli çıktıları ağırlıklı olarak run-state ve çıktı dosyalarında tutuluyor.

Yeni sistemde:

* kaynakların,
* dokümanların,
* chunk'ların,
* çıkarılan kayıtların,
* evidence bilgilerinin,
* entity bilgilerinin,
* araştırma görevlerinin

zaman içerisinde korunması gerekir.

Bu nedenle veritabanı platformun kalıcı hafızası olacaktır.

---

## Teknoloji

Başlangıç tercihi:

```text
PostgreSQL
SQLAlchemy 2.x
Alembic
```

PostgreSQL tercih edilmesinin nedeni:

* ilişkisel kayıtları desteklemesi,
* JSONB desteklemesi,
* entity/relation yapısına uygun olması,
* güçlü index desteği,
* ileride pgvector eklenebilmesi,
* structured dataset ile knowledge-base yapısını aynı yerde destekleyebilmesidir.

---

## Oluşturulacak Kod Alanları

Yeni:

```text
src/storage/
    __init__.py
    database.py
    models/
    repositories/
    migrations/
```

Önerilen yapı:

```text
src/storage/
├── database.py
├── models/
│   ├── dataset.py
│   ├── run.py
│   ├── source.py
│   ├── document.py
│   ├── chunk.py
│   ├── record.py
│   └── evidence.py
└── repositories/
    ├── dataset_repository.py
    ├── source_repository.py
    ├── document_repository.py
    └── record_repository.py
```

Ayrıca incelenecek:

```text
src/state/state.py
src/schemas/
src/agents/graphs/phase2_pipeline.py
src/agents/nodes/
src/core/
.env.example
requirements-baseline.txt
requirements.txt
```

---

## İlk Veritabanı Tabloları

### datasets

```text
id
name
topic
purpose
schema_json
schema_version
created_at
updated_at
```

### research_runs

```text
id
dataset_id
status
started_at
completed_at
request_json
metrics_json
```

### sources

```text
id
canonical_url
domain
title
source_type
content_hash
first_seen_at
last_seen_at
```

### documents

```text
id
source_id
run_id
raw_markdown
processed_markdown
raw_html
language
word_count
content_hash
retrieved_at
```

### document_chunks

```text
id
document_id
chunk_index
content
token_count
heading
content_hash
```

### dataset_records

```text
id
dataset_id
identity_key
data_json
completeness_score
quality_score
status
created_at
updated_at
```

### field_evidence

```text
id
record_id
field_name
source_id
document_id
chunk_id
evidence_text
confidence
```

---

## Yapılması Gerekenler

* [ ] PostgreSQL bağlantı ayarları ekle.
* [ ] SQLAlchemy engine/session altyapısını oluştur.
* [ ] İlk database modellerini oluştur.
* [ ] Alembic migration altyapısını ekle.
* [ ] Repository abstraction oluştur.
* [ ] Pipeline kodunun doğrudan SQL çalıştırmasını engelle.
* [ ] Existing Pydantic modellerini database modelleriyle karıştırma.
* [ ] Storage mapper katmanı kullan.
* [ ] Transaction testleri yaz.
* [ ] Duplicate source insert için idempotency sağla.

---

## Beklenen Çıktı

Bir mock pipeline çalıştırıldığında:

```text
1 research_run
N sources
N documents
N chunks
N dataset_records
N evidence
```

veritabanında görülebilmelidir.

Aynı run tekrar işlendiğinde gereksiz duplicate kayıt oluşmamalıdır.

---

## Testler

Yeni testler:

```text
tests/storage/
tests/integration/test_database_persistence.py
```

Kontrol edilmesi gerekenler:

```text
source upsert
document persistence
record persistence
evidence foreign keys
transaction rollback
duplicate prevention
```

---

## Acceptance Gate

Aşağıdakilerin tamamı gerçekleşmelidir:

* pipeline eski JSON çıktısını üretmeye devam ediyor,
* aynı zamanda seçilen run veritabanına yazılabiliyor,
* evidence kaybolmuyor,
* duplicate URL gereksiz yeni source oluşturmuyor,
* migration sıfırdan temiz PostgreSQL üzerinde çalışıyor,
* test suite geçiyor.

---

## Faz Sonu Zorunlu Proje Hafızası Güncellemesi

AI:

```text
docs/PROJECT_MANAGEMENT_KNOWLEDGE.md
```

dosyasına gitmeli ve şu alanları doldurmalıdır:

```text
Current Status
Implementation History
Architecture Decisions
Database State
AI Contribution Assessment
Known Problems
Next Phase Readiness
```

Özellikle şunu açıklamalıdır:

> Veritabanı eklenmesi projeye ne kazandırdı ve mevcut pipeline'ın hangi sınırlamasını ortadan kaldırdı?

---

# PHASE 29 — High-Volume Knowledge Ingestion

## Amaç

Pipeline'ın yalnızca küçük miktarda özet bilgi üretmesini engelleyip kaynaklardaki mümkün olduğunca fazla yapılandırılabilir bilgiyi kaybetmeden işleyebilmesini sağlamak.

Bu fazın ana ilkesi:

> One source != one record.

ve:

> One chunk != one record.

olacaktır.

Mevcut multi-record extraction korunur ve daha yüksek veri hacmini destekleyecek hale getirilir.

---

## Mevcut Yapıdan Kullanılacaklar

Yeniden yazılmayacak:

```text
Firecrawl discovery
Crawl4AI acquisition
Document processing
Chunking
ExtractionRouter
StructuredGenerationProvider
Field evidence
Evidence validation
Record resolution
Deduplication
```

Bunların üzerine persistence ve yüksek hacim desteği eklenir.

---

## Kod Alanları

Öncelikle incelenecek:

```text
src/agents/nodes/chunking_node.py
src/agents/nodes/extraction_router_node.py
src/agents/nodes/structured_extraction_node.py
src/agents/nodes/record_merge_node.py
src/state/state.py
src/schemas/
```

Yeni gerekirse:

```text
src/knowledge/
    ingestion.py
    record_mapper.py
```

---

## Yeni Extraction Prensibi

Modelin görevi:

```text
"Bu chunk'ın özetini oluştur."
```

olmamalıdır.

Görevi:

```text
"Onaylanmış şemaya uyan tüm bağımsız kayıtları çıkar."
```

olmalıdır.

Örneğin:

```json
{
  "records": [
    {...},
    {...},
    {...}
  ]
}
```

şeklinde sıfır, bir veya çok sayıda kayıt dönebilmelidir.

---

## Raw → Silver → Knowledge Ayrımı

Sistem üç katmanı açık biçimde ayırmalıdır.

### Bronze / Raw

```text
Web'den geldiği haliyle kaynak
```

### Silver / Processed

```text
Temizlenmiş ancak anlamı değiştirilmemiş içerik
```

### Knowledge

```text
Doğrulanmış structured kayıtlar
```

Hiçbir semantic model Bronze veya Silver içeriğin yerine özet yazmamalıdır.

Orijinal içerik korunmalıdır.

---

## Yapılması Gerekenler

* [ ] Her başarılı source'un DB'de Bronze kaydı bulunduğunu doğrula.
* [ ] Her processed document'i Silver katmanda sakla.
* [ ] Chunk'ları kalıcı hale getir.
* [ ] Extraction sonuçlarını `records[]` olarak işle.
* [ ] Bir chunk'taki çoklu kayıtların kaybolmadığını test et.
* [ ] Extraction sırasında pagination/truncation oluşmasını engelle.
* [ ] Büyük source benchmark oluştur.
* [ ] `records_per_source` metriği ekle.
* [ ] `records_per_chunk` metriğini koru.
* [ ] `knowledge_yield` metriği ekle.

---

## Knowledge Yield

Yeni metriğin amacı:

> Kaynaktan ne kadar kullanılabilir yapılandırılmış bilgi çıkarıldı?

Örnek:

```text
source_word_count
records_extracted
fields_populated
supported_fields
accepted_records
```

kullanılarak ölçülebilir.

Tek bir kesin formül ilk fazda zorunlu değildir.

Ancak metrikler manifest içerisinde gözlenebilir olmalıdır.

---

## Beklenen Çıktı

Örneğin bir sayfada 50 bağımsız kayıt bulunuyorsa pipeline yalnızca birkaç örnek değil, mümkün olduğunca bütün kayıtları çıkarabilmelidir.

Final database:

```text
sources
documents
chunks
records
evidence
```

arasında traceable bağlantıya sahip olmalıdır.

---

## Acceptance Gate

Gold fixture üzerinde bilinen 25 kayıt bulunan bir kaynak için:

```text
çıkarılan kayıt sayısı
accepted kayıt sayısı
evidence destek oranı
```

ölçülebilir olmalıdır.

Sistem yüksek bilgi hacmi nedeniyle eski validasyon kurallarını gevşetmemelidir.

---

## Faz Sonu Zorunlu Proje Hafızası Güncellemesi

`PROJECT_MANAGEMENT_KNOWLEDGE.md` içerisinde:

```text
Implementation History
Data Flow State
Quality Metrics
AI Contribution Assessment
Known Problems
Next Phase Readiness
```

güncellenmelidir.

AI özellikle şu soruyu cevaplamalıdır:

> Bu faz sonucunda bilgi hacmi neden arttı? Artış gerçek evidence-backed bilgi mi, yoksa yalnızca daha fazla model çıktısı mı?

---

# PHASE 30 — Knowledge Model, Entity Resolution and Database Upsert

## Amaç

Dataset kayıtlarını yalnız bağımsız JSON satırları olarak değil, gerektiğinde birbirleriyle ilişkilendirilebilen kalıcı knowledge nesneleri olarak saklamak.

---

## Yeni Knowledge Katmanı

Yeni modeller:

```text
entities
facts
relations
evidence
```

---

## Database Tabloları

### entities

```text
id
entity_type
canonical_name
normalized_name
attributes_json
created_at
updated_at
```

### facts

```text
id
entity_id
predicate
value_json
value_hash
confidence
status
```

### relations

```text
id
source_entity_id
relation_type
target_entity_id
attributes_json
confidence
```

### fact_evidence

```text
id
fact_id
source_id
document_id
chunk_id
evidence_text
```

---

## Önemli Ayrım

`dataset_records` silinmeyecektir.

İki ayrı kavram olacaktır:

```text
Dataset Record
```

Kullanıcının istediği schema'ya göre oluşturulmuş çıktı.

ve:

```text
Knowledge Entity / Fact / Relation
```

Platformun kalıcı bilgi katmanı.

Yani:

```text
Knowledge Database
        |
        +--> Dataset A
        +--> Dataset B
        +--> RAG
        +--> GraphRAG
```

oluşturulabilir.

---

## Kod Alanları

Yeni:

```text
src/knowledge/
├── models.py
├── entity_resolution.py
├── fact_extraction.py
├── relation_resolution.py
├── knowledge_writer.py
└── completeness.py
```

Storage:

```text
src/storage/models/
src/storage/repositories/
```

Existing:

```text
src/agents/nodes/record_merge_node.py
src/agents/nodes/
src/schemas/
src/state/state.py
```

---

## Entity Resolution

Örneğin:

```text
"MIT"
"Massachusetts Institute of Technology"
"Massachusetts Inst. of Technology"
```

doğrudan üç entity oluşturulmamalıdır.

İlk aşamada:

```text
normalized exact match
stable identifiers
domain-specific identifiers
canonical URL
```

kullanılmalıdır.

LLM entity matching ilk çözüm olmamalıdır.

Belirsiz eşleşmeler daha sonra semantic resolver'a gönderilebilir.

---

## Upsert Mantığı

Yeni bilgi geldiğinde:

```text
INSERT EVERY TIME
```

yapılmamalıdır.

Akış:

```text
Identity Resolution
      |
      v
Entity exists?
   /      \
 no        yes
 |          |
INSERT     MERGE
             |
             v
        add evidence
```

olmalıdır.

---

## Çelişkili Bilgi

Eski bilgi hemen overwrite edilmemelidir.

Örneğin iki kaynak:

```text
birth_date = X
birth_date = Y
```

diyorsa:

```text
conflict
```

olarak saklanmalıdır.

Kaynak provenance korunmalıdır.

---

## Yapılması Gerekenler

* [ ] Entity modellerini oluştur.
* [ ] Fact modelini oluştur.
* [ ] Relation modelini oluştur.
* [ ] Evidence bağlarını oluştur.
* [ ] Deterministic entity resolution ekle.
* [ ] Dataset record → knowledge mapper oluştur.
* [ ] Conflict handling oluştur.
* [ ] Upsert işlemlerini idempotent yap.
* [ ] Knowledge export testleri yaz.

---

## Acceptance Gate

Aynı entity üç farklı kaynaktan geldiğinde:

```text
3 entity
```

yerine mümkün olduğunda:

```text
1 canonical entity
+
3 provenance/evidence
```

oluşmalıdır.

Çelişkili bilgi sessizce silinmemelidir.

---

## Faz Sonu Proje Hafızası

AI `PROJECT_MANAGEMENT_KNOWLEDGE.md` içerisinde özellikle şunları doldurmalıdır:

```text
Knowledge Model State
Architecture Decisions
Implementation History
AI Contribution Assessment
Technical Debt
Next Phase Readiness
```

Şu soruya açık cevap vermelidir:

> Bu fazdan sonra sistem basit dataset generator'dan hangi noktada knowledge platform'a dönüşmeye başladı?

---

# PHASE 31 — Coverage Ledger and Enrichment Research Loop

## Amaç

Sistemin tek araştırma turundan sonra durmasını engellemek.

Artık sistem her kayıt için:

```text
Ne biliyorum?
Ne eksik?
Hangi bilgi zayıf?
Hangi bilgi çelişkili?
```

sorularını cevaplayabilmelidir.

---

## Yeni Yapılar

```text
CoverageLedger
ResearchTask
EnrichmentQueue
GapAnalyzer
```

---

## Örnek Coverage

```json
{
  "entity_id": "123",
  "fields": {
    "name": {
      "status": "supported",
      "evidence_count": 3
    },
    "education": {
      "status": "missing",
      "evidence_count": 0
    },
    "birth_date": {
      "status": "conflicting",
      "evidence_count": 2
    }
  }
}
```

---

## research_tasks Tablosu

```text
id
dataset_id
entity_id
field_name
task_type
priority
status
attempt_count
query_context_json
created_at
last_attempt_at
completed_at
```

Task tipleri:

```text
discover_entity
fill_missing_field
resolve_conflict
find_additional_evidence
expand_relation
```

---

## Yeni Node'lar

Önerilen:

```text
src/agents/nodes/
    coverage_analysis_node.py
    research_task_generation_node.py
    enrichment_planner_node.py
```

Gerekirse:

```text
src/knowledge/
    coverage.py
    task_queue.py
```

---

## Graph Değişikliği

Mevcut canonical graph:

```text
src/agents/graphs/phase2_pipeline.py
```

korunmalıdır.

Ancak final aşamadan sonra yeni conditional branch eklenebilir:

```text
Validation
    |
    v
Knowledge Write
    |
    v
Coverage Analysis
    |
    v
Enough?
 /      \
YES      NO
 |        |
Finish    Research Tasks
            |
            v
       Research Planner
            |
            v
        Discovery
```

---

## Sonsuz Döngü Engeli

Araştırma hiçbir zaman kontrolsüz sonsuz olmamalıdır.

Request/config içerisine:

```yaml
research_loop:
  enabled: true
  max_rounds: 4
  max_total_sources: 150
  max_tasks_per_round: 25
  max_no_gain_rounds: 2
```

gibi budget değerleri eklenebilir.

Sayılar başlangıç varsayımlarıdır.

Benchmark sonucunda değiştirilmelidir.

---

## Stop Conditions

Araştırma yalnızca:

```text
pipeline çalıştı
```

diye bitmemelidir.

Aşağıdakiler değerlendirilmelidir:

```text
required field coverage
accepted evidence
new records per round
new supported fields per round
new entities per round
information gain
remaining high-priority tasks
research budget
```

---

## Yapılması Gerekenler

* [ ] Coverage modeli oluştur.
* [ ] Completeness hesaplama oluştur.
* [ ] Missing/weak/conflicting field ayrımı yap.
* [ ] ResearchTask persistence oluştur.
* [ ] Priority sistemi oluştur.
* [ ] Gap-based query üret.
* [ ] Yeni discovery round'u graph'a bağla.
* [ ] Max round budget uygula.
* [ ] No-information-gain stopping ekle.
* [ ] Resume durumunda task queue korunmalı.

---

## Beklenen Davranış

Örnek:

```text
Entity:
Ali Yılmaz
```

DB:

```text
name            SUPPORTED
university      SUPPORTED
research_area   MISSING
email           MISSING
```

Pipeline otomatik olarak:

```text
fill research_area
fill email
```

task'ları oluşturmalıdır.

Yeni araştırma tamamlandığında mevcut entity güncellenmelidir.

Yeni duplicate entity oluşturulmamalıdır.

---

## Acceptance Gate

Test fixture içinde bilinçli olarak eksik bırakılan alan için:

1. Coverage `missing` göstermeli.
2. ResearchTask oluşmalı.
3. İkinci fixture kaynağı keşfedilmeli.
4. Alan evidence ile doldurulmalı.
5. Task `completed` olmalı.
6. Entity completeness artmalı.

---

## Faz Sonu Proje Hafızası

`PROJECT_MANAGEMENT_KNOWLEDGE.md` içinde:

```text
Research Loop State
Coverage State
Architecture Decisions
Implementation History
Observed Improvements
AI Contribution Assessment
Known Failure Modes
```

güncellenmelidir.

Özellikle:

> Sistem artık neden tek-run dataset generator değildir?

sorusunun cevabı yazılmalıdır.

---

# PHASE 32 — Local-First Intelligence and Final Acceptance

## Amaç

Yapay zekâyı mümkün olduğunca yalnızca gerçekten zekâ gerektiren alanlarda kullanmak ve local modeli sistemin normal semantic motoru haline getirmek.

Cloud model yalnız gerektiğinde escalation/fallback olmalıdır.

---

## Hedef Prensip

```text
Parser işi yapabiliyorsa parser kullan.

SQL yapabiliyorsa SQL kullan.

Regex yapabiliyorsa regex kullan.

Deterministic resolver yapabiliyorsa onu kullan.

Local model çözebiliyorsa local model kullan.

Yalnız kalite gate geçilmezse cloud modele çık.
```

---

## Local Model Rolleri

Local model şu görevlerde kullanılabilir:

```text
research planning
gap query generation
ambiguous source evaluation
semantic extraction
entity resolution only when deterministic resolution fails
conflict interpretation
```

Local model şu işleri yapmamalıdır:

```text
HTTP request
web crawling
database writing
transaction management
deduplication
schema validation
basic parsing
simple filtering
```

---

## Kod Alanları

Mevcut:

```text
src/tools/structured_generation/
src/agents/nodes/structured_extraction_node.py
src/evaluation/
scripts/
.env.example
```

Yeni gerekirse:

```text
src/tools/structured_generation/
    routing_provider.py
    ollama_generator.py
```

Ayrıca doğrudan Groq kullanan node'lar provider abstraction'a taşınmalıdır.

---

## Routing

```text
Deterministic
     |
     | unresolved
     v
Local Model
     |
     v
Schema valid?
Evidence valid?
Quality sufficient?
     |
  +--+--+
 YES    NO
 |       |
Accept  Cloud Provider
```

---

## Benchmark

Aynı gold dataset üzerinde:

```text
Groq
Local
Local-first + Groq fallback
```

karşılaştırılmalıdır.

Metrikler:

```text
record precision
record recall
field precision
field recall
schema validity
evidence support
unsupported field rate
latency
P95 latency
input tokens
output tokens
cloud calls
estimated cloud cost
accepted records
cost per accepted record
fallback rate
```

---

## Local-First Kabul Kriteri

Local model yalnız JSON ürettiği için başarılı kabul edilmez.

Sonuç:

```text
Pydantic valid
+
evidence valid
+
quality gate valid
```

olmalıdır.

---

## Final End-to-End Test

Final test şu akışı kanıtlamalıdır:

```text
User Request
    ↓
Research
    ↓
Web Discovery
    ↓
Crawl
    ↓
Raw Storage
    ↓
Document Processing
    ↓
Multi-record Extraction
    ↓
Evidence
    ↓
Knowledge DB
    ↓
Coverage Analysis
    ↓
Missing Data
    ↓
Enrichment Research
    ↓
Database Update
    ↓
Local-first AI
    ↓
Validated Dataset Export
```

---

# 5. Final Definition of Done

Yeni iterasyon yalnız aşağıdakilerin tamamı gerçekleştiğinde tamamlanmıştır.

## Persistence

* [ ] Kaynaklar DB'de tutuluyor.
* [ ] Raw document korunuyor.
* [ ] Processed document korunuyor.
* [ ] Chunk'lar tutuluyor.
* [ ] Records tutuluyor.
* [ ] Evidence tutuluyor.

## Knowledge

* [ ] Entity sistemi var.
* [ ] Fact sistemi var.
* [ ] Relation sistemi var.
* [ ] Entity resolution var.
* [ ] Conflict saklanıyor.
* [ ] Provenance kaybolmuyor.

## Research

* [ ] Eksik alan tespit ediliyor.
* [ ] ResearchTask oluşturuluyor.
* [ ] Enrichment round çalışıyor.
* [ ] Araştırma budget ile sınırlı.
* [ ] Information gain gözlenebilir.

## AI

* [ ] Deterministic-first korunuyor.
* [ ] Local provider gerçek backend ile çalışıyor.
* [ ] Local/cloud benchmark var.
* [ ] Cloud fallback kontrollü.
* [ ] AI database işlemlerini doğrudan yönetmiyor.

## Output

* [ ] Structured dataset export çalışıyor.
* [ ] JSON/JSONL üretilebiliyor.
* [ ] DataFrame oluşturulabiliyor.
* [ ] RAG output korunuyor.
* [ ] GraphRAG output korunuyor.

## Management

* [ ] `PROJECT_MANAGEMENT_KNOWLEDGE.md` güncel.
* [ ] Güncel architecture çizimi var.
* [ ] Her fazın katkısı açıklanmış.
* [ ] Bilinen sorunlar kayıtlı.
* [ ] Teknik borçlar kayıtlı.
* [ ] Test sonuçları kayıtlı.

---

# 6. AI İçin Zorunlu Faz Sonu Protokolü

Her faz tamamlandığında AI aşağıdaki işlemleri sırayla yapmalıdır:

```text
1. Faz kapsamını tekrar oku.
2. Değiştirilen dosyaları listele.
3. Eklenen dosyaları listele.
4. Yapılan mimari kararları yaz.
5. Çalıştırılan testleri kaydet.
6. Ölçülen metrikleri kaydet.
7. Yapılamayan işleri açıkça belirt.
8. Projeye katkısını değerlendir.
9. Oluşan teknik borcu belirt.
10. PROJECT_MANAGEMENT_KNOWLEDGE.md dosyasını güncelle.
11. Acceptance Gate'i kontrol et.
12. Ancak bundan sonra fazı COMPLETED yap.
```

AI yalnız:

```text
"Phase completed."
```

yazamaz.

Neden tamamlandığını kanıtlayan test ve çıktı bulunmalıdır.

---

# 7. Faz Özeti

| Phase | Amaç                     | Ana Sonuç                                                                  |
| ----- | ------------------------ | -------------------------------------------------------------------------- |
| 28    | Persistence Foundation   | Pipeline çıktıları PostgreSQL'de kalıcı hale gelir                         |
| 29    | High-Volume Ingestion    | Kaynaklardan daha yüksek hacimde evidence-backed kayıt çıkarılır           |
| 30    | Knowledge Model          | Entity/fact/relation ve upsert tabanlı bilgi katmanı oluşur                |
| 31    | Enrichment Loop          | Eksikler tekrar araştırılır ve DB zamanla zenginleşir                      |
| 32    | Local-First + Acceptance | AI yalnız gerekli yerde kullanılır, local-first production mimarisi oluşur |

Bu beş fazın dışında yeni bir faz oluşturulmadan önce gerçekten ayrı bir mimari sınır gerekip gerekmediği değerlendirilmelidir.
