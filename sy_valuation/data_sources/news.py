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

    def __init__(self, timeout: int = 6):
        self.timeout = timeout
        self.naver_id = os.environ.get("NAVER_CLIENT_ID", "")
        self.naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "")

    def search(self, query: str, limit: int = 10) -> list[NewsItem]:
        """Naver API (키있으면) → Naver 검색 스크레이핑 → Google News RSS 순서."""
        items: list[NewsItem] = []
        if self.naver_id and self.naver_secret:
            items = self._search_naver(query, limit)
        if not items:
            items = self._search_naver_scrape(query, limit)
        if not items:
            items = self._search_google(query, limit)
        return items[:limit]

    def _search_naver_scrape(self, query: str, limit: int) -> list[NewsItem]:
        """Naver 검색 결과 페이지 HTML 스크레이핑 (키 불필요)."""
        url = f"https://search.naver.com/search.naver?where=news&query={urllib.parse.quote(query)}&sort=1"
        data = fetch(url, timeout=self.timeout)
        if not data:
            return []
        try:
            html = data.decode("utf-8", errors="replace")
        except Exception:
            return []
        # Naver 뉴스 결과 파싱: <a class="news_tit" href="..." title="..."> 또는 비슷한 구조
        items: list[NewsItem] = []
        # 제목 + 링크 추출 (클래스명 변경에 강건한 정규식)
        pattern = re.compile(
            r'<a[^>]+class="[^"]*news_tit[^"]*"[^>]+href="([^"]+)"[^>]*title="([^"]+)"',
            re.IGNORECASE,
        )
        for m in pattern.finditer(html):
            link, title = m.group(1), m.group(2)
            items.append(NewsItem(
                title=_strip_html(title),
                link=link,
                description="",
                published="",
                source="Naver",
            ))
            if len(items) >= limit:
                break
        return items

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

    TOPICS = {
        # 시장
        "코스피":           "코스피 OR KOSPI",
        "코스닥":           "코스닥 OR KOSDAQ",
        "미국증시":         "S&P500 OR 나스닥 OR 다우 OR 미국증시",
        "유럽증시":         "DAX OR FTSE OR 유럽증시 OR 유로스톡스",
        "일본증시":         "닛케이 OR 일본증시 OR 도쿄증시",
        "중국증시":         "상하이종합 OR 항셍 OR 중국증시",
        "환율":             "환율 OR 달러 OR 원달러 OR 원/달러",
        "금리/채권":        "기준금리 OR 미국채 OR FOMC OR 한국은행 OR 금통위",
        "원유/에너지":      "WTI OR 유가 OR 원유 OR OPEC OR 천연가스",
        "금속/원자재":      "금값 OR 구리 OR 니켈 OR 알루미늄 OR 리튬",
        "농산물":           "곡물 OR 옥수수 OR 대두 OR 커피 OR 설탕",
        # 산업/테마
        "반도체":           "반도체 OR HBM OR D램 OR TSMC OR 파운드리",
        "2차전지":          "2차전지 OR 배터리 OR 양극재 OR LFP OR 음극재",
        "AI":               "AI OR 인공지능 OR 엔비디아 OR NVIDIA OR 챗GPT",
        "바이오":           "바이오 OR 신약 OR 임상 OR 제약",
        "자동차":           "전기차 OR 자동차 OR 현대차 OR 테슬라",
        "조선/방산":        "조선 OR 방산 OR K-방산 OR 함정",
        "엔터/콘텐츠":      "K-POP OR 엔터 OR 하이브 OR 드라마",
        "부동산":           "부동산 OR 아파트 OR 분양 OR 청약",
        "가상자산":         "비트코인 OR 이더리움 OR 가상자산 OR 코인 OR BTC",
        "ETF":              "ETF OR 상장지수펀드",
        # 정책/사회
        "정부정책":         "정부정책 OR 정책발표 OR 국정과제 OR 부처",
        "경제정책":         "경제정책 OR 거시정책 OR 재정정책 OR 추경",
        "청년정책":         "청년정책 OR 청년지원 OR 청년창업 OR 청년일자리",
        "서울청년정책":     "서울청년 OR 청년월세 OR 청년수당 OR 서울시 청년",
        "주택정책":         "주택정책 OR 분양정책 OR 임대주택 OR LH",
        "세제":             "세금 OR 세제개편 OR 종부세 OR 양도세",
        "노동/일자리":      "일자리 OR 최저임금 OR 노동정책 OR 고용",
        "복지":             "복지정책 OR 기초수급 OR 국민연금",
    }

    def topic_news(self, topic: str, limit: int = 8) -> list[NewsItem]:
        q = self.TOPICS.get(topic, topic)
        return self.search(q, limit=limit)

    _CACHE_TTL = 3600  # 1시간 (SQLite 영속 캐시)

    def all_topics(
        self, per_topic: int = 4, parallel: int = 8, force_refresh: bool = False,
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

            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
                for topic, items in ex.map(do_fetch, to_fetch):
                    cache.set(
                        f"news:topic:{topic}",
                        [it.to_dict() for it in items],
                        ttl_sec=self._CACHE_TTL,
                        source="google_news_rss" if not self.naver_id else "naver_api",
                    )
                    out[topic] = items[:per_topic]

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
