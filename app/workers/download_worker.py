"""Arka planda video indirme is parcacigi.

Birden fazla video ayni anda (es zamanli) indirilir. Her video kendi
DownloadService ornegini kullanir (iptal durumu paylasilmasin diye);
ilerleme, tamamlanan ve hata sinyalleri video basina yayilir.
"""
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QThread, Signal

from app.services.download_history import DownloadHistory
from app.services.download_service import DownloadError, DownloadService, sanitize_filename

# Ayarlar'dan bir deger gelmezse kullanilacak varsayilan.
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 3


class DownloadWorker(QThread):
    # (video_id, baslik, indirilen_byte, toplam_byte, hiz, kalan_sn, dosya_adi)
    progress = Signal(str, str, int, int, float, int, str)
    # (video_id, baslik, dosya_yolu)
    finished = Signal(str, str, str)
    # (video_id, baslik, hata_mesaji)
    failed = Signal(str, str, str)
    # (tamamlanan, toplam)
    all_done = Signal(int, int)
    # (su an aktif indirme sayisi)
    active_count_changed = Signal(int)

    def __init__(self, download_dir: str, quality: str, items: list[dict],
                 history: DownloadHistory | None = None, ffmpeg_path: str | None = None,
                 subtitles: bool = False, subtitle_langs: str = "tr,en",
                 max_concurrent: int = DEFAULT_MAX_CONCURRENT_DOWNLOADS,
                 speed_limit_kbps: int = 0, parent=None):
        """items: [{'video_id', 'title', 'url'}, ...]"""
        super().__init__(parent)
        self.download_dir = download_dir
        self.quality = quality
        self.ffmpeg_path = ffmpeg_path
        self.subtitles = subtitles
        self.subtitle_langs = subtitle_langs
        self.max_concurrent = max(1, int(max_concurrent or DEFAULT_MAX_CONCURRENT_DOWNLOADS))
        self.speed_limit_kbps = max(0, int(speed_limit_kbps or 0))
        self.items = items
        self.history = history
        self.log = logging.getLogger("yt_ara.dl_worker")
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._active_services: list[DownloadService] = []
        # Birden fazla kanaldan toplu indirmede dosyalarin karismamasi icin
        # her kanal kendi alt klasorune indirilir. Tek kanal/tek videoluk
        # indirmelerde gereksiz alt klasor olusturulmaz.
        channels = {item.get("channel_title") for item in items if item.get("channel_title")}
        self._organize_by_channel = len(channels) > 1

    def _item_dir(self, item: dict) -> str:
        if not self._organize_by_channel:
            return self.download_dir
        channel = item.get("channel_title") or "Bilinmeyen Kanal"
        return os.path.join(self.download_dir, sanitize_filename(channel))

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            services = list(self._active_services)
        for service in services:
            service.cancel()

    def run(self) -> None:
        total = len(self.items)
        counter = {"done": 0}
        counter_lock = threading.Lock()

        def work(item: dict) -> None:
            if self._cancel_event.is_set():
                return
            video_id = item.get("video_id", "")
            title = item.get("title", "")
            url = item.get("url", "")
            record_id = 0
            if self.history:
                record_id = self.history.add(title, url, None, "indiriliyor")
            target_dir = self._item_dir(item)
            os.makedirs(target_dir, exist_ok=True)
            service = DownloadService(
                target_dir, quality=self.quality, ffmpeg_path=self.ffmpeg_path,
                subtitles=self.subtitles, subtitle_langs=self.subtitle_langs,
                speed_limit_kbps=self.speed_limit_kbps)
            with self._lock:
                self._active_services.append(service)
                self.active_count_changed.emit(len(self._active_services))
            try:
                path = service.download(
                    url,
                    progress_cb=lambda info, vid=video_id, t=title: self._on_progress(vid, t, info))
                with counter_lock:
                    counter["done"] += 1
                if self.history and record_id:
                    self.history.update_status(record_id, "tamam", path)
                self.finished.emit(video_id, title, path)
            except DownloadError as exc:
                if self.history and record_id:
                    self.history.update_status(record_id, "hata")
                self.failed.emit(video_id, title, exc.user_message)
            except Exception:
                self.log.exception("Indirme parcacigi hatasi")
                if self.history and record_id:
                    self.history.update_status(record_id, "hata")
                self.failed.emit(video_id, title, "Beklenmeyen bir hata oluştu.")
            finally:
                with self._lock:
                    if service in self._active_services:
                        self._active_services.remove(service)
                    self.active_count_changed.emit(len(self._active_services))

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as pool:
            list(pool.map(work, self.items))
        self.all_done.emit(counter["done"], total)

    def _on_progress(self, video_id: str, title: str, info: dict) -> None:
        if self._cancel_event.is_set():
            return
        status = info.get("status")
        if status == "downloading":
            self.progress.emit(
                video_id, title,
                int(info.get("downloaded_bytes", 0)),
                int(info.get("total_bytes", 0)),
                float(info.get("speed", 0)),
                int(info.get("eta", 0)),
                str(info.get("filename", "")),
            )
