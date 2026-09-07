"""Zamanlanmis indirmeler (SQLite).

Kullanici "Daha sonra indir" secip bir zaman belirledigi zaman buraya
kaydedilir; MainWindow icindeki bir zamanlayici, zamani gelenleri
denetleyip otomatik baslatir. Uygulama kapatilip acilsa bile bekleyen
gorevler kalir (persist).
"""
import datetime as dt
import logging
import os
import sqlite3

from app.utils.paths import data_dir

DB_PATH = os.path.join(data_dir(), "scheduled_downloads.db")


class ScheduledDownloadService:
    def __init__(self, path: str | None = None):
        self.path = path or DB_PATH
        self.log = logging.getLogger("yt_ara.scheduler")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scheduled (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        video_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        channel_title TEXT,
                        quality TEXT NOT NULL,
                        download_dir TEXT NOT NULL,
                        run_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
        except sqlite3.Error as exc:
            self.log.warning("Zamanlama db acilamadi: %s", exc)

    def add(self, video_id: str, title: str, url: str, channel_title: str,
            quality: str, download_dir: str, run_at: dt.datetime) -> int:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO scheduled "
                    "(video_id, title, url, channel_title, quality, download_dir, "
                    "run_at, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'bekliyor', ?)",
                    (video_id, title, url, channel_title, quality, download_dir,
                     run_at.isoformat(timespec="seconds"),
                     dt.datetime.now().isoformat(timespec="seconds")))
                return int(cur.lastrowid)
        except sqlite3.Error as exc:
            self.log.warning("Zamanlanmis gorev eklenemedi: %s", exc)
            return 0

    def due(self, now: dt.datetime | None = None) -> list[dict]:
        """Zamani gelmis (run_at <= now), henuz calismamis gorevleri dondurur."""
        now = now or dt.datetime.now()
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM scheduled WHERE status='bekliyor' AND run_at<=? "
                    "ORDER BY run_at ASC",
                    (now.isoformat(timespec="seconds"),)
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            self.log.warning("Zamanlanmis gorevler okunamadi: %s", exc)
            return []

    def pending(self) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM scheduled WHERE status='bekliyor' ORDER BY run_at ASC"
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            self.log.warning("Zamanlanmis gorevler okunamadi: %s", exc)
            return []

    def mark_status(self, task_id: int, status: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute("UPDATE scheduled SET status=? WHERE id=?", (status, task_id))
        except sqlite3.Error as exc:
            self.log.warning("Zamanlanmis gorev guncellenemedi: %s", exc)

    def delete(self, task_id: int) -> None:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM scheduled WHERE id=?", (task_id,))
        except sqlite3.Error as exc:
            self.log.warning("Zamanlanmis gorev silinemedi: %s", exc)
