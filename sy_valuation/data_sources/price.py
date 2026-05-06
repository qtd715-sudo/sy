"""주가 커넥터.

소스 우선순위:
  1) Naver Finance polling API   - 한국 6자리 코드, 실시간 (장중 7초 주기)
  2) Yahoo Finance v8 chart      - 글로벌 (US 주식, ETF), 최근 종가

API 키 불필요.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from typing import Any

from .http_util import fetch_json


@dataclass
class PriceQuote:
    ticker: str
    price: float
    prev_close: float
    change_pct: float
    high_52w: float = 0.0
    low_52w: float = 0.0
    volume: int = 0
    market_cap: float = 0.0
    currency: str = ""
    market_status: str = ""        # OPEN / CLOSE / PRE_OPEN_MARKET 등
    traded_at: str = ""            # ISO timestamp (YYYY-MM-DDTHH:MM:SS+09:00)
    source: str = ""               # naver / yahoo

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PriceHistory:
    ticker: str
    timestamps: list[int]
    closes: list[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PriceConnector:
    NAVER_POLL = "https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
    YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={range}&interval={interval}"

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    @staticmethod
    def to_yahoo_symbol(ticker: str) -> str:
        if ticker.isdigit() and len(ticker) == 6:
            return f"{ticker}.KS"
        return ticker

    @staticmethod
    def is_korean(ticker: str) -> bool:
        return bool(ticker and ticker.isdigit() and len(ticker) == 6)

    def quote(self, ticker: str) -> PriceQuote | None:
        # 1) Naver 우선 (한국 종목)
        if self.is_korean(ticker):
            q = self._fetch_naver(ticker)
            if q:
                return q
        # 2) Yahoo 폴백
        for suffix in ("", ".KS", ".KQ"):
            sym = ticker if (suffix == "" or "." in ticker) else f"{ticker}{suffix}"
            if suffix == "" and self.is_korean(ticker):
                continue
            q = self._fetch_quote(sym)
            if q:
                return q
        return None

    def _fetch_naver(self, code: str) -> PriceQuote | None:
        url = self.NAVER_POLL.format(code=code)
        data = fetch_json(url, timeout=self.timeout)
        if not data:
            return None
        try:
            d = (data.get("datas") or [None])[0]
            if not d:
                return None
            price = float(d.get("closePriceRaw") or 0)
            change_amt = float(d.get("compareToPreviousClosePriceRaw") or 0)
            prev = price - change_amt if price > 0 else 0
            change_pct = float(d.get("fluctuationsRatioRaw") or 0)
            sign = (d.get("compareToPreviousPrice") or {}).get("code", "")
            if sign == "5":  # 하락
                change_pct = -abs(change_pct)
            mcap = float(d.get("marketValueFullRaw") or 0)
            ccy = (d.get("currencyType") or {}).get("code", "KRW")
            return PriceQuote(
                ticker=code,
                price=price,
                prev_close=prev,
                change_pct=change_pct,
                high_52w=0.0, low_52w=0.0,
                volume=int(float(d.get("accumulatedTradingVolumeRaw") or 0)),
                market_cap=mcap,
                currency=ccy,
                market_status=d.get("marketStatus", ""),
                traded_at=d.get("localTradedAt", ""),
                source="naver",
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def _fetch_quote(self, sym: str) -> PriceQuote | None:
        url = self.YAHOO_CHART.format(sym=sym, range="1y", interval="1d")
        data = fetch_json(url, timeout=self.timeout)
        if not data:
            return None
        try:
            r = data["chart"]["result"][0]
            meta = r["meta"]
            price = float(meta.get("regularMarketPrice") or 0)
            prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)
            chg = ((price - prev) / prev * 100) if prev > 0 else 0.0
            ts = int(meta.get("regularMarketTime") or 0)
            from datetime import datetime, timezone
            iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
            return PriceQuote(
                ticker=sym,
                price=price,
                prev_close=prev,
                change_pct=round(chg, 3),
                high_52w=float(meta.get("fiftyTwoWeekHigh") or 0),
                low_52w=float(meta.get("fiftyTwoWeekLow") or 0),
                volume=int(meta.get("regularMarketVolume") or 0),
                market_cap=float(meta.get("marketCap") or 0),
                currency=meta.get("currency", ""),
                market_status=meta.get("marketState", ""),
                traded_at=iso,
                source="yahoo",
            )
        except (KeyError, IndexError, TypeError):
            return None

    def history(self, ticker: str, range_: str = "1y", interval: str = "1d") -> PriceHistory | None:
        sym = self.to_yahoo_symbol(ticker)
        url = self.YAHOO_CHART.format(sym=sym, range=range_, interval=interval)
        data = fetch_json(url, timeout=self.timeout)
        if not data:
            return None
        try:
            r = data["chart"]["result"][0]
            ts = r.get("timestamp") or []
            closes = (r.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
            ts = [int(t) for t in ts]
            closes = [float(c) if c is not None else 0.0 for c in closes]
            return PriceHistory(ticker=sym, timestamps=ts, closes=closes)
        except (KeyError, IndexError, TypeError):
            return None
