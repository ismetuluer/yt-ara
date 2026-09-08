"""yt-dlp tabanli dusuk seviyeli servis.

Arama, kanal cozumleme ve metadata alma islemlerini yt-dlp uzerinden yapar.
Video indirme islemleri download_service icinde ayri ele alinir.

`tools/yt-dlp/yt-dlp.exe` varsa (updater'in indirdigi guncel standalone
binary) islemler onun uzerinden (subprocess, --dump-single-json) yapilir;
yoksa gömülü yt-dlp modulu kullanilir. Boylece updater'in guncelledigi
surum, download_service ile ayni sekilde arama tarafinda da etkin olur.
"""
import datetime as dt
import html
import json
import logging
import os
import re
import subprocess
import sys
import threading

import yt_dlp

from app.models.video import VideoResult
from app.utils.paths import ytdlp_binary
from app.utils.process_utils import kill_process_tree

# Kanal URL'sinden kanal kimligi cikarir (channel/UC... veya @handle)
_CHANNEL_ID_RE = re.compile(r"youtube\.com/channel/(UC[\w-]{22})", re.IGNORECASE)
_HANDLE_RE = re.compile(r"youtube\.com/@([\w.\-]+)", re.IGNORECASE)


class YtDlpError(Exception):
    """Kullaniciya gosterilecek Turkce mesaj + teknik ayrinti tasir."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


def _upload_date_to_iso(upload_date: str | None) -> str:
    """yt-dlp upload_date (YYYYMMDD) -> ISO 8601 (YYYY-MM-DDT00:00:00Z)."""
    if not upload_date or len(upload_date) != 8:
        return ""
    try:
        d = dt.datetime.strptime(upload_date, "%Y%m%d")
        return d.strftime("%Y-%m-%dT00:00:00Z")
    except ValueError:
        return ""


def _entry_to_video(entry: dict, fallback_channel: str = "",
                    fallback_channel_id: str = "") -> VideoResult | None:
    """yt-dlp entry'sini VideoResult'a cevirir. Video ID yoksa None."""
    video_id = entry.get("id")
    if not video_id:
        return None
    # YouTube baslik/kanal adlarini bazen HTML kaciriciyla dondurur
    # (ornek: "Alihan Kuriş&#39;in..."); kullaniciya ham haliyle gosterilmemesi
    # icin cozulur.
    title = html.unescape(str(entry.get("title") or ""))
    channel = html.unescape(str(entry.get("channel") or entry.get("uploader") or fallback_channel or ""))
    channel_id = str(entry.get("channel_id") or entry.get("uploader_id") or fallback_channel_id or "")
    published = _upload_date_to_iso(entry.get("upload_date"))
    duration = entry.get("duration")
    try:
        duration = int(duration) if duration is not None else 0
    except (TypeError, ValueError):
        duration = 0
    return VideoResult(
        video_id=video_id,
        title=title,
        channel_id=channel_id,
        channel_title=channel,
        published_at=published,
        url=VideoResult.make_url(video_id),
        duration=duration,
    )


class YtDlpService:
    """yt-dlp uzerinden arama / kanal / metadata islemleri."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.log = logging.getLogger("yt_ara.ytdlp")
        self._cancelled = threading.Event()
        self._proc_lock = threading.Lock()
        # Tarih zenginlestirme (_with_dates) ayni servis nesnesini paralel
        # iş parçacıklarından cagirir; bu yuzden tek bir surec yerine
        # kumelenmis (birden fazla es zamanli) suracler tutulur.
        self._current_procs: set = set()

    def cancel(self) -> None:
        """Devam eden istekleri mumkunse hemen durdurur (harici yt-dlp.exe icin)."""
        self._cancelled.set()
        with self._proc_lock:
            procs = list(self._current_procs)
        for proc in procs:
            if proc.poll() is None:
                kill_process_tree(proc)

    def reset_cancel(self) -> None:
        self._cancelled.clear()

    # ------------------------------------------------------------ yardimcilar
    def _base_opts(self, **extra) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": self.timeout,
            "retries": 2,
            # YouTube'un varsayilan istemciye "bot" supheliyle 403/dogrulama
            # istemesine karsi android istemcisi kullanilir (download_service
            # ile ayni yaygin cozum; aksi halde arama/metadata cagrilari
            # gereksiz yere basarisiz olabilir).
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            # 50 sonuclu bir aramada TEK bir video (ornegin yasa bagli
            # kisitli) erisilemez oldugunda tum arama basarisiz olmasin;
            # yalnizca o video atlanir.
            "ignoreerrors": True,
        }
        opts.update(extra)
        return opts

    def _extract(self, url: str, opts: dict) -> dict:
        if self._cancelled.is_set():
            raise YtDlpError("İptal edildi.", "cancelled")
        cmd_prefix = self._subprocess_prefix()
        if cmd_prefix:
            return self._extract_external(cmd_prefix, url, opts)
        return self._extract_module(url, opts)

    def _external_binary(self) -> str | None:
        """Guncel standalone yt-dlp.exe yolu (varsa)."""
        path = ytdlp_binary()
        return path if os.path.isfile(path) else None

    def _subprocess_prefix(self) -> list[str] | None:
        """Bilgi cikarma islemini calistiracak komut on eki.

        Oncelik `tools/yt-dlp/yt-dlp.exe` (guncellenebilir standalone
        binary). O yoksa, dondurulmus (PyInstaller) EXE degilsek kendi
        yorumlayicimizla `python -m yt_dlp` calistirilir — boylece gömülü
        modul de subprocess olarak calisir ve iptal (kill) gercekten
        calisir; extract_info() in-process cagrilirsa iptal edilemez.
        Yalnizca dondurulmus EXE'de (surumu guncellenemeyen eski dagitim
        yontemi) baska secenek olmadigindan in-process modul kullanilir.
        """
        binary = self._external_binary()
        if binary:
            return [binary]
        if not getattr(sys, "frozen", False):
            return [sys.executable, "-m", "yt_dlp"]
        return None

    def _extract_module(self, url: str, opts: dict) -> dict:
        """Gömülü yt-dlp modulu ile bilgi cikarir."""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            self.log.warning("yt-dlp hatasi (%s): %s", url, exc)
            raise YtDlpError(
                "Arama gerçekleştirilemedi. YouTube'a erişilemedi veya geçici bir "
                "hata oluştu. Lütfen tekrar deneyin.",
                str(exc),
            ) from exc
        except Exception as exc:  # beklenmeyen hata
            self.log.exception("yt-dlp beklenmeyen hata (%s)", url)
            raise YtDlpError(
                "Arama gerçekleştirilemedi. Beklenmeyen bir hata oluştu.",
                str(exc),
            ) from exc
        if info is None:  # ignoreerrors: True iken tum hedef basarisiz oldu
            raise YtDlpError(
                "Arama gerçekleştirilemedi. YouTube'a erişilemedi veya geçici "
                "bir hata oluştu. Lütfen tekrar deneyin.")
        return info

    def _extract_external(self, cmd_prefix: list[str], url: str, opts: dict) -> dict:
        """Ayri bir surecte (subprocess) bilgi cikarir.

        `cmd_prefix`, standalone `yt-dlp.exe` ya da `[python, -m, yt_dlp]`
        olabilir. `--dump-single-json`, gömülü modulun `extract_info()`
        donusuyle ayni yapida (playlist/kanal icin "entries" alani dahil)
        tek bir JSON nesnesi verir; boylece cagiran kod (search/kanal/
        metadata) motor farketmeksizin ayni sekilde calisir. Subprocess
        olmasi, iptal edildiginde surecin gercekten oldurulebilmesini
        saglar (in-process cagriyi iptal etmenin guvenilir bir yolu yoktur).
        """
        cmd = list(cmd_prefix) + ["--dump-single-json", "--no-warnings"]
        if opts.get("ignoreerrors"):
            cmd.append("--ignore-errors")
        if opts.get("noplaylist"):
            cmd.append("--no-playlist")
        if opts.get("extract_flat"):
            cmd.append("--flat-playlist")
        if opts.get("playlistend"):
            cmd += ["--playlist-end", str(opts["playlistend"])]
        player_clients = (opts.get("extractor_args", {})
                          .get("youtube", {}).get("player_client"))
        if player_clients:
            cmd += ["--extractor-args", "youtube:player_client=" + ",".join(player_clients)]
        socket_timeout = opts.get("socket_timeout", self.timeout)
        cmd += ["--socket-timeout", str(socket_timeout)]
        retries = opts.get("retries", 2)
        cmd += ["--retries", str(retries)]
        cmd.append(url)

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            self.log.warning("yt-dlp (harici) baslatilamadi: %s", exc)
            raise YtDlpError(
                "Arama gerçekleştirilemedi. yt-dlp başlatılamadı.", str(exc),
            ) from exc

        with self._proc_lock:
            self._current_procs.add(proc)
        if self._cancelled.is_set():
            # cancel() proc kaydedilmeden hemen once cagrilmis olabilir
            kill_process_tree(proc)
        try:
            out, err = proc.communicate(
                timeout=socket_timeout * (retries + 1) + 30)
        except subprocess.TimeoutExpired as exc:
            kill_process_tree(proc)
            proc.communicate()
            self.log.warning("yt-dlp (harici) zaman asimi (%s): %s", url, exc)
            raise YtDlpError(
                "Arama gerçekleştirilemedi. YouTube'a erişilemedi veya geçici bir "
                "hata oluştu. Lütfen tekrar deneyin.",
                str(exc),
            ) from exc
        finally:
            with self._proc_lock:
                self._current_procs.discard(proc)

        if self._cancelled.is_set():
            raise YtDlpError("İptal edildi.", "cancelled")

        # --ignore-errors ile bir alt ogenin (ornegin uyeliğe ozel bir video)
        # cikarimi basarisiz olsa bile yt-dlp gecerli JSON basar ama cikis
        # kodu yine de 0'dan farkli olabilir. Bu yuzden dondurulen JSON
        # gecerliyse cikis kodu tek basina hata sayilmaz. Ancak tek hedefin
        # (ör. tek video metadata'si) kendisi basarisiz olursa yt-dlp "null"
        # basabilir; bu da hata olarak ele alinmali.
        if out.strip():
            try:
                data = json.loads(out)
            except ValueError:
                data = None
            if data is not None:
                return data

        detail = (err or "").strip()[-1000:]
        self.log.warning("yt-dlp (harici) hatasi (%s): %s", url, detail)
        raise YtDlpError(
            "Arama gerçekleştirilemedi. YouTube'a erişilemedi veya geçici bir "
            "hata oluştu. Lütfen tekrar deneyin.",
            detail,
        )

    # ------------------------------------------------------------ genel arama
    def search_flat(self, query: str, max_results: int = 50) -> list[VideoResult]:
        """Genel YouTube aramasi yapar; hizli (flat) liste, yayin tarihi yok.

        Sonuc sayfasini tek seferde okur (her video icin ayri sayfa
        cekmez); bu yuzden buyuk `max_results` degerlerinde bile hizli ve
        zaman asimina dayaniklidir. Yayin tarihi gerekiyorsa ayrica
        `video_upload_date` ile (yalnizca gereken videolar icin) alinir.
        """
        url = f"ytsearch{max_results}:{query}"
        info = self._extract(url, self._base_opts(extract_flat="in_playlist"))
        entries = info.get("entries") or []
        videos: list[VideoResult] = []
        for entry in entries:
            video = _entry_to_video(entry)
            if video:
                videos.append(video)
        return videos

    # ------------------------------------------------------------ kanal
    def resolve_channel(self, text: str) -> tuple[str, str]:
        """Kanal metnini (channel_id, channel_title) olarak cozumler.

        Bulunamazsa YtDlpError firlatir.
        """
        text = text.strip()
        if not text:
            raise YtDlpError("Kanal adresi boş olamaz.")
        # Kanal basligini almak icin yalnizca ilk kaydi iste; tum kanali
        # islemek yavas olur.
        info = self._extract(text, self._base_opts(playlistend=1))
        channel_id = info.get("channel_id") or info.get("uploader_id") or ""
        channel_title = info.get("channel") or info.get("uploader") or ""
        if not channel_id:
            self.log.info("Kanal cozumlenemedi: %s", text)
            raise YtDlpError(
                f"Kanal bulunamadı: {text}\nLütfen kanal adresini kontrol edin."
            )
        return channel_id, channel_title

    def channel_videos(self, channel_url: str, limit: int = 100) -> list[VideoResult]:
        """Kanalin video listesini alir (tam metadata, yavas).

        channel_url bir kanal adresi olabilir (@handle, /channel/UC..., /c/...).
        Her video ayri cozumlenir; bu yuzden buyuk kanallarda yavas olabilir.
        """
        videos_url = self._channel_videos_url(channel_url)
        info = self._extract(videos_url, self._base_opts(playlistend=limit))
        fallback_channel = str(info.get("channel") or info.get("uploader") or "")
        fallback_channel_id = str(info.get("channel_id") or info.get("uploader_id") or "")
        entries = info.get("entries") or []
        videos: list[VideoResult] = []
        for entry in entries:
            video = _entry_to_video(entry, fallback_channel, fallback_channel_id)
            if video:
                videos.append(video)
        return videos

    def channel_videos_flat(self, channel_url: str, limit: int = 100) -> list[VideoResult]:
        """Kanalin video listesini hizli alir (flat, yayin tarihi yok).

        Yayin tarihi gerekmeyen taramalar icin hizlidir. upload_date bos olur.
        """
        videos_url = self._channel_videos_url(channel_url)
        info = self._extract(
            videos_url, self._base_opts(playlistend=limit, extract_flat="in_playlist"))
        fallback_channel = str(info.get("channel") or info.get("uploader") or "")
        fallback_channel_id = str(info.get("channel_id") or info.get("uploader_id") or "")
        entries = info.get("entries") or []
        videos: list[VideoResult] = []
        for entry in entries:
            video = _entry_to_video(entry, fallback_channel, fallback_channel_id)
            if video:
                videos.append(video)
        return videos

    def video_upload_date(self, video_id: str) -> str:
        """Tek bir videonun yayin tarihini (ISO) dondurur."""
        info = self.video_metadata(video_id)
        return _upload_date_to_iso(info.get("upload_date"))

    @staticmethod
    def _channel_videos_url(channel_url: str) -> str:
        """Kanal adresini /videos sekmesine yonlendirir."""
        url = channel_url.strip()
        if url.endswith("/videos"):
            return url
        if url.endswith("/"):
            return url + "videos"
        return url + "/videos"

    # ------------------------------------------------------------ metadata
    def video_metadata(self, video_id: str) -> dict:
        """Tek bir videonun metadata'sini alir."""
        url = VideoResult.make_url(video_id)
        info = self._extract(url, self._base_opts())
        return info
