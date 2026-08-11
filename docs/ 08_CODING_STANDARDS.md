# 08 – Kodlama Standartları

## Ne?

Bu doküman, isimlendirme kurallarını, fonksiyon/node büyüklük sınırını ve hata yönetimi kuralını tanımlar.

## Neden?

Küçük ve tek sorumluluklu node ilkesi (bkz. `Yazım İlkeleri`), ancak tutarlı kodlama standartlarıyla sürdürülebilir. Standart olmadan node'lar zamanla büyür ve tek sorumluluk ilkesi bozulur.

## Nasıl?

### İsimlendirme

- Dosya ve fonksiyon adları: `snake_case`.
- Sınıf adları: `PascalCase`.
- Sabitler: `UPPER_SNAKE_CASE`.
- Node fonksiyonları `_node` son ekiyle biter (örn. `clean_text_node`).

### Fonksiyon / Node Büyüklük Sınırı

- Bir node fonksiyonu **50 satırı** aşmaz; aşarsa alt fonksiyonlara bölünür.
- Bir node, birden fazla state alanını güncelliyorsa, bu güncellemelerin hepsi tek bir mantıksal sorumluluğa ait olmalıdır; değilse node ikiye bölünür.
- Bir fonksiyon en fazla 4 parametre alır; fazlası için yapılandırılmış girdi (obje/dataclass) kullanılır.

### Hata Yönetimi

- Node içinde oluşan hatalar, akışı durdurmadan `state.errors` alanına yazılır (bkz. `05_STATE_DESIGN`).
- Kurtarılamaz hatalar (örn. şema uyuşmazlığı), `status` alanını `failed` yapar ve akış sonlanır.
- Hata mesajları, hangi node'da ve hangi girdiyle oluştuğunu içerir; sessiz (loglanmamış) hata bastırma yapılmaz.
- Dış servis çağrıları (LLM, API) `try/except` ile sarılır; yeniden deneme (retry) sayısı konfigürasyon üzerinden yönetilir.

### Yasaklı Uygulamalar

- Global değişken üzerinden state paylaşımı.
- Node içinde başka bir node'un doğrudan çağrılması (yalnızca graph üzerinden yönlendirme).
- Domain'e özgü koşul (`if domain == "turkish_culture"`) çekirdek kod içinde kullanılması; bu tür ayrımlar yalnızca konfigürasyon üzerinden yapılır.