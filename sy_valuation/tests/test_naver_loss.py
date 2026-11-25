"""Naver 대체 경로: 적자 기업도 재무를 돌려줘야 한다.

    python -m unittest sy_valuation.tests.test_naver_loss
"""
import unittest

from sy_valuation.data_sources.naver_financials import NaverFinancials


class _Stub(NaverFinancials):
    def __init__(self, ttm, annual):
        self._ttm, self._annual = ttm, annual

    def ttm_metrics(self, code):
        return dict(self._ttm)

    def latest_metrics(self, code):
        return dict(self._annual)


class NaverLossTest(unittest.TestCase):
    def test_loss_making_company_keeps_revenue(self):
        nf = _Stub({"매출액": 739.0, "영업이익": -41.0, "당기순이익": -16.0, "지배주주순이익": -13.0,
                    "EPS": -101.0, "BPS": 7506.0, "ROE": -1.35, "_period_key": "2026.06 최근4분기 TTM"},
                   {"주당배당금": 0.0})
        out = nf.to_partial_financials("058970", "엠로", "IT서비스")
        self.assertIsNotNone(out)
        self.assertEqual(out["revenue"], 739e8)
        self.assertEqual(out["operating_income"], -41e8)
        self.assertEqual(out["net_income"], -13e8)
        self.assertEqual((out["ebitda"], out["fcf"]), (0, 0))   # 적자면 추정 EBITDA·FCF 는 0
        self.assertEqual(out["_naver_period"], "2026.06 최근4분기 TTM")

    def test_truly_empty_is_still_none(self):
        self.assertIsNone(_Stub({}, {}).to_partial_financials("000000", "x", "기타"))
        self.assertIsNone(_Stub({"매출액": 0, "EPS": 0, "_period_key": "x"}, {}).to_partial_financials("0", "x", "기타"))


if __name__ == "__main__":
    unittest.main()
