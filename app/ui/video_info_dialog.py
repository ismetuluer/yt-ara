"""Video bilgi penceresi.

Secilen videonun metadata'sini gosterir ve indirme / kare cikarma
islemlerine gecis saglar.
"""
import logging
import os
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from app.models.video import VideoResult
from app.ui.icons import icon
from app.services.download_history import DownloadHistory
from app.services.ytdlp_service import YtDlpError, YtDlpService


class VideoInfoDialog(QDialog):
    def __init__(self, video: VideoResult, settings, parent=None):
        super().__init__(parent)
        self.video = video
        self.settings = settings
        self.log = logging.getLogger("yt_ara.info_dialog")
        self._service = YtDlpService()

        self.setWindowTitle("Video bilgisi")
        self.setMinimumSize(480, 360)
        from app.ui.theme import sync_titlebar
        sync_titlebar(self)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.title_label = QLabel(self.video.title)
        self.title_label.setWordWrap(True)
        font = self.title_label.font()
        font.setBold(True)
        font.setPointSize(11)
        self.title_label.setFont(font)
        layout.addWidget(self.title_label)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.info_label)

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        self.open_btn = QPushButton(icon("open"), "Tarayıcıda aç")
        self.open_btn.clicked.connect(lambda: webbrowser.open(self.video.url))
        self.download_btn = QPushButton(icon("download"), "İndir")
        self.download_btn.clicked.connect(self._download)
        self.frames_btn = QPushButton("Görüntü çıkar")
        self.frames_btn.clicked.connect(self._frames)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.open_btn)
        btn_row.addWidget(self.download_btn)
        btn_row.addWidget(self.frames_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _load(self):
        self.info_label.setText("Bilgiler yükleniyor...")
        try:
            info = self._service.video_metadata(self.video.video_id)
        except YtDlpError as exc:
            self.info_label.setText(f"Bilgiler alınamadı: {exc.user_message}")
            return
        self._info = info
        self._render(info)

    def _render(self, info: dict):
        duration = info.get("duration")
        dur_txt = f"{int(duration // 60)} dk {int(duration % 60)} sn" if duration else "?"
        upload_date = info.get("upload_date") or ""
        if len(upload_date) == 8:
            upload_date = f"{upload_date[6:8]}.{upload_date[4:6]}.{upload_date[0:4]}"
        views = info.get("view_count")
        views_txt = f"{views:,}".replace(",", ".") if views else "?"
        lines = [
            f"<b>Kanal:</b> {info.get('channel') or '?'}",
            f"<b>Süre:</b> {dur_txt}",
            f"<b>Yayın Tarihi:</b> {upload_date or '?'}",
            f"<b>Görüntülenme:</b> {views_txt}",
            f"<b>Video ID:</b> {self.video.video_id}",
        ]
        desc = (info.get("description") or "").strip()
        if desc:
            lines.append(f"<b>Açıklama:</b><br>{desc[:400]}")
        self.info_label.setText("<br>".join(lines))

    def _download(self):
        from app.ui.download_dialog import DownloadDialog
        item = {"video_id": self.video.video_id, "title": self.video.title,
                "url": self.video.url}
        dlg = DownloadDialog([item], self.settings, self)
        dlg.exec()

    def _frames(self):
        from PySide6.QtWidgets import QMessageBox
        history = DownloadHistory()
        file_path = history.file_path_for(self.video.url)
        if file_path and os.path.isfile(file_path):
            from app.ui.frame_dialog import FrameDialog
            dlg = FrameDialog(file_path, self.video.title, self.settings, self)
            dlg.exec()
            return
        answer = QMessageBox.question(
            self, "Görüntü Çıkarma",
            "Görüntü çıkarmak için önce videonun indirilmesi gerekir.\n"
            "Şimdi indirilsin mi?")
        if answer != QMessageBox.Yes:
            return
        from app.ui.download_dialog import DownloadDialog
        item = {"video_id": self.video.video_id, "title": self.video.title,
                "url": self.video.url}
        dlg = DownloadDialog([item], self.settings, self)
        if dlg.exec() and self.video.url in dlg.completed_urls:
            file_path = history.file_path_for(self.video.url)
            if file_path and os.path.isfile(file_path):
                from app.ui.frame_dialog import FrameDialog
                fdlg = FrameDialog(file_path, self.video.title, self.settings, self)
                fdlg.exec()
