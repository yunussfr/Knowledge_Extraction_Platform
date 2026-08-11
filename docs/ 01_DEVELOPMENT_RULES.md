# 01 – Geliştirme Kuralları

## Ne?

Bu doküman, proje boyunca değişmeyecek kuralları; izinli/yasaklı kütüphaneleri ve yeni bir araç değerlendirilirken uygulanacak karar ilkesini tanımlar.

## Neden?

Projenin amacı yalnızca çalışan bir sistem değil, agent mimarisinin şeffaf biçimde anlaşılmasıdır. Bu nedenle, planlama/yönlendirme/orkestrasyon mantığını gizleyen araçların kullanımı engellenmelidir; aksi halde mimari "kara kutu" haline gelir.

## Nasıl?

### Agent Geliştirme – İzinli Kütüphaneler

| Kütüphane | Kullanım Alanı |
|---|---|
| LangGraph | Agent orkestrasyonu, state machine, node/edge tanımı |
| LangChain | Model çağrıları, prompt yönetimi, araç entegrasyonu |
| LlamaIndex | Bilgi indeksleme, retrieval |

### Agent Geliştirme – Yasaklı Kütüphaneler

- CrewAI
- AutoGen
- PydanticAI Agents
- Semantic Kernel Agents
- Planlama, yönlendirme, orkestrasyon veya agent mantığını gizleyen her türlü çerçeve

### Karar İlkesi

Bu projede yeni bir teknoloji, kütüphane veya araç sisteme eklenmeden önce aşağıdaki temel soru değerlendirilir:

> **"Bu araç agent mantığını benim yerime soyutlayıp gizliyor mu, yoksa mevcut mimariyi güçlendiren bağımsız bir bileşen mi?"**

Bu soru, projedeki tüm teknik kararların temel değerlendirme kriteridir.

Eğer belirtilmeyen ve yeni eklenmiş  bir araç; agent planlama, routing, state yönetimi, tool calling, karar verme veya workflow orkestrasyonu gibi temel agent davranışlarını geliştiriciden gizliyor ve bu süreçleri kendi içinde otomatik olarak yönetiyorsa, bu proje kapsamında kullanılmamalıdır. Çünkü projenin temel amaçlarından biri, modern agent mimarilerinin nasıl çalıştığını doğrudan öğrenmek, geliştirmek ve gerektiğinde özelleştirebilmektir.

Fakat ; veri toplama, belge işleme, ayrıştırma, indeksleme, model entegrasyonu, değerlendirme, görselleştirme veya benzeri alanlarda çalışan ve agent karar mekanizmasına müdahale etmeyen bağımsız araçlar mimariyi güçlendiren bileşenler olarak değerlendirilir ve kullanılabilir.

Bu nedenle proje, **agent geliştirme katmanında kontrollü ve bilinçli bir teknoloji seçimi**, diğer katmanlarda ise **ihtiyaca göre en uygun aracın kullanılmasını** benimser.

Bu ilke yalnızca **agent orkestrasyon katmanı** için bağlayıcıdır. Veri edinme ve işleme katmanında araç seçimi kalite, performans ve bakım kolaylığı gibi mühendislik kriterlerine göre serbesttir. Model katmanında ise belirli bir sağlayıcıya bağımlılık oluşturulmaz; mimari mümkün olduğunca model bağımsız (provider-agnostic) tasarlanır.

### İhlal Durumunda Aksiyon

- Kod incelemesinde yasaklı bir kütüphane tespit edilirse, ilgili değişiklik onaylanmaz.
- Mevcut kodda tespit edilirse, izinli bir alternatifle değiştirilene kadar teknik borç olarak işaretlenir.