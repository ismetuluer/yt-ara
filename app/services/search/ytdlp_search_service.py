"""yt-dlp tabanli (API'siz) arama motoru.

Genel arama ve kanal taramasi yapar. Sayfalama, yt-dlp'nin sinirlari
nedeniyle "daha buyuk bir kume getirip kalanini dondur" seklinde uygulanir;
bu yuzden sonuclar YouTube ve yt-dlp tarafindan erisilebilen sonuclarla
sinirlidir.
"""
import datetime as dt
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.models.video import VideoResult
from app.services.search.base_search_service import SearchEngine
from app.services.ytdlp_service import YtDlpError, YtDlpService

# Varsayilan kanal tarama siniri (son N video)
DEFAULT_CHANNEL_LIMIT = 100
# Genel aramada tek seferde cekilen sonuc sayisi
SEARCH_BATCH = 50
# "Tum sonuclari getir" icin guvenlik ust siniri
MAX_SEARCH_RESULTS = 500
# Kanal taramasinda tarih zenginlestirme icin es zamanli istek sayisi
DATE_FETCH_WORKERS = 12


def _date_in_range(published_at: str, after: dt.date | None, before: dt.date | None) -> bool:
    """Yayin tarihi (ISO) verilen aralikta mi? Tarih yoksa aralik yoksa True."""
    if not published_at:
        return True
    try:
        d = dt.date.fromisoformat(published_at[:10])
    except ValueError:
        return True
    if after and d < after:
        return False
    if before and d > before:
        return False
    return True


def _exact_phrase_match(title: str, phrase: str) -> bool:
    """Tam ifade filtresi: ifade baslikta butun halinde mi (harf duyarsiz).

    Turkce ozel karakterler (I/i, İ/ı) dogru eslesir.
    """
    if not phrase:
        return True
    return _turkish_fold(phrase) in _turkish_fold(title)


def _turkish_fold(text: str) -> str:
    """Turkce harf duyarsiz karsilastirma icin metni normalize eder."""
    return (text.casefold()
            .replace("i̇", "i")   # İ -> i (noktali buyuk I)
            .replace("ı", "i")    # ı -> i (noktasiz kucuk i)
            .replace("ş", "s").replace("ç", "c")
            .replace("ğ", "g").replace("ü", "u").replace("ö", "o"))


