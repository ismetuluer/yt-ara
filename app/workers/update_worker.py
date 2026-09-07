"""Arka planda yt-dlp surum denetimi ve guncelleme is parcacigi.

Arayuzu kilitlemeden en son surumu denetler ve gerekiyorsa guncel
standalone yt-dlp.exe'yi indirir. auto=True iken (acilista otomatik
denetim) hatalar kullaniciya bildirilmez, yalnizca gunluge yazilir.
"""
import logging

from PySide6.QtCore import QThread, Signal

from app.services.ytdlp_updater import YtDlpUpdateError, YtDlpUpdater


class _Cancelled(Exception):
    """Iptal edilen indirmeyi urlretrieve'dan cikarmak icin."""


class YtDlpUpdateWorker(QThread):
    checked = Signal(str, str, bool)   # (kurulu_surum, en_son_surum, guncelleme_gerekli)
    progress = Signal(int, str)        # (yuzde, mesaj)
    updated = Signal(str)              # yeni surum
    up_to_date = Signal(str)           # kurulu surum
    failed = Signal(str)               # kullaniciya gosterilecek mesaj (yalniz manuel modda)

    def __init__(self, auto: bool = False, parent=None):
        super().__init__(parent)
        self.auto = auto
        self.log = logging.getLogger("yt_ara.update_worker")
        self._cancelled = False
        # Otomatik (sessiz) denetim kisa zaman asimi kullanir; boylece
        # uygulama kapatilirken bu is parcacigini beklemek uzun surmez.
        self.timeout = 8 if auto else 20

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        updater = YtDlpUpdater(timeout=self.timeout)
        try:
            current, latest, outdated = updater.compare()
        except YtDlpUpdateError as exc:
            if self.auto:
                self.log.info("Otomatik yt-dlp denetimi yapilamadi: %s", exc.detail)
            else:
                self.failed.emit(exc.user_message)
            return
        self.checked.emit(current, latest, outdated)
        if not outdated:
            self.up_to_date.emit(current)
            return
        try:
            updater.update(progress_cb=self._on_progress)
        except YtDlpUpdateError as exc:
            if self._cancelled:
                return
            self.log.warning("yt-dlp guncellenemedi: %s", exc.detail)
            if not self.auto:
                self.failed.emit(exc.user_message)
            return
        if not self._cancelled:
            self.updated.emit(latest)

    def _on_progress(self, pct: int, msg: str) -> None:
        if self._cancelled:
            raise _Cancelled()
        self.progress.emit(pct, msg)
