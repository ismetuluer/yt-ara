"""yt-dlp surum kontrolu ve guncelleme servisi.

YouTube guncellemeleri yt-dlp'yi kirabilir. Bu servis:

* Kurulu (gömülü) yt-dlp surumunu ve GitHub'daki en son surumu karsilastirir.
* Guncel standalone `yt-dlp.exe`'yi `tools/yt-dlp/` klasorune indirir.

Indirme islemleri, `tools/yt-dlp/yt-dlp.exe` varsa onu (guncel binary) kullanir;
yoksa gömülü modulu kullanir. Boylece portable EXE'de bile yt-dlp, EXE'yi
yeniden derlemeden guncellenebilir.
"""
import json
import logging
import os
import socket
import subprocess
import urllib.request

import yt_dlp

from app.utils.paths import ytdlp_binary, ytdlp_dir

# GitHub API: en son yayin
_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
# Standalone Windows binary (sabit URL, en son surume yonlendirir)
_DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


class YtDlpUpdateError(Exception):
    """Kullaniciya gosterilecek Turkce mesaj + teknik ayrinti."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


def _version_tuple(version: str) -> tuple:
    """'2026.08.19' -> (2026, 8, 19) karsilastirma icin."""
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)


class YtDlpUpdater:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.log = logging.getLogger("yt_ara.ytdlp_updater")
        self._binary_ver: str | None = None

    # ------------------------------------------------------------ surumler
    def current_version(self) -> str:
        """Uygulamanin kullandigi en guncel surum.

        Gömülü modul ile indirilmis standalone exe'nin surumlerinden yenisi;
        cunku indirmeler exe varsa onu kullanir.
        """
        versions = [yt_dlp.version.__version__]
        binary_ver = self._binary_version()
        if binary_ver:
            versions.append(binary_ver)
        return max(versions, key=_version_tuple)

    def _binary_version(self) -> str:
        """tools/yt-dlp/yt-dlp.exe --version ciktisi (varsa). Oturumda bir kez sorulur."""
        if self._binary_ver is not None:
            return self._binary_ver
        self._binary_ver = ""
        binary = ytdlp_binary()
        if os.path.isfile(binary):
            try:
                out = subprocess.run(
                    [binary, "--version"], capture_output=True, text=True,
                    timeout=15,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self._binary_ver = out.stdout.strip()
            except Exception as exc:
                self.log.warning("Harici yt-dlp surumu alinamadi: %s", exc)
        return self._binary_ver

    def compare(self) -> tuple:
        """(kurulu_surum, en_son_surum, guncelleme_gerekli) dondurur.

        Ag hatasinda YtDlpUpdateError firlatir.
        """
        current = self.current_version()
        latest = self.latest_version()
        return current, latest, _version_tuple(current) < _version_tuple(latest)

    def latest_version(self) -> str:
        """GitHub'daki en son yt-dlp surumu."""
        req = urllib.request.Request(_LATEST_API, headers={"User-Agent": "yt-ara"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except Exception as exc:
            self.log.warning("En son surum alinamadi: %s", exc)
            raise YtDlpUpdateError(
                "En son yt-dlp sürümü alınamadı. İnternet bağlantınızı kontrol edin.",
                str(exc),
            )
        tag = data.get("tag_name", "")
        return tag.lstrip("v")

    def is_outdated(self) -> bool:
        """Kurulu surum en son surumden eski mi?"""
        try:
            current = _version_tuple(self.current_version())
            latest = _version_tuple(self.latest_version())
        except YtDlpUpdateError:
            return False
        return current < latest

    # ------------------------------------------------------------ guncelleme
    def update(self, progress_cb=None) -> str:
        """En son standalone yt-dlp.exe'yi indirir. Yeni dosya yolunu dondurur."""
        if progress_cb is None:
            progress_cb = lambda pct, msg: None
        os.makedirs(ytdlp_dir(), exist_ok=True)
        dest = ytdlp_binary()
        tmp = dest + ".tmp"
        progress_cb(0, "İndiriliyor...")
        # urlretrieve zaman asimi parametresi almaz; indirme askida kalmasin
        # diye gecici olarak global soket zaman asimini ayarlariz.
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout)
        try:
            urllib.request.urlretrieve(
                _DOWNLOAD_URL, tmp, reporthook=self._make_hook(progress_cb))
        except Exception as exc:
            self.log.warning("yt-dlp indirilemedi: %s", exc)
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise YtDlpUpdateError(
                "yt-dlp güncellemesi indirilemedi. İnternet bağlantınızı kontrol edin.",
                str(exc),
            )
        finally:
            socket.setdefaulttimeout(previous_timeout)
        # Gecici dosyayi asil konuma tasi
        try:
            if os.path.exists(dest):
                os.remove(dest)
            os.replace(tmp, dest)
        except OSError as exc:
            self.log.warning("yt-dlp dosyasi tasinamadi: %s", exc)
            raise YtDlpUpdateError(
                "yt-dlp indirildi ancak kaydedilemedi. Klasör izinlerini kontrol edin.",
                str(exc),
            )
        self._binary_ver = None  # yeni exe: surum onbellegi gecersiz
        progress_cb(100, "Tamamlandı")
        return dest

    @staticmethod
    def _make_hook(progress_cb):
        def hook(count, block_size, total_size):
            if total_size > 0:
                pct = min(100, int(count * block_size * 100 / total_size))
            else:
                pct = 0
            progress_cb(pct, f"İndiriliyor... %{pct}")
        return hook
