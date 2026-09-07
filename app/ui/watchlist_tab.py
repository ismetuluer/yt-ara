"""Izleme listesi sekmesi.

Bir kanali (istege bagli bir anahtar kelimeyle) izlemeye alir. Arka
planda MainWindow tarafindan periyodik denetlenir; eslesen yeni videolar
otomatik indirilir ve burada "Bulunan Videolar" olarak listelenir.
"""
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services.watchlist_service import WatchlistService


class WatchlistTab(QWidget):
    def __init__(self, watchlist: WatchlistService, resolve_channel_name,
                 prime_watch, check_now, parent=None):
        """
        resolve_channel_name(url) -> str: kanal adini senkron cozer.
        prime_watch(watch_id, url): mevcut videolari "gorulmus" isaretler
            (izlemeye yeni alinan kanalin gecmis videolari indirilmesin diye).
        check_now(): "Şimdi Denetle" icin geri cagri.
        """
        super().__init__(parent)
        self.watchlist = watchlist
        self._resolve_channel_name = resolve_channel_name
        self._prime_watch = prime_watch
        self._check_now = check_now
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

        add_row = QHBoxLayout()
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("Kanal adresi")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("Anahtar kelime (boş = tüm videolar)")
        self.add_btn = QPushButton("İzlemeye Al")
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
        self.remove_watch_btn = QPushButton("İzlemeyi Bırak")
        self.remove_watch_btn.clicked.connect(self._remove_selected_watch)
        self.check_now_btn = QPushButton("Şimdi Denetle")
        self.check_now_btn.clicked.connect(self._check_now)
        watch_btn_row.addWidget(self.remove_watch_btn)
        watch_btn_row.addWidget(self.check_now_btn)
        watch_btn_row.addStretch(1)
        layout.addLayout(watch_btn_row)

        layout.addWidget(QLabel("Bulunan Videolar:"))
        self.found_table = QTableWidget(0, 4)
        self.found_table.setHorizontalHeaderLabels(
            ["Video Başlığı", "Kanal", "Bulunma Zamanı", "Video Adresi"])
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

    def refresh(self):
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
        toggle_act = menu.addAction(
            "Pasif Yap" if watch and watch.get("active", True) else "Aktif Yap")
        remove_act = menu.addAction("İzlemeyi Bırak")
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
