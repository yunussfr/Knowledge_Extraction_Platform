# 00 – Proje Vizyonu

## Ne?

Bu doküman, platformun neden var olduğunu, hangi problemi çözdüğünü ve hangi hedeflerin kapsam dışı olduğunu tanımlar.

## Neden?

Vizyon net olmadan mimari kararlar tutarsızlaşır. Bu doküman, sonraki tüm teknik kararlar için referans niyet beyanıdır.

## Nasıl?

### Problem Tanımı

Farklı bilgi alanlarına (kültür, tarih, hukuk, tıp, finans, eğitim, bilim, edebiyat vb.) özgü bilgi toplama, doğrulama ve yapılandırma işlemleri yapılır. Bu durum:

- kod tekrarına,
- tutarsız veri kalitesine,
- alanlar arası bilgi paylaşımının imkânsız hale gelmesine

yol açar.

### Hedef

Bu projenin temel amacı, belirli bir alana özel çalışan bir veri toplama aracı geliştirmek değil; farklı bilgi alanlarına uyarlanabilen, yeniden kullanılabilir ve konfigürasyon odaklı bir Bilgi Edinme Platformu (Knowledge Acquisition Platform) oluşturmaktır.

Platform, kullanıcı tarafından tanımlanan kurallar ve yapılandırmalar doğrultusunda farklı veri kaynaklarından bilgi toplayabilmeli, bu bilgileri analiz edebilmeli, temizleyebilmeli, doğrulayabilmeli, zenginleştirebilmeli ve standartlaştırılmış bir bilgi formatına dönüştürebilmelidir.

Oluşturulan bilgi yalnızca ham metin olarak saklanmayacak; kaynak bilgisi, metadata, varlıklar (entities), ilişkiler (relations), kalite değerlendirmeleri ve diğer yapısal bilgiler ile birlikte JSON tabanlı, makine tarafından işlenebilir bir bilgi nesnesi (Knowledge Object) olarak üretilecektir.

Platformun en önemli tasarım hedeflerinden biri, çekirdek mimariyi değiştirmeden yalnızca yapılandırma dosyaları, veri kaynakları ve şemalar değiştirilerek farklı bilgi alanlarında çalışabilmesidir. Böylece aynı altyapı;

Türk kültürü,
Osmanlı tarihi,
İslam düşüncesi,
hukuk,
tıp,
finans,
eğitim,
bilim,
edebiyat

gibi tamamen farklı alanlar için yeniden kullanılabilecektir.

Uzun vadede hedef; yüksek kaliteli veri kümeleri üretebilen, agent tabanlı iş akışlarını destekleyen, farklı yapay zekâ sistemleri tarafından doğrudan kullanılabilecek bilgi tabanları oluşturabilen ve Advanced RAG, Knowledge Graph, Agentic AI ve benzeri sistemlere güvenilir veri altyapısı sağlayan genel amaçlı bir bilgi edinme platformu geliştirmektir.
### Kapsam Dışı Hedefler

- Belirli bir bilgi alanına özel iş mantığının çekirdek mimariye gömülmesi.
- Kullanıcı arayüzü (UI/UX) geliştirme.
- Bilgiyi son kullanıcıya sunan bir uygulama katmanı inşa etmek (platform yalnızca yapılandırılmış çıktı üretir).
- Agent orkestrasyonunu gizleyen çerçevelerin kullanılması (bkz. `01_DEVELOPMENT_RULES`).

### Başarı Kriteri

Bir bilgi alanı, çekirdek koda dokunulmadan, yalnızca konfigürasyon dosyaları eklenerek/değiştirilerek platforma entegre edilebiliyorsa, vizyon karşılanmış sayılır.