"""SQLite 기반 영속 캐시. 서버 재시작에도 데이터 유지.

테이블:
  kv (key TEXT PK, value BLOB, expires_at REAL, source TEXT, fetched_at REAL)

주 사용처:
- 뉴스 토픽 응답 (24h TTL)
- 시세 스냅샷 (5분 TTL, 장중)
- DART corp_codes (영구)
- 사용자 워치리스트 등 추후 확장
"""

from __future__ import annotations
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "cache.db"


class Cache:
    """단일 영속 SQLite 커넥션 + 락.

    이전 구현은 get/set 매 호출마다 ``sqlite3.connect`` + ``PRAGMA journal_mode=WAL``
    를 실행했다. API 요청 1건당 캐시 접근이 수 차례 일어나므로 커넥션 셋업 비용이
    누적돼 응답 지연의 큰 부분을 차지했다. 커넥션을 1개로 재사용하고 autocommit
    모드(isolation_level=None) + 락으로 스레드 안전성을 확보한다.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else _DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        # 영속 커넥션 1개를 재사용. isolation_level=None → autocommit(별도 commit 불필요).
        if self._db is None:
            c = sqlite3.connect(
                self.path, timeout=5.0, check_same_thread=False, isolation_level=None,
            )
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("PRAGMA synchronous=NORMAL;")
            self._db = c
        return self._db

    def _init_db(self) -> None:
        with self._lock:
            c = self._conn()
            c.execute("""
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value BLOB NOT NULL,
                    expires_at REAL,
                    source TEXT,
                    fetched_at REAL NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv(expires_at)")

    def get(self, key: str) -> tuple[Any, dict[str, Any]] | None:
        """리턴: (value, meta) 또는 None. meta 에 fetched_at, source 포함."""
        now = time.time()
        with self._lock:
            row = self._conn().execute(
                "SELECT value, expires_at, source, fetched_at FROM kv WHERE key=?", (key,)
            ).fetchone()
        if not row:
            return None
        value_blob, expires_at, source, fetched_at = row
        if expires_at and expires_at < now:
            return None
        try:
            value = json.loads(value_blob.decode("utf-8") if isinstance(value_blob, bytes) else value_blob)
        except Exception:
            return None
        return value, {
            "source": source or "",
            "fetched_at": fetched_at,
            "age_sec": int(now - fetched_at) if fetched_at else 0,
        }

    def set(self, key: str, value: Any, ttl_sec: int | None = 3600, source: str = "") -> None:
        now = time.time()
        expires = now + ttl_sec if ttl_sec else None
        blob = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        with self._lock:
            self._conn().execute(
                "INSERT OR REPLACE INTO kv (key, value, expires_at, source, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (key, blob, expires, source, now),
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn().execute("DELETE FROM kv WHERE key=?", (key,))

    def purge_expired(self) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn().execute("DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
            return cur.rowcount

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT key FROM kv WHERE key LIKE ? ORDER BY key", (f"{prefix}%",)
            ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            c = self._conn()
            total = c.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
            expired = c.execute(
                "SELECT COUNT(*) FROM kv WHERE expires_at IS NOT NULL AND expires_at < ?",
                (time.time(),),
            ).fetchone()[0]
            latest = c.execute("SELECT MAX(fetched_at) FROM kv").fetchone()[0]
        return {"total": total, "expired": expired, "latest_fetch": latest}


_GLOBAL: Cache | None = None


def get_cache() -> Cache:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Cache()
    return _GLOBAL
