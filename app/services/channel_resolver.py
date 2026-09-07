"""Kanal adresi (URL / @handle / ID) cozumleme."""
import logging
import re
from dataclasses import dataclass

from app.services.youtube_service import YouTubeError, YouTubeService

UC_PATTERN = re.compile(r"^UC[\w-]{22}$")

_PATTERNS = [
    ("id", re.compile(r"youtube\.com/channel/(UC[\w-]{22})", re.IGNORECASE)),
    ("handle", re.compile(r"youtube\.com/@([\w.\-]+)", re.IGNORECASE)),
    ("user", re.compile(r"youtube\.com/user/([\w.\-]+)", re.IGNORECASE)),
    ("custom", re.compile(r"youtube\.com/c/([\w.\-]+)", re.IGNORECASE)),
]


@dataclass
class ChannelInfo:
    channel_id: str
    title: str


def parse_channel_input(text: str) -> tuple[str, str]:
    """Girilen metni (tur, deger) ciftine dondurur. Ag erisimi gerektirmez.

    tur: id | handle | user | custom | search
    """
    text = text.strip()
    for kind, pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            return kind, m.group(1)
    if UC_PATTERN.match(text):
        return "id", text
    if text.startswith("@"):
        return "handle", text.lstrip("@")
    return "search", text


class ChannelResolver:
    def __init__(self, service: YouTubeService):
        self.service = service
        self.log = logging.getLogger("yt_ara.channel")
        self._cache: dict[str, ChannelInfo] = {}

    def resolve(self, text: str) -> ChannelInfo:
        """Kanal metnini ChannelInfo'ya cevirir. Bulunamazsa YouTubeError firlatir."""
        text = text.strip()
        if not text:
            raise YouTubeError("Kanal adresi boş olamaz.")
        if text in self._cache:
            return self._cache[text]

        kind, value = parse_channel_input(text)
        info: ChannelInfo | None = None
        if kind == "id":
            info = self._by_id(value)
        elif kind == "handle":
            info = self._by_handle(value)
        elif kind == "user":
            info = self._by_username(value) or self._by_search(value)
        else:
            info = self._by_search(value)

        if info is None:
            self.log.info("Kanal bulunamadi: %s", text)
            raise YouTubeError(
                f"Kanal bulunamadı: {text}\nLütfen kanal adresini kontrol edin."
            )
        self._cache[text] = info
        return info

    # ------------------------------------------------------------ ozel API cagrilari
    def _by_id(self, channel_id: str) -> ChannelInfo | None:
        data = self.service._get("channels", {"part": "snippet", "id": channel_id})
        items = data.get("items", [])
        if not items:
            return None
        return ChannelInfo(channel_id=channel_id,
                           title=str(items[0].get("snippet", {}).get("title", "")))

    def _by_handle(self, handle: str) -> ChannelInfo | None:
        data = self.service._get("channels", {"part": "snippet", "forHandle": handle})
        items = data.get("items", [])
        if not items:
            return None
        item = items[0]
        return ChannelInfo(channel_id=str(item.get("id", "")),
                           title=str(item.get("snippet", {}).get("title", "")))

    def _by_username(self, username: str) -> ChannelInfo | None:
        data = self.service._get("channels", {"part": "snippet", "forUsername": username})
        items = data.get("items", [])
        if not items:
            return None
        item = items[0]
        return ChannelInfo(channel_id=str(item.get("id", "")),
                           title=str(item.get("snippet", {}).get("title", "")))

    def _by_search(self, name: str) -> ChannelInfo | None:
        data = self.service._get("search", {
            "part": "snippet",
            "type": "channel",
            "q": name,
            "maxResults": 1,
            "fields": "items(id/channelId,snippet/channelTitle)",
        })
        items = data.get("items", [])
        if not items:
            return None
        item = items[0]
        return ChannelInfo(
            channel_id=str((item.get("id") or {}).get("channelId", "")),
            title=str((item.get("snippet") or {}).get("channelTitle", "")),
        )
