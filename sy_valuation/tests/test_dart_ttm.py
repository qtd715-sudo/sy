"""DART TTM 재무 계산 테스트 (네트워크 없이 — DART 응답 형식의 가짜 rows 사용).

실행: python -m unittest discover -s sy_valuation/tests -t .
"""

from __future__ import annotations
import unittest
from datetime import date
from unittest import mock

from sy_valuation.data_sources import dart as dart_mod
from sy_valuation.data_sources.dart import (
    DartConnector, _candidate_reports, _ttm_flows, apply_per_share,
)


class FakeCache:
    def __init__(self):
        self.d = {}

    def get(self, key):
        return (self.d[key], {}) if key in self.d else None

    def set(self, key, value, ttl_sec=0, source=""):
        self.d[key] = value


def _is(aid, nm, amount, add=None, sj="IS"):
    r = {"sj_div": sj, "account_id": aid, "account_nm": nm, "thstrm_amount": f"{amount:,}"}
    if add is not None:
        r["thstrm_add_amount"] = f"{add:,}"
    return r


def _bs(aid, nm, amount):
    return {"sj_div": "BS", "account_id": aid, "account_nm": nm, "thstrm_amount": f"{amount:,}"}


def _cf(aid, nm, amount):
    return {"sj_div": "CF", "account_id": aid, "account_nm": nm, "thstrm_amount": f"{amount:,}"}


