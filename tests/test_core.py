"""Cekirdek mantik testleri (ag erisimi gerektirmez)."""
import csv
import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.video import VideoResult
from app.services import export_service
from app.services.channel_resolver import ChannelInfo, ChannelResolver, parse_channel_input
from app.services.settings_service import SettingsService
from app.services.youtube_service import YouTubeError, YouTubeService
from app.ui.main_window import validate_inputs


def sample_video(video_id="abc12345678", title="Türkçe Başlık ğüşİıçö",
                 channel="Kanal Adı", published="2024-03-15T14:22:00Z"):
    return VideoResult(
        video_id=video_id, title=title, channel_id="UCxxxxxxxxxxxxxxxxxxxxxx",
        channel_title=channel, published_at=published,
        url=VideoResult.make_url(video_id))


class TestParseChannelInput(unittest.TestCase):
    def test_handle_url(self):
        self.assertEqual(parse_channel_input("https://www.youtube.com/@kanaladi"),
                         ("handle", "kanaladi"))

    def test_handle_url_with_suffix(self):
        self.assertEqual(parse_channel_input("https://www.youtube.com/@kanaladi/videos"),
                         ("handle", "kanaladi"))

    def test_channel_id_url(self):
        cid = "UCBR8-60-B28hp2BmDPdntcQ"
        self.assertEqual(parse_channel_input(f"https://www.youtube.com/channel/{cid}"),
                         ("id", cid))

    def test_user_url(self):
        self.assertEqual(parse_channel_input("https://www.youtube.com/user/eskiadi"),
                         ("user", "eskiadi"))

    def test_custom_url(self):
        self.assertEqual(parse_channel_input("https://www.youtube.com/c/kanaladi"),
                         ("custom", "kanaladi"))

    def test_bare_handle(self):
        self.assertEqual(parse_channel_input("@kanaladi"), ("handle", "kanaladi"))

    def test_bare_id(self):
        cid = "UCBR8-60-B28hp2BmDPdntcQ"
        self.assertEqual(parse_channel_input(cid), ("id", cid))

    def test_plain_name_falls_back_to_search(self):
        self.assertEqual(parse_channel_input("rastgele kanal"), ("search", "rastgele kanal"))


class TestVideoModel(unittest.TestCase):
    def test_display_date_turkish_format(self):
        self.assertEqual(sample_video().published_display, "15.03.2024")

    def test_sort_key(self):
        self.assertEqual(sample_video().published_sort_key, "2024-03-15T14:22:00Z")

    def test_url(self):
        self.assertEqual(VideoResult.make_url("XYZ"),
                         "https://www.youtube.com/watch?v=XYZ")


class TestExport(unittest.TestCase):
    def test_txt_one_url_per_line(self):
        videos = [sample_video("AAAA"), sample_video("BBBB"), sample_video("CCCC")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "videolar.txt")
            count = export_service.export_txt(path, videos)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        self.assertEqual(count, 3)
        self.assertEqual(content,
                         "https://www.youtube.com/watch?v=AAAA\n"
                         "https://www.youtube.com/watch?v=BBBB\n"
                         "https://www.youtube.com/watch?v=CCCC\n")

    def test_csv_turkish_chars_and_bom(self):
        videos = [sample_video()]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "videolar.csv")
            export_service.export_csv(path, videos)
            with open(path, "rb") as f:
                raw = f.read()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))  # BOM (Excel icin)
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0], ["Video Başlığı", "Kanal", "Yayın Tarihi", "Video URL"])
        self.assertEqual(rows[1][0], "Türkçe Başlık ğüşİıçö")
        self.assertEqual(rows[1][2], "15.03.2024")
        self.assertEqual(rows[1][3], "https://www.youtube.com/watch?v=abc12345678")


