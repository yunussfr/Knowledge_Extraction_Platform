Sen kıdemli bir Python, Data Engineering, Web Scraping, LLM, Dataset Generation ve RAG altyapı geliştiricisisin.

Önünde hali hazırda çalışan bir proje bulunmaktadır.

Bu projeyi sıfırdan yeniden yazmanı istemiyorum.

İlk olarak repository'nin tamamını analiz et, mevcut mimariyi anla ve aşağıdaki sistemi mevcut yapıyı mümkün olduğunca koruyarak entegre et.

Mevcut çalışan yapıların yerine gereksiz yeni mimariler kurma.


---

# PROJENİN TEMEL VİZYONU

Bu proje bir chatbot veya doğrudan RAG sistemi değildir.

Bu proje başka:

- RAG
- GraphRAG
- LLM
- Machine Learning
- Fine-tuning
- Knowledge Base
- AI Agent

projelerinde kullanılabilecek kaliteli ve yapılandırılmış datasetleri gerçek web kaynaklarından üretmek için kullanılmaktadır.

Projenin temel fikri şudur:

```text
Kullanıcı bütün veri modelini,
kaynak listesini ve araştırma sorgularını
kendisi tek tek hazırlamak zorunda kalmamalıdır.

Kullanıcı veri toplamak istediği konuyu tanımlar.

Sistem araştırmayı planlar.

Gerçek kaynakları bulur.

Kaynakları değerlendirir.

Dataset için uygun veri şemasını tasarlar.

Kullanıcı bu şemayı inceler ve onaylar.

Ardından sistem yalnızca onaylanmış şemaya göre
gerçek kaynaklardan veri çıkarır.

Sonuçta doğrulanmış,
kaynağı belli,
confidence bilgisi bulunan
JSON / JSONL dataset üretir.
```

Bu proje ileride farklı RAG ve yapay zekâ projelerine veri sağlayan bağımsız bir:

```text
DATASET GENERATION
+
WEB RESEARCH
+
STRUCTURED EXTRACTION
```

altyapısı olacaktır.

---

# KULLANICININ BAŞLANGIÇTA YAPACAĞI ŞEY

Kullanıcı başlangıçta yalnızca hangi konuda veri toplamak istediğini ve isterse dataset'in amacını belirtmelidir.Hatta referans adreslerde verebilmektedir.

Örneğin:

```text
Türk kahve kültürü
```

veya:

```text
Malatya yöresel yemekleri
```

veya:

```text
Osmanlı dönemindeki mimari yapılar
```

Kullanıcı başlangıçta:

- bütün URL'leri,
- bütün search query'leri,
- bütün JSON alanlarını

elle oluşturmak zorunda olmamalıdır.

Ancak sistem aynı zamanda kullanıcıya manual override imkânı vermelidir.

---

# MEVCUT PROJEYİ ÖNCE ANALİZ ET

Kod yazmadan önce repository'nin tamamını incele.

Özellikle şunları tespit et:

- config yapısı
- mock veri sistemi
- source/provider sistemi
- URL/source modelleri
- JSON schema modelleri
- metadata modelleri
- extraction pipeline
- parser'lar
- validation sistemi
- dataset writer
- JSON / JSONL output sistemi
- CLI
- API varsa API
- application entry point
- environment configuration
- logging sistemi
- test sistemi
- dependency management
- mevcut prompt yönetimi
- mevcut LLM entegrasyonları
- mevcut pipeline state/status sistemi varsa onun yapısı

Repository'de zaten aynı sorumluluğu yerine getiren abstraction/interface/factory varsa yeni paralel sistem oluşturma.

---

# ANA HEDEF PIPELINE

Sistemin ana akışı şu olmalıdır:

```text
DATASET TOPIC
      ↓
GROQ — RESEARCH PLANNER
      ↓
RESEARCH PLAN
      ↓
FIRECRAWL SEARCH
      ↓
CANDIDATE SOURCES
      ↓
GROQ — SOURCE EVALUATOR
      ↓
SELECTED SOURCES
      ↓
GROQ — DATASET SCHEMA DESIGNER
      ↓
DRAFT DATASET SCHEMA
      ↓
WAITING FOR USER APPROVAL
      ↓
USER
REVIEW / ADD / REMOVE / EDIT
      ↓
APPROVED DATASET SCHEMA
      ↓
FIRECRAWL SCRAPE
      ↓
CLEAN SOURCE CONTENT
      ↓
GROQ — STRUCTURED EXTRACTOR
      ↓
STRUCTURED DATA
+
CONFIDENCE
      ↓
SCHEMA VALIDATION
      ↓
CONFIDENCE VALIDATION
      ↓
DEDUPLICATION
      ↓
METADATA BUILDING
      ↓
JSON / JSONL DATASET
```

Bu akış projenin temel mimarisidir.

Bu aşamaları birbirine karıştırma.

---

# HUMAN-IN-THE-LOOP PRENSİBİ

Dataset schema tamamen otomatik şekilde oluşturulup doğrudan extraction işlemine gönderilmemelidir.

Groq'un oluşturduğu schema:

```text
DRAFT DATASET SCHEMA
```

olarak değerlendirilmelidir.

Kullanıcı bu şemayı inceleyebilmelidir.

Kullanıcı:

- alan ekleyebilmeli,
- alan silebilmeli,
- alan adını değiştirebilmeli,
- type değiştirebilmeli,
- required durumunu değiştirebilmeli,
- nullable durumunu değiştirebilmeli,
- description değiştirebilmeli,
- extraction_instruction değiştirebilmelidir.

Kullanıcı şemayı onayladıktan sonra:

```text
APPROVED DATASET SCHEMA
```

oluşmalıdır.

Structured extraction yalnızca:

```text
APPROVED DATASET SCHEMA
```

ile çalışmalıdır.

---

# ÇOK ÖNEMLİ — ONAY BEKLEME DURUMU

DatasetSchemaDesigner çalıştıktan sonra pipeline otomatik olarak devam etmemelidir.

Pipeline:

```text
DatasetSchemaDesigner
        ↓
Draft Schema
        ↓
WAITING_FOR_SCHEMA_APPROVAL
```

durumuna geçmelidir.

Bu durumda:

```text
Firecrawl Scrape
Groq Structured Extraction
Dataset Generation
```

başlamamalıdır.

Kullanıcı schema'yı onaylayana kadar pipeline'ın durumu korunmalıdır.

Kullanıcı onayladığında:

```text
SCHEMA_APPROVED
```

durumuna geçilmeli ve pipeline kaldığı noktadan devam edebilmelidir.

Bu mekanizmayı uygulamanın mevcut mimarisine uygun şekilde tasarla.

---

# PIPELINE STATE / STATUS MODELİ

İleride bu proje için basit bir arayüz oluşturacağım.

Bu arayüzde dataset generation işleminin hangi aşamada olduğunu görmek istiyorum.

Şu anda büyük veya karmaşık bir frontend geliştirmeni istemiyorum.

Ancak backend/pipeline mimarisi gelecekte bu arayüzü destekleyebilecek durumda olmalıdır.

Pipeline'ın anlamlı durumları bulunmalıdır.

Örneğin:

```text
CREATED

PLANNING_RESEARCH

RESEARCH_PLAN_READY

SEARCHING_SOURCES

SOURCES_DISCOVERED

EVALUATING_SOURCES

SOURCES_SELECTED

DESIGNING_SCHEMA

WAITING_FOR_SCHEMA_APPROVAL

SCHEMA_APPROVED

SCRAPING_SOURCES

EXTRACTING_DATA

VALIDATING_RECORDS

DEDUPLICATING

WRITING_DATASET

COMPLETED

FAILED
```

Bunlar yalnızca örnek isimlerdir.

Mevcut proje naming convention'ına uygun isimler kullan.

Ancak kullanıcı açısından pipeline'ın hangi aşamada olduğu anlaşılabilir olmalıdır.

---

# GELECEKTEKİ ARAYÜZ İÇİN HAZIRLIK

Şu anda gelişmiş bir UI oluşturma.

Bu promptun temel amacı backend ve dataset pipeline altyapısını oluşturmaktır.

Ancak mimari gelecekte basit bir arayüzün şu bilgileri gösterebilmesini desteklemelidir:

```text
Dataset Topic

Research Plan

Generated Search Queries

Candidate Sources

Selected Sources

Draft Dataset Schema

Schema Approval Status

Approved Dataset Schema

Scraping Progress

Extraction Progress

Validation Results

Rejected / Review Records

Dataset Output

Errors
```

Bu nedenle pipeline aşamaları mümkün olduğunca observable olmalıdır.

Gelecekte UI'nin doğrudan internal Python objelerine bağımlı olması gerekmesin.

Mevcut mimariye uygunsa pipeline state/result modelleri oluştur.

Ancak sırf ileride UI yapılacak diye aşırı karmaşık event-driven sistem kurma.

Basit, modüler ve genişletilebilir çözüm tercih et.

---

# FIRECRAWL'IN SORUMLULUĞU

Firecrawl gerçek web erişim katmanıdır.

Firecrawl:

```text
SEARCH
SCRAPE
gerekirse CRAWL
```

işlemlerinden sorumludur.

Firecrawl:

- gerçek URL bulur,
- gerçek web içeriğini getirir,
- mümkünse temiz Markdown/text döndürür,
- source metadata'yı korur.

Firecrawl:

- dataset schema tasarlamaz,
- dataset alanlarını belirlemez,
- confidence üretmez,
- structured dataset oluşturmaz,
- kaynakların nihai kalite kararını vermez.

---

# GROQ CLOUD'UN SORUMLULUĞU

GroqCloud dört ayrı görev için kullanılmalıdır:

```text
1. ResearchPlanner
2. SourceEvaluator
3. DatasetSchemaDesigner
4. StructuredExtractor
```

Tek büyük Groq promptu kullanma.

Her görevin kendi:

```text
System Prompt
User Prompt
Structured Output Schema
```

yapısı bulunmalıdır.

Mantıksal yapı:

```text
GroqClient
   │
   ├── ResearchPlanner
   │      ├── System Prompt
   │      ├── User Prompt
   │      └── ResearchPlan Output Schema
   │
   ├── SourceEvaluator
   │      ├── System Prompt
   │      ├── User Prompt
   │      └── SourceEvaluation Output Schema
   │
   ├── DatasetSchemaDesigner
   │      ├── System Prompt
   │      ├── User Prompt
   │      └── DatasetSchemaDesign Output Schema
   │
   └── StructuredExtractor
          ├── System Prompt
          ├── User Prompt
          └── ExtractionResult Output Schema
```

Bu output schema'lar Groq'un kendi görev çıktılarının hangi formatta olacağını belirler.

Dataset'in gerçek dinamik alanları ise DatasetSchemaDesigner tarafından oluşturulur.

---

# 1 — RESEARCH PLANNER

ResearchPlanner'ın görevi dataset konusu için araştırma stratejisi oluşturmaktır.

Örneğin kullanıcı:

