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
        """Naver API → 실패 시 Google News RSS."""
        items: list[NewsItem] = []
        if self.naver_id and self.naver_secret:
            items = self._search_naver(query, limit)
        if not items:
            items = self._search_google(query, limit)
        return items[:limit]

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

    _topic_cache: dict[str, tuple[float, list[NewsItem]]] = {}
    _CACHE_TTL = 120  # 2분

    def all_topics(self, per_topic: int = 4, parallel: int = 8) -> dict[str, list[NewsItem]]:
        """병렬 fetch + 2분 캐시. 28 토픽이라 직렬은 너무 느림."""
        import concurrent.futures
        import time

        topics = list(self.TOPICS.keys())
        out: dict[str, list[NewsItem]] = {}
        now = time.time()

        # 캐시에서 가져오기
        to_fetch: list[str] = []
        for t in topics:
            cached = self._topic_cache.get(t)
            if cached and (now - cached[0]) < self._CACHE_TTL:
                out[t] = cached[1][:per_topic]
            else:
                to_fetch.append(t)

        if to_fetch:
            def fetch(topic: str) -> tuple[str, list[NewsItem]]:
                try:
                    return topic, self.topic_news(topic, limit=per_topic)
                except Exception:
                    return topic, []

            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
                for topic, items in ex.map(fetch, to_fetch):
                    out[topic] = items
                    self._topic_cache[topic] = (now, items)

        # TOPICS 순서대로 재정렬
        return {t: out.get(t, []) for t in topics}

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
