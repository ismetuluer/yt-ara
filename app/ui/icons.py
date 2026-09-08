"""Arayuz ikonlari.

Windows'un kendi ikon fontundan (Segoe Fluent Icons / Segoe MDL2 Assets)
tek renkli, ince cizgili ikonlar uretir; boylece uygulamaya ek bir ikon
dosyasi paketlemek gerekmez ve gorunum sistemle tutarli olur.

Font bulunamazsa (Windows disi, cok eski Windows) `icon()` bos bir QIcon
dondurur: dugmeler ve menuler yalnizca metinle, bozulmadan calisir.
"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QPainter, QPixmap,
)

_ICON_FONT_CANDIDATES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

# Ikon renkleri kasitli olarak temadan BAGIMSIZ sabittir: bu uc ton hem
# acik hem koyu zeminde okunur, boylece tema degistiginde ikonlarin
# yeniden uretilmesi gerekmez.
_NEUTRAL = "#86868b"   # normal dugme/menu zemininde
_ON_ACCENT = "#ffffff"  # mavi (vurgu) zeminde: vurgu dugmesi, secili satir
_DISABLED = "#b0b0b4"

# Anlamli ad -> Segoe ikon fontundaki kod noktasi. Kod noktalari,
# kaynak dosyanin kodlamasindan etkilenmesinler diye kacis dizisiyle
# yazilir (ozel kullanim alani karakterleri kopyalanirken bozulabiliyor).
_GLYPHS = {
    "search": "\uE721",       # buyutec
    "results": "\uE8FD",      # liste
    "history": "\uE81C",      # gecmis (saat)
    "calendar": "\uE787",     # takvim
    "watch": "\uE890",        # goz (izleme listesi)
    "settings": "\uE713",     # disli
    "download": "\uE896",     # asagi ok
    "copy": "\uE8C8",         # kopyala
    "delete": "\uE74D",       # cop kutusu
    "edit": "\uE70F",         # kalem
    "refresh": "\uE72C",      # yenile
    "folder": "\uE8B7",       # klasor
    "add": "\uE710",          # arti
    "cancel": "\uE711",       # carpi
    "check": "\uE73E",        # onay
    "select_all": "\uE8B3",   # tumunu sec
    "clear": "\uE894",        # temizle
    "document": "\uE8A5",     # belge
    "more": "\uE70D",         # asagi chevron
    "info": "\uE946",         # bilgi
    "open": "\uE8A7",         # yeni pencerede ac
}

_font_family: str | None = None
_font_checked = False
_cache: dict = {}


def _family() -> str | None:
    global _font_family, _font_checked
    if not _font_checked:
        _font_checked = True
        available = set(QFontDatabase.families())
        for name in _ICON_FONT_CANDIDATES:
            if name in available:
                _font_family = name
                break
    return _font_family


def available() -> bool:
    """Ikon fontu bu makinede var mi."""
    return _family() is not None


def _pixmap(glyph: str, size: int, color: str) -> QPixmap:
    ratio = 2  # keskin gorunum icin 2x cozunurlukte uretilir
    pm = QPixmap(size * ratio, size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    # DIKKAT: devicePixelRatio atandigi icin bu pixmap uzerindeki
    # QPainter MANTIKSAL koordinatlarla calisir; olculer ve cizim
    # `size * ratio` ile degil, `size` ile yapilmalidir (aksi halde
    # glyph iki kat buyuk cizilip kirpilir).
    box = size

    # Ikon fontu glyph'leri em kutusunu tasirir: satir yuksekligine gore
    # ortalamak (AlignCenter) ikonun kenarlarini kirpiyordu. Bunun yerine
    # glyph'in gercek murekkep siniri olculur, kutuya sigacak sekilde
    # olceklenir ve o sinira gore ortalanir.
    font = QFont(_family())
    font.setPixelSize(box)
    bounds = QFontMetricsF(font).tightBoundingRect(glyph)
    if bounds.width() > 0 and bounds.height() > 0:
        scale = min(box / bounds.width(), box / bounds.height()) * 0.84
        font.setPixelSize(max(1, int(box * scale)))
        bounds = QFontMetricsF(font).tightBoundingRect(glyph)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setFont(font)
    painter.setPen(QColor(color))
    # drawText(QPointF) taban cizgisini alir; tight sinirin sol-ust kosesi
    # bu noktaya gore verildiginden ofsetler cikarilir.
    painter.drawText(QPointF((box - bounds.width()) / 2 - bounds.x(),
                             (box - bounds.height()) / 2 - bounds.y()), glyph)
    painter.end()
    return pm


def icon(name: str, size: int = 16, on_accent: bool = False) -> QIcon:
    """Adiyla bir ikon dondurur.

    on_accent: ikon mavi (vurgu) zeminde duracaksa beyaz uretilir.
    Secili liste satirlari icin ayrica QIcon.Selected kipi doldurulur;
    boylece satir secilince ikon beyaza doner.
    """
    glyph = _GLYPHS.get(name)
    if glyph is None or not available():
        return QIcon()
    key = (name, size, on_accent)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    result = QIcon()
    base = _ON_ACCENT if on_accent else _NEUTRAL
    result.addPixmap(_pixmap(glyph, size, base), QIcon.Normal)
    result.addPixmap(_pixmap(glyph, size, _DISABLED), QIcon.Disabled)
    result.addPixmap(_pixmap(glyph, size, _ON_ACCENT), QIcon.Selected)
    _cache[key] = result
    return result
