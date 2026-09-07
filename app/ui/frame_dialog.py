"""Videodan kare cikarma penceresi.

Belirli bir zaman noktasi, birden fazla zaman noktasi veya belirli
araliklarla kare cikarir. FFmpeg kullanir.
"""
import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

from app.services.ffmpeg_service import (
    FFmpegError, ffmpeg_available, parse_timecode,
)
from app.workers.frame_worker import FrameWorker


class FrameDialog(QDialog):
    def __init__(self, video_path: str, video_title: str, settings, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.video_title = video_title
        self.settings = settings
        self.log = logging.getLogger("yt_ara.frame_dialog")
        self._worker: FrameWorker | None = None

        self.setWindowTitle("Görüntü Çıkar")
        self.setMinimumSize(520, 320)
        from app.ui.theme import sync_titlebar
        sync_titlebar(self)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Video: {self.video_title}"))
        layout.addWidget(QLabel(f"Dosya: {os.path.basename(self.video_path)}"))

        # Cikti klasoru
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Çıktı Klasörü:"))
        self.dir_edit = QLineEdit()
        default_dir = os.path.join(os.path.dirname(self.video_path), "kareler")
        self.dir_edit.setText(default_dir)
        browse_btn = QPushButton("Gözat...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # Format
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Görüntü Formatı:"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("JPG", "jpg")
        self.format_combo.addItem("PNG", "png")
        idx = 0 if self.settings.frame_format == "jpg" else 1
        self.format_combo.setCurrentIndex(idx)
        fmt_row.addWidget(self.format_combo)
        fmt_row.addStretch(1)
        layout.addLayout(fmt_row)

        # Mod secimi
        self.specific_check = QCheckBox("Belirli zaman noktalarından çıkar")
        self.specific_check.setChecked(True)
        self.specific_check.toggled.connect(self._toggle_mode)
        layout.addWidget(self.specific_check)

        # Belirli zamanlar
        self.specific_box = QVBoxLayout()
        self.specific_box.addWidget(QLabel(
            "Zaman noktaları (virgülle ayırın, örn: 00:30, 01:15, 02:00):"))
        self.times_edit = QLineEdit()
        self.times_edit.setPlaceholderText("00:30, 01:15, 02:00")
        self.specific_box.addWidget(self.times_edit)
        layout.addLayout(self.specific_box)

        # Aralik
        self.interval_box = QVBoxLayout()
        self.interval_box.addWidget(QLabel("Aralık (saniye):"))
        self.interval_edit = QLineEdit()
        self.interval_edit.setPlaceholderText("örn: 30")
        self.interval_box.addWidget(self.interval_edit)
        layout.addLayout(self.interval_box)
        self.interval_box.setEnabled(False)

        # Ilerleme
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Hazır")
        layout.addWidget(self.status_label)

        # Butonlar
        btn_row = QHBoxLayout()
        self.extract_btn = QPushButton("Görüntüleri Çıkar")
        self.extract_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.extract_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _toggle_mode(self, checked: bool):
        self.specific_box.setEnabled(checked)
        self.interval_box.setEnabled(not checked)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Çıktı Klasörü Seç", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)

    def _start(self):
        if self._worker is not None:
            return
        if not ffmpeg_available():
            QMessageBox.warning(
                self, "FFmpeg Gerekli",
                "Görüntü çıkarmak için FFmpeg gereklidir. Lütfen FFmpeg'i "
                "kurun veya uygulama klasöründeki tools/ffmpeg/ içine koyun.")
            return
        output_dir = self.dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Klasör Gerekli", "Çıktı klasörü boş olamaz.")
            return
        image_format = self.format_combo.currentData()
        base_name = self._safe_base_name(self.video_title)

        if self.specific_check.isChecked():
            raw = self.times_edit.text().strip()
            if not raw:
                QMessageBox.warning(self, "Zaman Gerekli",
                                    "En az bir zaman noktası girin.")
                return
            try:
                times = [parse_timecode(t) for t in raw.split(",") if t.strip()]
            except ValueError as exc:
                QMessageBox.warning(self, "Geçersiz Zaman", str(exc))
                return
            if not times:
                QMessageBox.warning(self, "Zaman Gerekli",
                                    "En az bir zaman noktası girin.")
                return
            self._worker = FrameWorker(
                self.video_path, output_dir, base_name,
                times_seconds=times, image_format=image_format, parent=self)
        else:
            raw = self.interval_edit.text().strip()
            try:
                interval = int(raw)
            except ValueError:
                QMessageBox.warning(self, "Geçersiz Aralık",
                                    "Aralık bir tam sayı (saniye) olmalıdır.")
                return
            if interval <= 0:
                QMessageBox.warning(self, "Geçersiz Aralık",
                                    "Aralık 0'dan büyük olmalıdır.")
                return
            self._worker = FrameWorker(
                self.video_path, output_dir, base_name,
                interval_seconds=interval, image_format=image_format, parent=self)

        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._set_busy(True)
        self._worker.start()

    def _cancel(self):
        if self._worker is not None:
            self._worker.cancel()
            self.status_label.setText("İptal ediliyor...")

    def _on_progress(self, done, total, path):
        if total > 0:
            pct = int(done * 100 / total)
        else:
            pct = 0
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"Çıkarılıyor: {done}/{total}")

    def _on_done(self, created):
        self._set_busy(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"{len(created)} görüntü çıkarıldı.")
        QMessageBox.information(
            self, "Tamamlandı",
            f"{len(created)} görüntü çıkarıldı.\nKlasör: {self.dir_edit.text()}")

    def _on_failed(self, message):
        self._set_busy(False)
        self.status_label.setText("Görüntü çıkarma başarısız.")
        QMessageBox.warning(self, "Hata", message)

    def _set_busy(self, busy: bool):
        self.extract_btn.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.close_btn.setEnabled(not busy)

    @staticmethod
    def _safe_base_name(title: str) -> str:
        import re
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)
        name = name.strip().strip(".")
        return name[:80] or "video"

    def closeEvent(self, event):
        if self._worker is not None:
            # Yorumlayici sonlanirken calisir durumda kalan bir QThread
            # Qt6Core.dll icinde cokmeye yol acabilir; is parcaciginin
            # gercekten bitmesini bekleriz (iptal genelde hizli sonuclanir).
            self._worker.cancel()
            self._worker.wait()
        super().closeEvent(event)