class TestSettings(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ayarlar.json")
            s = SettingsService(path=path)
            s.api_key = "  TEST-KEY-123 "
            s.theme = "dark"
            s.export_dir = tmp
            s.save()
            s2 = SettingsService(path=path)
            self.assertEqual(s2.api_key, "TEST-KEY-123")
            self.assertEqual(s2.theme, "dark")
            self.assertEqual(s2.export_dir, tmp)

    def test_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = SettingsService(path=os.path.join(tmp, "yok.json"))
            self.assertEqual(s.api_key, "")
            self.assertEqual(s.theme, "system")


class TestValidation(unittest.TestCase):
    def test_empty_query(self):
        self.assertIsNotNone(validate_inputs("", False, None, None))

    def test_end_before_start(self):
        d1, d2 = dt.date(2024, 12, 31), dt.date(2024, 1, 1)
        self.assertIsNotNone(validate_inputs("x", True, d1, d2))

    def test_valid(self):
        d1, d2 = dt.date(2024, 1, 1), dt.date(2024, 12, 31)
        self.assertIsNone(validate_inputs("Türkiye ekonomisi", True, d1, d2))
        self.assertIsNone(validate_inputs("Türkiye ekonomisi", False, None, None))


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class TestYouTubeService(unittest.TestCase):
    def make_service(self):
        return YouTubeService("FAKE-KEY")

    def test_search_page_parses_results(self):
        service = self.make_service()
        payload = {
            "nextPageToken": "TOKEN2",
            "items": [
                {"id": {"videoId": "v1"},
                 "snippet": {"title": "Bir", "channelId": "UC1", "channelTitle": "K1",
                             "publishedAt": "2024-01-02T10:00:00Z"}},
                {"id": {"videoId": "v2"},
                 "snippet": {"title": "İki", "channelId": "UC2", "channelTitle": "K2",
                             "publishedAt": "2024-01-01T10:00:00Z"}},
            ],
        }
        captured = {}

        def fake_get(endpoint, params):
            captured.update(params)
            return payload

        service._get = fake_get
        videos, token = service.search_page(
            "deprem", channel_id="UC1",
            published_after=dt.date(2024, 1, 1), published_before=dt.date(2024, 12, 31))
        self.assertEqual(token, "TOKEN2")
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0].url, "https://www.youtube.com/watch?v=v1")
        self.assertEqual(captured["q"], "deprem")
        self.assertEqual(captured["channelId"], "UC1")
        self.assertEqual(captured["publishedAfter"], "2024-01-01T00:00:00Z")
        # bitis gunu kapsanmali -> ertesi gun
        self.assertEqual(captured["publishedBefore"], "2025-01-01T00:00:00Z")
        self.assertEqual(captured["type"], "video")

    def test_error_mapping_quota(self):
        service = self.make_service()
        resp = FakeResponse(403, {"error": {"errors": [{"reason": "quotaExceeded"}],
                                            "message": "quota"}})
        err = service._map_error(resp)
        self.assertIn("kota", err.user_message.lower())

    def test_error_mapping_bad_key(self):
        service = self.make_service()
        resp = FakeResponse(400, {"error": {"errors": [{"reason": "keyInvalid"}],
                                            "message": "bad key"}})
        err = service._map_error(resp)
        self.assertIn("API anahtarı", err.user_message)

    def test_error_mapping_generic(self):
        service = self.make_service()
        err = service._map_error(FakeResponse(503, {}))
        self.assertIn("geçici", err.user_message.lower())


class FakeResolver:
    def resolve(self, raw):
        return ChannelInfo(channel_id="UC" + raw, title="Kanal " + raw)


class FakeEngine:
    """Arama motoru taklidi yapan sahte motor."""

    def __init__(self, pages_by_channel, resolver=None):
        self.pages_by_channel = pages_by_channel
        self.calls = 0
        self._resolver = resolver or FakeResolver()

    def search_page(self, query, channel_id=None, published_after=None,
                    published_before=None, page_token=None, max_results=50,
                    on_video=None):
        self.calls += 1
        pages = self.pages_by_channel[channel_id or ""]
        index = 0 if not page_token else int(page_token)
        videos, next_index = pages[index]
        if on_video:
            for video in videos:
                on_video(video)
        return videos, (str(next_index) if next_index is not None else "")

    def resolve_channel(self, text):
        info = self._resolver.resolve(text)
        return info.channel_id, info.title

    def validate_available(self):
        return True


