"""자동 피어 그룹 빌더.

타겟 기업과 (1) 같은 섹터, (2) 매출액 비슷한 규모 (±50% ~ ±2배)
인 기업들을 sample_financials.json 에서 골라 피어 평균 PER/PBR/PSR/EV-EBITDA 계산.

예: IT서비스 섹터 + 매출 X억 기업 → 같은 섹터의 매출 ±50% 기업들과 비교.
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
    target_market = target.get("market", "")

    # 같은 섹터 후보 (revenue 0 도 허용 — DART universe 항목은 revenue 미보유)
    same_sector = [
        c for c in universe
        if c.get("sector") == target_sector
        and c.get("ticker") != target_ticker
    ]

    # 섹터 매칭 실패 시 같은 시장(KOSPI/KOSDAQ) 폴백
    if not same_sector and target_market:
        same_sector = [
            c for c in universe
            if c.get("market") == target_market
            and c.get("ticker") != target_ticker
        ]

    if not same_sector:
        return []

    # revenue 보유 후보와 비보유 후보 분리
    with_rev = [c for c in same_sector if float(c.get("revenue", 0) or 0) > 0]
    without_rev = [c for c in same_sector if float(c.get("revenue", 0) or 0) <= 0]

    # target 매출이 0 이면 섹터 후보 그대로 (with_rev 우선, 부족분 without_rev)
    if target_rev <= 0:
        out = with_rev[:max_peers]
        if len(out) < max_peers:
            out += without_rev[: max_peers - len(out)]
        return out

    # 매출 밴드 내 기업
    lo, hi = revenue_band
    in_band = [
        c for c in with_rev
        if lo * target_rev <= float(c.get("revenue", 0) or 0) <= hi * target_rev
    ]

    # 부족하면 밴드 확장 — with_rev 에서 매출 거리 가까운 순
    if len(in_band) < min_peers and with_rev:
        with_rev_sorted = sorted(with_rev, key=lambda c: abs(float(c.get("revenue", 0) or 0) - target_rev))
        in_band = with_rev_sorted[: max(min_peers, max_peers)]

    # 그래도 부족하면 without_rev (DART-only) 로 충당
    if len(in_band) < min_peers:
        in_band = in_band + without_rev[: max_peers - len(in_band)]

    # 매출 거리 가까운 순으로 정렬 후 max_peers 제한 (revenue 없는 항목은 뒤로)
    in_band.sort(key=lambda c: (
        0 if float(c.get("revenue", 0) or 0) > 0 else 1,
        abs(float(c.get("revenue", 0) or 0) - target_rev),
    ))
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


def enrich_peers_with_naver(
    peers: list[dict[str, Any]],
    naver_fetcher: Any,
    cache: Any = None,
    cache_ttl_sec: int = 86400,
) -> list[dict[str, Any]]:
    """피어 후보 중 가격/EPS/BPS 가 비어있는 항목을 Naver fundamentals 로 채움.

    - sample_financials 의 항목은 이미 모든 필드 있음 → 그대로 통과
    - DART universe 의 항목은 {ticker, name, sector, market} 뿐 → Naver fetch 필요
    - 캐시 24h TTL (key: ``peer:naver:{ticker}``)

    naver_fetcher: NaverFundamentals 인스턴스. 없으면 enrichment 스킵.
    """
    if not naver_fetcher:
        return peers
    from ..data_sources.naver_fundamentals import _to_won
    out: list[dict[str, Any]] = []
    for p in peers:
        # 이미 가격/EPS/BPS 있으면 통과
        if (float(p.get("current_price", 0) or 0) > 0
                and float(p.get("eps", 0) or 0) != 0
                and float(p.get("bps", 0) or 0) > 0):
            out.append(p)
            continue
        ticker = p.get("ticker", "")
        if not ticker or not ticker.isdigit() or len(ticker) != 6:
            out.append(p)
            continue
        # 캐시 hit
        cache_key = f"peer:naver:{ticker}"
        info = None
        if cache:
            cached = cache.get(cache_key)
            if cached:
                info = cached[0]
        # 캐시 miss → 라이브 fetch
        if not info:
            try:
                info = naver_fetcher.fetch(ticker)
            except Exception:
                info = None
            if info and cache:
                cache.set(cache_key, info, ttl_sec=cache_ttl_sec, source="naver_fundamentals")
        if not info:
            out.append(p)
            continue
        price = _to_won(info.get("lastClosePrice", ""))
        eps = _to_won(info.get("eps", ""))
        bps = _to_won(info.get("bps", ""))
        mcap = _to_won(info.get("marketValue", ""))
        shares = (mcap / price) if price > 0 else 0
        enriched = dict(p)
        enriched.update({
            "current_price": price,
            "eps": eps,
            "bps": bps,
            "shares_outstanding": shares,
            "market_cap": mcap,
            # sps/ebitda/net_debt 등은 Naver fundamentals 에 없음 → 0 유지
        })
        out.append(enriched)
    return out


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
