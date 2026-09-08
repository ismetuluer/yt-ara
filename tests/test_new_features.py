"""Yeni ozelliklerin testleri: yt-dlp motoru, indirme, kare cikarma, gecmis."""
import datetime as dt
import os
import tempfile
import unittest
from unittest import mock

from PySide6.QtCore import Qt

from app.models.video import VideoResult
from app.services.download_history import DownloadHistory
from app.services.download_service import (
    QUALITY_OPTIONS, DownloadService, sanitize_filename,
)
from app.services.ffmpeg_service import (
    FFmpegError, format_timecode, parse_timecode,
)
from app.services.search.ytdlp_search_service import (
    YtDlpSearchEngine, _date_in_range, _exact_phrase_match,
)
from app.services.ytdlp_service import YtDlpService, _entry_to_video


def sample_video(video_id, title="Türkçe Başlık ğüşİıçö", channel="Kanal",
                 channel_id="UC1", published="2024-01-15T00:00:00Z"):
    return VideoResult(
        video_id=video_id, title=title, channel_id=channel_id,
        channel_title=channel, published_at=published,
        url=VideoResult.make_url(video_id))


class TestTimecode(unittest.TestCase):
    def test_parse_seconds(self):
        self.assertEqual(parse_timecode("45"), 45)

    def test_parse_mmss(self):
        self.assertEqual(parse_timecode("01:30"), 90)

    def test_parse_hhmmss(self):
        self.assertEqual(parse_timecode("01:02:03"), 3723)

    def test_parse_invalid(self):
        with self.assertRaises(ValueError):
            parse_timecode("abc")
        with self.assertRaises(ValueError):
            parse_timecode("1:2:3:4")

    def test_format_timecode(self):
        self.assertEqual(format_timecode(90), "00-01-30")
        self.assertEqual(format_timecode(3723), "01-02-03")


