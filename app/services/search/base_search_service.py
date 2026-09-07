"""Arama motoru ortak arayuzu.

UI ve worker, hangi motorun kullanildigini bilmeden bu arayuz uzerinden
sorgu gonderir. Iki uygulama vardir:

* YouTubeApiSearchEngine  -> YouTube Data API v3
* YtDlpSearchEngine       -> yt-dlp (API'siz)
"""
import abc
import datetime as dt
from typing import Callable

from app.models.video import VideoResult


class SearchEngine(abc.ABC):
    """Ortak arama motoru arayuzu."""

    name: str = "base"

    @abc.abstractmethod
    def search_page(
        self,
        query: str,
        channel_id: str | None = None,
        published_after: dt.date | None = None,
        published_before: dt.date | None = None,
        page_token: str | None = None,
        max_results: int = 50,
        on_video: Callable[[VideoResult], None] | None = None,
    ) -> tuple[list[VideoResult], str]:
        """Bir sayfa video arar. (video listesi, sonraki sayfa tokeni) dondurur.

        Sayfalama desteklenmiyorsa sonraki token bos string olur.
        `on_video` verilirse (destekleyen motorlarda) her video hazir
        oldukca -- arama/zenginlestirme tamamen bitmeden -- cagrilir;
        boylece cagiran taraf sonuclari aninda gosterebilir.
        """

    @abc.abstractmethod
    def resolve_channel(self, text: str) -> tuple[str, str]:
        """Kanal metnini (channel_id, channel_title) olarak cozumler."""

    @abc.abstractmethod
    def validate_available(self) -> bool:
        """Motorun kullanilabilir olup olmadigini dondurur (ornek: API anahtari)."""
