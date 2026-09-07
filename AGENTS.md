# AGENTS.md — YouTubeSearch Projesi

## 1. Proje amacı

Bu proje Windows üzerinde çalışan, Python + PySide6 tabanlı, sade ve portable bir YouTube arama ve video indirme masaüstü uygulamasıdır.

Ana hedefler:

- Basit ve hızlı Windows arayüzü
- Türkçe kullanıcı arayüzü
- Windows 10/11 uyumu
- Portable çalışma
- API'siz YouTube araması için yt-dlp
- İsteğe bağlı YouTube Data API v3 desteği
- Video indirme
- FFmpeg ile video/ses işlemleri
- Videodan belirli zamanlarda kare/görüntü çıkarma

Kullanıcı programlama bilmiyor. Bu nedenle geliştirme sırasında teknik kararları ajan vermeli, kullanıcıyı gereksiz teknik ayrıntılarla uğraştırmamalı ve çalışan özellikler gereksiz yere yeniden yazılmamalıdır.

---

## 2. Proje teknolojileri

Mevcut teknoloji:

- Python
- PySide6 / Qt6
- requests
- yt-dlp
- FFmpeg
- YouTube Data API v3
- PyInstaller

Portable EXE oluşturulmaktadır.

---

## 3. Daha önce tamamlanmış temel özellikler

Mevcut projede daha önce şu özellikler oluşturulmuştur:

- YouTube video araması
- YouTube Data API v3 ile arama
- API'siz arama / yt-dlp
- Tarih aralığı filtresi
- Takvimden tarih seçme
- Kanal URL'si ile arama
- Birden fazla kanal ile arama
- Kanal URL'sinden kanal ID çözümleme
- Sonuçların listelenmesi
- Sonuçların tarihe göre sıralanması
- Video URL'lerini kopyalama
- Seçilen URL'leri kopyalama
- TXT dışa aktarma
- CSV dışa aktarma
- Sayfalama
- Sonuçlarda mükerrer video temizleme
- Arama önbelleği
- Arka planda QThread worker
- Arama iptali
- Türkçe hata mesajları
- Log sistemi
- Ayarlar penceresi
- Sistem / Açık / Koyu tema
- Portable çalışma
- yt-dlp ile video indirme
- Video kalite seçimi
- FFmpeg entegrasyonu
- Video/ses birleştirme
- Videodan belirli zamanlarda görüntü/kare çıkarma

Bu listeyi varsayım olarak kabul etme. Projeyi inceleyerek gerçek durumu doğrula.

---

# 4. BU GÖREVİN BAŞLANGIÇ NOKTASI

Proje daha önce başka bir AI ajanı tarafından tamamlanmıştı.

Daha sonra kullanıcı iki yeni değişiklik istedi:

1. YouTube değişiklikleri nedeniyle yt-dlp gerektiğinde otomatik ve manuel güncellenebilsin.
2. Tarih aralığı artık her zaman aktif olsun; ayrıca tarih filtresini açıp kapatan onay kutusu olmasın.

Önceki AI ajanının kredisi bitmiş ve çalışma test/syntax doğrulaması aşamasında yarım kalmıştır.

Bu nedenle:

**BU BİR SIFIRDAN GELİŞTİRME GÖREVİ DEĞİLDİR.**

Mevcut projeyi devral, yarım kalan değişiklikleri incele ve tamamla.

---

# 5. ÖNCE MEVCUT KODU İNCELE

Kod değiştirmeden önce proje yapısını incele.

Özellikle şu dosya ve klasörleri kontrol et:

- `ytdlp_updater.py`
- `update_worker.py`
- `main.py`
- Ayarlar servisi
- Ayarlar penceresi
- yt-dlp arama servisi
- Video indirme servisi
- Worker sınıfları
- `tools/`
- `config/`
- `logs/`
- `tests/`
- `.gitignore`
- PyInstaller/build dosyaları

Ayrıca tüm projede `yt-dlp` kullanımını ara.

Özellikle şu soruya kesin cevap bul:

**Uygulama gerçekte yt-dlp'yi nereden çalıştırıyor?**

Olasılıklar:

- Python modülü
- Harici `yt-dlp.exe`
- İkisi birden
- Kullanım yerine göre farklı kaynak

Bu konu netleşmeden updater mimarisini yeniden yazma.

---

# 6. ÖNCEKİ AJANIN YAPTIĞI DEĞİŞİKLİKLER

Önceki ajan aşağıdaki işlemleri yapmaya başlamıştı:

- `ytdlp_updater.py` mevcut olduğu tespit edildi.
- Updater'ın uygulamaya tam bağlanmadığı tespit edildi.
- `ytdlp_updater.py` üzerinde değişiklik yapıldı.
- Kurulu sürüm tespitinin hem gömülü Python modülünü hem de harici EXE'yi dikkate alması amaçlandı.
- Güncelleme sonrasında eski EXE sürüm cache'inin sıfırlanması için değişiklik yapıldı.
- `update_worker.py` oluşturuldu.
- Ayarlar servisine otomatik güncelleme kontrolünün son tarihini tutacak alan eklendi.
- Otomatik kontrolün günde bir kez yapılması amaçlandı.
- Ayarlar penceresine manuel yt-dlp güncelleme bölümü eklenmeye başlandı.
- Güncelleme event/handler bağlantıları ve pencere kapanış koruması eklenmeye başlandı.
- `.gitignore` içine indirilen yt-dlp EXE'si eklenmeye başlandı.
- Son olarak testler ve syntax kontrolleri çalıştırılacaktı.
- Ancak kredi bittiği için doğrulama tamamlanamadı.

Bu değişiklikleri silme.

Önce gerçekten ne durumda olduklarını kontrol et.

---

# 7. ANA GÖREV: YT-DLP GÜNCELLEME SİSTEMİ

Amaç:

YouTube değişiklikleri nedeniyle eski yt-dlp çalışamaz hale geldiğinde kullanıcı uygulamanın tamamını yeniden kurmak zorunda kalmadan yt-dlp bileşenini güncelleyebilsin.

İki yöntem bulunmalıdır:

## A. Otomatik güncelleme kontrolü

Uygulama yt-dlp güncellemesini otomatik olarak kontrol edebilmelidir.

Ancak her açılışta gereksiz internet isteği yapılmamalıdır.

Hedef:

- En fazla günde bir otomatik kontrol.
- Son kontrol tarihi ayarlarda tutulmalı.
- UI kilitlenmemeli.
- Güncel ise kullanıcı gereksiz popup ile rahatsız edilmemeli.
- Yeni sürüm varsa anlaşılır biçimde bildirilmeli.

Otomatik kontrol arka planda yapılmalıdır.

---

# 8. OTOMATİK GÜNCELLEME DAVRANIŞI

Uygulama açılırken:

- Ana pencerenin açılmasını bekletme.
- Güncelleme kontrolünü arka planda yap.
- Kullanıcı uygulamayı kullanmaya devam edebilsin.
- Son kontrol tarihini kontrol et.
- 24 saat geçmediyse tekrar kontrol etme.

Yeni sürüm bulunduğunda kullanıcıya:

`Yeni bir yt-dlp sürümü mevcut.`

gibi sade bir mesaj gösterilebilir.

Güncellemenin otomatik olarak uygulanması gerekiyorsa mevcut tasarımı ve güvenliği dikkate al.

Kullanıcının dosyalarını bozacak agresif otomatik güncelleme davranışı oluşturma.

---

# 9. MANUEL GÜNCELLEME

Ayarlar ekranında yt-dlp için manuel kontrol/güncelleme bölümü bulunmalıdır.

Örneğin:

```text
yt-dlp

Mevcut sürüm: 2026.xx.xx

[ Güncellemeleri Denetle ]
```

Yeni sürüm varsa:

```text
Yeni sürüm: 2026.xx.xx

[ Güncelle ]
```

Güncelse:

```text
yt-dlp güncel.
```

Gerçek sürüm gösterilmelidir.

Mock değer kullanma.

---

# 10. EN KRİTİK KONU: ETKİN YT-DLP KAYNAĞI

Updater'ın bir yt-dlp dosyasını güncellemesi tek başına yeterli değildir.

Aşağıdaki zincirin gerçekten çalıştığını doğrula:

```text
Updater
   ↓
Güncellenen yt-dlp
   ↓
Search Service
   ↓
Güncel yt-dlp
```

ve:

```text
Updater
   ↓
Güncellenen yt-dlp
   ↓
Download Service
   ↓
Güncel yt-dlp
```

Örneğin updater:

`tools/yt-dlp/yt-dlp.exe`

dosyasını güncelliyor fakat indirme servisi eski Python modülünü kullanıyorsa sistem hatalıdır.

Tam tersine Python modülü güncelleniyor fakat indirme servisi eski EXE'yi kullanıyorsa yine hatalıdır.

Bu nedenle uygulamada tek bir **etkin yt-dlp kaynağı** belirlenmeli veya mevcut mimariye uygun şekilde hangi kaynağın etkin olduğu açıkça yönetilmelidir.

---

# 11. YT-DLP GÜNCELLEMEDE GÜVENLİ DOSYA DEĞİŞİMİ

Windows'ta çalışan EXE'nin üzerine doğrudan yazmak sorun çıkarabilir.

Mümkün olduğunca şu yaklaşımı kullan:

1. Yeni dosyayı geçici dosyaya indir.
2. İndirmenin tamamlandığını doğrula.
3. Dosyanın geçerli olduğunu kontrol et.
4. Mümkünse sürümünü doğrula.
5. Eski dosyayı güvenli şekilde yeni dosyayla değiştir.
6. Başarısız olursa eski çalışan sürümü koru.
7. Geçici dosyaları temizle.

Yarım indirilmiş bir dosya etkin yt-dlp olarak bırakılmamalıdır.

---

# 12. GÜNCELLEME SONRASI DOĞRULAMA

Güncelleme başarılı kabul edilmeden önce:

- Etkin yt-dlp sürümünü tekrar oku.
- Yeni sürüm gerçekten çalıştırılabiliyor mu kontrol et.
- UI sürüm bilgisini yenile.
- Sürüm cache'ini temizle/güncelle.

Sadece "dosya indirildi" sonucunu başarılı güncelleme kabul etme.

---

# 13. AĞ VE GÜNCELLEME HATALARI

Güncelleme başarısız olursa:

- Eski çalışan sürüm korunmalı.
- Uygulama çalışmaya devam etmeli.
- Kullanıcıya Türkçe ve sade hata mesajı gösterilmeli.
- Teknik hata log dosyasına yazılmalı.

Örnek:

`yt-dlp güncellenemedi. İnternet bağlantınızı kontrol edip tekrar deneyebilirsiniz.`

Ham traceback'i ana kullanıcı arayüzüne basma.

---

# 14. ARAMA SERVİSİ

API'siz arama yt-dlp kullanıyorsa güncel etkin yt-dlp kaynağını kullanmalıdır.

Kontrol et:

```text
YtdlpSearchService
        ↓
Etkin yt-dlp
```

Updater'dan sonra gerçekten yeni sürüm kullanılmalı.

---

# 15. İNDİRME SERVİSİ

Video indirme sırasında hangi yt-dlp kaynağının kullanıldığını kesin olarak tespit et.

Kontrol et:

```text
DownloadService
        ↓
Etkin yt-dlp
```

Updater'ın güncellediği kaynak kullanılmalıdır.

---

# 16. API MODU KORUNMALI

YouTube Data API v3 desteğini kaldırma.

API anahtarı ile çalışan mevcut arama korunmalı.

API'siz yt-dlp modu da korunmalı.

---

# 17. TARİH ARALIĞI — ZORUNLU

Kullanıcının yeni talebi:

**Tarih aralığı her zaman aktif olacak.**

