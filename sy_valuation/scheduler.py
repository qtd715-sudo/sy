"""백그라운드 prefetch 스케줄러.

서버 시작 시 daemon 스레드 한 개를 띄워 주기적으로:
- 뉴스 29개 토픽 (1시간마다)
- 원자재/지수/환율 (5분마다)
- 핵심 종목 시세 (1시간마다)

캐시는 SQLite (data/cache.db) 에 영속. 서버 재시작에도 유지.
환경변수로 비활성화 가능: SY_DISABLE_SCHEDULER=1
"""

from __future__ import annotations
import logging
import os
import threading
import time
from typing import Any

log = logging.getLogger("sy.scheduler")


# 핵심 종목 (자주 조회되는 KR/US 큰 종목)
HOT_TICKERS = [
    "005930", "000660", "035420", "035720", "005380", "000270", "207940",
    "373220", "066570", "012330", "017670", "030200", "105560", "055550",
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    "SPY", "QQQ", "VOO",
]


class Scheduler:
    def __init__(self, app):
        self.app = app
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_runs: dict[str, float] = {}

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("SY_DISABLE_SCHEDULER") not in ("1", "true", "True")

    def start(self) -> None:
        if not self.enabled():
            log.info("scheduler disabled by env")
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="sy-prefetch", daemon=True)
        self._thread.start()
        log.info("scheduler started")

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled(),
            "alive": bool(self._thread and self._thread.is_alive()),
            "last_runs": dict(self._last_runs),
        }

    # -------- jobs --------

    def _job_news(self) -> int:
        try:
            self.app.news.all_topics(per_topic=10, force_refresh=True)
            self.app.news.all_market_topics(per_topic=10)
            log.info("prefetched news topics + market topics")
            return 1
        except Exception as e:
            log.warning("news prefetch failed: %s", e)
            return 0

    def _job_market(self) -> int:
        from .data_sources.cache import get_cache
        cache = get_cache()
        try:
            quotes = self.app.commodities.watchlist_groups()
            cache.set(
                "market:groups",
                {g: [q.to_dict() for q in qs] for g, qs in quotes.items()},
                ttl_sec=600,
                source="yahoo",
            )
            log.info("prefetched commodity groups")
            return 1
        except Exception as e:
            log.warning("market prefetch failed: %s", e)
            return 0

    def _job_hot_tickers(self) -> int:
        from .data_sources.cache import get_cache
        cache = get_cache()
        ok = 0
        for tk in HOT_TICKERS:
            try:
                q = self.app.price.quote(tk)
                if q:
                    cache.set(f"price:{tk}", q.to_dict(), ttl_sec=900, source=q.source)
                    ok += 1
            except Exception:
                continue
        log.info("prefetched hot tickers: %d/%d", ok, len(HOT_TICKERS))
        return ok

    def _job_krx_universe(self) -> int:
        try:
            from .data_sources.krx_universe import load_universe
            items = load_universe(force_refresh=True)
            # repository 에도 즉시 반영
            self.app.repo.load()
            log.info("refreshed KRX universe: %d tickers", len(items))
            return len(items)
        except Exception as e:
            log.warning("KRX universe refresh failed: %s", e)
            return 0

    # -------- loop --------

    SCHEDULE = [
        ("news",     3600,   "_job_news"),         # 1시간
        ("market",   300,    "_job_market"),       # 5분
        ("hot",      1800,   "_job_hot_tickers"),  # 30분
        ("krx_univ", 86400,  "_job_krx_universe"), # 24시간 — 코스피/코스닥 전종목
    ]

    def _loop(self) -> None:
        # 서버 부팅 후 5초 뒤 첫 실행 (포트 바인딩 후)
        time.sleep(5)
        # 부팅 직후 모든 잡을 병렬로 실행 (서로 의존성 없음)
        boot_threads = []
        for name, _interval, jobname in self.SCHEDULE:
            self._last_runs[name] = time.time()  # 표시는 시작 시각
            t = threading.Thread(
                target=getattr(self, jobname),
                name=f"sy-boot-{name}",
                daemon=True,
            )
            t.start()
            boot_threads.append(t)
        # 백그라운드 잡들이 알아서 끝나면 됨 — 메인 루프는 계속
        while not self._stop.is_set():
            now = time.time()
            for name, interval, jobname in self.SCHEDULE:
                last = self._last_runs.get(name, 0)
                if now - last >= interval:
                    threading.Thread(
                        target=getattr(self, jobname),
                        name=f"sy-{name}",
                        daemon=True,
                    ).start()
                    self._last_runs[name] = time.time()
            self._stop.wait(30)