```text
Türk kahve kültürü
```

dediğinde sistem şunları belirleyebilmelidir:

- hangi alt konular araştırılmalı,
- hangi search query'ler kullanılmalı,
- hangi kaynak türleri öncelikli,
- hangi kaynak türlerinden kaçınılmalı,
- araştırmanın kapsamı nasıl olmalı.

Örnek structured output:

```json
{
  "research_topic": "Türk kahve kültürü",

  "subtopics": [
    "tarih",
    "hazırlama yöntemleri",
    "kullanılan araçlar",
    "gelenekler",
    "bölgesel farklılıklar"
  ],

  "search_queries": [
    "Türk kahvesi tarihi",
    "Türk kahvesi hazırlanışı",
    "Türk kahvesi kültürü gelenekleri",
    "Osmanlı kahvehane kültürü",
    "Türk kahvesi UNESCO"
  ],

  "preferred_source_types": [
    "resmi kurum",
    "üniversite",
    "akademik kaynak",
    "müze",
    "kültür kurumu"
  ],

  "excluded_source_types": [
    "forum",
    "spam",
    "reklam ağırlıklı içerik"
  ]
}
```

---

# RESEARCH PLANNER SYSTEM PROMPT

Merkezi olarak tanımlanmış ayrı System Prompt kullan.

Temel davranışı:

```text
You are a Dataset Research Planning Agent.

Your only responsibility is to design a high-quality research strategy for the supplied dataset topic.

Determine:

- what should be researched,
- which subtopics should be covered,
- which search queries should be executed,
- which source categories should be prioritized,
- which source categories should be avoided.

Do not perform web searches yourself.

Do not fabricate URLs.

Do not claim that a source exists unless it was supplied to you.

Optimize the research strategy for high-quality dataset generation.

Prefer authoritative, primary, institutional, academic, governmental or otherwise trustworthy sources when appropriate.

Avoid unnecessary duplicate queries.

Return only the requested structured ResearchPlan.
```

User Prompt dinamik olmalıdır:

```text
Dataset topic:
{dataset_topic}

Dataset purpose:
{dataset_purpose}

Maximum search queries:
{max_queries}

User research constraints:
{research_constraints}
```

---

# 2 — FIRECRAWL SEARCH

ResearchPlanner tarafından oluşturulan search query'leri Firecrawl Search üzerinden çalıştır.

Akış:

```text
ResearchPlan
     ↓
Search Queries
     ↓
Firecrawl Search
     ↓
Candidate Sources
```

Candidate source mümkün olduğunca şu bilgileri taşımalıdır:

```json
{
  "url": "https://...",
  "title": "...",
  "description": "...",
  "domain": "...",
  "search_query": "..."
}
```

Firecrawl SDK'nın mevcut modelleri yeterliyse gereksiz wrapper oluşturma.

---

# 3 — SOURCE EVALUATOR

Firecrawl'ın bulduğu bütün URL'leri doğrudan scrape etme.

Önce SourceEvaluator kaynakları değerlendirmelidir.

Değerlendirme kriterleri:

```text
relevance
authority
information quality
topic coverage
redundancy
source type
structured extraction usefulness
```

Groq yalnızca Firecrawl tarafından bulunan candidate URL'leri değerlendirebilir.

URL üretemez.

URL değiştiremez.

URL uyduramaz.

Örnek output:

```json
{
  "selected_sources": [
    {
      "url": "https://...",
      "reason": "Konu için güçlü ve güvenilir kaynak.",
      "priority": 1
    }
  ],

  "rejected_sources": [
    {
      "url": "https://...",
      "reason": "Konu ile yeterince ilgili değil."
    }
  ]
}
```

---

# SOURCE EVALUATOR SYSTEM PROMPT

```text
You are a Dataset Source Evaluation Agent.

Your responsibility is to evaluate candidate web sources for a dataset.

You may ONLY evaluate URLs supplied in the candidate source list.

Never generate URLs.

Never modify URLs.

Never invent URLs.

Evaluate sources according to:

- relevance,
- authority,
- likely information quality,
- topic coverage,
- redundancy,
- source type,
- usefulness for structured extraction.

Prefer reliable and information-rich sources.

Reject irrelevant, low-quality, duplicate, suspicious or unsuitable sources.

Return only the required structured SourceEvaluation output.
```

---

# 4 — DATASET SCHEMA DESIGNER

Bu bileşenin adı kesinlikle:

```text
DatasetSchemaDesigner
```

olmalıdır.

`SchemaProposalGenerator` gibi bir isim kullanma.

DatasetSchemaDesigner'ın görevi kullanıcının yerine nihai kararı vermek değildir.

Görevi:

```text
Dataset konusu için mantıklı bir
DRAFT DATASET SCHEMA tasarlamak.
```

DatasetSchemaDesigner topic, dataset purpose ve ResearchPlan'i analiz ederek hangi bilgilerin dataset içerisinde tutulmasının faydalı olduğunu belirlemelidir.

Örneğin:

```text
Malatya yöresel yemekleri
```

için şunları önerebilir:

```json
{
  "dish_name": {
    "type": "string",
    "required": true
  },

  "ingredients": {
    "type": "array[string]",
    "required": false
  },

  "preparation": {
    "type": "string",
    "required": false
  },

  "cultural_significance": {
    "type": "string",
    "required": false
  },

  "region": {
    "type": "string",
    "required": false
  }
}
```

Ancak bu şema:

```text
DRAFT
```

durumunda olmalıdır.

Otomatik olarak extraction'a gönderilmemelidir.

---

# DATASET SCHEMA DESIGNER FIELD YAPISI

Her field mümkünse şu bilgileri içermelidir:

```text
field_name
type
description
required
nullable
is_array
extraction_instruction
```

Örneğin:

```json
{
  "field_name": "ingredients",

  "type": "array[string]",

  "description":
    "Yemeğin hazırlanmasında kullanılan malzemeler.",

  "required": false,

  "nullable": true,

  "is_array": true,

  "extraction_instruction":
    "Sadece kaynakta açıkça belirtilen malzemeleri ekle."
}
```

Bu bilgiler ileride kullanıcının schema'yı incelemesini kolaylaştıracaktır.

---

# DATASET SCHEMA DESIGNER SYSTEM PROMPT

```text
You are a Dynamic Dataset Schema Design Agent.

Your responsibility is to design a draft structured dataset schema for the supplied dataset topic.

The schema must be topic-specific.

Your output is a DRAFT.

The user will review, edit and approve the schema before extraction begins.

Never assume fixed fields such as title, description, category, history or region unless they are appropriate for the supplied topic.

For every field determine:

- field name,
- data type,
- description,
- required status,
- nullable status,
- whether it is an array,
- extraction instructions.

Design fields that are genuinely useful for downstream:

- RAG,
- GraphRAG,
- knowledge bases,
- machine learning,
- LLM applications.

Avoid redundant and unnecessary fields.

Do not place provenance information inside the primary dataset schema.

Provenance belongs to metadata.

Do not treat the generated schema as approved.

Return only the required structured DatasetSchemaDesign output.
```

User Prompt:

```text
Dataset topic:
{dataset_topic}

Dataset purpose:
{dataset_purpose}

Research plan:
{research_plan}

User schema constraints:
{schema_constraints}
```

---

# DRAFT SCHEMA → USER REVIEW

DatasetSchemaDesigner sonucunu kalıcı veya yeniden yüklenebilir şekilde tut.

Pipeline:

```text
DatasetSchemaDesigner
        ↓
Draft Schema
        ↓
WAITING_FOR_SCHEMA_APPROVAL
```

durumuna geçmelidir.

Kullanıcı draft schema'yı görebilmeli ve değiştirebilmelidir.

Kullanıcının yaptığı değişiklikler kaybolmamalıdır.

---

# SCHEMA EDITING OPERATIONS

Mimariye uygunsa schema üzerinde şu işlemleri destekle:

```text
add_field

remove_field

update_field

rename_field

change_type

change_required

change_nullable

change_description

change_extraction_instruction
```

Bunların illa ayrı endpoint/function olması zorunlu değildir.

Mevcut config/model sistemi daha temiz bir çözüm sunuyorsa onu kullan.

Ancak kullanıcı schema'yı düzenleyebilmelidir.

---

# SCHEMA APPROVAL

Kullanıcı schema'yı onayladığında:

```text
Draft Dataset Schema
        ↓
User Approval
        ↓
Approved Dataset Schema
```

olmalıdır.

Approved schema mümkünse version bilgisi taşımalıdır.

Örneğin:

```text
schema_version = 1
```

veya mevcut proje standardına uygun başka bir sistem kullanılabilir.

StructuredExtractor yalnızca approved schema kullanmalıdır.

---
# SCHEMA APPROVAL VE PIPELINE RESUME MEKANİZMASI

Kullanıcı schema'yı onayladığında pipeline state değerini doğrudan değiştirmemelidir.

Örneğin kullanıcı veya UI katmanı doğrudan:

```python
pipeline.state = "SCHEMA_APPROVED"
```

gibi bir işlem YAPMAMALIDIR.

Bunun yerine schema approval işlemi pipeline'ın kendi domain/application operasyonu üzerinden gerçekleştirilmelidir.

Tercih edilen mantıksal kullanım:

```python
pipeline.approve_schema()
```

olmalıdır.

Mevcut mimariye göre method adı veya class yerleşimi küçük farklılık gösterebilir ancak davranış kesinlikle aşağıdaki gibi olmalıdır.

Pipeline başlangıçta:

```text
DatasetSchemaDesigner
        ↓
Draft Dataset Schema
        ↓
WAITING_FOR_SCHEMA_APPROVAL
```

durumuna gelir.

Bu aşamada pipeline çalışması durur ve extraction aşamalarına geçmez.

Kullanıcı draft schema üzerinde gerekli:

```text
add
remove
edit
rename
type change
required change
nullable change
description change
extraction instruction change
```

işlemlerini yaptıktan sonra schema'yı onaylamak için:

```python
pipeline.approve_schema()
```

operasyonunu çağırır.

`approve_schema()` yalnızca state değiştiren basit bir setter olmamalıdır.

Bu operasyon aşağıdaki işlemleri sırasıyla gerçekleştirmelidir:

```text
pipeline.approve_schema()
        ↓
Current State Check
        ↓
Draft Schema Check
        ↓
Draft Schema Validation
        ↓
Persist User Changes
        ↓
Create Approved Schema
        ↓
Assign Schema Version
        ↓
Persist Approved Schema
        ↓
Change Pipeline State
        ↓
SCHEMA_APPROVED
        ↓
Resume Pipeline
```

## 1. CURRENT STATE CHECK

`approve_schema()` yalnızca pipeline:

```text
WAITING_FOR_SCHEMA_APPROVAL
```

durumundayken çalışabilmelidir.

Örneğin pipeline:

```text
SCRAPING_SOURCES
COMPLETED
FAILED
```

gibi başka bir state içerisindeyken approval işlemi yapılmaya çalışılırsa kontrollü domain/application error döndür.