class YtDlpSearchEngine(SearchEngine):
    name = "ytdlp"

    def __init__(self, timeout: int = 30):
        self.service = YtDlpService(timeout=timeout)
        self.log = logging.getLogger("yt_ara.ytdlp_engine")
        # channel_id -> orijinal kanal adresi (kanal taramasi icin)
        self._channel_urls: dict[str, str] = {}
        self._channel_scan_limit = DEFAULT_CHANNEL_LIMIT

    # ------------------------------------------------------------ arayuz
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
        if channel_id:
            return self._search_channel(
                channel_id, query, published_after, published_before,
                page_token, max_results, on_video=on_video)
        return self._search_general(
            query, published_after, published_before, page_token, max_results,
            on_video=on_video)

    def resolve_channel(self, text: str) -> tuple[str, str]:
        channel_id, title = self.service.resolve_channel(text)
        self._channel_urls[channel_id] = text.strip()
        return channel_id, title

    def validate_available(self) -> bool:
        return True  # yt-dlp her zaman kullanilabilir

    def cancel(self) -> None:
        """Devam eden istegi mumkunse hemen durdurur."""
        self.service.cancel()

    # ------------------------------------------------------------ genel arama
    def _search_general(
        self,
        query: str,
        after: dt.date | None,
        before: dt.date | None,
        page_token: str | None,
        max_results: int,
        on_video: Callable[[VideoResult], None] | None = None,
    ) -> tuple[list[VideoResult], str]:
        offset = int(page_token) if page_token else 0
        fetch = min(offset + max_results, MAX_SEARCH_RESULTS)
        # Once hizli (flat) liste alinir -- her video icin ayri sayfa
        # cekmez, bu yuzden fetch buyudukce (sayfalama ilerledikce) yavas
        # veya zaman asimina ugrayan bir cagri olmaz. Daha once burada tam
        # metadata (`search`) kullaniliyordu; bu, "Daha Fazla Sonuc Getir"
        # tikladikca N videonun tumunu YENIDEN tek bir cagrida tam olarak
        # cikarmaya calisiyordu ve N buyudukce zaman asimiyla basarisiz
        # olabiliyordu.
        flat = self.service.search_flat(query, max_results=fetch)
        # Bu sayfada daha once zenginlestirilmemis (yeni) videolar
        new_videos = flat[offset:fetch]
        page = self._enrich_and_filter(new_videos, after, before, on_video=on_video)
        next_offset = offset + max_results
        # "Daha fazla var mi" sorusu, tarih filtresinden kac tanesinin
        # gectigine degil, yt-dlp'nin istenen kadar video dondurup
        # dondurmedigine bakilarak cevaplanir. Aksi halde -- ozellikle
        # tarih filtresinden pek video elenmediginde -- filtrelenmis
        # uzunluk her zaman fetch'e esit kalir ve "daha fazla" hicbir zaman
        # etkinlesmez, oysa YouTube'da gercekte daha fazla sonuc olabilir.
        has_more = next_offset < MAX_SEARCH_RESULTS and len(flat) >= fetch
        return page, (str(next_offset) if has_more else "")

    # ------------------------------------------------------------ kanal taramasi
    def _search_channel(
        self,
        channel_id: str,
        query: str,
        after: dt.date | None,
        before: dt.date | None,
        page_token: str | None,
        max_results: int,
        on_video: Callable[[VideoResult], None] | None = None,
    ) -> tuple[list[VideoResult], str]:
        url = self._channel_urls.get(channel_id)
        if not url:
            # Kanal adresi bilinmiyorsa channel_id uzerinden dene
            url = f"https://www.youtube.com/channel/{channel_id}"
        limit = int(page_token) if page_token else self._channel_scan_limit
        # 1. Hizli flat tarama (yayin tarihi olmadan)
        videos = self.service.channel_videos_flat(url, limit=limit)
        # 2. Sorgu / tam ifade filtresi
        if query:
            videos = [v for v in videos if _exact_phrase_match(v.title, query)]
        # 3. Tarih zenginlestirme + filtre (yalnizca gereken videolar icin)
        videos = self._enrich_and_filter(videos, after, before, on_video=on_video)
        return videos, ""

    def _enrich_and_filter(
        self,
        videos: list[VideoResult],
        after: dt.date | None,
        before: dt.date | None,
        on_video: Callable[[VideoResult], None] | None = None,
    ) -> list[VideoResult]:
        """Yayin tarihi eksik videolari zenginlestirir ve aralikla filtreler.

        Tarihi zaten bilinen videolar hemen degerlendirilir; bilinmeyenler
        (yt-dlp'nin duz/flat listelemesi tarih vermez) paralel olarak
        cekilir. `on_video` verilmisse her video, TUMU bitmeden -- tek tek
        hazir oldukca -- geri bildirilir; boylece cagiran taraf (arama
        is parcacigi) sonuclari arayuze aninda ekleyebilir.
        """
        result: list[VideoResult] = []

        def emit(video: VideoResult) -> None:
            result.append(video)
            if on_video:
                on_video(video)

        if after is None and before is None:
            for v in videos:
                emit(v)
            return result

        pending: list[VideoResult] = []
        for v in videos:
            if v.published_at:
                if _date_in_range(v.published_at, after, before):
                    emit(v)
            else:
                pending.append(v)

        if not pending:
            return result

        def fetch(video: VideoResult) -> VideoResult:
            try:
                video.published_at = self.service.video_upload_date(video.video_id)
            except YtDlpError:
                self.log.warning("Tarih alinamadi: %s", video.video_id)
            return video

        with ThreadPoolExecutor(max_workers=DATE_FETCH_WORKERS) as pool:
            futures = [pool.submit(fetch, v) for v in pending]
            for future in as_completed(futures):
                video = future.result()
                if _date_in_range(video.published_at, after, before):
                    emit(video)
        return result

    def set_channel_scan_limit(self, limit: int) -> None:
        """Kanal tarama kapsamini ayarlar (son N video)."""
        self._channel_scan_limit = limit
