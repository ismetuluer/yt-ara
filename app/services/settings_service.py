"""Kullanici ayarlari: AppData\\Local\\YouTubeSearch\\ayarlar.json icinde saklanir."""
import json
import os

from app.utils.paths import config_dir, legacy_config_dir

DEFAULTS = {
    "api_key": "",
    "theme": "system",      # system | light | dark
    "export_dir": "",
    "download_dir": "",
    "search_method": "auto",   # auto | api | ytdlp
    "exact_phrase": True,      # tam ifade filtresi
    "channel_scan_scope": "100",  # 100 | 500 | 1000 | all
    "frame_format": "jpg",     # jpg | png
    "ytdlp_last_check": "",    # otomatik denetimin yapildigi gun (YYYY-MM-DD)
    "saved_channels": [],      # eklenen kanal adresleri (oturumlar arasi)
    "notify_download_complete": True,  # indirme bitince bildirim goster
    "window_geometry": "",     # pencere konum/boyutu (hex, saveGeometry)
    "splitter_state": "",      # bolum boyutlari (hex, QSplitter.saveState)
    "quota_date": "",          # tahmini kota sayacinin ait oldugu gun (PT)
    "quota_used": 0,           # o gun icin tahmini kullanilan birim
    "quota_limit": 10000,      # gunluk kota siniri (artirim talebiyle degisebilir)
    "download_subtitles": False,   # indirirken altyazi da indirilsin mi
    "subtitle_langs": "tr,en",     # altyazi dilleri (virgulle ayrilmis)
    "hide_downloaded": False,      # daha once indirilenler sonuc listesinde gizlensin mi
    "watchlist_interval_minutes": 30,  # izleme listesi denetim araligi
    "app_update_last_check": "",   # uygulama surumu otomatik denetiminin yapildigi gun
    "app_update_skip_version": "", # kullanicinin "atla" dedigi surum (tekrar sorulmaz)
    "max_concurrent_downloads": 3,  # ayni anda indirilecek en fazla video sayisi
    "download_speed_limit_kbps": 0,  # indirme hizi siniri (KB/s); 0 = sinirsiz
}


