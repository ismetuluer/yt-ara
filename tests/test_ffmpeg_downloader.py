"""ffmpeg_downloader testleri. Ag erisimi gerektirmez (urlretrieve mock'lanir)."""
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


class TestFFmpegDownloader(unittest.TestCase):
    def test_downloads_extracts_and_copies_binaries(self):
        d = FFmpegDownloader()
        tmp_source = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_source, "ffmpeg.zip")
        _make_fake_ffmpeg_zip(zip_path)

        def fake_urlretrieve(url, filename, reporthook=None):
            with open(zip_path, "rb") as src, open(filename, "wb") as dst:
                dst.write(src.read())
            if reporthook:
                reporthook(1, 100, 100)

        fake_ffmpeg_dir = tempfile.mkdtemp()
        events = []
        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlretrieve",
                        side_effect=fake_urlretrieve), \
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

        def fake_urlretrieve(url, filename, reporthook=None):
            with open(zip_path, "rb") as src, open(filename, "wb") as dst:
                dst.write(src.read())

        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlretrieve",
                        side_effect=fake_urlretrieve), \
             mock.patch("app.services.ffmpeg_downloader.ffmpeg_dir",
                        return_value=tempfile.mkdtemp()):
            with self.assertRaises(FFmpegDownloadError):
                d.download()

    def test_download_failure_raises_clean_error(self):
        d = FFmpegDownloader()
        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlretrieve",
                        side_effect=OSError("connection reset")):
            with self.assertRaises(FFmpegDownloadError):
                d.download()

    def test_bad_zip_raises_clean_error(self):
        d = FFmpegDownloader()

        def fake_urlretrieve(url, filename, reporthook=None):
            with open(filename, "wb") as f:
                f.write(b"not a zip")

        with mock.patch("app.services.ffmpeg_downloader.urllib.request.urlretrieve",
                        side_effect=fake_urlretrieve):
            with self.assertRaises(FFmpegDownloadError):
                d.download()


if __name__ == "__main__":
    unittest.main()
