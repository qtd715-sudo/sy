"""Naver Finance 기반 실시간 재무 데이터.

m.stock.naver.com/api/stock/{code}/integration 가 한국 종목 핵심 지표를 반환:
- per, pbr, eps, bps (개별 PER/PBR — 자동평가 핵심)
- 주식수, 시총, 매출액, 영업이익, 당기순이익
- 외인보유율, 배당수익률 등

Yahoo 대비 한국 종목 커버리지/정확도 우수.
"""

from __future__ import annotations
import re
from typing import Any

from .http_util import fetch_json
from ..valuation.engine import Financials


def _to_won(s: str) -> float:
    """'1,562조 4,180억' / '232,500' / '38,162,953' 등 → 원 단위 float."""
    if not s:
        return 0.0
    s = s.strip().replace(",", "")
    total = 0.0
    # '1조 4,180억' 형태
    if "조" in s or "억" in s or "만" in s:
        m_jo = re.search(r"([\d.]+)\s*조", s)
        if m_jo: total += float(m_jo.group(1)) * 1e12
        m_eok = re.search(r"([\d.]+)\s*억", s)
        if m_eok: total += float(m_eok.group(1)) * 1e8
        m_man = re.search(r"([\d.]+)\s*만", s)
        if m_man: total += float(m_man.group(1)) * 1e4
        return total
    # '40.71배' / '6,564원' / '0.62%' 같이 단위 붙은 숫자
    m = re.match(r"^[-]?[\d.]+", s)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return 0.0
    return 0.0


class NaverFundamentals:
    URL = "https://m.stock.naver.com/api/stock/{code}/integration"

    def __init__(self, timeout: int = 6):
        self.timeout = timeout

    def fetch(self, code: str) -> dict[str, Any] | None:
        if not code or not code.isdigit() or len(code) != 6:
            return None
        data = fetch_json(self.URL.format(code=code), timeout=self.timeout)
        if not data:
            return None
        info = {it["code"]: it.get("value", "") for it in data.get("totalInfos", [])}
        info["_stockName"] = data.get("stockName", "")
        info["_industryCode"] = data.get("industryCode", "")
        return info

    def build_financials(
        self,
        code: str,
        name: str,
        sector: str,
        sector_multiples: dict[str, float],
    ) -> Financials | None:
        info = self.fetch(code)
        if not info:
            return None

        price = _to_won(info.get("lastClosePrice", ""))
        eps = _to_won(info.get("eps", ""))
        bps = _to_won(info.get("bps", ""))
        per_now = _to_won(info.get("per", ""))
        pbr_now = _to_won(info.get("pbr", ""))
        mcap = _to_won(info.get("marketValue", ""))
        div_yield_pct = _to_won(info.get("dividendYieldRatio", ""))
        div_per_share = _to_won(info.get("dividend", ""))

        if price <= 0 or mcap <= 0:
            return None

        # 시총에서 주식수 역산 (per/pbr 기반 추정)
        shares = mcap / price if price > 0 else 0
        if shares <= 0:
            return None

        # ROE 추정: ROE = EPS / BPS
        roe = (eps / bps) if bps > 0 else 0.0
        # 매출 추정: PSR 데이터가 없으니 간이 추정 — eps × shares × 적정배수 / sector_psr
        # (없으면 0 으로 두고 PSR 모델 비활성화)
        # 성장률: 섹터 평균 가정 (5%)
        growth = 0.05

        return Financials(
            ticker=code,
            name=name or info.get("_stockName", ""),
            sector=sector or "",
            current_price=price,
            shares_outstanding=shares,
            eps=eps,
            bps=bps,
            sps=0.0,                 # Naver integration API 에는 매출 직접 없음
            dps=div_per_share,
            roe=roe,
            revenue=0.0,
            operating_income=0.0,
            net_income=eps * shares if eps > 0 else 0,
            ebitda=0.0,
            fcf=0.0,
            net_debt=0.0,
            growth_rate=growth,
            sector_per=float(sector_multiples.get("per", 12.0)),
            sector_pbr=float(sector_multiples.get("pbr", 1.0)),
            sector_psr=float(sector_multiples.get("psr", 1.0)),
            sector_ev_ebitda=float(sector_multiples.get("ev_ebitda", 8.0)),
        )
