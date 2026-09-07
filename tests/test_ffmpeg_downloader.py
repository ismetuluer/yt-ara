"""ffmpeg_downloader testleri. Ag erisimi gerektirmez (urlopen mock'lanir)."""
import io
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ffmpeg_downloader import FFmpegDownloadError, FFmpegDownloader


def _make_fake_ffmpeg_zip(zip_path: str, with_ffprobe: bool = True):
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe", "fake-ffmpeg-binary")
        if with_ffprobe:
            zf.writestr("ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe", "fake-ffprobe-binary")
        zf.writestr("ffmpeg-master-latest-win64-gpl/README.txt", "hello")


class _FakeResponse(io.BytesIO):
    """urllib.request.urlopen(...) context-manager sonucunu taklit eder."""

    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestFFmpegDownloader(unittest.TestCase):
    def test_downloads_extracts_and_copies_binaries(self):
        d = FFmpegDownloader()
        tmp_source = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_source, "ffmpeg.zip")
        _make_fake_ffmpeg_zip(zip_path)
        with open(zip_path, "rb") as f:
            zip_bytes = f.read()

        fake_ffmpeg_dir = tempfile.mkdtemp()
        events = []
        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlopen",
                        return_value=_FakeResponse(zip_bytes)), \
             mock.patch("app.services.ffmpeg_downloader.ffmpeg_dir",
                        return_value=fake_ffmpeg_dir):
            dest = d.download(progress_cb=lambda p, m: events.append((p, m)))

        self.assertEqual(dest, os.path.join(fake_ffmpeg_dir, "ffmpeg.exe"))
        self.assertTrue(os.path.isfile(dest))
        self.assertTrue(os.path.isfile(os.path.join(fake_ffmpeg_dir, "ffprobe.exe")))
        self.assertTrue(any(p == 100 for p, _ in events))

    def test_missing_ffmpeg_exe_in_zip_raises(self):
        d = FFmpegDownloader()
        tmp_source = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_source, "ffmpeg.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("some/other/file.txt", "nothing useful")
        with open(zip_path, "rb") as f:
            zip_bytes = f.read()

        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlopen",
                        return_value=_FakeResponse(zip_bytes)), \
             mock.patch("app.services.ffmpeg_downloader.ffmpeg_dir",
                        return_value=tempfile.mkdtemp()):
            with self.assertRaises(FFmpegDownloadError):
                d.download()

    def test_download_failure_raises_clean_error(self):
        d = FFmpegDownloader()
        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlopen",
                        side_effect=OSError("connection reset")):
            with self.assertRaises(FFmpegDownloadError):
                d.download()

    def test_download_403_gives_specific_message_not_generic_internet_check(self):
        d = FFmpegDownloader()
        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlopen",
                        side_effect=OSError("HTTP Error 403: Forbidden")):
            with self.assertRaises(FFmpegDownloadError) as ctx:
                d.download()
        self.assertIn("403", ctx.exception.user_message)

    def test_bad_zip_raises_clean_error(self):
        d = FFmpegDownloader()
        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlopen",
                        return_value=_FakeResponse(b"not a zip")):
            with self.assertRaises(FFmpegDownloadError):
                d.download()


if __name__ == "__main__":
    unittest.main()
