"""Arka planda FFmpeg indirme is parcacigi (arayuzu kilitlemez)."""
import logging

from PySide6.QtCore import QThread, Signal

from app.services.ffmpeg_downloader import FFmpegDownloadError, FFmpegDownloader


class FFmpegDownloadWorker(QThread):
    progress = Signal(int, str)   # (yuzde, mesaj)
    done = Signal(str)            # ffmpeg.exe yolu
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log = logging.getLogger("yt_ara.ffmpeg_download_worker")

    def run(self) -> None:
        downloader = FFmpegDownloader()
        try:
            path = downloader.download(progress_cb=self._on_progress)
        except FFmpegDownloadError as exc:
            self.log.warning("FFmpeg indirilemedi: %s", exc.detail)
            self.failed.emit(exc.user_message)
            return
        self.done.emit(path)

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress.emit(pct, msg)
