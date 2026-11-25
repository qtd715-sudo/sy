"""경기 사이클 정상화 (mid-cycle normalization).

DCF 는 기준 현금흐름을 영구히 성장시키므로, 최근 4분기(TTM)가 사이클 정점이면
정점 이익이 통째로 영구가치에 들어가 기업가치가 과대 산출된다.
(예: 반도체 호황기 TTM 영업이익률 46% vs 직전 3개년 평균 9%)

규칙
  - 정상 마진 = mean(과거 실적 연도 영업이익률들 + TTM 영업이익률)
  - TTM 마진이 정상 마진의 PEAK_RATIO 배 이상일 때만(=정점) 하향 정상화한다.
  - 저점(TTM < 정상)은 **상향하지 않는다** — 구조적 쇠퇴 기업을 싸게 보이게 만들 위험.
    대신 cycle="trough" 로 표시만 한다.
  - 정점이면 이익 기반 모델 전부(DCF·영업이익 배수·EBITDA 멀티플·PER·EV/EBITDA)에 정상화 이익을 쓴다.
    피어·섹터 멀티플은 평상시 이익 수준을 전제로 한 배수라, 정점 이익에 곱하면 이중으로 부풀기 때문.
    매출(PSR)·순자산(PBR) 기반 모델은 대상이 아니다.
  - 정상화 FCF = FCF − (영업이익 − 정상 영업이익) × (1 − 세율)
    (감가상각·CapEx 는 그대로 두고 초과 이익의 세후분만 뺀다.)
    결과가 0 이하이면 비례 축소(FCF × 정상/TTM 마진)로 대체.
"""

from __future__ import annotations
from typing import Any

MIN_HISTORY_YEARS = 3     # 과거 실적 연도가 이보다 적으면 판단 보류
MAX_HISTORY_YEARS = 5
PEAK_RATIO = 1.25         # TTM 마진 / 정상 마진 ≥ 1.25 → 정점
TROUGH_RATIO = 0.75       # ≤ 0.75 → 저점 (표시만)


def normalize_cash_flow(
    revenue: float,
    operating_income: float,
    fcf: float,
    tax_rate: float,
    margin_history: list[float] | None,
    net_income: float = 0.0,
    ebitda: float = 0.0,
) -> dict[str, Any]:
    """정상화 판단 결과. applied=True 일 때만 normalized_* 값을 써야 한다.

    margin_history: 과거 실적 연도의 영업이익률(소수, 오래된 순). 컨센서스·TTM 제외.
    """
    hist = [float(m) for m in (margin_history or []) if m is not None][-MAX_HISTORY_YEARS:]
    out: dict[str, Any] = {
        "applied": False, "cycle": "unknown", "reason": "",
        "history_years": len(hist), "margin_history": [round(m, 4) for m in hist],
    }
    if revenue <= 0 or operating_income <= 0:
        out["reason"] = "매출 또는 영업이익이 0 이하 — 정상화 대상 아님"
        return out
    if len(hist) < MIN_HISTORY_YEARS:
        out["reason"] = f"과거 실적 {len(hist)}개년 — 최소 {MIN_HISTORY_YEARS}개년 필요"
        return out

    ttm_margin = operating_income / revenue
    normal_margin = (sum(hist) + ttm_margin) / (len(hist) + 1)
    out.update(ttm_margin=round(ttm_margin, 4), normal_margin=round(normal_margin, 4))
    if normal_margin <= 0:
        out["reason"] = "과거 평균이 적자 — 정상 마진을 정의할 수 없음"
        return out

    ratio = ttm_margin / normal_margin
    out["ratio"] = round(ratio, 3)
    if ratio <= TROUGH_RATIO:
        out.update(cycle="trough", reason="TTM 마진이 평균보다 낮음 — 상향 조정하지 않음")
        return out
    if ratio < PEAK_RATIO:
        out.update(cycle="mid", reason="TTM 마진이 평균 범위 내")
        return out

    normal_op = revenue * normal_margin
    excess_after_tax = (operating_income - normal_op) * (1 - tax_rate)
    method = "excess_profit"
    normal_fcf = fcf - excess_after_tax if fcf > 0 else 0.0
    if fcf > 0 and normal_fcf <= 0:
        normal_fcf = fcf / ratio
        method = "proportional"
    # 순이익: 영업이익과 같은 비율로 축소. EBITDA: 감가상각은 그대로, 초과 영업이익만 차감.
    normal_ni = net_income / ratio if net_income > 0 else 0.0
    normal_ebitda = 0.0
    if ebitda > 0:
        normal_ebitda = ebitda - (operating_income - normal_op)
        if normal_ebitda <= 0:
            normal_ebitda = ebitda / ratio
    out.update(
        normalized_net_income=normal_ni,
        normalized_ebitda=normal_ebitda,
    )
    out.update(
        applied=True, cycle="peak", method=method,
        reason=f"TTM 영업이익률 {ttm_margin:.1%} 가 {len(hist)}개년+TTM 평균 {normal_margin:.1%} 의 {ratio:.2f}배",
        normalized_operating_income=normal_op,
        normalized_fcf=normal_fcf,
    )
    return out
