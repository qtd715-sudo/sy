"""Multiples-based valuation."""

from __future__ import annotations


def per_per_share(eps: float, target_per: float) -> float:
    if eps is None or target_per is None:
        return 0.0
    if eps <= 0:
        return 0.0
    return eps * target_per


def pbr_per_share(bps: float, target_pbr: float) -> float:
    if bps is None or target_pbr is None:
        return 0.0
    if bps <= 0:
        return 0.0
    return bps * target_pbr


def psr_per_share(sps: float, target_psr: float) -> float:
    if sps is None or target_psr is None:
        return 0.0
    if sps <= 0:
        return 0.0
    return sps * target_psr


def ev_ebitda_per_share(
    ebitda: float,
    target_multiple: float,
    net_debt: float,
    shares_outstanding: float,
) -> float:
    if ebitda is None or shares_outstanding <= 0:
        return 0.0
    ev = ebitda * target_multiple
    equity = ev - net_debt
    return equity / shares_outstanding
