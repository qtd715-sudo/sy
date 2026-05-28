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


# ─── CAPM/WACC 표준 파라미터 (설계서 v2.0 기준) ────────────────────────────
# Rf: 한국은행 국채 3년 (2026-05 기준 ~2.59%)
# MRP: KOSPI 5년 평균 시장프리미엄 (~4.75%)
# β:  Yahoo Finance 측 베타. 미수집 시 1.0 가정
# Tc: 한국 법인세 실효세율 22% (DART 데이터 있으면 종목별 재계산)
CAPM_RF = 0.0259
CAPM_BETA_DEFAULT = 1.0
CAPM_MRP = 0.0475
CORPORATE_TAX_RATE = 0.22


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
    fcf: float = 0.0           # FCFF(자유현금흐름) — 정통 공식: EBIT(1-Tc)+감가-CapEx-ΔWC

    # 재무상태 (원)
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0  # 자산-부채
    net_debt: float = 0.0

    # WACC 동적 계산용 입력 (DART 가용 시 사용)
    interest_expense: float = 0.0     # 이자비용 (Rd 추정)
    tax_rate: float = CORPORATE_TAX_RATE  # 실효세율 (DART: 법인세비용/영업이익)
    beta: float = CAPM_BETA_DEFAULT       # 베타 (외부 입력 가능)
    risk_free_rate: float = CAPM_RF
    market_risk_premium: float = CAPM_MRP

    # 자산 세부 (자산가치접근법 강화용 — OpenDart 재무상태표)
    current_assets: float = 0.0       # 유동자산
    tangible_assets: float = 0.0      # 유형자산
    intangible_assets: float = 0.0    # 무형자산 (영업권/브랜드 등)
    inventory: float = 0.0            # 재고자산
    receivables: float = 0.0          # 매출채권
    investment_assets: float = 0.0    # 투자부동산
    cash_equivalents: float = 0.0     # 현금및현금성자산

    # 성장/할인
    growth_rate_short: float = 0.05   # 5년 단기 성장률 (ROE×(1-payout) 로 동적 산출)
    growth_rate_long: float = 0.03    # 6~10년
    terminal_growth: float = 0.025    # 영구성장
    wacc: float = 0.0875              # 가중평균자본비용 (동적 계산 결과 또는 폴백)
    forecast_years: int = 10           # 명시 예측기간 10년
    dividend_payout_ratio: float = 0.30  # 배당성향 (ROE 성장률 산식용)

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

    asset_book: float = 0.0          # 순자산 (자본총계 또는 자산-부채)
    asset_liquidation: float = 0.0   # 청산가치 = 순자산 × liquidation_discount
    asset_adjusted_nav: float = 0.0  # 조정 순자산 — 자산을 항목별 보수계수로 재평가 후 부채 차감
    asset_nnwc: float = 0.0          # 순현금자산(Net-Net Working Capital, 그레이엄식) = 유동자산 - 총부채
    asset_min: float = 0.0           # 자산접근법 min/mid/max
    asset_mid: float = 0.0
    asset_max: float = 0.0

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


# -------- WACC 동적 계산 (CAPM 기반) --------

def calculate_wacc(
    market_cap: float,
    net_debt: float,
    interest_expense: float,
    tax_rate: float = CORPORATE_TAX_RATE,
    beta: float = CAPM_BETA_DEFAULT,
    rf: float = CAPM_RF,
    mrp: float = CAPM_MRP,
) -> float:
    """WACC = (E/V × Re) + (D/V × Rd × (1-Tc))

    Re = Rf + β × MRP                              (CAPM)
    Rd = interest_expense / net_debt               (DART)  부재 시 Rf × 1.5
    가중치는 시가총액(E) 와 순부채(D, 0 이상) 로.
    결과는 5%~15% 범위로 클립 (이상치 차단).
    """
    # 자기자본비용
    re = rf + beta * mrp

    # 타인자본비용
    d_pos = max(net_debt, 0.0)
    if d_pos > 0 and interest_expense > 0:
        rd = interest_expense / d_pos
    else:
        rd = rf * 1.5
    rd_after_tax = rd * (1 - tax_rate)

    total_value = market_cap + d_pos
    if total_value <= 0:
        return 0.0875  # 폴백 — 입력 부적합 시 표준 8.75%

    we = market_cap / total_value
    wd = d_pos / total_value
    wacc = we * re + wd * rd_after_tax

    # 안전 범위 클립
    return min(max(wacc, 0.05), 0.15)


def calculate_growth_rate(
    net_income: float,
    total_equity: float,
    dividend_payout_ratio: float = 0.30,
    cap: float = 0.20,
) -> float:
    """지속가능 성장률 g = ROE × (1 - payout).

    내부 자본만으로 달성 가능한 성장률 (sustainable growth rate).
    cap 으로 비현실적 값 차단 (기본 20%).
    """
    if total_equity <= 0 or net_income <= 0:
        return 0.05  # 폴백 — 데이터 부족 시 시장 평균 5%
    roe = net_income / total_equity
    retention = 1 - dividend_payout_ratio
    g = roe * retention
    return min(max(g, 0.0), cap)


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
# 4가지 방법으로 자산가치 범위 산출:
#   ① 순자산(Book NAV)         = 자본총계 (자산-부채)
#   ② 청산가치(Liquidation)     = 순자산 × liquidation_discount(기본 0.7)
#   ③ 조정 순자산(Adjusted NAV) = 항목별 보수계수 재평가 후 부채 차감
#                                  유형자산 ×1.0 + 투자부동산 ×0.9 + 현금 ×1.0
#                                  + 매출채권 ×0.85 + 재고자산 ×0.7 + 무형자산 ×0.5
#                                  + 기타(잔여) ×0.5  −  총부채
#   ④ 순현금자산(NNWC, Graham)  = 유동자산 − 총부채

# 자산 항목별 보수계수 (장부가 → 현실 회수가치)
ASSET_HAIRCUTS = {
    "tangible":   1.00,  # 유형자산 (현물 — 시장가 추정 어려워 장부가 유지)
    "investment": 0.90,  # 투자부동산 (10% 할인)
    "cash":       1.00,  # 현금성자산
    "receivable": 0.85,  # 매출채권 (대손 15%)
    "inventory":  0.70,  # 재고자산 (할인판매 30%)
    "intangible": 0.50,  # 무형자산 (영업권/브랜드는 보수적으로 절반만 인정)
    "other":      0.50,  # 잔여(기타 비유동자산 등) — 50% 인정
}


def asset_book(inp: SyInputs) -> float:
    """① 순자산 = 자본총계 (또는 자산총계 − 부채총계)."""
    if inp.total_equity > 0:
        return inp.total_equity
    if inp.total_assets > 0:
        return inp.total_assets - max(inp.total_liabilities, 0)
    return 0.0


def asset_adjusted_nav(inp: SyInputs) -> float:
    """③ 조정 순자산 — OpenDart 세부 자산 항목별 보수계수 재평가.

    자산을 다음 6 카테고리로 분해 후 보수계수 적용 → 합산 → 부채 차감:
      - 유형자산(1.0), 투자부동산(0.9), 현금(1.0),
        매출채권(0.85), 재고자산(0.7), 무형자산(0.5),
        그 외 잔여(기타 자산) 0.5
    세부 자산 데이터 부족 시 0 반환 (장부 NAV로 대체 가능).
    """
    h = ASSET_HAIRCUTS
    classified = (
        inp.tangible_assets
        + inp.intangible_assets
        + inp.inventory
        + inp.receivables
        + inp.investment_assets
        + inp.cash_equivalents
    )
    # 세부 자산이 모두 0이면 조정 NAV 계산 불가
    if classified <= 0:
        return 0.0

    adjusted = (
        inp.tangible_assets   * h["tangible"]
        + inp.investment_assets * h["investment"]
        + inp.cash_equivalents  * h["cash"]
        + inp.receivables       * h["receivable"]
        + inp.inventory         * h["inventory"]
        + inp.intangible_assets * h["intangible"]
    )
    # 자산총계와 분류된 자산의 차이 = 기타 자산 → 50% 보수
    if inp.total_assets > 0:
        other = max(inp.total_assets - classified, 0.0)
        adjusted += other * h["other"]

    nav = adjusted - max(inp.total_liabilities, 0.0)
    return max(nav, 0.0)


def asset_nnwc(inp: SyInputs) -> float:
    """④ 순현금자산(Net-Net Working Capital) — 벤저민 그레이엄.

    유동자산 − 총부채 (가장 보수적인 자산가치 — 청산 시 즉시 회수 가능 자산만).
    음수면 0 반환.
    """
    if inp.current_assets <= 0 or inp.total_liabilities < 0:
        return 0.0
    return max(inp.current_assets - inp.total_liabilities, 0.0)


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

# 투자 등급 기준 (설계서 v2.0):
#   STRONG_BUY  ≥ +30%
#   BUY         +15% ~ +30%
#   ACCUMULATE  +5%  ~ +15%
#   HOLD        -5%  ~ +5%
#   REDUCE      -15% ~ -5%
#   SELL        -30% ~ -15%
#   STRONG_SELL < -30%
RATING_THRESHOLDS = [
    (0.30,  "STRONG_BUY"),
    (0.15,  "BUY"),
    (0.05,  "ACCUMULATE"),
    (-0.05, "HOLD"),
    (-0.15, "REDUCE"),
    (-0.30, "SELL"),
]


def _rating(upside_mid: float) -> str:
    for threshold, label in RATING_THRESHOLDS:
        if upside_mid >= threshold:
            return label
    return "STRONG_SELL"


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

    # 2) 자산가치 — 4가지 방법
    book = asset_book(inp)
    liq = book * inp.liquidation_discount if book > 0 else 0.0
    adj_nav = asset_adjusted_nav(inp)
    nnwc = asset_nnwc(inp)
    asset_vals = [v for v in (book, liq, adj_nav, nnwc) if v > 0]
    asset_lo = min(asset_vals) if asset_vals else 0.0
    asset_md = statistics.median(asset_vals) if asset_vals else 0.0
    asset_hi = max(asset_vals) if asset_vals else 0.0
    if not asset_vals:
        notes.append("자산가치: 재무상태표 데이터 부족")
    elif adj_nav <= 0 and (inp.tangible_assets + inp.intangible_assets + inp.inventory) <= 0:
        notes.append("자산가치 — 조정 NAV: OpenDart 자산 세부 항목 부족, 장부 NAV로 대체")

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

    # 종합: 3접근법의 min/mid/max 묶음 (자산은 새 min/mid/max 범위 사용)
    all_mins = [v for v in (income_min, asset_lo, market_min) if v > 0]
    all_mids = [v for v in (income_mid, asset_md, market_mid) if v > 0]
    all_maxs = [v for v in (income_max, asset_hi, market_max) if v > 0]
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
        {"approach": "자산가치", "method": f"청산가치 (×{inp.liquidation_discount:.2f})", "value": liq},
        {"approach": "자산가치", "method": "조정 NAV (항목별 보수계수)", "value": adj_nav},
        {"approach": "자산가치", "method": "순현금자산(NNWC, Graham)",  "value": nnwc},
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
        asset_adjusted_nav=round(adj_nav, 0),
        asset_nnwc=round(nnwc, 0),
        asset_min=round(asset_lo, 0),
        asset_mid=round(asset_md, 0),
        asset_max=round(asset_hi, 0),
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
