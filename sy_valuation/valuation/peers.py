"""자동 피어 그룹 빌더.

타겟 기업과 (1) 같은 섹터, (2) 매출액 비슷한 규모 (±50% ~ ±2배)
인 기업들을 sample_financials.json 에서 골라 피어 평균 PER/PBR/PSR/EV-EBITDA 계산.

KTDS 사례: IT서비스 섹터, 매출 6,668억 → 비슷한 IT기업들과 비교.
"""

from __future__ import annotations
from typing import Any


def select_peers(
    target: dict[str, Any],
    universe: list[dict[str, Any]],
    revenue_band: tuple[float, float] = (0.3, 3.0),  # 0.3x ~ 3x
    min_peers: int = 3,
    max_peers: int = 8,
) -> list[dict[str, Any]]:
    """타겟과 같은 섹터 + 비슷한 매출 규모 기업.

    유사도 1순위: 같은 섹터.
    필터: 매출액이 target 의 (revenue_band) 배 안.
    부족하면 매출 밴드를 점진적으로 넓혀 min_peers 충족.
    """
    target_sector = target.get("sector", "")
    target_rev = float(target.get("revenue", 0) or 0)
    target_ticker = target.get("ticker")

    # 같은 섹터 후보
    same_sector = [
        c for c in universe
        if c.get("sector") == target_sector
        and c.get("ticker") != target_ticker
        and float(c.get("revenue", 0) or 0) > 0
    ]
    if not same_sector:
        return []

    # target 매출이 0 이면 섹터 전체에서 매출 가까운 N 개
    if target_rev <= 0:
        same_sector.sort(key=lambda c: float(c.get("revenue", 0) or 0))
        return same_sector[:max_peers]

    # 매출 밴드 내 기업
    lo, hi = revenue_band
    in_band = [
        c for c in same_sector
        if lo * target_rev <= float(c.get("revenue", 0) or 0) <= hi * target_rev
    ]

    # 부족하면 밴드 확장
    if len(in_band) < min_peers:
        # 매출 거리가 가까운 순으로 정렬
        same_sector.sort(key=lambda c: abs(float(c.get("revenue", 0) or 0) - target_rev))
        in_band = same_sector[:max(min_peers, max_peers)]

    # 매출 거리 가까운 순으로 정렬 후 max_peers 제한
    in_band.sort(key=lambda c: abs(float(c.get("revenue", 0) or 0) - target_rev))
    return in_band[:max_peers]


def compute_peer_multiples(peers: list[dict[str, Any]]) -> dict[str, float]:
    """피어들의 PER/PBR/PSR/EV-EBITDA 평균 (이상치 제외)."""
    pers, pbrs, psrs, evs = [], [], [], []
    for p in peers:
        price = float(p.get("current_price", 0) or 0)
        eps = float(p.get("eps", 0) or 0)
        bps = float(p.get("bps", 0) or 0)
        sps = float(p.get("sps", 0) or 0)
        ebitda = float(p.get("ebitda", 0) or 0)
        shares = float(p.get("shares_outstanding", 0) or 0)
        net_debt = float(p.get("net_debt", 0) or 0)
        mcap = price * shares
        if eps > 0 and price > 0:
            per = price / eps
            if 0 < per < 100:
                pers.append(per)
        if bps > 0 and price > 0:
            pbr = price / bps
            if 0 < pbr < 20:
                pbrs.append(pbr)
        if sps > 0 and price > 0:
            psr = price / sps
            if 0 < psr < 20:
                psrs.append(psr)
        if ebitda > 0 and mcap > 0:
            ev_eb = (mcap + net_debt) / ebitda
            if 0 < ev_eb < 50:
                evs.append(ev_eb)

    def avg(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    return {
        "per": avg(pers),
        "pbr": avg(pbrs),
        "psr": avg(psrs),
        "ev_ebitda": avg(evs),
        "n_peers": len(peers),
        "n_per": len(pers),
        "n_pbr": len(pbrs),
        "n_psr": len(psrs),
        "n_ev": len(evs),
    }


def peer_summary(peers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UI 표시용 피어 요약 (이름, PER, PBR, 매출)."""
    out = []
    for p in peers:
        price = float(p.get("current_price", 0) or 0)
        eps = float(p.get("eps", 0) or 0)
        bps = float(p.get("bps", 0) or 0)
        out.append({
            "name": p.get("name"),
            "ticker": p.get("ticker"),
            "sector": p.get("sector"),
            "revenue": float(p.get("revenue", 0) or 0),
            "per": round(price / eps, 2) if eps > 0 else None,
            "pbr": round(price / bps, 2) if bps > 0 else None,
        })
    return out