State'i sessizce değiştirme.

---

## 2. DRAFT SCHEMA CHECK

Approval işleminden önce mevcut bir Draft Dataset Schema bulunduğunu doğrula.

Draft schema yoksa approval gerçekleşmemelidir.

---

## 3. APPROVED SCHEMA OLUŞTURMA

Validation başarılı olduktan sonra Draft Dataset Schema doğrudan mutate edilerek kullanılmamalıdır.

Mantıksal olarak ayrı bir:

```text
Approved Dataset Schema
```

oluştur.

Örneğin:

```text
DraftDatasetSchema
        ↓
approve_schema()
        ↓
ApprovedDatasetSchema
```

Approved schema extraction pipeline'ın kullanacağı gerçek contract olmalıdır.

StructuredExtractor yalnızca ApprovedDatasetSchema kullanmalıdır.

---


## 4. STATE TRANSITION

Yalnızca yukarıdaki işlemlerin tamamı başarılı olduktan sonra:

```text
WAITING_FOR_SCHEMA_APPROVAL
        ↓
SCHEMA_APPROVED
```

state transition gerçekleşmelidir.

Onay işleminin herhangi bir aşaması başarısız olursa:

```text
SCHEMA_APPROVED
```

state'ine geçme.

---

## 5. PIPELINE RESUME

`approve_schema()` başarılı olduğunda sistem yalnızca state'i değiştirip durmamalıdır.

Pipeline kaldığı checkpoint'ten devam edebilmelidir.

Beklenen akış:

```text
WAITING_FOR_SCHEMA_APPROVAL

        ↓

pipeline.approve_schema()

        ↓

SCHEMA_APPROVED

        ↓

SCRAPING_SOURCES

        ↓

EXTRACTING_DATA

        ↓

VALIDATING_RECORDS

        ↓

DEDUPLICATING

        ↓

WRITING_DATASET

        ↓

COMPLETED
```

Mevcut mimari synchronous çalışıyorsa `approve_schema()` pipeline continuation'ı doğrudan tetikleyebilir.

Mevcut sistem async/job/worker mantığı kullanıyorsa approval işleminden sonra mevcut pipeline job'ının resume edilmesini sağlayan mimariyi kullan.

Sırf bunun için gereksiz yeni queue veya background system oluşturma.

Mevcut mimariye en doğal şekilde entegre et.

---

## 6. IDEMPOTENCY / DOUBLE APPROVAL

Aynı schema yanlışlıkla iki kez onaylanırsa iki ayrı pipeline execution başlamamalıdır.

Örneğin:

```python
pipeline.approve_schema()
pipeline.approve_schema()
```

işlemleri duplicate scraping/extraction başlatmamalıdır.

İkinci approval:

* kontrollü şekilde reddedilebilir,
* veya mevcut approved state güvenli şekilde döndürülebilir.

Ancak ikinci dataset generation süreci başlatılmamalıdır.

---


# ÖNEMLİ TASARIM KURALI

State:

```text
SCHEMA_APPROVED
```

kullanıcının doğrudan değiştirdiği bir değer değildir.

Bu state:

```text
pipeline.approve_schema()
```

operasyonunun başarılı sonucudur.

Yani:

```text
KÖTÜ:

User
↓
state = SCHEMA_APPROVED


DOĞRU:

User
↓
pipeline.approve_schema()
↓
approved schema creation
↓
persistence
↓
state = SCHEMA_APPROVED
↓
pipeline resume
```

Bu davranışı yalnızca dokümante etme.

Gerçek kod seviyesinde uygula ve unit testlerle doğrula.


# JSON DATA SCHEMA VE METADATA AYRIMI

Kesinlikle şu ayrımı koru:

```text
DATA SCHEMA

Kaynaktan çıkarmak istediğimiz
asıl bilgi.


METADATA

Bu bilginin nereden,
ne zaman,
hangi kaynak üzerinden
ve hangi kalite seviyesinde
oluşturulduğunu açıklayan bilgi.
```

Örnek:

```json
{
  "data": {
    "dish_name": "Analı Kızlı",
    "ingredients": [
      "bulgur",
      "kıyma"
    ]
  },

  "_metadata": {
    "source_url": "https://...",
    "source_title": "...",
    "retrieved_at": "...",
    "source_provider": "firecrawl",
    "confidence": 0.95
  }
}
```

---

# METADATA

Minimum metadata mümkünse şu bilgileri içermelidir:

```text
source_url

source_title

source_domain

retrieved_at

source_provider

search_query

dataset_topic

confidence
```
İkinci metadata sistemi oluşturma.

---

# FIRECRAWL SCRAPE

Yalnızca:

```text
APPROVED DATASET SCHEMA
```

oluştuktan sonra selected source'ları scrape etmeye başla.

Akış:

```text
Approved Schema
+
Selected Sources
        ↓
Firecrawl Scrape
        ↓
Clean Source Content
        ↓
StructuredExtractor
```

Firecrawl response içerisinde bulunuyorsa şu bilgileri koru:

- source URL
- title
- description
- canonical URL
- author
- published date
- language
- domain
- Markdown/text

Bulunmayan metadata'yı uydurma.

---

# STRUCTURED EXTRACTOR

StructuredExtractor:

```text
Approved Dataset Schema
+
Field Extraction Instructions
+
Source Content
+
Source Metadata
```

kullanarak gerçek dataset  record'larını üretmelidir.

Taslak schema kullanmamalıdır.

---

# STRUCTURED EXTRACTOR SYSTEM PROMPT

```text
You are a Strict Structured Dataset Extraction Agent.

Your responsibility is to extract structured information from the supplied source according to the APPROVED dataset schema.

Use ONLY information supported by the supplied source.

Never use outside knowledge.

Never fabricate facts.

Never fabricate people.

Never fabricate names.

Never fabricate dates.

Never fabricate URLs.

Never fabricate statistics.

Never fabricate citations.

Never infer unsupported factual claims.

Follow the approved dataset schema exactly.

Do not create additional fields.

Do not remove required schema fields.

Preserve the requested data types.

If an optional value is not supported by the source, return null when allowed.

If required information cannot be reliably extracted, report the extraction failure according to the application's structured output schema.

For every extracted record, evaluate how strongly the source supports the extracted information.
For every extracted record, you MUST generate a confidence score.

The confidence score must be a float between 0.0 and 1.0.

The confidence score represents how strongly and directly the supplied source supports the extracted record.

Use the following rubric:

0.90 - 1.00:
The extracted information is explicitly and directly supported by the source.

0.70 - 0.89:
The extracted information is strongly supported but requires minor interpretation.

0.50 - 0.69:
The extracted information is partially or indirectly supported.

0.00 - 0.49:
The available evidence is insufficient or ambiguous.

Confidence is NOT a probability returned by the Groq API.

It is an evidence-support score generated as part of the extraction result.

Return the confidence together with the extracted structured data according to the required ExtractionResult schema.

Confidence is an evidence-support score.
```
----
# CONFIDENCE GENERATION

Confidence değeri StructuredExtractor tarafından,
structured data extraction ile AYNI Groq çağrısında üretilmelidir.

Yani StructuredExtractor sonucu mantıksal olarak:

ExtractionResult
    ├── data
    └── confidence

şeklinde olmalıdır.

Örnek:

{
  "data": {
    "dish_name": "Analı Kızlı",
    "ingredients": [
      "bulgur",
      "kıyma"
    ]
  },
  "confidence": 0.94
}

Confidence:

- Validator tarafından üretilmemelidir.
- MetadataBuilder tarafından üretilmemelidir.
- Firecrawl tarafından üretilmemelidir.

Confidence yalnızca Groq StructuredExtractor tarafından,
kaynak içeriğin extracted record'u ne kadar desteklediğine
bakılarak oluşturulmalıdır.

StructuredExtractor çıktısı alındıktan sonra:

ExtractionResult.confidence
        ↓
MetadataBuilder
        ↓
_metadata.confidence

şeklinde final dataset metadata'sına aktarılmalıdır.

Daha sonra Quality Control katmanı bu değeri yalnızca kontrol etmelidir.
---

# STRUCTURED OUTPUT

Groq tarafında mümkün olduğunca Structured Output / JSON Schema yaklaşımını kullan.

Serbest response alıp regex ile JSON ayıklama gibi kırılgan yöntemlerden kaçın.

Akış:

```text
Output Schema
     ↓
Groq
     ↓
Structured JSON
     ↓
Validation
```

olmalıdır.

Strict structured output desteklenmeyen model kullanılırsa kontrollü fallback uygula.

Fallback çıktısı yine validation'dan geçmelidir.

---

# CONFIDENCE

Her extracted record metadata'sında:

```json
{
  "confidence": 0.94
}
```

bulunmalıdır.

Confidence:

```text
0.0 <= confidence <= 1.0
```

arasında float olmalıdır.

Bu değer:

```text
Groq API tarafından sağlanan native probability değildir.
```

Bu projede confidence:

```text
Kaynak içeriğin,
çıkarılan structured record'u
ne kadar açık ve güçlü şekilde
desteklediğini gösteren
evidence-support skorudur.
```

---

# CONFIDENCE RUBRIC

StructuredExtractor şu mantığı kullanmalıdır:

```text
0.90 - 1.00

Bilgi kaynakta açık ve doğrudan ifade edilmiştir.


0.70 - 0.89

Bilgi güçlü şekilde desteklenmektedir,
ancak küçük miktarda yorumlama gerekmiştir.


0.50 - 0.69

Bilgi kısmen veya dolaylı desteklenmektedir.


0.00 - 0.49

Kanıt yetersiz veya belirsizdir.

Alan mümkünse null olmalı
veya record review/reject işlemine gönderilmelidir.
```

----

# QUALITY CONTROL

Config üzerinden:

```yaml
quality:
  minimum_confidence: 0.70
  low_confidence_action: reject
```

ayarlanabilsin.

Mümkünse:

```text
accept
reject
```

davranışlarını destekle.

Akış:

```text
Structured Extraction
        ↓
Schema Validation
        ↓
Confidence Validation
        ↓
confidence >= threshold?
       /             \
     YES              NO
      ↓                ↓
   Accept         Review / Reject
```

---

# VALIDATION

Groq cevabını doğrudan dataset'e yazma.

Pipeline:

```text
Groq Response
     ↓
JSON Parse
     ↓
Approved Schema Validation
     ↓
Type Validation
     ↓
Required Field Validation
     ↓
Metadata Validation
     ↓
Confidence Validation
     ↓
Validated Record
```

olmalıdır.

---

# RAW / CLEAN / STRUCTURED DATA AYRIMI

Mümkünse açık veri aşamaları kullan:

```text
RawSourceDocument
        ↓
CleanDocument
        ↓
StructuredExtraction
        ↓
ValidatedRecord
        ↓
DatasetRecord
```

Tek dictionary'yi pipeline boyunca rastgele mutate etmekten kaçın.

---

# DEDUPLICATION

Aynı bilgi:

