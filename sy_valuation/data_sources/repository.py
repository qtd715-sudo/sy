"""Financials repository.

두 단계로 구성:
1) 샘플 financials (data/sample_financials.json) — 한국 블루칩 50여 종목, 정확한 가치평가
2) 경량 ticker DB (data/tickers.json) — 한국/미국/ETF 수백 종목, 검색·자동완성용

샘플에 없는 종목을 검색하면 LiveFinancials 가 Yahoo Finance / Naver finance 에서
실시간 데이터를 끌어와 Financials 객체를 즉석 생성합니다.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

from ..valuation.engine import Financials


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class FinancialsRepository:
    def __init__(
        self,
        sample_path: Path | None = None,
        tickers_path: Path | None = None,
    ):
        self.sample_path = sample_path or _DATA_DIR / "sample_financials.json"
        self.tickers_path = tickers_path or _DATA_DIR / "tickers.json"
        self._raw: dict[str, Any] = {}
        self._companies: list[dict[str, Any]] = []
        self._sectors: dict[str, dict[str, float]] = {}
        self._by_ticker: dict[str, dict[str, Any]] = {}
        self._by_name: dict[str, dict[str, Any]] = {}
        self._tickers: list[dict[str, str]] = []   # full lightweight DB
        self._lite_by_ticker: dict[str, dict[str, str]] = {}
        self._lite_by_name: dict[str, dict[str, str]] = {}
        self.load()

    def load(self) -> None:
        with open(self.sample_path, "r", encoding="utf-8") as f:
            self._raw = json.load(f)
        self._sectors = self._raw.get("sectors", {})
        self._companies = self._raw.get("companies", [])
        self._by_ticker = {c["ticker"]: c for c in self._companies}
        self._by_name = {c["name"]: c for c in self._companies}

        seen: set[tuple[str, str]] = set()
        if self.tickers_path.exists():
            with open(self.tickers_path, "r", encoding="utf-8") as f:
                tdata = json.load(f)
            for t in tdata.get("tickers", []):
                key = (t["ticker"], t["name"])
                if key in seen:
                    continue
                seen.add(key)
                self._tickers.append(t)
                self._lite_by_ticker[t["ticker"]] = t
                self._lite_by_name[t["name"]] = t

        # KRX 전 종목 자동 로드 (네이버 캐시) — 있으면 추가
        try:
            from .krx_universe import load_universe
            for t in load_universe():
                key = (t["ticker"], t["name"])
                if key in seen:
                    continue
                seen.add(key)
                self._tickers.append(t)
                self._lite_by_ticker[t["ticker"]] = t
                self._lite_by_name[t["name"]] = t
        except Exception:
            pass

    @staticmethod
    def _norm(s: str) -> str:
        return "".join(ch for ch in (s or "").lower() if not ch.isspace() and ch.isalnum())

    def list_tickers(self) -> list[dict[str, str]]:
        if self._tickers:
            return [
                {"ticker": t["ticker"], "name": t["name"], "sector": t.get("sector", ""),
                 "exchange": t.get("exchange", ""), "asset": t.get("asset", "stock")}
                for t in self._tickers
            ]
        return [
            {"ticker": c["ticker"], "name": c["name"], "sector": c["sector"],
             "exchange": "KOSPI", "asset": "stock"}
            for c in self._companies
        ]

    def get_ticker_meta(self, query: str) -> dict[str, str] | None:
        if query in self._lite_by_ticker:
            return self._lite_by_ticker[query]
        if query in self._lite_by_name:
            return self._lite_by_name[query]
        qn = self._norm(query)
        for t in self._tickers:
            if self._norm(t["name"]) == qn:
                return t
        for t in self._tickers:
            if qn in self._norm(t["name"]) or self._norm(t["name"]) in qn:
                return t
        return None

    def find(self, query: str) -> dict[str, Any] | None:
        if not query:
            return None
        q = query.strip()
        if q in self._by_ticker:
            return self._by_ticker[q]
        if q in self._by_name:
            return self._by_name[q]
        qn = self._norm(q)
        if not qn:
            return None
        for name, c in self._by_name.items():
            if self._norm(name) == qn:
                return c
        candidates = []
        for name, c in self._by_name.items():
            n = self._norm(name)
            if qn in n or n in qn:
                candidates.append((len(n), c))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
        return None

    def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        """자동완성 — 샘플 + ticker DB 통합 검색."""
        pool = self.list_tickers()
        if not query:
            return pool[:limit]
        q = query.strip()
        qn = self._norm(q)
        out: list[tuple[int, dict[str, str]]] = []
        for c in pool:
            score = 0
            if c["ticker"] == q.upper() or c["ticker"] == q:
                score = 100
            elif c["ticker"].upper().startswith(q.upper()):
                score = 90
            elif c["name"] == q:
                score = 95
            elif self._norm(c["name"]) == qn:
                score = 90
            elif self._norm(c["name"]).startswith(qn):
                score = 80
            elif qn and qn in self._norm(c["name"]):
                score = 60
            elif q.lower() in c.get("sector", "").lower():
                score = 30
            if score > 0:
                # 샘플 financials 보유 종목은 보너스 점수
                if c["ticker"] in self._by_ticker:
                    score += 5
                out.append((-score, c))
        out.sort(key=lambda x: x[0])
        return [item for _, item in out[:limit]]

    def all(self) -> list[dict[str, Any]]:
        return list(self._companies)

    def to_financials(self, raw: dict[str, Any]) -> Financials:
        s = self._sectors.get(raw["sector"], {})
        return Financials(
            ticker=raw["ticker"],
            name=raw["name"],
            sector=raw["sector"],
            current_price=float(raw["current_price"]),
            shares_outstanding=float(raw["shares_outstanding"]),
            eps=float(raw["eps"]),
            bps=float(raw["bps"]),
            sps=float(raw.get("sps", 0)),
            dps=float(raw.get("dps", 0)),
            roe=float(raw.get("roe", 0)),
            revenue=float(raw.get("revenue", 0)),
            operating_income=float(raw.get("operating_income", 0)),
            net_income=float(raw.get("net_income", 0)),
            ebitda=float(raw.get("ebitda", 0)),
            fcf=float(raw.get("fcf", 0)),
            net_debt=float(raw.get("net_debt", 0)),
            growth_rate=float(raw.get("growth_rate", 0.05)),
            sector_per=float(s.get("per", 12.0)),
            sector_pbr=float(s.get("pbr", 1.0)),
            sector_psr=float(s.get("psr", 1.0)),
            sector_ev_ebitda=float(s.get("ev_ebitda", 8.0)),
        )

    def get_financials(self, query: str) -> Financials | None:
        raw = self.find(query)
        if not raw:
            return None
        return self.to_financials(raw)

    def get_or_build_financials(self, query: str, live=None) -> Financials | None:
        """샘플에 있으면 그대로, 없으면 live 데이터로 즉석 빌드."""
        f = self.get_financials(query)
        if f:
            return f
        if live is None:
            return None
        meta = self.get_ticker_meta(query)
        if not meta:
            return None
        sector = meta.get("sector", "기타")
        s = self._sectors.get(sector, {"per": 12.0, "pbr": 1.0, "psr": 1.0, "ev_ebitda": 8.0})
        try:
            built = live.build_financials(meta["ticker"], meta["name"], sector, s)
        except Exception:
            return None
        return built

    def all_financials(self) -> list[Financials]:
        return [self.to_financials(c) for c in self._companies]

    def sector_table(self) -> dict[str, dict[str, float]]:
        return dict(self._sectors)
