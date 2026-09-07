# YouTube Gelişmiş Arama

Windows için basit, hızlı ve **portable** (kurulum gerektirmeyen) bir YouTube
gelişmiş video arama uygulaması.

## 1. Uygulama nedir?

YouTube üzerinde gelişmiş video araması yapmanızı sağlayan bir masaüstü
programıdır. Özellikleri:

- Bir veya birden fazla arama ifadesi ile video arama
- İsteğe bağlı tarih aralığı filtresi (GG.AA.YYYY, takvimden seçimli)
- İsteğe bağlı bir veya birden fazla kanal içinde arama
  (kanal adresini yapıştırmanız yeterli; kanal kimliği otomatik bulunur)
- Kanal girilmezse tüm YouTube üzerinde genel arama
- **API'siz arama** (yt-dlp): YouTube API anahtarı olmadan da arama yapabilir
  (Ayarlar → Arama Yöntemi)
- **Tam ifade filtresi**: arama ifadesini kelimelere bölmeden bütün olarak eşleştirir
- **Kanal tarama kapsamı**: son 100 / 500 / 1000 video veya tümü
- Sonuçları tabloda görüntüleme (başlık, kanal, tarih, video adresi)
- Sütun başlıklarına tıklayarak sıralama (tarih, başlık, kanal)
- Videoyu çift tıklayarak veya sağ tık menüsüyle tarayıcıda açma
- **Video indirme**: tek veya çoklu video, kalite seçimi, ilerleme çubuğu,
  indirme geçmişi (sağ tık → İndir)
- **Görüntü çıkarma**: videodan belirli zaman noktalarından veya aralıklarla
  kare çıkarma (JPG/PNG, FFmpeg ile)
- **Video bilgisi**: seçilen videonun kanal, süre, tarih, görüntülenme bilgisi
- **Seçilen** veya **tüm** video adreslerini tek tuşla panoya kopyalama
  (her adres ayrı satırda, temiz biçimde)
- TXT olarak dışa aktarma (tümünü veya kanala göre gruplandırarak)
- Açık / koyu tema (varsayılan: Windows temasını izler)
- Türkçe arayüz

## 2. Nasıl çalışır?

1. **Arama ifadesi** kutusuna aradığınız konuyu yazın (örn. `İstanbul depremi`).
   Yazdığınız ifade bütün olarak YouTube'a gönderilir; kelimelere bölünmez.
2. İsterseniz **Tarih Aralığı** kutusunu işaretleyip başlangıç ve bitiş
   tarihlerini seçin. İşaretlemezseniz tüm tarihlerde aranır.
3. İsterseniz **kanal adresleri** ekleyin (`+ Kanal Ekle` düğmesiyle).
   Desteklenen biçimler:
   - `https://www.youtube.com/@kanaladi`
   - `https://www.youtube.com/channel/UC...`
   - `https://www.youtube.com/c/kanaladi`
   - `https://www.youtube.com/user/kanaladi`

   Kanal eklemezseniz tüm YouTube'da aranır; kanal eklerseniz yalnızca o
   kanallarda aranır ve sonuçlar tek listede birleştirilir (mükerrer
   videolar gösterilmez).
4. **ARA** düğmesine basın. Sonuçlar listelenir. Arama sırasında
   **İptal** düğmesiyle işlemi durdurabilirsiniz.
5. Daha çok sonuç için **Daha Fazla Sonuç Getir** düğmesini kullanın.
   **Tüm Sonuçları Getir** seçeneği büyük aramalarda uzun sürebilir ve
   API kotanızı hızlı tüketebilir.
6. Sonuçlardan seçtiklerinizi veya tümünü **kopyalayın** ya da
   **TXT** olarak kaydedin.

## 3. YouTube API anahtarı nasıl alınır?

Uygulama resmi **YouTube Data API v3** kullanabilir ve sizin ücretsiz API
anahtarınıza ihtiyaç duyar (anahtar programa gömülü değildir; size aittir).
**API anahtarı olmadan da** yt-dlp tabanlı **API'siz** arama yapabilirsiniz
(Ayarlar → Arama Yöntemi → "API'siz"). API anahtarı girerseniz uygulama
varsayılan olarak API'yi kullanır; girmeseniz de arama çalışır.

API anahtarı almak isterseniz:

1. <https://console.cloud.google.com> adresine Google hesabınızla girin.
2. Üstten yeni bir **proje** oluşturun (örn. `youtube-arama`).
3. Sol menüden **API'ler ve Hizmetler → Kitaplık** bölümüne girin.
4. **YouTube Data API v3** öğesini bulun ve **Etkinleştir** deyin.
5. **Kimlik Bilgileri → Kimlik bilgisi oluştur → API anahtarı** yolunu izleyin.
6. Oluşan anahtarı kopyalayın.
7. Uygulamada **Ayarlar** düğmesine basıp anahtarı yapıştırın ve **Kaydet**
   deyin. İsterseniz **Anahtarı Sına** ile doğrulayabilirsiniz.

Notlar:

- Anahtarınız yalnızca kendi bilgisayarınızda, kullanıcı ayarlar
  klasöründe (`%LOCALAPPDATA%\YouTubeSearch\ayarlar.json`) saklanır.
  Kimseyle paylaşmayın.