class TestWorkerLogic(unittest.TestCase):
    """Worker'i gercek is parcacigi baslatmadan eszamanli calistirir."""

    def run_worker(self, worker):
        outcomes = {"videos": []}
        worker.partial.connect(
            lambda videos, channels: outcomes["videos"].extend(videos))
        worker.search_done.connect(
            lambda c, t, m, cancel: outcomes.update(
                channels=c, tokens=t, more=m, canceled=cancel))
        worker.failed.connect(lambda msg: outcomes.update(failed=msg))
        worker.run()
        return outcomes

    def test_fetch_all_pages_and_dedupe(self):
        from app.workers.search_worker import SearchTask, SearchWorker
        v = [sample_video("v1"), sample_video("v2"), sample_video("v3")]
        pages = {"": [([v[0], v[1]], 1), ([v[1], v[2]], None)]}  # v1 tekrar
        worker = SearchWorker(FakeEngine(pages),
                              SearchTask(query="x", fetch_all=True))
        out = self.run_worker(worker)
        self.assertNotIn("failed", out)
        self.assertEqual([x.video_id for x in out["videos"]], ["v1", "v2", "v3"])
        self.assertFalse(out["more"])

    def test_general_search_excludes_selected_channels(self):
        from app.models.video import VideoResult
        from app.workers.search_worker import SearchTask, SearchWorker
        kept = VideoResult("keep1", "T", "UCkeep", "Tutulan Kanal",
                           "2024-01-01T00:00:00Z", VideoResult.make_url("keep1"))
        excluded = VideoResult("exc1", "T", "UChariç", "Hariç Kanal",
                               "2024-01-01T00:00:00Z", VideoResult.make_url("exc1"))
        pages = {"": [([kept, excluded], None)]}
        worker = SearchWorker(
            FakeEngine(pages),
            SearchTask(query="x", exclude_channel_inputs=["haric-kanal-url"]))
        # FakeEngine.resolve_channel: ChannelInfo(channel_id="UC"+raw, ...)
        # "haric-kanal-url" -> "UChariç-kanal-url" olsun diye resolver'i esitleyelim
        worker.engine._resolver.resolve = lambda raw: ChannelInfo("UChariç", "Hariç Kanal")
        out = self.run_worker(worker)
        ids = [x.video_id for x in out["videos"]]
        self.assertEqual(ids, ["keep1"])

    def test_multi_channel_merge_and_dedupe(self):
        from app.workers.search_worker import SearchTask, SearchWorker
        ch1 = ChannelInfo("UC1", "K1")
        ch2 = ChannelInfo("UC2", "K2")
        shared = sample_video("ortak")
        pages = {
            "UC1": [([sample_video("a"), shared], None)],
            "UC2": [([sample_video("b"), shared], None)],
        }
        worker = SearchWorker(FakeEngine(pages),
                              SearchTask(query="x"), resolved_channels=[ch1, ch2])
        out = self.run_worker(worker)
        ids = [x.video_id for x in out["videos"]]
        self.assertEqual(sorted(ids), ["a", "b", "ortak"])  # mukerrer yok
        self.assertFalse(out["more"])

    def test_cancel_keeps_partial_results(self):
        from app.workers.search_worker import SearchTask, SearchWorker
        ch1 = ChannelInfo("UC1", "K1")
        ch2 = ChannelInfo("UC2", "K2")
        pages = {"UC1": [([sample_video("a")], None)], "UC2": [([sample_video("b")], None)]}
        worker = SearchWorker(FakeEngine(pages),
                              SearchTask(query="x"), resolved_channels=[ch1, ch2])
        original = worker.engine.search_page

        def cancel_after_first(*args, **kwargs):
            worker.cancel()
            return original(*args, **kwargs)

        worker.engine.search_page = cancel_after_first
        out = self.run_worker(worker)
        self.assertTrue(out["canceled"])
        self.assertEqual([x.video_id for x in out["videos"]], ["a"])

    def test_channel_resolution_failure_reported(self):
        from app.workers.search_worker import SearchTask, SearchWorker

        class BadResolver:
            def resolve(self, raw):
                raise YouTubeError(f"Kanal bulunamadı: {raw}")

        worker = SearchWorker(FakeEngine({}, resolver=BadResolver()),
                              SearchTask(query="x", channel_inputs=["bozuk"]))
        out = self.run_worker(worker)
        self.assertIn("Kanal bulunamadı", out.get("failed", ""))

    def test_exact_phrase_filter_applied(self):
        from app.workers.search_worker import SearchTask, SearchWorker
        v_match = sample_video("m1", title="İstanbul depremi sonrası son durum")
        v_no = sample_video("n1", title="İstanbul'da deprem paniği")
        pages = {"": [([v_match, v_no], None)]}
        worker = SearchWorker(FakeEngine(pages),
                              SearchTask(query="İstanbul depremi", exact_phrase=True))
        out = self.run_worker(worker)
        self.assertEqual([x.video_id for x in out["videos"]], ["m1"])

    def test_exact_phrase_disabled_keeps_all(self):
        from app.workers.search_worker import SearchTask, SearchWorker
        v_match = sample_video("m1", title="İstanbul depremi sonrası son durum")
        v_no = sample_video("n1", title="İstanbul'da deprem paniği")
        pages = {"": [([v_match, v_no], None)]}
        worker = SearchWorker(FakeEngine(pages),
                              SearchTask(query="İstanbul depremi", exact_phrase=False))
        out = self.run_worker(worker)
        self.assertEqual(sorted(x.video_id for x in out["videos"]), ["m1", "n1"])


if __name__ == "__main__":
    unittest.main()
