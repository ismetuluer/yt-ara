"""FFmpeg yonetimi ve videodan kare cikarma.

Portable yapi korunur: FFmpeg oncelikle uygulama klasorundeki
tools/ffmpeg/ icinde aranir; bulunamazsa sistem PATH'ine bakilir.
Sistem PATH'ine kurulum zorlanmaz.
"""
import logging
import os
import shutil
import subprocess

from app.utils.paths import ffmpeg_dir


class FFmpegError(Exception):
    """Kullaniciya gosterilecek Turkce mesaj + teknik ayrinti."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


def parse_timecode(text: str) -> int:
    """Zaman kodunu saniyeye cevirir. Gecersizse ValueError firlatir.

    Desteklenen: 'SS', 'MM:SS', 'HH:MM:SS'
    """
    text = text.strip()
    parts = text.split(":")
    if not parts or len(parts) > 3:
        raise ValueError(f"Geçersiz zaman kodu: {text}")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"Geçersiz zaman kodu: {text}")
    if any(n < 0 for n in nums):
        raise ValueError(f"Geçersiz zaman kodu: {text}")
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def format_timecode(seconds: int) -> str:
    """Saniyeyi HH-MM-SS (dosya adi icin) bicimine cevirir."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}-{m:02d}-{s:02d}"


def find_ffmpeg() -> str | None:
    """FFmpeg yolunu bulur. Oncelik portable klasor, sonra PATH."""
    candidates = [
        os.path.join(ffmpeg_dir(), "ffmpeg.exe"),
        os.path.join(ffmpeg_dir(), "ffmpeg"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return shutil.which("ffmpeg")


def find_ffprobe() -> str | None:
    """ffprobe yolunu bulur. Oncelik portable klasor, sonra PATH."""
    candidates = [
        os.path.join(ffmpeg_dir(), "ffprobe.exe"),
        os.path.join(ffmpeg_dir(), "ffprobe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return shutil.which("ffprobe")


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def _run(cmd: list[str]) -> None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError:
        raise FFmpegError("FFmpeg bulunamadığı için bu işlem gerçekleştirilemedi.")
    except subprocess.TimeoutExpired:
        raise FFmpegError("İşlem zaman aşımına uğradı. Lütfen tekrar deneyin.")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-500:]
        raise FFmpegError(
            "Görüntü çıkarma sırasında bir hata oluştu. Lütfen tekrar deneyin.",
            detail,
        )


def extract_frames(
    video_path: str,
    output_dir: str,
    base_name: str,
    times_seconds: list[int],
    image_format: str = "jpg",
    quality: int = 2,
) -> list[str]:
    """Belirtilen zaman noktalarindan kare cikarir.

    image_format: 'jpg' veya 'png'. jpg icin quality 2-31 (kucuk daha iyi).
    Cikarilan dosya yollarini dondurur.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise FFmpegError("FFmpeg bulunamadığı için bu işlem gerçekleştirilemedi.")
    if not os.path.isfile(video_path):
        raise FFmpegError("Video dosyası bulunamadı.")
    os.makedirs(output_dir, exist_ok=True)

    ext = "png" if image_format == "png" else "jpg"
    created: list[str] = []
    for seconds in times_seconds:
        out_name = f"{base_name}_{format_timecode(seconds)}.{ext}"
        out_path = os.path.join(output_dir, out_name)
        cmd = [ffmpeg, "-y", "-ss", str(seconds), "-i", video_path,
               "-frames:v", "1"]
        if image_format == "png":
            cmd += ["-compression_level", "6"]
        else:
            cmd += ["-q:v", str(quality)]
        cmd += [out_path]
        _run(cmd)
        created.append(out_path)
    return created


def extract_frames_interval(
    video_path: str,
    output_dir: str,
    base_name: str,
    interval_seconds: int,
    image_format: str = "jpg",
    quality: int = 2,
) -> list[str]:
    """Videodan belirli araliklarla kare cikarir (0'dan baslayarak)."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise FFmpegError("FFmpeg bulunamadığı için bu işlem gerçekleştirilemedi.")
    if not os.path.isfile(video_path):
        raise FFmpegError("Video dosyası bulunamadı.")
    os.makedirs(output_dir, exist_ok=True)

    duration = _video_duration(video_path)
    if duration is None or duration <= 0:
        raise FFmpegError("Video süresi belirlenemedi.")

    ext = "png" if image_format == "png" else "jpg"
    created: list[str] = []
    seconds = 0
    while seconds <= duration:
        out_name = f"{base_name}_{format_timecode(seconds)}.{ext}"
        out_path = os.path.join(output_dir, out_name)
        cmd = [ffmpeg, "-y", "-ss", str(seconds), "-i", video_path,
               "-frames:v", "1"]
        if image_format == "png":
            cmd += ["-compression_level", "6"]
        else:
            cmd += ["-q:v", str(quality)]
        cmd += [out_path]
        _run(cmd)
        created.append(out_path)
        seconds += interval_seconds
    return created


def _video_duration(video_path: str) -> float | None:
    """ffprobe ile video suresini saniye olarak dondurur."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        pass
    return None
