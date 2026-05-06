"""실시간 재무/시세 데이터 빌더.

Yahoo Finance v8 chart + v10 quoteSummary 두 엔드포인트 사용.
키 불필요. 네트워크 차단 환경에서는 None 리턴.
"""

from __future__ import annotations
import json
from typing import Any

from ..valuation.engine import Financials
from .http_util import fetch_json


class LiveFinancials:
    CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    SUMMARY = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules={mods}"

    MODULES = ",".join([
        "summaryDetail",
        "defaultKeyStatistics",
        "financialData",
        "incomeStatementHistory",
        "balanceSheetHistory",
        "cashflowStatementHistory",
        "price",
    ])

    def __init__(self, timeout: int = 6):
        self.timeout = timeout

    @staticmethod
    def _to_yahoo(ticker: str) -> list[str]:
        """6자리 한국 코드면 .KS / .KQ 둘 다 시도 후보."""
        if ticker.isdigit() and len(ticker) == 6:
            return [f"{ticker}.KS", f"{ticker}.KQ"]
        return [ticker]

    def _get(self, url: str) -> dict[str, Any] | None:
        return fetch_json(url, timeout=self.timeout)

    def _summary(self, sym: str) -> dict[str, Any] | None:
        url = self.SUMMARY.format(sym=sym, mods=self.MODULES)
        data = self._get(url)
        if not data:
            return None
        try:
            return data["quoteSummary"]["result"][0]
        except (KeyError, IndexError, TypeError):
            return None

    @staticmethod
    def _v(d: dict[str, Any] | None, key: str) -> float:
        if not d: return 0.0
        x = d.get(key)
        if isinstance(x, dict):
            return float(x.get("raw") or 0)
        if isinstance(x, (int, float)):
            return float(x)
        return 0.0

    def build_financials(
        self,
        ticker: str,
        name: str,
        sector: str,
        sector_multiples: dict[str, float],
    ) -> Financials | None:
        last_err = None
        for sym in self._to_yahoo(ticker):
            r = self._summary(sym)
            if r is None:
                continue
            sd = r.get("summaryDetail") or {}
            ks = r.get("defaultKeyStatistics") or {}
            fd = r.get("financialData") or {}
            pr = r.get("price") or {}
            shares = self._v(ks, "sharesOutstanding") or self._v(ks, "impliedSharesOutstanding")
            price = self._v(pr, "regularMarketPrice") or self._v(sd, "previousClose")
            eps = self._v(ks, "trailingEps")
            bps = self._v(ks, "bookValue")
            ebitda = self._v(fd, "ebitda")
            revenue = self._v(fd, "totalRevenue")
            net_income = self._v(ks, "netIncomeToCommon") or 0
            fcf = self._v(fd, "freeCashflow")
            total_debt = self._v(fd, "totalDebt")
            total_cash = self._v(fd, "totalCash")
            net_debt = total_debt - total_cash
            roe = self._v(fd, "returnOnEquity")
            growth = self._v(fd, "earningsGrowth") or self._v(fd, "revenueGrowth") or 0.05
            div = self._v(sd, "dividendRate")
            sps = (revenue / shares) if shares > 0 else 0
            if not shares or not price:
                continue
            return Financials(
                ticker=ticker, name=name, sector=sector,
                current_price=price, shares_outstanding=shares,
                eps=eps, bps=bps, sps=sps, dps=div,
                roe=roe, revenue=revenue, operating_income=0,
                net_income=net_income, ebitda=ebitda, fcf=fcf, net_debt=net_debt,
                growth_rate=growth,
                sector_per=float(sector_multiples.get("per", 12.0)),
                sector_pbr=float(sector_multiples.get("pbr", 1.0)),
                sector_psr=float(sector_multiples.get("psr", 1.0)),
                sector_ev_ebitda=float(sector_multiples.get("ev_ebitda", 8.0)),
            )
        return None
