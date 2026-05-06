"""저평가 종목 스크리너.

기준:
1) 가치평가 엔진의 fair_price 대비 upside 가 큼
2) 동시에 다음 정량 필터를 통과해야 함 (가치 함정 방지):
   - ROE >= 5%        (자본 효율성)
   - net_income > 0   (적자 제외)
   - 부채비율 양호    (net_debt/EBITDA <= 4)  ← EBITDA 0이면 통과
3) Score = 0.6*upside + 0.2*ROE + 0.2*(1 - PBR/sector_PBR)

상위 N 개를 반환.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

from ..valuation.engine import value_company, ValuationResult, Financials


@dataclass
class ScreenResult:
    valuation: ValuationResult
    score: float
    flags: list[str]
    roe: float = 0.0
    per_now: float = 0.0
    pbr_now: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["valuation"] = self.valuation.to_dict()
        return d


def _passes_filters(f: Financials) -> tuple[bool, list[str]]:
    flags: list[str] = []
    if f.roe < 0.05:
        flags.append("ROE<5%")
    if f.net_income <= 0:
        flags.append("적자")
    if f.ebitda > 0 and (f.net_debt / f.ebitda) > 4:
        flags.append("부채과다")
    return (len(flags) == 0, flags)


def _score(v: ValuationResult, f: Financials) -> float:
    upside = v.upside
    roe_score = max(min(f.roe, 0.30), 0.0) / 0.30
    pbr_now = (f.current_price / f.bps) if f.bps > 0 else 999
    pbr_disc = 1 - (pbr_now / f.sector_pbr) if f.sector_pbr > 0 else 0
    pbr_disc = max(min(pbr_disc, 1.0), -1.0)
    return round(0.6 * upside + 0.2 * roe_score + 0.2 * pbr_disc, 4)


def find_undervalued(
    financials: list[Financials],
    top_n: int = 10,
    strict: bool = True,
) -> list[ScreenResult]:
    out: list[ScreenResult] = []
    for f in financials:
        v = value_company(f)
        ok, flags = _passes_filters(f)
        if strict and not ok:
            continue
        if v.upside <= 0:
            continue
        out.append(ScreenResult(
            valuation=v,
            score=_score(v, f),
            flags=flags,
            roe=round(f.roe, 4),
            per_now=round(f.current_price / f.eps, 2) if f.eps > 0 else 0.0,
            pbr_now=round(f.current_price / f.bps, 2) if f.bps > 0 else 0.0,
        ))
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top_n]
