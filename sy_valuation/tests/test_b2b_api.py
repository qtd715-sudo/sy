"""B2B 계산 API · MCP 단위 테스트 (네트워크 없음 — inputs 직접 입력 경로만).

    python -m unittest sy_valuation.tests.test_b2b_api
"""
import unittest

from sy_valuation import b2b_api


class _Repo:
    def sector_table(self):
        return {"IT서비스": {"per": 20.0, "pbr": 2.0, "psr": 1.5, "ev_ebitda": 10.0}}


class _App:
    repo = _Repo()

    def search(self, q, limit=5):
        return [{"ticker": "000000", "name": q}]


TARGET = {
    "name": "TargetCo", "sector": "IT서비스",
    "revenue": 50e9, "operating_income": 6e9, "net_income": 4.5e9,
    "ebitda": 8e9, "fcf": 4e9,
    "total_assets": 60e9, "total_liabilities": 20e9, "net_debt": 5e9,
    "shares_outstanding": 1_000_000,
}


class ComputeTest(unittest.TestCase):
    def test_deterministic_same_input_same_output(self):
        a = b2b_api.compute(_App(), {"inputs": TARGET})
        b = b2b_api.compute(_App(), {"inputs": dict(TARGET)})
        self.assertEqual(a["input_hash"], b["input_hash"])
        self.assertEqual(a["result"], b["result"])

    def test_private_company_has_no_upside(self):
        r = b2b_api.compute(_App(), {"inputs": TARGET})["result"]
        self.assertEqual(r["rating"], "N/A")
        self.assertIsNone(r["upside_mid"])
        self.assertGreater(r["enterprise_mid"], 0)
        self.assertEqual(r["fair_price_mid"], round(r["enterprise_mid"] / 1_000_000))
        # 섹터 표준 멀티플 적용: PER 20 × 순이익 45억
        self.assertEqual(r["market_per"], 20.0 * 4.5e9)

    def test_higher_wacc_lowers_dcf(self):
        lo = b2b_api.compute(_App(), {"inputs": TARGET, "assumptions": {"wacc": 0.08}})
        hi = b2b_api.compute(_App(), {"inputs": TARGET, "assumptions": {"wacc": 0.12}})
        self.assertGreater(lo["result"]["income_dcf"], hi["result"]["income_dcf"])
        self.assertNotEqual(lo["input_hash"], hi["input_hash"])
        self.assertIn("baseline", hi)
        self.assertEqual(hi["assumptions_applied"], {"wacc": 0.12})

    def test_short_growth_override_derives_long(self):
        r = b2b_api.compute(_App(), {"inputs": TARGET, "assumptions": {"growth_rate_short": 0.10}})
        self.assertAlmostEqual(r["assumptions_applied"]["growth_rate_long"], 0.05)

    def test_sensitivity_grid_monotonic_in_wacc(self):
        r = b2b_api.compute(_App(), {"inputs": TARGET, "sensitivity": {"metric": "income_dcf"}})
        s = r["sensitivity"]
        self.assertEqual((len(s["grid"]), len(s["grid"][0])), (len(s["y_values"]), len(s["x_values"])))
        for row in s["grid"]:
            vals = [v for v in row if v is not None]
            self.assertEqual(vals, sorted(vals, reverse=True))

    def test_validation_errors(self):
        cases = [
            ({}, "missing_input"),
            ({"inputs": {"revenu": 1}}, "unknown_field"),
            ({"inputs": {"revenue": "많음"}}, "invalid_input"),
            ({"inputs": TARGET, "assumptions": {"wacc": 0.9}}, "out_of_range"),
            ({"inputs": TARGET, "assumptions": {"magic": 1}}, "unknown_assumption"),
            ({"inputs": TARGET, "assumptions": {"wacc": 0.02, "terminal_growth": 0.03}}, "invalid_assumption"),
            ({"inputs": TARGET, "sensitivity": {"x": "wacc", "y": "wacc"}}, "invalid_sensitivity"),
        ]
        for body, code in cases:
            with self.assertRaises(b2b_api.ApiError) as cm:
                b2b_api.compute(_App(), body)
            self.assertEqual(cm.exception.code, code, body)


class McpTest(unittest.TestCase):
    def rpc(self, method, params=None, rid=1):
        return b2b_api.handle_mcp(_App(), {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})

    def test_initialize_and_list(self):
        init = self.rpc("initialize", {"protocolVersion": "2025-03-26"})
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")
        names = [t["name"] for t in self.rpc("tools/list")["result"]["tools"]]
        self.assertIn("compute_valuation", names)

    def test_notification_returns_none(self):
        self.assertIsNone(b2b_api.handle_mcp(_App(), {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tool_call_and_tool_error(self):
        ok = self.rpc("tools/call", {"name": "compute_valuation", "arguments": {"inputs": TARGET}})
        self.assertFalse(ok["result"]["isError"])
        self.assertGreater(ok["result"]["structuredContent"]["result"]["enterprise_mid"], 0)
        self.assertNotIn("inputs", ok["result"]["structuredContent"]["result"])
        bad = self.rpc("tools/call", {"name": "compute_valuation", "arguments": {}})
        self.assertTrue(bad["result"]["isError"])
        self.assertEqual(self.rpc("tools/call", {"name": "nope"})["error"]["code"], -32602)
        self.assertEqual(self.rpc("nope")["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
