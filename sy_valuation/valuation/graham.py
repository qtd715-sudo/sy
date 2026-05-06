"""Benjamin Graham number & Graham defensive intrinsic value."""

from __future__ import annotations
import math


def graham_number(eps: float, bps: float) -> float:
    """sqrt(22.5 * EPS * BPS) — 보수적 적정주가."""
    if eps is None or bps is None or eps <= 0 or bps <= 0:
        return 0.0
    return math.sqrt(22.5 * eps * bps)


def graham_intrinsic(eps: float, growth_rate: float, aaa_yield: float = 0.045) -> float:
    """V = EPS * (8.5 + 2g) * 4.4 / Y"""
    if eps is None or eps <= 0:
        return 0.0
    g_pct = growth_rate * 100
    return eps * (8.5 + 2 * g_pct) * 4.4 / (aaa_yield * 100)
