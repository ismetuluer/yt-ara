"""Izleme listesi (SQLite).

Belirli kanallar periyodik olarak taranir; yeni video bulunursa (ve
varsa anahtar kelimeyle eslesirse) otomatik indirilir. Hangi videolarin
zaten degerlendirildigi (`watchlist_seen`) tutulur ki ayni video tekrar
tekrar bulunmus/indirilmis sayilmasin.
"""
import datetime as dt
import logging
import os
import sqlite3

from app.utils.paths import data_dir

DB_PATH = os.path.join(data_dir(), "watchlist.db")


def _turkish_fold(text: str) -> str:
    return (text.casefold()
            .replace("i̇", "i").replace("ı", "i")
            .replace("ş", "s").replace("ç", "c")
            .replace("ğ", "g").replace("ü", "u").replace("ö", "o"))


def keyword_matches(title: str, keyword: str) -> bool:
    """Anahtar kelime baslikta herhangi bir yerde geciyor mu (harf duyarsiz)."""
    if not keyword:
        return True
    return _turkish_fold(keyword) in _turkish_fold(title)


class WatchlistService:
    def __init__(self, path: str | None = None):
        self.path = path or DB_PATH
        self.log = logging.getLogger("yt_ara.watchlist")
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
                    CREATE TABLE IF NOT EXISTS watches (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_url TEXT NOT NULL,
                        channel_title TEXT,
                        keyword TEXT,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        last_checked_at TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS watchlist_seen (
                        watch_id INTEGER NOT NULL,
                        video_id TEXT NOT NULL,
                        title TEXT,
                        url TEXT,
                        found_at TEXT NOT NULL,
                        matched INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (watch_id, video_id)
                    )
                """)
                # Eski veritabanlarinda "matched" sutunu olmayabilir (bkz.
                # "Bulunan Videolar" listesi anahtar kelimeyle eslesmeyenleri
                # de gosteriyordu hatasinin duzeltilmesi); sutun yoksa eklenir.
                cols = {row[1] for row in conn.execute("PRAGMA table_info(watchlist_seen)")}
                if "matched" not in cols:
                    conn.execute(
                        "ALTER TABLE watchlist_seen ADD COLUMN matched INTEGER NOT NULL DEFAULT 0")
        except sqlite3.Error as exc:
            self.log.warning("Izleme listesi db acilamadi: %s", exc)

    # ------------------------------------------------------------ izleme girisleri
    def add(self, channel_url: str, channel_title: str, keyword: str = "") -> int:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO watches (channel_url, channel_title, keyword, active, "
                    "created_at) VALUES (?, ?, ?, 1, ?)",
                    (channel_url, channel_title, keyword.strip(),
                     dt.datetime.now().isoformat(timespec="seconds")))
                return int(cur.lastrowid)
        except sqlite3.Error as exc:
            self.log.warning("Izleme eklenemedi: %s", exc)
            return 0

    def all(self) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM watches ORDER BY id DESC").fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            self.log.warning("Izleme listesi okunamadi: %s", exc)
            return []

    def active(self) -> list[dict]:
        return [w for w in self.all() if w.get("active")]

    def set_active(self, watch_id: int, active: bool) -> None:
        try:
            with self._connect() as conn:
                conn.execute("UPDATE watches SET active=? WHERE id=?",
                            (1 if active else 0, watch_id))
        except sqlite3.Error as exc:
            self.log.warning("Izleme guncellenemedi: %s", exc)

    def delete(self, watch_id: int) -> None:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM watches WHERE id=?", (watch_id,))
                conn.execute("DELETE FROM watchlist_seen WHERE watch_id=?", (watch_id,))
        except sqlite3.Error as exc:
            self.log.warning("Izleme silinemedi: %s", exc)

    def mark_checked(self, watch_id: int) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE watches SET last_checked_at=? WHERE id=?",
                    (dt.datetime.now().isoformat(timespec="seconds"), watch_id))
        except sqlite3.Error as exc:
            self.log.warning("Izleme guncellenemedi: %s", exc)

    # ------------------------------------------------------------ gorulen videolar
    def seen_ids(self, watch_id: int) -> set[str]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT video_id FROM watchlist_seen WHERE watch_id=?", (watch_id,)
                ).fetchall()
                return {r["video_id"] for r in rows}
        except sqlite3.Error as exc:
            self.log.warning("Gorulen videolar okunamadi: %s", exc)
            return set()

    def mark_seen(self, watch_id: int, video_id: str, title: str, url: str,
                  matched: bool = False) -> None:
        """`matched=True`: video anahtar kelimeyle eslesip indirmeye alindi
        ("Bulunan Videolar" listesinde gosterilir). `matched=False`:
        yalnizca bir daha "yeni" sayilmamasi icin gorulmus isaretlenir
        (ornegin izlemeye yeni alinan kanalin gecmis videolari, veya
        anahtar kelimeyle eslesmeyen videolar) -- listede GORUNMEZ."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO watchlist_seen "
                    "(watch_id, video_id, title, url, found_at, matched) VALUES (?, ?, ?, ?, ?, ?)",
                    (watch_id, video_id, title, url,
                     dt.datetime.now().isoformat(timespec="seconds"), 1 if matched else 0))
        except sqlite3.Error as exc:
            self.log.warning("Video gorulmus olarak isaretlenemedi: %s", exc)

    def recent_found(self, limit: int = 100) -> list[dict]:
        """Bulunan (anahtar kelimeyle ESLESEN) videolarin, en yeniden
        eskiye, kanal adiyla birlikte listesi."""
        try:
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT s.video_id, s.title, s.url, s.found_at, w.channel_title, w.keyword
                    FROM watchlist_seen s JOIN watches w ON w.id = s.watch_id
                    WHERE s.matched = 1
                    ORDER BY s.found_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            self.log.warning("Bulunanlar okunamadi: %s", exc)
            return []
