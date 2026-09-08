"""Arayuz duman testi: pencere acilir, sahte sonuclar yuklenir,
kopyalama/siralama/disa aktarma dogrulanir. Ekran gerektirmez (offscreen)."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.models.video import VideoResult
from app.services.settings_service import SettingsService
from app.ui.main_window import COL_DATE, COL_TITLE, MainWindow


def make_videos(n):
    return [
        VideoResult(video_id=f"id{i:03d}", title=f"Video {i:03d} ğüşİıçö",
                    channel_id=f"UC{i}", channel_title=f"Kanal {i % 3}",
                    published_at=f"2024-01-{(i % 28) + 1:02d}T10:00:00Z",
                    url=f"https://www.youtube.com/watch?v=id{i:03d}")
        for i in range(1, n + 1)
    ]


def main():
    app = QApplication(sys.argv)
    with tempfile.TemporaryDirectory() as tmp:
        settings = SettingsService(path=os.path.join(tmp, "ayarlar.json"))
        win = MainWindow(settings)

        # 1) 50 sahte sonuc yukle (worker sinyallerini taklit et)
        videos = make_videos(50)
        win._signature = ("test", False, None, None, ())
        win._on_partial(videos, [])
        win._on_search_done([], {"": ""}, False, False, True)

        assert win.table.rowCount() == 50, f"Satir sayisi: {win.table.rowCount()}"
        assert win.count_label.text() == "50 sonuç", win.count_label.text()

        # 2) Varsayilan siralama: en yeni en ustte (tarih azalan)
        first_title = win.table.item(0, COL_TITLE).text()
        dates = [win.table.item(r, COL_DATE).data(Qt.UserRole) for r in range(50)]
        assert dates == sorted(dates, reverse=True), "Varsayilan siralama tarih azalan olmali"

        # 3) Tum adresleri kopyala -> her satirda bir URL
        win.copy_all()
        clip = QGuiApplication.clipboard().text()
        lines = clip.split("\n")
        assert len(lines) == 50, f"Pano satir sayisi: {len(lines)}"
        assert all(l.startswith("https://www.youtube.com/watch?v=") for l in lines)
        print(f"  kopyalama OK (ilk: {lines[0]})")

        # 4) Secili satirlari kopyala
        win.table.selectAll()
        assert len(win._selected_rows()) == 50
        win.table.clearSelection()
        win.table.selectRow(0)
        win.copy_selected()
        assert len(QGuiApplication.clipboard().text().split("\n")) == 1
        print("  secili kopyalama OK")

        # 5) Mukerrer video eklenmemeli
        win._on_partial([videos[0], videos[1]], [])
        assert len(win.results) == 50, f"Mukerrer eklendi: {len(win.results)}"
        print("  mukerrer kontrolu OK")

        # 6) Onbellek: ayni arama API'siz yuklenmeli
        assert win._load_from_cache(("test", False, None, None, ())) is True
        print("  onbellek OK")

        # 7) TXT / CSV disa aktarma
        txt_path = os.path.join(tmp, "out.txt")
        from app.services import export_service
        export_service.export_txt(txt_path, win._table_videos())
        with open(txt_path, encoding="utf-8") as f:
            assert len(f.read().strip().split("\n")) == 50
        csv_path = os.path.join(tmp, "out.csv")
        export_service.export_csv(csv_path, win._table_videos())
        with open(csv_path, encoding="utf-8-sig") as f:
            content = f.read()
        assert "ğüşİıçö" in content
        print("  disa aktarma OK")

        # 8) Tarih dogrulama: bitis < baslangic reddedilmeli
        import datetime as dt
        from app.ui.main_window import validate_inputs
        assert validate_inputs("x", True, dt.date(2024, 5, 1), dt.date(2024, 1, 1)) is not None
        print("  tarih dogrulama OK")

        win.close()
    print("SMOKE TEST BASARILI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
