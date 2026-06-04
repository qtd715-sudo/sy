"""SyInputs 빌더.

샘플 financials 의 보강 필드(자산/부채/시총/피어 평균)가 있으면 그대로 사용,
없으면 합리적 추정으로 채움.

피어 평균이 raw 에 없으면 universe(전체 sample) 에서 자동 선정 — 같은 섹터 +
매출 0.3x~3x 범위 기업들로 평균 PER/PBR/PSR/EV-EBITDA 계산.
"""

from __future__ import annotations
from typing import Any

from .sy_method import (
    SyInputs, calculate_wacc, calculate_growth_rate,
    CAPM_RF, CAPM_BETA_DEFAULT, CAPM_MRP, CORPORATE_TAX_RATE,
)
from .peers import select_peers, compute_peer_multiples, peer_summary, enrich_peers_with_naver


# 섹터별 베타 (DART 미수집 시 폴백 값. Yahoo β 받아오면 그것 우선).
# KOSPI 5년 회귀 기반 추정.
SECTOR_BETA = {
    "반도체": 1.20, "IT서비스": 1.05, "자동차": 1.10, "2차전지": 1.35,
    "바이오": 1.40, "은행": 0.85, "통신": 0.70, "유통": 0.90,
    "철강": 1.10, "조선": 1.30, "에너지": 1.05, "엔터": 1.25,
    "기술": 1.10, "가상자산": 2.00,
}

# 폴백 WACC (DART/시총 데이터 부재 시)
FALLBACK_WACC = 0.0875


def build_inputs_from_raw(
    raw: dict[str, Any],
    sector_multiples: dict[str, float],
    universe: list[dict[str, Any]] | None = None,
    naver_fetcher: Any = None,
    cache: Any = None,
) -> SyInputs:
    """sample_financials 의 raw dict (회사 1건) → SyInputs.

    universe 가 주어지면 자동 피어 선정 (같은 섹터 + 비슷한 매출 규모).
    naver_fetcher 가 주어지면 피어 후보 중 재무 데이터 부재 항목을
    Naver fundamentals 로 lazy enrich (캐시 24h TTL).
    """
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

    # 피어 멀티플 결정 우선순위:
    # 1) raw 에 명시 (사용자가 직접 지정한 경우)
    # 2) universe 에서 자동 선정 (같은 섹터 + 매출 비슷)
    # 3) sector_multiples (섹터 표준값)
    auto_peers: list[dict[str, Any]] = []
    auto_mults: dict[str, float] = {}
    if universe and not raw.get("peers"):
        auto_peers = select_peers(raw, universe)
        # 후보가 DART-only (재무 데이터 없음) 이면 Naver 로 보강
        if naver_fetcher and any(
            float(p.get("current_price", 0) or 0) <= 0 or float(p.get("bps", 0) or 0) <= 0
            for p in auto_peers
        ):
            auto_peers = enrich_peers_with_naver(auto_peers, naver_fetcher, cache=cache)
        auto_mults = compute_peer_multiples(auto_peers)

    def _pick(key_user: str, key_auto: str, default_key: str, default_value: float) -> float:
        if raw.get(key_user):
            return float(raw[key_user])
        if auto_mults.get(key_auto):
            return float(auto_mults[key_auto])
        return float(sector_multiples.get(default_key, default_value))

    peer_per = _pick("peer_per_avg",       "per",       "per",       12.0)
    peer_pbr = _pick("peer_pbr_avg",       "pbr",       "pbr",        1.0)
    peer_psr = _pick("peer_psr_avg",       "psr",       "psr",        1.0)
    peer_ev  = _pick("peer_ev_ebitda_avg", "ev_ebitda", "ev_ebitda",  8.0)

    # 피어 정보 (UI 표시용)
    peers_info = raw.get("peers") or peer_summary(auto_peers)

    # ─── WACC 동적 계산 (CAPM 기반) ──────────────────────────────────────
    # 1) Tc: DART 법인세비용/영업이익. 없으면 CORPORATE_TAX_RATE(22%).
    tax_expense = float(raw.get("tax_expense", 0) or 0)
    interest_expense = float(raw.get("interest_expense", 0) or 0)
    if tax_expense > 0 and op_inc > 0:
        tax_rate = min(max(tax_expense / op_inc, 0.10), 0.30)
    else:
        tax_rate = CORPORATE_TAX_RATE
    # 2) β: raw 명시 > 섹터 베타 > 1.0
    beta = float(raw.get("beta") or SECTOR_BETA.get(sector, CAPM_BETA_DEFAULT))
    # 3) WACC: raw 명시 > CAPM 동적 계산 > 폴백 8.75%
    if raw.get("wacc"):
        wacc = float(raw["wacc"])
    elif mcap > 0:
        wacc = calculate_wacc(
            market_cap=mcap,
            net_debt=net_debt,
            interest_expense=interest_expense,
            tax_rate=tax_rate,
            beta=beta,
        )
    else:
        wacc = FALLBACK_WACC

    # ─── 성장률 동적 계산 (ROE × retention) ───────────────────────────────
    # raw.growth_rate 명시 시 우선. 없으면 ROE × (1 - payout) 로 단기 g 산출.
    # 장기는 단기의 절반으로 감속 (성숙기 가정), terminal 은 한국 GDP 추세 2.5%.
    payout = float(raw.get("dividend_payout_ratio", 0.30) or 0.30)
    if raw.get("growth_rate"):
        growth_short = min(max(float(raw["growth_rate"]), 0.0), 0.20)
    else:
        growth_short = calculate_growth_rate(
            net_income=net_income,
            total_equity=total_equity,
            dividend_payout_ratio=payout,
        )
    growth_long = growth_short * 0.5  # 후반 5년은 절반으로 감속
    terminal_growth = 0.025            # 한국 GDP 추세 (설계서 v2.0)

    # 기초 재무 데이터의 회계연도 (DART _dart_year, 예: "2025") — DCF 투영 연도 라벨용.
    # 없으면 0 → dcf_fcff 가 현재연도-1 로 폴백.
    _dy = raw.get("_dart_year")
    try:
        base_year = int(_dy) if _dy else 0
    except (ValueError, TypeError):
        base_year = 0

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
        # WACC 입력 (UI 표시·재계산용)
        interest_expense=interest_expense,
        tax_rate=tax_rate,
        beta=beta,
        risk_free_rate=CAPM_RF,
        market_risk_premium=CAPM_MRP,
        # 자산가치접근법 강화용 세부 자산 (OpenDart 보강 — 없으면 0)
        current_assets=float(raw.get("current_assets", 0) or 0),
        tangible_assets=float(raw.get("tangible_assets", 0) or 0),
        intangible_assets=float(raw.get("intangible_assets", 0) or 0),
        inventory=float(raw.get("inventory", 0) or 0),
        receivables=float(raw.get("receivables", 0) or 0),
        investment_assets=float(raw.get("investment_assets", 0) or 0),
        cash_equivalents=float(raw.get("cash_equivalents", 0) or 0),
        growth_rate_short=growth_short,
        growth_rate_long=growth_long,
        terminal_growth=terminal_growth,
        wacc=wacc,
        forecast_years=10,
        base_year=base_year,
        dividend_payout_ratio=payout,
        peer_per_avg=peer_per,
        peer_pbr_avg=peer_pbr,
        peer_psr_avg=peer_psr,
        peer_ev_ebitda_avg=peer_ev,
        peers=peers_info,
    )
