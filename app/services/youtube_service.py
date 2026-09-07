"""YouTube Data API v3 ile video arama servisi."""
import datetime as dt
import logging

import requests

from app.models.video import VideoResult

API_BASE = "https://www.googleapis.com/youtube/v3"

# Anahtar dogrulamasi icin bilinen sabit bir kanal (YouTube resmi kanali)
_KEY_TEST_CHANNEL_ID = "UCBR8-60-B28hp2BmDPdntcQ"


class YouTubeError(Exception):
    """Kullaniciya gosterilecek Turkce mesaj + teknik ayrinti tasir."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


def _to_rfc3339_start(d: dt.date) -> str:
    return f"{d:%Y-%m-%d}T00:00:00Z"


def _to_rfc3339_end(d: dt.date) -> str:
    """Bitis gununu de kapsamasi icin ertesi gunun baslangici kullanilir."""
    return f"{d + dt.timedelta(days=1):%Y-%m-%d}T00:00:00Z"


class YouTubeService:
    def __init__(self, api_key: str, timeout: int = 20, on_call=None):
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.log = logging.getLogger("yt_ara.youtube")
        # Her basarili HTTP cagrisinda (endpoint adiyla) cagrilir; tahmini
        # kota sayaci (QuotaTracker) bunu kullanir.
        self._on_call = on_call

    # ------------------------------------------------------------ yardimcilar
    def _get(self, endpoint: str, params: dict) -> dict:
        query = dict(params)
        query["key"] = self.api_key
        try:
            resp = self.session.get(f"{API_BASE}/{endpoint}", params=query, timeout=self.timeout)
        except requests.RequestException as exc:
            self.log.warning("Baglanti hatasi: %s", exc)
            raise YouTubeError(
                "YouTube'a bağlanılamadı. İnternet bağlantınızı kontrol edin.",
                str(exc),
            ) from exc
        # Istek Google'a ulastiysa (yanit alindiysa) basarili/basarisiz
        # farketmeksizin kota tuketilmis sayilir.
        if self._on_call:
            self._on_call(endpoint)
        if resp.status_code != 200:
            raise self._map_error(resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise YouTubeError(
                "YouTube'dan beklenmeyen bir yanıt alındı. Lütfen tekrar deneyin.",
                f"JSON cozumlenemedi: {exc}",
            ) from exc

    def _map_error(self, resp) -> YouTubeError:
        reason = ""
        message = ""
        try:
            payload = resp.json()
            errors = payload.get("error", {}).get("errors", [])
            if errors:
                reason = str(errors[0].get("reason", ""))
            message = str(payload.get("error", {}).get("message", ""))
        except ValueError:
            message = resp.text[:300]
        detail = f"HTTP {resp.status_code} reason={reason} message={message}"
        self.log.warning("API hatasi: %s", detail)

        if resp.status_code == 400 and reason == "keyInvalid":
            user = "API anahtarı geçersiz. Ayarlar bölümünden doğru anahtarı girdiğinizden emin olun."
        elif resp.status_code == 403 and "quota" in reason.lower():
            user = ("YouTube API günlük kotası doldu. Kota her gün yenilenir; "
                    "lütfen daha sonra tekrar deneyin.")
        elif resp.status_code == 403:
            user = ("YouTube API erişimi reddedildi. API anahtarınızı ve Google Cloud "
                    "üzerinde YouTube Data API v3'ün etkinleştirildiğini kontrol edin.")
        elif resp.status_code in (500, 502, 503, 504):
            user = "YouTube geçici bir hata verdi. Lütfen kısa bir süre sonra tekrar deneyin."
        elif resp.status_code == 400:
            user = "İstek YouTube tarafından kabul edilmedi. Arama ölçütlerinizi kontrol edin."
        else:
            user = "Arama gerçekleştirilemedi. İnternet bağlantınızı ve API ayarlarınızı kontrol edin."
        return YouTubeError(user, detail)

    # ------------------------------------------------------------ genel API
    def validate_key(self) -> bool:
        """Anahtari dusuk maliyetli bir istekle dener. Hata durumunda YouTubeError firlatir."""
        self._get("channels", {"part": "id", "id": _KEY_TEST_CHANNEL_ID})
        return True

    def search_page(
        self,
        query: str,
        channel_id: str | None = None,
        published_after: dt.date | None = None,
        published_before: dt.date | None = None,
        page_token: str | None = None,
        max_results: int = 50,
    ) -> tuple[list[VideoResult], str]:
        """Bir sayfa video arar. (video listesi, sonraki sayfa tokeni) dondurur."""
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": max_results,
            "order": "date",
            "safeSearch": "none",
            "fields": "nextPageToken,items(id/videoId,snippet(publishedAt,channelId,channelTitle,title))",
        }
        if channel_id:
            params["channelId"] = channel_id
        if published_after:
            params["publishedAfter"] = _to_rfc3339_start(published_after)
        if published_before:
            params["publishedBefore"] = _to_rfc3339_end(published_before)
        if page_token:
            params["pageToken"] = page_token

        data = self._get("search", params)
        videos: list[VideoResult] = []
        for item in data.get("items", []):
            video_id = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}
            if not video_id:
                continue
            videos.append(VideoResult(
                video_id=video_id,
                title=str(snippet.get("title", "")),
                channel_id=str(snippet.get("channelId", "")),
                channel_title=str(snippet.get("channelTitle", "")),
                published_at=str(snippet.get("publishedAt", "")),
                url=VideoResult.make_url(video_id),
            ))
        return videos, str(data.get("nextPageToken") or "")