def make_rows(rev, op, ni, ni_owner, tax, capex, depr, assets, equity, equity_owner, cash,
              quarter_only=None):
    """연초 누적값으로 rows 생성. quarter_only 가 있으면 IS 의 thstrm_amount 는 3개월치,
    thstrm_add_amount 는 누적 (분·반기 보고서 형식)."""
    def isrow(aid, nm, cum, q):
        if quarter_only is None:
            return _is(aid, nm, cum)
        return _is(aid, nm, q, add=cum)
    q = quarter_only or {}
    return [
        isrow("ifrs-full_Revenue", "매출액", rev, q.get("rev", 1)),
        isrow("dart_OperatingIncomeLoss", "영업이익", op, q.get("op", 1)),
        isrow("ifrs-full_ProfitLoss", "당기순이익", ni, q.get("ni", 1)),
        isrow("ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익",
              ni_owner, q.get("ni_owner", 1)),
        isrow("ifrs-full_IncomeTaxExpenseContinuingOperations", "법인세비용", tax, q.get("tax", 1)),
        _cf("dart_DepreciationExpense", "감가상각비", depr),
        _cf("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "유형자산의 취득", -capex),
        _bs("ifrs-full_Assets", "자산총계", assets),
        _bs("ifrs-full_Equity", "자본총계", equity),
        _bs("ifrs-full_EquityAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 자본", equity_owner),
        _bs("ifrs-full_Liabilities", "부채총계", assets - equity),
        _bs("ifrs-full_CashAndCashEquivalents", "현금및현금성자산", cash),
    ]


# 작년 연간 / 작년 반기 누적 / 올해 반기 누적
ANNUAL_2025 = make_rows(1000, 200, 150, 140, 40, 80, 60, 5000, 3000, 2800, 500)
H1_2025 = make_rows(450, 90, 70, 65, 18, 35, 28, 4800, 2900, 2700, 450,
                    quarter_only={"rev": 230})
H1_2026 = make_rows(600, 130, 100, 95, 26, 50, 34, 5400, 3200, 3000, 700,
                    quarter_only={"rev": 320, "op": 70, "ni": 55, "ni_owner": 50, "tax": 14})


class DartTTMTest(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache()
        p = mock.patch("sy_valuation.data_sources.cache.get_cache", return_value=self.cache)
        p.start()
        self.addCleanup(p.stop)
        self.calls = []
        self.reports = {}  # (year, report, fs) -> (status, rows)

        conn = DartConnector(api_key="test")
        conn._corp_map = {"000001": "00000001"}

        def fake_fetch(stock, year, report, fs):
            self.calls.append((year, report, fs))
            return self.reports.get((year, report, fs), ("013", []))
        conn._fetch_report = fake_fetch
        self.conn = conn

    def _run(self, today=date(2026, 10, 8)):
        # 보고서 후보를 고정 날짜 기준으로 (실제 오늘 날짜와 무관하게)
        with mock.patch.object(dart_mod, "_candidate_reports",
                               side_effect=lambda _t: _candidate_reports(today)):
            return self.conn.latest_partial_financials("000001", "테스트", "반도체")

    def test_half_year_ttm(self):
        self.reports = {
            (2026, "11012", "CFS"): ("000", H1_2026),
            (2025, "11011", "CFS"): ("000", ANNUAL_2025),
            (2025, "11012", "CFS"): ("000", H1_2025),
        }
        r = self._run()
        # 매출 TTM = 600 + 1000 − 450 (3개월치 320/230 이 아니라 누적 사용)
        self.assertEqual(r["revenue"], 1150)
        self.assertEqual(r["operating_income"], 130 + 200 - 90)
        # 순이익은 지배주주 기준, 전체는 별도 필드
        self.assertEqual(r["net_income"], 95 + 140 - 65)
        self.assertEqual(r["net_income_total"], 100 + 150 - 70)
        self.assertEqual(r["tax_expense"], 26 + 40 - 18)
        # 현금흐름표(누적) 항목도 TTM
        self.assertEqual(r["capex"], 50 + 80 - 35)
        self.assertEqual(r["depreciation"], 34 + 60 - 28)
        # 재무상태표는 최신(2026 반기말) 잔액 그대로
        self.assertEqual(r["total_assets"], 5400)
        self.assertEqual(r["equity_owner"], 3000)
        self.assertEqual(r["cash_equivalents"], 700)
        self.assertEqual(r["_dart_basis"], "2026 반기 TTM")
        self.assertEqual(r["_dart_period_end"], "2026-06-30")
        self.assertEqual(r["_dart_year"], "2025")

    def test_annual_report_used_as_is(self):
        self.reports = {(2025, "11011", "CFS"): ("000", ANNUAL_2025)}
        r = self._run(today=date(2026, 4, 20))
        self.assertEqual(r["revenue"], 1000)
        self.assertEqual(r["net_income"], 140)
        self.assertEqual(r["_dart_basis"], "2025 사업보고서")

    def test_missing_prior_interim_falls_back_to_annual_flows(self):
        self.reports = {
            (2026, "11012", "CFS"): ("000", H1_2026),
            (2025, "11011", "CFS"): ("000", ANNUAL_2025),
        }
        r = self._run()
        self.assertEqual(r["revenue"], 1000)
        self.assertEqual(r["total_assets"], 5400)  # 재무상태는 최신
        self.assertIn("2025 사업보고서", r["_dart_basis"])

    def test_ofs_fallback_and_preference_remembered(self):
        self.reports = {
            (2026, "11012", "OFS"): ("000", H1_2026),
            (2025, "11011", "OFS"): ("000", ANNUAL_2025),
            (2025, "11012", "OFS"): ("000", H1_2025),
        }
        r = self._run()
        self.assertEqual(r["revenue"], 1150)
        self.assertEqual(r["_dart_fs"], "OFS")
        # 첫 보고서 이후엔 OFS 를 먼저 시도 → CFS 헛호출은 첫 보고서 1회뿐
        self.assertEqual(sum(1 for c in self.calls if c[2] == "CFS"), 1)

    def test_quota_error_not_cached_as_missing(self):
        self.reports = {(2026, "11012", "CFS"): ("020", [])}
        self.assertIsNone(self._run())
        n = len(self.calls)
        self.assertIsNone(self._run())
        self.assertGreater(len(self.calls), n)  # 020 은 캐시 안 됨 → 재시도

    def test_reports_cached_between_runs(self):
        self.reports = {
            (2026, "11012", "CFS"): ("000", H1_2026),
            (2025, "11011", "CFS"): ("000", ANNUAL_2025),
            (2025, "11012", "CFS"): ("000", H1_2025),
        }
        self._run()
        self.cache.d.pop("dart:partial:v2:000001")  # 24h 결과 캐시만 제거
        n = len(self.calls)
        self.assertEqual(self._run()["revenue"], 1150)
        self.assertEqual(len(self.calls), n)  # 보고서별 캐시로 추가 호출 없음


class HelperTest(unittest.TestCase):
    def test_candidates(self):
        def c(d):
            return [(y, r) for y, r, _ in _candidate_reports(d)][:2]
        self.assertEqual(c(date(2026, 10, 8)), [(2026, "11012"), (2026, "11013")])
        self.assertEqual(c(date(2026, 11, 10))[0], (2026, "11014"))
        self.assertEqual(c(date(2026, 3, 15))[0], (2025, "11011"))
        self.assertEqual(c(date(2026, 5, 20))[0], (2026, "11013"))

    def test_partial_parse_uses_annual(self):
        flows = _ttm_flows({"revenue": 600, "capex": 0}, {"revenue": 1000, "capex": 80},
                           {"revenue": 450, "capex": 35})
        self.assertEqual(flows["revenue"], 1150)
        self.assertEqual(flows["capex"], 80)  # 올해 누락 → 연간 값

    def test_apply_per_share(self):
        raw = {"shares_outstanding": 10, "net_income": 170, "equity_owner": 3000,
               "revenue": 1150, "_dart_basis": "2026 반기 TTM", "eps": 999}
        apply_per_share(raw)
        self.assertEqual(raw["eps"], 17)
        self.assertEqual(raw["bps"], 300)
        self.assertAlmostEqual(raw["roe"], 170 / 3000)
        self.assertEqual(raw["sps"], 115)

    def test_apply_per_share_skips_without_dart(self):
        raw = {"shares_outstanding": 10, "net_income": 170, "eps": 999}
        apply_per_share(raw)
        self.assertEqual(raw["eps"], 999)


class NaverConsensusTest(unittest.TestCase):
    def test_consensus_excluded(self):
        from sy_valuation.data_sources.naver_financials import NaverFinancials
        data = {"periods": ["202506", "202509", "202512", "202603", "202606", "202609"],
                "consensus": ["202609"]}
        with mock.patch("datetime.date") as d:
            d.today.return_value = date(2026, 10, 8)
            got = NaverFinancials._actual_periods(data)
        self.assertEqual(got[-1], "202606")


if __name__ == "__main__":
    unittest.main()
