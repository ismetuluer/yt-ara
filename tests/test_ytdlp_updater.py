"""yt-dlp updater, update worker ve etkin kaynak zinciri testleri.

Ag erisimi gerektirmez; urllib/subprocess mock'lanir.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.settings_service import SettingsService
from app.services.ytdlp_updater import YtDlpUpdateError, YtDlpUpdater, _version_tuple


class FakeCompletedProcess:
    def __init__(self, stdout=""):
        self.stdout = stdout


class TestVersionTuple(unittest.TestCase):
    def test_parses_dotted_version(self):
        self.assertEqual(_version_tuple("2026.08.19"), (2026, 8, 19))

    def test_invalid_falls_back(self):
        self.assertEqual(_version_tuple("not-a-version"), (0,))


class TestCurrentVersion(unittest.TestCase):
    def test_uses_module_when_no_binary(self):
        u = YtDlpUpdater()
        with mock.patch.object(u, "_binary_version", return_value=""):
            with mock.patch("app.services.ytdlp_updater.yt_dlp.version.__version__",
                            "2026.03.17"):
                self.assertEqual(u.current_version(), "2026.03.17")

    def test_uses_newer_binary_version(self):
        u = YtDlpUpdater()
        with mock.patch.object(u, "_binary_version", return_value="2026.08.19"):
            with mock.patch("app.services.ytdlp_updater.yt_dlp.version.__version__",
                            "2026.03.17"):
                self.assertEqual(u.current_version(), "2026.08.19")

    def test_binary_version_cached_per_session(self):
        u = YtDlpUpdater()
        with mock.patch("app.services.ytdlp_updater.os.path.isfile", return_value=True), \
             mock.patch("app.services.ytdlp_updater.subprocess.run",
                        return_value=FakeCompletedProcess("2026.08.19\n")) as run:
            first = u._binary_version()
            second = u._binary_version()
        self.assertEqual(first, "2026.08.19")
        self.assertEqual(second, "2026.08.19")
        run.assert_called_once()  # ikinci cagri onbellekten donmeli

    def test_binary_version_missing_file_returns_empty(self):
        u = YtDlpUpdater()
        with mock.patch("app.services.ytdlp_updater.os.path.isfile", return_value=False):
            self.assertEqual(u._binary_version(), "")


class TestLatestVersion(unittest.TestCase):
    def test_parses_tag_name(self):
        u = YtDlpUpdater()
        payload = json.dumps({"tag_name": "2026.08.19"}).encode()

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return payload

        with mock.patch("app.services.ytdlp_updater.urllib.request.urlopen",
                        return_value=FakeResp()), \
             mock.patch("app.services.ytdlp_updater.json.load",
                        return_value={"tag_name": "v2026.08.19"}):
            self.assertEqual(u.latest_version(), "2026.08.19")

    def test_network_failure_raises_ytdlp_update_error(self):
        u = YtDlpUpdater()
        with mock.patch("app.services.ytdlp_updater.urllib.request.urlopen",
                        side_effect=OSError("boom")):
            with self.assertRaises(YtDlpUpdateError):
                u.latest_version()

    def test_is_outdated_false_on_network_error(self):
        u = YtDlpUpdater()
        with mock.patch.object(u, "latest_version", side_effect=YtDlpUpdateError("x")):
            self.assertFalse(u.is_outdated())


class TestCompare(unittest.TestCase):
    def test_outdated_true_when_current_lower(self):
        u = YtDlpUpdater()
        with mock.patch.object(u, "current_version", return_value="2026.01.01"), \
             mock.patch.object(u, "latest_version", return_value="2026.08.19"):
            current, latest, outdated = u.compare()
        self.assertTrue(outdated)
        self.assertEqual((current, latest), ("2026.01.01", "2026.08.19"))

    def test_outdated_false_when_up_to_date(self):
        u = YtDlpUpdater()
        with mock.patch.object(u, "current_version", return_value="2026.08.19"), \
             mock.patch.object(u, "latest_version", return_value="2026.08.19"):
            *_, outdated = u.compare()
        self.assertFalse(outdated)


class TestUpdate(unittest.TestCase):
    def _updater_with_tmp_dir(self, tmp):
        u = YtDlpUpdater()
        dest = os.path.join(tmp, "yt-dlp.exe")
        patches = [
            mock.patch("app.services.ytdlp_updater.ytdlp_dir", return_value=tmp),
            mock.patch("app.services.ytdlp_updater.ytdlp_binary", return_value=dest),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return u, dest

    def test_update_writes_via_temp_file_then_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            u, dest = self._updater_with_tmp_dir(tmp)
            written_tmp_paths = []

            def fake_retrieve(url, filename, reporthook=None):
                written_tmp_paths.append(filename)
                with open(filename, "wb") as f:
                    f.write(b"fake-binary-content")
                if reporthook:
                    reporthook(1, 100, 100)

            with mock.patch("app.services.ytdlp_updater.urllib.request.urlretrieve",
                            side_effect=fake_retrieve):
                result = u.update()

            self.assertEqual(result, dest)
            self.assertTrue(os.path.isfile(dest))
            # gecici dosya asil konuma tasindi, kendisi kalmadi
            self.assertTrue(written_tmp_paths[0].endswith(".tmp"))
            self.assertFalse(os.path.isfile(written_tmp_paths[0]))
            # surum onbellegi gecersiz kilindi
            self.assertIsNone(u._binary_ver)

    def test_update_network_failure_preserves_old_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            u, dest = self._updater_with_tmp_dir(tmp)
            with open(dest, "wb") as f:
                f.write(b"old-working-binary")

            with mock.patch("app.services.ytdlp_updater.urllib.request.urlretrieve",
                            side_effect=OSError("network down")):
                with self.assertRaises(YtDlpUpdateError):
                    u.update()

            # eski dosya korunmali
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"old-working-binary")
            # yarim indirilmis gecici dosya birakilmamali
            self.assertFalse(os.path.isfile(dest + ".tmp"))

    def test_update_download_failure_reports_progress_zero_then_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            u, dest = self._updater_with_tmp_dir(tmp)
            progress_calls = []

            def fake_retrieve(url, filename, reporthook=None):
                raise OSError("connection reset")

            with mock.patch("app.services.ytdlp_updater.urllib.request.urlretrieve",
                            side_effect=fake_retrieve):
                with self.assertRaises(YtDlpUpdateError):
                    u.update(progress_cb=lambda pct, msg: progress_calls.append((pct, msg)))
            self.assertFalse(os.path.isfile(dest))
            self.assertTrue(len(progress_calls) >= 1)


class TestSettingsYtdlpLastCheck(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ayarlar.json")
            s = SettingsService(path=path)
            s.ytdlp_last_check = "2026-08-30"
            s.save()
            s2 = SettingsService(path=path)
            self.assertEqual(s2.ytdlp_last_check, "2026-08-30")

    def test_missing_field_defaults_empty_old_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ayarlar.json")
            # eski config: ytdlp_last_check alani yok
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"api_key": "X", "theme": "dark"}, f)
            s = SettingsService(path=path)
            self.assertEqual(s.ytdlp_last_check, "")
            self.assertEqual(s.api_key, "X")
            self.assertEqual(s.theme, "dark")


class TestUpdateWorker(unittest.TestCase):
    def run_worker(self, worker):
        outcomes = {"progress": []}
        worker.checked.connect(
            lambda c, l, o: outcomes.update(checked=(c, l, o)))
        worker.progress.connect(lambda pct, msg: outcomes["progress"].append((pct, msg)))
        worker.updated.connect(lambda v: outcomes.update(updated=v))
        worker.up_to_date.connect(lambda v: outcomes.update(up_to_date=v))
        worker.failed.connect(lambda msg: outcomes.update(failed=msg))
        worker.run()
        return outcomes

    def test_up_to_date_emits_up_to_date_not_updated(self):
        from app.workers.update_worker import YtDlpUpdateWorker
        worker = YtDlpUpdateWorker(auto=False)
        with mock.patch("app.workers.update_worker.YtDlpUpdater") as MockUpdater:
            inst = MockUpdater.return_value
            inst.compare.return_value = ("2026.08.19", "2026.08.19", False)
            out = self.run_worker(worker)
        self.assertEqual(out["checked"], ("2026.08.19", "2026.08.19", False))
        self.assertEqual(out["up_to_date"], "2026.08.19")
        self.assertNotIn("updated", out)

    def test_outdated_triggers_update_and_emits_updated(self):
        from app.workers.update_worker import YtDlpUpdateWorker
        worker = YtDlpUpdateWorker(auto=False)
        with mock.patch("app.workers.update_worker.YtDlpUpdater") as MockUpdater:
            inst = MockUpdater.return_value
            inst.compare.return_value = ("2026.01.01", "2026.08.19", True)
            inst.update.return_value = "C:/tools/yt-dlp/yt-dlp.exe"
            out = self.run_worker(worker)
        self.assertEqual(out["updated"], "2026.08.19")
        self.assertNotIn("up_to_date", out)

    def test_manual_network_failure_emits_failed(self):
        from app.workers.update_worker import YtDlpUpdateWorker
        from app.services.ytdlp_updater import YtDlpUpdateError
        worker = YtDlpUpdateWorker(auto=False)
        with mock.patch("app.workers.update_worker.YtDlpUpdater") as MockUpdater:
            inst = MockUpdater.return_value
            inst.compare.side_effect = YtDlpUpdateError("İnternet bağlantınızı kontrol edin.")
            out = self.run_worker(worker)
        self.assertIn("failed", out)
        self.assertIn("İnternet", out["failed"])

    def test_auto_network_failure_stays_silent(self):
        """auto=True iken hata kullaniciya gosterilmemeli (yalniz loglanir)."""
        from app.workers.update_worker import YtDlpUpdateWorker
        from app.services.ytdlp_updater import YtDlpUpdateError
        worker = YtDlpUpdateWorker(auto=True)
        with mock.patch("app.workers.update_worker.YtDlpUpdater") as MockUpdater:
            inst = MockUpdater.return_value
            inst.compare.side_effect = YtDlpUpdateError("boom")
            out = self.run_worker(worker)
        self.assertNotIn("failed", out)

    def test_download_failure_after_outdated_check_reports_failed_manual(self):
        from app.workers.update_worker import YtDlpUpdateWorker
        from app.services.ytdlp_updater import YtDlpUpdateError
        worker = YtDlpUpdateWorker(auto=False)
        with mock.patch("app.workers.update_worker.YtDlpUpdater") as MockUpdater:
            inst = MockUpdater.return_value
            inst.compare.return_value = ("2026.01.01", "2026.08.19", True)
            inst.update.side_effect = YtDlpUpdateError("İndirilemedi.")
            out = self.run_worker(worker)
        self.assertIn("failed", out)
        self.assertNotIn("updated", out)


class TestActiveSourceChain(unittest.TestCase):
    """Updater'in guncelledigi kaynagin Search ve Download tarafinda da
    etkin oldugunu dogrular (AGENTS.md #10, #14, #15)."""

    def test_search_service_prefers_external_binary_when_present(self):
        from app.services.ytdlp_service import YtDlpService
        svc = YtDlpService()
        with tempfile.TemporaryDirectory() as tmp:
            fake_binary = os.path.join(tmp, "yt-dlp.exe")
            with open(fake_binary, "wb") as f:
                f.write(b"fake")
            with mock.patch("app.services.ytdlp_service.ytdlp_binary",
                            return_value=fake_binary):
                self.assertEqual(svc._external_binary(), fake_binary)

    def test_search_service_falls_back_to_module_without_binary(self):
        from app.services.ytdlp_service import YtDlpService
        svc = YtDlpService()
        with mock.patch("app.services.ytdlp_service.ytdlp_binary",
                        return_value="C:/nonexistent/yt-dlp.exe"):
            self.assertIsNone(svc._external_binary())

    def test_download_service_prefers_external_binary_when_present(self):
        from app.services.download_service import DownloadService
        svc = DownloadService("C:/tmp")
        with tempfile.TemporaryDirectory() as tmp:
            fake_binary = os.path.join(tmp, "yt-dlp.exe")
            with open(fake_binary, "wb") as f:
                f.write(b"fake")
            with mock.patch("app.services.download_service.ytdlp_binary",
                            return_value=fake_binary):
                self.assertEqual(svc._external_binary(), fake_binary)

    def test_search_and_download_agree_on_same_updated_binary_path(self):
        """Updater'in yazdigi dosya yolu ile search/download servislerinin
        aradigi yol ayni olmali (tek etkin kaynak)."""
        from app.utils.paths import ytdlp_binary as paths_binary
        from app.services.ytdlp_service import ytdlp_binary as search_binary
        from app.services.download_service import ytdlp_binary as download_binary
        from app.services.ytdlp_updater import ytdlp_binary as updater_binary
        self.assertIs(paths_binary, search_binary)
        self.assertIs(paths_binary, download_binary)
        self.assertIs(paths_binary, updater_binary)

    def test_extract_dispatches_to_external_when_binary_present(self):
        from app.services.ytdlp_service import YtDlpService
        svc = YtDlpService()
        with mock.patch.object(svc, "_subprocess_prefix", return_value=["C:/fake/yt-dlp.exe"]), \
             mock.patch.object(svc, "_extract_external", return_value={"id": "x"}) as ext, \
             mock.patch.object(svc, "_extract_module") as mod:
            result = svc._extract("https://youtu.be/x", {})
        ext.assert_called_once()
        mod.assert_not_called()
        self.assertEqual(result, {"id": "x"})

    def test_extract_dispatches_to_module_only_when_frozen_without_binary(self):
        """In-process modul yalnizca dondurulmus EXE'de ve binary yokken
        kullanilir; aksi halde `python -m yt_dlp` subprocess'i tercih
        edilir (iptalin gercekten calismasi icin)."""
        from app.services.ytdlp_service import YtDlpService
        svc = YtDlpService()
        with mock.patch.object(svc, "_external_binary", return_value=None), \
             mock.patch("app.services.ytdlp_service.sys.frozen", True, create=True), \
             mock.patch.object(svc, "_extract_module", return_value={"id": "y"}) as mod, \
             mock.patch.object(svc, "_extract_external") as ext:
            result = svc._extract("https://youtu.be/y", {})
        mod.assert_called_once()
        ext.assert_not_called()
        self.assertEqual(result, {"id": "y"})

    def test_extract_uses_python_module_subprocess_when_not_frozen_and_no_binary(self):
        from app.services.ytdlp_service import YtDlpService
        import sys as sys_module
        svc = YtDlpService()
        with mock.patch.object(svc, "_external_binary", return_value=None), \
             mock.patch.object(svc, "_extract_external", return_value={"id": "z"}) as ext, \
             mock.patch.object(svc, "_extract_module") as mod:
            result = svc._extract("https://youtu.be/z", {})
        mod.assert_not_called()
        ext.assert_called_once()
        cmd_prefix = ext.call_args[0][0]
        self.assertEqual(cmd_prefix, [sys_module.executable, "-m", "yt_dlp"])
        self.assertEqual(result, {"id": "z"})


if __name__ == "__main__":
    unittest.main()
