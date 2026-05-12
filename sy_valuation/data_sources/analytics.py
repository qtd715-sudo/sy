"""방문자 분석 로그 (자체 SQLite, 무료).

테이블 `visits`:
  ts        REAL   요청 시각 (epoch)
  path      TEXT   /#/dashboard, /api/valuation 등
  ip        TEXT   클라이언트 IP (X-Forwarded-For 우선, 앞 3옥텟만 저장 시 옵션)
  ua        TEXT   User-Agent
  ref       TEXT   Referer
  status    INT    HTTP 응답 코드
  duration  REAL   처리 시간(s)

User-Agent 에서 디바이스/OS 추출은 간단 정규식 (외부 lib 없이).

기본 URL prefix 필터:
- 정적 파일 (.css/.js/.ico/.png) 와 /api/admin/* 는 로깅에서 제외 가능 (옵션)
"""

from __future__ import annotations
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "analytics.db"


class Analytics:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else _DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # IP 익명화 옵션: 환경변수 ANALYTICS_ANON_IP=1 이면 마지막 옥텟 0 으로
        self.anon_ip = os.environ.get("ANALYTICS_ANON_IP") in ("1", "true", "True")
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=5.0, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL;")
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY,
                    ts REAL NOT NULL,
                    path TEXT NOT NULL,
                    ip TEXT,
                    ua TEXT,
                    ref TEXT,
                    status INTEGER,
                    duration REAL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits(ts)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_visits_path ON visits(path)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_visits_ip ON visits(ip)")

    def _normalize_ip(self, ip: str) -> str:
        if not ip:
            return ""
        # X-Forwarded-For 는 콤마 구분 (가장 왼쪽이 원본 IP)
        ip = ip.split(",")[0].strip()
        if self.anon_ip and "." in ip:
            parts = ip.split(".")
            if len(parts) == 4:
                parts[3] = "0"
                ip = ".".join(parts)
        return ip[:64]

    def log(self, path: str, ip: str = "", ua: str = "", ref: str = "", status: int = 200, duration: float = 0):
        # 정적 자산은 제외 (트래픽 증폭 방지)
        if path.endswith((".css", ".js", ".ico", ".png", ".jpg", ".svg", ".woff", ".woff2")):
            return
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO visits (ts, path, ip, ua, ref, status, duration) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (time.time(), path[:200], self._normalize_ip(ip),
                     (ua or "")[:300], (ref or "")[:200], int(status), float(duration)),
                )
        except Exception:
            pass

    # -------- 디바이스/OS 파싱 --------

    @staticmethod
    def parse_ua(ua: str) -> dict[str, str]:
        ua = ua or ""
        device = "Desktop"
        os_name = "Unknown"
        browser = "Unknown"
        if re.search(r"iPhone|iPod", ua, re.I): device = "Mobile (iPhone)"
        elif "iPad" in ua: device = "Tablet (iPad)"
        elif "Android" in ua: device = "Mobile (Android)" if "Mobile" in ua else "Tablet (Android)"
        # OS
        if "Windows" in ua: os_name = "Windows"
        elif "Mac OS X" in ua or "Macintosh" in ua: os_name = "macOS"
        elif "Android" in ua: os_name = "Android"
        elif "iPhone" in ua or "iPad" in ua: os_name = "iOS"
        elif "Linux" in ua: os_name = "Linux"
        # Browser
        if "Edg/" in ua: browser = "Edge"
        elif "Chrome/" in ua and "Chromium" not in ua and "Edg" not in ua: browser = "Chrome"
        elif "Firefox/" in ua: browser = "Firefox"
        elif "Safari/" in ua and "Chrome" not in ua: browser = "Safari"
        elif "curl" in ua.lower(): browser = "curl"
        return {"device": device, "os": os_name, "browser": browser}

    # -------- 통계 --------

    def summary(self, hours: int = 24) -> dict[str, Any]:
        cutoff = time.time() - hours * 3600
        with self._conn() as c:
            # 총 방문, 유니크 IP, 유니크 패스
            row = c.execute(
                "SELECT COUNT(*), COUNT(DISTINCT ip), COUNT(DISTINCT path) FROM visits WHERE ts >= ?",
                (cutoff,),
            ).fetchone()
            total, uniq_ip, uniq_path = row
            # top 페이지
            top_paths = c.execute(
                "SELECT path, COUNT(*) c FROM visits WHERE ts >= ? GROUP BY path ORDER BY c DESC LIMIT 10",
                (cutoff,),
            ).fetchall()
            # top IP
            top_ips = c.execute(
                "SELECT ip, COUNT(*) c FROM visits WHERE ts >= ? AND ip != '' GROUP BY ip ORDER BY c DESC LIMIT 10",
                (cutoff,),
            ).fetchall()
            # UA 샘플
            ua_rows = c.execute(
                "SELECT ua FROM visits WHERE ts >= ? AND ua != ''", (cutoff,),
            ).fetchall()
            # 시간대별 분포 (시간:방문수)
            hour_rows = c.execute(
                "SELECT CAST(strftime('%H', ts, 'unixepoch', '+9 hours') AS INTEGER) h, COUNT(*) c "
                "FROM visits WHERE ts >= ? GROUP BY h ORDER BY h",
                (cutoff,),
            ).fetchall()
            # 일별 분포 (지난 7일)
            day_rows = c.execute(
                "SELECT date(ts, 'unixepoch', '+9 hours') d, COUNT(*) c, COUNT(DISTINCT ip) u "
                "FROM visits WHERE ts >= ? GROUP BY d ORDER BY d",
                (time.time() - 7 * 86400,),
            ).fetchall()

        # UA 파싱 집계
        devices = Counter()
        oses = Counter()
        browsers = Counter()
        for (ua,) in ua_rows:
            p = self.parse_ua(ua)
            devices[p["device"]] += 1
            oses[p["os"]] += 1
            browsers[p["browser"]] += 1

        return {
            "window_hours": hours,
            "total": total,
            "unique_ips": uniq_ip,
            "unique_paths": uniq_path,
            "top_paths": [{"path": p, "count": c} for p, c in top_paths],
            "top_ips": [{"ip": i, "count": c} for i, c in top_ips],
            "devices": dict(devices.most_common(10)),
            "os": dict(oses.most_common(10)),
            "browsers": dict(browsers.most_common(10)),
            "hourly_kst": [{"hour": h, "count": c} for h, c in hour_rows],
            "daily": [{"date": d, "count": c, "unique": u} for d, c, u in day_rows],
        }

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT ts, path, ip, ua, ref, status, duration "
                "FROM visits ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        from datetime import datetime, timezone, timedelta
        kst = timezone(timedelta(hours=9))
        for ts, path, ip, ua, ref, status, dur in rows:
            p = self.parse_ua(ua or "")
            out.append({
                "ts": datetime.fromtimestamp(ts, tz=kst).strftime("%m-%d %H:%M:%S"),
                "ts_epoch": ts,
                "path": path,
                "ip": ip,
                "device": p["device"],
                "os": p["os"],
                "browser": p["browser"],
                "ref": ref,
                "status": status,
                "duration_ms": int(dur * 1000) if dur else 0,
            })
        return out

    def purge_old(self, keep_days: int = 90) -> int:
        cutoff = time.time() - keep_days * 86400
        with self._conn() as c:
            cur = c.execute("DELETE FROM visits WHERE ts < ?", (cutoff,))
            return cur.rowcount


_GLOBAL: Analytics | None = None


def get_analytics() -> Analytics:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Analytics()
    return _GLOBAL
