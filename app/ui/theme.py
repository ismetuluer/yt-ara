"""Acik / koyu tema destegi. 'system' secilirse Windows temasi izlenir."""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

_DARK_QSS = """
QToolTip { color: #eeeeee; background-color: #2b2b2b; border: 1px solid #555; }
QLineEdit, QListWidget, QTableWidget, QDateEdit, QComboBox {
    background-color: #2b2b2b; border: 1px solid #555; border-radius: 3px;
    padding: 3px; selection-background-color: #3d6fa5;
}
QGroupBox { border: 1px solid #555; border-radius: 5px; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton {
    background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #454545; }
QPushButton:pressed { background-color: #2f2f2f; }
QPushButton:disabled { color: #888; background-color: #333; }
QHeaderView::section {
    background-color: #3a3a3a; border: 1px solid #555; padding: 4px;
}
QCalendarWidget QToolButton { color: #eeeeee; }
"""

_LIGHT_QSS = """
QLineEdit, QListWidget, QTableWidget, QDateEdit, QComboBox {
    border: 1px solid #b8b8b8; border-radius: 3px; padding: 3px;
    selection-background-color: #0078d4;
}
QGroupBox { border: 1px solid #c8c8c8; border-radius: 5px; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton {
    background-color: #f3f3f3; border: 1px solid #adadad; border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #e5f1fb; border-color: #0078d4; }
QPushButton:pressed { background-color: #cce4f7; }
QPushButton:disabled { color: #999; }
"""


def system_is_dark() -> bool:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        return False


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(32, 32, 32))
    p.setColor(QPalette.WindowText, QColor(238, 238, 238))
    p.setColor(QPalette.Base, QColor(43, 43, 43))
    p.setColor(QPalette.AlternateBase, QColor(38, 38, 38))
    p.setColor(QPalette.ToolTipBase, QColor(43, 43, 43))
    p.setColor(QPalette.ToolTipText, QColor(238, 238, 238))
    p.setColor(QPalette.Text, QColor(238, 238, 238))
    p.setColor(QPalette.Button, QColor(58, 58, 58))
    p.setColor(QPalette.ButtonText, QColor(238, 238, 238))
    p.setColor(QPalette.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.Link, QColor(90, 160, 250))
    p.setColor(QPalette.Highlight, QColor(61, 111, 165))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.PlaceholderText, QColor(150, 150, 150))
    return p


def apply_theme(app: QApplication, mode: str) -> None:
    dark = system_is_dark() if mode == "system" else (mode == "dark")
    app.setStyle("Fusion")
    if dark:
        app.setPalette(_dark_palette())
        app.setStyleSheet(_DARK_QSS)
    else:
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet(_LIGHT_QSS)
    # Sonraki pencerelerin (henuz acilmamis dialoglar dahil) baslik
    # cubugunu dogru modda acmasi icin son secilen koyuluk saklanir.
    app.setProperty("yt_ara_dark", dark)
    # O an acik olan tum pencerelerin baslik cubuklari da hemen guncellenir
    # (Windows'ta baslik cubugu Qt palette'inden bagimsiz, DWM tarafindan
    # cizilir; guncellenmezse -- ozellikle Windows koyu modundayken --
    # "acik tema secince de baslik cubugu koyu kaliyor, calismiyor" izlenimi
    # verir).
    for widget in app.topLevelWidgets():
        if widget.isWindow():
            sync_titlebar(widget)


def sync_titlebar(widget) -> None:
    """Verilen pencerenin baslik cubugunu mevcut tema koyulugu ile eslestirir.

    Yalnizca Windows 10 1809+ / Windows 11'de etkilidir; diger platformlarda
    sessizce hicbir sey yapmaz.
    """
    if sys.platform != "win32":
        return
    app = QApplication.instance()
    if app is None:
        return
    dark = bool(app.property("yt_ara_dark"))
    try:
        import ctypes
        hwnd = int(widget.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass
