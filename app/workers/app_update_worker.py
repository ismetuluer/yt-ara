"""Arka planda uygulama surumu denetimi ve guncelleme indirme is parcacigi.

Arayuzu kilitlemeden GitHub Releases'i denetler; kullanici onaylarsa
guncellemeyi indirip degisim betigini hazirlar (betigi CALISTIRMAZ --
bu, MainWindow'un uygulamayi kapatmadan hemen once yapmasi gereken bir
adimdir, bkz. app_updater.launch_apply_script).
"""
import logging

from PySide6.QtCore import QThread, Signal

from app.services.app_updater import AppUpdateError, AppUpdater


class AppUpdateWorker(QThread):
    checked = Signal(str, str, bool, dict)  # (kurulu, en_son, guncelleme_var_mi, release)
    progress = Signal(int, str)             # (yuzde, mesaj)
    ready = Signal(str)                     # degisim betiginin yolu
    failed = Signal(str)

    def __init__(self, mode: str = "check", download_url: str = "",
                 auto: bool = False, parent=None):
        """mode: 'check' (yalnizca denetle) | 'download' (indirip hazirla)."""
        super().__init__(parent)
        self.mode = mode
        self.download_url = download_url
        self.auto = auto
        self.log = logging.getLogger("yt_ara.app_update_worker")
        self.timeout = 10 if auto else 20

    def run(self) -> None:
        updater = AppUpdater(timeout=self.timeout)
        if self.mode == "check":
            try:
                current, latest, outdated, release = updater.compare()
            except AppUpdateError as exc:
                if self.auto:
                    self.log.info("Otomatik surum denetimi yapilamadi: %s", exc.detail)
                else:
                    self.failed.emit(exc.user_message)
                return
            self.checked.emit(current, latest, outdated, release)
            return

        # mode == "download"
        try:
            script_path = updater.download_and_stage(
                self.download_url, progress_cb=self._on_progress)
        except AppUpdateError as exc:
            self.log.warning("Guncelleme hazirlanamadi: %s", exc.detail)
            self.failed.emit(exc.user_message)
            return
        self.ready.emit(script_path)

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress.emit(pct, msg)
