# 04 – Agent Spesifikasyonları

## Ne?

Bu doküman, platformdaki agent'ları, her agent'ın girdi/çıktısını, sorumluluğunu ve kullandığı node'ları tanımlar.

## Neden?

Agent orkestrasyonunun şeffaf kalması için (bkz. `01_DEVELOPMENT_RULES`), her agent'ın sınırları ve sorumluluğu açıkça tanımlanmalıdır. Belirsiz sorumluluk, node'ların büyümesine ve mantığın gizlenmesine yol açar.

## Nasıl?

### Agent Listesi

| Agent | Sorumluluk | Girdi | Çıktı |
|---|---|---|---|
| Acquisition Agent | Konfigürasyonda tanımlı kaynaklardan ham veri toplar | Domain config | Ham veri (JSON) |
| Processing Agent | Ham veriyi temizler, normalize eder | Ham veri | İşlenmiş veri (JSON) |
| Enrichment Agent | Bağlam ve ilişki bilgisi ekler | İşlenmiş veri | Zenginleştirilmiş veri (JSON) |
| Validation Agent | Kural ve LLM tabanlı doğruluk kontrolü yapar | Zenginleştirilmiş veri | Doğrulanmış veri + doğrulama raporu |
| Export Agent | Nihai JSON çıktısını üretir | Doğrulanmış veri | Şemaya uygun çıktı dosyası |

### Ortak Kurallar

- Her agent, `02_ARCHITECTURE` içinde tanımlanan bir katmana karşılık gelir.
- Her agent, bir veya daha fazla küçük node'dan oluşur; tek bir node birden fazla sorumluluk üstlenmez.
- Agent'lar arası geçiş yalnızca LangGraph edge tanımlarıyla yapılır; doğrudan fonksiyon çağrısı yapılmaz.
- Bir agent'ın LLM kullanıp kullanmadığı, deterministik yöntemin yetersiz kaldığı node bazında belirlenir (bkz. `Yazım İlkeleri`, `01_DEVELOPMENT_RULES`).

### Node Kullanım İlkesi

Her node:

- tek bir girdi şeması, tek bir çıktı şeması ile çalışır,
- state'i doğrudan değil, tanımlı alanlar üzerinden günceller (bkz. `05_STATE_DESIGN`),
- hata durumunda akışı durdurmak yerine hatayı state'e yazar ve bir sonraki node'un karar vermesine izin verir.