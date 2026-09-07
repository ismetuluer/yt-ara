"""YouTube Data API v3 gunluk kota kullanimini tahmini olarak izler.

YouTube API, kalan/kullanilan kotayi hicbir response'ta dondurmez; bu
yuzden burada yalnizca BU uygulamanin yaptigi cagrilar, bilinen birim
maliyetlerine gore sayilir. Ayni anahtar baska bir yerde de kullaniliyorsa
gercek kalan kota burada gosterilenden daha az olabilir.
"""
import datetime as dt

from app.services.settings_service import SettingsService

# Pasifik saati (kota sifirlama noktasi) icin yaklasik sabit fark.
# DST hesaba katilmaz; tahmini bir sayac oldugu icin yeterlidir.
_PT_OFFSET_HOURS = 8

# YouTube Data API v3 bilinen birim maliyetleri (endpoint adina gore).
ENDPOINT_COSTS = {
    "search": 100,
    "channels": 1,
    "videos": 1,
    "playlistItems": 1,
}
DEFAULT_COST = 1


class QuotaTracker:
    def __init__(self, settings: SettingsService):
        self.settings = settings

    @staticmethod
    def _pt_today() -> str:
        now_pt = dt.datetime.utcnow() - dt.timedelta(hours=_PT_OFFSET_HOURS)
        return now_pt.date().isoformat()

    def _roll_if_new_day(self) -> None:
        if self.settings.quota_date != self._pt_today():
            self.settings.quota_date = self._pt_today()
            self.settings.quota_used = 0

    def record(self, endpoint: str) -> None:
        self._roll_if_new_day()
        cost = ENDPOINT_COSTS.get(endpoint, DEFAULT_COST)
        self.settings.quota_used = self.settings.quota_used + cost
        self.settings.save()

    def used(self) -> int:
        self._roll_if_new_day()
        return self.settings.quota_used

    def limit(self) -> int:
        return self.settings.quota_limit

    def percent(self) -> int:
        limit = max(self.limit(), 1)
        return min(100, int(self.used() * 100 / limit))