- farklı query'lerden,
- farklı URL'lerden,
- aynı sayfanın farklı bölümlerinden,

gelebilir.

Duplicate record'ları azalt.

Ancak provenance bilgisini kaybetme.

---

# MEVCUT REPOSITORY YAPISINA GÖRE GERÇEK ENTEGRASYON PLANI

Bu projede yeni ve paralel bir uygulama mimarisi oluşturma.

Mevcut yapı zaten:

```text
configs
    ↓
run_domain_test.py
    ↓
LangGraph
    ↓
src/agents/graphs/phase2_pipeline.py
    ↓
src/agents/nodes/*
    ↓
src/state/state.py
    ↓
src/schemas/models.py
    ↓
knowledge/datasets/*
```

akışına sahiptir.

Yeni Firecrawl + Groq + DatasetSchemaDesigner sistemi bu yapının ÜZERİNE eklenmelidir.

Yeni bir frontend, yeni bir bağımsız backend veya ikinci bir pipeline oluşturma.

---

# 1. KULLANICI GİRDİSİ NEREDEN GELECEK?

Şu anda frontend bulunmadığı için kullanıcının dataset isteği mevcut `configs/` yapısı üzerinden verilmelidir.

Öncelikle mevcut domain config dosyalarını incele.

Eğer mevcut domain config yapısına doğal şekilde eklenebiliyorsa yeni config formatı oluşturma.

Aksi halde ilgili domain altında örneğin:

```text
configs/domains/turkish_culture/request.yaml
```

benzeri tek bir dataset request dosyası oluşturulabilir.

Bu dosyanın mantıksal olarak şu bilgileri taşıması yeterlidir:

```yaml
dataset:
  name: turkish_culture_dataset

  topic: >
    Geleneksel Türk kahve kültürü hakkında
    yapılandırılmış dataset oluştur.

  purpose: >
    RAG ve knowledge-base sistemlerinde kullanılacak.


research:
  auto_generate_queries: true

  max_queries: 10

  max_sources: 20

  preferred_domains: []

  queries: []


schema:
  auto_design: true

  require_user_approval: true


quality:
  minimum_confidence: 0.70
  low_confidence_action: reject


output:
  format: json
```

Bu kullanıcının Groq'a doğrudan yazdığı prompt değildir.

Bu:

```text
USER INTENT / DATASET REQUEST
```

olmalıdır.

Groq'un ResearchPlanner, SourceEvaluator, DatasetSchemaDesigner ve StructuredExtractor user promptları bu config verilerinden uygulama içerisinde otomatik oluşturulmalıdır.

Yani kullanıcı:

```text
"Groq'a prompt nereden gireceğim?"
```

diye düşünmemelidir.

Kullanıcı yalnızca:

```text
topic
purpose
opsiyonel research override'ları
```

girmelidir.

Groq promptlarını sistem oluşturmalıdır.

---

# 2. run_domain_test.py GİRİŞ NOKTASI OLARAK KORUNMALI

Şu anda pipeline:

```text
run_domain_test.py
```

üzerinden başlatılıyorsa bu çalışma biçimini koru.

Bu dosyayı gereksiz yere yeni bir CLI uygulamasıyla değiştirme.

Ancak mevcut giriş betiğini gerçek pipeline'ı çalıştırabilecek şekilde genişlet.

Mantıksal kullanım örneği:

```powershell
python run_domain_test.py --domain turkish_culture
```

olabilir.

Mevcut kullanım biçimi farklıysa mevcut standardı koru.

`run_domain_test.py` şu işleri yapmalıdır:

```text
domain seç
↓
config yükle
↓
pipeline state oluştur
↓
phase2_pipeline çalıştır
↓
gerektiğinde schema approval aşamasını yönet
↓
pipeline sonucunu göster
```

Mock data injection yalnızca mock/test modunda kullanılmalıdır.

Gerçek modda mock content enjekte edilmemelidir.

---

# 3. İLK OLARAK STATE MODELİNİ GENİŞLET

Mevcut:

```text
src/state/state.py
```

pipeline'ın bütün node'ları arasında veri taşıdığı için yeni akışın merkezi burada olmalıdır.

Mevcut state'i bozma.

Gerekli alanları mevcut state'e ekle.

Mantıksal olarak aşağıdaki bilgilerin taşınabilmesi gerekir:

```text
dataset_topic
dataset_purpose

research_plan

candidate_sources

selected_sources

draft_dataset_schema

approved_dataset_schema

pipeline_status

scraped_documents

extraction_results

accepted_records

rejected_records

errors
```

Bütün node'ların birbirleriyle global variable üzerinden konuşmasını engelle.

LangGraph state ana taşıma mekanizması olarak kalmalıdır.

Beklenen ilk durum:

```text
dataset_topic
dataset_purpose
```

config'den doldurulmuş olur.

Pipeline ilerledikçe diğer alanlar node'lar tarafından doldurulur.

---

# 4. ARDINDAN STRUCTURED MODELLERİ TANIMLA

Mevcut:

```text
src/schemas/models.py
```

dosyasını ve mevcut Pydantic modellerini incele.

Mevcut modellere uyumlu şekilde yeni structured output modellerini ekle.

En azından mantıksal olarak şunlara ihtiyaç vardır:

```text
ResearchPlan

CandidateSource

SourceEvaluation

DatasetSchemaField

DraftDatasetSchema

ApprovedDatasetSchema

ExtractionResult
```

Ancak mevcut projede bunlarla aynı görevi yapan modeller varsa yeniden oluşturma.

Beklenen görevleri:

```text
ResearchPlan
→ Groq ResearchPlanner çıktısı

CandidateSource
→ Firecrawl Search sonucu

SourceEvaluation
→ Groq SourceEvaluator çıktısı

DraftDatasetSchema
→ DatasetSchemaDesigner çıktısı

ApprovedDatasetSchema
→ kullanıcının onayladığı final schema

ExtractionResult
→ StructuredExtractor tarafından üretilen data + confidence
```

olmalıdır.

---

# 5. SONRA GROQ TOOL / CLIENT KATMANINI OLUŞTUR

Mevcut:

```text
src/tools/
```

klasörü LLM araçları için ayrılmıştır ve şu anda boşsa Groq entegrasyonunu burada gerçekleştir.

Örneğin mevcut naming convention uygunsa:

```text
src/tools/groq_client.py
```

veya mevcut proje standardına uygun benzer bir dosya kullanılabilir.

Bu katman yalnızca:

```text
Groq API bağlantısı
Structured Output çağrısı
timeout
retry
API error handling
```

gibi ortak işlemlerden sorumlu olmalıdır.

ResearchPlanner veya DatasetSchemaDesigner iş mantığını Groq client'ın içine doldurma.

Groq client reusable olmalıdır.

---

# 6. DÖRT GROQ GÖREVİNİN PROMPTLARINI AYIR

Mevcut prompt sistemi varsa onu kullan.

Yoksa merkezi bir prompt modülü oluştur.

Örneğin:

```text
src/agents/prompts/
```

veya repository naming convention'ına uygun bir konum.

Şu dört System Prompt ayrı tutulmalıdır:

```text
RESEARCH_PLANNER_SYSTEM_PROMPT

SOURCE_EVALUATOR_SYSTEM_PROMPT

DATASET_SCHEMA_DESIGNER_SYSTEM_PROMPT

STRUCTURED_EXTRACTOR_SYSTEM_PROMPT
```

Her node:

```text
System Prompt
+
State/config'den oluşturulan User Prompt
+
Output Schema
```

ile Groq çağrısı yapmalıdır.

---

# 7. RESEARCH PLANNER NODE

Mevcut:

```text
src/agents/nodes/
```

yapısına ResearchPlanner node ekle.

Mantıksal dosya:

```text
research_planner_node.py
```

olabilir.

Input:

```text
state.dataset_topic
state.dataset_purpose
research config
```

Output:

```text
state.research_plan
```

Beklenen örnek:

```json
{
  "subtopics": [
    "tarih",
    "hazırlama yöntemleri",
    "gelenekler"
  ],

  "search_queries": [
    "Türk kahvesi tarihi",
    "Türk kahvesi gelenekleri"
  ],

  "preferred_source_types": [
    "resmi kurum",
    "üniversite",
    "akademik kaynak"
  ]
}
```

Bu node web'e çıkmamalıdır.

Yalnızca araştırma planlamalıdır.

---

# 8. FIRECRAWL TOOL

Gerçek web işlemleri mevcut:

```text
src/tools/
```

altına eklenmelidir.

Mantıksal olarak:

```text
src/tools/firecrawl_tool.py
```

veya mevcut standarda uygun eşdeğer yapı kullanılabilir.

Firecrawl tool en az:

```text
search(query)

scrape(url)
```

operasyonlarını desteklemelidir.

API key `.env` üzerinden alınmalıdır.

Bu tool dataset schema, source quality veya extraction kararı vermemelidir.

---

# 9. SOURCE SEARCH NODE

`src/agents/nodes/` içerisinde Firecrawl Search kullanan node oluştur veya mevcut acquisition yapısı buna uygunsa genişlet.

Input:

```text
state.research_plan.search_queries
```

Output:

```text
state.candidate_sources
```

Akış:

```text
ResearchPlan
↓
search queries
↓
Firecrawl Search
↓
CandidateSource[]
```

Aynı URL birkaç query sonucunda gelirse mümkün olduğunca normalize/deduplicate et.

---

# 10. SOURCE EVALUATOR NODE

Yeni veya mevcut uygun node içerisinde Groq SourceEvaluator çalışmalıdır.

Input:

```text
dataset_topic
research_plan
candidate_sources
```

Output:

```text
state.selected_sources
```

Bu node yeni URL oluşturamaz.

Yalnızca Firecrawl tarafından bulunan candidate source'lar arasından seçim yapmalıdır.

---

# 11. DATASET SCHEMA DESIGNER NODE

`src/agents/nodes/` içerisinde:

```text
dataset_schema_designer_node.py
```

veya naming convention'a uygun node oluştur.

Input:

```text
dataset_topic
dataset_purpose
research_plan
user schema constraints
```

Output:

```text
state.draft_dataset_schema
```

Bu node'un sonucu ASLA doğrudan StructuredExtractor'a gitmemelidir.

Node tamamlandığında:

```text
state.pipeline_status =
WAITING_FOR_SCHEMA_APPROVAL
```

olmalıdır.

---

# 12. FRONTEND OLMADAN SCHEMA NASIL İNCELENECEK?

Şu anda frontend olmadığı için schema approval sürecini terminal + geçici editable dosya ile çöz.

DatasetSchemaDesigner tamamlandığında:

1. Draft schema terminalde okunabilir şekilde gösterilsin.
2. Draft schema geçici/review amacıyla düzenlenebilir bir JSON/YAML dosyasına yazılsın.

Örneğin repository yapısına uygunsa:

```text
knowledge/review/turkish_culture_draft_schema.json
```

benzeri bir working file kullanılabilir.

Bu bir schema version history sistemi değildir.

