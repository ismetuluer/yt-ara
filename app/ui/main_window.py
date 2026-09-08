"""Ana pencere: arama olcutleri, sonuc tablosu, kopyalama ve disa aktarma."""
import datetime as dt
import logging
import os
import time
import webbrowser
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QByteArray, QDate, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDateEdit, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from app.models.video import VideoResult
from app.services import export_service
from app.services.download_history import DownloadHistory
from app.services.download_service import QUALITY_OPTIONS
from app.services.ffmpeg_service import find_ffmpeg
from app.services.quota_service import QuotaTracker
from app.services.scheduled_download_service import ScheduledDownloadService
from app.services.search import SearchEngine, YouTubeApiSearchEngine, YtDlpSearchEngine
from app.services.settings_service import SettingsService
from app.services.watchlist_service import WatchlistService
from app.ui.scheduled_tab import ScheduledTab
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme import (
    ACCENT_BUTTON_OBJECT_NAME, BETA_BADGE_OBJECT_NAME, CARD_OBJECT_NAME,
    MUTED_LABEL_OBJECT_NAME, NAV_LIST_OBJECT_NAME, PAGE_TITLE_OBJECT_NAME,
    PILL_BUTTON_OBJECT_NAME, SECTION_LABEL_OBJECT_NAME, SIDEBAR_OBJECT_NAME,
    apply_theme,
)
from app.ui.watchlist_tab import WatchlistTab
from app.utils.paths import default_download_dir
from app.workers.app_update_worker import AppUpdateWorker
from app.workers.download_worker import DownloadWorker
from app.workers.search_worker import SearchTask, SearchWorker
from app.workers.update_worker import YtDlpUpdateWorker
from app.workers.watchlist_worker import WatchlistWorker

COL_NO, COL_TITLE, COL_CHANNEL, COL_DATE, COL_URL = range(5)
HEADERS = ["No", "Video Başlığı", "Kanal", "Yayın Tarihi", "Video Adresi"]
CACHE_TTL = 300  # saniye; ayni aramanin tekrarini onler
# Sol kenar cubugundaki gezinme baslikları; sirasi QStackedWidget'taki
# sayfa sirasiyla birebir ayni olmalidir.
NAV_ITEMS = ["Sonuçlar", "Geçmiş", "Zamanlanmış", "İzleme listesi"]
# Bolme durumu kaydinin duzen surumu (bkz. _restore_window_state).
_SPLITTER_STATE_VERSION = "v2:"
DOWNLOADED_COLOR = QColor(198, 239, 206)  # indirilen videolari vurgulamak icin
# Vurgu rengi acik oldugundan, koyu temada da okunabilmesi icin metin
# rengi de birlikte sabitlenir (tema rengine birakilmaz).
DOWNLOADED_TEXT_COLOR = QColor(20, 40, 24)
# Tarih araligi hazir sablonlari: (etiket, baslangic gun once, bitis gun once)
DATE_PRESETS = [
    ("Bugün", 0, 0),
    ("Dün", 1, 1),
    ("Son 1 hafta", 7, 0),
    ("Son 1 ay", 30, 0),
    ("Son 3 ay", 90, 0),
    ("Son 6 ay", 182, 0),
    ("Son 1 yıl", 365, 0),
]


class SortableItem(QTableWidgetItem):
    """UserRole icinde saklanan siralanabilir degere gore karsilastirir."""

    def __lt__(self, other):
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        return super().__lt__(other)


