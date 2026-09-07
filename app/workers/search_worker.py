"""Arka planda calisan arama is parcacigi.

Ana arayuzu bloklamamak icin arama cagrilari bu QThread icinde yapilir.
Sonuclar hazir oldukca (kanal/sayfa bazinda) `partial` sinyaliyle
yayinlanir; arayuz tum arama bitmeden sonuclari listeye ekleyebilir.
Iptal, istekler arasinda kontrol edilir ve motor destekliyorsa devam eden
istek de hemen durdurulur; o ana kadar toplanan sonuclar korunur.

Arama motoru (SearchEngine) uzerinden calisir; UI hangi motorun
kullanildigini bilmez.
"""
import logging
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Signal

from app.services.channel_resolver import ChannelInfo
from app.services.search.base_search_service import SearchEngine
from app.services.search.ytdlp_search_service import _exact_phrase_match
from app.services.ytdlp_service import YtDlpError
from app.services.youtube_service import YouTubeError

MAX_ROUNDS = 25  # "Tum sonuclari getir" icin hedef basina guvenlik siniri
STREAM_FLUSH_SIZE = 5    # bu kadar video biriktikce arayuze hemen gonderilir
STREAM_FLUSH_SECONDS = 0.5  # az sonuclu aramalarda da duzenli akis icin


@dataclass
class SearchTask:
    query: str
    date_from: object = None            # datetime.date | None
    date_to: object = None              # datetime.date | None
    channel_inputs: list = field(default_factory=list)   # ham kanal adresleri
    exclude_channel_inputs: list = field(default_factory=list)  # haric tutulacak kanal adresleri
    page_tokens: dict = field(default_factory=dict)      # channel_id (""=genel) -> token
    fetch_all: bool = False
    exact_phrase: bool = False          # tam ifade filtresi (UI ayarlar)
    channel_scan_scope: str = "100"     # 100 | 500 | 1000 | all


