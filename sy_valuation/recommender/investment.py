"""투자 추천 엔진: 단기 vs 장기 + 매수/매도가.

입력:
- 가치평가 결과 (fair_price, upside)
- 뉴스 감성 점수 (-1 ~ +1)
- 가격 히스토리 (선택, 변동성/추세 산출)

규칙 (단순/투명하게):
- horizon = "장기"  if 본질가치 갭이 크고 (upside >= 20%) ROE >= 8% 면 장기 매수 매력
- horizon = "단기"  if 단기 모멘텀(뉴스 감성) 우호 + 변동성 보통/낮음
- horizon = "관망"  if 두 조건 모두 약함

단기 가격대:
- buy_zone  = max(현재가, fair_price) * (1 - 0.05)
- sell_zone = fair_price * 1.02

장기 사유:
- DCF / RIM 기반 본질가치, 산업 멀티플 대비 디스카운트, ROE-CoE 스프레드
"""

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any
import statistics

from ..valuation.engine import ValuationResult, Financials


@dataclass
class InvestmentRecommendation:
    ticker: str
    name: str
    horizon: str                    # "장기" / "단기" / "관망"
    action: str                     # BUY / HOLD / SELL
    confidence: float               # 0.0 ~ 1.0
    short_term_buy_zone: float
    short_term_sell_zone: float
    stop_loss: float
    long_term_thesis: list[str]     # 장기 투자 사유
    risks: list[str]
    news_sentiment: float
    volatility_pct: float = 0.0     # 일간 표준편차 * sqrt(252)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _annualized_vol(closes: list[float]) -> float:
    if not closes or len(closes) < 5:
        return 0.0
    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
    if len(rets) < 2:
        return 0.0
    sd = statistics.pstdev(rets)
    return round(sd * (252 ** 0.5) * 100, 2)


def recommend_investment(
    f: Financials,
    v: ValuationResult,
    news_score: float = 0.0,
    closes: list[float] | None = None,
    cost_of_equity: float = 0.085,
) -> InvestmentRecommendation:
    vol = _annualized_vol(closes or [])
    upside = v.upside
    fair = v.fair_price

    # 장기 매력도
    long_attractive = (upside >= 0.20) and (f.roe >= 0.08)
    # 단기 매력도: 적정가 대비 5% 이상 디스카운트 + 뉴스 우호
    short_attractive = (upside >= 0.05) and (news_score >= 0.10)

    if long_attractive and short_attractive:
        horizon, action = "장기+단기", "BUY"
        confidence = 0.85
    elif long_attractive:
        horizon, action = "장기", "BUY"
        confidence = 0.75
    elif short_attractive:
        horizon, action = "단기", "BUY"
        confidence = 0.55
    elif upside <= -0.10:
        horizon, action = "단기", "SELL"
        confidence = 0.60
    else:
        horizon, action = "관망", "HOLD"
        confidence = 0.40

    # 단기 매수/매도 구간
    buy_zone = round(min(f.current_price, fair) * 0.95, 0) if fair > 0 else round(f.current_price * 0.95, 0)
    sell_zone = round(fair * 1.02, 0) if fair > 0 else round(f.current_price * 1.10, 0)
    stop_loss = round(buy_zone * 0.92, 0)

    # 장기 사유 (정량 근거)
    thesis: list[str] = []
    pbr_now = (f.current_price / f.bps) if f.bps > 0 else 0
    per_now = (f.current_price / f.eps) if f.eps > 0 else 0

    if upside >= 0.20:
        thesis.append(f"적정주가 {fair:,.0f}원 대비 현재가 {f.current_price:,.0f}원, 상승여력 {upside*100:.1f}%")
    if f.roe > cost_of_equity:
        thesis.append(f"ROE {f.roe*100:.1f}% > 자본비용 {cost_of_equity*100:.1f}% → 가치창출 진행 중")
    if pbr_now and pbr_now < f.sector_pbr:
        thesis.append(f"PBR {pbr_now:.2f} < 섹터 평균 {f.sector_pbr:.2f} (자산가치 디스카운트)")
    if per_now and per_now < f.sector_per:
        thesis.append(f"PER {per_now:.1f} < 섹터 평균 {f.sector_per:.1f} (이익 멀티플 디스카운트)")
    if f.fcf > 0 and f.net_income > 0:
        thesis.append(f"FCF {f.fcf/1e8:,.0f}억 흑자 → 본질적 현금창출력 확보")
    if f.growth_rate >= 0.10:
        thesis.append(f"향후 EPS 성장률 추정 {f.growth_rate*100:.1f}% (성장 모멘텀)")
    if not thesis:
        thesis.append("현재 가격 수준에서 장기 매수 근거 약함 — 분할 진입 또는 관망 권고")

    # 리스크
    risks: list[str] = []
    if f.roe < 0.05:
        risks.append("낮은 ROE — 자본효율 부진")
    if f.net_income <= 0:
        risks.append("적자 — 모델 신뢰도 하락")
    if f.ebitda > 0 and (f.net_debt / f.ebitda) > 3:
        risks.append("순부채/EBITDA > 3 — 부채부담")
    if vol > 40:
        risks.append(f"연간 변동성 {vol}% — 단기 트레이딩 시 리스크 큼")
    if news_score <= -0.20:
        risks.append("최근 뉴스 흐름 부정적")
    if f.current_price > 0 and v.fair_price > 0 and (v.fair_price / f.current_price) > 3:
        risks.append("적정가 추정치 과대 — 가정 민감도 검토 필요")

    return InvestmentRecommendation(
        ticker=f.ticker,
        name=f.name,
        horizon=horizon,
        action=action,
        confidence=confidence,
        short_term_buy_zone=buy_zone,
        short_term_sell_zone=sell_zone,
        stop_loss=stop_loss,
        long_term_thesis=thesis,
        risks=risks,
        news_sentiment=news_score,
        volatility_pct=vol,
    )
