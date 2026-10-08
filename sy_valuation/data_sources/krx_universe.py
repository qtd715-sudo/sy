"""KOSPI/KOSDAQ 전 종목 리스트 빌더.

Naver 모바일 증권 API 의 시가총액 순 목록을 페이지 단위로 받아서
전 종목 (코드 + 이름 + 시장) 를 SQLite 캐시에 저장.
하루 1번 자동 갱신.

URL 예: https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=100
        https://m.stock.naver.com/api/stocks/marketValue/KOSDAQ?page=1&pageSize=100

※ 2026-10 Naver 금융 PC 페이지(sise_market_sum.naver)가 Next.js 로 개편되어
   기존 HTML 스크레이프가 0건을 반환 → 모바일 JSON API 로 교체.
"""

from __future__ import annotations
import json
from typing import Any

from .http_util import fetch
from .cache import get_cache


CACHE_KEY = "krx:universe"
CACHE_TTL = 86400  # 24시간
PAGE_SIZE = 100
URL = "https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize={size}"


def _parse_page(data: bytes, market: str) -> list[dict[str, str]]:
    try:
        j = json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for s in j.get("stocks") or []:
        code = (s.get("itemCode") or "").strip()
        name = (s.get("stockName") or "").strip()
        if len(code) != 6 or not name:
            continue
        end_type = s.get("stockEndType") or "stock"
        out.append({
            "ticker": code,
            "name": name,
            "exchange": market,
            "asset": "stock" if end_type == "stock" else end_type,
            "sector": "",   # 목록 API 엔 섹터 없음 — 추후 보강 가능
        })
    return out


def fetch_market(market: str = "KOSPI", max_pages: int = 40) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        data = fetch(URL.format(market=market, page=page, size=PAGE_SIZE), timeout=8)
        if not data:
            break
        items = _parse_page(data, market)
        if not items:
            break  # 마지막 페이지
        new_items = [it for it in items if it["ticker"] not in seen]
        if not new_items:
            break  # 페이지 반복 (마지막 도달)
        for it in new_items:
            seen.add(it["ticker"])
        out.extend(new_items)
        if len(items) < PAGE_SIZE:
            break
    return out


def fetch_all() -> list[dict[str, str]]:
    """KOSPI + KOSDAQ 전 종목."""
    out: list[dict[str, str]] = []
    out.extend(fetch_market("KOSPI"))
    out.extend(fetch_market("KOSDAQ"))
    return out


def load_universe(force_refresh: bool = False) -> list[dict[str, str]]:
    """캐시에서 가져오거나, 없으면 fetch + 저장."""
    cache = get_cache()
    if not force_refresh:
        cached = cache.get(CACHE_KEY)
        if cached:
            return cached[0]
    items = fetch_all()
    if items:
        cache.set(CACHE_KEY, items, ttl_sec=CACHE_TTL, source="naver_finance")
    return items
