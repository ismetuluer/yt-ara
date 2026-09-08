"""Indirme gecmisi (SQLite).

Her kayit: video basligi, video URL, dosya yolu, indirme tarihi, durum.
"""
import datetime as dt
import logging
import os
import sqlite3

from app.utils.paths import data_dir

DB_PATH = os.path.join(data_dir(), "download_history.db")


class DownloadHistory:
    def __init__(self, path: str | None = None):
        self.path = path or DB_PATH
        self.log = logging.getLogger("yt_ara.history")
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
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        file_path TEXT,
                        downloaded_at TEXT NOT NULL,
                        status TEXT NOT NULL
                    )
                """)
        except sqlite3.Error as exc:
            self.log.warning("Gecmis db acilamadi: %s", exc)

    def add(self, title: str, url: str, file_path: str | None, status: str) -> int:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO downloads (title, url, file_path, downloaded_at, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (title, url, file_path,
                     dt.datetime.now().isoformat(timespec="seconds"), status))
                return int(cur.lastrowid)
        except sqlite3.Error as exc:
            self.log.warning("Gecmis kaydi eklenemedi: %s", exc)
            return 0

    def update_status(self, record_id: int, status: str, file_path: str | None = None) -> None:
        try:
            with self._connect() as conn:
                if file_path is not None:
                    conn.execute(
                        "UPDATE downloads SET status=?, file_path=? WHERE id=?",
                        (status, file_path, record_id))
                else:
                    conn.execute(
                        "UPDATE downloads SET status=? WHERE id=?",
                        (status, record_id))
        except sqlite3.Error as exc:
            self.log.warning("Gecmis guncellenemedi: %s", exc)

    def completed_urls(self) -> set[str]:
        """Basariyla indirilmis video URL'lerini dondurur (vurgulama icin)."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT url FROM downloads WHERE status='tamam'"
                ).fetchall()
                return {r["url"] for r in rows}
        except sqlite3.Error as exc:
            self.log.warning("Gecmis okunamadi: %s", exc)
            return set()

    def file_path_for(self, url: str) -> str | None:
        """Verilen video icin en son basarili indirmenin dosya yolunu dondurur."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT file_path FROM downloads WHERE url=? AND status='tamam' "
                    "AND file_path IS NOT NULL ORDER BY id DESC LIMIT 1",
                    (url,)
                ).fetchone()
                return row["file_path"] if row else None
        except sqlite3.Error as exc:
            self.log.warning("Dosya yolu okunamadi: %s", exc)
            return None

    def mark_stale_downloading_as_failed(self) -> int:
        """"indiriliyor" durumunda kalmis kayitlari "hata" yapar.

        Bu durum yalnizca uygulama indirme sirasinda kapatilirsa/coktuyse
        olusur (calisan bir worker bir daha oncekinden devam edemez); bu
        yuzden her baslangicta bir kez cagrilir -- aksi halde gecmis
        ekraninda hicbir zaman bitmeyecek bir "indiriliyor" kaydi kalirdi."""
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE downloads SET status='hata' WHERE status='indiriliyor'")
                return cur.rowcount
        except sqlite3.Error as exc:
            self.log.warning("Yarim kalan kayitlar guncellenemedi: %s", exc)
            return 0

    def delete(self, record_id: int) -> None:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM downloads WHERE id=?", (record_id,))
        except sqlite3.Error as exc:
            self.log.warning("Gecmis kaydi silinemedi: %s", exc)

    def recent(self, limit: int = 50) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            self.log.warning("Gecmis okunamadi: %s", exc)
            return []
