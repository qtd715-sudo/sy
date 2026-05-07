"""뉴스 커넥터.

세 가지 소스 지원:
1) Naver 검색 API (NAVER_CLIENT_ID / NAVER_CLIENT_SECRET) - 정식 API
2) Google News RSS                                       - 키 불필요
3) 네이버 증권 종목뉴스 페이지 RSS                        - 백업

키가 없으면 RSS fallback.
"""

from __future__ import annotations
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Any

from .http_util import fetch, fetch_json
from .cache import get_cache


@dataclass
class NewsItem:
    title: str
    link: str
    description: str
    published: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


class NewsConnector:
    NAVER_API = "https://openapi.naver.com/v1/search/news.json"
    GOOGLE_RSS = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    BING_RSS = "https://www.bing.com/news/search?q={q}&format=rss&setLang=ko"

    def __init__(self, timeout: int = 4):
        self.timeout = timeout
        self.naver_id = os.environ.get("NAVER_CLIENT_ID", "")
        self.naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "")

    def search(self, query: str, limit: int = 10) -> list[NewsItem]:
        """다중 fallback: Naver API → Bing News RSS → Google News RSS."""
        items: list[NewsItem] = []
        if self.naver_id and self.naver_secret:
            items = self._search_naver(query, limit)
        if not items:
            items = self._search_bing(query, limit)
        if not items:
            items = self._search_google(query, limit)
        return items[:limit]

    def _search_bing(self, query: str, limit: int) -> list[NewsItem]:
        """Bing News RSS — 한국어 검색 결과, 글로벌 IP 에서 안정적."""
        url = self.BING_RSS.format(q=urllib.parse.quote(query))
        data = fetch(url, timeout=self.timeout)
        if not data:
            return []
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return []
        out: list[NewsItem] = []
        for item in root.findall("./channel/item"):
            out.append(NewsItem(
                title=_strip_html(item.findtext("title") or ""),
                link=item.findtext("link") or "",
                description=_strip_html(item.findtext("description") or ""),
                published=item.findtext("pubDate") or "",
                source="Bing News",
            ))
            if len(out) >= limit:
                break
        return out

    def _search_naver(self, query: str, limit: int) -> list[NewsItem]:
        url = f"{self.NAVER_API}?query={urllib.parse.quote(query)}&display={limit}&sort=date"
        headers = {
            "X-Naver-Client-Id": self.naver_id,
            "X-Naver-Client-Secret": self.naver_secret,
        }
        data = fetch_json(url, timeout=self.timeout, headers=headers)
        if not data:
            return []
        out = []
        for it in data.get("items", []):
            out.append(NewsItem(
                title=_strip_html(it.get("title", "")),
                link=it.get("originallink") or it.get("link", ""),
                description=_strip_html(it.get("description", "")),
                published=it.get("pubDate", ""),
                source="Naver",
            ))
        return out

    def _search_google(self, query: str, limit: int) -> list[NewsItem]:
        url = self.GOOGLE_RSS.format(q=urllib.parse.quote(query))
        data = fetch(url, timeout=self.timeout)
        if not data:
            return []
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return []
        out = []
        for item in root.findall("./channel/item"):
            out.append(NewsItem(
                title=_strip_html(item.findtext("title") or ""),
                link=item.findtext("link") or "",
                description=_strip_html(item.findtext("description") or ""),
                published=item.findtext("pubDate") or "",
                source=item.findtext("source") or "Google News",
            ))
            if len(out) >= limit:
                break
        return out

    def market_news(self, limit: int = 10) -> list[NewsItem]:
        """시장 전반 뉴스 (코스피, 환율, 금리, 미장)."""
        return self.search("코스피 OR 미국증시 OR 환율 OR 금리", limit=limit)

    # Bing News 는 OR 미지원 → 단일 키워드 사용 (가장 대표적인 1개)
    # 시장 종합은 대시보드 페이지에 표시, 여기 TOPICS 는 토픽 뉴스 페이지용 (산업/테마/정책)

    MARKET_TOPICS = {
        "코스피":           "코스피",
        "코스닥":           "코스닥",
        "미국증시":         "미국증시",
        "유럽증시":         "유럽증시",
        "일본증시":         "닛케이",
        "중국증시":         "상하이종합",
        "환율":             "원달러 환율",
        "금리":             "기준금리",
        "채권":             "국고채",
        "원유/에너지":      "유가",
        "금속/원자재":      "금값",
        "농산물":           "곡물 가격",
    }

    TOPICS = {
        # ── 정책/금융/부동산 (상위) ──
        "금융":             "금융 은행 보험",
        "부동산":           "부동산",
        "정부정책":         "정부정책",
        "경제정책":         "경제정책",
        "청년정책":         "청년정책",
        "주택정책":         "주택정책",
        "청약":             "주택 청약",
        # ── 산업/테마 (반도체부터 이어서) ──
        "반도체":           "반도체",
        "2차전지":          "2차전지",
        "AI":               "인공지능",
        "바이오":           "바이오 신약",
        "자동차":           "전기차",
        "조선/방산":        "K-방산",
        "엔터/콘텐츠":      "K팝",
        "ETF":              "ETF",
        "글로벌":           "글로벌 경제",
        "IT":               "IT 소프트웨어",
        # ── 하위 ──
        "가상자산":         "비트코인",
        "서울청년정책":     "서울 청년수당",
        "세제":             "세제개편",
        "노동/일자리":      "일자리",
        "복지":             "복지정책",
    }

    @classmethod
    def all_query_topics(cls) -> dict[str, str]:
        """대시보드용 + 토픽뉴스용 합쳐서 반환 (캐시/prefetch 용도)."""
        merged = dict(cls.MARKET_TOPICS)
        merged.update(cls.TOPICS)
        return merged

    def topic_news(self, topic: str, limit: int = 8) -> list[NewsItem]:
        q = self.TOPICS.get(topic) or self.MARKET_TOPICS.get(topic) or topic
        return self.search(q, limit=limit)

    def all_market_topics(self, per_topic: int = 4) -> dict[str, list[NewsItem]]:
        """대시보드용 — 시장 종합 토픽 (캐시 공유)."""
        import concurrent.futures
        cache = get_cache()
        topics = list(self.MARKET_TOPICS.keys())
        out: dict[str, list[NewsItem]] = {}
        to_fetch: list[str] = []
        for t in topics:
            cached = cache.get(f"news:topic:{t}")
            if cached:
                items_raw, _meta = cached
                out[t] = [NewsItem(**it) for it in items_raw[:per_topic]]
            else:
                to_fetch.append(t)
        if to_fetch:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                future_topic = {ex.submit(lambda x=t: (x, self.topic_news(x, limit=10)), ): t for t in to_fetch}
                try:
                    for fut in concurrent.futures.as_completed(future_topic, timeout=60):
                        try:
                            topic, items = fut.result(timeout=15)
                        except Exception:
                            topic = future_topic[fut]
                            items = []
                        if items:
                            cache.set(
                                f"news:topic:{topic}",
                                [it.to_dict() for it in items],
                                ttl_sec=self._CACHE_TTL,
                                source="bing_rss",
                            )
                        out[topic] = items[:per_topic]
                except concurrent.futures.TimeoutError:
                    pass
        return {t: out.get(t, []) for t in topics}

    _CACHE_TTL = 3600  # 1시간 (SQLite 영속 캐시)

    def all_topics(
        self, per_topic: int = 4, parallel: int = 4, force_refresh: bool = False,
    ) -> dict[str, list[NewsItem]]:
        """병렬 fetch + SQLite 1시간 캐시 (서버 재시작에도 유지).

        force_refresh=True 면 캐시 무시하고 새로 가져옴 (prefetch 잡 등).
        """
        import concurrent.futures
        cache = get_cache()
        topics = list(self.TOPICS.keys())
        out: dict[str, list[NewsItem]] = {}
        to_fetch: list[str] = []

        if not force_refresh:
            for t in topics:
                cached = cache.get(f"news:topic:{t}")
                if cached:
                    items_raw, _meta = cached
                    out[t] = [NewsItem(**it) for it in items_raw[:per_topic]]
                else:
                    to_fetch.append(t)
        else:
            to_fetch = topics

        if to_fetch:
            def do_fetch(topic: str) -> tuple[str, list[NewsItem]]:
                try:
                    return topic, self.topic_news(topic, limit=10)  # 넉넉히 받아 캐시
                except Exception:
                    return topic, []

            # as_completed + 견고한 timeout (느린 토픽 하나가 전체를 막지 않게)
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
                future_topic = {ex.submit(do_fetch, t): t for t in to_fetch}
                try:
                    for fut in concurrent.futures.as_completed(future_topic, timeout=120):
                        try:
                            topic, items = fut.result(timeout=15)
                        except Exception:
                            topic = future_topic[fut]
                            items = []
                        if items:
                            # 빈 결과는 캐시 안 함 (다음에 재시도 기회 줌)
                            cache.set(
                                f"news:topic:{topic}",
                                [it.to_dict() for it in items],
                                ttl_sec=self._CACHE_TTL,
                                source="bing_rss",
                            )
                        out[topic] = items[:per_topic]
                except concurrent.futures.TimeoutError:
                    # 일부 토픽만 시간 안에 완료 — 그것만 반환
                    pass

        return {t: out.get(t, []) for t in topics}

    def cache_status(self) -> dict[str, Any]:
        cache = get_cache()
        keys = cache.keys("news:topic:")
        latest_fetch = 0.0
        oldest_fetch = float("inf")
        for k in keys:
            cached = cache.get(k)
            if cached:
                _, meta = cached
                ts = meta.get("fetched_at", 0)
                latest_fetch = max(latest_fetch, ts)
                oldest_fetch = min(oldest_fetch, ts)
        return {
            "topics_cached": len(keys),
            "topics_total": len(self.TOPICS),
            "latest_fetch": latest_fetch if latest_fetch else None,
            "oldest_fetch": oldest_fetch if oldest_fetch < float("inf") else None,
        }

    def sentiment(self, items: list[NewsItem]) -> dict[str, float]:
        """간이 키워드 기반 감성 점수. -1.0 ~ +1.0"""
        positive = ["상승", "급등", "호조", "최대", "흑자", "성장", "돌파", "수혜", "상향"]
        negative = ["하락", "급락", "부진", "적자", "감소", "리스크", "충격", "하향", "둔화", "악화"]
        if not items:
            return {"score": 0.0, "positive": 0, "negative": 0}
        pos = neg = 0
        for it in items:
            text = f"{it.title} {it.description}"
            pos += sum(1 for kw in positive if kw in text)
            neg += sum(1 for kw in negative if kw in text)
        total = pos + neg
        score = (pos - neg) / total if total else 0.0
        return {"score": round(score, 3), "positive": pos, "negative": neg}
