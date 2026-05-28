"""DART (전자공시시스템) OpenAPI 커넥터.

API key 발급: https://opendart.fss.or.kr/  (무료, 환경변수 DART_API_KEY 로 주입)

주요 사용 엔드포인트:
- /api/company.json          : 기업 개요 (corp_code 필요)
- /api/fnlttSinglAcntAll.json: 단일회사 전체 재무제표
- /api/list.json             : 공시 목록

corp_code(8자리)는 /api/corpCode.xml 의 ZIP 안 corpCode.xml 에 있음.
이 파일은 한 번 받아서 캐시하면 됨 (CORPCODE_PATH 환경변수로 경로 지정).
"""

from __future__ import annotations
import io
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any


_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"


class DartConnector:
    BASE = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str | None = None, timeout: int = 10):
        self.api_key = api_key or os.environ.get("DART_API_KEY", "")
        self.timeout = timeout
        self._corp_map: dict[str, str] = {}  # stock_code → corp_code

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")
        params["crtfc_key"] = self.api_key
        url = f"{self.BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def load_corp_codes(self, force: bool = False) -> dict[str, str]:
        """stock_code → corp_code 매핑 로드 (최초 1회 ZIP 다운로드)."""
        cache = _CACHE_DIR / "corp_codes.json"
        if cache.exists() and not force:
            self._corp_map = json.loads(cache.read_text(encoding="utf-8"))
            return self._corp_map

        if not self.enabled:
            return {}

        url = f"{self.BASE}/corpCode.xml?crtfc_key={self.api_key}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            with zf.open("CORPCODE.xml") as xf:
                tree = ET.parse(xf)
        root = tree.getroot()
        mapping: dict[str, str] = {}
        for item in root.findall("list"):
            stock = (item.findtext("stock_code") or "").strip()
            corp = (item.findtext("corp_code") or "").strip()
            if stock and corp:
                mapping[stock] = corp
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
        self._corp_map = mapping
        return mapping

    def fetch_financials(self, stock_code: str, year: int, report: str = "11011") -> list[dict[str, Any]]:
        """재무제표 전체 (보고서코드 11011=사업보고서, 11014=3분기, 11013=반기, 11012=1분기)."""
        if not self._corp_map:
            self.load_corp_codes()
        corp = self._corp_map.get(stock_code)
        if not corp:
            return []
        try:
            res = self._get(
                "fnlttSinglAcntAll.json",
                corp_code=corp, bsns_year=str(year), reprt_code=report,
                fs_div="CFS",  # 연결재무제표
            )
        except Exception:
            return []
        if res.get("status") != "000":
            return []
        return res.get("list", [])

    def latest_partial_financials(
        self,
        stock_code: str,
        name: str,
        sector: str,
    ) -> dict[str, Any] | None:
        """가장 최근 사업보고서 → 재무 항목 보강 (sample_financials raw 형태로).

        DART OpenAPI 데이터에서 다음을 추출:
        - 매출액, 영업이익, 당기순이익
        - EBITDA (영업이익 + 감가상각비)
        - 자산총계, 부채총계, 자본총계
        - 순부채 (차입금 - 현금성자산)
        """
        from datetime import date
        if not self.enabled:
            return None
        # 최근 2년치 시도 (직전 회계연도 우선)
        cur_year = date.today().year
        rows: list[dict[str, Any]] = []
        for year in (cur_year - 1, cur_year - 2):
            rows = self.fetch_financials(stock_code, year, "11011")
            if rows:
                break
        if not rows:
            return None

        def find_amount(name_kw: str, sj: str = "") -> float:
            """account_nm 이 name_kw 포함하는 행의 thstrm_amount(당기) 반환."""
            for r in rows:
                if sj and r.get("sj_div") != sj:
                    continue
                if name_kw in (r.get("account_nm") or ""):
                    try:
                        return float((r.get("thstrm_amount") or "0").replace(",", ""))
                    except (ValueError, TypeError):
                        return 0.0
            return 0.0

        # 손익계산서 (sj_div=IS or CIS)
        revenue = find_amount("매출액", "IS") or find_amount("매출", "CIS")
        op_inc = find_amount("영업이익", "IS") or find_amount("영업이익", "CIS")
        net_inc = find_amount("당기순이익", "IS") or find_amount("당기순이익", "CIS")
        # 재무상태표 (sj_div=BS) — 총계
        total_assets = find_amount("자산총계", "BS")
        total_liab = find_amount("부채총계", "BS")
        total_equity = find_amount("자본총계", "BS")
        # 재무상태표 — 자산 세부 (자산가치접근법 보강)
        current_assets = find_amount("유동자산", "BS")
        tangible_assets = find_amount("유형자산", "BS")
        intangible_assets = find_amount("무형자산", "BS")
        inventory = find_amount("재고자산", "BS")
        receivables = find_amount("매출채권", "BS")
        investment_assets = find_amount("투자부동산", "BS")
        # 재무상태표 — 차입/현금 (순부채)
        cash = find_amount("현금및현금성자산", "BS")
        st_borrow = find_amount("단기차입금", "BS")
        lt_borrow = find_amount("장기차입금", "BS")
        # 현금흐름표 (sj_div=CF)
        depr = find_amount("감가상각비", "CF")
        net_debt = (st_borrow + lt_borrow) - cash

        ebitda = op_inc + depr if op_inc > 0 else 0
        fcf = net_inc * 0.85 if net_inc > 0 else 0  # 보수 추정

        if revenue <= 0 and op_inc <= 0 and net_inc <= 0:
            return None

        return {
            "ticker": stock_code,
            "name": name,
            "sector": sector,
            "revenue": revenue,
            "operating_income": op_inc,
            "net_income": net_inc,
            "ebitda": ebitda,
            "fcf": fcf,
            "total_assets": total_assets,
            "total_liabilities": total_liab,
            "total_equity": total_equity,
            "net_debt": net_debt,
            # 자산가치접근법 강화용 세부 자산
            "current_assets": current_assets,
            "tangible_assets": tangible_assets,
            "intangible_assets": intangible_assets,
            "inventory": inventory,
            "receivables": receivables,
            "investment_assets": investment_assets,
            "cash_equivalents": cash,
            "_dart_year": rows[0].get("bsns_year") if rows else "",
            "_source": "dart",
        }

    def fetch_disclosures(self, stock_code: str, page_count: int = 10) -> list[dict[str, Any]]:
        """최근 공시 목록."""
        if not self._corp_map:
            self.load_corp_codes()
        corp = self._corp_map.get(stock_code)
        if not corp:
            return []
        try:
            res = self._get("list.json", corp_code=corp, page_count=str(page_count))
        except Exception:
            return []
        if res.get("status") != "000":
            return []
        return res.get("list", [])
