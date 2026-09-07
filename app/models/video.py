"""Video sonucu veri modeli."""
from dataclasses import dataclass


@dataclass
class VideoResult:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: str  # ISO 8601, ornek: 2024-03-15T14:22:00Z
    url: str

    @property
    def published_display(self) -> str:
        """GG.AA.YYYY biciminde gosterim."""
        try:
            y, m, d = self.published_at[:10].split("-")
            return f"{d}.{m}.{y}"
        except (ValueError, AttributeError):
            return self.published_at

    @property
    def published_sort_key(self) -> str:
        return self.published_at or ""

    @staticmethod
    def make_url(video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"
