"""Zamanlanmis indirmeler sekmesi.

Kullanicinin indirme penceresinden ileri bir zamana ertelendigi
gorevleri listeler; zamani gelenler MainWindow'daki zamanlayici
tarafindan otomatik baslatilir (bkz. MainWindow._check_scheduled_downloads).
"""
import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services.scheduled_download_service import ScheduledDownloadService


class ScheduledTab(QWidget):
    def __init__(self, scheduler: ScheduledDownloadService, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Video Başlığı", "Çalışma Zamanı"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Yenile")
        self.refresh_btn.clicked.connect(self.refresh)
        self.cancel_btn = QPushButton("Seçilenleri iptal et")
        self.cancel_btn.clicked.connect(self._cancel_selected)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def refresh(self):
        tasks = self.scheduler.pending()
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            title_item = QTableWidgetItem(task.get("title") or "")
            title_item.setData(Qt.UserRole, task.get("id"))
            try:
                run_at = dt.datetime.fromisoformat(task.get("run_at"))
                run_txt = run_at.strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                run_txt = task.get("run_at") or ""
            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, QTableWidgetItem(run_txt))

    def _selected_ids(self) -> list:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        ids = []
        for row in rows:
            item = self.table.item(row, 0)
            if item:
                ids.append(item.data(Qt.UserRole))
        return ids

    def _cancel_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        answer = QMessageBox.question(
            self, "İptal et",
            f"{len(ids)} zamanlanmış indirme iptal edilecek. Devam edilsin mi?")
        if answer != QMessageBox.Yes:
            return
        for task_id in ids:
            self.scheduler.delete(task_id)
        self.refresh()

    def _context_menu(self, pos):
        if self.table.itemAt(pos) is None:
            return
        menu = QMenu(self)
        cancel_act = menu.addAction("İptal et")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == cancel_act:
            self._cancel_selected()