- Google, API için günlük ücretsiz kota verir (varsayılan 10.000 birim).
  Bir arama sayfası 100 birim harcar; günlük yaklaşık 100 arama sayfası
  eder. Kota dolarsa uygulama sizi bilgilendirir ve kota ertesi gün yenilenir.
- **API'siz** yöntemde kota yoktur; ancak sonuçlar yt-dlp'nin erişebildiği
  sonuçlarla sınırlıdır ve sayfalama API kadar kapsamlı değildir.

## 3.1 Video indirme ve görüntü çıkarma

- **Video indirme**: Sonuç tablosunda bir veya birden fazla video seçin,
  sağ tıklayın ve **İndir** deyin. Kalite seçin (En İyi / 1080p / 720p /
  480p / En İyi Tek Dosya). İndirilen dosyalar varsayılan olarak
  `downloads/` klasörüne, kanal adına göre alt klasörlere kaydedilir.
  İndirme geçmişi `data/download_history.db` içinde tutulur.
- **Görüntü çıkarma**: Bir video seçip sağ tıklayın ve **Görüntü Çıkar**
  deyin. Belirli zaman noktalarından (örn. `00:30, 01:15`) veya belirli
  aralıklarla (örn. her 30 saniyede bir) kare çıkarabilirsiniz. JPG veya
  PNG formatı seçilebilir.
- **FFmpeg gereksinimi**: Video indirme (yüksek kaliteli video+ses
  birleştirme) ve görüntü çıkarma için **FFmpeg** gerekir. Program küçük
  kalması için FFmpeg'i önceden içermez; ilk ihtiyaç duyulduğunda
  (indirme penceresinde veya Ayarlar → FFmpeg → İndir) tek tıkla otomatik
  indirilir (~140 MB, bir kereliğine).

## 4. Uygulama nasıl kurulur?

**Python kurmanıza veya bilgisayarda yönetici (admin) yetkisine sahip
olmanıza gerek yoktur.** Kurulum tamamen kullanıcı klasörünüze yapılır.

1. [Releases](https://github.com/ismetuluer/yt-ara/releases/latest)
   sayfasından `YouTubeSearch.zip` dosyasını indirin.
2. Zip dosyasının içeriğini bir klasöre çıkarın (sağ tık → "Tümünü
   Çıkart").
3. Çıkan klasördeki **`Kur.bat`** dosyasına çift tıklayın.

`Kur.bat`:

- Program dosyalarını `Belgelerim\YouTubeSearch` klasörüne kopyalar,
- Gerekli çalışma ortamını (Python) ve kütüphaneleri (PySide6, requests,
  yt-dlp) internetten indirip aynı klasöre kurar (yönetici yetkisi
  gerektirmez, sisteminizdeki hiçbir şeyi değiştirmez),
- Masaüstünüze **"YouTube Arama"** kısayolu oluşturur,
- Kurulum bitince programı otomatik açar.

Zip dosyası bu sayede küçük kalır; ağır bağımlılıklar yalnızca sizin
bilgisayarınıza, ihtiyaç anında indirilir. FFmpeg de aynı mantıkla,
yalnızca gerektiğinde indirilir (yukarıya bakın).

Bir sonraki kullanımda **masaüstündeki kısayolu** kullanmanız yeterlidir;
`Kur.bat`'a tekrar ihtiyacınız yoktur (yalnızca onarım/yeniden kurulum
için tekrar çalıştırılabilir — mevcut kurulumu bozmadan dosyaları
günceller).

Uygulama güncellemelerini (Ayarlar → Uygulama Sürümü) ve yt-dlp
güncellemelerini (YouTube'un değişikliklerine karşı) kendisi GitHub
üzerinden denetler; kısayolu kullanmaya devam edebilirsiniz.

### Geliştiriciler için

Kaynak koddan doğrudan çalıştırmak isteyen geliştiriciler için `run.bat`
(sistemde kurulu Python 3.10+ gerektirir) ve tam bağımsız bir dağıtım
klasörü üretmek için `build_portable.bat` mevcuttur; son kullanıcılar
için önerilen yöntem her zaman yukarıdaki `Kur.bat`'tır.

## Sorun giderme

| Sorun | Çözüm |
|---|---|
| "API anahtarı geçersiz" | Ayarlar'dan anahtarı kontrol edin, sondaki boşlukları silin. |
| "Günlük kota doldu" | Ertesi gün tekrar deneyin, başka bir anahtar kullanın veya API'siz yönteme geçin. |
| "Kanal bulunamadı" | Kanal adresini tarayıcıdan kopyalayıp tam olarak yapıştırın. |
| "Bağlanılamadı" | İnternet bağlantınızı ve güvenlik duvarınızı kontrol edin. |
| Video indirilemiyor | FFmpeg gerekebilir: Ayarlar → FFmpeg → İndir. |
| "FFmpeg bulunamadı" | İndirme penceresinde "FFmpeg'i İndir" deyin ya da Ayarlar'dan indirin. |
| Program açılmıyor | `logs\uygulama.log` dosyasındaki son satırlara bakın. |

Teknik ayrıntılar her zaman `logs\uygulama.log` dosyasına yazılır.
