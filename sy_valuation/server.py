"""HTTP API + 정적파일 서버 (Python 표준 라이브러리만 사용).

엔드포인트:
  GET  /                              → static/index.html
  GET  /api/health                    → 시스템 상태
  GET  /api/tickers                   → 전체 티커 DB
  GET  /api/search?q=&limit=          → 자동완성 (이름/코드 멀티매치)
  GET  /api/valuation?q=              → 가치평가 (샘플→없으면 live)
  GET  /api/undervalued?n=            → 저평가 Top N
  GET  /api/recommend?q=              → 투자 추천
  GET  /api/news?q=&n=                → 뉴스 검색
  GET  /api/market-news?n=            → 시장 뉴스 + 감성
  GET  /api/news/topics               → 카테고리별 뉴스 묶음
  GET  /api/news/topic?topic=&n=      → 단일 토픽 뉴스
  GET  /api/commodities               → 원물/지수 (그룹화)
  GET  /api/commodities/flat          → 전체 평탄 리스트
  GET  /api/price?q=                  → 실시간 시세
  GET  /api/history?q=                → 1년 종가 히스토리
"""

from __future__ import annotations
import base64
import gzip
import json
import mimetypes
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .data_sources import (
    FinancialsRepository, NewsConnector, CommodityConnector, PriceConnector, DartConnector,
    LiveFinancials, NaverFundamentals, NaverFinancials,
)
from .data_sources.cache import get_cache
from .data_sources.analytics import get_analytics
from .valuation.engine import value_company
from .valuation.sy_method import evaluate_sy
from .valuation.sy_builder import build_inputs_from_raw
from .recommender import find_undervalued, recommend_investment
from .scheduler import Scheduler


_ROOT = Path(__file__).resolve().parent
_STATIC = _ROOT / "static"


