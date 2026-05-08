"""YouTube 채널 RSS 기반 영상 리스트 + 간이 요약.

소스: https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID

기본 채널: 삼프로TV (UChlv4GSd7OQl3js-jkLOnFA)
환경변수 SAMPRO_CHANNEL_ID 로 변경 가능.
환경변수 YT_CHANNELS 로 다중 채널 등록 가능 (콤마 구분).

요약: 제목 + 첫 200자 description 표시 (자막은 별도 API 필요).
"""

from __future__ import annotations
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Any

from .http_util import fetch
from .cache import get_cache


SAMPRO_CHANNEL_ID = "UChlv4GSd7OQl3js-jkLOnFA"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


@dataclass
class VideoItem:
    video_id: str
    title: str
    link: str
    published: str
    updated: str
    description: str
    thumbnail: str
    channel: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 토픽 자동 분류 (제목 키워드 매칭)
TOPIC_KEYWORDS = {
    "주식/시황":   ["코스피", "코스닥", "주식", "증시", "지수", "상한가", "하한가", "급등", "급락"],
    "거시/경제":   ["FOMC", "금리", "기준금리", "인플레", "GDP", "경제지표", "한은", "연준"],
    "채권/외환":   ["국채", "환율", "달러", "원화", "엔화", "위안화"],
    "부동산":      ["부동산", "아파트", "분양", "청약", "전세", "매매가"],
    "글로벌":      ["미국", "중국", "일본", "유럽", "글로벌", "원자재", "원유"],
    "기업분석":    ["기업분석", "실적", "어닝", "실적발표", "재무"],
    "기술/AI":     ["AI", "반도체", "테크", "엔비디아", "TSMC"],
    "정치":        ["대통령", "정부", "정책", "국회", "선거"],
    "기타":        [],
}


def _classify_topic(title: str) -> str:
    title_l = title.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in title_l:
                return topic
    return "기타"


def _summarize(title: str, description: str, max_len: int = 200) -> str:
    """제목 + 설명 첫 N자 → 한 줄 요약."""
    desc = re.sub(r"\s+", " ", description or "").strip()
    if len(desc) > max_len:
        desc = desc[:max_len].rstrip() + "..."
    return desc or title