Yalnızca mevcut pipeline çalışmasında kullanıcının schema'yı rahatça düzenleyebilmesi içindir.

Terminal kullanıcıya örneğin şu mantıkta bilgi verebilir:

```text
Draft dataset schema oluşturuldu.

Dosya:
knowledge/review/turkish_culture_draft_schema.json

Schema'yı inceleyip istediğiniz alanları:
- ekleyin
- silin
- değiştirin

Hazır olduğunda terminale geri dönüp onaylayın.
```

Kullanıcının terminal içerisinde uzun JSON elle yazması zorunlu olmamalıdır.

IDE/editor üzerinden dosyayı düzenleyebilmelidir.

---

# 13. pipeline.approve_schema() MEKANİZMASI
 # TERMINAL ÜZERİNDEN SCHEMA REVIEW VE APPROVAL AKIŞI

 Frontend şu anda bulunmadığı için Draft Dataset Schema inceleme ve onay süreci terminal üzerinden yönetilmelidir.

 Ancak approval iş mantığını doğrudan `run_domain_test.py` içerisine gömme.

 Terminal yalnızca kullanıcı etkileşim katmanı olmalıdır.

 Gerçek schema approval işlemi pipeline/domain katmanındaki:

 ```python
 pipeline.approve_schema(...)
 ```

 operasyonu üzerinden gerçekleştirilmelidir.

 Beklenen akış:

 ```text
  DatasetSchemaDesigner
        ↓
  DraftDatasetSchema
        ↓
  Draft schema review dosyasına yazılır
        ↓
  WAITING_FOR_SCHEMA_APPROVAL
        ↓
  Terminal kullanıcıya seçenek gösterir
```

   Draft schema oluşturulduğunda terminalde açık şekilde:

  ```text
 --------------------------------------------------
 Draft Dataset Schema oluşturuldu.

 Dosya:
 knowledge/review/turkish_culture_draft_schema.json
  
 Schema dosyasını inceleyebilirsiniz.

 1 - Schema'yı olduğu haliyle ONAYLA
 2 - Schema üzerinde değişiklik yaptım, YENİDEN YÜKLE ve ONAYLA
 3 - İşlemi İPTAL ET
 --------------------------------------------------

 Seçiminiz:
 ```

 benzeri sade bir kullanıcı etkileşimi göster.

 ---

 ## SEÇENEK 1 — DOĞRUDAN ONAYLA

 Kullanıcı:

 ```text
 1
 ```

 seçerse mevcut DraftDatasetSchema kullanılmalıdır.

 Akış:

 ```text
 User selects 1
        ↓
 Current DraftDatasetSchema
        ↓
 pipeline.approve_schema(draft_schema)
        ↓
 Schema Validation
        ↓
 ApprovedDatasetSchema
        ↓
 SCHEMA_APPROVED
        ↓
 Pipeline Resume
 ```

 `pipeline.approve_schema()` validation başarılı olmadan state'i değiştirmemelidir.

 Validation başarısız olursa kullanıcıya hata gösterilmeli ve pipeline:

 ```text
 WAITING_FOR_SCHEMA_APPROVAL
 ```

 durumunda kalmalıdır.

 ---

 ## SEÇENEK 2 — SCHEMA DEĞİŞTİRİLDİ

 Kullanıcı schema dosyasını IDE/editor üzerinden değiştirdiyse:

 ```text
 2
 ```

 seçebilmelidir.

 Bu durumda sistem memory içerisindeki eski DraftDatasetSchema'yı kullanmamalıdır.

 Önce review dosyasını tekrar okumalıdır.

 Akış:

 ```text
 User edits:

 knowledge/review/..._draft_schema.json

        ↓

 User returns to terminal

        ↓

 Selects 2

        ↓

 Reload schema file

        ↓

 Parse edited schema

        ↓

 Validate edited schema

        ↓

 pipeline.approve_schema(edited_schema)

        ↓

 ApprovedDatasetSchema

        ↓

 SCHEMA_APPROVED

        ↓

 Pipeline Resume
```

 Bu sayede kullanıcı örneğin:

```text
 alan ekleyebilir
 alan silebilir
 alan adını değiştirebilir
 type değiştirebilir
 required değiştirebilir
 nullable değiştirebilir
 description değiştirebilir
 extraction_instruction değiştirebilir
 ```

 ve terminale geri dönüp:

 ```text
 2
 ```

 dediğinde sistem değiştirilmiş dosyayı yeniden yükler.

 ---

 ## ÇOK ÖNEMLİ

 `2` seçeneği:

 ```text
 schema'yı tekrar AI'a tasarlat
 ```

 anlamına GELMEMELİDİR.

 Anlamı:

 ```text
 Ben DraftDatasetSchema dosyasını manuel olarak değiştirdim.

 Dosyayı yeniden oku.

 Yeni halini validate et.

 Geçerliyse bunu ApprovedDatasetSchema yap.
 ```

 olmalıdır.

 ---

 ## SEÇENEK 3 — İPTAL

 Kullanıcı:

 ```text
 3
 ```

 seçerse dataset generation işlemi kontrollü şekilde durdurulmalıdır.

 Pipeline yanlışlıkla scraping veya extraction aşamasına devam etmemelidir.

 Mümkünse durum:

 ```text
 CANCELLED
 ```

 gibi açık bir terminal/pipeline sonucu ile sonlandırılabilir.

 Mevcut state modelinde böyle bir durum yoksa gereksiz karmaşıklık yaratmadan kontrollü sonlandırma kullanılabilir.

 ---

 # TERMINAL LOOP

 Kullanıcı geçersiz değer girerse program çökmemelidir.

 Örneğin:

 ```text
 Seçiminiz: 7

 Geçersiz seçim.

 1 - Onayla
 2 - Değiştirilmiş schema'yı yeniden yükle ve onayla
 3 - İptal

 Seçiminiz:
 ```

 şeklinde tekrar seçim istemelidir.

 Basit bir terminal interaction loop yeterlidir.

 ---

 # VALIDATION HATASI DURUMUNDA

 Örneğin kullanıcı schema dosyasını değiştirdi fakat geçersiz hale getirdi:

 ```json
{
  "field_name": "ingredients",
  "type": "bilinmeyen_tip"
}
```

 Bu durumda:

 ```text
 2
 ```

 seçildiğinde sistem:

```text
Reload Schema
↓
Validation Failed
```

 sonucunu vermelidir.

 Terminal kullanıcıya anlaşılır hata göstermelidir.

 Örneğin:

 ```text
 Schema doğrulanamadı.

 Hata:
 Field "ingredients" unsupported type: "bilinmeyen_tip"

 Schema dosyasını tekrar düzenleyin.

 1 - Mevcut schema'yı tekrar dene
 2 - Düzenlenmiş dosyayı yeniden yükle
 3 - İptal
```

 Pipeline bu sırada:

 ```text
 WAITING_FOR_SCHEMA_APPROVAL
 ```

 durumunda kalmalıdır.

 ---

 # run_domain_test.py SORUMLULUĞU

`run_domain_test.py` bu terminal etkileşimini yönetebilir.

 Ancak şu iş mantıklarını kendisi implement etmemelidir:

 ```text 
 schema validation
 approved schema creation
 pipeline state transition
 pipeline continuation
 ```

 Bunlar pipeline/application/domain katmanının sorumluluğu olmalıdır.

 `run_domain_test.py` yalnızca:

 ```text
 Draft schema'yı göster
  ↓
 Kullanıcı input'u al
  ↓
 Gerekirse schema dosyasını yeniden oku
  ↓
 pipeline.approve_schema(schema) çağır
  ↓
 Sonucu kullanıcıya göster
```

 işlemlerini yapmalıdır.

 ---

 # ÖNERİLEN TERMINAL KULLANICI DENEYİMİ

 Gerçek kullanım yaklaşık şöyle görünmelidir:

 ```text
 [INFO] DatasetSchemaDesigner çalışıyor...

 [INFO] Draft Dataset Schema oluşturuldu.

 Draft schema:
 knowledge/review/turkish_culture_draft_schema.json

 Schema dosyasını inceleyebilir ve düzenleyebilirsiniz.


 1 - Schema'yı olduğu haliyle onayla
 2 - Schema'yı değiştirdim, yeniden yükle ve onayla
 3 - İşlemi iptal et

 Seçiminiz: 2


 [INFO] Düzenlenmiş schema yeniden yükleniyor...

 [INFO] Schema validation başarılı.

 [INFO] ApprovedDatasetSchema oluşturuldu.

 [INFO] Pipeline state: SCHEMA_APPROVED

 [INFO] Pipeline devam ediyor...

 [INFO] Selected sources Firecrawl ile scrape ediliyor...
```

 ---

 # TASARIM KURALI

 Terminal kullanıcı açısından:

 ```text
 1
 2
 3
```

 seçeneklerini sunar.

 Ancak sistemin gerçek mimarisi:

 ```text
 Terminal Input
      ↓
 Presentation Layer
      ↓
 pipeline.approve_schema(...)
      ↓
 Schema Validation
      ↓
 ApprovedDatasetSchema
      ↓
 SCHEMA_APPROVED
      ↓
 Pipeline Resume
```

 şeklinde kalmalıdır.

 Bu sayede ileride frontend oluşturulduğunda terminal interaction kaldırılabilir ve aynı:

 ```python
 pipeline.approve_schema(...)
```

 operasyonu UI'daki:

```text
 Approve
```

 butonu tarafından çağrılabilir.

 Schema approval iş mantığını terminale bağımlı hale getirme.

---

# 14. LANGGRAPH PIPELINE'I GÜNCELLE

Mevcut:

```text
src/agents/graphs/phase2_pipeline.py
```

yeni sistemin orchestration merkezi olarak kalmalıdır.

Yeni bağımsız graph oluşturma.

Mevcut graph'a gerekli node'ları ve transition'ları ekle.

Hedef sıra:

```text
START
  ↓
ResearchPlanner
  ↓
SourceSearch
  ↓
SourceEvaluator
  ↓
DatasetSchemaDesigner
  ↓
WAITING_FOR_SCHEMA_APPROVAL
  ↓
pipeline.approve_schema()
  ↓
Approved Schema
  ↓
Acquisition
  ↓
Cleaning
  ↓
Structured Extraction
  ↓
Metadata
  ↓
Quality / Validation
  ↓
Export
  ↓
END
```

Mevcut:

```text
collection
cleaning
classification
metadata
entity/relation
quality
validation
export
```

node'larını gereksiz yere silme.

Yeni sistem bunların önüne ve uygun noktalarına entegre edilmelidir.

Özellikle mevcut `acquisition_node.py` gerçek source content'i alma sorumluluğunu taşıyorsa Firecrawl Scrape entegrasyonunu burada yapmak daha doğru olabilir.

Aynı işi yapan ikinci bir acquisition sistemi oluşturma.

---

# 15. ACQUISITION NODE'U GERÇEK KAYNAĞA BAĞLA

Mevcut mimaride:

```text
sources.yaml
→ acquisition_node.py
```

hattı gerçek kaynak entegrasyonu için planlanmışsa bunu koru.

Firecrawl scraping işlemini mevcut acquisition katmanına bağla.

Input:

```text
state.selected_sources
+
state.approved_dataset_schema mevcut mu?
```

Approved schema doğrudan Firecrawl'a gönderilmek zorunda değildir.

Ancak acquisition aşamasının başlaması için schema approval tamamlanmış olmalıdır.

Output:

```text
state.scraped_documents
```

olmalıdır.

---

# 16. STRUCTURED EXTRACTION NODE

Mevcut extraction/classification node'larını incele.

Structured extraction için zaten uygun bir node varsa onu genişlet.

Yoksa:

```text
structured_extraction_node.py
```

oluştur.

Input:

```text
ApprovedDatasetSchema
+
Clean Source Content
+
Source Metadata
+
Field Extraction Instructions
```

Output:

```text
state.extraction_results
```

Her `ExtractionResult` mantıksal olarak:

```text
data
+
confidence
```

taşımalıdır.

Confidence StructuredExtractor tarafından aynı Groq çağrısında oluşturulmalıdır.

---

# 17. CONFIDENCE AKIŞI

Confidence'ın nerede üretildiği kesin olmalıdır.

```text
ApprovedDatasetSchema
+
Source Content
        ↓
Groq StructuredExtractor
        ↓
ExtractionResult
        ├── data
        └── confidence
        ↓
Metadata Node
        ↓
_metadata.confidence
        ↓
Quality / Validation
```

Confidence:

```text
Metadata node tarafından hesaplanmamalıdır.

Validation node tarafından hesaplanmamalıdır.

Firecrawl tarafından hesaplanmamalıdır.
```

Groq StructuredExtractor üretmelidir.

Metadata node yalnızca confidence değerini final metadata'ya taşımalıdır.

Quality/validation node yalnızca threshold kontrolü yapmalıdır.

---

# 18. MEVCUT METADATA NODE'UNU KORU

Projede zaten metadata node bulunduğu için yeni bağımsız MetadataBuilder sistemi oluşturma.

Mevcut metadata node'u genişlet.

En az:

```text
source_url
source_title
source_domain
retrieved_at
source_provider
search_query
dataset_topic
confidence
```

bilgilerini final record metadata'sına ekleyebilmelidir.

---

# 19. ENTITY / RELATION NODE'LARINI KORU

Projede zaten:

```text
entity
relation
ontology
```

işleme node'ları bulunuyorsa bunları kaldırma.

Dataset ileride GraphRAG/Graph Database kullanımına uygun olacak şekilde mevcut entity/relation extraction aşamalarından geçmeye devam edebilir.

Graph bilgilerini zorunlu olarak `_metadata` içerisine doldurma.

Mevcut entity/relation modelleri ve output yapısı ne şekilde tasarlanmışsa önce onu analiz et ve koru.

---

# 20. QUALITY VE VALIDATION NODE'LARINI KORU

Mevcut quality ve validation node'ları yeni sistemde kullanılmaya devam etmelidir.

StructuredExtractor:

```text
confidence
```

üretir.

Mevcut quality node:

```text
minimum_confidence
```

kontrolünü yapabilir.

Örneğin:

```text
confidence >= 0.70
→ accept

confidence < 0.70
→ reject
```

Mevcut validation node ise:

```text
ApprovedDatasetSchema
type
required fields
metadata
structured output
```

kontrollerini yapmalıdır.

Yeni ikinci validation sistemi oluşturma.

---

# 21. EXPORT NODE'UNU KORU

Final dataset mevcut:

```text
knowledge/datasets/
```

yapısına yazılmaya devam etmelidir.

Örneğin:

```text
knowledge/datasets/turkish_culture.json
```

Mevcut export node JSON üretimini zaten gerçekleştiriyorsa bunu kullan.

Yeni DatasetWriter sistemi oluşturma.

Gerekli alanları mevcut export modeline adapte et.

---

# 22. DOSYA / DEĞİŞİKLİK ÖNCELİK SIRASI

Kodlama sırasında rastgele dosyalardan başlama.

Önce mevcut yapıyı analiz ettikten sonra mantıksal olarak şu sırayı takip et:

```text
1.
src/schemas/models.py
→ yeni structured modeller

2.
src/state/state.py
→ yeni pipeline state alanları

3.
src/tools/groq_*
→ Groq ortak client/tool

4.
src/tools/firecrawl_*
→ gerçek web search/scrape

5.
Prompt definitions
→ 4 ayrı Groq System Prompt

6.
ResearchPlanner node

7.
SourceSearch node

8.
SourceEvaluator node

9.
DatasetSchemaDesigner node

10.
Schema approval / pipeline.approve_schema()

11.
Mevcut acquisition_node.py
→ Firecrawl scrape entegrasyonu

12.
Structured extraction entegrasyonu

13.
Mevcut metadata node
→ provenance + confidence

14.
Mevcut quality/validation
→ approved schema + confidence

15.
phase2_pipeline.py
→ yeni graph sırası ve state transition'ları

16.
run_domain_test.py
→ gerçek config + terminal approval akışı

17.
tests/
→ yeni davranışların testleri

18.
README.md
→ bütün sistemin detaylı dokümantasyonu
```

Gerçek dependency ilişkileri farklıysa gerekli küçük sıra değişikliklerini yap fakat nedenini açıkla.

---

# 23. HER AŞAMADAN BEKLENEN ÇIKTI

Sistemde hangi node'un ne ürettiği net olmalıdır.

```text
Config Loader
→ dataset_topic + dataset_purpose


ResearchPlanner
→ ResearchPlan


Firecrawl Search
→ CandidateSource[]


SourceEvaluator
→ SelectedSource[]


DatasetSchemaDesigner
→ DraftDatasetSchema


User Approval
→ ApprovedDatasetSchema


Acquisition / Firecrawl Scrape
→ RawSourceDocument[]


Cleaning
→ CleanDocument[]


StructuredExtractor
→ ExtractionResult[]
   data + confidence


Metadata Node
→ enriched dataset records


Entity / Relation Nodes
→ mevcut graph/entity/relation bilgileri


Quality Node
→ accepted / rejected records


Validation Node
→ validated records


Export Node
→ knowledge/datasets/*.json
```

Bu contract'ları mümkün olduğunca typed modeller üzerinden koru.

---

# 24. FRONTEND ŞİMDİLİK YOK

Bu aşamada frontend oluşturma.

Kullanıcı etkileşimi:

```text
config dosyası
+
run_domain_test.py
+
terminal
+
draft schema review dosyası
```

üzerinden gerçekleşmelidir.

İleride frontend geldiğinde aynı backend/domain operasyonları kullanılacaktır.

Özellikle frontend gelecekte:

```text
pipeline.approve_schema()
```

operasyonunu çağırabilmelidir.

Bu nedenle approval mantığını `run_domain_test.py` içerisine gömülü ve yeniden kullanılamaz hale getirme.

Terminal runner yalnızca bu domain operasyonunu çağıran presentation katmanı olmalıdır.

---

# 25. BU YAPIDA KULLANICI DENEYİMİ

İlk sürümde gerçek kullanım yaklaşık şöyle olmalıdır:

```text
1. Kullanıcı domain config içerisinde topic/purpose girer.

2. Terminalden pipeline'ı başlatır.

3. Groq ResearchPlanner araştırmayı planlar.

4. Firecrawl gerçek URL'leri bulur.

5. Groq SourceEvaluator kaynakları seçer.

6. Groq DatasetSchemaDesigner draft schema üretir.

7. Pipeline WAITING_FOR_SCHEMA_APPROVAL durumuna geçer.

8. Draft schema terminalde gösterilir ve review dosyasına yazılır.

9. Kullanıcı dosyayı IDE/editor ile düzenler.

10. Terminale geri dönerek schema'yı onaylar.

11. run_domain_test.py düzenlenmiş schema'yı yükler ve
    pipeline.approve_schema(...) çağırır.

12. Schema validate edilir.

13. ApprovedDatasetSchema oluşturulur.

14. Pipeline kaldığı yerden devam eder.

15. Firecrawl selected URL'leri scrape eder.

16. Mevcut cleaning işlemleri çalışır.

17. Groq StructuredExtractor approved schema'ya göre data + confidence üretir.

18. Metadata/entity/relation/quality/validation node'ları mevcut görevlerini gerçekleştirir.

19. Final dataset knowledge/datasets/ altına yazılır.
```

Bu kullanıcı deneyimini README içerisinde de detaylı olarak açıkla.

---

# TEMEL TASARIM KURALI

Bu repository'nin mevcut mimarisini:

```text
CONFIG
→ LANGGRAPH
→ STATE
→ NODES
→ VALIDATION
→ EXPORT
```

koru.

Yeni sistem:

```text
GROQ
+
FIRECRAWL
+
DATASET SCHEMA DESIGNER
+
SCHEMA APPROVAL
```

özelliklerini bu mimariye ENTEGRE etmelidir.

Mevcut projeyi ikinci bir mimari ile sarmalama veya yeniden yazma.

# .ENV.EXAMPLE

Repository root'ta:

```text
.env.example
```

oluştur veya mevcutsa güncelle.

En az şu ayarların karşılığı bulunmalıdır:

```env
# =====================================================
# APPLICATION
# =====================================================

APP_ENV=development
LOG_LEVEL=INFO


# =====================================================
# DATA SOURCE
# mock | firecrawl
# =====================================================

DATA_SOURCE_PROVIDER=firecrawl


# =====================================================
# FIRECRAWL
# Search / Scrape / Crawl
# =====================================================

FIRECRAWL_API_KEY=fc-your-api-key
FIRECRAWL_API_URL=https://api.firecrawl.dev
FIRECRAWL_SEARCH_LIMIT=10
FIRECRAWL_REQUEST_TIMEOUT=60


# =====================================================
# GROQ CLOUD
# Research planning
# Source evaluation
# Dataset schema design
# Structured extraction
# =====================================================

GROQ_API_KEY=gsk-your-api-key
GROQ_MODEL=your-groq-model-id
GROQ_TEMPERATURE=0
GROQ_REQUEST_TIMEOUT=60


# =====================================================
# RESEARCH
# =====================================================

DEFAULT_MAX_SEARCH_QUERIES=10
DEFAULT_MAX_SOURCES=20


# =====================================================
# SCHEMA APPROVAL
# =====================================================

REQUIRE_SCHEMA_APPROVAL=true


# =====================================================
# QUALITY
# =====================================================

MINIMUM_CONFIDENCE=0.70
LOW_CONFIDENCE_ACTION=review


# =====================================================
# EXTRACTION
# =====================================================

MAX_EXTRACTION_RETRIES=3
VALIDATE_STRUCTURED_OUTPUT=true


# =====================================================
# OUTPUT
# =====================================================

OUTPUT_DIRECTORY=./data/output
DEFAULT_OUTPUT_FORMAT=jsonl

SAVE_RAW_CONTENT=false
SAVE_CLEAN_CONTENT=false
```