class TestSanitizeFilename(unittest.TestCase):
    def test_invalid_chars_replaced(self):
        self.assertEqual(sanitize_filename('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")

    def test_reserved_names(self):
        self.assertTrue(sanitize_filename("con").startswith("_"))

    def test_empty_becomes_video(self):
        self.assertEqual(sanitize_filename("   "), "video")

    def test_trailing_dots_stripped(self):
        self.assertEqual(sanitize_filename("video..."), "video")


class TestExactPhrase(unittest.TestCase):
    def test_match_case_insensitive(self):
        self.assertTrue(_exact_phrase_match("İstanbul depremi sonrası", "istanbul depremi"))

    def test_no_match_when_split(self):
        self.assertFalse(_exact_phrase_match("İstanbul'da deprem", "istanbul depremi"))

    def test_empty_phrase_matches(self):
        self.assertTrue(_exact_phrase_match("herhangi", ""))


class TestDateInRange(unittest.TestCase):
    def test_within_range(self):
        self.assertTrue(_date_in_range(
            "2024-01-15T00:00:00Z",
            dt.date(2024, 1, 1), dt.date(2024, 2, 1)))

    def test_before_range(self):
        self.assertFalse(_date_in_range(
            "2023-12-01T00:00:00Z",
            dt.date(2024, 1, 1), None))

    def test_after_range(self):
        self.assertFalse(_date_in_range(
            "2024-03-01T00:00:00Z",
            None, dt.date(2024, 2, 1)))

    def test_no_date_always_true(self):
        self.assertTrue(_date_in_range("", dt.date(2024, 1, 1), None))


class TestEntryToVideo(unittest.TestCase):
    def test_basic_conversion(self):
        entry = {"id": "abc123", "title": "Başlık", "channel": "K",
                 "channel_id": "UC1", "upload_date": "20240115"}
        v = _entry_to_video(entry)
        self.assertEqual(v.video_id, "abc123")
        self.assertEqual(v.published_at, "2024-01-15T00:00:00Z")

    def test_missing_id_returns_none(self):
        self.assertIsNone(_entry_to_video({"title": "x"}))

    def test_fallback_channel(self):
        entry = {"id": "abc", "title": "x"}
        v = _entry_to_video(entry, fallback_channel="Kanal", fallback_channel_id="UC9")
        self.assertEqual(v.channel_title, "Kanal")
        self.assertEqual(v.channel_id, "UC9")


class TestYtDlpSearchEngine(unittest.TestCase):
    def test_general_search_filters_dates(self):
        engine = YtDlpSearchEngine()
        v1 = sample_video("v1", published="2024-01-15T00:00:00Z")
        v2 = sample_video("v2", published="2023-06-01T00:00:00Z")
        with mock.patch.object(engine.service, "search_flat", return_value=[v1, v2]):
            videos, token = engine.search_page(
                "test", published_after=dt.date(2024, 1, 1))
        self.assertEqual([v.video_id for v in videos], ["v1"])

    def test_general_search_pagination(self):
        engine = YtDlpSearchEngine()
        videos = [sample_video(f"v{i}") for i in range(10)]
        with mock.patch.object(engine.service, "search_flat", return_value=videos):
            page1, token = engine.search_page("test", max_results=4)
            page2, token2 = engine.search_page("test", page_token=token, max_results=4)
        self.assertEqual(len(page1), 4)
        self.assertEqual(len(page2), 4)
        self.assertEqual(page1[0].video_id, "v0")
        self.assertEqual(page2[0].video_id, "v4")

    def test_general_search_has_more_when_full_batch_returned_even_if_none_filtered(self):
        """yt-dlp istenen kadar sonuc dondurdugunde -- tarih filtresi hicbir
        seyi elemese bile -- 'daha fazla sonuc' hala mumkun olmali.
        Onceki hata: has_more, filtrelenmis uzunluga bakiyordu ve bu da
        fetch sayisina esit kaldigi icin hep False oluyordu."""
        engine = YtDlpSearchEngine()
        videos = [sample_video(f"v{i}") for i in range(50)]  # hepsi tarih icinde
        with mock.patch.object(engine.service, "search_flat", return_value=videos):
            page, token = engine.search_page("test", max_results=50)
        self.assertEqual(len(page), 50)
        self.assertNotEqual(token, "", "yt-dlp tam istenen kadar sonuc dondurdu; 'daha fazla' aktif olmali")

    def test_general_search_no_more_when_fewer_returned_than_requested(self):
        engine = YtDlpSearchEngine()
        videos = [sample_video(f"v{i}") for i in range(3)]  # istenenden az
        with mock.patch.object(engine.service, "search_flat", return_value=videos):
            page, token = engine.search_page("test", max_results=50)
        self.assertEqual(token, "", "YouTube'da baska sonuc kalmadiginda 'daha fazla' kapali olmali")

    def test_general_search_streams_via_on_video(self):
        """Sonuclar tek tek hazir oldukca `on_video` ile bildirilmeli,
        tumu bitmeden -- bu, arayuzun sonuclari arama sirasinda listeye
        eklemesini saglayan mekanizmadir."""
        engine = YtDlpSearchEngine()
        videos = [sample_video(f"v{i}") for i in range(5)]
        streamed = []
        with mock.patch.object(engine.service, "search_flat", return_value=videos):
            page, _ = engine.search_page("test", max_results=5, on_video=streamed.append)
        self.assertEqual({v.video_id for v in streamed}, {v.video_id for v in page})
        self.assertEqual(len(streamed), 5)

    def test_channel_scan_streams_via_on_video_as_dates_arrive(self):
        engine = YtDlpSearchEngine()
        engine._channel_urls["UC1"] = "https://www.youtube.com/@kanal"
        videos = [sample_video(f"c{i}", title="t", published="") for i in range(4)]
        with mock.patch.object(engine.service, "channel_videos_flat", return_value=videos), \
             mock.patch.object(engine.service, "video_upload_date",
                               return_value="2024-06-01T00:00:00Z"):
            streamed = []
            page, _ = engine.search_page(
                "", channel_id="UC1", published_after=dt.date(2024, 1, 1),
                on_video=streamed.append)
        self.assertEqual(len(streamed), 4)
        self.assertEqual({v.video_id for v in streamed}, {v.video_id for v in page})

    def test_channel_scan_uses_stored_url(self):
        engine = YtDlpSearchEngine()
        engine._channel_urls["UC1"] = "https://www.youtube.com/@kanal"
        with mock.patch.object(engine.service, "channel_videos_flat",
                               return_value=[sample_video("c1", title="test başlık")]) as m:
            videos, token = engine.search_page("test", channel_id="UC1")
        m.assert_called_once_with("https://www.youtube.com/@kanal", limit=100)
        self.assertEqual([v.video_id for v in videos], ["c1"])

    def test_channel_scan_limit(self):
        engine = YtDlpSearchEngine()
        engine.set_channel_scan_limit(500)
        engine._channel_urls["UC1"] = "https://www.youtube.com/channel/UC1"
        with mock.patch.object(engine.service, "channel_videos_flat",
                               return_value=[]) as m:
            engine.search_page("test", channel_id="UC1")
        self.assertEqual(m.call_args[1]["limit"], 500)

    def test_channel_scan_query_filter(self):
        engine = YtDlpSearchEngine()
        engine._channel_urls["UC1"] = "https://www.youtube.com/@kanal"
        v_match = sample_video("m1", title="İstanbul depremi sonrası")
        v_no = sample_video("n1", title="Başka bir video")
        with mock.patch.object(engine.service, "channel_videos_flat",
                               return_value=[v_match, v_no]):
            videos, _ = engine.search_page("istanbul depremi", channel_id="UC1")
        self.assertEqual([v.video_id for v in videos], ["m1"])

    def test_channel_scan_date_filter_enriches(self):
        engine = YtDlpSearchEngine()
        engine._channel_urls["UC1"] = "https://www.youtube.com/@kanal"
        v_old = sample_video("old", title="eski", published="")
        v_new = sample_video("new", title="yeni", published="")
        def fake_date(vid):
            return "2023-01-01T00:00:00Z" if vid == "old" else "2024-06-01T00:00:00Z"
        with mock.patch.object(engine.service, "channel_videos_flat",
                               return_value=[v_old, v_new]), \
             mock.patch.object(engine.service, "video_upload_date",
                               side_effect=fake_date):
            videos, _ = engine.search_page(
                "", channel_id="UC1", published_after=dt.date(2024, 1, 1))
        self.assertEqual([v.video_id for v in videos], ["new"])

    def test_resolve_channel_stores_url(self):
        engine = YtDlpSearchEngine()
        with mock.patch.object(engine.service, "resolve_channel",
                               return_value=("UC1", "Kanal")):
            cid, title = engine.resolve_channel("https://www.youtube.com/@kanal")
        self.assertEqual(cid, "UC1")
        self.assertEqual(engine._channel_urls["UC1"], "https://www.youtube.com/@kanal")


class TestDownloadHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "hist.db")
        self.history = DownloadHistory(self.db)

    def tearDown(self):
        try:
            os.remove(self.db)
        except OSError:
            pass

    def test_add_and_recent(self):
        rid = self.history.add("Başlık", "https://youtu.be/abc", None, "indiriliyor")
        self.assertGreater(rid, 0)
        recent = self.history.recent()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["title"], "Başlık")
        self.assertEqual(recent[0]["status"], "indiriliyor")

    def test_update_status(self):
        rid = self.history.add("Başlık", "url", None, "indiriliyor")
        self.history.update_status(rid, "tamam", "C:/path/video.mp4")
        recent = self.history.recent()
        self.assertEqual(recent[0]["status"], "tamam")
        self.assertEqual(recent[0]["file_path"], "C:/path/video.mp4")


