"""Valuation orchestrator: combines models with weights → fair price."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

from .dcf import dcf_per_share, DcfAssumptions
from .rim import rim_per_share
from .multiples import (
    per_per_share, pbr_per_share, psr_per_share, ev_ebitda_per_share,
)
from .graham import graham_number, graham_intrinsic
from .lynch import lynch_fair_price


# 모델별 기본 가중치 (합이 1.0 이 아니어도 정규화됨)
DEFAULT_WEIGHTS: dict[str, float] = {
    "dcf": 0.20,
    "rim": 0.20,
    "per": 0.15,
    "pbr": 0.10,
    "psr": 0.05,
    "ev_ebitda": 0.10,
    "graham_number": 0.05,
    "graham_intrinsic": 0.05,
    "lynch": 0.10,
}


@dataclass
class Financials:
    ticker: str
    name: str
    sector: str
    current_price: float
    shares_outstanding: float
    eps: float                 # 주당순이익
    bps: float                 # 주당순자산
    sps: float                 # 주당매출
    dps: float                 # 주당배당금
    roe: float                 # 자기자본이익률
    revenue: float
    operating_income: float
    net_income: float
    ebitda: float
    fcf: float
    net_debt: float            # 순차입금 = 차입금 - 현금성자산
    growth_rate: float         # 향후 5y EPS CAGR 추정치
    sector_per: float
    sector_pbr: float
    sector_psr: float
    sector_ev_ebitda: float


@dataclass
class ValuationResult:
    ticker: str
    name: str
    sector: str
    current_price: float
    fair_price: float          # 가중평균 적정가
    upside: float              # (fair - current) / current
    rating: str                # STRONG_BUY / BUY / HOLD / SELL
    by_model: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rating(upside: float) -> str:
    if upside >= 0.30:
        return "STRONG_BUY"
    if upside >= 0.10:
        return "BUY"
    if upside >= -0.10:
        return "HOLD"
    return "SELL"


def value_company(
    f: Financials,
    weights: dict[str, float] | None = None,
    dcf_assumptions: DcfAssumptions | None = None,
    cost_of_equity: float = 0.085,
) -> ValuationResult:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    by_model: dict[str, float] = {}
    notes: list[str] = []

    # DCF
    try:
        by_model["dcf"] = dcf_per_share(
            f.fcf, f.net_debt, f.shares_outstanding, dcf_assumptions,
        )
    except Exception as e:
        notes.append(f"DCF skipped: {e}")
        w["dcf"] = 0.0

    # RIM
    by_model["rim"] = rim_per_share(f.bps, f.roe, cost_of_equity)
    if by_model["rim"] <= 0:
        w["rim"] = 0.0

    # Multiples (sector medians as targets)
    by_model["per"] = per_per_share(f.eps, f.sector_per)
    by_model["pbr"] = pbr_per_share(f.bps, f.sector_pbr)
    by_model["psr"] = psr_per_share(f.sps, f.sector_psr)
    by_model["ev_ebitda"] = ev_ebitda_per_share(
        f.ebitda, f.sector_ev_ebitda, f.net_debt, f.shares_outstanding,
    )

    # Graham
    by_model["graham_number"] = graham_number(f.eps, f.bps)
    by_model["graham_intrinsic"] = graham_intrinsic(f.eps, f.growth_rate)

    # Lynch
    div_yield = (f.dps / f.current_price) if f.current_price > 0 else 0.0
    by_model["lynch"] = lynch_fair_price(f.eps, f.growth_rate, div_yield)

    # 0인 모델은 가중치에서 제외
    for k in list(w.keys()):
        if by_model.get(k, 0.0) <= 0:
            w[k] = 0.0

    total_w = sum(w.values())
    if total_w <= 0:
        notes.append("모든 모델이 산출 불가 → 적정가 0")
        return ValuationResult(
            ticker=f.ticker, name=f.name, sector=f.sector,
            current_price=f.current_price, fair_price=0.0,
            upside=-1.0, rating="SELL", by_model=by_model,
            weights=w, notes=notes,
        )

    norm_w = {k: v / total_w for k, v in w.items()}
    fair = sum(by_model[k] * norm_w.get(k, 0.0) for k in by_model)

    upside = (fair - f.current_price) / f.current_price if f.current_price > 0 else 0.0

    return ValuationResult(
        ticker=f.ticker, name=f.name, sector=f.sector,
        current_price=f.current_price,
        fair_price=round(fair, 2),
        upside=round(upside, 4),
        rating=_rating(upside),
        by_model={k: round(v, 2) for k, v in by_model.items()},
        weights={k: round(v, 4) for k, v in norm_w.items()},
        notes=notes,
    )