class SettingsService:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config_dir(), "ayarlar.json")
        self.data = dict(DEFAULTS)
        self._migrate_legacy()
        self.load()

    def _migrate_legacy(self) -> None:
        """Eski (uygulama klasorundeki) ayarlar dosyasini yeni konuma tasir.

        Yalnizca yeni konumda henuz bir dosya yoksa calisir; boylece
        uygulama klasoru guncellenip/yeniden acilip kapatilirken kullanicinin
        ayarlari kaybolmaz.
        """
        if os.path.isfile(self.path):
            return
        legacy_path = os.path.join(legacy_config_dir(), "ayarlar.json")
        if not os.path.isfile(legacy_path):
            return
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(loaded, f, ensure_ascii=False, indent=2)
        except (OSError, ValueError):
            pass

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for key in DEFAULTS:
                    if key in loaded:
                        self.data[key] = loaded[key]
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @property
    def api_key(self) -> str:
        return str(self.data.get("api_key", "")).strip()

    @api_key.setter
    def api_key(self, value: str) -> None:
        self.data["api_key"] = value.strip()

    @property
    def theme(self) -> str:
        value = str(self.data.get("theme", "system"))
        return value if value in ("system", "light", "dark") else "system"

    @theme.setter
    def theme(self, value: str) -> None:
        self.data["theme"] = value

    @property
    def export_dir(self) -> str:
        return str(self.data.get("export_dir", ""))

    @export_dir.setter
    def export_dir(self, value: str) -> None:
        self.data["export_dir"] = value

    @property
    def download_dir(self) -> str:
        return str(self.data.get("download_dir", ""))

    @download_dir.setter
    def download_dir(self, value: str) -> None:
        self.data["download_dir"] = value

    @property
    def search_method(self) -> str:
        value = str(self.data.get("search_method", "auto"))
        return value if value in ("auto", "api", "ytdlp") else "auto"

    @search_method.setter
    def search_method(self, value: str) -> None:
        self.data["search_method"] = value

    @property
    def exact_phrase(self) -> bool:
        return bool(self.data.get("exact_phrase", True))

    @exact_phrase.setter
    def exact_phrase(self, value: bool) -> None:
        self.data["exact_phrase"] = bool(value)

    @property
    def channel_scan_scope(self) -> str:
        value = str(self.data.get("channel_scan_scope", "100"))
        return value if value in ("100", "500", "1000", "all") else "100"

    @channel_scan_scope.setter
    def channel_scan_scope(self, value: str) -> None:
        self.data["channel_scan_scope"] = value

    @property
    def frame_format(self) -> str:
        value = str(self.data.get("frame_format", "jpg"))
        return value if value in ("jpg", "png") else "jpg"

    @frame_format.setter
    def frame_format(self, value: str) -> None:
        self.data["frame_format"] = value

    @property
    def ytdlp_last_check(self) -> str:
        return str(self.data.get("ytdlp_last_check", ""))

    @ytdlp_last_check.setter
    def ytdlp_last_check(self, value: str) -> None:
        self.data["ytdlp_last_check"] = value

    @property
    def saved_channels(self) -> list[dict]:
        """Her ogesi {"url", "name", "active"} sozlugu olan kanal listesi.

        Eski surumlerde duz metin listesi olarak saklaniyordu; geriye
        donuk uyumluluk icin buraya donusturulur.
        """
        value = self.data.get("saved_channels", [])
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            if isinstance(item, str):
                result.append({"url": item, "name": "", "active": True})
            elif isinstance(item, dict) and item.get("url"):
                result.append({
                    "url": str(item["url"]),
                    "name": str(item.get("name", "")),
                    "active": bool(item.get("active", True)),
                })
        return result

    @saved_channels.setter
    def saved_channels(self, value: list[dict]) -> None:
        self.data["saved_channels"] = list(value)

    @property
    def notify_download_complete(self) -> bool:
        return bool(self.data.get("notify_download_complete", True))

    @notify_download_complete.setter
    def notify_download_complete(self, value: bool) -> None:
        self.data["notify_download_complete"] = bool(value)

    @property
    def window_geometry(self) -> str:
        return str(self.data.get("window_geometry", ""))

    @window_geometry.setter
    def window_geometry(self, value: str) -> None:
        self.data["window_geometry"] = value

    @property
    def splitter_state(self) -> str:
        return str(self.data.get("splitter_state", ""))

    @splitter_state.setter
    def splitter_state(self, value: str) -> None:
        self.data["splitter_state"] = value

    @property
    def quota_date(self) -> str:
        return str(self.data.get("quota_date", ""))

    @quota_date.setter
    def quota_date(self, value: str) -> None:
        self.data["quota_date"] = value

    @property
    def quota_used(self) -> int:
        try:
            return int(self.data.get("quota_used", 0))
        except (TypeError, ValueError):
            return 0

    @quota_used.setter
    def quota_used(self, value: int) -> None:
        self.data["quota_used"] = int(value)

    @property
    def quota_limit(self) -> int:
        try:
            return int(self.data.get("quota_limit", 10000)) or 10000
        except (TypeError, ValueError):
            return 10000

    @quota_limit.setter
    def quota_limit(self, value: int) -> None:
        self.data["quota_limit"] = int(value)

    @property
    def download_subtitles(self) -> bool:
        return bool(self.data.get("download_subtitles", False))

    @download_subtitles.setter
    def download_subtitles(self, value: bool) -> None:
        self.data["download_subtitles"] = bool(value)

    @property
    def subtitle_langs(self) -> str:
        return str(self.data.get("subtitle_langs", "tr,en")) or "tr,en"

    @subtitle_langs.setter
    def subtitle_langs(self, value: str) -> None:
        self.data["subtitle_langs"] = value

    @property
    def hide_downloaded(self) -> bool:
        return bool(self.data.get("hide_downloaded", False))

    @hide_downloaded.setter
    def hide_downloaded(self, value: bool) -> None:
        self.data["hide_downloaded"] = bool(value)

    @property
    def watchlist_interval_minutes(self) -> int:
        try:
            return max(5, int(self.data.get("watchlist_interval_minutes", 30)))
        except (TypeError, ValueError):
            return 30

    @watchlist_interval_minutes.setter
    def watchlist_interval_minutes(self, value: int) -> None:
        self.data["watchlist_interval_minutes"] = int(value)

    @property
    def app_update_last_check(self) -> str:
        return str(self.data.get("app_update_last_check", ""))

    @app_update_last_check.setter
    def app_update_last_check(self, value: str) -> None:
        self.data["app_update_last_check"] = value

    @property
    def app_update_skip_version(self) -> str:
        return str(self.data.get("app_update_skip_version", ""))

    @app_update_skip_version.setter
    def app_update_skip_version(self, value: str) -> None:
        self.data["app_update_skip_version"] = value

    @property
    def max_concurrent_downloads(self) -> int:
        try:
            value = int(self.data.get("max_concurrent_downloads", 3))
        except (TypeError, ValueError):
            return 3
        return min(6, max(1, value))

    @max_concurrent_downloads.setter
    def max_concurrent_downloads(self, value: int) -> None:
        self.data["max_concurrent_downloads"] = min(6, max(1, int(value)))

    @property
    def download_speed_limit_kbps(self) -> int:
        try:
            value = int(self.data.get("download_speed_limit_kbps", 0))
        except (TypeError, ValueError):
            return 0
        return max(0, value)

    @download_speed_limit_kbps.setter
    def download_speed_limit_kbps(self, value: int) -> None:
        self.data["download_speed_limit_kbps"] = max(0, int(value))
