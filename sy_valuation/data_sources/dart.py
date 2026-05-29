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

        def _parse(r: dict[str, Any]) -> float:
            try:
                return float((r.get("thstrm_amount") or "0").replace(",", ""))
            except (ValueError, TypeError):
                return 0.0

        def find_amount(keys, sj: str = "", allow_substring: bool = False) -> float:
            """account_id (IFRS 표준) 우선 → account_nm 정확매치 → (옵션) substring.

            keys 는 단일 문자열 또는 우선순위 리스트.
              - `ifrs-full_*`, `dart_*` 로 시작하면 account_id 매치
              - 그 외는 account_nm 매치 (공백·괄호·콤마 제거 후 정확 비교)
            allow_substring=True 면 정확 매치 실패 시 substring 폴백.
            """
            ks = [keys] if isinstance(keys, str) else list(keys)
            def _norm(s: str) -> str:
                return s.replace(" ", "").replace("(", "").replace(")", "").replace(",", "")
            id_keys = [k for k in ks if k.startswith("ifrs-full_") or k.startswith("dart_")]
            nm_keys = [k for k in ks if k not in id_keys]
            nm_keys_norm = [_norm(k) for k in nm_keys]

            for r in rows:
                if sj and r.get("sj_div") != sj:
                    continue
                # 1) account_id 정확 매치 (가장 신뢰 — IFRS 표준 태깅)
                aid = (r.get("account_id") or "").strip()
                if aid and aid in id_keys:
                    return _parse(r)
                # 2) account_nm 정확 매치 (정규화 후)
                nm_norm = _norm((r.get("account_nm") or "").strip())
                if nm_norm and nm_norm in nm_keys_norm:
                    return _parse(r)
            # 3) substring 폴백 (회사가 비표준 태깅한 케이스 — 최후의 수단)
            if allow_substring:
                for r in rows:
                    if sj and r.get("sj_div") != sj:
                        continue
                    nm_norm = _norm((r.get("account_nm") or "").strip())
                    for kw in nm_keys_norm:
                        if kw and kw in nm_norm:
                            return _parse(r)
            return 0.0

        # 손익계산서 (sj_div=IS or CIS) — IFRS account_id 우선
        revenue = (find_amount(["ifrs-full_Revenue", "매출액", "수익매출액", "영업수익"], "IS")
                   or find_amount(["ifrs-full_Revenue", "매출액", "수익매출액", "영업수익"], "CIS")
                   or find_amount(["매출액", "매출"], "IS", allow_substring=True))
        op_inc = (find_amount(["dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities", "영업이익", "영업이익손실"], "IS")
                  or find_amount(["dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities", "영업이익", "영업이익손실"], "CIS")
                  or find_amount("영업이익", "IS", allow_substring=True))
        net_inc = (find_amount(["ifrs-full_ProfitLoss", "당기순이익", "당기순이익손실"], "IS")
                   or find_amount(["ifrs-full_ProfitLoss", "당기순이익", "당기순이익손실"], "CIS")
                   or find_amount("당기순이익", "IS", allow_substring=True))

        # 재무상태표 — 총계 (IFRS ID 우선, "자본및부채총계" 같은 합계행 자동 회피)
        total_assets = find_amount(
            ["ifrs-full_Assets", "자산총계", "총자산", "자산합계"], "BS", allow_substring=True)
        total_equity = find_amount(
            ["ifrs-full_Equity", "자본총계", "총자본", "자본합계"], "BS", allow_substring=True)
        total_liab_raw = find_amount(
            ["ifrs-full_Liabilities", "부채총계", "총부채", "부채합계"], "BS", allow_substring=False)
        # 검증: 자산 = 부채 + 자본 — 자산·자본이 신뢰 가능하면 항등식 우선
        # "자본및부채총계"(= 자산총계) 행을 부채로 오매칭하는 케이스 차단
        if total_assets > 0 and total_equity > 0:
            total_liab_calc = total_assets - total_equity
            # raw가 자산총계와 ~동일하면 (오매칭 신호) 항등식 사용
            if total_liab_raw <= 0 or abs(total_liab_raw - total_assets) / total_assets < 0.02:
                total_liab = max(total_liab_calc, 0)
            else:
                # 둘 다 의미있는 값이면 raw 채택 (보고서가 직접 명시한 부채)
                total_liab = total_liab_raw
        else:
            total_liab = total_liab_raw

        # 재무상태표 — 자산 세부 (자산가치접근법 보강)
        current_assets = find_amount(
            ["ifrs-full_CurrentAssets", "유동자산"], "BS", allow_substring=True)
        tangible_assets = find_amount(
            ["ifrs-full_PropertyPlantAndEquipment", "유형자산"], "BS", allow_substring=True)
        intangible_assets = find_amount(
            ["ifrs-full_IntangibleAssetsOtherThanGoodwill", "ifrs-full_IntangibleAssetsAndGoodwill", "무형자산"],
            "BS", allow_substring=True)
        inventory = find_amount(
            ["ifrs-full_Inventories", "재고자산"], "BS", allow_substring=True)
        receivables = find_amount(
            ["ifrs-full_TradeAndOtherCurrentReceivables", "매출채권", "매출채권및기타채권"],
            "BS", allow_substring=True)
        investment_assets = find_amount(
            ["ifrs-full_InvestmentProperty", "투자부동산", "투자자산"], "BS", allow_substring=True)
        # 재무상태표 — 차입/현금 (순부채)
        cash = find_amount(
            ["ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "현금성자산"],
            "BS", allow_substring=True)
        st_borrow = find_amount(
            ["ifrs-full_ShorttermBorrowings", "dart_ShortTermBorrowings", "단기차입금"],
            "BS", allow_substring=True)
        lt_borrow = find_amount(
            ["ifrs-full_NoncurrentBorrowings", "dart_LongTermBorrowings", "장기차입금"],
            "BS", allow_substring=True)
        # 현금흐름표 (sj_div=CF)
        depr = find_amount(
            ["dart_DepreciationExpense", "ifrs-full_DepreciationAndAmortisationExpense", "감가상각비"],
            "CF", allow_substring=True)
        # CapEx — 투자활동 현금흐름의 "유형자산의 취득" 등 (절대값). 부재 시 0 → 추정 폴백
        capex = find_amount(
            ["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
             "dart_PurchaseOfPropertyPlantAndEquipment",
             "유형자산의취득", "유형자산의 취득"],
            "CF", allow_substring=True)
        capex = abs(capex)

        # 손익계산서 추가 항목 — 법인세비용, 이자비용 (WACC 계산용)
        tax_expense = (
            find_amount(["ifrs-full_IncomeTaxExpenseContinuingOperations", "법인세비용", "법인세"], "IS")
            or find_amount(["ifrs-full_IncomeTaxExpenseContinuingOperations", "법인세비용", "법인세"], "CIS")
            or find_amount("법인세비용", "IS", allow_substring=True)
        )
        interest_expense = (
            find_amount(["ifrs-full_InterestExpense", "dart_InterestExpense", "이자비용", "금융원가"], "IS")
            or find_amount(["ifrs-full_InterestExpense", "dart_InterestExpense", "이자비용", "금융원가"], "CIS")
            or find_amount("이자비용", "IS", allow_substring=True)
        )

        net_debt = (st_borrow + lt_borrow) - cash
        ebitda = op_inc + depr if op_inc > 0 else 0
        # FCFF 는 sy_builder 에서 정통 공식으로 계산 — 여기선 raw 데이터만 전달.
        # 다만 호환을 위해 fcf 필드도 유지 (sample_financials 형식과 일치).
        # fcf = EBIT(1-Tc) + 감가상각 - CapEx - ΔWC. 운전자본은 데이터 부족 → 0 가정.
        if op_inc > 0:
            tc_eff = (tax_expense / op_inc) if tax_expense > 0 else 0.22
            tc_eff = min(max(tc_eff, 0.10), 0.30)   # 10~30% 범위로 클립 (이상치 방지)
            dep_eff = depr if depr > 0 else op_inc * 0.05
            cap_eff = capex if capex > 0 else dep_eff * 0.8
            fcf_calc = op_inc * (1 - tc_eff) + dep_eff - cap_eff
            # 음수면 보수 폴백: 영업이익 × (1-Tc) × 0.75
            fcf = fcf_calc if fcf_calc > 0 else op_inc * (1 - tc_eff) * 0.75
        else:
            fcf = 0

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
            # WACC/FCFF 정통 공식용 추가 항목
            "depreciation": depr,
            "capex": capex,
            "tax_expense": tax_expense,
            "interest_expense": interest_expense,
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

    # ── 전체 상장사 universe 빌더 (피어 매칭용) ───────────────────────────

    def fetch_company_info(self, stock_code: str) -> dict[str, Any] | None:
        """단일 상장사의 기본 정보 (업종코드, 시장구분)."""
        if not self._corp_map:
            self.load_corp_codes()
        corp = self._corp_map.get(stock_code)
        if not corp:
            return None
        try:
            res = self._get("company.json", corp_code=corp)
        except Exception:
            return None
        if res.get("status") != "000":
            return None
        return res

    def build_listed_universe(
        self,
        max_workers: int = 5,
        log_progress: bool = False,
    ) -> list[dict[str, Any]]:
        """KRX 전 상장사 universe 빌더 (주 1회 배치).

        corp_codes 매핑(약 2,500개) 을 돌며 company.json 호출 →
        ticker, name, induty_code(KSIC), 시장구분 추출 → sample 섹터 라벨로 매핑.

        결과는 data/cache/dart_universe.json 에 저장. 7일 TTL.
        병렬 5-worker 로 약 3~4분 소요. DART rate-limit (~20,000 req/day) 한도 내.
        """
        import concurrent.futures
        from .dart_sectors import map_induty

        if not self.enabled:
            return []
        if not self._corp_map:
            self.load_corp_codes()

        # corp_cls: Y=유가증권(KOSPI), K=코스닥, N=코넥스, E=기타
        MARKET_MAP = {"Y": "KOSPI", "K": "KOSDAQ", "N": "KONEX", "E": "ETC"}

        stock_codes = list(self._corp_map.keys())
        total = len(stock_codes)
        results: list[dict[str, Any]] = []

        def fetch_one(stock: str) -> dict[str, Any] | None:
            info = self.fetch_company_info(stock)
            if not info:
                return None
            cls = info.get("corp_cls", "")
            # 코스피/코스닥만 (코넥스/비상장 제외)
            if cls not in ("Y", "K"):
                return None
            induty = (info.get("induty_code") or "").strip()
            return {
                "ticker": stock,
                "name": (info.get("corp_name") or "").strip(),
                "induty_code": induty,
                "sector": map_induty(induty),
                "market": MARKET_MAP.get(cls, "ETC"),
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            for i, row in enumerate(ex.map(fetch_one, stock_codes)):
                if row:
                    results.append(row)
                if log_progress and (i + 1) % 200 == 0:
                    print(f"  DART universe progress: {i+1}/{total} ({len(results)} valid)")

        # 캐시 파일 저장 (scheduler 가 7일 주기로 갱신)
        cache_path = _CACHE_DIR / "dart_universe.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"tickers": results}, ensure_ascii=False),
            encoding="utf-8",
        )
        return results

    def load_universe_cache(self) -> list[dict[str, Any]]:
        """캐시 파일에서 universe 로드 (없으면 빈 리스트)."""
        cache_path = _CACHE_DIR / "dart_universe.json"
        if not cache_path.exists():
            return []
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return data.get("tickers", [])
        except Exception:
            return []
