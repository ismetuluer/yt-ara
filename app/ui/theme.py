"""Acik / koyu tema destegi. 'system' secilirse Windows temasi izlenir.

Gorsel dil Apple'in HIG'ine yakinlastirilmistir: agir kenarlikli kutular
yerine bosluk ve ince ayirici cizgiler, tek bir vurgu rengi (mavi),
yuvarlatilmis koseler, daha ferah dolgu (padding).
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

# Apple sistem mavisi (acik/koyu tema icin ayri tonlar -- koyu zeminde
# okunabilirlik/kontrast icin biraz daha acik bir mavi kullanilir).
_ACCENT_LIGHT = "#0071e3"
_ACCENT_LIGHT_HOVER = "#0077ed"
_ACCENT_LIGHT_PRESSED = "#005bbf"
_ACCENT_DARK = "#0a84ff"
_ACCENT_DARK_HOVER = "#3396ff"
_ACCENT_DARK_PRESSED = "#0068cc"

# Windows'ta San Francisco yerine en yakin sistem fontu.
_FONT_FAMILY = "Segoe UI Variable Text, Segoe UI, sans-serif"

_DARK_QSS = f"""
* {{ font-family: {_FONT_FAMILY}; }}
QToolTip {{ color: #eeeeee; background-color: #2b2b2b; border: 1px solid #444; border-radius: 6px; padding: 4px 8px; }}
QLineEdit, QListWidget, QTableWidget, QDateEdit, QComboBox {{
    background-color: #262626; color: #eeeeee; border: 1px solid #3a3a3a;
    border-radius: 8px; padding: 6px 8px; selection-background-color: {_ACCENT_DARK};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {_ACCENT_DARK}; }}
QGroupBox {{ border: none; margin-top: 18px; font-weight: 500; color: #b0b0b0; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 0; top: 4px; padding: 0; color: #9a9a9a; }}
QPushButton {{
    background-color: #2c2c2c; color: #eeeeee; border: 1px solid #3a3a3a;
    border-radius: 8px; padding: 7px 16px;
}}
QPushButton:hover {{ background-color: #363636; }}
QPushButton:pressed {{ background-color: #232323; }}
QPushButton:disabled {{ color: #666; background-color: #262626; }}
QPushButton#accentButton {{
    background-color: {_ACCENT_DARK}; color: #ffffff; border: none; font-weight: 500;
}}
QPushButton#accentButton:hover {{ background-color: {_ACCENT_DARK_HOVER}; }}
QPushButton#accentButton:pressed {{ background-color: {_ACCENT_DARK_PRESSED}; }}
QPushButton#accentButton:disabled {{ background-color: #3a3a3a; color: #777; }}
QPushButton#pillButton {{
    background-color: #2c2c2c; border: 1px solid #3a3a3a; border-radius: 14px;
    padding: 5px 14px; color: #cfcfcf;
}}
QPushButton#pillButton:hover {{ background-color: #363636; }}
QPushButton#pillButton:checked {{ background-color: {_ACCENT_DARK}; color: #ffffff; border: none; }}
QCheckBox, QRadioButton {{ color: #dedede; spacing: 8px; }}
QTabWidget::pane {{ border: none; border-top: 1px solid #333; }}
QTabBar::tab {{
    background: transparent; color: #999; padding: 8px 16px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: #eeeeee; border-bottom: 2px solid {_ACCENT_DARK}; }}
QTabBar::tab:hover:!selected {{ color: #ccc; }}
QHeaderView::section {{
    background-color: transparent; color: #999; border: none; border-bottom: 1px solid #333;
    padding: 6px 4px; font-weight: 500;
}}
QTableWidget {{ gridline-color: #2e2e2e; alternate-background-color: #232323; }}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:selected {{ background-color: {_ACCENT_DARK}; color: #ffffff; }}
QCalendarWidget QToolButton {{ color: #eeeeee; }}
QSplitter::handle {{ background-color: #3a3a3a; }}
QSplitter::handle:hover {{ background-color: {_ACCENT_DARK}; }}
QSplitter::handle:vertical {{ height: 6px; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #444; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #555; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QWidget#sidebar {{ background-color: #1c1c1c; border-right: 1px solid #303030; }}
QWidget#sidebar QListWidget {{ background-color: #232323; border: 1px solid #303030; }}
QWidget#sidebar QListWidget#navList {{ background: transparent; border: none; padding: 0; }}
QWidget#sidebar QListWidget#navList::item {{
    padding: 7px 10px; border-radius: 7px; color: #dedede; margin: 1px 0;
}}
QWidget#sidebar QListWidget#navList::item:hover {{ background-color: #2e2e2e; }}
QWidget#sidebar QListWidget#navList::item:selected {{ background-color: {_ACCENT_DARK}; color: #ffffff; }}
QLabel#sectionLabel {{ color: #7d7d82; font-size: 10px; font-weight: bold; }}
QLabel#pageTitle {{ color: #f2f2f2; font-size: 19px; font-weight: bold; }}
QLabel#mutedLabel {{ color: #8e8e93; }}
QLabel#betaBadge {{
    color: #fbbf24; background-color: #3a2f10; border: 1px solid #6b5312;
    border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: bold;
}}
QFrame#card {{ background-color: #262626; border: 1px solid #333333; border-radius: 12px; }}
"""

_LIGHT_QSS = f"""
* {{ font-family: {_FONT_FAMILY}; }}
QToolTip {{ color: #1d1d1f; background-color: #ffffff; border: 1px solid #d2d2d7; border-radius: 6px; padding: 4px 8px; }}
QLineEdit, QListWidget, QTableWidget, QDateEdit, QComboBox {{
    background-color: #ffffff; color: #1d1d1f; border: 1px solid #d2d2d7;
    border-radius: 8px; padding: 6px 8px; selection-background-color: {_ACCENT_LIGHT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {_ACCENT_LIGHT}; }}
QGroupBox {{ border: none; margin-top: 18px; font-weight: 500; color: #6e6e73; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 0; top: 4px; padding: 0; color: #6e6e73; }}
QPushButton {{
    background-color: #f5f5f7; color: #1d1d1f; border: 1px solid #d2d2d7;
    border-radius: 8px; padding: 7px 16px;
}}
QPushButton:hover {{ background-color: #ececee; }}
QPushButton:pressed {{ background-color: #e2e2e4; }}
QPushButton:disabled {{ color: #a1a1a6; background-color: #f5f5f7; }}
QPushButton#accentButton {{
    background-color: {_ACCENT_LIGHT}; color: #ffffff; border: none; font-weight: 500;
}}
QPushButton#accentButton:hover {{ background-color: {_ACCENT_LIGHT_HOVER}; }}
QPushButton#accentButton:pressed {{ background-color: {_ACCENT_LIGHT_PRESSED}; }}
QPushButton#accentButton:disabled {{ background-color: #e2e2e4; color: #a1a1a6; }}
QPushButton#pillButton {{
    background-color: #f5f5f7; border: 1px solid #d2d2d7; border-radius: 14px;
    padding: 5px 14px; color: #3a3a3c;
}}
QPushButton#pillButton:hover {{ background-color: #ececee; }}
QPushButton#pillButton:checked {{ background-color: {_ACCENT_LIGHT}; color: #ffffff; border: none; }}
QCheckBox, QRadioButton {{ color: #1d1d1f; spacing: 8px; }}
QTabWidget::pane {{ border: none; border-top: 1px solid #e5e5ea; }}
QTabBar::tab {{
    background: transparent; color: #6e6e73; padding: 8px 16px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: #1d1d1f; border-bottom: 2px solid {_ACCENT_LIGHT}; }}
QTabBar::tab:hover:!selected {{ color: #1d1d1f; }}
QHeaderView::section {{
    background-color: transparent; color: #6e6e73; border: none; border-bottom: 1px solid #e5e5ea;
    padding: 6px 4px; font-weight: 500;
}}
QTableWidget {{ gridline-color: #f0f0f2; alternate-background-color: #fafafa; }}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:selected {{ background-color: {_ACCENT_LIGHT}; color: #ffffff; }}
QCalendarWidget QToolButton {{ color: #1d1d1f; }}
QSplitter::handle {{ background-color: #e5e5ea; }}
QSplitter::handle:hover {{ background-color: {_ACCENT_LIGHT}; }}
QSplitter::handle:vertical {{ height: 6px; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #d2d2d7; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #b8b8bd; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QWidget#sidebar {{ background-color: #f0f0f2; border-right: 1px solid #e0e0e5; }}
QWidget#sidebar QListWidget {{ background-color: #ffffff; border: 1px solid #e0e0e5; }}
QWidget#sidebar QListWidget#navList {{ background: transparent; border: none; padding: 0; }}
QWidget#sidebar QListWidget#navList::item {{
    padding: 7px 10px; border-radius: 7px; color: #1d1d1f; margin: 1px 0;
}}
QWidget#sidebar QListWidget#navList::item:hover {{ background-color: #e4e4e9; }}
QWidget#sidebar QListWidget#navList::item:selected {{ background-color: {_ACCENT_LIGHT}; color: #ffffff; }}
QLabel#sectionLabel {{ color: #86868b; font-size: 10px; font-weight: bold; }}
QLabel#pageTitle {{ color: #1d1d1f; font-size: 19px; font-weight: bold; }}
QLabel#mutedLabel {{ color: #86868b; }}
QLabel#betaBadge {{
    color: #b45309; background-color: #fef3c7; border: 1px solid #e0b055;
    border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: bold;
}}
QFrame#card {{ background-color: #ffffff; border: 1px solid #e5e5ea; border-radius: 12px; }}
"""

# main_window.py'deki "ARA" gibi tek bir birincil eylem butonu, objectName
# "accentButton" verilerek bu vurgu rengini alir (bkz. yukaridaki QSS).
ACCENT_BUTTON_OBJECT_NAME = "accentButton"
# Tarih hizli secim / kanal etiketi gibi "hap" (pill) gorunumlu, ikincil
# secim butonlari icin.
PILL_BUTTON_OBJECT_NAME = "pillButton"
# Ana penceredeki sol kenar cubugu ve icindeki gezinme listesi.
SIDEBAR_OBJECT_NAME = "sidebar"
NAV_LIST_OBJECT_NAME = "navList"
# Kucuk, buyuk harfli bolum basligi ("KANALLAR" gibi).
SECTION_LABEL_OBJECT_NAME = "sectionLabel"
# Sayfa basligi ve ikincil (soluk) aciklama metni.
PAGE_TITLE_OBJECT_NAME = "pageTitle"
MUTED_LABEL_OBJECT_NAME = "mutedLabel"
BETA_BADGE_OBJECT_NAME = "betaBadge"
# Icerigi gruplayan, yuvarlatilmis kose ve hafif kenarlikli kutu.
CARD_OBJECT_NAME = "card"


def system_is_dark() -> bool:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        return False


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(30, 30, 30))
    p.setColor(QPalette.WindowText, QColor(238, 238, 238))
    p.setColor(QPalette.Base, QColor(38, 38, 38))
    p.setColor(QPalette.AlternateBase, QColor(35, 35, 35))
    p.setColor(QPalette.ToolTipBase, QColor(43, 43, 43))
    p.setColor(QPalette.ToolTipText, QColor(238, 238, 238))
    p.setColor(QPalette.Text, QColor(238, 238, 238))
    p.setColor(QPalette.Button, QColor(44, 44, 44))
    p.setColor(QPalette.ButtonText, QColor(238, 238, 238))
    p.setColor(QPalette.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.Link, QColor(_ACCENT_DARK))
    p.setColor(QPalette.Highlight, QColor(_ACCENT_DARK))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.PlaceholderText, QColor(140, 140, 140))
    return p


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(246, 246, 248))
    p.setColor(QPalette.WindowText, QColor(29, 29, 31))
    p.setColor(QPalette.Base, QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase, QColor(250, 250, 250))
    p.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    p.setColor(QPalette.ToolTipText, QColor(29, 29, 31))
    p.setColor(QPalette.Text, QColor(29, 29, 31))
    p.setColor(QPalette.Button, QColor(245, 245, 247))
    p.setColor(QPalette.ButtonText, QColor(29, 29, 31))
    p.setColor(QPalette.BrightText, QColor(200, 0, 0))
    p.setColor(QPalette.Link, QColor(_ACCENT_LIGHT))
    p.setColor(QPalette.Highlight, QColor(_ACCENT_LIGHT))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.PlaceholderText, QColor(134, 134, 139))
    return p


def apply_theme(app: QApplication, mode: str) -> None:
    dark = system_is_dark() if mode == "system" else (mode == "dark")
    app.setStyle("Fusion")
    font = QFont("Segoe UI Variable Text")
    if not font.exactMatch():
        font = QFont("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)
    if dark:
        app.setPalette(_dark_palette())
        app.setStyleSheet(_DARK_QSS)
    else:
        # NOT app.style().standardPalette(): Qt6/Windows'ta bu, stilden
        # bagimsiz sabit bir palet degildir -- isletim sistemi koyu
        # temadaysa "standart" palet de koyulasabilir ("acik tema secince
        # de her sey koyu kaliyor, dugme yazilari gorunmuyor" hatasina yol
        # acar). Bu yuzden acik mod icin de sabit, elle tanimli bir palet
        # kullanilir (bkz. _dark_palette).
        app.setPalette(_light_palette())
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
