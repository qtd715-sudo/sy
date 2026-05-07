"""SY 평가법 — 3접근법 기업가치 평가.

세 가지 접근법으로 기업가치 범위(최소/중간/최대)를 산출:

  ┌───────────────────────────────────────────────────────────────┐
  │  1. 수익가치접근법 (Income Approach)                            │
  │     - DCF (FCFF 10년 + 영구가치)                                │
  │     - EBITDA Multiple (EBITDA × 동종 평균 EV/EBITDA)            │
  │     - 영업이익 기반 (영업이익 × 멀티플)                          │
  ├───────────────────────────────────────────────────────────────┤
  │  2. 자산가치접근법 (Asset Approach)                             │
  │     - 순자산 가치 = 자산총계 - 부채총계                          │
  │     - (옵션) 청산가치 = 순자산 × 보수계수                        │
  ├───────────────────────────────────────────────────────────────┤
  │  3. 상대가치접근법 (Market Approach)                            │
  │     - PER 비교 (피어 평균 PER × 순이익)                          │
  │     - PBR 비교 (피어 평균 PBR × 순자산)                          │
  │     - PSR 비교 (피어 평균 PSR × 매출)                            │
  └───────────────────────────────────────────────────────────────┘

  → 결론: 최소 ~ 중간 ~ 최대 기업가치 + 시총 비교
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
import statistics


@dataclass
class SyInputs:
    """SY 평가법 입력값."""
    ticker: str
    name: str
    sector: str

    # 시장 정보
    market_cap: float          # 시가총액(원)
    current_price: float = 0.0
    shares_outstanding: float = 0.0

    # 손익 (연간, 원)
    revenue: float = 0.0
    operating_income: float = 0.0
    net_income: float = 0.0
    ebitda: float = 0.0
    fcf: float = 0.0           # FCFF(자유현금흐름)

    # 재무상태 (원)
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0  # 자산-부채
    net_debt: float = 0.0

    # 성장/할인
    growth_rate_short: float = 0.025  # 5년 단기 성장률
    growth_rate_long: float = 0.025   # 6~10년
    terminal_growth: float = 0.005    # 영구성장
    wacc: float = 0.0875              # 가중평균자본비용
    forecast_years: int = 10           # 명시 예측기간 10년

    # 피어 (상대가치)
    peer_per_avg: float = 0.0
    peer_pbr_avg: float = 0.0
    peer_psr_avg: float = 0.0
    peer_ev_ebitda_avg: float = 0.0
    peers: list[dict[str, Any]] = field(default_factory=list)  # 비교군 상세

    # 보수계수
    liquidation_discount: float = 0.7  # 청산가치 = 순자산×0.7


@dataclass
class SyValuationResult:
    ticker: str
    name: str
    sector: str

    # 접근법별 산출값 (원)
    income_dcf: float = 0.0
    income_ebitda_multiple: float = 0.0
    income_op_multiple: float = 0.0
    income_min: float = 0.0
    income_mid: float = 0.0
    income_max: float = 0.0

    asset_book: float = 0.0          # 순자산
    asset_liquidation: float = 0.0   # 청산가치

    market_per: float = 0.0
    market_pbr: float = 0.0
    market_psr: float = 0.0
    market_ev_ebitda: float = 0.0
    market_min: float = 0.0
    market_mid: float = 0.0
    market_max: float = 0.0

    # 종합 기업가치 (3접근법 묶음)
    enterprise_min: float = 0.0
    enterprise_mid: float = 0.0
    enterprise_max: float = 0.0

    # 시총 대비
    market_cap: float = 0.0
    upside_min: float = 0.0    # (mid - mcap) / mcap
    upside_mid: float = 0.0
    upside_max: float = 0.0
    rating: str = "HOLD"

    # 주당 환산 (기업가치 / 발행주식수)
    shares_outstanding: float = 0.0
    current_price: float = 0.0
    fair_price_min: float = 0.0       # enterprise_min / shares
    fair_price_mid: float = 0.0       # enterprise_mid / shares  ★ 주당 적정가
    fair_price_max: float = 0.0       # enterprise_max / shares
    upside_per_share: float = 0.0     # (fair_price_mid - current_price) / current_price

    notes: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    detail_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -------- 1) 수익가치접근법 --------

def dcf_fcff(inp: SyInputs) -> tuple[float, list[dict[str, float]]]:
    """FCFF 10년 명시기간 + 영구가치.
    리턴: (기업가치, 연도별 표)
    """
    if inp.fcf <= 0 or inp.wacc <= inp.terminal_growth:
        return 0.0, []
    rows = []
    pv_total = 0.0
    fcff = inp.fcf
    for t in range(1, inp.forecast_years + 1):
        g = inp.growth_rate_short if t <= 5 else inp.growth_rate_long
        fcff = fcff * (1 + g)
        pv = fcff / (1 + inp.wacc) ** t
        pv_total += pv
        rows.append({"year": 2023 + t, "fcff": fcff, "pv": pv, "g": g})
    fcff_terminal = fcff * (1 + inp.terminal_growth)
    tv = fcff_terminal / (inp.wacc - inp.terminal_growth)
    pv_tv = tv / (1 + inp.wacc) ** inp.forecast_years
    rows.append({"year": "terminal", "fcff": fcff_terminal, "pv": pv_tv, "g": inp.terminal_growth})
    return pv_total + pv_tv, rows


def ebitda_multiple(inp: SyInputs) -> float:
    if inp.ebitda <= 0 or inp.peer_ev_ebitda_avg <= 0:
        return 0.0
    return inp.ebitda * inp.peer_ev_ebitda_avg


def op_income_multiple(inp: SyInputs, mult: float = 10.0) -> float:
    if inp.operating_income <= 0:
        return 0.0
    return inp.operating_income * mult


# -------- 2) 자산가치접근법 --------

def asset_book(inp: SyInputs) -> float:
    if inp.total_equity > 0:
        return inp.total_equity
    if inp.total_assets > 0:
        return inp.total_assets - max(inp.total_liabilities, 0)
    return 0.0


# -------- 3) 상대가치접근법 --------

def market_per(inp: SyInputs) -> float:
    if inp.peer_per_avg <= 0 or inp.net_income <= 0:
        return 0.0
    return inp.net_income * inp.peer_per_avg


def market_pbr(inp: SyInputs) -> float:
    eq = asset_book(inp)
    if eq <= 0 or inp.peer_pbr_avg <= 0:
        return 0.0
    return eq * inp.peer_pbr_avg


def market_psr(inp: SyInputs) -> float:
    if inp.revenue <= 0 or inp.peer_psr_avg <= 0:
        return 0.0
    return inp.revenue * inp.peer_psr_avg


def market_ev_ebitda(inp: SyInputs) -> float:
    if inp.ebitda <= 0 or inp.peer_ev_ebitda_avg <= 0:
        return 0.0
    return inp.ebitda * inp.peer_ev_ebitda_avg - inp.net_debt


# -------- 종합 --------

def _rating(upside_mid: float) -> str:
    if upside_mid >= 2.0:    return "STRONG_BUY"
    if upside_mid >= 0.50:   return "BUY"
    if upside_mid >= 0.10:   return "ACCUMULATE"
    if upside_mid >= -0.10:  return "HOLD"
    return "SELL"


def evaluate_sy(inp: SyInputs) -> SyValuationResult:
    notes: list[str] = []

    # 1) 수익가치
    dcf_val, dcf_rows = dcf_fcff(inp)
    eb_mult = ebitda_multiple(inp)
    op_mult = op_income_multiple(inp)
    income_vals = [v for v in (dcf_val, eb_mult, op_mult) if v > 0]
    income_min = min(income_vals) if income_vals else 0.0
    income_max = max(income_vals) if income_vals else 0.0
    income_mid = statistics.median(income_vals) if income_vals else 0.0
    if not income_vals:
        notes.append("수익가치: 계산 가능한 모델 없음 (FCF/EBITDA/영업이익 부족)")

    # 2) 자산가치
    book = asset_book(inp)
    liq = book * inp.liquidation_discount if book > 0 else 0.0

    # 3) 상대가치
    per_v = market_per(inp)
    pbr_v = market_pbr(inp)
    psr_v = market_psr(inp)
    ev_v  = market_ev_ebitda(inp)
    market_vals = [v for v in (per_v, pbr_v, psr_v, ev_v) if v > 0]
    if not market_vals:
        notes.append("상대가치: 피어 데이터 부족")
    market_min = min(market_vals) if market_vals else 0.0
    market_max = max(market_vals) if market_vals else 0.0
    market_mid = statistics.median(market_vals) if market_vals else 0.0

    # 종합: 3접근법의 min/mid/max 묶음
    all_mins = [v for v in (income_min, book, market_min) if v > 0]
    all_mids = [v for v in (income_mid, book, market_mid) if v > 0]
    all_maxs = [v for v in (income_max, book, market_max) if v > 0]
    enterprise_min = min(all_mins) if all_mins else 0.0
    enterprise_mid = statistics.median(all_mids) if all_mids else 0.0
    enterprise_max = max(all_maxs) if all_maxs else 0.0

    mcap = max(inp.market_cap, 1.0)
    upside_min = (enterprise_min - mcap) / mcap
    upside_mid = (enterprise_mid - mcap) / mcap
    upside_max = (enterprise_max - mcap) / mcap

    # 주당 환산
    shares = inp.shares_outstanding or (mcap / inp.current_price if inp.current_price > 0 else 0)
    fair_min_ps = enterprise_min / shares if shares > 0 else 0
    fair_mid_ps = enterprise_mid / shares if shares > 0 else 0
    fair_max_ps = enterprise_max / shares if shares > 0 else 0
    upside_ps = (fair_mid_ps - inp.current_price) / inp.current_price if inp.current_price > 0 else 0

    detail_rows = [
        {"approach": "수익가치", "method": "DCF (FCFF 10y)",        "value": dcf_val},
        {"approach": "수익가치", "method": "EBITDA × peer 멀티플",  "value": eb_mult},
        {"approach": "수익가치", "method": "영업이익 × 10x",         "value": op_mult},
        {"approach": "자산가치", "method": "순자산 (자산-부채)",      "value": book},
        {"approach": "자산가치", "method": "청산가치 (×0.7)",         "value": liq},
        {"approach": "상대가치", "method": "PER × 순이익",            "value": per_v},
        {"approach": "상대가치", "method": "PBR × 순자산",            "value": pbr_v},
        {"approach": "상대가치", "method": "PSR × 매출",              "value": psr_v},
        {"approach": "상대가치", "method": "EV/EBITDA × EBITDA - 순부채", "value": ev_v},
    ]

    return SyValuationResult(
        ticker=inp.ticker, name=inp.name, sector=inp.sector,
        income_dcf=round(dcf_val, 0),
        income_ebitda_multiple=round(eb_mult, 0),
        income_op_multiple=round(op_mult, 0),
        income_min=round(income_min, 0),
        income_mid=round(income_mid, 0),
        income_max=round(income_max, 0),
        asset_book=round(book, 0),
        asset_liquidation=round(liq, 0),
        market_per=round(per_v, 0),
        market_pbr=round(pbr_v, 0),
        market_psr=round(psr_v, 0),
        market_ev_ebitda=round(ev_v, 0),
        market_min=round(market_min, 0),
        market_mid=round(market_mid, 0),
        market_max=round(market_max, 0),
        enterprise_min=round(enterprise_min, 0),
        enterprise_mid=round(enterprise_mid, 0),
        enterprise_max=round(enterprise_max, 0),
        market_cap=round(mcap, 0),
        upside_min=round(upside_min, 4),
        upside_mid=round(upside_mid, 4),
        upside_max=round(upside_max, 4),
        rating=_rating(upside_mid),
        shares_outstanding=round(shares, 0),
        current_price=round(inp.current_price, 0),
        fair_price_min=round(fair_min_ps, 0),
        fair_price_mid=round(fair_mid_ps, 0),
        fair_price_max=round(fair_max_ps, 0),
        upside_per_share=round(upside_ps, 4),
        notes=notes,
        inputs=asdict(inp),
        detail_rows=[
            {**r, "value": round(r["value"], 0)} for r in detail_rows
        ],
    )
