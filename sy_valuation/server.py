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
import json
import mimetypes
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .data_sources import (
    FinancialsRepository, NewsConnector, CommodityConnector, PriceConnector, DartConnector,
    LiveFinancials,
)
from .valuation.engine import value_company
from .valuation.sy_method import evaluate_sy
from .valuation.sy_builder import build_inputs_from_raw
from .recommender import find_undervalued, recommend_investment


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

    # ---------- API handlers ----------

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "dart_enabled": self.dart.enabled,
            "naver_news_enabled": bool(self.news.naver_id),
            "tickers_loaded": len(self.repo.list_tickers()),
            "samples_loaded": len(self.repo.all()),
        }

    def tickers(self) -> list[dict[str, str]]:
        return self.repo.list_tickers()

    def search(self, q: str, limit: int = 10) -> list[dict[str, str]]:
        return self.repo.search(q, limit=limit)

    def _resolve_financials(self, query: str):
        """샘플 → live → None 순으로 시도."""
        f = self.repo.get_or_build_financials(query, live=self.live)
        if not f:
            return None, None
        # 실시간 가격으로 최신화
        try:
            q = self.price.quote(f.ticker)
            if q and q.price > 0:
                f.current_price = q.price
        except Exception:
            pass
        meta = self.repo.get_ticker_meta(f.ticker) or {}
        return f, meta

    def valuation(self, query: str) -> dict[str, Any]:
        f, meta = self._resolve_financials(query)
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
        }

    def undervalued(self, n: int = 10, strict: bool = True) -> list[dict[str, Any]]:
        results = find_undervalued(self.repo.all_financials(), top_n=n, strict=strict)
        return [r.to_dict() for r in results]

    def sy_evaluate(self, query: str) -> dict[str, Any]:
        raw = self.repo.find(query)
        if not raw:
            return {
                "error": f"종목을 찾을 수 없습니다: {query}",
                "suggestions": self.repo.search(query, limit=5),
                "hint": "SY 평가법은 자산/부채/시총/피어 정보가 필요합니다. 샘플 financials 에 등록된 종목만 평가 가능합니다.",
            }
        sectors = self.repo.sector_table()
        sector_mults = sectors.get(raw["sector"], {})
        # 실시간 가격 (있으면) 으로 시총 갱신
        try:
            q = self.price.quote(raw["ticker"])
            if q and q.price > 0 and raw.get("shares_outstanding"):
                raw = dict(raw)
                raw["current_price"] = q.price
                if "market_cap" not in raw:
                    raw["market_cap"] = q.price * raw["shares_outstanding"]
        except Exception:
            pass
        inp = build_inputs_from_raw(raw, sector_mults)
        result = evaluate_sy(inp)
        return result.to_dict()

    def sy_undervalued(self, n: int = 10) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        sectors = self.repo.sector_table()
        for raw in self.repo.all():
            sector_mults = sectors.get(raw["sector"], {})
            inp = build_inputs_from_raw(raw, sector_mults)
            r = evaluate_sy(inp)
            if r.market_cap <= 0 or r.enterprise_mid <= 0:
                continue
            if r.upside_mid <= 0:
                continue
            out.append(r.to_dict())
        out.sort(key=lambda x: x["upside_mid"], reverse=True)
        return out[:n]

    def recommend(self, query: str) -> dict[str, Any]:
        f, meta = self._resolve_financials(query)
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

    def news_topic(self, topic: str, n: int = 10) -> dict[str, Any]:
        items = self.news.topic_news(topic, limit=n)
        return {
            "topic": topic,
            "items": [it.to_dict() for it in items],
            "sentiment": self.news.sentiment(items),
        }

    def commodity_groups(self) -> dict[str, list[dict[str, Any]]]:
        groups = self.commodities.watchlist_groups()
        return {g: [q.to_dict() for q in qs] for g, qs in groups.items()}

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

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            return self._not_found()
        ctype, _ = mimetypes.guess_type(str(path))
        if ctype is None:
            ctype = "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript") or ctype.endswith("json"):
            ctype += "; charset=utf-8"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("404 Not Found".encode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        path = parsed.path

        try:
            app = get_app()
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
            if path == "/api/news":
                return self._send_json(app.news_search(params.get("q", ""), n=int(params.get("n", 10))))
            if path == "/api/market-news":
                return self._send_json(app.market_news(n=int(params.get("n", 10))))
            if path == "/api/news/topics":
                return self._send_json(app.news_topics(per_topic=int(params.get("n", 4))))
            if path == "/api/news/topic":
                return self._send_json(app.news_topic(params.get("topic", "코스피"), n=int(params.get("n", 10))))
            if path == "/api/commodities":
                return self._send_json(app.commodity_groups())
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


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"  ▶ SY Valuation server: http://{host}:{port}")
    print(f"  ▶ 종료: Ctrl+C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  ▶ 서버 종료")
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    serve(args.host, args.port)
