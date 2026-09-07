"""Uygulamanin kendisini GitHub Releases uzerinden guncelleme servisi.

yt-dlp guncelleyicisiyle (bkz. ytdlp_updater.py) ayni yaklasimi kullanir:
GitHub'daki en son release'in etiketini (tag_name) kurulu surumle
karsilastirir. Ancak uygulama guncellemesi tek bir dosya degil, butun
`app/` kaynak agacini degistirdigi icin farkli calisir: calisan bir
Python sureci kendi calisan kaynak dosyalarinin uzerine guvenilir sekilde
yazamaz. Bu yuzden:

1. Yayindaki hafif "update.zip" (yalnizca app/, main.py, assets/,
   requirements.txt -- Python calisma zamanini veya ffmpeg'i icermez)
   indirilip gecici bir klasore acilir.
2. Degisiklikleri asil uygulama klasorune kopyalayip uygulamayi yeniden
   baslatacak kucuk bir toplu (.bat) betik yazilir.
3. Bu betik, ana uygulama surecinden BAGIMSIZ (detached) olarak baslatilir;
   boylece ana uygulama kapandiktan sonra dosyalari degistirebilir.

Kullanicinin `data/`, `logs/`, `downloads/` klasorleri update.zip'e dahil
edilmedigi icin guncelleme sirasinda dokunulmaz.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from app.utils.paths import app_root

# Yayinlarken burasi guncel tutulmali (bkz. README "Yeni surum yayinlama").
GITHUB_OWNER = "ismetuluer"
GITHUB_REPO = "yt-ara"
_LATEST_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
# Her yayinda ayni sabit adla eklenen, hafif (yalnizca kaynak kodu) paket.
_UPDATE_ASSET_NAME = "update.zip"


class AppUpdateError(Exception):
    """Kullaniciya gosterilecek Turkce mesaj + teknik ayrinti tasir."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


def version_tuple(version: str) -> tuple:
    """'1.2.0' / 'v1.2.0' -> (1, 2, 0) karsilastirma icin."""
    try:
        return tuple(int(x) for x in version.strip().lstrip("vV").split("."))
    except ValueError:
        return (0,)


class AppUpdater:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.log = logging.getLogger("yt_ara.app_updater")

    # ------------------------------------------------------------ surumler
    @staticmethod
    def current_version() -> str:
        from app.version import APP_VERSION
        return APP_VERSION

    def latest_release(self) -> dict:
        """GitHub'daki en son release bilgisini dondurur.

        {"version": "1.2.0", "download_url": "...", "notes_url": "..."}
        Ag hatasinda veya beklenmeyen yanitta AppUpdateError firlatir.
        """
        req = urllib.request.Request(_LATEST_API, headers={"User-Agent": "yt-ara"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except Exception as exc:
            self.log.warning("En son surum alinamadi: %s", exc)
            raise AppUpdateError(
                "En son sürüm bilgisi alınamadı. İnternet bağlantınızı kontrol edin.",
                str(exc),
            ) from exc
        version = str(data.get("tag_name", "")).lstrip("vV")
        notes_url = str(data.get("html_url", ""))
        download_url = ""
        for asset in data.get("assets") or []:
            if str(asset.get("name", "")) == _UPDATE_ASSET_NAME:
                download_url = str(asset.get("browser_download_url", ""))
                break
        if not version or not download_url:
            self.log.warning("Beklenmeyen release yaniti: %s", str(data)[:300])
            raise AppUpdateError(
                "En son sürüm bilgisi eksik veya beklenmeyen biçimde geldi.",
                str(data)[:300],
            )
        return {"version": version, "download_url": download_url, "notes_url": notes_url}

    def compare(self) -> tuple:
        """(kurulu_surum, en_son_surum, guncelleme_var_mi, release_bilgisi) dondurur."""
        current = self.current_version()
        release = self.latest_release()
        outdated = version_tuple(current) < version_tuple(release["version"])
        return current, release["version"], outdated, release

    # ------------------------------------------------------------ guncelleme
    def download_and_stage(self, download_url: str, progress_cb=None) -> str:
        """update.zip'i indirir, gecici klasore acar ve degisim/yeniden
        baslatma betiginin yolunu dondurur. Betik henuz CALISTIRILMAZ --
        cagiran taraf (UI), uygulamayi kapatmadan hemen once baslatmalidir.
        """
        if progress_cb is None:
            progress_cb = lambda pct, msg: None
        tmp_dir = tempfile.mkdtemp(prefix="yt_ara_update_")
        zip_path = os.path.join(tmp_dir, _UPDATE_ASSET_NAME)
        progress_cb(0, "İndiriliyor...")
        try:
            urllib.request.urlretrieve(
                download_url, zip_path, reporthook=self._make_hook(progress_cb))
        except Exception as exc:
            self.log.warning("Guncelleme indirilemedi: %s", exc)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise AppUpdateError(
                "Güncelleme indirilemedi. İnternet bağlantınızı kontrol edin.",
                str(exc),
            ) from exc

        extract_dir = os.path.join(tmp_dir, "extracted")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise AppUpdateError(
                "İndirilen güncelleme dosyası bozuk. Lütfen tekrar deneyin.",
                str(exc),
            ) from exc

        progress_cb(100, "Hazırlanıyor...")
        script_path = self._write_apply_script(extract_dir, tmp_dir)
        return script_path

    def _write_apply_script(self, extract_dir: str, tmp_dir: str) -> str:
        """Uygulama kapandiktan sonra dosyalari degistirip yeniden
        baslatacak .bat betigini yazar."""
        target = app_root()
        launcher = os.path.join(target, "YouTubeSearch.bat")
        script_path = os.path.join(tmp_dir, "apply_update.bat")
        # /MIR kullanilmaz (data/logs/downloads gibi kullanici klasorlerini
        # SILME riski olur); yalnizca guncellenen dosyalar/klasorler
        # (extract_dir icindekiler) hedefe kopyalanir.
        content = (
            "@echo off\r\n"
            "setlocal\r\n"
            # "timeout" konsol/stdin gerektirir ve bagimsiz (DETACHED_PROCESS,
            # konsolsuz) baslatilan bu betikte sessizce basarisiz olabilir;
            # ping tabanli gecikme her ortamda calisir (klasik, guvenilir
            # bir yontemdir) -- ana uygulamanin surecinin tamamen kapanip
            # dosya kilitlerini birakmasi icin birkac saniye beklenir.
            "ping -n 3 127.0.0.1 >nul\r\n"
            f'robocopy "{extract_dir}" "{target}" /E /IS /IT /NFL /NDL /NJH /NJS\r\n'
            f'if exist "{launcher}" start "" "{launcher}"\r\n'
            f'rmdir /s /q "{tmp_dir}"\r\n'
            'del "%~f0"\r\n'
        )
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(content)
        return script_path

    def launch_apply_script(self, script_path: str) -> None:
        """Degisim betigini ana uygulamadan bagimsiz (detached) baslatir.

        Cagiran taraf bundan hemen sonra uygulamayi kapatmalidir; betik
        birkac saniye bekleyip dosyalari degistirir ve uygulamayi yeniden
        acar.
        """
        creationflags = 0
        if sys.platform == "win32":
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
        subprocess.Popen(
            [script_path], creationflags=creationflags,
            close_fds=True, cwd=os.path.dirname(script_path))

    @staticmethod
    def _make_hook(progress_cb):
        def hook(count, block_size, total_size):
            if total_size > 0:
                pct = min(100, int(count * block_size * 100 / total_size))
            else:
                pct = 0
            progress_cb(pct, f"İndiriliyor... %{pct}")
        return hook
