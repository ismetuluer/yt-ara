"""Video indirme servisi (yt-dlp tabanli).

Kalite secimi, guvenli dosya adi, ilerleme geri cagrisi ve iptal destegi
saglar. FFmpeg varsa yuksek kaliteli video+ses akislari birlestirilir.
"""
import logging
import os
import re
import subprocess
import threading

import yt_dlp

from app.services.ffmpeg_service import find_ffmpeg
from app.utils.paths import ytdlp_binary
from app.utils.process_utils import kill_process_tree

# Windows'ta dosya adinda gecersiz karakterler
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])$', re.IGNORECASE)

# Kalite secenekleri: (etiket, yt-dlp format secimi)
# "bestvideo" (yildizsiz) yt-dlp'yi belirli video-only kodeklerle sinirlar;
# bazi videolarda (ozellikle yalnizca DASH/HLS formatlari sunulanlarda) bu
# hicbir formatla eslesmeyip "Requested format is not available" hatasina
# yol aciyordu. "bestvideo*" (yildizli) tum video-only formatlari (kodek
# farketmeksizin) degerlendirir; sonunda ayrica "/best" ile TEK dosyalik
# (onceden birlestirilmis) formatlara da dusulur -- boylece secilen kalite
# hicbir sekilde eslesmezse bile indirme tamamen basarisiz olmaz.
QUALITY_OPTIONS = [
    ("En İyi", "bestvideo*+bestaudio/best"),
    ("1080p", "bestvideo*[height<=1080]+bestaudio/best[height<=1080]/best"),
    ("720p", "bestvideo*[height<=720]+bestaudio/best[height<=720]/best"),
    ("480p", "bestvideo*[height<=480]+bestaudio/best[height<=480]/best"),
    ("En İyi Tek Dosya", "best"),
]