Mevcut:

`Tarih aralığını kullan`

veya benzeri checkbox varsa kaldır.

Başlangıç tarihi ve bitiş tarihi her zaman görünür olmalı.

Takvim seçici korunmalı.

Elle giriş korunmalı.

Tarih filtresini açıp kapatma özelliği olmamalıdır.

---

# 18. TARİH ARALIĞI UYGULAMASI

Her aramada:

- Başlangıç tarihi
- Bitiş tarihi

kullanılmalıdır.

Hem:

- API araması
- API'siz / yt-dlp araması
- Kanal araması

aynı tarih anlamını kullanmalıdır.

---

# 19. TARİH DOĞRULAMA

Kesinlikle korunmalı:

- Başlangıç tarihi > bitiş tarihi olamaz.
- Geçersiz tarih kabul edilmemeli.
- Takvim ve elle giriş aynı doğrulamayı kullanmalı.
- Tarih filtresi gerçekten arama sonucuna uygulanmalı.
- Saat dilimi kaynaklı günlük kaymalara dikkat edilmeli.

---

# 20. TARİH VARSAYILANI

Mevcut uygulamadaki tarih varsayılanını incele.

Mantıklı bir başlangıç/bitiş tarihi kullan.

Tarih alanları boş bırakılarak filtresiz arama yapılmasına izin verme.

Eğer mevcut projede kullanıcı deneyimini sağlayan mantıklı bir varsayılan varsa onu koru.

---

# 21. UI

Mevcut sade Windows görünümünü koru.

Yeni tasarım oluşturma.

Yalnızca gerekli değişiklikleri yap:

- Tarih checkbox'ını kaldır.
- Tarih alanlarını sürekli aktif tut.
- yt-dlp güncelleme bölümünü tamamla.

---

# 22. THREAD / WORKER

Güncelleme işlemleri UI thread'inde çalışmamalıdır.

Mevcut `update_worker.py` dosyasını kullan veya gerekiyorsa düzelt.

Şunlar UI'yi kilitlememelidir:

- Güncelleme kontrolü
- Güncelleme indirmesi
- yt-dlp sürüm kontrolü
- YouTube araması
- Video indirme
- FFmpeg işlemleri

---

# 23. UYGULAMA KAPANIŞI

Önceki ajanın eklediği kapanış korumasını kontrol et.

Şu tip hatalar olmamalı:

```text
QThread: Destroyed while thread is still running
```

Update worker çalışırken uygulama kapanırsa thread düzgün temizlenmeli.

Yarım güncelleme dosyası bırakılmamalı.

---

# 24. PORTABLE

Portable çalışma kesinlikle korunmalıdır.

Registry kullanma.

PATH değiştirme.

Sistem geneline kurulum yapma.

Mevcut portable klasör yapısını koru.

Örneğin:

```text
config/
data/
logs/
downloads/
tools/
```

Mevcut projedeki gerçek klasör yapısı esas alınmalıdır.

---

# 25. PYINSTALLER

Sadece Python geliştirme ortamında çalışması yeterli değildir.

Portable EXE oluşturulduğunda da:

- yt-dlp
- updater
- FFmpeg
- config
- logs
- downloads

doğru çalışmalıdır.

PyInstaller build dosyasını kontrol et.

---

# 26. FFmpeg

FFmpeg güncelleme sistemi bu görevin parçası değildir.

FFmpeg'i gereksiz yere değiştirme.

Yalnızca yt-dlp updater değişikliklerinin FFmpeg yollarını bozmadığını kontrol et.

---

# 27. TESTLER

Önce mevcut testleri çalıştır.

Sonra gerekli yeni testleri ekle.

## Updater

Test et:

- mevcut sürüm tespiti
- güncel sürüm
- yeni sürüm
- güncelleme kontrolü
- başarısız network
- başarısız download
- geçici dosya
- eski dosyanın korunması
- güncelleme sonrası sürüm doğrulaması

## Ayarlar

Test et:

- son kontrol tarihi
- kaydetme
- yeniden yükleme
- eski config ile uyumluluk

## Tarih

Test et:

- başlangıç tarihi
- bitiş tarihi
- başlangıç > bitiş
- checkbox'ın kaldırılması
- tarih filtresinin zorunlu olması
- API modunda tarih filtresi
- yt-dlp modunda tarih filtresi

## Entegrasyon

Özellikle:

```text
Updater → Search
Updater → Download
```

zincirlerini doğrula.

---

# 28. GERÇEK TEST

Mümkünse canlı yt-dlp/YouTube testi yap.

Sıra:

1. Mevcut yt-dlp sürümünü oku.
2. Güncelleme kontrolü yap.
3. Yeni sürüm varsa güncelle.
4. Yeni sürümü tekrar oku.
5. API'siz arama yap.
6. Bir video metadata'sı al.
7. Uygun bir test videosunu indir.
8. Dosyanın oluştuğunu ve açılabilir olduğunu kontrol et.

Gerçek test yapılamadıysa bunu açıkça belirt.

Mock testleri canlı test gibi raporlama.

---

# 29. LOG

Şu olayları logla:

- Güncelleme kontrolü başladı.
- Mevcut sürüm.
- Uzak sürüm.
- Yeni sürüm bulundu.
- Güncelleme başladı.
- Güncelleme tamamlandı.
- Güncelleme hatası.

API anahtarı gibi hassas bilgileri loglama.

---

# 30. CONFIG GERİYE DÖNÜK UYUMLULUK

Yeni ayar alanları eski config dosyalarında bulunmayabilir.

Bu durumda güvenli varsayılanlar kullan.

Eski config dosyalarını bozulmuş kabul edip kullanıcıyı zor durumda bırakma.

---

# 31. KOD KALİTESİ

Mevcut mimariyi koru.

Yeni kod:

- modüler
- test edilebilir
- mümkün olduğunca type hint kullanan
- hata yönetimi düzgün
- gereksiz global state kullanmayan

bir yapıda olmalı.

Çalışan kodu yalnızca stil amacıyla yeniden yazma.

---

# 32. ÇALIŞMA SIRASI

Şu sırayı takip et:

### Aşama 1
Projeyi ve yarım kalan değişiklikleri incele.

### Aşama 2
Syntax ve mevcut test durumunu tespit et.

### Aşama 3
Yt-dlp updater bağlantılarını tamamla.

### Aşama 4
Manuel güncelleme UI'sını tamamla.

### Aşama 5
Otomatik günlük kontrolü tamamla.

### Aşama 6
Search ve Download servislerinin etkin yt-dlp kaynağını doğrula.

### Aşama 7
Tarih checkbox'ını kaldır ve tarih aralığını zorunlu hale getir.

### Aşama 8
Testleri güncelle.

### Aşama 9
Gerçek testleri yap.

### Aşama 10
Portable EXE build et ve test et.

---

# 33. İLK RAPOR

İlk inceleme sonunda kısa bir durum raporu ver:

## Mevcut durum

- Updater:
- Update worker:
- Ayarlar:
- Search service:
- Download service:
- Tarih filtresi:
- Build:
- Testler:

## En önemli bulgu

Özellikle updater'ın güncellediği yt-dlp ile search/download servislerinin kullandığı yt-dlp'nin aynı olup olmadığını belirt.

Ardından uygulamaya devam et.

---

# 34. YAPILMAMASI GEREKENLER

- Projeyi sıfırdan yazma.
- Çalışan özellikleri silme.
- API sistemini kaldırma.
- yt-dlp updater'ı yalnızca görsel bir buton olarak bırakma.
- Test etmeden "çalışıyor" deme.
- Tarih filtresini tekrar opsiyonel yapma.
- Tarih checkbox'ı ekleme.
- Kullanıcıyı terminale yönlendirme.
- Registry kullanma.
- Sistem PATH'ini değiştirme.
- API anahtarını kaynak koda yazma.
- Gerçek test yapılmadıysa yapılmış gibi raporlama.
- FFmpeg'i gereksiz yere değiştirme.
- Mevcut çalışan mimariyi gereksiz yere yeniden yazma.