Gerçek API key yazma.

Kod içerisinde API key veya secret hard-code etme.

Mevcut naming convention varsa koru.

---

# .GITIGNORE

`.env` Git'e commit edilmemelidir.

`.env.example` commit edilebilmelidir.

API key'leri:

- source code
- test
- fixture
- output
- log
- README

içerisinde bulunmamalıdır.

---

# CENTRAL SETTINGS

Environment variable'ları uygulamanın farklı yerlerinden rastgele `os.getenv()` ile okuma.

Mevcut centralized settings sistemi varsa onu genişlet.

Yoksa uygun merkezi settings sistemi oluştur.

---

# PROMPT MANAGEMENT

Dört Groq görevinin System Prompt'larını merkezi olarak yönet.

Mantıksal olarak:

```text
RESEARCH_PLANNER_SYSTEM_PROMPT

SOURCE_EVALUATOR_SYSTEM_PROMPT

DATASET_SCHEMA_DESIGNER_SYSTEM_PROMPT

STRUCTURED_EXTRACTOR_SYSTEM_PROMPT
```

System Prompt:

```text
görev
+
değişmeyen kurallar
+
sınırlar
+
output davranışı
```

içermelidir.

User Prompt ise o çalıştırmaya özgü:

```text
topic
research plan
sources
schema
content
config
```

bilgilerini içermelidir.

System Prompt ve User Prompt'u birbirine karıştırma.

---

# ERROR HANDLING

Şunları düzgün yönet:

- FIRECRAWL_API_KEY eksik
- GROQ_API_KEY eksik
- geçersiz URL
- Firecrawl timeout
- Firecrawl rate limit
- authentication error
- search sonucu olmaması
- scrape sonucu boş olması
- Groq timeout
- Groq rate limit
- model hatası
- structured output hatası
- invalid schema
- schema approval olmadan extraction başlatılması
- schema validation hatası
- düşük confidence
- output problemi
- dosya yazma problemi

Özellikle:

```text
WAITING_FOR_SCHEMA_APPROVAL
```

durumu bir hata değildir.

Pipeline'ın normal bir durumudur.

---

# RETRY

Firecrawl ve Groq transient network hatalarında kontrollü exponential backoff kullan.

Ancak:

```text
401
invalid API key
invalid schema
unsupported model
configuration error
```

gibi retry ile düzelmeyecek hataları tekrar tekrar çağırma.

---

# LOGGING

Pipeline logları aşamaları açıkça göstermelidir.

Örneğin:

```text
[INFO] Dataset topic loaded

[INFO] Pipeline state: PLANNING_RESEARCH

[INFO] Generating research plan

[INFO] Generated 8 search queries

[INFO] Searching sources with Firecrawl

[INFO] 38 candidate sources discovered

[INFO] Evaluating sources

[INFO] 11 sources selected

[INFO] Designing draft dataset schema

[INFO] Draft schema created

[INFO] Pipeline state: WAITING_FOR_SCHEMA_APPROVAL

[INFO] Schema approved by user

[INFO] Pipeline state: SCHEMA_APPROVED

[INFO] Scraping selected sources

[INFO] Extracting structured records

[INFO] Record confidence: 0.93

[INFO] Validation successful

[INFO] Dataset completed
```

Secret'ları loglama.

---

# DEPENDENCIES

Mevcut dependency manager'ı tespit et.

Örneğin:

```text
requirements.txt
pyproject.toml
Poetry
uv
Pipenv
```

hangisi kullanılıyorsa onu koru.

Gerekliyse resmi:

```text
firecrawl-py
groq
```

paketlerini ekle.

Gereksiz dependency ekleme.

---

# TESTLER

Unit testler gerçek API çağrılarına bağımlı olmamalıdır.

Mock kullan.

En az şu davranışları test et:

```text
config loading

environment loading

mock provider

Firecrawl provider

ResearchPlanner

Firecrawl search

candidate source normalization

SourceEvaluator

DatasetSchemaDesigner

draft schema creation

pipeline enters WAITING_FOR_SCHEMA_APPROVAL

extraction cannot start before approval

schema field editing

schema approval

approved schema persistence

Firecrawl scrape

StructuredExtractor

record confidence

field confidence

minimum confidence validation

schema validation

invalid structured output

missing API keys

failed URL

empty content

deduplication

metadata building

JSON serialization

JSONL serialization

pipeline state transitions
```

Mevcut test suite'i de çalıştır.

---

# OPTIONAL INTEGRATION TEST

Gerçek API'lerle çalışan testler:

```text
RUN_INTEGRATION_TESTS=true
```

gibi bir flag ile açılabilir.

Normal unit test suite'in parçası olmasın.

API key yoksa skip edilsin.

---

# README.MD ÇOK ÖNEMLİ

Bu projede README basit birkaç kurulum satırından ibaret olmamalıdır.

README projenin ana teknik ve kavramsal dokümanı olmalıdır.

README'yi detaylı şekilde güncelle.

README'de aşağıdaki bölümler MUTLAKA bulunmalıdır.

---

# README — 1. PROJECT VISION

Projenin neden var olduğunu açıkla.

Şunu net şekilde anlat:

```text
Bu proje RAG değildir.

Bu proje RAG,
GraphRAG,
LLM,
ML,
Knowledge Base ve
Fine-tuning sistemlerini beslemek için
gerçek web kaynaklarından
structured dataset üretir.
```

Kullanıcının yalnızca dataset konusunu tanımlayarak süreci başlatabildiğini anlat.

---

# README — 2. PROBLEM

Manuel veri toplamanın sorunlarını anlat:

- kaynakları elle araştırmak,
- URL toplamak,
- veri yapısını elle tasarlamak,
- web sayfalarını temizlemek,
- verileri JSON'a çevirmek,
- kaynak bilgisini takip etmek,
- kalitesiz kayıtları ayıklamak

gibi işlemlerin bu sistem tarafından nasıl azaltıldığını açıkla.

---

# README — 3. CORE PIPELINE

Şu pipeline'ı detaylı açıkla:

```text
Dataset Topic
      ↓
ResearchPlanner
      ↓
Firecrawl Search
      ↓
SourceEvaluator
      ↓
DatasetSchemaDesigner
      ↓
Draft Schema
      ↓
User Review
      ↓
Approved Schema
      ↓
Firecrawl Scrape
      ↓
StructuredExtractor
      ↓
Confidence
      ↓
Validation
      ↓
Dataset
```

Her aşamada:

- input nedir,
- hangi servis çalışır,
- output nedir,
- sonraki aşamaya ne gider

anlat.

---

# README — 4. HUMAN-IN-THE-LOOP

Bu bölüm özellikle detaylı olmalıdır.

Şunu anlat:

```text
DatasetSchemaDesigner nihai schema oluşturmaz.

Bir draft tasarlar.

Kullanıcı draft schema'yı inceler.

Gerekirse değiştirir.

Sonra onaylar.

Extraction yalnızca approved schema
ile çalışır.
```

Neden bu yaklaşımın kullanıldığını açıkla:

- kullanıcı kontrolü,
- yanlış field'ların engellenmesi,
- gereksiz alanların temizlenmesi,
- farklı RAG projelerine göre schema özelleştirme,
- AI tarafından verilen kararları körü körüne kabul etmeme.

---

# README — 5. GROQ ARCHITECTURE

Groq'un dört görevini ayrı ayrı açıkla:

```text
ResearchPlanner

SourceEvaluator

DatasetSchemaDesigner

StructuredExtractor
```

Her birinin:

- ne yaptığını,
- ne yapmadığını,
- System Prompt'un görevini,
- User Prompt'un görevini,
- Structured Output'un neden kullanıldığını

açıkla.

---

# README — 6. FIRECRAWL ARCHITECTURE

Firecrawl'ın:

```text
Search
Scrape
gerekirse Crawl
```

işlemlerinde kullanıldığını açıkla.

Groq ile Firecrawl'ın sorumluluklarının neden ayrıldığını anlat.

---

# README — 7. SCHEMA SYSTEM

Şunları açıkça ayır:

```text
Groq Output Schema

Draft Dataset Schema

Approved Dataset Schema

Metadata Schema
```

Özellikle şu karışıklığı engelle:

```text
Groq Output Schema
=
Groq'un cevap formatı.

Dataset Schema
=
Gerçek dataset'in alanları.
```

---

# README — 8. PIPELINE STATES

Pipeline durumlarını açıkla.

Özellikle:

```text
WAITING_FOR_SCHEMA_APPROVAL
```

durumunun neden var olduğunu anlat.

İleride kurulacak UI'nin bu state'leri kullanarak kullanıcıya her aşamayı gösterebileceğini belirt.

---

# README — 9. CONFIDENCE

Confidence sistemini detaylı açıkla.

Şunları belirt:

```text
Confidence native Groq probability değildir.

Kaynak kanıtının extracted data'yı
ne kadar desteklediğine ilişkin
evidence-support skorudur.
```

Rubric'i açıkla.

Minimum threshold kullanımını anlat.

---

# README — 10. CONFIGURATION

Config'in:

- dataset topic
- purpose
- research
- source
- schema approval
- quality
- output

ayarlarını nasıl yönettiğini gerçek örnekle anlat.

---

# README — 11. ENVIRONMENT

`.env.example` üzerinden:

- Firecrawl
- Groq
- confidence
- output
- source provider

ayarlarını açıkla.

Gerçek secret gösterme.

---

# README — 12. MOCK VS REAL MODE

Mock mode ile Firecrawl/Groq mode arasındaki farkları açıkla.

Mock sistemin neden korunacağını anlat.

---

# README — 13. HOW TO RUN

Repository'nin gerçek çalışma yöntemini tespit et.

Windows PowerShell için gerçek komutlarla anlat.

Tahmin ederek entry point uydurma.

---

# README — 14. EXAMPLE WORKFLOW

Örnek bir dataset generation senaryosu göster.

Örneğin:

```text
Malatya yöresel yemekleri
```

konusu üzerinden:

```text
topic
↓
research plan
↓
search
↓
sources
↓
draft schema
↓
user edit
↓
approval
↓
scrape
↓
extraction
↓
confidence
↓
dataset
```

akışını göster.

---

# README — 15. OUTPUT FORMAT

Örnek JSON / JSONL record göster.

Örneğin:

```json
{
  "data": {
    "dish_name": "Analı Kızlı",
    "ingredients": [
      "bulgur",
      "kıyma"
    ]
  },

  "_metadata": {
    "source_url": "https://...",
    "source_title": "...",
    "retrieved_at": "...",
    "source_provider": "firecrawl",
    "schema_version": "1",
    "extraction_model": "...",
    "confidence": 0.94
  }
}
```

---

# README — 16. FUTURE UI

README içerisinde kısa bir future roadmap bölümü oluştur.

Şu anda UI'nin oluşturulmadığını açıkça belirt.

Ancak gelecekte basit bir arayüzün:

