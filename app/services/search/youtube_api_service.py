"""YouTube Data API v3 tabanli arama motoru.

Mevcut YouTubeService ve ChannelResolver'i sarmalar; SearchEngine
arayuzune uyarlar.
"""
import datetime as dt

from app.models.video import VideoResult
from app.services.channel_resolver import ChannelResolver
from app.services.search.base_search_service import SearchEngine
from app.services.youtube_service import YouTubeService


class YouTubeApiSearchEngine(SearchEngine):
    name = "api"

    def __init__(self, api_key: str, timeout: int = 20, quota_tracker=None):
        on_call = quota_tracker.record if quota_tracker else None
        self.service = YouTubeService(api_key, timeout=timeout, on_call=on_call)
        self.resolver = ChannelResolver(self.service)

    def search_page(
        self,
        query: str,
        channel_id: str | None = None,
        published_after: dt.date | None = None,
        published_before: dt.date | None = None,
        page_token: str | None = None,
        max_results: int = 50,
        on_video=None,
    ) -> tuple[list[VideoResult], str]:
        # API sonuclari zaten tek bir hizli cagriyla (tarihi dahil) gelir;
        # akis (streaming) gerektirmez, ancak arayuz uyumu icin videolar
        # yine de tek tek geri bildirilir.
        videos, token = self.service.search_page(
            query,
            channel_id=channel_id,
            published_after=published_after,
            published_before=published_before,
            page_token=page_token,
            max_results=max_results,
        )
        if on_video:
            for video in videos:
                on_video(video)
        return videos, token

    def resolve_channel(self, text: str) -> tuple[str, str]:
        info = self.resolver.resolve(text)
        return info.channel_id, info.title

    def validate_available(self) -> bool:
        return bool(self.service.api_key)
