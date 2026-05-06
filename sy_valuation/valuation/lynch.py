"""Peter Lynch fair price by PEG = 1."""

from __future__ import annotations


def lynch_fair_price(eps: float, growth_rate: float, dividend_yield: float = 0.0) -> float:
    """Fair PER = (g% + dividend_yield%) → fair price = EPS * Fair PER.
    PEG=1 가정.
    """
    if eps is None or eps <= 0:
        return 0.0
    fair_per = (growth_rate * 100) + (dividend_yield * 100)
    fair_per = max(fair_per, 0.0)
    return eps * fair_per
