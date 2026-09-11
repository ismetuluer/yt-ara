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
    # Altyazi/kapali baslik mevcut mu. Yalnizca YouTube API modunda
    # doldurulur (yt-dlp'nin hizli/duz aramasi bu bilgiyi vermez); API'siz
    # modda hep False kalir -- yani ikon yalnizca API anahtari varken gorunur.
    has_captions: bool = False

    @property
    def published_display(self) -> str:
        """GG.AA.YYYY biciminde gosterim."""
        try:
            y, m, d = self.published_at[:10].split("-")
            return f"{d}.{m}.{y}"
        except (ValueError, AttributeError):
            return self.published_at

    @property
    def published_datetime_display(self) -> str:
        """GG.AA.YYYY SS:DD -- saat bilgisi varsa eklenir.

        yt-dlp (API'siz) modunda yayin tarihi yalnizca gun hassasiyetinde
        gelir (saat hep gece yarisina sabitlenir); bu yuzden saat, yalnizca
        00:00'dan farkliysa (gercekten bilindiginde, ornegin API modunda)
        gosterime eklenir -- aksi halde yaniltici bir "gece yarisi
        yayinlandi" izlenimi vermemek icin sadece tarih gosterilir.
        """
        base = self.published_display
        time_part = self.published_at[11:16] if len(self.published_at) >= 16 else ""
        if time_part and time_part != "00:00":
            return f"{base} {time_part}"
        return base

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