class TestDownloadService(unittest.TestCase):
    def test_quality_format_mapping(self):
        svc = DownloadService("C:/tmp", quality="720p")
        self.assertIn("height<=720", svc._format_for("720p"))
        self.assertIn("bestvideo*+bestaudio", svc._format_for("En İyi"))

    def test_unknown_quality_falls_back(self):
        svc = DownloadService("C:/tmp", quality="Bilinmeyen")
        self.assertIn("bestvideo*+bestaudio", svc._format_for("Bilinmeyen"))

    def test_resolved_path(self):
        svc = DownloadService("C:/tmp")
        info = {"title": "Güzel Video", "id": "abc123", "ext": "mp4"}
        path = svc._resolved_path(info, "")
        self.assertTrue(path.endswith("Güzel Video [abc123].mp4"))

    def test_download_cancel_raises_module_path(self):
        """Gömülü modul yolu: tools/yt-dlp/yt-dlp.exe yokken."""
        svc = DownloadService("C:/tmp")
        svc.cancel()
        with mock.patch.object(svc, "_external_binary", return_value=None), \
             mock.patch("yt_dlp.YoutubeDL") as m:
            m.return_value.__enter__.return_value.extract_info.side_effect = \
                __import__("yt_dlp").utils.DownloadCancelled()
            with self.assertRaises(Exception):
                svc.download("https://youtu.be/abc")

    def test_download_cancel_raises_external_path(self):
        """Harici binary yolu: indirme sirasinda iptal edilirse hata verir."""
        svc = DownloadService("C:/tmp")
        with mock.patch.object(svc, "_external_binary", return_value="C:/fake/yt-dlp.exe"), \
             mock.patch("subprocess.Popen") as popen:
            proc = popen.return_value
            proc.poll.return_value = 0

            def fake_communicate():
                svc.cancel()  # indirme "sirasinda" iptal edildi
                return (b"", None)
            proc.communicate.side_effect = fake_communicate
            with self.assertRaises(Exception):
                svc.download("https://youtu.be/abc")


