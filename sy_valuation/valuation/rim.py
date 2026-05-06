"""Residual Income Model (잔여이익모형).

장부가치 BPS + Σ (ROE - 자본비용) * BPS 의 현가
한국 가치투자에서 자주 쓰는 모델 (S-RIM 포함).
"""

from __future__ import annotations


def rim_per_share(
    bps: float,
    roe: float,
    cost_of_equity: float = 0.085,
    persistence: float = 0.9,   # S-RIM 잔여이익 지속계수
    horizon: int = 10,
) -> float:
    """S-RIM 방식: 초과이익이 매년 persistence 비율로 감쇠한다고 가정."""
    if bps <= 0:
        return 0.0
    excess_return = roe - cost_of_equity
    if excess_return <= 0:
        return bps  # 초과이익 없음 → 청산가치 수준

    # excess earnings per share at year 1
    ex_t = bps * excess_return
    pv = 0.0
    for t in range(1, horizon + 1):
        pv += ex_t / (1 + cost_of_equity) ** t
        ex_t *= persistence

    # 영구가치 (잔존 초과이익이 지속계수로 영구 감쇠)
    if persistence < 1:
        terminal_excess = ex_t / (1 + cost_of_equity - persistence)
        pv_terminal = terminal_excess / (1 + cost_of_equity) ** horizon
        pv += pv_terminal

    return bps + pv
