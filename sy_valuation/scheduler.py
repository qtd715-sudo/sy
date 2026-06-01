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
        """핫티커 + 모든 샘플 종목 시세 prefetch (스크리너 즉시 응답용)."""
        import concurrent.futures
        from .data_sources.cache import get_cache
        cache = get_cache()
        # 샘플 종목 모두 + 핫티커
        sample_tks = [c["ticker"] for c in self.app.repo.all()]
        all_tks = list(dict.fromkeys(HOT_TICKERS + sample_tks))

        def fetch_one(tk: str):
            try:
                q = self.app.price.quote(tk)
                if q:
                    cache.set(f"price:{tk}", q.to_dict(), ttl_sec=900, source=q.source)
                    return 1
            except Exception:
                pass
            return 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            ok = sum(ex.map(fetch_one, all_tks))
        log.info("prefetched tickers: %d/%d", ok, len(all_tks))
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

    def _job_dart_corpcodes(self) -> int:
        """DART_API_KEY 가 있으면 corp_code 매핑 갱신 (분기 1회면 충분)."""
        try:
            if not self.app.dart.enabled:
                return 0
            mapping = self.app.dart.load_corp_codes(force=True)
            log.info("refreshed DART corp_codes: %d entries", len(mapping))
            return len(mapping)
        except Exception as e:
            log.warning("DART corp_codes refresh failed: %s", e)
            return 0

    def _job_dart_universe(self) -> int:
        """KRX 전 상장사 섹터/시장 매핑 빌더 (주 1회).

        DART /api/company.json 을 corp_codes 약 2,500건에 대해 호출.
        5-worker 병렬, 약 3~4분 소요. 결과는 data/cache/dart_universe.json 에 저장.
        피어 매칭용 universe 확장에 사용.

        부팅 시 호출되면 캐시 파일 mtime 이 7일 이내일 때 스킵 — 서버 재시작마다
        3~4분 빈 호출을 막기 위함.
        """
        try:
            if not self.app.dart.enabled:
                return 0
            from pathlib import Path
            cache_path = Path(__file__).resolve().parent / "data" / "cache" / "dart_universe.json"
            if cache_path.exists():
                age_sec = time.time() - cache_path.stat().st_mtime
                if age_sec < 604800:  # 7일 이내면 재빌드 스킵
                    cached = self.app.dart.load_universe_cache()
                    log.info("DART universe cache fresh (%.1fh, %d entries) — skip rebuild",
                             age_sec / 3600, len(cached))
                    return len(cached)
            items = self.app.dart.build_listed_universe(max_workers=5)
            log.info("refreshed DART universe: %d listed companies", len(items))
            return len(items)
        except Exception as e:
            log.warning("DART universe refresh failed: %s", e)
            return 0

    def _job_full_screener(self) -> int:
        """전종목 저평가 스크리너 배치.

        기본 비활성 — 운영(Render 무료)은 GitHub Actions 가 만든 캐시 파일을 서빙만 한다.
        (무료 플랜은 15분 미사용 시 잠들고 재시작 시 디스크가 휘발돼 36분 배치 완주 불가.)
        서버가 직접 배치를 돌리려면 SY_ENABLE_SCREENER_BATCH=1 로 명시 활성화.
        """
        if os.environ.get("SY_ENABLE_SCREENER_BATCH") not in ("1", "true", "True"):
            return 0
        try:
            from .recommender import full_screener
            age = full_screener.cache_age_sec()
            if age is not None and age < 14400:  # 4시간 이내면 스킵
                log.info("full screener cache fresh (%.1fh) — skip rebuild", age / 3600)
                return 0
            summary = self.app.build_full_screener(max_workers=10)
            log.info("full screener built: %s", summary)
            return summary.get("count_sy", 0)
        except Exception as e:
            log.warning("full screener build failed: %s", e)
            return 0

    # -------- loop --------

    SCHEDULE = [
        ("news",      3600,   "_job_news"),             # 1시간
        ("market",    300,    "_job_market"),           # 5분
        ("hot",       300,    "_job_hot_tickers"),      # 5분 — 샘플+핫 종목 가격 (스크리너용)
        ("krx_univ",  86400,  "_job_krx_universe"),     # 24시간 — 코스피/코스닥 전종목 (Naver)
        ("dart_cc",   604800, "_job_dart_corpcodes"),   # 7일 — DART corp_code 매핑
        ("dart_univ", 604800, "_job_dart_universe"),    # 7일 — KRX 전종목 섹터/시장 (피어 매칭용)
        ("screener",  14400,  "_job_full_screener"),    # 4시간 — 전종목 저평가 스크리너 배치
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
