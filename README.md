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
- TXT ve CSV (Excel uyumlu, Türkçe karakter destekli) dışa aktarma
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
   **TXT / CSV** olarak kaydedin.

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

- Anahtarınız yalnızca kendi bilgisayarınızda, uygulama klasöründeki
  `config/ayarlar.json` dosyasında saklanır. Kimseyle paylaşmayın.
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
  birleştirme) ve görüntü çıkarma için **FFmpeg** gerekir. Uygulama önce
  `tools/ffmpeg/` klasörüne bakar, sonra sistem PATH'ine. FFmpeg'i
  <https://www.gyan.dev/ffmpeg/builds/> adresinden indirip `ffmpeg.exe` ve
  `ffprobe.exe` dosyalarını `tools/ffmpeg/` klasörüne koyabilirsiniz.

## 4. Uygulama nasıl çalıştırılır?

### A) Portable EXE ile (önerilen — Python gerekmez)

1. `portable\YouTubeSearch` klasörünü istediğiniz yere kopyalayın.
2. `YouTubeSearch.exe` dosyasına çift tıklayın. Kurulum gerekmez.
3. İlk açılış birkaç saniye sürebilir (tek dosyalı EXE kendini hazırlar).

### B) Kaynak koddan çalıştırma (geliştiriciler için)

Gereksinim: Python 3.10 veya üzeri.

```bat
run.bat
```

`run.bat` gerekli kütüphaneleri otomatik kurar ve uygulamayı başlatır.

## 5. Portable EXE nasıl oluşturulur?

1. Proje klasöründe `build.bat` dosyasına çift tıklayın.
2. İşlem bitince `portable\YouTubeSearch\` klasörü oluşur:
   ```
   YouTubeSearch/
   ├── YouTubeSearch.exe
   ├── data/
   ├── config/
   ├── logs/
   ├── downloads/
   └── tools/ffmpeg/   (isteğe bağlı: ffmpeg.exe, ffprobe.exe)
   ```
3. Bu klasörü olduğu gibi USB belleğe veya başka bir bilgisayara
   kopyalayıp kullanabilirsiniz. Ayarlar ve loglar klasörün içinde tutulur;
   Windows kayıt defteri (Registry) kullanılmaz.

## Sorun giderme

| Sorun | Çözüm |
|---|---|
| "API anahtarı geçersiz" | Ayarlar'dan anahtarı kontrol edin, sondaki boşlukları silin. |
| "Günlük kota doldu" | Ertesi gün tekrar deneyin, başka bir anahtar kullanın veya API'siz yönteme geçin. |
| "Kanal bulunamadı" | Kanal adresini tarayıcıdan kopyalayıp tam olarak yapıştırın. |
| "Bağlanılamadı" | İnternet bağlantınızı ve güvenlik duvarınızı kontrol edin. |
| Video indirilemiyor | FFmpeg'in kurulu olduğundan emin olun (tools/ffmpeg/ veya PATH). |
| "FFmpeg bulunamadı" | FFmpeg'i indirip tools/ffmpeg/ klasörüne koyun. |
| Program açılmıyor | `logs\uygulama.log` dosyasındaki son satırlara bakın. |

Teknik ayrıntılar her zaman `logs\uygulama.log` dosyasına yazılır.