---

# 35. TAMAMLANMA KRİTERLERİ

Görev ancak aşağıdakiler sağlandığında tamamlanmış kabul edilir:

- [ ] Proje syntax kontrolünden geçiyor.
- [ ] Mevcut testler geçiyor.
- [ ] Yeni updater testleri geçiyor.
- [ ] Yeni tarih testleri geçiyor.
- [ ] yt-dlp sürümü doğru gösteriliyor.
- [ ] Manuel güncelleme gerçekten çalışıyor.
- [ ] Otomatik günlük kontrol çalışıyor.
- [ ] Güncelleme sonrası yeni yt-dlp gerçekten kullanılıyor.
- [ ] API'siz arama güncel yt-dlp'yi kullanıyor.
- [ ] Video indirme güncel yt-dlp'yi kullanıyor.
- [ ] Tarih aralığı her zaman aktif.
- [ ] Tarih checkbox'ı yok.
- [ ] Tarih doğrulaması çalışıyor.
- [ ] Güncelleme UI'yi kilitlemiyor.
- [ ] Uygulama kapanırken worker/thread hatası yok.
- [ ] Portable yapı çalışıyor.
- [ ] FFmpeg çalışmaya devam ediyor.
- [ ] Portable EXE build ediliyor.
- [ ] Portable EXE test edildi.
- [ ] Gerçek testler mümkün olduğunca yapıldı.
- [ ] Bilinen sınırlamalar açıkça raporlandı.

---

# 36. SON RAPOR FORMATI

İş bittiğinde şu formatta rapor ver:

## 1. Başlangıçta ne buldun?

Yarım kalmış değişiklikler nelerdi?

## 2. Hangi dosyaları değiştirdin?

Dosya dosya listele ve kısa açıklama yap.

## 3. yt-dlp güncelleme

- Mevcut sürüm nasıl bulunuyor?
- Güncelleme nasıl kontrol ediliyor?
- Otomatik kontrol ne sıklıkta?
- Manuel güncelleme nasıl çalışıyor?
- Güncelleme sonrası gerçekten yeni sürüm kullanılıyor mu?

## 4. Etkin yt-dlp kaynağı

Açıkça belirt:

```text
Arama:
...

İndirme:
...

Güncellemenin hedeflediği kaynak:
...
```

Bunların aynı olduğundan emin ol.

## 5. Tarih sistemi

- Checkbox kaldırıldı mı?
- Tarih zorunlu mu?
- API modunda çalışıyor mu?
- yt-dlp modunda çalışıyor mu?

## 6. Testler

Toplam / başarılı / başarısız sayılarını ver.

## 7. Gerçek testler

Gerçek YouTube/yt-dlp testi yapıldı mı?

Hangi işlemler denendi?

## 8. Portable EXE

Gerçek EXE konumunu belirt.

## 9. Bilinen sınırlamalar

Varsa açıkça yaz.

---

# 37. EN ÖNEMLİ TALİMAT

Bu belge bir "sıfırdan proje geliştirme promptu" değildir.

Bu proje daha önce tamamlanmıştır.

Görevin:

**mevcut projeyi devralmak, yarım kalmış değişiklikleri tamamlamak, test etmek ve çalışan portable uygulama üretmektir.**

Özellikle şu zincirin doğru olmasını sağla:

```text
             ┌── Search
             │
Updater ─────┼── Download
             │
             └── Metadata
```

ve:

```text
Başlangıç tarihi
       +
Bitiş tarihi
       ↓
Her aramada zorunlu tarih filtresi
```

Hedef:

**Kullanıcı API anahtarı olmadan da uygulamayı kullanabilmeli ve yt-dlp gerektiğinde uygulama içinden güncellenebilmelidir.**

Uygulama hızlı, sade, Windows uyumlu ve portable kalmalıdır.
