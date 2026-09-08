"""Ayarlar penceresi: API anahtari, tema, disa aktarma klasoru, yt-dlp guncelleme."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.services.app_updater import AppUpdater
from app.services.ffmpeg_service import ffmpeg_available, find_ffmpeg
from app.services.quota_service import QuotaTracker
from app.services.settings_service import SettingsService
from app.services.youtube_service import YouTubeError, YouTubeService
from app.services.ytdlp_updater import YtDlpUpdater
from app.ui.icons import icon
from app.ui.theme import ACCENT_BUTTON_OBJECT_NAME
from app.workers.app_update_worker import AppUpdateWorker
from app.workers.ffmpeg_download_worker import FFmpegDownloadWorker
from app.workers.update_worker import YtDlpUpdateWorker

THEMES = [("system", "Sistem"), ("light", "Açık"), ("dark", "Koyu")]


class SettingsDialog(QDialog):
    def __init__(self, settings: SettingsService, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._quota = QuotaTracker(settings)
        self._update_worker: YtDlpUpdateWorker | None = None
        self._app_update_worker: AppUpdateWorker | None = None
        self._pending_release: dict | None = None
        self._ffmpeg_worker: FFmpegDownloadWorker | None = None
        self.setWindowTitle("Ayarlar")
        self.setMinimumWidth(560)
        from app.ui.theme import sync_titlebar
        sync_titlebar(self)

        # Ayarlar listesi uzun; dizustu gibi kisa ekranlarda pencere ekrana
        # sigmadiginda alt kismi (Kaydet dugmesi dahil) hic gorunmuyordu.
        # Bu yuzden icerik kaydirilabilir bir alana konur; Kaydet/Vazgeç
        # satiri kaydirma alaninin DISINDA, her zaman gorunur kalir.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 16)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # API anahtari
        form.addRow(self._section("YouTube API", first=True))
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit(self.settings.api_key)
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("YouTube Data API v3 anahtarınız")
        self.show_key = QCheckBox("Göster")
        self.show_key.toggled.connect(
            lambda on: self.key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self.show_key)
        form.addRow("API anahtarı", key_row)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Anahtarı sına")
        self.test_btn.clicked.connect(self._test_key)
        self.test_result = QLabel("")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result, 1)
        form.addRow("", test_row)

        # Tahmini kota kullanimi
        quota_row = QHBoxLayout()
        self.quota_bar = QProgressBar()
        self.quota_bar.setRange(0, 100)
        self.quota_bar.setFormat("%p%")
        quota_row.addWidget(self.quota_bar, 1)
        self.quota_refresh_btn = QPushButton(icon("refresh"), "Yenile")
        self.quota_refresh_btn.clicked.connect(self._refresh_quota)
        quota_row.addWidget(self.quota_refresh_btn)
        form.addRow("Kota kullanımı", quota_row)
        self.quota_hint = QLabel(
            "Yalnızca bu uygulamanın yaptığı çağrılara göre tahmindir; "
            "anahtar başka yerde de kullanılıyorsa gerçek kalan kota daha az olabilir.")
        self.quota_hint.setWordWrap(True)
        self.quota_hint.setStyleSheet("color: #888;")
        form.addRow("", self.quota_hint)
        self._refresh_quota()

        help_label = QLabel(
            'Anahtarınız yalnızca bu bilgisayarda, kullanıcı ayarlar '
            'klasöründe saklanır.<br>'
            '<a href="https://console.cloud.google.com/apis/library/youtube.googleapis.com">'
            'YouTube API anahtarı nasıl alınır?</a>')
        help_label.setWordWrap(True)
        help_label.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        form.addRow(help_label)

        form.addRow(self._section("Görünüm"))

        # Tema
        self.theme_combo = QComboBox()
        for key, label in THEMES:
            self.theme_combo.addItem(label, key)
        idx = next((i for i, (k, _) in enumerate(THEMES) if k == self.settings.theme), 0)
        self.theme_combo.setCurrentIndex(idx)
        form.addRow("Tema", self.theme_combo)

        form.addRow(self._section("Klasörler"))

        # Disa aktarma klasoru
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(self.settings.export_dir)
        self.dir_edit.setPlaceholderText("Her seferinde sorulur")
        browse = QPushButton(icon("folder"), "Gözat")
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse)
        form.addRow("Dışa aktarma klasörü", dir_row)

        # Indirme klasoru
        dl_row = QHBoxLayout()
        self.dl_dir_edit = QLineEdit(self.settings.download_dir)
        self.dl_dir_edit.setPlaceholderText("Masaüstü")
        dl_browse = QPushButton(icon("folder"), "Gözat")
        dl_browse.clicked.connect(self._browse_dl_dir)
        dl_row.addWidget(self.dl_dir_edit, 1)
        dl_row.addWidget(dl_browse)
        form.addRow("İndirme klasörü", dl_row)

        form.addRow(self._section("Arama"))

        # Arama yontemi
        self.method_combo = QComboBox()
        self.method_combo.addItem("Otomatik", "auto")
        self.method_combo.addItem("YouTube API", "api")
        self.method_combo.addItem("API'siz", "ytdlp")
        idx = next((i for i in range(self.method_combo.count())
                    if self.method_combo.itemData(i) == self.settings.search_method), 0)
        self.method_combo.setCurrentIndex(idx)
        form.addRow("Arama yöntemi", self.method_combo)

        # Tam ifade filtresi
        self.exact_check = QCheckBox("Tam eşleşme")
        self.exact_check.setToolTip(
            "Açıkken arama ifadesi kelimelere bölünmeden bütün olarak eşleştirilir.")
        self.exact_check.setChecked(self.settings.exact_phrase)
        form.addRow("", self.exact_check)

        # Kanal tarama kapsami
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Son 100 video", "100")
        self.scope_combo.addItem("Son 500 video", "500")
        self.scope_combo.addItem("Son 1000 video", "1000")
        self.scope_combo.addItem("Tümü", "all")
        idx = next((i for i in range(self.scope_combo.count())
                    if self.scope_combo.itemData(i) == self.settings.channel_scan_scope), 0)
        self.scope_combo.setCurrentIndex(idx)
        form.addRow("Kanal tarama kapsamı", self.scope_combo)

        form.addRow(self._section("İndirme"))

        # Kare format
        self.frame_combo = QComboBox()
        self.frame_combo.addItem("JPG", "jpg")
        self.frame_combo.addItem("PNG", "png")
        idx = 0 if self.settings.frame_format == "jpg" else 1
        self.frame_combo.setCurrentIndex(idx)
        form.addRow("Görüntü formatı", self.frame_combo)

        # Indirme bildirimi
        self.notify_check = QCheckBox("İndirme tamamlanınca bildirim göster")
        self.notify_check.setChecked(self.settings.notify_download_complete)
        form.addRow("", self.notify_check)

        # Ayni anda indirme sayisi
        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setRange(1, 6)
        self.max_concurrent_spin.setValue(self.settings.max_concurrent_downloads)
        self.max_concurrent_spin.setToolTip(
            "Aynı anda en fazla kaç video indirileceği. Yüksek değer daha "
            "hızlı toplu indirme sağlar ama internet bağlantınızı ve "
            "bilgisayarınızı daha çok kullanır.")
        form.addRow("Aynı anda indirme", self.max_concurrent_spin)

        # Indirme hizi sinirlamasi
        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 100_000)
        self.speed_limit_spin.setSingleStep(100)
        self.speed_limit_spin.setSuffix(" KB/sn")
        self.speed_limit_spin.setSpecialValueText("Sınırsız")
        self.speed_limit_spin.setValue(self.settings.download_speed_limit_kbps)
        self.speed_limit_spin.setToolTip(
            "Her video indirmesi için ayrı ayrı uygulanan hız sınırı "
            "(0 = sınırsız). İnternet bağlantınızı diğer kullanımlar için "
            "boşta bırakmak isterseniz kullanışlıdır.")
        form.addRow("İndirme hızı sınırı", self.speed_limit_spin)

        # Altyazi dilleri (varsayilan; indirme penceresindeki secenegi etkiler)
        self.subtitle_langs_edit = QLineEdit(self.settings.subtitle_langs)
        self.subtitle_langs_edit.setPlaceholderText("tr,en")
        form.addRow("Altyazı dilleri", self.subtitle_langs_edit)

        # Sonuc listesinde indirilenleri gizleme
        self.hide_downloaded_check = QCheckBox(
            "Daha önce indirilen videoları sonuç listesinde gizle")
        self.hide_downloaded_check.setChecked(self.settings.hide_downloaded)
        form.addRow("", self.hide_downloaded_check)

        form.addRow(self._section("İzleme listesi"))

        # Izleme listesi denetim araligi
        self.watchlist_interval_combo = QComboBox()
        for minutes in (15, 30, 60, 120, 240):
            label = f"{minutes} dakika" if minutes < 60 else f"{minutes // 60} saat"
            self.watchlist_interval_combo.addItem(label, minutes)
        idx = next((i for i in range(self.watchlist_interval_combo.count())
                    if self.watchlist_interval_combo.itemData(i)
                    == self.settings.watchlist_interval_minutes), 1)
        self.watchlist_interval_combo.setCurrentIndex(idx)
        form.addRow("İzleme listesi denetim aralığı", self.watchlist_interval_combo)

        # FFmpeg (yuksek kaliteli birlestirme ve goruntu cikarma icin gerekli;
        # dagitim boyutunu kucuk tutmak icin onceden paketlenmez)
        form.addRow(self._section("Bileşenler ve sürüm"))
        ffmpeg_row = QHBoxLayout()
        self.ffmpeg_status_label = QLabel()
        self._refresh_ffmpeg_status()
        self.download_ffmpeg_btn = QPushButton(icon("download"), "İndir")
        self.download_ffmpeg_btn.clicked.connect(self._download_ffmpeg)
        ffmpeg_row.addWidget(self.ffmpeg_status_label, 1)
        ffmpeg_row.addWidget(self.download_ffmpeg_btn)
        form.addRow("FFmpeg", ffmpeg_row)
        self.ffmpeg_progress = QProgressBar()
        self.ffmpeg_progress.setRange(0, 100)
        self.ffmpeg_progress.setVisible(False)
        form.addRow("", self.ffmpeg_progress)

        # yt-dlp guncelleme (YouTube degisikliklerine karsi)
        upd_row = QHBoxLayout()
        self.ytdlp_version_label = QLabel(f"Kurulu: {YtDlpUpdater().current_version()}")
        self.update_ytdlp_btn = QPushButton(icon("refresh"), "Güncellemeyi denetle")
        self.update_ytdlp_btn.clicked.connect(self._update_ytdlp)
        upd_row.addWidget(self.ytdlp_version_label, 1)
        upd_row.addWidget(self.update_ytdlp_btn)
        form.addRow("yt-dlp sürümü", upd_row)
        self.ytdlp_progress = QProgressBar()
        self.ytdlp_progress.setRange(0, 100)
        self.ytdlp_progress.setVisible(False)
        form.addRow("", self.ytdlp_progress)
        self.ytdlp_status = QLabel("")
        form.addRow("", self.ytdlp_status)

        # Uygulama surumu (GitHub Releases)
        app_upd_row = QHBoxLayout()
        self.app_version_label = QLabel(f"Kurulu: v{AppUpdater.current_version()}")
        self.check_app_update_btn = QPushButton(icon("refresh"), "Güncellemeyi denetle")
        self.check_app_update_btn.clicked.connect(self._check_app_update)
        app_upd_row.addWidget(self.app_version_label, 1)
        app_upd_row.addWidget(self.check_app_update_btn)
        form.addRow("Uygulama sürümü", app_upd_row)
        self.app_update_progress = QProgressBar()
        self.app_update_progress.setRange(0, 100)
        self.app_update_progress.setVisible(False)
        form.addRow("", self.app_update_progress)
        self.app_update_status = QLabel("")
        form.addRow("", self.app_update_status)
        self.apply_app_update_btn = QPushButton("Güncelle ve yeniden başlat")
        self.apply_app_update_btn.setVisible(False)
        self.apply_app_update_btn.clicked.connect(self._apply_app_update)
        form.addRow("", self.apply_app_update_btn)

        layout.addLayout(form)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        # Kaydirma alani icerigi kendiliginden daraltmaz; pencere icerigin
        # gerektirdiginden dar acilirsa sag taraf (Gözat gibi dugmeler)
        # kirpilir. Alt sinir icerige gore belirlenir (+ kaydirma cubugu).
        self.setMinimumWidth(max(560, content.minimumSizeHint().width() + 40))

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 10, 20, 14)
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Vazgeç")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Kaydet")
        save_btn.setObjectName(ACCENT_BUTTON_OBJECT_NAME)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)

        self._fit_to_screen()

    @staticmethod
    def _section(title: str, first: bool = False) -> QLabel:
        """Uzun ayar listesini gorsel olarak bolen bolum basligi."""
        label = QLabel(title)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet(
            "color: #6e6e73; text-transform: uppercase;"
            f" margin-top: {2 if first else 18}px; margin-bottom: 2px;")
        return label

    def _fit_to_screen(self):
        """Pencereyi ekrana sigacak sekilde acar.

        Dizustu gibi kisa ekranlarda pencere ekrandan tasip alt kismi
        (Kaydet dugmesi dahil) gorunmez hale geliyordu; yukseklik ekranin
        kullanilabilir alanina gore sinirlanir, kalan icerige kaydirma
        cubugundan erisilir.
        """
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(600, 700)
            return
        available = screen.availableGeometry()
        width = min(max(self.minimumWidth(), 640), max(520, available.width() - 80))
        height = min(820, max(360, available.height() - 80))
        self.resize(width, height)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Dışa aktarma klasörü seç",
                                                self.dir_edit.text() or "")
        if path:
            self.dir_edit.setText(path)

    def _browse_dl_dir(self):
        path = QFileDialog.getExistingDirectory(self, "İndirme klasörü seç",
                                                self.dl_dir_edit.text() or "")
        if path:
            self.dl_dir_edit.setText(path)

    def _test_key(self):
        key = self.key_edit.text().strip()
        if not key:
            self.test_result.setText("Önce bir anahtar girin.")
            return
        self.test_btn.setEnabled(False)
        self.test_result.setText("Sınanıyor...")
        self.test_result.repaint()
        try:
            YouTubeService(key, on_call=self._quota.record).validate_key()
            self.test_result.setText("Anahtar geçerli.")
        except YouTubeError as exc:
            self.test_result.setText(exc.user_message)
        finally:
            self.test_btn.setEnabled(True)
            self._refresh_quota()

    def _refresh_quota(self):
        self.quota_bar.setValue(self._quota.percent())
        self.quota_bar.setToolTip(
            f"Tahmini kullanım: {self._quota.used()} / {self._quota.limit()} birim")

    # ------------------------------------------------------------ ffmpeg
    def _refresh_ffmpeg_status(self):
        if ffmpeg_available():
            path = find_ffmpeg()
            self.ffmpeg_status_label.setText(f"Kurulu ({path})")
        else:
            self.ffmpeg_status_label.setText(
                "Kurulu değil — yüksek kaliteli birleştirme ve görüntü çıkarma için gerekir")

    def _download_ffmpeg(self):
        if self._ffmpeg_worker is not None:
            return
        self.download_ffmpeg_btn.setEnabled(False)
        self.ffmpeg_progress.setVisible(True)
        self.ffmpeg_progress.setValue(0)
        self.ffmpeg_status_label.setText("İndiriliyor...")
        self._ffmpeg_worker = FFmpegDownloadWorker(parent=self)
        self._ffmpeg_worker.progress.connect(self._on_ffmpeg_progress)
        self._ffmpeg_worker.done.connect(self._on_ffmpeg_done)
        self._ffmpeg_worker.failed.connect(self._on_ffmpeg_failed)
        self._ffmpeg_worker.finished.connect(self._on_ffmpeg_worker_done)
        self._ffmpeg_worker.start()

    def _on_ffmpeg_progress(self, pct: int, msg: str):
        self.ffmpeg_progress.setValue(pct)
        self.ffmpeg_status_label.setText(msg)

    def _on_ffmpeg_done(self, path: str):
        self.ffmpeg_progress.setValue(100)
        self._refresh_ffmpeg_status()

    def _on_ffmpeg_failed(self, message: str):
        self.ffmpeg_progress.setVisible(False)
        self._refresh_ffmpeg_status()
        QMessageBox.warning(self, "FFmpeg indirme", message)

    def _on_ffmpeg_worker_done(self):
        self.download_ffmpeg_btn.setEnabled(True)
        self.ffmpeg_progress.setVisible(False)
        if self._ffmpeg_worker is not None:
            self._ffmpeg_worker.deleteLater()
            self._ffmpeg_worker = None

    # ------------------------------------------------------------ yt-dlp guncelleme
    def _update_ytdlp(self):
        if self._update_worker is not None:
            return
        self.update_ytdlp_btn.setEnabled(False)
        self.ytdlp_status.setText("En son sürüm denetleniyor...")
        self.ytdlp_progress.setVisible(True)
        self.ytdlp_progress.setRange(0, 0)  # denetim sirasinda belirsiz ilerleme
        self._update_worker = YtDlpUpdateWorker(auto=False, parent=self)
        self._update_worker.checked.connect(self._on_ytdlp_checked)
        self._update_worker.progress.connect(self._on_ytdlp_progress)
        self._update_worker.updated.connect(self._on_ytdlp_updated)
        self._update_worker.up_to_date.connect(self._on_ytdlp_up_to_date)
        self._update_worker.failed.connect(self._on_ytdlp_failed)
        self._update_worker.finished.connect(self._on_ytdlp_worker_done)
        self._update_worker.start()

    def _on_ytdlp_checked(self, current: str, latest: str, outdated: bool):
        if outdated:
            self.ytdlp_status.setText(f"Yeni sürüm bulundu: {latest} — indiriliyor...")
            self.ytdlp_progress.setRange(0, 100)
            self.ytdlp_progress.setValue(0)

    def _on_ytdlp_progress(self, pct: int, msg: str):
        if self.ytdlp_progress.maximum() == 0:
            self.ytdlp_progress.setRange(0, 100)
        self.ytdlp_progress.setValue(pct)
        self.ytdlp_status.setText(msg)

    def _on_ytdlp_updated(self, version: str):
        self.ytdlp_progress.setRange(0, 100)
        self.ytdlp_progress.setValue(100)
        self.ytdlp_status.setText(f"yt-dlp {version} sürümüne güncellendi.")
        self.ytdlp_version_label.setText(f"Kurulu: {YtDlpUpdater().current_version()}")

    def _on_ytdlp_up_to_date(self, current: str):
        self.ytdlp_progress.setVisible(False)
        self.ytdlp_status.setText(f"yt-dlp zaten güncel (sürüm {current}).")

    def _on_ytdlp_failed(self, message: str):
        self.ytdlp_progress.setVisible(False)
        self.ytdlp_status.setText("")
        QMessageBox.warning(self, "yt-dlp güncelleme", message)

    def _on_ytdlp_worker_done(self):
        self.update_ytdlp_btn.setEnabled(True)
        if self._update_worker is not None:
            self._update_worker.deleteLater()
            self._update_worker = None

    # ------------------------------------------------------------ uygulama guncellemesi
    def _check_app_update(self):
        if self._app_update_worker is not None:
            return
        self.check_app_update_btn.setEnabled(False)
        self.apply_app_update_btn.setVisible(False)
        self.app_update_status.setText("En son sürüm denetleniyor...")
        self._app_update_worker = AppUpdateWorker(mode="check", parent=self)
        self._app_update_worker.checked.connect(self._on_app_update_checked)
        self._app_update_worker.failed.connect(self._on_app_update_failed)
        self._app_update_worker.finished.connect(self._on_app_update_worker_done)
        self._app_update_worker.start()

    def _on_app_update_checked(self, current: str, latest: str, outdated: bool, release: dict):
        if outdated:
            self._pending_release = release
            self.app_update_status.setText(
                f"Yeni sürüm mevcut: v{latest} (kurulu: v{current})")
            self.apply_app_update_btn.setVisible(True)
        else:
            self.app_update_status.setText(f"Uygulama zaten güncel (v{current}).")

    def _on_app_update_failed(self, message: str):
        self.app_update_status.setText("")
        QMessageBox.warning(self, "Sürüm denetimi", message)

    def _on_app_update_worker_done(self):
        self.check_app_update_btn.setEnabled(True)
        if self._app_update_worker is not None:
            self._app_update_worker.deleteLater()
            self._app_update_worker = None

    def _apply_app_update(self):
        if self._app_update_worker is not None or not self._pending_release:
            return
        answer = QMessageBox.question(
            self, "Uygulamayı güncelle",
            "Güncelleme indirilip uygulanacak; bu işlem sırasında uygulama "
            "kapanıp yeniden başlayacak. Devam edilsin mi?")
        if answer != QMessageBox.Yes:
            return
        self.apply_app_update_btn.setEnabled(False)
        self.check_app_update_btn.setEnabled(False)
        self.app_update_progress.setVisible(True)
        self.app_update_progress.setValue(0)
        self._app_update_worker = AppUpdateWorker(
            mode="download", download_url=self._pending_release["download_url"], parent=self)
        self._app_update_worker.progress.connect(self._on_app_update_progress)
        self._app_update_worker.ready.connect(self._on_app_update_ready)
        self._app_update_worker.failed.connect(self._on_app_update_apply_failed)
        self._app_update_worker.finished.connect(self._on_app_update_worker_done)
        self._app_update_worker.start()

    def _on_app_update_progress(self, pct: int, msg: str):
        self.app_update_progress.setValue(pct)
        self.app_update_status.setText(msg)

    def _on_app_update_ready(self, script_path: str):
        AppUpdater().launch_apply_script(script_path)
        QApplication.instance().quit()

    def _on_app_update_apply_failed(self, message: str):
        self.apply_app_update_btn.setEnabled(True)
        self.check_app_update_btn.setEnabled(True)
        self.app_update_progress.setVisible(False)
        self.app_update_status.setText("")
        QMessageBox.warning(self, "Güncelleme", message)

    def closeEvent(self, event):
        ffmpeg_worker = self._ffmpeg_worker
        if ffmpeg_worker is not None:
            ffmpeg_worker.finished.disconnect(self._on_ffmpeg_worker_done)
            self._ffmpeg_worker = None
            ffmpeg_worker.wait()
            ffmpeg_worker.deleteLater()
        app_worker = self._app_update_worker
        if app_worker is not None:
            app_worker.finished.disconnect(self._on_app_update_worker_done)
            self._app_update_worker = None
            app_worker.wait()
            app_worker.deleteLater()
        worker = self._update_worker
        if worker is not None:
            # deleteLater()/None atamasi araya girmesin diye once koparilir
            worker.finished.disconnect(self._on_ytdlp_worker_done)
            self._update_worker = None
            worker.cancel()
            # QThread.terminate() Python thread'ini GIL tutarken oldurebilir
            # (tum uygulamayi kilitler); is parcacigini pencereden koparip
            # kendi haline birakmak da Python yorumlayicisi sonlanirken
            # calisir durumda kalirsa Qt6Core.dll icinde cokmeye yol acar
            # (gozlemlendi). Bu yuzden guvenli tek secenek: bitene kadar
            # bekle. Ag zaman asimi sinirli oldugundan (bkz. update_worker)
            # bu bekleme de sinirlidir.
            worker.wait()
            worker.deleteLater()
        super().closeEvent(event)

    def _save(self):
        self.settings.api_key = self.key_edit.text()
        self.settings.theme = self.theme_combo.currentData()
        self.settings.export_dir = self.dir_edit.text().strip()
        self.settings.download_dir = self.dl_dir_edit.text().strip()
        self.settings.search_method = self.method_combo.currentData()
        self.settings.exact_phrase = self.exact_check.isChecked()
        self.settings.channel_scan_scope = self.scope_combo.currentData()
        self.settings.frame_format = self.frame_combo.currentData()
        self.settings.notify_download_complete = self.notify_check.isChecked()
        self.settings.max_concurrent_downloads = self.max_concurrent_spin.value()
        self.settings.download_speed_limit_kbps = self.speed_limit_spin.value()
        self.settings.subtitle_langs = self.subtitle_langs_edit.text().strip() or "tr,en"
        self.settings.hide_downloaded = self.hide_downloaded_check.isChecked()
        self.settings.watchlist_interval_minutes = self.watchlist_interval_combo.currentData()
        self.settings.save()
        app = QApplication.instance()
        if app is not None:
            from app.ui.theme import apply_theme
            apply_theme(app, self.settings.theme)
        self.accept()