class App:
    def __init__(self):
        self.repo = FinancialsRepository()
        self.news = NewsConnector()
        self.commodities = CommodityConnector()
        self.price = PriceConnector()
        self.dart = DartConnector()
        self.live = LiveFinancials()
        self.naver = NaverFundamentals()
        self.naver_fin = NaverFinancials()
        self.scheduler = Scheduler(self)

    # ---------- API handlers ----------

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "dart_enabled": self.dart.enabled,
            "naver_news_enabled": bool(self.news.naver_id),
            "tickers_loaded": len(self.repo.list_tickers()),
            "samples_loaded": len(self.repo.all()),
            "scheduler": self.scheduler.status(),
            "cache": get_cache().stats(),
            "news_cache": self.news.cache_status(),
        }

    def tickers(self) -> list[dict[str, str]]:
        return self.repo.list_tickers()

    def search(self, q: str, limit: int = 10) -> list[dict[str, str]]:
        return self.repo.search(q, limit=limit)

    def _resolve_financials(self, query: str):
        """샘플 → DART (키있으면) → Naver 재무제표 → Naver 기본 → Yahoo → None."""
        f = self.repo.get_or_build_financials(
            query,
            live=self.live, naver=self.naver,
            dart=self.dart, naver_fin=self.naver_fin,
        )
        if not f:
            return None, None, None
        # 실시간 가격으로 최신화
        quote_info = None
        try:
            q = self.price.quote(f.ticker)
            if q and q.price > 0:
                f.current_price = q.price
                quote_info = q.to_dict()
        except Exception:
            pass
        meta = self.repo.get_ticker_meta(f.ticker) or {}
        return f, meta, quote_info

    def valuation(self, query: str) -> dict[str, Any]:
        f, meta, quote = self._resolve_financials(query)
        if not f:
            suggestions = self.repo.search(query, limit=5)
            return {
                "error": f"종목을 찾을 수 없습니다: {query}",
                "suggestions": suggestions,
            }
        v = value_company(f)
        return {
            "financials": {
                "ticker": f.ticker, "name": f.name, "sector": f.sector,
                "exchange": meta.get("exchange", ""),
                "asset": meta.get("asset", "stock"),
                "current_price": f.current_price, "eps": f.eps, "bps": f.bps,
                "roe": f.roe, "growth_rate": f.growth_rate,
                "per_now": round(f.current_price / f.eps, 2) if f.eps > 0 else None,
                "pbr_now": round(f.current_price / f.bps, 2) if f.bps > 0 else None,
                "sector_per": f.sector_per, "sector_pbr": f.sector_pbr,
                "ebitda": f.ebitda, "fcf": f.fcf, "net_debt": f.net_debt,
                "shares_outstanding": f.shares_outstanding,
            },
            "valuation": v.to_dict(),
            "live": f.ticker not in self.repo._by_ticker,
            "quote": quote,
        }

    def _refresh_prices(self, tickers: list[str]) -> dict[str, float]:
        """캐시만 읽기 — 즉시 응답.
        백그라운드 스케줄러가 모든 샘플 종목 가격을 5분/30분 주기로 prefetch.
        캐시에 없는 종목은 정적 샘플 가격 사용 (첫 부팅 후 1~2분만 발생)."""
        cache = get_cache()
        out: dict[str, float] = {}
        for t in tickers:
            cached = cache.get(f"price:{t}")
            if cached:
                data, _ = cached
                if data.get("price"):
                    out[t] = float(data["price"])
        return out

    def undervalued(self, n: int = 10, strict: bool = True) -> list[dict[str, Any]]:
        financials = self.repo.all_financials()
        prices = self._refresh_prices([f.ticker for f in financials])
        for f in financials:
            if f.ticker in prices:
                f.current_price = prices[f.ticker]
        results = find_undervalued(financials, top_n=n, strict=strict)
        cache = get_cache()
        rows = []
        for r in results:
            d = r.to_dict()
            ticker = d.get("valuation", {}).get("ticker") or d.get("ticker")
            cached = cache.get(f"price:{ticker}") if ticker else None
            d["price_as_of"] = cached[1].get("fetched_at") if cached else None
            rows.append(d)
        return rows

    def sy_evaluate(self, query: str) -> dict[str, Any]:
        raw = self.repo.find(query)
        if not raw:
            # 샘플에 없으면 Naver 실시간 데이터로 raw 빌드 시도
            meta = self.repo.get_ticker_meta(query)
            if meta and meta["ticker"].isdigit() and len(meta["ticker"]) == 6:
                info = self.naver.fetch(meta["ticker"])
                if info:
                    from .data_sources.naver_fundamentals import _to_won
                    price = _to_won(info.get("lastClosePrice", ""))
                    eps = _to_won(info.get("eps", ""))
                    bps = _to_won(info.get("bps", ""))
                    mcap = _to_won(info.get("marketValue", ""))
                    div = _to_won(info.get("dividend", ""))
                    shares = mcap / price if price > 0 else 0
                    if price > 0 and shares > 0:
                        raw = {
                            "ticker": meta["ticker"],
                            "name": meta["name"],
                            "sector": meta.get("sector") or "기타",
                            "current_price": price,
                            "shares_outstanding": shares,
                            "eps": eps, "bps": bps,
                            "sps": 0, "dps": div,
                            "roe": (eps / bps) if bps > 0 else 0.0,
                            "revenue": 0, "operating_income": 0,
                            "net_income": eps * shares if eps > 0 else 0,
                            "ebitda": 0, "fcf": 0, "net_debt": 0,
                            "growth_rate": 0.05,
                            "market_cap": mcap,
                            "_live": True,
                        }
            if not raw:
                return {
                    "error": f"종목을 찾을 수 없습니다: {query}",
                    "suggestions": self.repo.search(query, limit=5),
                    "hint": "Naver Finance에서도 데이터를 가져오지 못했습니다.",
                }
        sectors = self.repo.sector_table()
        sector_mults = sectors.get(raw.get("sector", ""), {})
        try:
            q = self.price.quote(raw["ticker"])
            if q and q.price > 0 and raw.get("shares_outstanding"):
                raw = dict(raw)
                raw["current_price"] = q.price
                if not raw.get("market_cap"):
                    raw["market_cap"] = q.price * raw["shares_outstanding"]
        except Exception:
            pass
        universe = self.repo.all()
        inp = build_inputs_from_raw(raw, sector_mults, universe=universe)
        result = evaluate_sy(inp)
        out = result.to_dict()
        if raw.get("_live"):
            out["notes"] = (out.get("notes") or []) + [
                "실시간 Naver 데이터 기반 — 자산/부채/EBITDA 등 일부 필드 부재로 수익가치/자산가치 부정확할 수 있음. 정확평가는 DART 키 필요."
            ]
        cached = get_cache().get(f"price:{raw['ticker']}")
        out["price_as_of"] = cached[1].get("fetched_at") if cached else None
        return out

    # SY 평가법 스크리너에서 제외할 종목 (지주사·통신사 등 자산가치/수익가치가 왜곡되는 케이스)
    SY_EXCLUDE_TICKERS = {"030200"}  # KT (자산-부채 비율 등으로 노이즈 큼)

    def sy_undervalued(self, n: int = 10) -> list[dict[str, Any]]:
        """SY 평가법 저평가 스크리너.

        ⚠ 라이브 가격은 **타겟 종목의 시총만** 갱신.
        피어 멀티플(PER/PBR/PSR/EV-EBITDA) 산정에는 sample 데이터의 정적 가격 사용.
        이유: 피어까지 라이브로 끌어올리면 멀티플이 부풀려져 적정가가 비현실적으로 커짐.
        """
        out: list[dict[str, Any]] = []
        sectors = self.repo.sector_table()
        universe = self.repo.all()  # 원본 sample — 피어 멀티플 계산용 (변하지 않음)
        prices = self._refresh_prices([raw["ticker"] for raw in universe])

        cache = get_cache()
        for raw in universe:
            if raw["ticker"] in self.SY_EXCLUDE_TICKERS:
                continue
            target = dict(raw)  # 타겟만 라이브 가격 주입
            if target["ticker"] in prices:
                target["current_price"] = prices[target["ticker"]]
                if target.get("shares_outstanding"):
                    target["market_cap"] = prices[target["ticker"]] * target["shares_outstanding"]
            sector_mults = sectors.get(target["sector"], {})
            inp = build_inputs_from_raw(target, sector_mults, universe=universe)
            r = evaluate_sy(inp)
            if r.market_cap <= 0 or r.enterprise_mid <= 0:
                continue
            if r.upside_mid <= 0:
                continue
            row = r.to_dict()
            # 가격 조회 시점 (cache fetched_at)
            cached = cache.get(f"price:{target['ticker']}")
            row["price_as_of"] = cached[1].get("fetched_at") if cached else None
            out.append(row)
        out.sort(key=lambda x: x["upside_mid"], reverse=True)
        return out[:n]

    def recommend(self, query: str) -> dict[str, Any]:
        f, meta, quote = self._resolve_financials(query)
        if not f:
            return {
                "error": f"종목을 찾을 수 없습니다: {query}",
                "suggestions": self.repo.search(query, limit=5),
            }
        v = value_company(f)
        news_items, sentiment = [], 0.0
        try:
            news_items = self.news.search(f.name, limit=10)
            sentiment = self.news.sentiment(news_items)["score"]
        except Exception:
            pass
        closes: list[float] = []
        try:
            h = self.price.history(f.ticker, range_="1y", interval="1d")
            if h:
                closes = [c for c in h.closes if c > 0]
        except Exception:
            pass
        rec = recommend_investment(f, v, news_score=sentiment, closes=closes)
        return {
            "financials": {
                "ticker": f.ticker, "name": f.name, "sector": f.sector,
                "current_price": f.current_price,
                "exchange": meta.get("exchange", ""),
                "asset": meta.get("asset", "stock"),
            },
            "valuation": v.to_dict(),
            "recommendation": rec.to_dict(),
            "news": [n.to_dict() for n in news_items[:5]],
            "quote": quote,
        }

    def news_search(self, q: str, n: int = 10) -> dict[str, Any]:
        items = self.news.search(q, limit=n)
        return {
            "query": q,
            "items": [it.to_dict() for it in items],
            "sentiment": self.news.sentiment(items),
        }

    def market_news(self, n: int = 10) -> dict[str, Any]:
        items = self.news.market_news(limit=n)
        return {
            "items": [it.to_dict() for it in items],
            "sentiment": self.news.sentiment(items),
        }

    def news_topics(self, per_topic: int = 4) -> dict[str, Any]:
        groups = self.news.all_topics(per_topic=per_topic)
        return {topic: [it.to_dict() for it in items] for topic, items in groups.items()}

    def market_topics(self, per_topic: int = 4) -> dict[str, Any]:
        groups = self.news.all_market_topics(per_topic=per_topic)
        return {topic: [it.to_dict() for it in items] for topic, items in groups.items()}

    def news_topic(self, topic: str, n: int = 10) -> dict[str, Any]:
        items = self.news.topic_news(topic, limit=n)
        return {
            "topic": topic,
            "items": [it.to_dict() for it in items],
            "sentiment": self.news.sentiment(items),
        }

    def commodity_groups(self) -> dict[str, list[dict[str, Any]]]:
        """캐시(`market:groups`) 우선 — 스케줄러가 5분마다 prefetch.
        캐시 미스 시에만 라이브 fetch (병렬, 8 workers).
        """
        cache = get_cache()
        cached = cache.get("market:groups")
        if cached:
            data, _meta = cached
            return data  # already dict[str, list[dict]]
        groups = self.commodities.watchlist_groups()
        out = {g: [q.to_dict() for q in qs] for g, qs in groups.items()}
        # 다음 호출용 즉시 캐시
        cache.set("market:groups", out, ttl_sec=600, source="yahoo")
        return out

    # Naver 연간 재무제표
    def financials_annual(self, code: str) -> dict[str, Any]:
        d = self.naver_fin.fetch(code, period="annual")
        if not d:
            return {"error": "재무제표를 가져오지 못했습니다 (한국 6자리 코드만 지원)."}
        return d

    def financials_quarter(self, code: str) -> dict[str, Any]:
        d = self.naver_fin.fetch(code, period="quarter")
        if not d:
            return {"error": "분기 재무제표 조회 실패."}
        return d

    def commodity_list(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.commodities.watchlist()]

    def price_quote(self, q: str) -> dict[str, Any]:
        quote = self.price.quote(q)
        return quote.to_dict() if quote else {"error": "조회 실패"}

    def price_history(self, q: str) -> dict[str, Any]:
        h = self.price.history(q)
        return h.to_dict() if h else {"error": "조회 실패"}


