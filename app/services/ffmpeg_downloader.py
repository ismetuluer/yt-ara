"""FFmpeg'i talep uzerine indirir.

Artik portable dagitimda FFmpeg onceden paketlenmiyor (dagitim boyutunu
kucuk tutmak icin); bunun yerine, gerektiginde (indirme/kare cikarma
sirasinda FFmpeg bulunamazsa ya da Ayarlar'dan elle) BtbN'in GitHub
Releases'inden guncel bir Windows derlemesi indirilip `tools/ffmpeg/`
icine acilir. yt-dlp toplulugunda yaygin/guvenilir bir kaynaktir.
"""
import logging
import os
import shutil
import socket
import tempfile
import urllib.request
import zipfile

from app.utils.paths import ffmpeg_dir

_DOWNLOAD_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-gpl.zip"
)


class FFmpegDownloadError(Exception):
    """Kullaniciya gosterilecek Turkce mesaj + teknik ayrinti tasir."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class FFmpegDownloader:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.log = logging.getLogger("yt_ara.ffmpeg_downloader")

    def download(self, progress_cb=None) -> str:
        """FFmpeg'i indirip tools/ffmpeg/ icine acar. ffmpeg.exe yolunu dondurur."""
        if progress_cb is None:
            progress_cb = lambda pct, msg: None
        tmp_dir = tempfile.mkdtemp(prefix="yt_ara_ffmpeg_")
        zip_path = os.path.join(tmp_dir, "ffmpeg.zip")
        progress_cb(0, "İndiriliyor...")
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout)
        try:
            self._download_with_progress(zip_path, progress_cb)
        except Exception as exc:
            self.log.warning("FFmpeg indirilemedi: %s", exc)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise FFmpegDownloadError(self._user_message_for(exc), str(exc)) from exc
        finally:
            socket.setdefaulttimeout(previous_timeout)

        progress_cb(100, "Çıkarılıyor...")
        try:
            dest = self._extract(zip_path, tmp_dir)
        except (zipfile.BadZipFile, FFmpegDownloadError) as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if isinstance(exc, FFmpegDownloadError):
                raise
            raise FFmpegDownloadError(
                "İndirilen FFmpeg dosyası bozuk. Lütfen tekrar deneyin.", str(exc),
            ) from exc
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return dest

    def _download_with_progress(self, zip_path: str, progress_cb) -> None:
        """urlretrieve yerine: GitHub'in bazi aglarda/kurumsal proxy'lerde
        varsayilan Python User-Agent'ini engelleyip 403 dondurmesini
        onlemek icin ozel bir User-Agent baslikli istek kullanir (bkz.
        app_updater.py / ytdlp_updater.py'deki ayni yaklasim)."""
        req = urllib.request.Request(_DOWNLOAD_URL, headers={"User-Agent": "yt-ara"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 64)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    pct = min(100, int(downloaded * 100 / total)) if total > 0 else 0
                    progress_cb(pct, f"İndiriliyor... %{pct}")

    @staticmethod
    def _user_message_for(exc: Exception) -> str:
        """Hatayi olabildigince dogru Turkce mesaja cevirir; her hatayi
        korulen 'internet baglantinizi kontrol edin' mesajiyla ortmez --
        ozellikle sunucu tarafi (403/404 gibi) veya sertifika hatalarinda
        yanlis yonlendirme yapmamak icin."""
        msg = str(exc)
        low = msg.lower()
        if "403" in msg:
            return ("FFmpeg indirilemedi (sunucu erişimi reddetti - HTTP 403). "
                     "Güvenlik duvarınız veya kurumsal ağ filtreniz GitHub'a "
                     "erişimi engelliyor olabilir.")
        if "404" in msg:
            return "FFmpeg indirilemedi (dosya bulunamadı - HTTP 404). Lütfen tekrar deneyin."
        if "certificate" in low or "ssl" in low:
            return ("FFmpeg indirilemedi (güvenli bağlantı/sertifika hatası). "
                     "Antivirüs programınızın SSL taramasını veya sistem saatinizin "
                     "doğru olduğunu kontrol edin.")
        if "timed out" in low or "timeout" in low:
            return "FFmpeg indirilemedi (bağlantı zaman aşımına uğradı). Lütfen tekrar deneyin."
        return "FFmpeg indirilemedi. İnternet bağlantınızı kontrol edin."

    def _extract(self, zip_path: str, tmp_dir: str) -> str:
        extract_dir = os.path.join(tmp_dir, "extracted")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        # BtbN derlemesi tek bir ust klasor icinde bin/ffmpeg.exe, bin/ffprobe.exe verir.
        ffmpeg_src = ffprobe_src = None
        for root, _dirs, files in os.walk(extract_dir):
            if "ffmpeg.exe" in files:
                ffmpeg_src = os.path.join(root, "ffmpeg.exe")
            if "ffprobe.exe" in files:
                ffprobe_src = os.path.join(root, "ffprobe.exe")
        if not ffmpeg_src:
            raise FFmpegDownloadError(
                "İndirilen pakette ffmpeg.exe bulunamadı.", str(os.listdir(extract_dir)))

        target_dir = ffmpeg_dir()
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, "ffmpeg.exe")
        shutil.copy2(ffmpeg_src, dest)
        if ffprobe_src:
            shutil.copy2(ffprobe_src, os.path.join(target_dir, "ffprobe.exe"))
        return dest
