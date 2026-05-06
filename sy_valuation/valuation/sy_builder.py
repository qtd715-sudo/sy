"""SyInputs 빌더.

샘플 financials 의 보강 필드(자산/부채/시총/피어 평균)가 있으면 그대로 사용,
없으면 합리적 추정으로 채움.
"""

from __future__ import annotations
from typing import Any

from .sy_method import SyInputs


# 섹터별 표준 WACC (KOSPI 평균 기반 추정. KTDS 사례 2.15% 처럼 자본구조 우호 기업은 별도 입력)
SECTOR_WACC = {
    "반도체": 0.085, "IT서비스": 0.090, "자동차": 0.095, "2차전지": 0.100,
    "바이오": 0.110, "은행": 0.075, "통신": 0.070, "유통": 0.085,
    "철강": 0.085, "조선": 0.095, "에너지": 0.090, "엔터": 0.105,
    "기술": 0.090, "가상자산": 0.150,
}


def build_inputs_from_raw(raw: dict[str, Any], sector_multiples: dict[str, float]) -> SyInputs:
    """sample_financials 의 raw dict (회사 1건) → SyInputs."""
    name = raw["name"]
    sector = raw["sector"]
    price = float(raw.get("current_price", 0))
    shares = float(raw.get("shares_outstanding", 0))
    mcap = float(raw.get("market_cap") or (price * shares))

    bps = float(raw.get("bps", 0))
    revenue = float(raw.get("revenue", 0))
    net_income = float(raw.get("net_income", 0))
    ebitda = float(raw.get("ebitda", 0))
    fcf = float(raw.get("fcf", 0))
    op_inc = float(raw.get("operating_income", 0))
    net_debt = float(raw.get("net_debt", 0))

    # 자산/부채: 보강 필드 우선, 없으면 BPS 기반 추정
    total_equity = float(raw.get("total_equity") or (bps * shares if bps > 0 and shares > 0 else 0))
    total_assets = float(raw.get("total_assets") or 0)
    total_liab = float(raw.get("total_liabilities") or 0)
    if total_assets <= 0 and total_equity > 0 and net_debt:
        total_assets = total_equity + max(net_debt, 0) * 1.5
    if total_liab <= 0 and total_assets > 0 and total_equity > 0:
        total_liab = max(total_assets - total_equity, 0)

    # 피어 멀티플: raw에 없으면 sector_multiples 사용
    peer_per = float(raw.get("peer_per_avg") or sector_multiples.get("per", 12.0))
    peer_pbr = float(raw.get("peer_pbr_avg") or sector_multiples.get("pbr", 1.0))
    peer_psr = float(raw.get("peer_psr_avg") or sector_multiples.get("psr", 1.0))
    peer_ev = float(raw.get("peer_ev_ebitda_avg") or sector_multiples.get("ev_ebitda", 8.0))

    wacc = float(raw.get("wacc") or SECTOR_WACC.get(sector, 0.0875))
    growth_short = float(raw.get("growth_rate") or 0.025)
    if growth_short > 0.30:
        growth_short = 0.30  # 비현실적 성장률 캡

    return SyInputs(
        ticker=raw["ticker"],
        name=name,
        sector=sector,
        market_cap=mcap,
        current_price=price,
        shares_outstanding=shares,
        revenue=revenue,
        operating_income=op_inc,
        net_income=net_income,
        ebitda=ebitda,
        fcf=fcf,
        total_assets=total_assets,
        total_liabilities=total_liab,
        total_equity=total_equity,
        net_debt=net_debt,
        growth_rate_short=growth_short,
        growth_rate_long=min(growth_short, 0.05),
        terminal_growth=0.005,
        wacc=wacc,
        forecast_years=10,
        peer_per_avg=peer_per,
        peer_pbr_avg=peer_pbr,
        peer_psr_avg=peer_psr,
        peer_ev_ebitda_avg=peer_ev,
        peers=raw.get("peers", []),
    )
