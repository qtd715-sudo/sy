"""사이클 정상화 단위 테스트.

    python -m unittest sy_valuation.tests.test_normalize
"""
import dataclasses
import unittest

from sy_valuation.valuation.normalize import normalize_cash_flow
from sy_valuation.valuation.sy_builder import build_inputs_from_raw
from sy_valuation.valuation.sy_method import dcf_fcff, evaluate_sy, op_income_multiple

RAW = {
    "ticker": "000001", "name": "CycleCo", "sector": "반도체",
    "current_price": 100_000, "shares_outstanding": 10_000_000,
    "revenue": 1000e8, "operating_income": 400e8, "net_income": 300e8,
    "ebitda": 500e8, "fcf": 300e8, "net_debt": 0, "bps": 50_000,
    "peer_per_avg": 10, "peer_pbr_avg": 1, "peer_psr_avg": 1, "peer_ev_ebitda_avg": 6,
    "growth_rate": 0.05,
}


class NormalizeTest(unittest.TestCase):
    def test_peak_is_normalized_down(self):
        n = normalize_cash_flow(1000, 400, 300, 0.22, [0.05, 0.10, 0.13])
        self.assertTrue(n["applied"])
        self.assertEqual(n["cycle"], "peak")
        self.assertAlmostEqual(n["normal_margin"], 0.17)
        self.assertAlmostEqual(n["normalized_operating_income"], 170)
        # FCF − (400−170)×(1−0.22)
        self.assertAlmostEqual(n["normalized_fcf"], 300 - 230 * 0.78)

    def test_mid_and_trough_are_not_adjusted(self):
        mid = normalize_cash_flow(1000, 110, 80, 0.22, [0.10, 0.11, 0.09])
        self.assertEqual((mid["applied"], mid["cycle"]), (False, "mid"))
        trough = normalize_cash_flow(1000, 30, 20, 0.22, [0.15, 0.14, 0.16])
        self.assertEqual((trough["applied"], trough["cycle"]), (False, "trough"))
        self.assertNotIn("normalized_fcf", trough)

    def test_guards(self):
        self.assertFalse(normalize_cash_flow(1000, 400, 300, 0.22, [0.05, 0.10])["applied"])   # 이력 부족
        self.assertFalse(normalize_cash_flow(1000, 400, 300, 0.22, None)["applied"])
        self.assertFalse(normalize_cash_flow(1000, -10, 0, 0.22, [0.1, 0.1, 0.1])["applied"])  # 적자
        self.assertFalse(normalize_cash_flow(1000, 50, 30, 0.22, [-0.2, -0.1, -0.1])["applied"])  # 평균 적자

    def test_falls_back_to_proportional_when_excess_exceeds_fcf(self):
        n = normalize_cash_flow(1000, 400, 100, 0.22, [0.05, 0.10, 0.13])
        self.assertEqual(n["method"], "proportional")
        self.assertAlmostEqual(n["normalized_fcf"], 100 / (0.40 / 0.17))

    def test_engine_uses_normalized_values(self):
        peak = build_inputs_from_raw({**RAW, "_op_margin_history": [0.05, 0.10, 0.13]}, {})
        plain = build_inputs_from_raw(RAW, {})
        off = build_inputs_from_raw({**RAW, "_op_margin_history": [0.05, 0.10, 0.13], "normalize": False}, {})
        self.assertEqual(plain.normalized_fcf, 0)
        self.assertEqual(off.normalized_fcf, 0)
        self.assertGreater(peak.normalized_fcf, 0)
        self.assertLess(dcf_fcff(peak)[0], dcf_fcff(plain)[0])
        # 같은 성장률이면 DCF 는 기준 FCF 에 선형
        same_g = dataclasses.replace(peak, growth_rate_short=plain.growth_rate_short,
                                     growth_rate_long=plain.growth_rate_long)
        self.assertAlmostEqual(dcf_fcff(same_g)[0] / dcf_fcff(plain)[0], peak.normalized_fcf / plain.fcf)
        self.assertAlmostEqual(op_income_multiple(peak) / (170e8 * 10), 1.0)
        # 표시용 원본 값은 바뀌지 않는다
        self.assertEqual(peak.fcf, plain.fcf)
        self.assertEqual(peak.operating_income, plain.operating_income)
        self.assertEqual(peak.net_income, plain.net_income)
        self.assertTrue(any("정상화" in n for n in evaluate_sy(peak).notes))
        self.assertFalse(any("정상화" in n for n in evaluate_sy(plain).notes))

    def test_peak_normalizes_every_earnings_based_model(self):
        peak = evaluate_sy(build_inputs_from_raw({**RAW, "_op_margin_history": [0.05, 0.10, 0.13]}, {}))
        plain = evaluate_sy(build_inputs_from_raw(RAW, {}))
        k = 0.17 / 0.40                                   # 정상 마진 / TTM 마진
        self.assertAlmostEqual(peak.market_per / plain.market_per, k)          # 순이익 비례 축소
        ebitda_n = 500e8 - (400e8 - 170e8)                                     # 초과 영업이익만 차감
        self.assertAlmostEqual(peak.income_ebitda_multiple / (ebitda_n * 6), 1.0)
        self.assertAlmostEqual(peak.market_ev_ebitda / (ebitda_n * 6), 1.0)
        # 매출·순자산 기반 모델은 그대로
        self.assertEqual(peak.market_psr, plain.market_psr)
        self.assertEqual(peak.market_pbr, plain.market_pbr)
        self.assertEqual(peak.asset_book, plain.asset_book)


