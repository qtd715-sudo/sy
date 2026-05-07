"""KOSPI/KOSDAQ 전 종목 리스트 빌더.

Naver Finance 의 시가총액 페이지를 페이지 단위로 스크레이프해서
전 종목 (코드 + 이름 + 시장) 를 SQLite 캐시에 저장.
하루 1번 자동 갱신.

URL 예: https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1   (KOSPI)
        https://finance.naver.com/sise/sise_market_sum.naver?sosok=1&page=1   (KOSDAQ)

각 페이지는 50종목 → 코스피 ~20페이지, 코스닥 ~30페이지.
"""

from __future__ import annotations
import re
from typing import Any

from .http_util import fetch
from .cache import get_cache


CACHE_KEY = "krx:universe"
CACHE_TTL = 86400  # 24시간


def _parse_page(html: str, market: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    # <a href="/item/main.naver?code=005930" class="tltle">삼성전자</a>
    pat = re.compile(r'<a\s+href="/item/main\.naver\?code=(\d{6})"[^>]*class="tltle"[^>]*>([^<]+)</a>')
    for m in pat.finditer(html):
        out.append({
            "ticker": m.group(1),
            "name": m.group(2).strip(),
            "exchange": market,
            "asset": "stock",
            "sector": "",   # Naver 시가총액 페이지엔 섹터 없음 — 추후 보강 가능
        })
    return out


def fetch_market(market: str = "KOSPI", max_pages: int = 50) -> list[dict[str, str]]:
    sosok = "0" if market == "KOSPI" else "1"
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
        data = fetch(url, timeout=8)
        if not data:
            break
        # Naver 페이지는 EUC-KR 인코딩
        try:
            html = data.decode("euc-kr", errors="replace")
        except Exception:
            html = data.decode("utf-8", errors="replace")
        items = _parse_page(html, market)
        if not items:
            break  # 마지막 페이지
        new_items = [it for it in items if it["ticker"] not in seen]
        if not new_items:
            break  # 페이지 반복 (마지막 도달)
        for it in new_items:
            seen.add(it["ticker"])
        out.extend(new_items)
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
