"""Video sonucu veri modeli."""
from dataclasses import dataclass

# YouTube'un kendi Shorts esigi: bu sureden kisa/esit dikey videolar
# Shorts sayilir. API/yt-dlp video suresi disinda "dikey mi" bilgisini
# ek bir cagri yapmadan vermedigi icin bu sure esigi tek basina kullanilir
# (kesin degil ama pratikte yeterince dogru bir yaklasimdir).
SHORTS_MAX_SECONDS = 60


@dataclass
class VideoResult:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: str  # ISO 8601, ornek: 2024-03-15T14:22:00Z
    url: str
    duration: int = 0  # saniye; bilinmiyorsa 0

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

    @property
    def duration_display(self) -> str:
        """SS:DD ya da (bir saatten uzunsa) SS:DD:DD bicimi. Bilinmiyorsa bos."""
        if not self.duration or self.duration <= 0:
            return ""
        total = int(self.duration)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def is_short(self) -> bool:
        return 0 < self.duration <= SHORTS_MAX_SECONDS

    @property
    def kind_display(self) -> str:
        if not self.duration:
            return ""
        return "Shorts" if self.is_short else "Video"

    @staticmethod
    def make_url(video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"
