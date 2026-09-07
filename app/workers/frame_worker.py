"""Arka planda kare cikarma is parcacigi.

Belirtilen zaman noktalarindan veya araliklarla videodan kare cikarir.
Ilerleme ve tamamlanma sinyalleri yayar.
"""
import logging

from PySide6.QtCore import QThread, Signal

from app.services.ffmpeg_service import (
    FFmpegError, extract_frames, extract_frames_interval,
)


class FrameWorker(QThread):
    # (tamamlanan, toplam, dosya_yolu)
    progress = Signal(int, int, str)
    # (cikarilan dosya yollari)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, video_path: str, output_dir: str, base_name: str,
                 times_seconds: list[int] | None = None,
                 interval_seconds: int | None = None,
                 image_format: str = "jpg", parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.output_dir = output_dir
        self.base_name = base_name
        self.times_seconds = times_seconds
        self.interval_seconds = interval_seconds
        self.image_format = image_format
        self.log = logging.getLogger("yt_ara.frame_worker")
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            if self.interval_seconds:
                created = extract_frames_interval(
                    self.video_path, self.output_dir, self.base_name,
                    self.interval_seconds, self.image_format)
            else:
                times = self.times_seconds or []
                created = []
                total = len(times)
                for i, seconds in enumerate(times, 1):
                    if self._cancel:
                        break
                    paths = extract_frames(
                        self.video_path, self.output_dir, self.base_name,
                        [seconds], self.image_format)
                    created.extend(paths)
                    self.progress.emit(i, total, paths[0] if paths else "")
            self.done.emit(created)
        except FFmpegError as exc:
            self.failed.emit(exc.user_message)
        except Exception as exc:
            self.log.exception("Kare cikarma hatasi")
            self.failed.emit("Görüntü çıkarma sırasında beklenmeyen bir hata oluştu.")
