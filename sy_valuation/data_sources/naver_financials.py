"""Naver 연간/분기 재무제표 자동 스크레이퍼.

엔드포인트:
- https://m.stock.naver.com/api/stock/{code}/finance/annual    (연간)
- https://m.stock.naver.com/api/stock/{code}/finance/quarter   (분기)

DART 키 없이도 작동. 매분기 발표 시 자동 갱신 (스케줄러가 24h 주기로 fetch).

응답 구조:
{
    "financeInfo": {
        "trTitleList": [{"title": "2023.12.", "key": "202312"}, ...],
        "rowList": [
            {"title": "매출액", "columns": {"202312": {"value": "..."}, ...}},
            {"title": "영업이익", ...},
            {"title": "당기순이익", ...},
            {"title": "EPS", ...},
            {"title": "BPS", ...},
            {"title": "PER", ...},
            {"title": "PBR", ...},
            {"title": "ROE", ...},
            {"title": "부채비율", ...},
            {"title": "주당배당금", ...},
        ]
    }
}

단위: 매출/이익은 억원, EPS/BPS는 원, ROE/부채비율은 %.
"""

from __future__ import annotations
from typing import Any

from .http_util import fetch_json
from .cache import get_cache


CACHE_TTL = 86400  # 24시간


def _to_num(s: str) -> float:
    """'3,336,059' → 3336059.0 / '-' → 0.0 / '13.07' → 13.07"""
    if not s or s in ("-", ""):
        return 0.0
    s = str(s).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


class NaverFinancials:
    URL = "https://m.stock.naver.com/api/stock/{code}/finance/{period}"

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    def fetch(self, code: str, period: str = "annual") -> dict[str, Any] | None:
        """{period: 'annual' | 'quarter'}"""
        if not code or not code.isdigit() or len(code) != 6:
            return None

        cache = get_cache()
        cache_key = f"naver_fin:{code}:{period}"
        cached = cache.get(cache_key)
        if cached:
            return cached[0]

        url = self.URL.format(code=code, period=period)
        data = fetch_json(url, timeout=self.timeout)
        if not data:
            return None

        fi = data.get("financeInfo") or {}
        if not fi:
            return None

        # 행 → 항목별 시계열 dict
        result: dict[str, dict[str, float]] = {}
        for row in fi.get("rowList", []):
            title = row.get("title", "").strip()
            cols = row.get("columns", {}) or {}
            result[title] = {k: _to_num(v.get("value", "")) for k, v in cols.items()}

        out = {
            "code": code,
            "period": period,
            "periods": [t["key"] for t in fi.get("trTitleList", [])],
            "labels": [t["title"] for t in fi.get("trTitleList", [])],
            "metrics": result,
        }
        cache.set(cache_key, out, ttl_sec=CACHE_TTL, source="naver_financials")
        return out

    def latest_metrics(self, code: str) -> dict[str, float]:
        """최근 결산 연도(컨센서스 'Y' 제외)의 재무 지표 dict."""
        data = self.fetch(code, period="annual")
        if not data:
            return {}
        # 가장 최근 실적 연도 (컨센서스 키는 미래) 찾기
        # trTitleList 의 isConsensus='N' 중 최근
        # 우리는 위에서 isConsensus 정보 안 저장했으니, periods 의 정수형 정렬 후 미래 제외
        periods = data.get("periods", [])
        if not periods:
            return {}
        import datetime
        cur_yyyymm = int(datetime.date.today().strftime("%Y%m"))
        # YYYYMM 형식 비교
        valid = [p for p in periods if int(p) <= cur_yyyymm]
        if not valid:
            valid = periods  # fallback
        latest = max(valid)
        out: dict[str, float] = {}
        for metric_name, ts in data["metrics"].items():
            if latest in ts:
                out[metric_name] = ts[latest]
        out["_period_key"] = latest
        return out

    def to_partial_financials(self, code: str, name: str, sector: str) -> dict[str, Any] | None:
        """sample_financials.json 의 raw dict 형태로 변환.

        Naver 가 직접 제공: 매출/영업이익/순이익/EPS/BPS/ROE/부채비율/배당
        Naver 가 직접 제공 X, 추정: EBITDA, FCF, 자산총계, 부채총계, 순부채

        - EBITDA ≈ 영업이익 × 1.3 (감가상각 추정)
        - FCF    ≈ 순이익 × 0.85 (워킹캐피탈/자본지출 보수적 차감)
        - 부채비율 활용해서 자산/부채 추정
        """
        m = self.latest_metrics(code)
        if not m:
            return None

        # Naver 단위:
        # 매출/영업이익/순이익/지분 등은 '억원' 단위로 보임 (예: 삼성전자 매출 3,336,059 = 약 3,336조? 실제론 333조 정도)
        # 잠시 — 삼성전자 매출 2025E = 333조 정도가 정상. Naver 데이터 3,336,059 라면 단위는 백만원 ('억원' 아님)
        # 또는 매출 333,605,900 (백만원)일 수도. 실제 값 확인 필요.
        # 임시: 1e8 (억) 가정으로 바꾸면 333조, 1e6(백만)이면 3.3조 — 1e8 이 맞음
        UNIT = 1e8  # 억원 단위 가정

        revenue        = m.get("매출액", 0) * UNIT
        operating_inc  = m.get("영업이익", 0) * UNIT
        net_income     = m.get("당기순이익", 0) * UNIT
        eps            = m.get("EPS", 0)             # 원 단위
        bps            = m.get("BPS", 0)             # 원 단위
        per            = m.get("PER", 0)
        pbr            = m.get("PBR", 0)
        roe            = m.get("ROE", 0) / 100.0     # %
        debt_ratio     = m.get("부채비율", 0) / 100.0  # %
        dps            = m.get("주당배당금", 0)         # 원

        if eps <= 0 and net_income <= 0:
            return None

        # 추정값
        ebitda  = operating_inc * 1.3 if operating_inc > 0 else 0
        fcf     = net_income * 0.85 if net_income > 0 else 0

        return {
            "ticker": code, "name": name, "sector": sector,
            "current_price": 0,                  # 가격은 별도 fetch
            "shares_outstanding": 0,             # market_value / price 로 역산 가능
            "eps": eps, "bps": bps,
            "sps": 0, "dps": dps, "roe": roe,
            "revenue": revenue,
            "operating_income": operating_inc,
            "net_income": net_income,
            "ebitda": ebitda,
            "fcf": fcf,
            "net_debt": 0,                       # 자산/부채 보강 시 계산
            "growth_rate": 0.05,                 # 추정값 (보수적)
            "_naver_period": m.get("_period_key", ""),
            "_naver_per": per,
            "_naver_pbr": pbr,
            "_naver_debt_ratio": debt_ratio,
        }
