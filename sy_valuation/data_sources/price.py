"""주가 커넥터.

소스: Yahoo Finance (한국 종목은 .KS / .KQ 접미사). API 키 불필요.
"""

from __future__ import annotations
import json
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class PriceQuote:
    ticker: str
    price: float
    prev_close: float
    change_pct: float
    high_52w: float
    low_52w: float
    volume: int
    market_cap: float
    currency: str

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
    CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={range}&interval={interval}"

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    @staticmethod
    def to_yahoo_symbol(ticker: str) -> str:
        """6자리 한국 코드면 KOSPI .KS / KOSDAQ .KQ 자동 부여."""
        if ticker.isdigit() and len(ticker) == 6:
            # KOSDAQ 시작 코드는 보통 0~9 다양 → 둘 다 시도하는 편이 안전
            return f"{ticker}.KS"
        return ticker

    def quote(self, ticker: str) -> PriceQuote | None:
        for suffix in ("", ".KS", ".KQ"):
            sym = ticker if (suffix == "" or "." in ticker) else f"{ticker}{suffix}"
            if suffix == "" and ticker.isdigit() and len(ticker) == 6:
                continue  # 숫자코드는 접미사 필요
            q = self._fetch_quote(sym)
            if q:
                return q
        return None

    def _fetch_quote(self, sym: str) -> PriceQuote | None:
        url = self.CHART.format(sym=sym, range="1y", interval="1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        try:
            r = data["chart"]["result"][0]
            meta = r["meta"]
            return PriceQuote(
                ticker=sym,
                price=float(meta.get("regularMarketPrice") or 0),
                prev_close=float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0),
                change_pct=0.0,
                high_52w=float(meta.get("fiftyTwoWeekHigh") or 0),
                low_52w=float(meta.get("fiftyTwoWeekLow") or 0),
                volume=int(meta.get("regularMarketVolume") or 0),
                market_cap=float(meta.get("marketCap") or 0),
                currency=meta.get("currency", ""),
            )
        except (KeyError, IndexError, TypeError):
            return None

    def history(self, ticker: str, range_: str = "1y", interval: str = "1d") -> PriceHistory | None:
        sym = self.to_yahoo_symbol(ticker)
        url = self.CHART.format(sym=sym, range=range_, interval=interval)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
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
