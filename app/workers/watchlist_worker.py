"""Izleme listesini arka planda denetleyen is parcacigi.

Her aktif izleme icin kanalin en son videolarini (hizli/flat) ceker,
daha once gorulmemis olanlari anahtar kelimeyle filtreler, hepsini
"gorulmus" olarak isaretler (bir daha bulunmus sayilmasinlar diye) ve
eslesenleri `found` sinyaliyle bildirir. Arayuz bloklanmasin diye QThread
icinde calisir.
"""
import logging

from PySide6.QtCore import QThread, Signal

from app.services.watchlist_service import WatchlistService, keyword_matches
from app.services.ytdlp_service import YtDlpError, YtDlpService

CHECK_LIMIT = 20  # her denetimde kanaldan cekilecek en son video sayisi


class WatchlistWorker(QThread):
    # (watch_id, kanal adi, [{'video_id','title','url','channel_title'}])
    found = Signal(int, str, list)
    progress = Signal(str)

    def __init__(self, watches: list[dict], service: WatchlistService | None = None, parent=None):
        super().__init__(parent)
        self.watches = watches
        self.service = service or WatchlistService()
        self.log = logging.getLogger("yt_ara.watchlist_worker")

    def run(self) -> None:
        service = self.service
        ytdlp = YtDlpService()
        for watch in self.watches:
            watch_id = watch["id"]
            url = watch["channel_url"]
            keyword = watch.get("keyword") or ""
            label = watch.get("channel_title") or url
            self.progress.emit(f"İzleniyor: {label}")
            try:
                videos = ytdlp.channel_videos_flat(url, limit=CHECK_LIMIT)
            except YtDlpError as exc:
                self.log.warning("Izleme taramasi basarisiz (%s): %s", url, exc.user_message)
                continue
            seen = service.seen_ids(watch_id)
            matches = []
            for video in videos:
                if video.video_id in seen:
                    continue
                service.mark_seen(watch_id, video.video_id, video.title, video.url)
                if keyword_matches(video.title, keyword):
                    matches.append({
                        "video_id": video.video_id, "title": video.title,
                        "url": video.url, "channel_title": label,
                    })
            service.mark_checked(watch_id)
            if matches:
                self.found.emit(watch_id, label, matches)