class DownloadError(Exception):
    """Kullaniciya gosterilecek Turkce mesaj + teknik ayrinti."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


def sanitize_filename(name: str) -> str:
    """Dosya adini Windows icin guvenli hale getirir."""
    name = _INVALID_CHARS.sub("_", name)
    name = name.strip().strip(".")
    if not name:
        name = "video"
    if _RESERVED.match(name):
        name = "_" + name
    # Uzunluk siniri (yol ile birlikte Windows 260 karakteri asmasin)
    if len(name) > 120:
        name = name[:120].rstrip(" .")
    return name


def build_output_template(channel_title: str, video_id: str) -> str:
    """Kanal adi / tarih - baslik [ID] yapisinda cikti sablonu uretir."""
    channel = sanitize_filename(channel_title or "Bilinmeyen Kanal")
    return os.path.join(
        channel,
        "%(upload_date>%Y-%m-%d)s - %(title)s [" + video_id + "].%(ext)s",
    )


class DownloadService:
    """Tek veya coklu video indirme islemlerini yonetir."""

    def __init__(self, download_dir: str, quality: str = "En İyi",
                 ffmpeg_path: str | None = None, subtitles: bool = False,
                 subtitle_langs: str = "tr,en", speed_limit_kbps: int = 0):
        self.download_dir = download_dir
        self.quality = quality
        self.ffmpeg_path = ffmpeg_path or find_ffmpeg()
        self.subtitles = subtitles
        self.subtitle_langs = subtitle_langs
        # Ayni anda birden fazla video indirilirken toplam bant genisligini
        # sinirlamak icin (bkz. Ayarlar -> Indirme hizi siniri); her video
        # kendi DownloadService'inde bu sinira ayri ayri uyar.
        self.speed_limit_kbps = max(0, int(speed_limit_kbps or 0))
        self.log = logging.getLogger("yt_ara.download")
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def reset_cancel(self) -> None:
        self._cancel.clear()

    def _progress_hook(self, progress_cb):
        def hook(d):
            if self._cancel.is_set():
                raise yt_dlp.utils.DownloadCancelled()
            status = d.get("status")
            if status == "downloading":
                info = {
                    "status": "downloading",
                    "downloaded_bytes": d.get("downloaded_bytes", 0),
                    "total_bytes": d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
                    "speed": d.get("speed") or 0,
                    "eta": d.get("eta") or 0,
                    "filename": os.path.basename(d.get("filename", "")),
                }
                progress_cb(info)
            elif status == "finished":
                progress_cb({"status": "finished",
                             "filename": os.path.basename(d.get("filename", ""))})
        return hook

    def _base_opts(self, progress_cb) -> dict:
        opts = {
            "outtmpl": os.path.join(self.download_dir, "%(title)s [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "progress_hooks": [self._progress_hook(progress_cb)],
            "retries": 3,
            "fragment_retries": 3,
            "continuedl": True,
            # Iptal edildiginde askidaki bir soket okumasinin sonsuza kadar
            # beklememesi icin (bkz. DownloadWorker.cancel): baglanti
            # donarsa en gec bu sure sonunda hata/yeniden deneme tetiklenir
            # ve iptal kontrolu bu sirada devreye girebilir.
            "socket_timeout": 10,
            # YouTube'un varsayilan istemciye 403 vermesine karsi android
            # istemcisi kullanilir (yt-dlp icin yaygin cozum).
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        if self.ffmpeg_path:
            opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_path)
        if self.speed_limit_kbps > 0:
            opts["ratelimit"] = self.speed_limit_kbps * 1024
        # DIKKAT: altyazi burada ISTENMEZ. Altyazi indirme (ozellikle
        # YouTube'un otomatik altyazilari) sik sik HTTP 429 ile basarisiz
        # oluyor ve bu, yt-dlp'de tum indirmeyi (videoyu da) hataya
        # dusuruyordu -- kullanici altyaziyi isaretlediginde video hic
        # inmiyordu. Bu yuzden video ONCE altyazisiz indirilir; altyazi
        # ayri (ve basarisizligi videoyu etkilemeyecek sekilde) denenir
        # (bkz. _download_subtitles_best_effort).
        return opts

    def _lang_list(self) -> list[str]:
        return [lang.strip() for lang in self.subtitle_langs.split(",") if lang.strip()] or ["tr", "en"]

    def download(self, url: str, progress_cb=None) -> str:
        """Tek videoyu indirir. Dosya yolunu dondurur.

        `tools/yt-dlp/yt-dlp.exe` varsa (guncel standalone binary) onu kullanir;
        yoksa gömülü yt-dlp modulunu kullanir.
        """
        self._cancel.clear()
        if progress_cb is None:
            progress_cb = lambda info: None
        external = self._external_binary()
        if external:
            return self._download_external(external, url, progress_cb)
        return self._download_module(url, progress_cb)

    def _external_binary(self) -> str | None:
        """Guncel standalone yt-dlp.exe yolu (varsa)."""
        path = ytdlp_binary()
        return path if os.path.isfile(path) else None

    def _download_module(self, url: str, progress_cb) -> str:
        """Gömülü yt-dlp modulu ile indirir."""
        fmt = self._format_for(self.quality)
        opts = self._base_opts(progress_cb)
        opts["format"] = fmt
        opts["merge_output_format"] = "mp4"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError("Video indirilemedi.")
                path = self._resolved_path(info, opts["outtmpl"])
        except yt_dlp.utils.DownloadCancelled:
            raise DownloadError("İndirme iptal edildi.", "cancelled")
        except yt_dlp.utils.DownloadError as exc:
            self.log.warning("Indirme hatasi (%s): %s", url, exc)
            raise self._map_download_error(exc)
        except Exception as exc:
            self.log.exception("Beklenmeyen indirme hatasi (%s)", url)
            raise DownloadError(
                "İndirme sırasında beklenmeyen bir hata oluştu.",
                str(exc),
            )
        if self.subtitles and not self._cancel.is_set():
            self._download_subtitles_module_best_effort(url, opts["outtmpl"])
        return path

    def _download_subtitles_module_best_effort(self, url: str, outtmpl: str) -> None:
        """Altyaziyi ayrica indirmeyi dener; basarisiz olursa yalnizca loglar.

        Video indirmesi bundan tamamen bagimsizdir (bkz. _base_opts notu):
        altyazi olsun ya da olmasin, sonucu ne olursa olsun video zaten
        indirilmis olur.
        """
        sub_opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": self._lang_list(),
            "socket_timeout": 10,
            "retries": 1,
            "fragment_retries": 1,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        if self.ffmpeg_path:
            sub_opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_path)
            sub_opts["postprocessors"] = [
                {"key": "FFmpegSubtitlesConvertor", "format": "srt"}]
        try:
            with yt_dlp.YoutubeDL(sub_opts) as ydl:
                ydl.extract_info(url, download=True)
        except Exception as exc:
            self.log.warning("Altyazi indirilemedi (video yine de indi) (%s): %s", url, exc)

    def _download_external(self, binary: str, url: str, progress_cb) -> str:
        """Standalone yt-dlp.exe ile (subprocess) indirir.

        Boylece portable EXE'de bile guncel yt-dlp kullanilabilir.
        Not: yt-dlp, stdout pipe'a yazarken ilerlemeyi blok tamponlar; bu
        yuzden gercek zamanli yuzde alinamaz. UI, ilerleme olayi gelmediginde
        belirsiz (spinner) ilerleme gosterir.
        """
        fmt = self._format_for(self.quality)
        outtmpl = os.path.join(self.download_dir, "%(title)s [%(id)s].%(ext)s")
        cmd = [
            binary, "--newline", "--no-warnings", "--no-playlist",
            "--extractor-args", "youtube:player_client=android",
            "--progress-template",
            "PROG:%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
            "%(progress.speed)s|%(progress.eta)s",
            "-f", fmt, "--merge-output-format", "mp4",
            "-o", outtmpl,
        ]
        if self.ffmpeg_path:
            cmd += ["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)]
        if self.speed_limit_kbps > 0:
            cmd += ["--limit-rate", f"{self.speed_limit_kbps * 1024}"]
        # DIKKAT: altyazi burada ISTENMEZ; ayri bir cagriyla (basarisizligi
        # videoyu etkilemeyecek sekilde) denenir (bkz. _download_subtitles_
        # external_best_effort ve _download_module'daki ayni notu).
        cmd.append(url)

        self.log.info("Harici yt-dlp ile indiriliyor: %s", binary)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as exc:
            self.log.warning("Harici yt-dlp baslatilamadi: %s", exc)
            raise DownloadError(
                "yt-dlp başlatılamadı. Lütfen tekrar deneyin.", str(exc))

        # Iptal icin sureci izle
        def _watch_cancel():
            while proc.poll() is None:
                if self._cancel.is_set():
                    kill_process_tree(proc)
                    return
                import time
                time.sleep(0.2)
        watcher = threading.Thread(target=_watch_cancel, daemon=True)
        watcher.start()

        try:
            raw_out, _ = proc.communicate()
        finally:
            watcher.join(timeout=1)

        if self._cancel.is_set():
            raise DownloadError("İndirme iptal edildi.", "cancelled")

        output = raw_out.decode("utf-8", errors="replace")
        final_path = ""
        error_lines: list[str] = []
        for line in output.splitlines():
            if line.startswith("PROG:"):
                self._parse_external_progress(line, progress_cb)
            elif line.startswith("ERROR:"):
                error_lines.append(line)
            elif "[Merger] Merging formats into" in line:
                # Birlestirilen son dosya yolu
                final_path = self._extract_quoted_path(line)
            elif line.startswith("[download] Destination:"):
                final_path = line.split(":", 1)[1].strip()

        if proc.returncode != 0:
            detail = "\n".join(error_lines)[-500:]
            self.log.warning("Harici yt-dlp hatasi (%s): %s", url, detail)
            raise self._map_download_error(
                DownloadError("Video indirilemedi.", detail))
        if not final_path or not os.path.isfile(final_path):
            final_path = self._find_latest_file()
        if self.subtitles and not self._cancel.is_set():
            self._download_subtitles_external_best_effort(binary, url, outtmpl)
        return final_path

    def _download_subtitles_external_best_effort(self, binary: str, url: str, outtmpl: str) -> None:
        """Harici yt-dlp.exe ile altyaziyi ayrica dener; hata yalnizca loglanir."""
        cmd = [
            binary, "--no-warnings", "--no-playlist", "--skip-download",
            "--extractor-args", "youtube:player_client=android",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", ",".join(self._lang_list()),
            "-o", outtmpl,
        ]
        if self.ffmpeg_path:
            cmd += ["--ffmpeg-location", os.path.dirname(self.ffmpeg_path), "--convert-subs", "srt"]
        cmd.append(url)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            _out, _ = proc.communicate(timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.log.warning("Altyazi indirilemedi (video yine de indi) (%s): %s", url, exc)

    @staticmethod
    def _extract_quoted_path(line: str) -> str:
        """'... "path"' icinden yolu cikarir."""
        if '"' in line:
            return line.split('"', 1)[1].rsplit('"', 1)[0]
        return line

    def _parse_external_progress(self, line: str, progress_cb) -> None:
        """'PROG:bytes|total|speed|eta' satirini ayristirir."""
        try:
            payload = line.split(":", 1)[1]
            parts = payload.split("|")
            downloaded = int(parts[0]) if parts[0].strip() else 0
            total = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
            speed = float(parts[2]) if len(parts) > 2 and parts[2].strip() else 0
            eta = int(float(parts[3])) if len(parts) > 3 and parts[3].strip() else 0
        except (ValueError, IndexError):
            return
        progress_cb({
            "status": "downloading",
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "speed": speed,
            "eta": eta,
            "filename": "",
        })

    def _find_latest_file(self) -> str:
        """Indirme klasorunde en son degisen dosyayi dondurur."""
        try:
            files = [os.path.join(self.download_dir, f)
                     for f in os.listdir(self.download_dir)
                     if os.path.isfile(os.path.join(self.download_dir, f))]
        except OSError:
            return ""
        if not files:
            return ""
        return max(files, key=os.path.getmtime)

    def _format_for(self, quality: str) -> str:
        for label, fmt in QUALITY_OPTIONS:
            if label == quality:
                return fmt
        return QUALITY_OPTIONS[0][1]

    def _resolved_path(self, info: dict, outtmpl: str) -> str:
        """Indirilen dosyanin gercek yolunu dondurur."""
        # yt-dlp indirme sonrasi gercek dosya yolunu verir
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            return requested[0]["filepath"]
        # Gercek yol yoksa tahmin et
        title = sanitize_filename(str(info.get("title") or "video"))
        video_id = str(info.get("id") or "")
        ext = str(info.get("ext") or "mp4")
        return os.path.join(self.download_dir, f"{title} [{video_id}].{ext}")

    def _map_download_error(self, exc) -> DownloadError:
        msg = str(exc)
        low = msg.lower()
        if "private video" in low or "video is private" in low:
            return DownloadError("Bu video artık erişilebilir değil.", msg)
        if "unavailable" in low or "not available" in low or "removed" in low:
            return DownloadError("Bu video artık erişilebilir değil.", msg)
        if "age" in low or "sign in" in low or "login" in low or "restricted" in low:
            return DownloadError(
                "Bu video erişim kısıtlaması nedeniyle indirilemedi.", msg)
        if "ffmpeg" in low:
            return DownloadError(
                "FFmpeg bulunamadığı için bu işlem gerçekleştirilemedi.", msg)
        if "disk" in low or "no space" in low:
            return DownloadError(
                "Disk alanı yetersiz. Lütfen boş alanı kontrol edin.", msg)
        return DownloadError(
            "Video indirilemedi. Lütfen tekrar deneyin.", msg)
