"""Izleme listesi sekmesi.

Bir kanali (istege bagli bir anahtar kelimeyle) izlemeye alir. Arka
planda MainWindow tarafindan periyodik denetlenir; eslesen yeni videolar
otomatik indirilir ve burada "Bulunan Videolar" olarak listelenir.
"""
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services.watchlist_service import WatchlistService
from app.ui.icons import icon
from app.ui.theme import ACCENT_BUTTON_OBJECT_NAME


class WatchlistTab(QWidget):
    def __init__(self, watchlist: WatchlistService, resolve_channel_name,
                 prime_watch, check_now, get_saved_channels=None, parent=None):
        """
        resolve_channel_name(url) -> str: kanal adini senkron cozer.
        prime_watch(watch_id, url): mevcut videolari "gorulmus" isaretler
            (izlemeye yeni alinan kanalin gecmis videolari indirilmesin diye).
        check_now(): "Şimdi Denetle" icin geri cagri.
        get_saved_channels() -> list[dict]: sol kenar cubugundaki kayitli
            kanallari dondurur ({"url", "name"}); verilirse kullanici bir
            kanal adresini elle yazmak yerine listeden secebilir.
        """
        super().__init__(parent)
        self.watchlist = watchlist
        self._resolve_channel_name = resolve_channel_name
        self._prime_watch = prime_watch
        self._check_now = check_now
        self._get_saved_channels = get_saved_channels
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        hint = QLabel(
            "Bir kanalı izlemeye alın; yeni video yayınlandığında (isterseniz "
            "yalnızca anahtar kelimeyle eşleşenler) otomatik indirilir.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

        # Kayitli kanallardan secim: kanal adresini elle yazmak yerine sol
        # kenar cubugundaki listeden secilebilir (secince adres kutusuna
        # otomatik yazilir).
        self.saved_channel_combo = QComboBox()
        self.saved_channel_combo.setToolTip("Zaten kayıtlı kanallardan birini seçin.")
        self.saved_channel_combo.currentIndexChanged.connect(self._on_saved_channel_picked)
        self._refresh_saved_channel_combo()
        layout.addWidget(self.saved_channel_combo)

        add_row = QHBoxLayout()
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("Kanal adresi")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("Anahtar kelime (isteğe bağlı)")
        self.add_btn = QPushButton(icon("add"), "İzlemeye al")
        self.add_btn.setObjectName(ACCENT_BUTTON_OBJECT_NAME)
        self.add_btn.clicked.connect(self._add_watch)
        add_row.addWidget(self.channel_edit, 2)
        add_row.addWidget(self.keyword_edit, 1)
        add_row.addWidget(self.add_btn)
        layout.addLayout(add_row)

        self.watch_list = QListWidget()
        self.watch_list.setMaximumHeight(140)
        self.watch_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.watch_list.customContextMenuRequested.connect(self._watch_context_menu)
        layout.addWidget(self.watch_list)

        watch_btn_row = QHBoxLayout()
        self.remove_watch_btn = QPushButton(icon("delete"), "İzlemeyi bırak")
        self.remove_watch_btn.clicked.connect(self._remove_selected_watch)
        self.check_now_btn = QPushButton(icon("refresh"), "Şimdi denetle")
        self.check_now_btn.clicked.connect(self._check_now)
        watch_btn_row.addWidget(self.remove_watch_btn)
        watch_btn_row.addWidget(self.check_now_btn)
        watch_btn_row.addStretch(1)
        layout.addLayout(watch_btn_row)

        layout.addWidget(QLabel("Bulunan videolar"))
        self.found_table = QTableWidget(0, 4)
        self.found_table.setHorizontalHeaderLabels(
            ["Başlık", "Kanal", "Bulunma zamanı", "Adres"])
        self.found_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.found_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.found_table.doubleClicked.connect(self._open_found_video)
        header = self.found_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        self.found_table.setColumnWidth(3, 260)
        self.found_table.verticalHeader().setVisible(False)
        layout.addWidget(self.found_table, 1)

    def _refresh_saved_channel_combo(self):
        if self._get_saved_channels is None:
            self.saved_channel_combo.setVisible(False)
            return
        channels = self._get_saved_channels()
        self.saved_channel_combo.blockSignals(True)
        self.saved_channel_combo.clear()
        self.saved_channel_combo.addItem("Kayıtlı kanallardan seç…", "")
        for entry in channels:
            url = entry.get("url", "")
            if not url:
                continue
            label = entry.get("name") or url
            self.saved_channel_combo.addItem(label, url)
        self.saved_channel_combo.setCurrentIndex(0)
        self.saved_channel_combo.blockSignals(False)
        self.saved_channel_combo.setVisible(self.saved_channel_combo.count() > 1)

    def _on_saved_channel_picked(self, index: int):
        url = self.saved_channel_combo.itemData(index)
        if url:
            self.channel_edit.setText(url)

    def refresh(self):
        self._refresh_saved_channel_combo()
        self.watch_list.clear()
        for watch in self.watchlist.all():
            label = watch.get("channel_title") or watch.get("channel_url")
            if watch.get("keyword"):
                label += f'  —  "{watch["keyword"]}"'
            if not watch.get("active", True):
                label += "  (pasif)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, watch["id"])
            self.watch_list.addItem(item)
        self._refresh_found()

    def _refresh_found(self):
        records = self.watchlist.recent_found(100)
        self.found_table.setRowCount(len(records))
        for row, rec in enumerate(records):
            self.found_table.setItem(row, 0, QTableWidgetItem(rec.get("title") or ""))
            self.found_table.setItem(row, 1, QTableWidgetItem(rec.get("channel_title") or ""))
            self.found_table.setItem(row, 2, QTableWidgetItem(rec.get("found_at") or ""))
            self.found_table.setItem(row, 3, QTableWidgetItem(rec.get("url") or ""))

    def _add_watch(self):
        url = self.channel_edit.text().strip()
        if not url:
            return
        keyword = self.keyword_edit.text().strip()
        name = self._resolve_channel_name(url)
        watch_id = self.watchlist.add(url, name, keyword)
        if watch_id:
            self._prime_watch(watch_id, url)
        self.channel_edit.clear()
        self.keyword_edit.clear()
        self.refresh()

    def _selected_watch_id(self):
        item = self.watch_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _remove_selected_watch(self):
        watch_id = self._selected_watch_id()
        if watch_id is None:
            return
        self.watchlist.delete(watch_id)
        self.refresh()

    def _watch_context_menu(self, pos):
        item = self.watch_list.itemAt(pos)
        if item is None:
            return
        self.watch_list.setCurrentItem(item)
        watch_id = item.data(Qt.UserRole)
        watches = {w["id"]: w for w in self.watchlist.all()}
        watch = watches.get(watch_id)
        menu = QMenu(self)
        active = bool(watch and watch.get("active", True))
        toggle_act = menu.addAction(
            icon("cancel") if active else icon("check"),
            "Pasif yap" if active else "Aktif yap")
        remove_act = menu.addAction(icon("delete"), "İzlemeyi bırak")
        action = menu.exec(self.watch_list.viewport().mapToGlobal(pos))
        if action == toggle_act and watch:
            self.watchlist.set_active(watch_id, not watch.get("active", True))
            self.refresh()
        elif action == remove_act:
            self.watchlist.delete(watch_id)
            self.refresh()

    def _open_found_video(self):
        row = self.found_table.currentRow()
        if row < 0:
            return
        item = self.found_table.item(row, 3)
        if item and item.text():
            webbrowser.open(item.text())
