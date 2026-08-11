# 09 – Test Rehberi

## Ne?

Bu doküman, test seviyelerini, kabul kriterlerini ve mock veri kuralını tanımlar.

## Neden?

Deterministik bileşenler ile LLM tabanlı bileşenlerin test yaklaşımı farklıdır. Net seviye ayrımı olmadan, testler ya yetersiz kalır ya da LLM çıktısına aşırı bağımlı hale gelir.

## Nasıl?

### Test Seviyeleri

| Seviye | Kapsam | Örnek |
|---|---|---|
| Unit | Tek fonksiyon, dış bağımlılık yok | Metin temizleme fonksiyonu |
| Node | Tek node, state girdi/çıktısı | Validation node'un state güncellemesi |
| Graph | Uçtan uca akış, birden fazla node | Acquisition → Export tam akışı |

### Kabul Kriteri

- **Unit test:** Girdi/çıktı çiftleri şema ile eşleşmelidir; kenar durumlar (boş veri, hatalı format) test edilir.
- **Node test:** Node çalıştıktan sonra state'in yalnızca ilgili alanları değişmiş olmalıdır (bkz. `05_STATE_DESIGN`).
- **Graph test:** Akış `completed` veya beklenen `failed` durumuyla sonuçlanmalı; `errors` alanı beklenen içerikle uyuşmalıdır.
- LLM tabanlı node'larda kabul kriteri tam eşleşme değil, şema uygunluğu ve tanımlı eşik değerlerin (örn. `confidence_score`) sağlanmasıdır.

### Mock Veri Kuralı

- Dış kaynaklara (web, API) gerçek istek atan testler yasaktır; kaynak yanıtları mock'lanır.
- LLM çağrıları test ortamında sabit/mock yanıtlarla çalıştırılır; gerçek model çağrısı yalnızca entegrasyon testlerinde ve açıkça işaretlenmiş şekilde yapılır.
- Mock veriler `tests/` altında domain'den bağımsız, jenerik örnekler olarak tutulur; belirli bir domain'e özel mock veri çekirdek testlerde kullanılmaz.