def validate_inputs(query, use_dates, date_from, date_to):
    """Girdi dogrulama. Hata mesaji (Turkce) ya da None dondurur."""
    if not query:
        return "Lütfen bir arama ifadesi girin."
    if use_dates and date_from and date_to and date_to < date_from:
        return "Bitiş tarihi başlangıç tarihinden önce olamaz."
    return None


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsService):
        super().__init__()
        self.settings = settings
        self.log = logging.getLogger("yt_ara.ui")
        self.results: list[VideoResult] = []
        self.result_ids: set[str] = set()
        self.channels = []
        self.tokens: dict = {}
        self.has_more = False
        self._history = DownloadHistory()
        self._quota = QuotaTracker(settings)
        self._history_records: dict = {}
        self._history_undo_stack: list = []
        self._history_redo_stack: list = []
        self._downloaded_urls: set[str] = self._load_downloaded_urls()
        self._open_download_dialogs: list = []
        self._worker: SearchWorker | None = None
        self._update_worker: YtDlpUpdateWorker | None = None
        self._app_update_worker: AppUpdateWorker | None = None
        self._cache: dict = {}
        self._user_sorted = False  # kullanici baslikla siralama secti mi
        self._signature = None
        # Zamanlanmis indirmeler + izleme listesi (JDownloader benzeri
        # otomasyon ozellikleri)
        self._scheduler = ScheduledDownloadService()
        self._watchlist = WatchlistService()
        self._watchlist_worker: WatchlistWorker | None = None
        self._headless_workers: list = []  # dialog acmadan calisan indirme is parcaciklari

        self.setWindowTitle("YouTube Gelişmiş Arama (Beta)")
        self.resize(1024, 700)
        self._build_ui()
        # Acilistan kisa bir sure sonra yt-dlp'yi sessizce denetle/guncelle
        QTimer.singleShot(1500, self._auto_update_ytdlp)
        # Uygulamanin kendi surumunu de (GitHub Releases) sessizce denetler;
        # yt-dlp'nin aksine yeni surumu OTOMATIK UYGULAMAZ (uygulamayi
        # kapatip yeniden baslatmayi gerektirir) -- yalnizca kullaniciya
        # haber verir, gercek guncelleme Ayarlar'dan onayla baslatilir.
        QTimer.singleShot(3000, self._auto_check_app_update)

        # Zamanlanmis indirmeleri duzenli denetle (uygulama kapaliyken
        # zamani gelmis olabilecekler icin acilista da bir kez bakilir).
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._check_scheduled_downloads)
        self._schedule_timer.start(30_000)
        QTimer.singleShot(5_000, self._check_scheduled_downloads)

        # Izleme listesini duzenli denetle.
        self._watchlist_timer = QTimer(self)
        self._watchlist_timer.timeout.connect(self._check_watchlist_now)
        self._watchlist_timer.start(self.settings.watchlist_interval_minutes * 60_000)
        QTimer.singleShot(20_000, self._check_watchlist_now)

    # ================================================================ arayuz
    def _build_ui(self):
        """Sol kenar cubugu + sag icerik duzeni.

        Onceki duzende her sey (arama olcutleri, kanallar, sonuclar) alt
        alta diziliyordu; genis ama kisa ekranlarda (dizustu, ultra-wide)
        dikey alan yetmiyordu. Degismeyen denetimler (kanallar, gezinme,
        ayarlar) sol kenar cubuguna alinarak dikey yigin yataya dagitildi.
        """
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self._build_sidebar())
        self.splitter.addWidget(self._build_content())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setHandleWidth(1)
        # Ayirici surukletildiginde bir bolum tamamen kaybolmasin.
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([260, 780])
        root.addWidget(self.splitter)

        self._update_method_label()
        self._restore_window_state()

        self.status_progress = QProgressBar()
        self.status_progress.setMaximumWidth(160)
        self.status_progress.setMaximumHeight(14)
        self.status_progress.setTextVisible(False)
        self.status_progress.setRange(0, 0)
        self.status_progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.status_progress)
        self.statusBar().showMessage("Hazır")

    # ------------------------------------------------------------ kenar cubugu
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName(SIDEBAR_OBJECT_NAME)
        side.setMinimumWidth(210)
        side.setMaximumWidth(380)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(8)

        # Marka satiri
        brand = QHBoxLayout()
        brand.setSpacing(6)
        title = QLabel("YouTube Arama")
        font = title.font()
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)
        beta_label = QLabel("BETA")
        beta_label.setObjectName(BETA_BADGE_OBJECT_NAME)
        beta_label.setToolTip(
            "Bu uygulama henüz kararlı (stable) sürüm değil; hatalarla karşılaşabilirsiniz.")
        brand.addWidget(title)
        brand.addWidget(beta_label)
        brand.addStretch(1)
        lay.addLayout(brand)
        lay.addSpacing(4)

        # Gezinme (eski sekmelerin yerini alir)
        self.nav_list = QListWidget()
        self.nav_list.setObjectName(NAV_LIST_OBJECT_NAME)
        for label in NAV_ITEMS:
            self.nav_list.addItem(QListWidgetItem(label))
        self.nav_list.setCurrentRow(0)
        self.nav_list.setFocusPolicy(Qt.NoFocus)
        self.nav_list.setFixedHeight(len(NAV_ITEMS) * 36 + 8)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        lay.addWidget(self.nav_list)
        lay.addSpacing(6)

        # Kanallar
        lay.addWidget(self._section_label("KANALLAR"))
        ch_hint = QLabel("Kanal eklemezsen tüm YouTube'da ararız.")
        ch_hint.setObjectName(MUTED_LABEL_OBJECT_NAME)
        ch_hint.setWordWrap(True)
        lay.addWidget(ch_hint)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("Kanal adresi yapıştır")
        self.channel_edit.returnPressed.connect(self.add_channel)
        self.add_channel_btn = QPushButton("Ekle")
        self.add_channel_btn.clicked.connect(self.add_channel)
        add_row.addWidget(self.channel_edit, 1)
        add_row.addWidget(self.add_channel_btn)
        lay.addLayout(add_row)

        self.channel_list = QListWidget()
        self.channel_list.setMinimumHeight(80)
        self.channel_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.channel_list.itemDoubleClicked.connect(self._rename_channel)
        self.channel_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.channel_list.customContextMenuRequested.connect(self._channel_context_menu)
        lay.addWidget(self.channel_list, 1)

        # Kenar cubugu dar oldugundan dort dugme tek satira sigmaz; iki
        # satira bolunur.
        self.select_all_channels_btn = QPushButton("Hepsini seç")
        self.select_all_channels_btn.clicked.connect(self._select_all_channels)
        self.clear_channel_selection_btn = QPushButton("Temizle")
        self.clear_channel_selection_btn.clicked.connect(self._clear_channel_selection)
        self.remove_channel_btn = QPushButton("Sil")
        self.remove_channel_btn.clicked.connect(self.remove_channel)
        self.rename_channel_btn = QPushButton("Adlandır")
        self.rename_channel_btn.clicked.connect(self._rename_selected_channel)
        for first, second in ((self.select_all_channels_btn, self.clear_channel_selection_btn),
                              (self.remove_channel_btn, self.rename_channel_btn)):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(first, 1)
            row.addWidget(second, 1)
            lay.addLayout(row)

        self.exclude_channels_check = QCheckBox("Bu kanalları hariç tut")
        self.exclude_channels_check.setToolTip(
            "Açıkken, işaretli kanallar arama kapsamı değil; tüm YouTube'da "
            "arayıp bu kanalların videolarını sonuçlardan çıkarır.")
        lay.addWidget(self.exclude_channels_check)

        self._load_saved_channels()

        lay.addSpacing(6)
        self.downloads_btn = QPushButton("İndirmeler")
        self.downloads_btn.setVisible(False)
        self.downloads_btn.clicked.connect(self._show_download_dialogs)
        lay.addWidget(self.downloads_btn)
        self.settings_btn = QPushButton("Ayarlar")
        self.settings_btn.clicked.connect(self.open_settings)
        lay.addWidget(self.settings_btn)
        return side

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(SECTION_LABEL_OBJECT_NAME)
        return label

    # ------------------------------------------------------------ icerik alani
    def _build_content(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(18, 14, 18, 8)
        lay.setSpacing(12)

        head = QHBoxLayout()
        self.page_title = QLabel(NAV_ITEMS[0])
        self.page_title.setObjectName(PAGE_TITLE_OBJECT_NAME)
        self.method_label = QLabel()
        self.method_label.setObjectName(MUTED_LABEL_OBJECT_NAME)
        head.addWidget(self.page_title)
        head.addStretch(1)
        head.addWidget(self.method_label)
        lay.addLayout(head)

        lay.addWidget(self._build_search_card())

        self.pages = QStackedWidget()
        self._build_pages()
        lay.addWidget(self.pages, 1)
        return content

    def _build_search_card(self) -> QWidget:
        """Arama olcutleri: uc kompakt satirda tek bir kart icinde."""
        self.search_card = QFrame()
        self.search_card.setObjectName(CARD_OBJECT_NAME)
        card = QVBoxLayout(self.search_card)
        card.setContentsMargins(14, 12, 14, 12)
        card.setSpacing(9)

        # 1. satir: arama kutusu + Ara / Iptal
        row = QHBoxLayout()
        row.setSpacing(8)
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("Ne aramak istersin?")
        self.query_edit.setMinimumHeight(34)
        self.query_edit.returnPressed.connect(self.start_search)
        self.search_btn = QPushButton("Ara")
        self.search_btn.setObjectName(ACCENT_BUTTON_OBJECT_NAME)
        self.search_btn.setMinimumHeight(34)
        self.search_btn.setMinimumWidth(96)
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.clicked.connect(self.start_search)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setMinimumHeight(34)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_search)
        row.addWidget(self.query_edit, 1)
        row.addWidget(self.search_btn)
        row.addWidget(self.cancel_btn)
        card.addLayout(row)

        # 2. satir: tarih araligi + tam eslesme
        today = dt.date.today()
        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        self.date_from = QDateEdit(today)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_to = QDateEdit(today)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        from_label = QLabel("Başlangıç")
        from_label.setObjectName(MUTED_LABEL_OBJECT_NAME)
        to_label = QLabel("Bitiş")
        to_label.setObjectName(MUTED_LABEL_OBJECT_NAME)
        date_row.addWidget(from_label)
        date_row.addWidget(self.date_from)
        date_row.addSpacing(10)
        date_row.addWidget(to_label)
        date_row.addWidget(self.date_to)
        date_row.addStretch(1)
        self.exact_phrase_check = QCheckBox("Tam eşleşme")
        self.exact_phrase_check.setToolTip(
            "Açıkken arama ifadesi kelimelere bölünmeden bütün olarak eşleştirilir.")
        self.exact_phrase_check.setChecked(self.settings.exact_phrase)
        self.exact_phrase_check.toggled.connect(self._on_exact_phrase_toggled)
        date_row.addWidget(self.exact_phrase_check)
        card.addLayout(date_row)

        # 3. satir: hazir tarih araliklari
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for label, start_back, end_back in DATE_PRESETS:
            btn = QPushButton(label)
            btn.setObjectName(PILL_BUTTON_OBJECT_NAME)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _=False, s=start_back, e=end_back: self._apply_date_preset(s, e))
            preset_row.addWidget(btn)
        preset_row.addStretch(1)
        card.addLayout(preset_row)
        return self.search_card

    def _on_nav_changed(self, index: int):
        if index < 0:
            return
        self.pages.setCurrentIndex(index)
        self.page_title.setText(NAV_ITEMS[index])
        # Arama olcutleri yalnizca "Sonuçlar" sayfasinda anlamli.
        self.search_card.setVisible(index == 0)
        self._on_results_tab_changed(index)

    # ------------------------------------------------------------ sayfalar
    def _build_pages(self):
        search_tab = QWidget()
        res_layout = QVBoxLayout(search_tab)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_top = QHBoxLayout()
        self.count_label = QLabel("0 sonuç")
        self.more_btn = QPushButton("Daha fazla")
        self.more_btn.setEnabled(False)
        self.more_btn.clicked.connect(lambda: self.continue_search(fetch_all=False))
        self.all_btn = QPushButton("Tümünü getir")
        self.all_btn.setEnabled(False)
        self.all_btn.clicked.connect(lambda: self.continue_search(fetch_all=True))
        res_top.addWidget(self.count_label)
        res_top.addStretch(1)
        res_top.addWidget(self.more_btn)
        res_top.addWidget(self.all_btn)
        res_layout.addLayout(res_top)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._open_current_video)
        header = self.table.horizontalHeader()
        header.sortIndicatorChanged.connect(lambda *_: setattr(self, "_user_sorted", True))
        header.setSectionResizeMode(COL_NO, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_CHANNEL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_DATE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_URL, QHeaderView.Interactive)
        self.table.setColumnWidth(COL_URL, 290)
        self.table.verticalHeader().setVisible(False)
        res_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.copy_sel_btn = QPushButton("Seçilenleri kopyala")
        self.copy_sel_btn.clicked.connect(self.copy_selected)
        self.copy_all_btn = QPushButton("Tümünü kopyala")
        self.copy_all_btn.clicked.connect(self.copy_all)
        self.txt_btn = QPushButton("TXT olarak kaydet")
        txt_menu = QMenu(self)
        txt_menu.addAction("Tümünü kaydet", lambda: self.export_txt(grouped=False))
        txt_menu.addAction("Kanala göre grupla",
                           lambda: self.export_txt(grouped=True))
        self.txt_btn.setMenu(txt_menu)
        self.download_all_btn = QPushButton("Tümünü indir")
        self.download_all_btn.clicked.connect(self.download_all)
        for b in (self.copy_sel_btn, self.copy_all_btn, self.txt_btn, self.download_all_btn):
            btn_row.addWidget(b)
        res_layout.addLayout(btn_row)
        self.pages.addWidget(search_tab)

        # --- Gecmis (daha once indirilenler)
        history_tab = QWidget()
        hist_layout = QVBoxLayout(history_tab)
        hist_layout.setContentsMargins(0, 0, 0, 0)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(
            ["Video Başlığı", "İndirme Tarihi", "Durum", "Video Adresi"])
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.doubleClicked.connect(self._open_history_video)
        self.history_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self._history_context_menu)
        hheader = self.history_table.horizontalHeader()
        hheader.setSectionResizeMode(0, QHeaderView.Stretch)
        hheader.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(3, QHeaderView.Interactive)
        self.history_table.setColumnWidth(3, 290)
        self.history_table.verticalHeader().setVisible(False)
        hist_layout.addWidget(self.history_table)
        hist_btn_row = QHBoxLayout()
        self.refresh_history_btn = QPushButton("Yenile")
        self.refresh_history_btn.clicked.connect(self._load_history_tab)
        hist_btn_row.addStretch(1)
        hist_btn_row.addWidget(self.refresh_history_btn)
        hist_layout.addLayout(hist_btn_row)
        self.pages.addWidget(history_tab)

        # --- Zamanlanmis indirmeler
        self.scheduled_tab = ScheduledTab(self._scheduler)
        self.pages.addWidget(self.scheduled_tab)

        # --- Izleme listesi (kanal + anahtar kelime ile otomatik indirme)
        self.watchlist_tab = WatchlistTab(
            self._watchlist, self._resolve_channel_name, self._prime_watch,
            self._check_watchlist_now)
        self.pages.addWidget(self.watchlist_tab)

    # ================================================================ pencere durumu
    def _restore_window_state(self):
        """Pencere konumu/boyutu ve bolum boyutlari onceki oturumdan geri yuklenir."""
        geo = self.settings.window_geometry
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromHex(geo.encode("ascii")))
            except Exception:
                pass
        state = self.settings.splitter_state
        # Kaydedilen durum yonlendirmeyi de tasir: eski (dikey, ust/alt)
        # duzenden kalan bir durum geri yuklenirse yeni yatay kenar cubugu
        # duzenini dikeye cevirir. Bu yuzden durum surumlenir; farkli
        # surumdeki kayitlar sessizce yok sayilir.
        if state.startswith(_SPLITTER_STATE_VERSION):
            try:
                self.splitter.restoreState(QByteArray.fromHex(
                    state[len(_SPLITTER_STATE_VERSION):].encode("ascii")))
            except Exception:
                pass

    def _save_window_state(self):
        self.settings.window_geometry = bytes(self.saveGeometry().toHex()).decode("ascii")
        self.settings.splitter_state = _SPLITTER_STATE_VERSION + bytes(
            self.splitter.saveState().toHex()).decode("ascii")
        self.settings.save()

    # ================================================================ kanal listesi
    def _load_saved_channels(self):
        for entry in self.settings.saved_channels:
            item = self._add_channel_item(entry["url"], entry.get("name", ""))
            item.setCheckState(Qt.Checked if entry.get("active", True) else Qt.Unchecked)

    def _save_channels(self):
        entries = []
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            entries.append({
                "url": item.data(Qt.UserRole),
                "name": item.data(Qt.UserRole + 1) or "",
                "active": item.checkState() == Qt.Checked,
            })
        self.settings.saved_channels = entries
        self.settings.save()

    def _add_channel_item(self, url: str, name: str = "") -> QListWidgetItem:
        item = QListWidgetItem(name or url)
        item.setData(Qt.UserRole, url)
        item.setData(Qt.UserRole + 1, name)
        item.setToolTip(url)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.channel_list.addItem(item)
        return item

    def add_channel(self, name: str = ""):
        text = self.channel_edit.text().strip()
        if not text:
            return
        for i in range(self.channel_list.count()):
            if self.channel_list.item(i).data(Qt.UserRole) == text:
                self.channel_edit.clear()
                return
        if not name:
            name = self._resolve_channel_name(text)
        self._add_channel_item(text, name)
        self.channel_edit.clear()
        self._save_channels()

    def _resolve_channel_name(self, url: str) -> str:
        """Kanal adini kanal adresinden otomatik cozmeyi dener.

        Bulunamazsa (agsiz, gecersiz adres vb.) sessizce bos dondurur;
        kullanici istedigi zaman elle yeniden adlandirabilir."""
        self.statusBar().showMessage("Kanal adı alınıyor...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            engine = self._build_engine()
            _, title = engine.resolve_channel(url)
            return title
        except Exception as exc:
            self.log.info("Kanal adi otomatik cozulemedi: %s", exc)
            return ""
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage("Hazır")

    def remove_channel(self):
        for item in self.channel_list.selectedItems():
            self.channel_list.takeItem(self.channel_list.row(item))
        self._save_channels()

    def _select_all_channels(self):
        """Hepsini Sec: satirlari secer VE hepsini isaretler (arama kapsamina alir)."""
        self.channel_list.selectAll()
        for i in range(self.channel_list.count()):
            self.channel_list.item(i).setCheckState(Qt.Checked)
        self._save_channels()

    def _clear_channel_selection(self):
        """Secimi Temizle: satir secimini kaldirir VE tum isaretleri kaldirir."""
        self.channel_list.clearSelection()
        for i in range(self.channel_list.count()):
            self.channel_list.item(i).setCheckState(Qt.Unchecked)
        self._save_channels()

    def _rename_selected_channel(self):
        items = self.channel_list.selectedItems()
        if not items:
            self.statusBar().showMessage("Yeniden adlandırmak için bir kanal seçin.")
            return
        self._rename_channel(items[0])

    def _rename_channel(self, item: QListWidgetItem):
        current_name = item.data(Qt.UserRole + 1) or ""
        url = item.data(Qt.UserRole)
        new_name, ok = QInputDialog.getText(
            self, "Kanalı Yeniden Adlandır", "Kanal adı:", text=current_name)
        if not ok:
            return
        new_name = new_name.strip()
        item.setData(Qt.UserRole + 1, new_name)
        item.setText(new_name or url)
        self._save_channels()

    def _channel_context_menu(self, pos):
        item = self.channel_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        rename_act = menu.addAction("Yeniden Adlandır")
        remove_act = menu.addAction("Kaldır")
        action = menu.exec(self.channel_list.viewport().mapToGlobal(pos))
        if action == rename_act:
            self._rename_channel(item)
        elif action == remove_act:
            self.channel_list.takeItem(self.channel_list.row(item))
            self._save_channels()

    def _channel_inputs(self) -> list:
        """Kayitli tum kanal adresleri (secili/secisiz farketmeksizin)."""
        return [self.channel_list.item(i).data(Qt.UserRole)
                for i in range(self.channel_list.count())]

    def _active_channel_inputs(self) -> list:
        """Aramada kullanilacak, isareti acik kanal adresleri."""
        return [self.channel_list.item(i).data(Qt.UserRole)
                for i in range(self.channel_list.count())
                if self.channel_list.item(i).checkState() == Qt.Checked]

    def _add_channel_from_video(self, video: VideoResult):
        if not video.channel_id:
            self.statusBar().showMessage("Bu videonun kanal bilgisi alınamadı.")
            return
        url = f"https://www.youtube.com/channel/{video.channel_id}"
        self.channel_edit.setText(url)
        self.add_channel(name=video.channel_title)
        self.statusBar().showMessage(f"Kanal eklendi: {video.channel_title}")

    def _apply_date_preset(self, start_days_back: int, end_days_back: int):
        today = dt.date.today()
        self.date_from.setDate(QDate.fromString(
            (today - dt.timedelta(days=start_days_back)).isoformat(), "yyyy-MM-dd"))
        self.date_to.setDate(QDate.fromString(
            (today - dt.timedelta(days=end_days_back)).isoformat(), "yyyy-MM-dd"))

    def _on_exact_phrase_toggled(self, checked: bool):
        self.settings.exact_phrase = checked
        self.settings.save()

    # ================================================================ arama
    def _build_engine(self) -> SearchEngine:
        """Secilen arama yontemine gore motor olusturur."""
        method = self.settings.search_method
        if method == "api":
            return YouTubeApiSearchEngine(self.settings.api_key, quota_tracker=self._quota)
        if method == "ytdlp":
            engine = YtDlpSearchEngine()
            engine.set_channel_scan_limit(self._scan_limit())
            return engine
        # auto: API anahtari varsa API, yoksa yt-dlp
        if self.settings.api_key:
            return YouTubeApiSearchEngine(self.settings.api_key, quota_tracker=self._quota)
        engine = YtDlpSearchEngine()
        engine.set_channel_scan_limit(self._scan_limit())
        return engine

    def _update_method_label(self):
        method = self.settings.search_method
        if method == "api":
            text = "Yöntem: YouTube API"
        elif method == "ytdlp":
            text = "Yöntem: API'siz"
        else:
            text = "Yöntem: YouTube API" if self.settings.api_key else "Yöntem: API'siz"
        self.method_label.setText(text)

    def _scan_limit(self) -> int:
        scope = self.settings.channel_scan_scope
        return {"100": 100, "500": 500, "1000": 1000, "all": 2000}.get(scope, 100)

    def start_search(self):
        if self._worker is not None:
            return
        query = self.query_edit.text().strip()
        d_from = self.date_from.date().toPython()
        d_to = self.date_to.date().toPython()

        error = validate_inputs(query, True, d_from, d_to)
        if error:
            QMessageBox.warning(self, "Geçersiz Giriş", error)
            return

        # API yontemi secildiyse anahtar gerekli
        method = self.settings.search_method
        if method == "api" and not self.settings.api_key:
            QMessageBox.information(
                self, "API Anahtarı Gerekli",
                "YouTube API yöntemi için bir API anahtarı gereklidir.\n"
                "Şimdi Ayarlar penceresi açılacak; lütfen anahtarınızı girin "
                "veya 'API'siz' yöntemini seçin.")
            self.open_settings()
            if not self.settings.api_key:
                return

        inputs = self._active_channel_inputs()
        # "Hariç Tut" isaretliyse secili kanallar arama kapsami degil,
        # tum YouTube'da aranip sonuclardan cikarilacak kanallar olur.
        exclude_mode = self.exclude_channels_check.isChecked() and bool(inputs)
        search_channel_inputs = [] if exclude_mode else inputs
        exclude_inputs = inputs if exclude_mode else []
        signature = (query, d_from, d_to, tuple(search_channel_inputs),
                     tuple(exclude_inputs), self.exact_phrase_check.isChecked())
        if self._load_from_cache(signature):
            return

        # Yeni arama, tablodaki mevcut sonuclari SILMEZ; yeni sonuclar
        # eklenir (mukerrerler zaten result_ids ile atlanir).
        self.tokens = {}
        self.channels = []
        self._signature = signature
        task = SearchTask(
            query=query, date_from=d_from, date_to=d_to,
            channel_inputs=search_channel_inputs,
            exclude_channel_inputs=exclude_inputs,
            exact_phrase=self.exact_phrase_check.isChecked(),
            channel_scan_scope=self.settings.channel_scan_scope,
        )
        self.log.info("Yeni arama: q=%r tarih=%s..%s kanal=%d haric=%d yontem=%s",
                      query, d_from, d_to, len(search_channel_inputs),
                      len(exclude_inputs), method)
        self._launch_worker(task, resolved_channels=None, is_new=True)

    def continue_search(self, fetch_all: bool):
        if self._worker is not None or not self.has_more:
            return
        if fetch_all:
            answer = QMessageBox.question(
                self, "Tümünü getir",
                "Büyük aramalarda bu işlem uzun sürebilir ve API kotanızı hızlı "
                "tüketebilir.\nDevam edilsin mi?")
            if answer != QMessageBox.Yes:
                return
        inputs = self._active_channel_inputs()
        exclude_inputs = inputs if (self.exclude_channels_check.isChecked() and bool(inputs)) else []
        task = SearchTask(
            query=self.query_edit.text().strip(),
            date_from=self.date_from.date().toPython(),
            date_to=self.date_to.date().toPython(),
            exclude_channel_inputs=exclude_inputs,
            page_tokens=dict(self.tokens),
            fetch_all=fetch_all,
            exact_phrase=self.exact_phrase_check.isChecked(),
            channel_scan_scope=self.settings.channel_scan_scope,
        )
        self._launch_worker(task, resolved_channels=self.channels, is_new=False)

    def _launch_worker(self, task: SearchTask, resolved_channels, is_new: bool):
        engine = self._build_engine()
        self._worker = SearchWorker(
            engine, task,
            resolved_channels=resolved_channels,
            existing_ids=self.result_ids,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.partial.connect(self._on_partial)
        self._worker.search_done.connect(
            lambda channels, tokens, more, canceled, new=is_new:
            self._on_search_done(channels, tokens, more, canceled, new))
        self._worker.failed.connect(self._on_failed)
        self._is_new_search = is_new
        self._set_busy(True)
        self.statusBar().showMessage("Aranıyor...")
        self._worker.start()

    def cancel_search(self):
        if self._worker is not None:
            self._worker.cancel()
            self.statusBar().showMessage("İptal ediliyor...")

    # ------------------------------------------------------------ worker geri cagrilari
    def _on_progress(self, message: str):
        self.statusBar().showMessage(message)

    def _on_partial(self, videos, channels):
        """Arama devam ederken hazir olan sonuclar gelir; liste aninda guncellenir."""
        self.channels = channels
        self._append_rows(videos)
        self._update_count()
        self.statusBar().showMessage(f"{len(self.results)} sonuç bulundu, aranmaya devam ediliyor...")

    def _on_search_done(self, channels, tokens, has_more, canceled, is_new):
        self._set_busy(False)
        self._finish_worker()
        self.channels = channels
        self.tokens = tokens
        self.has_more = has_more
        self.more_btn.setEnabled(has_more)
        self.all_btn.setEnabled(has_more)

        if canceled:
            self.statusBar().showMessage(
                f"Arama iptal edildi. {len(self.results)} sonuç korundu.")
        elif not self.results:
            self.statusBar().showMessage("Sonuç bulunamadı.")
        elif has_more:
            self.statusBar().showMessage(
                f"{len(self.results)} sonuç gösteriliyor — devamı için "
                f"'Daha fazla'.")
        else:
            self.statusBar().showMessage(f"Tüm sonuçlar getirildi: {len(self.results)} video.")

        if is_new and self.results and not canceled:
            self._cache[self._signature] = {
                "time": time.time(),
                "videos": list(self.results),
                "channels": list(channels),
                "tokens": dict(tokens),
                "has_more": has_more,
            }
            while len(self._cache) > 10:
                self._cache.pop(next(iter(self._cache)))

    def _on_failed(self, message: str):
        self._set_busy(False)
        self._finish_worker()
        self.statusBar().showMessage("Arama başarısız.")
        QMessageBox.warning(self, "Arama Hatası", message)

    def _finish_worker(self):
        if self._worker is not None:
            self._worker.wait(3000)
            self._worker.deleteLater()
            self._worker = None

    def _set_busy(self, busy: bool):
        self.search_btn.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.more_btn.setEnabled(not busy and self.has_more)
        self.all_btn.setEnabled(not busy and self.has_more)
        self.settings_btn.setEnabled(not busy)
        self.status_progress.setVisible(busy)

    # ------------------------------------------------------------ onbellek
    def _load_from_cache(self, signature) -> bool:
        entry = self._cache.get(signature)
        if not entry or time.time() - entry["time"] > CACHE_TTL:
            return False
        self.channels = list(entry["channels"])
        self.tokens = dict(entry["tokens"])
        self.has_more = entry["has_more"]
        self._signature = signature
        self._append_rows(entry["videos"])  # mevcut sonuclari silmez
        self._update_count()
        self.more_btn.setEnabled(self.has_more)
        self.all_btn.setEnabled(self.has_more)
        self.statusBar().showMessage(
            f"Aynı arama önbellekten yüklendi ({len(entry['videos'])} sonuç) — API kullanılmadı.")
        return True

    # ================================================================ tablo
    def _set_row_items(self, row: int, no: int, video: VideoResult):
        no_item = SortableItem(str(no))
        no_item.setData(Qt.UserRole, no)
        title_item = SortableItem(video.title)
        title_item.setData(Qt.UserRole, video.title.casefold())
        ch_item = SortableItem(video.channel_title)
        ch_item.setData(Qt.UserRole, video.channel_title.casefold())
        date_item = SortableItem(video.published_display)
        date_item.setData(Qt.UserRole, video.published_sort_key)
        url_item = SortableItem(video.url)
        items = (no_item, title_item, ch_item, date_item, url_item)
        for col, item in zip((COL_NO, COL_TITLE, COL_CHANNEL, COL_DATE, COL_URL), items):
            self.table.setItem(row, col, item)
        if video.url in self._downloaded_urls:
            for item in items:
                item.setBackground(DOWNLOADED_COLOR)
                item.setForeground(DOWNLOADED_TEXT_COLOR)

    def _sort_table(self):
        if self._user_sorted:
            header = self.table.horizontalHeader()
            self.table.sortItems(header.sortIndicatorSection(),
                                 header.sortIndicatorOrder())
        else:
            # varsayilan: en yeni videodan en eskiye
            self.table.sortItems(COL_DATE, Qt.DescendingOrder)
        self._renumber_rows()

    def _renumber_rows(self):
        """No sutununu gorunen sira ile eslestirir.

        No degeri onceden satirin eklendigi (arama sirasindaki) sirayi
        gosteriyordu; tablo tarihe gore siralaninca bu sira gorunumle
        eslesmiyor, "duzensiz" gorunuyordu. Her siralamadan sonra
        yeniden numaralandirilarak 1'den baslayip gorunen sirayi izler.
        """
        self.table.setSortingEnabled(False)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_NO)
            if item is not None:
                item.setText(str(row + 1))
                item.setData(Qt.UserRole, row + 1)
        self.table.setSortingEnabled(True)

    def _visible_videos(self) -> list[VideoResult]:
        """Ayar acikken daha once indirilmis videolari sonuc listesinden gizler."""
        if self.settings.hide_downloaded:
            return [v for v in self.results if v.url not in self._downloaded_urls]
        return self.results

    def _rebuild_table(self):
        """Tabloyu sifirdan olusturur (yeni arama veya onbellekten yukleme)."""
        visible = self._visible_videos()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(visible))
        for row, video in enumerate(visible):
            self._set_row_items(row, row + 1, video)
        self.table.setSortingEnabled(True)
        self._sort_table()
        self._update_count()

    def _append_rows(self, videos: list[VideoResult]):
        """Arama devam ederken yeni gelen sonuclari, mevcut secimi bozmadan ekler."""
        added = [v for v in videos if v.video_id not in self.result_ids]
        if not added:
            return
        for video in added:
            self.result_ids.add(video.video_id)
            self.results.append(video)
        visible_added = [v for v in added
                        if not (self.settings.hide_downloaded and v.url in self._downloaded_urls)]
        self._update_count()
        if not visible_added:
            return
        self.table.setSortingEnabled(False)
        start = self.table.rowCount()
        self.table.setRowCount(start + len(visible_added))
        for i, video in enumerate(visible_added):
            self._set_row_items(start + i, start + i + 1, video)
        self.table.setSortingEnabled(True)
        self._sort_table()

    def _load_downloaded_urls(self) -> set[str]:
        try:
            return self._history.completed_urls()
        except Exception:
            return set()

    def _on_results_tab_changed(self, index: int):
        if index == 1:
            self._load_history_tab()
        elif index == 2:
            self.scheduled_tab.refresh()
        elif index == 3:
            self.watchlist_tab.refresh()

    def _load_history_tab(self):
        records = self._history.recent(200)
        self._history_records = {rec["id"]: rec for rec in records}
        self.history_table.setSortingEnabled(False)
        self.history_table.setRowCount(len(records))
        status_labels = {"tamam": "Tamamlandı", "hata": "Hata"}
        for row, rec in enumerate(records):
            title_item = QTableWidgetItem(rec.get("title") or "")
            title_item.setData(Qt.UserRole, rec.get("id"))
            date_item = QTableWidgetItem(rec.get("downloaded_at") or "")
            status = rec.get("status") or ""
            status_item = QTableWidgetItem(status_labels.get(status, status))
            url_item = QTableWidgetItem(rec.get("url") or "")
            self.history_table.setItem(row, 0, title_item)
            self.history_table.setItem(row, 1, date_item)
            self.history_table.setItem(row, 2, status_item)
            self.history_table.setItem(row, 3, url_item)
        self.history_table.setSortingEnabled(True)

    def _open_history_video(self):
        row = self.history_table.currentRow()
        if row < 0:
            return
        item = self.history_table.item(row, 3)
        if item and item.text():
            webbrowser.open(item.text())

    @staticmethod
    def _video_id_from_url(url: str) -> str:
        try:
            query = parse_qs(urlparse(url).query)
            return (query.get("v") or [""])[0]
        except ValueError:
            return ""

    def _history_context_menu(self, pos):
        row = self.history_table.itemAt(pos).row() if self.history_table.itemAt(pos) else -1
        if row < 0:
            return
        self.history_table.selectRow(row)
        title = self.history_table.item(row, 0).text()
        record_id = self.history_table.item(row, 0).data(Qt.UserRole)
        url = self.history_table.item(row, 3).text()
        menu = QMenu(self)
        open_act = menu.addAction("Tarayıcıda Aç")
        redownload_act = menu.addAction("Tekrar İndir")
        channel_act = menu.addAction("Kanal Olarak Ekle")
        menu.addSeparator()
        delete_act = menu.addAction("Geçmişten Sil")
        action = menu.exec(self.history_table.viewport().mapToGlobal(pos))
        if action == open_act:
            if url:
                webbrowser.open(url)
        elif action == redownload_act:
            self._redownload_from_history(title, url)
        elif action == channel_act:
            self._add_channel_from_history(title, url)
        elif action == delete_act:
            self._delete_selected_history()

    def _redownload_from_history(self, title: str, url: str):
        video_id = self._video_id_from_url(url)
        if not video_id:
            self.statusBar().showMessage("Video adresi çözümlenemedi.")
            return
        items = [{"video_id": video_id, "title": title, "url": url}]
        from app.ui.download_dialog import DownloadDialog
        dlg = DownloadDialog(items, self.settings, self)
        dlg.setWindowModality(Qt.NonModal)
        dlg.finished.connect(lambda _res=None, d=dlg: self._on_download_dialog_finished(d))
        self._open_download_dialogs.append(dlg)
        self._update_downloads_btn()
        dlg.show()

    def _add_channel_from_history(self, title: str, url: str):
        video_id = self._video_id_from_url(url)
        if not video_id:
            self.statusBar().showMessage("Video adresi çözümlenemedi.")
            return
        self.statusBar().showMessage("Kanal bilgisi alınıyor...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            from app.services.ytdlp_service import YtDlpError, YtDlpService
            info = YtDlpService().video_metadata(video_id)
        except YtDlpError as exc:
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage(f"Kanal bilgisi alınamadı: {exc.user_message}")
            return
        QApplication.restoreOverrideCursor()
        channel_id = str(info.get("channel_id") or info.get("uploader_id") or "")
        channel_title = str(info.get("channel") or info.get("uploader") or "")
        if not channel_id:
            self.statusBar().showMessage("Bu videonun kanal bilgisi alınamadı.")
            return
        self.channel_edit.setText(f"https://www.youtube.com/channel/{channel_id}")
        self.add_channel(name=channel_title)
        self.statusBar().showMessage(f"Kanal eklendi: {channel_title or channel_id}")

    def _delete_selected_history(self):
        rows = sorted({idx.row() for idx in self.history_table.selectedIndexes()})
        ids = []
        for row in rows:
            item = self.history_table.item(row, 0)
            rid = item.data(Qt.UserRole) if item else None
            if rid is not None:
                ids.append(rid)
        if not ids:
            self.statusBar().showMessage("Silmek için geçmişten satır seçin.")
            return
        answer = QMessageBox.question(
            self, "Geçmişten Sil",
            f"{len(ids)} kayıt geçmişten kaldırılacak. Devam edilsin mi?")
        if answer != QMessageBox.Yes:
            return
        batch = [self._history_records[rid] for rid in ids if rid in self._history_records]
        for rid in ids:
            self._history.delete(rid)
        self._history_undo_stack.append(batch)
        self._history_redo_stack.clear()
        self._load_history_tab()
        self.statusBar().showMessage(f"{len(ids)} kayıt silindi. (Ctrl+Z ile geri alınabilir)")

    def _history_undo(self):
        if not self._history_undo_stack:
            self.statusBar().showMessage("Geri alınacak bir işlem yok.")
            return
        batch = self._history_undo_stack.pop()
        for rec in batch:
            self._history.add(rec.get("title", ""), rec.get("url", ""),
                              rec.get("file_path"), rec.get("status", "tamam"))
        self._history_redo_stack.append(batch)
        self._load_history_tab()
        self.statusBar().showMessage(f"{len(batch)} kayıt geri yüklendi.")

    def _history_redo(self):
        if not self._history_redo_stack:
            self.statusBar().showMessage("Yinelenecek bir işlem yok.")
            return
        batch = self._history_redo_stack.pop()
        for rec in batch:
            matches = [rid for rid, r in self._history_records.items()
                      if r.get("url") == rec.get("url")
                      and r.get("downloaded_at") == rec.get("downloaded_at")]
            for rid in matches:
                self._history.delete(rid)
        self._history_undo_stack.append(batch)
        self._load_history_tab()
        self.statusBar().showMessage(f"{len(batch)} kayıt yeniden silindi.")

    def _highlight_downloaded(self, urls: set[str]):
        """Indirilen videolari tabloda arka plan rengiyle vurgular.

        "İndirilenleri gizle" ayari acikken, yeni indirilenler vurgulanmak
        yerine dogrudan listeden kaldirilir (tablo yeniden olusturulur).
        """
        if not urls:
            return
        self._downloaded_urls |= urls
        if self.settings.hide_downloaded:
            self._rebuild_table()
            return
        for row in range(self.table.rowCount()):
            url_item = self.table.item(row, COL_URL)
            if url_item is None or url_item.text() not in urls:
                continue
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None:
                    item.setBackground(DOWNLOADED_COLOR)
                    item.setForeground(DOWNLOADED_TEXT_COLOR)

    def _update_count(self):
        total = len(self.results)
        shown = self.table.rowCount()
        if shown != total:
            self.count_label.setText(f"{shown} sonuç (gizlenen: {total - shown})")
        else:
            self.count_label.setText(f"{shown} sonuç")

    def _row_urls(self, rows) -> list:
        urls = []
        for row in sorted(rows):
            item = self.table.item(row, COL_URL)
            if item:
                urls.append(item.text())
        return urls

    def _selected_rows(self) -> list:
        return sorted({idx.row() for idx in self.table.selectedIndexes()})

    def _table_videos(self) -> list:
        """Tablodaki gorunum sirasina gore video listesi."""
        by_url = {v.url: v for v in self.results}
        videos = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_URL)
            if item and item.text() in by_url:
                videos.append(by_url[item.text()])
        return videos

    # ================================================================ kopyalama / acma
    def copy_selected(self):
        urls = self._row_urls(self._selected_rows())
        if not urls:
            self.statusBar().showMessage("Önce tablodan satır seçin.")
            return
        QGuiApplication.clipboard().setText("\n".join(urls))
        self.statusBar().showMessage(f"{len(urls)} video adresi panoya kopyalandı.")

    def copy_all(self):
        urls = self._row_urls(range(self.table.rowCount()))
        if not urls:
            self.statusBar().showMessage("Kopyalanacak sonuç yok.")
            return
        QGuiApplication.clipboard().setText("\n".join(urls))
        self.statusBar().showMessage(f"{len(urls)} video adresi panoya kopyalandı.")

    def _open_current_video(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, COL_URL)
        if item:
            webbrowser.open(item.text())

    def _context_menu(self, pos):
        menu = QMenu(self)
        open_act = menu.addAction("Tarayıcıda Aç")
        copy_act = menu.addAction("Video Adresini Kopyala")
        info_act = menu.addAction("Video Bilgisi")
        menu.addSeparator()
        download_act = menu.addAction("İndir")
        frames_act = menu.addAction("Görüntü Çıkar")
        channel_act = menu.addAction("Kanal Olarak Ekle")
        menu.addSeparator()
        sel_act = menu.addAction("Tümünü Seç")
        clear_act = menu.addAction("Listeyi Temizle")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == open_act:
            self._open_current_video()
        elif action == copy_act:
            self.copy_selected()
        elif action == info_act:
            self._show_video_info()
        elif action == download_act:
            self._download_selected()
        elif action == frames_act:
            self._extract_frames_selected()
        elif action == channel_act:
            self._add_channel_from_selected()
        elif action == clear_act:
            self._clear_results()
        elif action == sel_act:
            self.table.selectAll()

    def _add_channel_from_selected(self):
        videos = self._selected_videos()
        if not videos:
            self.statusBar().showMessage("Kanalını eklemek için bir video seçin.")
            return
        self._add_channel_from_video(videos[0])

    def _clear_results(self):
        if not self.results:
            return
        answer = QMessageBox.question(
            self, "Listeyi Temizle",
            f"{len(self.results)} sonuç listeden kaldırılacak. Devam edilsin mi?")
        if answer != QMessageBox.Yes:
            return
        self.results = []
        self.result_ids = set()
        self._rebuild_table()
        self._update_count()
        self.statusBar().showMessage("Liste temizlendi.")

    # ================================================================ indirme / kare
    def _selected_videos(self) -> list[VideoResult]:
        """Secili satirlarin videolarini dondurur.

        Tablo tarihe (veya kullanicinin sectigi sutuna) gore sirali
        olabilir; bu yuzden satir indeksi `self.results` indeksiyle
        eslesmeyebilir. Eslestirme URL sutunu uzerinden yapilir.
        """
        by_url = {v.url: v for v in self.results}
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        videos = []
        for row in rows:
            item = self.table.item(row, COL_URL)
            if item and item.text() in by_url:
                videos.append(by_url[item.text()])
        return videos

    @staticmethod
    def _video_to_item(video: VideoResult) -> dict:
        return {"video_id": video.video_id, "title": video.title, "url": video.url,
                "channel_title": video.channel_title}

    def _open_download_dialog(self, items: list[dict]):
        from app.ui.download_dialog import DownloadDialog
        dlg = DownloadDialog(items, self.settings, self)
        dlg.setWindowModality(Qt.NonModal)
        dlg.finished.connect(lambda _res=None, d=dlg: self._on_download_dialog_finished(d))
        self._open_download_dialogs.append(dlg)
        self._update_downloads_btn()
        dlg.show()
        return dlg

    def _download_selected(self):
        videos = self._selected_videos()
        if not videos:
            self.statusBar().showMessage("İndirilecek video seçin.")
            return
        items = [self._video_to_item(v) for v in videos]
        self._open_download_dialog(items)

    def download_all(self):
        videos = self._table_videos()
        if not videos:
            self.statusBar().showMessage("İndirilecek sonuç yok.")
            return
        if len(videos) > 20:
            answer = QMessageBox.question(
                self, "Tümünü indir",
                f"Listedeki {len(videos)} video indirilecek. Devam edilsin mi?")
            if answer != QMessageBox.Yes:
                return
        items = [self._video_to_item(v) for v in videos]
        self._open_download_dialog(items)

    def _on_download_dialog_finished(self, dlg):
        self._highlight_downloaded(dlg.completed_urls)
        if dlg in self._open_download_dialogs:
            self._open_download_dialogs.remove(dlg)
        dlg.deleteLater()
        self._update_downloads_btn()
        if self.pages.currentIndex() == 1:
            self._load_history_tab()

    def _update_downloads_btn(self):
        count = len(self._open_download_dialogs)
        self.downloads_btn.setVisible(count > 0)
        self.downloads_btn.setText(f"İndirmeler ({count})" if count else "İndirmeler")

    def _show_download_dialogs(self):
        for dlg in self._open_download_dialogs:
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    # ================================================================ zamanlanmis indirmeler
    def _check_scheduled_downloads(self):
        due = self._scheduler.due()
        if not due:
            return
        for task in due:
            self._scheduler.mark_status(task["id"], "başlatıldı")
            item = {"video_id": task["video_id"], "title": task["title"],
                    "url": task["url"], "channel_title": task.get("channel_title") or ""}
            self._start_headless_download(
                [item], quality=task["quality"], download_dir=task["download_dir"])
            self.statusBar().showMessage(f"Zamanlanmış indirme başladı: {task['title']}")
        self.scheduled_tab.refresh()

    def _start_headless_download(self, items: list[dict], quality: str | None = None,
                                 download_dir: str | None = None):
        """Pencere acmadan (izleme listesi/zamanlama gibi otomatik akislar
        icin) indirme baslatir. Sonuc, indirilenler vurgusuna ve gecmise
        normal indirmeler gibi yansir."""
        download_dir = download_dir or self.settings.download_dir or default_download_dir()
        os.makedirs(download_dir, exist_ok=True)
        quality = quality or QUALITY_OPTIONS[0][0]
        worker = DownloadWorker(
            download_dir, quality, items, self._history, ffmpeg_path=find_ffmpeg(),
            subtitles=self.settings.download_subtitles,
            subtitle_langs=self.settings.subtitle_langs,
            max_concurrent=self.settings.max_concurrent_downloads,
            speed_limit_kbps=self.settings.download_speed_limit_kbps, parent=self)
        worker.finished.connect(self._on_headless_finished)
        worker.failed.connect(
            lambda vid, title, msg: self.log.warning(
                "Otomatik indirme basarisiz: %s (%s)", title, msg))
        worker.all_done.connect(lambda done, total, w=worker: self._on_headless_done(w))
        self._headless_workers.append(worker)
        worker.start()

    def _on_headless_finished(self, video_id: str, title: str, path: str):
        self._highlight_downloaded({VideoResult.make_url(video_id)})
        if self.pages.currentIndex() == 1:
            self._load_history_tab()

    def _on_headless_done(self, worker: DownloadWorker):
        if worker in self._headless_workers:
            self._headless_workers.remove(worker)
        worker.deleteLater()

    # ================================================================ izleme listesi
    def _prime_watch(self, watch_id: int, url: str):
        """Yeni izlemeye alinan kanalin MEVCUT videolarini "gorulmus"
        isaretler; aksi halde ilk denetimde tum gecmis videolar "yeni"
        sayilip topluca indirilmeye baslar."""
        self.statusBar().showMessage("Kanal videoları taranıyor...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            from app.services.ytdlp_service import YtDlpError, YtDlpService
            from app.workers.watchlist_worker import CHECK_LIMIT
            videos = YtDlpService().channel_videos_flat(url, limit=CHECK_LIMIT)
            for video in videos:
                self._watchlist.mark_seen(watch_id, video.video_id, video.title, video.url)
            self._watchlist.mark_checked(watch_id)
        except YtDlpError as exc:
            self.log.info("Izleme baslangic taramasi basarisiz: %s", exc.user_message)
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage("Hazır")

    def _check_watchlist_now(self):
        if self._watchlist_worker is not None:
            return
        watches = self._watchlist.active()
        if not watches:
            return
        self._watchlist_worker = WatchlistWorker(watches, service=self._watchlist, parent=self)
        self._watchlist_worker.progress.connect(self._on_progress)
        self._watchlist_worker.found.connect(self._on_watchlist_found)
        self._watchlist_worker.finished.connect(self._on_watchlist_worker_done)
        self._watchlist_worker.start()

    def _on_watchlist_found(self, watch_id: int, channel_name: str, matches: list):
        self.statusBar().showMessage(
            f"İzleme listesi: {channel_name} kanalında {len(matches)} yeni video "
            "bulundu, indiriliyor...")
        self._start_headless_download(matches)
        self.watchlist_tab.refresh()

    def _on_watchlist_worker_done(self):
        if self._watchlist_worker is not None:
            self._watchlist_worker.deleteLater()
            self._watchlist_worker = None

    def _extract_frames_selected(self):
        videos = self._selected_videos()
        if not videos:
            self.statusBar().showMessage("Görüntü çıkarılacak video seçin.")
            return
        if len(videos) > 1:
            QMessageBox.information(
                self, "Görüntü Çıkarma",
                "Görüntü çıkarma tek bir video için yapılır. Lütfen bir video seçin.")
            return
        self._open_frame_dialog(videos[0])

    def _open_frame_dialog(self, video: VideoResult):
        """Video daha once indirilmisse dogrudan kare cikarma penceresini
        acar; degilse once indirilmesini teklif eder (kare cikarma icin
        dosyanin diskte olmasi gerekir)."""
        file_path = self._history.file_path_for(video.url)
        if file_path and os.path.isfile(file_path):
            from app.ui.frame_dialog import FrameDialog
            dlg = FrameDialog(file_path, video.title, self.settings, self)
            dlg.exec()
            return
        answer = QMessageBox.question(
            self, "Görüntü Çıkarma",
            "Görüntü çıkarmak için önce videonun indirilmesi gerekir.\n"
            "Şimdi indirilsin mi?")
        if answer != QMessageBox.Yes:
            return
        self._download_then_extract(video)

    def _download_then_extract(self, video: VideoResult):
        items = [self._video_to_item(video)]
        from app.ui.download_dialog import DownloadDialog
        dlg = DownloadDialog(items, self.settings, self)
        dlg.setWindowModality(Qt.NonModal)

        def _after(_res=None, d=dlg, v=video):
            self._on_download_dialog_finished(d)
            if v.url in d.completed_urls:
                self._open_frame_dialog(v)

        dlg.finished.connect(_after)
        self._open_download_dialogs.append(dlg)
        self._update_downloads_btn()
        dlg.show()

    def _show_video_info(self):
        videos = self._selected_videos()
        if not videos:
            self.statusBar().showMessage("Video seçin.")
            return
        video = videos[0]
        from app.ui.video_info_dialog import VideoInfoDialog
        dlg = VideoInfoDialog(video, self.settings, self)
        dlg.exec()

    # ================================================================ disa aktarma
    def export_txt(self, grouped: bool = False):
        if not self.results:
            self.statusBar().showMessage("Dışa aktarılacak sonuç yok.")
            return
        base_dir = self.settings.export_dir or default_download_dir()
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "TXT Olarak Kaydet", f"{base_dir}/videolar_{stamp}.txt",
            "Metin Dosyası (*.txt)")
        if not path:
            return
        videos = self._table_videos()
        try:
            if grouped:
                count = export_service.export_txt_grouped(path, videos)
            else:
                count = export_service.export_txt(path, videos)
        except OSError as exc:
            self.log.error("Disa aktarma hatasi: %s", exc)
            QMessageBox.warning(self, "Kayıt Hatası",
                                "Dosya kaydedilemedi. Klasör izinlerini kontrol edin.")
            return
        self.log.info("TXT dosyasina %d kayit aktarildi: %s", count, path)
        self.statusBar().showMessage(f"{count} kayıt kaydedildi: {path}")

    # ================================================================ ayarlar
    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        old_theme = self.settings.theme
        old_hide = self.settings.hide_downloaded
        old_interval = self.settings.watchlist_interval_minutes
        if dialog.exec():
            if self.settings.theme != old_theme:
                app = QApplication.instance()
                if app:
                    apply_theme(app, self.settings.theme)
            if self.settings.hide_downloaded != old_hide:
                self._rebuild_table()
            if self.settings.watchlist_interval_minutes != old_interval:
                self._watchlist_timer.start(self.settings.watchlist_interval_minutes * 60_000)
            self._update_method_label()
            self.statusBar().showMessage("Ayarlar kaydedildi.")

    # ================================================================ yt-dlp otomatik guncelleme
    def _auto_update_ytdlp(self):
        """Yt-dlp'yi sessizce denetler ve gerekiyorsa gunceller (gunde bir kez)."""
        if os.environ.get("YTARA_SELFTEST") == "1":
            return
        if self.settings.ytdlp_last_check == dt.date.today().isoformat():
            return
        self._update_worker = YtDlpUpdateWorker(auto=True, parent=self)
        self._update_worker.checked.connect(self._on_ytdlp_checked)
        self._update_worker.updated.connect(self._on_ytdlp_updated)
        self._update_worker.finished.connect(self._on_ytdlp_worker_done)
        self._update_worker.start()

    def _on_ytdlp_checked(self, current: str, latest: str, outdated: bool):
        self.settings.ytdlp_last_check = dt.date.today().isoformat()
        self.settings.save()
        if outdated:
            self.statusBar().showMessage(
                f"yt-dlp güncelleniyor... ({current} → {latest})")

    def _on_ytdlp_updated(self, version: str):
        self.log.info("yt-dlp otomatik guncellendi: %s", version)
        self.statusBar().showMessage(
            f"yt-dlp {version} sürümüne güncellendi.", 15000)

    def _on_ytdlp_worker_done(self):
        if self._update_worker is not None:
            self._update_worker.deleteLater()
            self._update_worker = None

    # ================================================================ uygulama guncellemesi
    def _auto_check_app_update(self):
        """Uygulama surumunu her acilista sessizce denetler.

        yt-dlp'nin aksine bulunan guncelleme otomatik uygulanmaz (uygulamayi
        kapatip yeniden baslatmayi gerektirir); yalnizca durum cubugunda
        haber verilir, gercek guncelleme Ayarlar'dan baslatilir.
        """
        if os.environ.get("YTARA_SELFTEST") == "1":
            return
        self._app_update_worker = AppUpdateWorker(mode="check", auto=True, parent=self)
        self._app_update_worker.checked.connect(self._on_app_update_checked_auto)
        self._app_update_worker.finished.connect(self._on_app_update_worker_done)
        self._app_update_worker.start()

    def _on_app_update_checked_auto(self, current: str, latest: str, outdated: bool, release: dict):
        self.settings.app_update_last_check = dt.date.today().isoformat()
        self.settings.save()
        if not outdated or latest == self.settings.app_update_skip_version:
            return
        # Kullaniciyi Ayarlar'a yollamak yerine guncellemeyi bulundugu
        # yerde, tek tikla yapilabilir hale getirir.
        from app.ui.update_dialog import UpdateDialog
        dlg = UpdateDialog(current, latest, release, self)
        dlg.exec()
        if dlg.skipped_version:
            self.settings.app_update_skip_version = dlg.skipped_version
            self.settings.save()
            self.statusBar().showMessage(f"v{latest} sürümü atlandı.", 10000)
        else:
            self.statusBar().showMessage(
                f"Yeni sürüm mevcut: v{latest} (kurulu: v{current}).", 20000)

    def _on_app_update_worker_done(self):
        if self._app_update_worker is not None:
            self._app_update_worker.deleteLater()
            self._app_update_worker = None

    # ================================================================ klavye
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self.history_table.hasFocus():
            self._delete_selected_history()
            return
        if event.matches(QKeySequence.Undo):
            self._history_undo()
            return
        if event.matches(QKeySequence.Redo):
            self._history_redo()
            return
        super().keyPressEvent(event)

    # ================================================================ kapanis
    def closeEvent(self, event):
        self._save_window_state()
        # Acik (kipsiz) indirme pencereleri varsa once onlar kapatilir;
        # her biri kendi worker'inin bitmesini bekler (bkz. DownloadDialog).
        for dlg in list(self._open_download_dialogs):
            dlg.close()
        if self._worker is not None:
            # Yorumlayici sonlanirken calisir durumda kalan bir QThread,
            # Qt6Core.dll icinde cokmeye yol acabilir (bkz. asagidaki not);
            # bu yuzden pencere kapanmadan once is parcaciginin gercekten
            # bitmesini bekleriz.
            self._worker.cancel()
            self._worker.wait()
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
        # Arkaplanda (pencere acmadan) calisan otomatik indirmeler ve
        # izleme listesi taramasi da ayni sebeple bitene kadar beklenir.
        for headless in list(self._headless_workers):
            headless.cancel()
            headless.wait()
        if self._watchlist_worker is not None:
            self._watchlist_worker.wait()
        if self._app_update_worker is not None:
            self._app_update_worker.wait()
        super().closeEvent(event)