_APP: App | None = None


def get_app() -> App:
    global _APP
    if _APP is None:
        _APP = App()
    return _APP


# ---------- HTTP layer ----------

class Handler(BaseHTTPRequestHandler):
    server_version = "SYValuation/0.2"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def log_request(self, code='-', size='-'):
        # 모든 요청 로깅 (SQLite 분석)
        try:
            path = self.path.split("?")[0]
            ua = self.headers.get("User-Agent", "")
            ref = self.headers.get("Referer", "")
            ip = self.headers.get("X-Forwarded-For", "")
            if ip:
                ip = ip.split(",")[0].strip()
            else:
                ip = self.client_address[0] if self.client_address else ""
            get_analytics().log(
                path=path, ip=ip, ua=ua, ref=ref,
                status=int(code) if isinstance(code, int) else 200,
            )
        except Exception:
            pass
        # 기본 stderr 로그
        sys.stderr.write("[%s] %s %s %s\n" % (
            self.log_date_time_string(), self.requestline, str(code), str(size),
        ))

    # 응답 캐시 친화 정책: 캐시 안전한 GET 엔드포인트는 짧은 max-age + stale-while-revalidate.
    # SW SWR 와 결합해 브라우저 HTTP 캐시까지 활용 → 같은 응답 재요청은 네트워크 안 탐.
    # 사용자별 인증/사이드이펙트 엔드포인트는 'no-store' (admin/prefetch).
    _CACHE_PUBLIC = {
        "/api/ping":           "public, max-age=30",
        "/api/health":         "public, max-age=30",
        "/api/tickers":        "public, max-age=3600, stale-while-revalidate=86400",
        "/api/commodities":    "public, max-age=120, stale-while-revalidate=600",
        "/api/commodities/flat": "public, max-age=120, stale-while-revalidate=600",
        "/api/undervalued":    "public, max-age=300, stale-while-revalidate=1800",
        "/api/sy/undervalued": "public, max-age=300, stale-while-revalidate=1800",
        "/api/news/topics":    "public, max-age=600, stale-while-revalidate=3600",
        "/api/news/market":    "public, max-age=600, stale-while-revalidate=3600",
        "/api/market-news":    "public, max-age=600, stale-while-revalidate=3600",
        "/api/news/topic":     "public, max-age=600, stale-while-revalidate=3600",
        "/api/news":           "public, max-age=300, stale-while-revalidate=1800",
        "/api/search":         "public, max-age=300",
    }

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # gzip 압축: Accept-Encoding 에 gzip 있을 때만, body 1KB 이상에만.
        # 한국↔Singapore 네트워크 latency 큰 환경에서 전송 시간 60~80% 감소.
        encoding = None
        accept = (self.headers.get("Accept-Encoding") or "").lower()
        if "gzip" in accept and len(body) >= 1024:
            body = gzip.compress(body, compresslevel=6)
            encoding = "gzip"

        # 캐시 정책 결정
        path = urllib.parse.urlparse(self.path).path
        cc = self._CACHE_PUBLIC.get(path, "no-store")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cc)
        # 같은 path 라도 Accept-Encoding 따라 응답이 다르므로 캐시 키에 포함
        self.send_header("Vary", "Accept-Encoding")
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("404 Not Found".encode("utf-8"))

    def _check_admin_auth(self) -> bool:
        """ANALYTICS_USER + ANALYTICS_PASS 환경변수 등록 시 Basic Auth 강제.
        둘 다 미등록이면 누구나 접근 가능 (현재 상태)."""
        user = os.environ.get("ANALYTICS_USER", "")
        pw = os.environ.get("ANALYTICS_PASS", "")
        if not user or not pw:
            return True
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8", "ignore")
            u, p = decoded.split(":", 1)
            return u == user and p == pw
        except Exception:
            return False

    def _send_unauthorized(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="SY Analytics"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Authentication required".encode("utf-8"))

    def _client_ip(self) -> str:
        # Render/Cloudflare 등 프록시 → X-Forwarded-For 가장 왼쪽
        xff = self.headers.get("X-Forwarded-For") or ""
        if xff: return xff.split(",")[0].strip()
        return self.client_address[0] if self.client_address else ""

    def _send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            return self._not_found()
        ctype, _ = mimetypes.guess_type(str(path))
        if ctype is None:
            ctype = "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript") or ctype.endswith("json"):
            ctype += "; charset=utf-8"
        body = path.read_bytes()

        # 텍스트 자산 gzip 압축 (이미지/svg 는 효과 적거나 역효과 → skip)
        encoding = None
        accept = (self.headers.get("Accept-Encoding") or "").lower()
        is_text = (
            ctype.startswith("text/")
            or "javascript" in ctype
            or "json" in ctype
            or path.suffix == ".svg"   # SVG 는 text/xml. 큰 svg 면 효과 있음
        )
        if "gzip" in accept and is_text and len(body) >= 1024:
            body = gzip.compress(body, compresslevel=6)
            encoding = "gzip"

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Vary", "Accept-Encoding")
        if encoding:
            self.send_header("Content-Encoding", encoding)
        # sw.js: 항상 최신 (브라우저 SW 업데이트 보장)
        if path.name == "sw.js":
            self.send_header("Cache-Control", "no-cache")
        # 이미지/아이콘: 길게 캐시 (거의 변하지 않음)
        elif path.suffix in (".png", ".jpg", ".svg", ".ico", ".webp"):
            self.send_header("Cache-Control", "public, max-age=604800")  # 7일
        # JS/CSS: 1일 + must-revalidate. SW 가 어차피 가져가지만 첫 진입/SW 미등록 환경 대비
        elif path.suffix in (".css", ".js"):
            self.send_header("Cache-Control", "public, max-age=86400, must-revalidate")  # 1일
        elif path.suffix == ".html":
            self.send_header("Cache-Control", "no-cache")              # 항상 최신
        elif path.suffix == ".json":
            self.send_header("Cache-Control", "public, max-age=3600")   # manifest 등
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        path = parsed.path
        _t0 = time.time()
        _status = 200

        try:
            app = get_app()
            # 분석 API — Basic Auth 보호
            if path.startswith("/api/admin/"):
                if not self._check_admin_auth():
                    return self._send_unauthorized()
                if path == "/api/admin/analytics/summary":
                    return self._send_json(get_analytics().summary(hours=int(params.get("hours", 24))))
                if path == "/api/admin/analytics/recent":
                    return self._send_json(get_analytics().recent(limit=int(params.get("n", 100))))
            if path == "/api/ping":
                # 초경량 헬스체크 — Render/UptimeRobot 등 외부 모니터링용.
                # 모듈 import 외엔 아무것도 안 함 → 콜드 스타트 직후에도 ~10ms.
                # /api/health 는 시스템 상태 상세까지 계산해서 무거움.
                return self._send_json({"ok": True})
            if path == "/api/health":
                return self._send_json(app.health())
            if path == "/api/tickers":
                return self._send_json(app.tickers())
            if path == "/api/search":
                return self._send_json(app.search(params.get("q", ""), int(params.get("limit", 10))))
            if path == "/api/valuation":
                return self._send_json(app.valuation(params.get("q", "")))
            if path == "/api/undervalued":
                n = int(params.get("n", 10))
                strict = params.get("strict", "1") not in ("0", "false", "False")
                return self._send_json(app.undervalued(n=n, strict=strict))
            if path == "/api/recommend":
                return self._send_json(app.recommend(params.get("q", "")))
            if path == "/api/sy/evaluate":
                return self._send_json(app.sy_evaluate(params.get("q", "")))
            if path == "/api/sy/undervalued":
                return self._send_json(app.sy_undervalued(n=int(params.get("n", 10))))
            if path == "/api/prefetch":
                # 외부 cron(GitHub Actions)이 호출. ?type=news|market|all (기본 all)
                s = app.scheduler
                type_filter = params.get("type", "all").lower()
                results: dict[str, Any] = {}
                if type_filter in ("all", "news"):
                    results["news"] = s._job_news()
                    s._last_runs["news"] = time.time()
                if type_filter in ("all", "market"):
                    results["market"] = s._job_market()
                    results["hot"] = s._job_hot_tickers()
                    s._last_runs["market"] = time.time()
                    s._last_runs["hot"] = time.time()
                return self._send_json({
                    "ok": True, "type": type_filter, "results": results, "ts": time.time(),
                })
            if path == "/api/news":
                return self._send_json(app.news_search(params.get("q", ""), n=int(params.get("n", 10))))
            if path == "/api/market-news":
                return self._send_json(app.market_news(n=int(params.get("n", 10))))
            if path == "/api/news/topics":
                # ?force=1 면 캐시 무시
                force = params.get("force", "0") in ("1", "true", "True")
                if force:
                    return self._send_json({
                        t: [it.to_dict() for it in items]
                        for t, items in app.news.all_topics(
                            per_topic=int(params.get("n", 4)), force_refresh=True,
                        ).items()
                    })
                return self._send_json(app.news_topics(per_topic=int(params.get("n", 4))))
            if path == "/api/news/market":
                return self._send_json(app.market_topics(per_topic=int(params.get("n", 4))))
            if path == "/api/news/topic":
                return self._send_json(app.news_topic(params.get("topic", "코스피"), n=int(params.get("n", 10))))
            if path == "/api/commodities":
                return self._send_json(app.commodity_groups())
            if path == "/api/financials/annual":
                return self._send_json(app.financials_annual(params.get("q", "")))
            if path == "/api/financials/quarter":
                return self._send_json(app.financials_quarter(params.get("q", "")))
            if path == "/api/commodities/flat":
                return self._send_json(app.commodity_list())
            if path == "/api/price":
                return self._send_json(app.price_quote(params.get("q", "")))
            if path == "/api/history":
                return self._send_json(app.price_history(params.get("q", "")))
        except Exception as e:
            return self._send_json({"error": str(e)}, status=500)

        if path == "/" or path == "":
            return self._send_file(_STATIC / "index.html")
        if path.startswith("/"):
            target = (_STATIC / path.lstrip("/")).resolve()
            try:
                target.relative_to(_STATIC.resolve())
            except ValueError:
                return self._not_found()
            return self._send_file(target)
        return self._not_found()


