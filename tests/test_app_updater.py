"""app_updater / AppUpdateWorker testleri. Ag erisimi gerektirmez."""
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.app_updater import AppUpdateError, AppUpdater, version_tuple


class FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.payload


class TestVersionTuple(unittest.TestCase):
    def test_parses_dotted_version(self):
        self.assertEqual(version_tuple("1.2.0"), (1, 2, 0))

    def test_strips_v_prefix(self):
        self.assertEqual(version_tuple("v1.2.0"), (1, 2, 0))

    def test_invalid_falls_back(self):
        self.assertEqual(version_tuple("not-a-version"), (0,))

    def test_comparison(self):
        self.assertLess(version_tuple("1.0.0"), version_tuple("1.1.0"))
        self.assertLess(version_tuple("1.9.0"), version_tuple("1.10.0"))


class TestLatestRelease(unittest.TestCase):
    def test_parses_tag_and_update_asset(self):
        u = AppUpdater()
        payload = {
            "tag_name": "v1.2.0",
            "html_url": "https://github.com/ismetuluer/yt-ara/releases/tag/v1.2.0",
            "assets": [
                {"name": "portable.zip", "browser_download_url": "https://x/portable.zip"},
                {"name": "update.zip", "browser_download_url": "https://x/update.zip"},
            ],
        }
        with mock.patch("app.services.app_updater.urllib.request.urlopen",
                        return_value=FakeResp(b"{}")), \
             mock.patch("app.services.app_updater.json.load", return_value=payload):
            release = u.latest_release()
        self.assertEqual(release["version"], "1.2.0")
        self.assertEqual(release["download_url"], "https://x/update.zip")

    def test_missing_update_asset_raises(self):
        u = AppUpdater()
        payload = {"tag_name": "v1.2.0", "assets": [
            {"name": "portable.zip", "browser_download_url": "https://x/portable.zip"}]}
        with mock.patch("app.services.app_updater.urllib.request.urlopen",
                        return_value=FakeResp(b"{}")), \
             mock.patch("app.services.app_updater.json.load", return_value=payload):
            with self.assertRaises(AppUpdateError):
                u.latest_release()

    def test_network_failure_raises(self):
        u = AppUpdater()
        with mock.patch("app.services.app_updater.urllib.request.urlopen",
                        side_effect=OSError("boom")):
            with self.assertRaises(AppUpdateError):
                u.latest_release()


class TestCompare(unittest.TestCase):
    def test_outdated_true_when_remote_newer(self):
        u = AppUpdater()
        with mock.patch.object(u, "current_version", return_value="1.0.0"), \
             mock.patch.object(u, "latest_release",
                               return_value={"version": "1.1.0", "download_url": "u",
                                            "notes_url": "n"}):
            current, latest, outdated, release = u.compare()
        self.assertEqual((current, latest, outdated), ("1.0.0", "1.1.0", True))

    def test_outdated_false_when_up_to_date(self):
        u = AppUpdater()
        with mock.patch.object(u, "current_version", return_value="1.1.0"), \
             mock.patch.object(u, "latest_release",
                               return_value={"version": "1.1.0", "download_url": "u",
                                            "notes_url": "n"}):
            _, _, outdated, _ = u.compare()
        self.assertFalse(outdated)


class TestDownloadAndStage(unittest.TestCase):
    def test_downloads_extracts_and_writes_apply_script(self):
        u = AppUpdater()
        tmp_source = tempfile.mkdtemp()
        # gercekci bir update.zip olustur (app/, main.py, assets/)
        zip_path = os.path.join(tmp_source, "update.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("main.py", "print('hi')")
            zf.writestr("app/version.py", "APP_VERSION = '9.9.9'")

        def fake_urlretrieve(url, filename, reporthook=None):
            with open(zip_path, "rb") as src, open(filename, "wb") as dst:
                dst.write(src.read())
            if reporthook:
                reporthook(1, os.path.getsize(zip_path), os.path.getsize(zip_path))

        fake_root = tempfile.mkdtemp()
        progress_events = []
        with mock.patch("app.services.app_updater.urllib.request.urlretrieve",
                        side_effect=fake_urlretrieve), \
             mock.patch("app.services.app_updater.app_root", return_value=fake_root):
            script_path = u.download_and_stage(
                "https://x/update.zip", progress_cb=lambda p, m: progress_events.append((p, m)))

        self.assertTrue(os.path.isfile(script_path))
        content = open(script_path, encoding="utf-8").read()
        self.assertIn("robocopy", content.lower())
        self.assertIn(fake_root, content)
        self.assertIn("pythonw.exe", content)
        self.assertIn("main.py", content)
        self.assertTrue(any(p == 100 for p, _ in progress_events))

    def test_bad_zip_raises_clean_error(self):
        u = AppUpdater()

        def fake_urlretrieve(url, filename, reporthook=None):
            with open(filename, "wb") as f:
                f.write(b"not a zip file")

        with mock.patch("app.services.app_updater.urllib.request.urlretrieve",
                        side_effect=fake_urlretrieve):
            with self.assertRaises(AppUpdateError):
                u.download_and_stage("https://x/update.zip")

    def test_download_failure_raises_clean_error(self):
        u = AppUpdater()
        with mock.patch("app.services.app_updater.urllib.request.urlretrieve",
                        side_effect=OSError("connection reset")):
            with self.assertRaises(AppUpdateError):
                u.download_and_stage("https://x/update.zip")


if __name__ == "__main__":
    unittest.main()