class YoutubeChannel:
    RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    CACHE_TTL = 1800  # 30분

    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        # 환경변수에서 추가 채널 로드 (콤마 구분)
        extra = os.environ.get("YT_CHANNELS", "")
        self.channels = {
            "삼프로TV": os.environ.get("SAMPRO_CHANNEL_ID", SAMPRO_CHANNEL_ID),
        }
        for pair in extra.split(","):
            pair = pair.strip()
            if ":" in pair:
                name, cid = pair.split(":", 1)
                self.channels[name.strip()] = cid.strip()

    def fetch_channel(self, channel_id: str, channel_name: str = "") -> list[VideoItem]:
        cache = get_cache()
        cache_key = f"youtube:{channel_id}"
        cached = cache.get(cache_key)
        if cached and cached[0]:
            return [VideoItem(**v) for v in cached[0]]

        # 1) RSS feed 시도
        out = self._fetch_rss(channel_id, channel_name)

        # 2) RSS 실패 → 채널 페이지 HTML 스크레이핑
        if not out:
            out = self._fetch_channel_page(channel_id, channel_name)

        if out:
            cache.set(cache_key, [v.to_dict() for v in out], ttl_sec=self.CACHE_TTL, source="youtube_rss")
        return out

    def _fetch_rss(self, channel_id: str, channel_name: str) -> list[VideoItem]:
        url = self.RSS.format(cid=channel_id)
        data = fetch(url, timeout=self.timeout)
        if not data:
            return []
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return []
        out: list[VideoItem] = []
        for entry in root.findall("atom:entry", NS):
            video_id = (entry.findtext("yt:videoId", default="", namespaces=NS) or "").strip()
            title = (entry.findtext("atom:title", default="", namespaces=NS) or "").strip()
            link_el = entry.find("atom:link", NS)
            link = link_el.get("href") if link_el is not None else ""
            published = entry.findtext("atom:published", default="", namespaces=NS) or ""
            updated = entry.findtext("atom:updated", default="", namespaces=NS) or ""
            mg = entry.find("media:group", NS)
            description = ""
            thumbnail = ""
            if mg is not None:
                description = (mg.findtext("media:description", default="", namespaces=NS) or "").strip()
                th_el = mg.find("media:thumbnail", NS)
                if th_el is not None:
                    thumbnail = th_el.get("url", "")
            out.append(VideoItem(
                video_id=video_id, title=title, link=link,
                published=published, updated=updated,
                description=description, thumbnail=thumbnail,
                channel=channel_name or channel_id,
            ))
        return out

    def _fetch_channel_page(self, channel_id: str, channel_name: str) -> list[VideoItem]:
        """채널 영상 페이지 HTML 에서 영상 추출.
        YouTube 는 React SPA 이고 ytInitialData JSON 에 데이터가 있음.

        전략:
        1) 모든 unique videoId 추출
        2) videoId 근처의 title 추출 시도 (다양한 패턴)
        3) thumbnail 은 i.ytimg.com 패턴으로 생성
        """
        url = f"https://www.youtube.com/channel/{channel_id}/videos"
        data = fetch(url, timeout=self.timeout, headers={
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        })
        if not data:
            return []
        try:
            html = data.decode("utf-8", errors="replace")
        except Exception:
            return []

        # 1) ytInitialData JSON 추출
        m = re.search(r'var ytInitialData = ({.+?});</script>', html)
        json_text = m.group(1) if m else html
        # 2) videoId 와 그 옆에 따라오는 title 패턴 매칭
        # YouTube 의 richItemRenderer > content.videoRenderer 구조 안:
        #   "videoId":"XXX",...,"title":{"runs":[{"text":"실제 제목"}]
        # 또는 "title":{"accessibility":{"accessibilityData":{"label":"제목 본문 ..."}}}
        out: list[VideoItem] = []
        seen: set[str] = set()
        # videoId 와 그 직후 약 800자 안의 title 매칭
        for m in re.finditer(r'"videoId":"([a-zA-Z0-9_-]{11})"', json_text):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            # videoId 위치 직후 1500자 안의 title 추출
            window = json_text[m.end(): m.end() + 1500]
            title = ""
            # runs 패턴
            tm = re.search(r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"', window)
            if tm:
                try:
                    import json as _json
                    title = _json.loads('"' + tm.group(1) + '"').strip()
                except Exception:
                    title = tm.group(1)
            else:
                # accessibilityData label 패턴 (제목 + 부가설명 포함)
                am = re.search(r'"accessibility":\{"accessibilityData":\{"label":"((?:[^"\\]|\\.)*)"', window)
                if am:
                    try:
                        import json as _json
                        full = _json.loads('"' + am.group(1) + '"').strip()
                        # "제목 by 채널명 12시간 전 1234 views 5분 30초" 같이 들어있음
                        # 첫 단어부터 " by " 또는 마지막 시간/조회수 직전까지 추출
                        title = re.split(r'\s+\d+\s*(시간|분|초|일|주|개월|년)\s*전', full)[0].strip()
                        if " by " in title:
                            title = title.rsplit(" by ", 1)[0].strip()
                    except Exception:
                        title = ""

            if not title:
                continue   # 제목 없으면 skip (재생목록 등)

            # 너무 짧거나 노이즈 항목 skip
            if len(title) < 3:
                continue

            out.append(VideoItem(
                video_id=vid,
                title=title,
                link=f"https://www.youtube.com/watch?v={vid}",
                published="",
                updated="",
                description="",
                thumbnail=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                channel=channel_name or channel_id,
            ))
            if len(out) >= 30:
                break
        return out

    # 단일 영상의 풀 description (RSS description 보다 더 길고 자세함)
    def fetch_video_full_description(self, video_id: str) -> str:
        cache = get_cache()
        ck = f"youtube:desc:{video_id}"
        cached = cache.get(ck)
        if cached and cached[0]:
            return cached[0]
        url = f"https://www.youtube.com/watch?v={video_id}"
        data = fetch(url, timeout=self.timeout)
        if not data:
            return ""
        try:
            html = data.decode("utf-8", errors="replace")
        except Exception:
            return ""
        # YouTube 페이지의 ytInitialData JSON 에서 shortDescription 또는 description.runs 추출
        m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
        if not m:
            return ""
        raw = m.group(1)
        # JSON 이스케이프 풀기
        try:
            import json as _json
            text = _json.loads('"' + raw + '"')
        except Exception:
            text = raw.replace("\\n", "\n").replace("\\\"", "\"")
        text = text.strip()
        if text:
            cache.set(ck, text, ttl_sec=86400, source="youtube_html")  # 24h
        return text

    def latest_with_summary(self, channel_name: str = "삼프로TV") -> dict[str, Any] | None:
        """가장 최근 영상 1개 + 풀 description 요약."""
        videos = self.list_videos(channel_name, limit=1)
        if not videos:
            return None
        v = videos[0]
        full_desc = self.fetch_video_full_description(v["video_id"])
        if full_desc:
            v["full_description"] = full_desc
            # 첫 800자 요약
            v["summary"] = (full_desc[:800] + ("..." if len(full_desc) > 800 else ""))
        return v

    def fetch_all(self) -> dict[str, list[VideoItem]]:
        out: dict[str, list[VideoItem]] = {}
        for name, cid in self.channels.items():
            out[name] = self.fetch_channel(cid, name)
        return out

    def list_videos(self, channel_name: str = "삼프로TV", limit: int = 20) -> list[dict[str, Any]]:
        """UI 용 — 영상 dict 리스트 (요약/토픽 포함)."""
        cid = self.channels.get(channel_name, SAMPRO_CHANNEL_ID)
        videos = self.fetch_channel(cid, channel_name)
        out = []
        for v in videos[:limit]:
            d = v.to_dict()
            d["topic"] = _classify_topic(v.title)
            d["summary"] = _summarize(v.title, v.description)
            out.append(d)
        return out

    def grouped_by_topic(self, channel_name: str = "삼프로TV", limit: int = 30) -> dict[str, list[dict[str, Any]]]:
        videos = self.list_videos(channel_name, limit=limit)
        groups: dict[str, list[dict[str, Any]]] = {t: [] for t in TOPIC_KEYWORDS}
        for v in videos:
            topic = v.get("topic", "기타")
            groups.setdefault(topic, []).append(v)
        return {t: vs for t, vs in groups.items() if vs}
