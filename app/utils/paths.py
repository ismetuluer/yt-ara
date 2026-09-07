"""Portable uygulama klasor yollari.

EXE ile calisirken uygulama klasoru EXE'nin bulundugu klasordur;
gelistirme ortaminda proje kok klasorudur.
"""
import os
import sys


def app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def config_dir() -> str:
    """Ayarlarin saklandigi klasor.

    Uygulama klasorunun disinda (AppData\\Local) tutulur; boylece portable
    klasor guncellenirken/tasinirken/yeniden acilirken ayarlar korunur.
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "YouTubeSearch")


def legacy_config_dir() -> str:
    """Eski (uygulama klasorundeki) ayarlar konumu; tek seferlik gecis icin."""
    return os.path.join(app_root(), "config")


def data_dir() -> str:
    return os.path.join(app_root(), "data")


def logs_dir() -> str:
    return os.path.join(app_root(), "logs")


def downloads_dir() -> str:
    return os.path.join(app_root(), "downloads")


def default_download_dir() -> str:
    """Kullanicinin Masaustu klasoru varsa onu, yoksa portable downloads/
    klasorunu dondurur (indirme klasoru ayari bos oldugunda kullanilir)."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(desktop):
        return desktop
    return downloads_dir()


def tools_dir() -> str:
    return os.path.join(app_root(), "tools")


def ffmpeg_dir() -> str:
    return os.path.join(tools_dir(), "ffmpeg")


def ytdlp_dir() -> str:
    return os.path.join(tools_dir(), "yt-dlp")


def ytdlp_binary() -> str:
    """Guncel standalone yt-dlp.exe yolu (varsa)."""
    return os.path.join(ytdlp_dir(), "yt-dlp.exe")


def icon_path() -> str:
    return os.path.join(app_root(), "assets", "icon.ico")


def ensure_dirs() -> None:
    for path in (config_dir(), data_dir(), logs_dir(), downloads_dir()):
        os.makedirs(path, exist_ok=True)
