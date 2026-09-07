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
            urllib.request.urlretrieve(
                _DOWNLOAD_URL, zip_path, reporthook=self._make_hook(progress_cb))
        except Exception as exc:
            self.log.warning("FFmpeg indirilemedi: %s", exc)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise FFmpegDownloadError(
                "FFmpeg indirilemedi. İnternet bağlantınızı kontrol edin.",
                str(exc),
            ) from exc
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

    @staticmethod
    def _make_hook(progress_cb):
        def hook(count, block_size, total_size):
            if total_size > 0:
                pct = min(100, int(count * block_size * 100 / total_size))
            else:
                pct = 0
            progress_cb(pct, f"İndiriliyor... %{pct}")
        return hook