class GrowthCapTest(unittest.TestCase):
    def test_short_growth_capped_at_10pct(self):
        self.assertEqual(build_inputs_from_raw({**RAW, "growth_rate": 0.18}, {}).growth_rate_short, 0.10)
        inp = build_inputs_from_raw({**RAW, "growth_rate": 0.18}, {})
        self.assertEqual(inp.growth_rate_long, 0.05)
        # 미지정 시 ROE×유보율 (300억/5000억 × 0.7 = 4.2%) — 상한 미만이면 그대로
        self.assertAlmostEqual(build_inputs_from_raw({**RAW, "growth_rate": 0}, {}).growth_rate_short, 0.042)

    def test_peak_growth_limited_by_normalized_roe(self):
        peak = build_inputs_from_raw({**RAW, "growth_rate": 0.10, "_op_margin_history": [0.05, 0.10, 0.13]}, {})
        # 정상 순이익 300억×0.425=127.5억, 자기자본 5000억 → ROE 2.55% × 0.7
        self.assertAlmostEqual(peak.growth_rate_short, 0.0255 * 0.7)
        self.assertAlmostEqual(peak.growth_rate_long, peak.growth_rate_short / 2)


class PeerSelectionTest(unittest.TestCase):
    BIG = {"ticker": "T", "sector": "반도체", "revenue": 600e12,
           "current_price": 100_000, "shares_outstanding": 10_000_000_000}   # 시총 1,000조

    def _c(self, tk, **kw):
        return {"ticker": tk, "name": tk, "sector": "반도체", **kw}

    def test_size_compared_on_same_basis(self):
        from sy_valuation.valuation.peers import select_peers
        universe = [
            self._c("A", revenue=270e12),                 # 매출 0.45배 → 밴드 안
            self._c("B", market_cap=400e8),               # 시총 400억 — 매출 600조와 비교하면 안 됨
            self._c("C", market_cap=3600e8),
            self._c("D", revenue=5e12),                   # 매출 0.008배 → 넓힌 밴드도 밖
        ]
        self.assertEqual([p["ticker"] for p in select_peers(self.BIG, universe)], ["A"])

    def test_widens_band_once_then_stops(self):
        from sy_valuation.valuation.peers import select_peers
        universe = [self._c("A", revenue=270e12), self._c("E", revenue=70e12), self._c("F", revenue=65e12),
                    self._c("D", revenue=5e12)]
        # 기본 밴드(0.3~3배)엔 A 뿐 → 0.1~10배로 넓혀 E, F 포함. D(0.008배)는 끝까지 제외.
        self.assertEqual([p["ticker"] for p in select_peers(self.BIG, universe)], ["A", "E", "F"])

    def test_median_and_min_observations(self):
        from sy_valuation.valuation.peers import compute_peer_multiples
        mk = lambda per: {"current_price": per * 100, "eps": 100, "bps": 1000, "shares_outstanding": 1}
        self.assertEqual(compute_peer_multiples([mk(8), mk(10), mk(60)])["per"], 10)   # 평균이면 26
        # 피어 2개뿐이면 섹터 표준값 사용
        raw = {k: v for k, v in RAW.items() if not k.startswith("peer_")}
        uni = [{"ticker": f"P{i}", "sector": "반도체", "revenue": RAW["revenue"], "sps": 1,
                **mk(per)} for i, per in enumerate((30, 40))]
        few = build_inputs_from_raw(raw, {"per": 14.5, "pbr": 1.6}, universe=uni)
        self.assertEqual((few.peer_per_avg, few.peer_source), (14.5, "sector"))
        uni.append({"ticker": "P2", "sector": "반도체", "revenue": RAW["revenue"], "sps": 1, **mk(50)})
        enough = build_inputs_from_raw(raw, {"per": 14.5, "pbr": 1.6}, universe=uni)
        self.assertEqual(enough.peer_per_avg, 40)
        self.assertIn(enough.peer_source, ("peers", "mixed"))


if __name__ == "__main__":
    unittest.main()
