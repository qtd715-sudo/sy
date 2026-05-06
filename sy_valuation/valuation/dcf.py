"""Discounted Cash Flow valuation.

가정:
- FCF (Free Cash Flow) 를 g_high 로 N년간 성장 후, g_terminal 로 영구 성장
- WACC 로 할인
- 기업가치(EV) - 순부채(NetDebt) = 자기자본가치 → 주식수로 나눠 주당가치
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class DcfAssumptions:
    high_growth_years: int = 5
    g_high: float = 0.08          # 고성장기 FCF 성장률
    g_terminal: float = 0.025     # 영구 성장률 (≈ 명목 GDP)
    wacc: float = 0.09            # 가중평균자본비용

    def validate(self) -> None:
        if self.wacc <= self.g_terminal:
            raise ValueError("WACC must be greater than terminal growth rate")
        if self.high_growth_years < 1:
            raise ValueError("high_growth_years must be >= 1")


def dcf_enterprise_value(
    fcf_latest: float,
    assumptions: DcfAssumptions | None = None,
) -> float:
    a = assumptions or DcfAssumptions()
    a.validate()

    pv_explicit = 0.0
    fcf = fcf_latest
    for t in range(1, a.high_growth_years + 1):
        fcf = fcf * (1 + a.g_high)
        pv_explicit += fcf / (1 + a.wacc) ** t

    fcf_terminal = fcf * (1 + a.g_terminal)
    terminal_value = fcf_terminal / (a.wacc - a.g_terminal)
    pv_terminal = terminal_value / (1 + a.wacc) ** a.high_growth_years

    return pv_explicit + pv_terminal


def dcf_per_share(
    fcf_latest: float,
    net_debt: float,
    shares_outstanding: float,
    assumptions: DcfAssumptions | None = None,
) -> float:
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be > 0")
    ev = dcf_enterprise_value(fcf_latest, assumptions)
    equity_value = ev - net_debt
    return equity_value / shares_outstanding
