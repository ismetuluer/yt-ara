"""Yeni surum bulundugunda acilan guncelleme penceresi.

Onceden yeni surum yalnizca durum cubugunda duyuruluyor, gercek
guncelleme icin kullanicinin Ayarlar'a gitmesi gerekiyordu. Bu pencere
guncellemeyi bulundugu yerde, tek tikla yapilabilir hale getirir.
"""
import logging

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout,
)

from app.services.app_updater import AppUpdater
from app.ui.theme import ACCENT_BUTTON_OBJECT_NAME, sync_titlebar
from app.workers.app_update_worker import AppUpdateWorker


class UpdateDialog(QDialog):
    """Yeni surumu duyurur ve "Şimdi güncelle" ile dogrudan uygular.

    Kullanici "Bu sürümü atla" derse `skipped_version` bu surumu tutar;
    cagiran taraf bunu ayarlara yazip bir daha sormaz.
    """

    def __init__(self, current: str, latest: str, release: dict, parent=None):
        super().__init__(parent)
        self.current = current
        self.latest = latest
        self.release = release
        self.skipped_version = ""
        self.log = logging.getLogger("yt_ara.update_dialog")
        self._worker: AppUpdateWorker | None = None

        self.setWindowTitle("Güncelleme var")
        self.setMinimumWidth(420)
        sync_titlebar(self)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)

        headline = QLabel(f"Yeni sürüm hazır: v{self.latest}")
        font = headline.font()
        font.setPointSize(14)
        font.setBold(True)
        headline.setFont(font)
        layout.addWidget(headline)

        sub = QLabel(
            f"Şu an v{self.current} kullanıyorsunuz. Güncelleme indirilecek, "
            "uygulama kapanıp kendi kendine yeniden açılacak.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #888;")
        layout.addWidget(sub)

        notes_url = self.release.get("notes_url") or ""
        if notes_url:
            link = QLabel(f'<a href="{notes_url}">Neler değişti?</a>')
            link.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
            layout.addWidget(link)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #888;")
        self.status.setVisible(False)
        layout.addWidget(self.status)

        btn_row = QHBoxLayout()
        self.skip_btn = QPushButton("Bu sürümü atla")
        self.skip_btn.clicked.connect(self._skip)
        self.later_btn = QPushButton("Sonra")
        self.later_btn.clicked.connect(self.reject)
        self.update_btn = QPushButton("Şimdi güncelle")
        self.update_btn.setObjectName(ACCENT_BUTTON_OBJECT_NAME)
        self.update_btn.setDefault(True)
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self._start)
        btn_row.addWidget(self.skip_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.later_btn)
        btn_row.addWidget(self.update_btn)
        layout.addLayout(btn_row)

    def _skip(self):
        self.skipped_version = self.latest
        self.reject()

    def _start(self):
        if self._worker is not None:
            return
        url = self.release.get("download_url") or ""
        if not url:
            QMessageBox.warning(self, "Güncelleme",
                                "Güncelleme dosyasının adresi alınamadı.")
            return
        self._set_busy(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setVisible(True)
        self.status.setText("İndiriliyor...")
        self._worker = AppUpdateWorker(mode="download", download_url=url, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.ready.connect(self._on_ready)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _on_progress(self, pct: int, msg: str):
        self.progress.setValue(pct)
        self.status.setText(msg)

    def _on_ready(self, script_path: str):
        AppUpdater().launch_apply_script(script_path)
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _on_failed(self, message: str):
        self._set_busy(False)
        self.progress.setVisible(False)
        self.status.setVisible(False)
        QMessageBox.warning(self, "Güncelleme", message)

    def _on_worker_done(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _set_busy(self, busy: bool):
        self.update_btn.setEnabled(not busy)
        self.skip_btn.setEnabled(not busy)
        self.later_btn.setEnabled(not busy)

    def closeEvent(self, event):
        worker = self._worker
        if worker is not None:
            # Yorumlayici sonlanirken calisir durumda kalan bir QThread
            # Qt6Core.dll icinde cokmeye yol acabilir; bitmesi beklenir
            # (indirmenin ag zaman asimi sinirlidir).
            worker.finished.disconnect(self._on_worker_done)
            self._worker = None
            worker.wait()
            worker.deleteLater()
        super().closeEvent(event)