- araştırma aşamasını,
- kaynakları,
- draft schema'yı,
- schema editing'i,
- approval işlemini,
- scraping durumunu,
- extraction durumunu,
- validation sonuçlarını,
- final dataset'i

gösterebileceğini açıkla.

Backend'in pipeline state modeli sayesinde buna hazırlandığını belirt.

---

# KOD DEĞİŞİKLİKLERİ SONRASINDA BANA YAPTIĞIN HER ŞEYİ AÇIKLA

Sadece:

```text
Done
```

deme.

Cevabını aşağıdaki sırada ver.

## 1. MEVCUT PROJEYİ NASIL ANLADIN?

Gerçek dosya yollarıyla anlat.

## 2. HANGİ DOSYALARI DEĞİŞTİRDİN?

Her önemli dosya için:

```text
Önceden ne yapıyordu?

Ne değiştirdin?

Neden değiştirdin?

Şimdi sistemde görevi ne?
```

anlat.

## 3. PIPELINE'I GERÇEK KOD ÜZERİNDEN ANLAT

Şu akışı:

```text
Topic
↓
ResearchPlanner
↓
Firecrawl Search
↓
SourceEvaluator
↓
DatasetSchemaDesigner
↓
Draft Schema
↓
WAITING_FOR_SCHEMA_APPROVAL
↓
Schema Approval
↓
Firecrawl Scrape
↓
StructuredExtractor
↓
Validation
↓
Dataset
```

gerçek:

- class,
- method/function,
- dosya

isimleriyle açıkla.

## 4. SCHEMA APPROVAL MEKANİZMASINI DETAYLI ANLAT

Şunları cevapla:

- Draft schema nerede oluşuyor?
- Nerede tutuluyor?
- Kullanıcı nasıl değiştirebilir?
- Pipeline neden duruyor?
- Approval nasıl kaydediliyor?
- Approved schema nasıl oluşuyor?
- Extraction neden draft schema ile başlayamıyor?
- Approved schema version nasıl tutuluyor?

## 5. GROQ'U AÇIKLA

Dört görevi ayrı ayrı anlat.

## 6. FIRECRAWL'I AÇIKLA

Search ve scrape akışını anlat.

## 7. CONFIDENCE'I AÇIKLA

Nasıl üretiliyor ve nasıl kullanılıyor anlat.

## 8. PIPELINE STATE SİSTEMİNİ AÇIKLA

Her önemli state'in anlamını anlat.

İleride UI'nin bunları nasıl kullanabileceğini kısaca belirt.

## 9. .ENV.EXAMPLE DOSYASINI TAM GÖSTER

Her environment variable'ın görevini açıkla.

## 10. README'Yİ ÖZETLE

README'ye hangi bölümleri eklediğini ve kullanıcının projeyi README üzerinden nasıl anlayabileceğini anlat.

## 11. WINDOWS POWERSHELL KURULUMU

Gerçek repository komutlarını kullan.

## 12. GERÇEK ÖRNEK WORKFLOW

Bir dataset konusu üzerinden baştan sona örnek göster.

---

# ÇOK ÖNEMLİ KURALLAR

1. Repository'yi analiz etmeden kod yazma.
2. Projeyi sıfırdan yeniden oluşturma.
3. Mevcut çalışan mock sistemini silme.
4. Mevcut config sistemini sebepsiz yere bozma.
5. Var olan abstraction varsa yeniden oluşturma.
6. Firecrawl ve Groq sorumluluklarını birbirine karıştırma.
7. Tek genel Groq promptu kullanma.
8. Dört Groq görevinin System Prompt'larını ayrı tut.
9. `DatasetSchemaDesigner` adını kullan.
10. `SchemaProposalGenerator` ismini kullanma.
11. DatasetSchemaDesigner çıktısını doğrudan extraction'a gönderme.
12. Draft schema ile extraction başlatma.
13. Kullanıcı onayını zorunlu tut.
14. Kullanıcı schema'yı değiştirebilsin.
15. Approved schema olmadan scraping/extraction aşamasına geçme.
16. `WAITING_FOR_SCHEMA_APPROVAL` normal pipeline state'i olarak ele al.
17. Gelecekteki UI için pipeline aşamalarını gözlemlenebilir tut.
18. Şu anda gereksiz büyük bir frontend oluşturma.
19. Dataset schema'yı sabit field'lara bağlama.
20. Metadata ile dataset verisini karıştırma.
21. Provenance bilgisini kaybetme.
22. LLM'e kaynakta olmayan bilgiyi uydurtma.
23. Structured output'u validation olmadan kaydetme.
24. Confidence'ın Groq API native probability'si olduğunu varsayma.
25. Düşük confidence verilerini kontrolsüz dataset'e ekleme.
26. API key'leri hard-code etme.
27. Secret'ları loglama.
28. Unit testleri gerçek API key'lere bağımlı yapma.
29. Gereksiz dependency ekleme.
30. Mevcut testleri bozma.
31. README'yi yüzeysel bırakma.
32. README projenin vizyonunu ve bütün pipeline'ı detaylı anlatmalı.
33. Testleri çalıştırmadan tamamlandı deme.

---

# SON HEDEF

Sistem sonunda şu şekilde çalışmalıdır:

```text
BEN

Dataset konusunu tanımlarım.
        ↓

GROQ
ResearchPlanner

Araştırma planını oluşturur.
        ↓

FIRECRAWL

Gerçek kaynakları bulur.
        ↓

GROQ
SourceEvaluator

Kaliteli kaynakları seçer.
        ↓

GROQ
DatasetSchemaDesigner

Dataset için
DRAFT SCHEMA tasarlar.
        ↓

SİSTEM

WAITING_FOR_SCHEMA_APPROVAL
durumuna geçer.
        ↓

BEN

Schema'yı incelerim.

Alan eklerim.

Alan silerim.

Alan değiştiririm.

İstediğim hale getiririm.

Onaylarım.
        ↓

APPROVED DATASET SCHEMA
        ↓

FIRECRAWL

Gerçek kaynakları scrape eder.
        ↓

GROQ
StructuredExtractor

Yalnızca approved schema'ya göre
verileri çıkarır.
        ↓

CONFIDENCE
        ↓

VALIDATION
        ↓

DEDUPLICATION
        ↓

METADATA
        ↓

JSON / JSONL DATASET
```

Bu dataset daha sonra başka:

```text
RAG
GraphRAG
Vector Database
Knowledge Base
Machine Learning
LLM
Fine-tuning
Agent
```

projelerinde kullanılabilmelidir.

Şu anda ana öncelik:

```text
SAĞLAM DATASET GENERATION BACKEND
+
HUMAN-IN-THE-LOOP SCHEMA APPROVAL
+
OBSERVABLE PIPELINE STATE
```

oluşturmaktır.

Gelişmiş UI bu altyapı tamamlandıktan sonra ayrı bir aşamada yapılacaktır.

Ancak mevcut backend mimarisi gelecekteki bu UI'yi desteklemeye hazır olmalıdır.

Önce repository'yi analiz et.

Sonra mevcut yapıyı bozmadan gerekli değişiklikleri gerçekten uygula.

`.env.example` oluştur.

README'yi detaylı şekilde güncelle.

Testleri ekle ve çalıştır.

En sonunda yaptığın sistemi bana gerçek dosya, class ve function isimleri üzerinden öğret.
# PROJECT LANGUAGE POLICY — MANDATORY

All newly written project content must be in English.

This rule applies to:

* source code comments
* docstrings
* variable descriptions
* error messages
* log messages
* CLI messages
* configuration comments
* YAML comments
* JSON examples
* schema descriptions
* extraction instructions
* prompt definitions
* test descriptions
* documentation
* `README.md`
* `DEVELOPMENT_PROGRESS.md`

All new technical documentation must be written in English.

`README.md` MUST be completely written in English.

`DEVELOPMENT_PROGRESS.md` MUST also be completely written in English.

Do not create Turkish versions of these files.

Do not create duplicate documentation files such as:

```text
README_TR.md
README_EN.md
DEVELOPMENT_PROGRESS_EN.md
```

unless explicitly requested.

The existing project files must be modified in place.

---

# EXISTING TURKISH CONTENT

Before making large changes, inspect the existing repository for Turkish text in:

* README files
* documentation
* source code comments
* docstrings
* logs
* CLI output
* config comments
* prompts
* schema descriptions
* tests
* progress documentation

Do NOT immediately rewrite unrelated existing Turkish content while implementing core functionality.

Instead, keep a temporary internal list of Turkish text that should be converted to English.

Do not create a new tracking file solely for this purpose.

If `DEVELOPMENT_PROGRESS.md` already exists, record this work under the existing progress/checkpoint structure.

For example:

```text
Pending Language Cleanup:
- README.md contains Turkish sections.
- src/agents/nodes/... contains Turkish log messages.
- configs/... contains Turkish comments.
```

This is only a temporary implementation note.

---

# LANGUAGE CLEANUP PHASE

After the functional implementation is complete and tests are passing, perform a final language cleanup pass.

During this phase:

1. Re-scan all files modified during this implementation.
2. Identify Turkish technical text.
3. Translate that text into clear technical English.
4. Modify the EXISTING files in place.
5. Do not create replacement copies.
6. Preserve code behavior while translating comments, documentation and messages.
7. Do not translate proper nouns, dataset content, user-provided cultural terms, source content or factual data unless translation is explicitly required.

Examples of content that SHOULD be translated:

```text
"Şema doğrulandı."
```

should become:

```text
"Schema validation succeeded."
```

and:

```text
"Kaynaklar aranıyor..."
```

should become:

```text
"Searching sources..."
```

Examples of content that should NOT automatically be translated:

```text
"Türk kahvesi"
"Analı Kızlı"
"Malatya"
```

because these may be real dataset values, entity names or user-provided domain content.

---

# README LANGUAGE REQUIREMENT

The final `README.md` must contain no Turkish explanatory or technical documentation unless a Turkish phrase is intentionally shown as example dataset content.

The README must describe in English:

* project vision
* problem statement
* architecture
* pipeline
* ResearchPlanner
* SourceEvaluator
* DatasetSchemaDesigner
* StructuredExtractor
* Firecrawl integration
* Groq integration
* schema review and approval
* terminal workflow
* confidence generation
* validation
* configuration
* mock vs real mode
* installation
* usage
* example workflow
* output structure
* future UI plan

Do not create a second README.

Update the existing `README.md`.

---

# FINAL LANGUAGE VERIFICATION

Before declaring the work complete, perform a final language verification.

Check all files modified during this task for accidental Turkish technical text.

Report any intentionally preserved Turkish text and explain why it was preserved.

The implementation must not be considered complete until:

```text
Code-related text       → English
Comments                → English
Docstrings              → English
Logs                    → English
CLI messages            → English
Prompts                 → English
README.md               → English
DEVELOPMENT_PROGRESS.md → English
```

Any real source content, entity names, dataset values or user-provided domain-specific text may remain in its original language.