def _local_ips() -> list[str]:
    """현재 머신의 LAN IP 추출."""
    import socket
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" in ip:  # IPv6 skip
                continue
            if ip.startswith("127."):
                continue
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def serve(host: str = "0.0.0.0", port: int = 8765) -> None:
    # 백그라운드 prefetch 스케줄러 시작
    app = get_app()
    app.scheduler.start()

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  ▶ SY Valuation 서버 실행 중")
    print(f"     로컬:   http://127.0.0.1:{port}/")
    if host in ("0.0.0.0", ""):
        for ip in _local_ips():
            print(f"     LAN:    http://{ip}:{port}/   (같은 와이파이/공유기에 연결된 기기)")
        print(f"\n     외부(인터넷)에서도 열려면 별도 터널이 필요합니다:")
        print(f"       1) cloudflared:  cloudflared tunnel --url http://localhost:{port}")
        print(f"       2) ngrok:        ngrok http {port}")
        print(f"       3) sy_valuation\\tunnel.bat  (자동 실행 헬퍼)")
    print(f"\n     스케줄러: 뉴스 1h / 원자재 5min / 시세 30min 자동 갱신")
    print(f"     종료: Ctrl+C\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  ▶ 서버 종료")
        app.scheduler.stop()
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = LAN open, 127.0.0.1 = local only")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    serve(args.host, args.port)
