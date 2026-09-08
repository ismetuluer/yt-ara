"""Video indirme penceresi.

Birden fazla video ayni anda indirilebilir. Kalite secimi, video basina
durum (bekliyor / indiriliyor / tamam / hata) ve iptal destegi vardir.
"""
import logging
import os

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFileDialog, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout,
)

from app.services.download_history import DownloadHistory
from app.services.download_service import QUALITY_OPTIONS
from app.services.ffmpeg_service import ffmpeg_available, find_ffmpeg
from app.services.scheduled_download_service import ScheduledDownloadService
from app.ui.icons import icon
from app.ui.theme import ACCENT_BUTTON_OBJECT_NAME
from app.utils.paths import default_download_dir
from app.workers.download_worker import DownloadWorker
from app.workers.ffmpeg_download_worker import FFmpegDownloadWorker

COLOR_DONE = QColor(198, 239, 206)
COLOR_FAILED = QColor(255, 214, 214)


class DownloadDialog(QDialog):
    def __init__(self, items: list[dict], settings, parent=None):
        """items: [{'video_id', 'title', 'url'}, ...]"""
        super().__init__(parent)
        self.items = items
        self.settings = settings
        self.log = logging.getLogger("yt_ara.dl_dialog")
        self._worker: DownloadWorker | None = None
        self._ffmpeg_worker: FFmpegDownloadWorker | None = None
        self._pending_start: tuple | None = None
        self._history = DownloadHistory()
        self._list_items: dict[str, QListWidgetItem] = {}
        self._id_to_url = {item.get("video_id", ""): item.get("url", "") for item in items}
        self.completed_urls: set[str] = set()
        # video_id -> (indirilen_byte, toplam_byte); genel yuzde bunlardan
        # hesaplanir (bkz. _recompute_overall_progress).
        self._byte_progress: dict[str, tuple[int, int]] = {}
        self._done_count = 0

        self.setWindowTitle("Video indir")
        self.setMinimumSize(560, 420)
        from app.ui.theme import sync_titlebar
        sync_titlebar(self)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Klasor secimi
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("İndirme klasörü"))
        self.dir_edit = QLabel()
        self.dir_edit.setText(self.settings.download_dir or default_download_dir())
        self.dir_edit.setWordWrap(True)
        browse_btn = QPushButton(icon("folder"), "Gözat")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # Kalite
        qual_row = QHBoxLayout()
        qual_row.addWidget(QLabel("Kalite"))
        self.quality_combo = QComboBox()
        for label, _ in QUALITY_OPTIONS:
            self.quality_combo.addItem(label)
        self.quality_combo.setCurrentIndex(0)
        qual_row.addWidget(self.quality_combo)
        qual_row.addStretch(1)
        layout.addLayout(qual_row)

        # Altyazi
        self.subtitle_check = QCheckBox("Altyazıları da indir (varsa)")
        self.subtitle_check.setChecked(self.settings.download_subtitles)
        self.subtitle_check.toggled.connect(self._on_subtitle_toggled)
        layout.addWidget(self.subtitle_check)

        # Zamanlama
        schedule_row = QHBoxLayout()
        self.schedule_check = QCheckBox("Daha sonra indir")
        self.schedule_check.toggled.connect(self._on_schedule_toggled)
        self.schedule_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_edit.setCalendarPopup(True)
        self.schedule_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.schedule_edit.setEnabled(False)
        self.schedule_edit.setMinimumDateTime(QDateTime.currentDateTime())
        schedule_row.addWidget(self.schedule_check)
        schedule_row.addWidget(self.schedule_edit)
        schedule_row.addStretch(1)
        layout.addLayout(schedule_row)

        # Video listesi
        layout.addWidget(QLabel("İndirilecek videolar"))
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        # Ilerleme
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        status_row = QHBoxLayout()
        self.status_label = QLabel("Hazır")
        self.active_label = QLabel("")
        self.active_label.setStyleSheet("color: #888;")
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.active_label)
        layout.addLayout(status_row)

        self.notify_check = QCheckBox("İndirme tamamlanınca bildirim göster")
        self.notify_check.setChecked(self.settings.notify_download_complete)
        self.notify_check.toggled.connect(self._on_notify_toggled)
        layout.addWidget(self.notify_check)

        # Butonlar
        btn_row = QHBoxLayout()
        self.download_btn = QPushButton(icon("download", on_accent=True), "İndir")
        self.download_btn.setObjectName(ACCENT_BUTTON_OBJECT_NAME)
        self.download_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton(icon("cancel"), "İptal")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.background_btn = QPushButton("Arka plana gönder")
        self.background_btn.setToolTip(
            "Pencereyi gizler; indirme arka planda devam eder.")
        self.background_btn.clicked.connect(self.hide)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.download_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.background_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _populate(self):
        for item in self.items:
            list_item = QListWidgetItem(item.get("title", ""))
            self.list_widget.addItem(list_item)
            self._list_items[item.get("video_id", "")] = list_item
        self.status_label.setText(f"{len(self.items)} video hazır.")

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "İndirme Klasörü Seç", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)

    def _start(self):
        if self._worker is not None:
            return
        download_dir = self.dir_edit.text().strip()
        if not download_dir:
            download_dir = default_download_dir()
        os.makedirs(download_dir, exist_ok=True)
        # Secilen klasor bir sonraki sefer icin hatirlanir.
        if self.settings.download_dir != download_dir:
            self.settings.download_dir = download_dir
            self.settings.save()
        quality = self.quality_combo.currentText()

        if self.schedule_check.isChecked():
            self._schedule(download_dir, quality)
            return

        if not ffmpeg_available():
            box = QMessageBox(self)
            box.setWindowTitle("FFmpeg bulunamadı")
            box.setText(
                "Yüksek kaliteli birleştirme için FFmpeg gerekir (yaklaşık 140 MB, "
                "bir kereliğine indirilir).\nFFmpeg olmadan yalnızca tek dosya "
                "(daha düşük kalite olabilir) indirilebilir.")
            download_btn = box.addButton("FFmpeg'i indir", QMessageBox.AcceptRole)
            box.addButton("FFmpeg olmadan devam et", QMessageBox.DestructiveRole)
            cancel_btn = box.addButton("Vazgeç", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is cancel_btn:
                return
            if clicked is download_btn:
                self._download_ffmpeg_then_start(download_dir, quality)
                return
        self._start_worker(download_dir, quality)

    def _download_ffmpeg_then_start(self, download_dir: str, quality: str):
        self._pending_start = (download_dir, quality)
        self._set_busy(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("FFmpeg indiriliyor...")
        self._ffmpeg_worker = FFmpegDownloadWorker(parent=self)
        self._ffmpeg_worker.progress.connect(self._on_ffmpeg_progress)
        self._ffmpeg_worker.done.connect(self._on_ffmpeg_ready)
        self._ffmpeg_worker.failed.connect(self._on_ffmpeg_download_failed)
        self._ffmpeg_worker.finished.connect(self._on_ffmpeg_worker_finished)
        self._ffmpeg_worker.start()

    def _on_ffmpeg_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.status_label.setText(msg)

    def _on_ffmpeg_ready(self, path: str):
        download_dir, quality = self._pending_start
        self._start_worker(download_dir, quality)

    def _on_ffmpeg_download_failed(self, message: str):
        self._set_busy(False)
        self.status_label.setText("Hazır")
        QMessageBox.warning(self, "FFmpeg İndirme", message)

    def _on_ffmpeg_worker_finished(self):
        if self._ffmpeg_worker is not None:
            self._ffmpeg_worker.deleteLater()
            self._ffmpeg_worker = None

    def _start_worker(self, download_dir: str, quality: str):
        self._byte_progress = {}
        self._done_count = 0
        self._worker = DownloadWorker(
            download_dir, quality, self.items, self._history,
            ffmpeg_path=find_ffmpeg(), subtitles=self.settings.download_subtitles,
            subtitle_langs=self.settings.subtitle_langs,
            max_concurrent=self.settings.max_concurrent_downloads,
            speed_limit_kbps=self.settings.download_speed_limit_kbps, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.active_count_changed.connect(self._on_active_count_changed)
        self._set_busy(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("İndiriliyor...")
        self._on_active_count_changed(0)
        self._worker.start()

    def _on_active_count_changed(self, active: int):
        self.active_label.setText(
            f"Aktif indirme: {active} / en fazla {self.settings.max_concurrent_downloads}")

    def _recompute_overall_progress(self):
        """Tum videolarin toplam indirilen/toplam byte'ina gore genel yuzdeyi hesaplar.

        Toplam boyutu henuz bilinmeyen (ornegin daha baslamamis) videolar
        icin, tamamlanan video sayisina gore kaba bir pay eklenir; boylece
        yuzde, tum boyutlar bilinmeden once bile mantikli sekilde ilerler.
        """
        total_items = len(self.items) or 1
        known_downloaded = sum(d for d, t in self._byte_progress.values() if t > 0)
        known_total = sum(t for _, t in self._byte_progress.values() if t > 0)
        items_with_known_total = sum(1 for _, t in self._byte_progress.values() if t > 0)
        if known_total > 0:
            byte_pct = known_downloaded / known_total
            # Boyutu bilinen videolarin agirlikli payi + geri kalanlarin
            # (boyutu bilinmeyen/henuz baslamamis) tamamlanma orani.
            weight = items_with_known_total / total_items
            other_done = max(0, self._done_count - items_with_known_total)
            other_weight = (total_items - items_with_known_total) / total_items
            other_pct = (other_done / (total_items - items_with_known_total)
                         if total_items > items_with_known_total else 0)
            pct = byte_pct * weight + other_pct * other_weight
        else:
            pct = self._done_count / total_items
        self.progress_bar.setValue(min(100, max(0, int(pct * 100))))

    def _schedule(self, download_dir: str, quality: str):
        run_at = self.schedule_edit.dateTime().toPython()
        scheduler = ScheduledDownloadService()
        for item in self.items:
            scheduler.add(
                item.get("video_id", ""), item.get("title", ""), item.get("url", ""),
                item.get("channel_title", ""), quality, download_dir, run_at)
        QMessageBox.information(
            self, "Zamanlandı",
            f"{len(self.items)} video {run_at.strftime('%d.%m.%Y %H:%M')} için "
            "kuyruğa eklendi.\n\"Zamanlanmış\" sekmesinden takip edebilirsiniz.")
        self.accept()

    def _on_schedule_toggled(self, checked: bool):
        self.schedule_edit.setEnabled(checked)
        self.download_btn.setText("Kuyruğa ekle" if checked else "İndir")

    def _on_subtitle_toggled(self, checked: bool):
        self.settings.download_subtitles = checked
        self.settings.save()

    def _cancel(self):
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)
            # Aktif indirmeler genelde birkac saniye icinde durur; ancak bir
            # video tam o an FFmpeg ile birlestiriliyorsa (ses+goruntu
            # birlestirme adimi), o adim yarida kesilemez ve bitmesi
            # beklenir -- bu yuzden kullaniciya suresiz "hala bekliyor"
            # izlenimi vermemek icin durum aciklamasi buna gore yazilir.
            self.status_label.setText(
                "İptal ediliyor... (bir video tam o an birleştiriliyorsa "
                "o adımın bitmesi birkaç saniye daha sürebilir)")

    def _on_progress(self, video_id, title, downloaded, total, speed, eta, filename):
        item = self._list_items.get(video_id)
        if item is None:
            return
        if total > 0:
            pct = int(downloaded * 100 / total)
            speed_txt = f"  ({speed / 1024 / 1024:.1f} MB/sn)" if speed > 0 else ""
            item.setText(f"{title}  —  %{pct}{speed_txt}")
        else:
            item.setText(f"{title}  —  indiriliyor...")
        self._byte_progress[video_id] = (downloaded, total)
        self._recompute_overall_progress()

    def _on_finished(self, video_id, title, path):
        url = self._id_to_url.get(video_id)
        if url:
            self.completed_urls.add(url)
        item = self._list_items.get(video_id)
        if item is not None:
            item.setText(title)
            item.setBackground(COLOR_DONE)
        self.status_label.setText(f"Tamamlandı: {title}")
        self._done_count += 1
        self._byte_progress.pop(video_id, None)
        self._recompute_overall_progress()

    def _on_failed(self, video_id, title, message):
        item = self._list_items.get(video_id)
        if item is not None:
            item.setText(title)
            item.setBackground(COLOR_FAILED)
            item.setToolTip(message)
        self.status_label.setText(f"İndirilemedi: {title}")
        self._done_count += 1
        self._byte_progress.pop(video_id, None)
        self._recompute_overall_progress()

    def _on_all_done(self, done, total):
        self._set_busy(False)
        self.active_label.setText("")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        if done == total:
            self.status_label.setText(f"Tümü tamamlandı: {done}/{total} video indirildi.")
        else:
            self.status_label.setText(
                f"Bitti: {done}/{total} video indirildi, {total - done} hata.")
        if self.settings.notify_download_complete:
            QMessageBox.information(
                self, "İndirme tamamlandı",
                f"{done}/{total} video indirildi.\nKlasör: {self.dir_edit.text()}")

    def _on_notify_toggled(self, checked: bool):
        self.settings.notify_download_complete = checked
        self.settings.save()

    def _set_busy(self, busy: bool):
        self.download_btn.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(busy)
        self.close_btn.setEnabled(not busy)
        self.quality_combo.setEnabled(not busy)

    def closeEvent(self, event):
        if self._worker is not None:
            # Yorumlayici sonlanirken calisir durumda kalan bir QThread
            # Qt6Core.dll icinde cokmeye yol acabilir; is parcaciginin
            # gercekten bitmesini bekleriz (iptal genelde hizli sonuclanir).
            self._worker.cancel()
            self._worker.wait()
        if self._ffmpeg_worker is not None:
            self._ffmpeg_worker.wait()
        super().closeEvent(event)