class SearchWorker(QThread):
    progress = Signal(str)
    # Sonuclar hazir oldukca: (yeni videolar, o ana kadar cozumlenmis kanallar)
    partial = Signal(list, list)
    # Arama tamamen bitince: (kanallar, guncel tokenlar, devam_var_mi, iptal_mi)
    search_done = Signal(list, dict, bool, bool)
    failed = Signal(str)

    def __init__(self, engine: SearchEngine, task: SearchTask,
                 resolved_channels=None, existing_ids=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.task = task
        self._resolved_channels = resolved_channels
        self._existing_ids = set(existing_ids or [])
        self._cancel = False
        self.log = logging.getLogger("yt_ara.worker")

    def cancel(self) -> None:
        self._cancel = True
        # Motor destekliyorsa (yt-dlp harici binary) devam eden istegi
        # hemen durdurur; aksi halde iptal bir sonraki kontrol noktasinda
        # (istekler arasinda) fark edilir.
        engine_cancel = getattr(self.engine, "cancel", None)
        if engine_cancel:
            engine_cancel()

    # ------------------------------------------------------------ ana dongu
    def run(self) -> None:
        try:
            channels = self._resolve_channels()
            if channels is None:  # iptal edildi
                self.search_done.emit([], dict(self.task.page_tokens), False, True)
                return
            exclude_ids = self._resolve_excludes()
            targets = channels if channels else [None]
            self._run_search(targets, channels, exclude_ids)
        except (YouTubeError, YtDlpError) as exc:
            if exc.detail:
                self.log.warning("Arama hatasi: %s", exc.detail)
            self.failed.emit(exc.user_message)
        except Exception as exc:  # beklenmeyen hata
            self.log.exception("Beklenmeyen arama hatasi")
            self.failed.emit(
                "Beklenmeyen bir hata oluştu. Ayrıntılar logs klasörüne kaydedildi.")
            _ = exc

    def _resolve_channels(self):
        """Kanal girislerini cozumler. Yalnizca iptal edilirse None dondurur.

        Gercek bir hata olusursa (mesela kanal bulunamadi) burada None
        dondurmek yerine YouTubeError/YtDlpError firlatilir; aksi halde
        `run()` bunu "iptal edildi" ile karistirip hem hata mesajini hem
        de "Arama iptal edildi" durumunu ayni anda gosterebilir.
        """
        if self._resolved_channels is not None:
            return self._resolved_channels
        inputs = list(self.task.channel_inputs)
        channels: list[ChannelInfo] = []
        total = len(inputs)
        for i, raw in enumerate(inputs, 1):
            if self._cancel:
                return None
            self.progress.emit(f"Kanal çözümleniyor ({i}/{total}): {raw}")
            try:
                channel_id, title = self.engine.resolve_channel(raw)
            except (YouTubeError, YtDlpError):
                raise
            except Exception as exc:
                self.log.exception("Kanal cozumleme hatasi: %s", raw)
                raise YouTubeError(
                    f"Kanal çözümlenemedi: {raw}\nLütfen adresi kontrol edin.") from exc
            if channel_id and not any(c.channel_id == channel_id for c in channels):
                channels.append(ChannelInfo(channel_id=channel_id, title=title))
        return channels

    def _resolve_excludes(self) -> set:
        """Haric tutulacak kanallarin ID'lerini cozer.

        Bu bir "en iyi caba" filtresidir: kanal scope'unun aksine, tek bir
        kanalin cozumlenememesi tum aramayi basarisiz saymaz -- yalnizca o
        kanal haric tutulamamis olur (loglanir, sessizce atlanir).
        """
        ids = set()
        for raw in self.task.exclude_channel_inputs:
            if self._cancel:
                break
            try:
                channel_id, _ = self.engine.resolve_channel(raw)
                if channel_id:
                    ids.add(channel_id)
            except Exception as exc:
                self.log.warning("Haric tutulacak kanal cozumlenemedi: %s (%s)", raw, exc)
        return ids

    def _run_search(self, targets, channels, exclude_ids: set) -> None:
        tokens = dict(self.task.page_tokens)
        seen = set(self._existing_ids)
        total_channels = len(targets)
        multi = total_channels > 1
        rounds = 0
        canceled = False

        # Motor destekliyorsa (yt-dlp) videolar tek tek hazir oldukca bu
        # tampona eklenip kucuk gruplar halinde `partial` ile gonderilir;
        # boylece kullanici, kanal/sayfa taramasi tamamen bitmeden sonuclari
        # gormeye baslar (onceden yalnizca her hedef/sayfa bittiginde toplu
        # gonderiliyordu, bu da buyuk kanal taramalarinda uzun sessiz
        # bekleme hissi veriyordu).
        buffer: list = []
        last_flush = time.monotonic()

        def flush() -> None:
            nonlocal last_flush
            if buffer:
                self.partial.emit(list(buffer), channels)
                buffer.clear()
                last_flush = time.monotonic()

        def on_video(video) -> None:
            if self._cancel or video.video_id in seen:
                return
            if exclude_ids and video.channel_id in exclude_ids:
                return
            if self.task.exact_phrase and not _exact_phrase_match(video.title, self.task.query):
                return
            seen.add(video.video_id)
            buffer.append(video)
            # Sonuc az geldiginde (ornegin dar bir sorguda) yalnizca sayi
            # esigine gore beklemek, tumu bitene kadar akisin gorunmemesine
            # yol acabilir; bu yuzden belirli bir sure gectiyse de gonderilir.
            if len(buffer) >= STREAM_FLUSH_SIZE or (time.monotonic() - last_flush) >= STREAM_FLUSH_SECONDS:
                flush()

        while True:
            rounds += 1
            for idx, target in enumerate(targets, 1):
                if self._cancel:
                    canceled = True
                    break
                key = target.channel_id if target else ""
                token = tokens.get(key)
                if token == "":      # bu hedef icin sonuca ulasilmis
                    continue
                if rounds > 1 and token is None:
                    continue
                if self.task.fetch_all:
                    self.progress.emit("Tüm sonuçlar getiriliyor...")
                else:
                    label = target.title if target else "Tüm YouTube"
                    prefix = f"{total_channels} kanal taranıyor ({idx}/{total_channels}): " if multi else ""
                    self.progress.emit(f"{prefix}{label} — aranıyor...")

                videos, next_token = self.engine.search_page(
                    self.task.query,
                    channel_id=target.channel_id if target else None,
                    published_after=self.task.date_from,
                    published_before=self.task.date_to,
                    page_token=token,
                    on_video=on_video,
                )
                tokens[key] = next_token or ""
                # `on_video` yukarida her videoyu zaten akis olarak
                # gonderdi/`seen`e ekledi; burada yalnizca (motor akisi
                # desteklemiyorsa, ornegin API motoru gec cagirdiysa) kalan
                # olasi videolar icin guvenlik agi olarak calisir.
                fresh = [v for v in videos if v.video_id not in seen]
                if exclude_ids:
                    fresh = [v for v in fresh if v.channel_id not in exclude_ids]
                if self.task.exact_phrase:
                    fresh = [v for v in fresh if _exact_phrase_match(v.title, self.task.query)]
                seen.update(v.video_id for v in fresh)
                if fresh:
                    self.partial.emit(fresh, channels)
                flush()

            if canceled or not self.task.fetch_all:
                break
            if not self._has_more(tokens):
                break
            if rounds >= MAX_ROUNDS:
                self.log.info("Guvenlik siniri: %d tur sonrasinda duruldu", rounds)
                break

        flush()
        self.search_done.emit(channels, tokens, self._has_more(tokens), canceled)

    @staticmethod
    def _has_more(tokens: dict) -> bool:
        return any(tokens.values())
