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
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Any


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
        req = urllib.request.Request(url, headers={
            "X-Naver-Client-Id": self.naver_id,
            "X-Naver-Client-Secret": self.naver_secret,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
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
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
        except Exception:
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
        "코스피":     "코스피 OR KOSPI",
        "코스닥":     "코스닥 OR KOSDAQ",
        "미국증시":   "S&P500 OR 나스닥 OR 다우",
        "환율":       "환율 OR 달러 OR 원달러",
        "금리/채권":  "기준금리 OR 미국채 OR FOMC OR 한국은행",
        "원유/에너지":"WTI OR 유가 OR 원유 OR OPEC",
        "금속/금":    "금값 OR 구리 OR 니켈",
        "반도체":     "반도체 OR HBM OR D램 OR TSMC",
        "2차전지":    "2차전지 OR 배터리 OR 양극재 OR LFP",
        "AI":         "AI OR 인공지능 OR 엔비디아 OR NVIDIA",
        "부동산":     "부동산 OR 아파트 OR 분양",
        "가상자산":   "비트코인 OR 이더리움 OR 가상자산 OR 코인",
        "ETF":        "ETF OR 상장지수펀드",
    }

    def topic_news(self, topic: str, limit: int = 8) -> list[NewsItem]:
        q = self.TOPICS.get(topic, topic)
        return self.search(q, limit=limit)

    def all_topics(self, per_topic: int = 4) -> dict[str, list[NewsItem]]:
        out: dict[str, list[NewsItem]] = {}
        for topic in self.TOPICS:
            try:
                out[topic] = self.topic_news(topic, limit=per_topic)
            except Exception:
                out[topic] = []
        return out

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
