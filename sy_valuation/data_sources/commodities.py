"""원물(원자재) 시세 커넥터.

소스:
- Yahoo Finance v8 차트 API (no key) : ^DJI, GC=F, CL=F, HG=F, ZS=F 등 선물 심볼
- 한국거래소 환율(USDKRW=X)

전부 실패 시 캐시된 sample data 반환.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from typing import Any

from .http_util import fetch_json


@dataclass
class CommodityQuote:
    symbol: str
    name: str
    price: float
    currency: str
    change_pct: float
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 카테고리별 심볼 (UI 그룹핑용)
WATCHLIST_GROUPS = {
    "지수": [
        ("^KS11",     "코스피",            "KRW"),
        ("^KQ11",     "코스닥",            "KRW"),
        ("^GSPC",     "S&P500",            "USD"),
        ("^IXIC",     "나스닥",            "USD"),
        ("^DJI",      "다우존스",          "USD"),
        ("^RUT",      "러셀2000",          "USD"),
        ("^N225",     "닛케이225",         "JPY"),
        ("^HSI",      "항셍",              "HKD"),
        ("000001.SS", "상해종합",          "CNY"),
        ("^FTSE",     "FTSE100",           "GBP"),
        ("^GDAXI",    "DAX",               "EUR"),
        ("^STOXX50E", "Euro Stoxx 50",     "EUR"),
        ("^VIX",      "VIX (변동성지수)",  ""),
    ],
    "환율": [
        ("USDKRW=X",  "원/달러",           "KRW"),
        ("EURKRW=X",  "원/유로",           "KRW"),
        ("JPYKRW=X",  "원/100엔",          "KRW"),
        ("CNYKRW=X",  "원/위안",           "KRW"),
        ("EURUSD=X",  "유로/달러",         "USD"),
        ("USDJPY=X",  "엔/달러",           "JPY"),
        ("GBPUSD=X",  "파운드/달러",       "USD"),
        ("DX-Y.NYB",  "달러인덱스 DXY",    ""),
    ],
    "채권": [
        ("^TNX",      "미 10년 국채",      "%"),
        ("^TYX",      "미 30년 국채",      "%"),
        ("^FVX",      "미 5년 국채",       "%"),
        ("^IRX",      "미 13주 단기금리",  "%"),
    ],
    "원자재": [
        ("CL=F",      "WTI 원유",          "USD"),
        ("BZ=F",      "Brent 원유",        "USD"),
        ("NG=F",      "천연가스",          "USD"),
        ("GC=F",      "금",                "USD"),
        ("SI=F",      "은",                "USD"),
        ("PL=F",      "백금",              "USD"),
        ("HG=F",      "구리",              "USD"),
        ("ALI=F",     "알루미늄",          "USD"),
        ("ZS=F",      "대두",              "USD"),
        ("ZC=F",      "옥수수",            "USD"),
        ("ZW=F",      "밀",                "USD"),
        ("KC=F",      "커피",              "USD"),
        ("SB=F",      "설탕",              "USD"),
        ("CC=F",      "코코아",            "USD"),
        ("CT=F",      "면화",              "USD"),
    ],
    "가상자산": [
        ("BTC-USD",   "비트코인",          "USD"),
        ("ETH-USD",   "이더리움",          "USD"),
        ("BNB-USD",   "바이낸스코인",      "USD"),
        ("XRP-USD",   "리플",              "USD"),
        ("SOL-USD",   "솔라나",            "USD"),
        ("DOGE-USD",  "도지코인",          "USD"),
        ("ADA-USD",   "에이다",            "USD"),
    ],
}

WATCHLIST = [
    (sym, name, ccy)
    for items in WATCHLIST_GROUPS.values()
    for (sym, name, ccy) in items
]


class CommodityConnector:
    YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    def fetch(self, symbol: str, name: str = "", currency: str = "") -> CommodityQuote | None:
        url = self.YAHOO_CHART.format(sym=symbol)
        data = fetch_json(url, timeout=self.timeout)
        if not data:
            return None
        try:
            result = data["chart"]["result"][0]
            meta = result["meta"]
            price = float(meta.get("regularMarketPrice") or 0.0)
            prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
            change = ((price - prev) / prev * 100) if prev else 0.0
            ts = int(meta.get("regularMarketTime") or 0)
            return CommodityQuote(
                symbol=symbol, name=name or meta.get("symbol", symbol),
                price=round(price, 4), currency=currency or meta.get("currency", ""),
                change_pct=round(change, 3), timestamp=ts,
            )
        except (KeyError, IndexError, TypeError):
            return None

    def watchlist(self) -> list[CommodityQuote]:
        out: list[CommodityQuote] = []
        for sym, name, ccy in WATCHLIST:
            q = self.fetch(sym, name, ccy)
            if q:
                out.append(q)
        return out

    def watchlist_groups(self) -> dict[str, list[CommodityQuote]]:
        groups: dict[str, list[CommodityQuote]] = {}
        for group, items in WATCHLIST_GROUPS.items():
            qs: list[CommodityQuote] = []
            for sym, name, ccy in items:
                q = self.fetch(sym, name, ccy)
                if q:
                    qs.append(q)
            groups[group] = qs
        return groups