class TestFrameWorker(unittest.TestCase):
    def test_worker_emits_done(self):
        from app.workers.frame_worker import FrameWorker
        worker = FrameWorker("C:/nonexistent.mp4", "C:/out", "base",
                             times_seconds=[10])
        outcomes = {}
        worker.done.connect(lambda paths: outcomes.update(done=paths))
        worker.failed.connect(lambda msg: outcomes.update(failed=msg))
        worker.run()
        # Dosya yok -> hata beklenir
        self.assertIn("failed", outcomes)


class TestDownloadWorker(unittest.TestCase):
    def test_worker_emits_all_done(self):
        from app.workers.download_worker import DownloadWorker
        worker = DownloadWorker("C:/tmp", "En İyi",
                                [{"video_id": "a", "title": "A", "url": "u"}])
        outcomes = {}
        worker.finished.connect(lambda *a: outcomes.update(finished=a),
                                Qt.ConnectionType.DirectConnection)
        worker.all_done.connect(lambda d, t: outcomes.update(all_done=(d, t)),
                                Qt.ConnectionType.DirectConnection)
        with mock.patch.object(DownloadService, "download", return_value="C:/out/video.mp4"):
            worker.run()
        self.assertEqual(outcomes["all_done"], (1, 1))
        self.assertEqual(outcomes["finished"][0], "a")

    def test_worker_downloads_concurrently(self):
        """Birden fazla video ayni anda indirilebilmeli (sirali degil)."""
        from app.workers.download_worker import DownloadWorker
        items = [{"video_id": f"v{i}", "title": f"T{i}", "url": f"u{i}"} for i in range(3)]
        worker = DownloadWorker("C:/tmp", "En İyi", items)
        outcomes = {"finished": []}
        worker.finished.connect(lambda vid, t, p: outcomes["finished"].append(vid),
                                Qt.ConnectionType.DirectConnection)
        worker.all_done.connect(lambda d, t: outcomes.update(all_done=(d, t)),
                                Qt.ConnectionType.DirectConnection)
        with mock.patch.object(DownloadService, "download", return_value="C:/out/video.mp4"):
            worker.run()
        self.assertEqual(outcomes["all_done"], (3, 3))
        self.assertEqual(sorted(outcomes["finished"]), ["v0", "v1", "v2"])

    def test_cancel_stops_active_services(self):
        from app.workers.download_worker import DownloadWorker
        worker = DownloadWorker("C:/tmp", "En İyi",
                                [{"video_id": "a", "title": "A", "url": "u"}])
        svc = mock.Mock()
        worker._active_services.append(svc)
        worker.cancel()
        svc.cancel.assert_called_once()


if __name__ == "__main__":
    unittest.main()
