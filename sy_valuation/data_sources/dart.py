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


# 업종별 감가상각 추정율 (매출 대비). DART fnlttSinglAcntAll 은 감가상각을 주석에만 둬서,
# 기능별-표시 기업(삼성 등 대형주 다수)은 본표에서 D&A=0 으로 잡힌다. 그 경우 FCFF 계산용으로
# 매출 × 업종율 로 추정한다. 매출 기준인 이유: 영업이익은 경기 따라 출렁이지만(분모 부적합)
# 감가상각/매출 비율은 업종별로 안정적이다.
_DEPR_GROUP_RATE = {
    "초자본집약": 0.12,  # 반도체·통신·2차전지·디스플레이 (팹/망 감가 큼)
    "일반제조": 0.06,    # 자동차·철강·조선·화학·기계 등
    "건설": 0.02,
    "유통": 0.03,
    "서비스": 0.04,      # IT서비스·SW·금융·엔터
    "기타": 0.03,
}

# 시스템 세부 섹터명(dart_sectors) → 그룹 키워드 매핑. 초자본집약 먼저 검사.
_DEPR_GROUP_KEYWORDS = (
    ("초자본집약", ("반도체", "디스플레이", "2차전지", "배터리", "통신")),
    ("일반제조", ("전자부품", "전기설비", "자동차", "철강", "조선", "에너지", "화학", "정유",
                "기계", "가정용기기", "의료기기", "의료용품", "의약", "바이오", "정밀",
                "조명", "식료품", "음식료", "제조", "소재", "부품", "섬유", "타이어")),
    ("건설", ("건설", "엔지니어링", "플랜트", "건자재")),
    ("유통", ("유통", "소매", "쇼핑", "도매", "무역", "백화점", "마트", "홈쇼핑")),
    ("서비스", ("서비스", "SW", "소프트웨어", "시스템", "데이터", "정보", "게임", "인터넷",
               "은행", "보험", "금융", "투자", "증권", "엔터", "미디어", "출판", "광고",
               "교육", "여행", "운송", "물류", "레저")),
)


def _depr_rate_for_sector(sector: str) -> float:
    """섹터명 → 감가상각 추정율(매출 대비). 키워드 매칭, 미분류는 기타(3%)."""
    s = sector or ""
    for group, kws in _DEPR_GROUP_KEYWORDS:
        if any(kw in s for kw in kws):
            return _DEPR_GROUP_RATE[group]
    return _DEPR_GROUP_RATE["기타"]


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

        # 24h 캐시 — 같은 종목을 9모델·SY 두 경로가 각각 호출하므로(within-run 중복)
        # DART 콜을 종목당 2→1 로 줄여 일일 한도(20,000)를 보호한다.
        # 성공 결과만 캐시 → 020(한도 초과)으로 None 이 나온 경우는 다음에 재시도.
        _cache = None
        cache_key = f"dart:partial:{stock_code}"
        try:
            from .cache import get_cache
            _cache = get_cache()
            hit = _cache.get(cache_key)
            if hit:
                return hit[0]
        except Exception:
            _cache = None

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
        # 감가상각비(D&A): 현금흐름표(간접법 가산) → 손익계산서(성격별 표시) 순으로 파싱.
        depr = find_amount(
            ["dart_DepreciationExpense", "ifrs-full_DepreciationAndAmortisationExpense",
             "감가상각비", "무형자산상각비"],
            "CF", allow_substring=True)
        if depr <= 0:
            depr = find_amount(
                ["ifrs-full_DepreciationAndAmortisationExpense", "감가상각비", "무형자산상각비"],
                "IS", allow_substring=True)
        # 기능별 표시 기업(삼성 등)은 감가상각이 본표에 없고 주석에만 있어 0으로 잡힌다.
        # → 업종별 매출 비율로 추정 (초자본집약 12% / 일반제조 6% / 건설 2% / 유통 3% /
        #    서비스 4% / 기타 3%). 매출이 0이면 추정 생략(아래 FCFF 폴백으로 처리).
        depr_estimated = False
        if depr <= 0 and op_inc > 0 and revenue > 0:
            depr = revenue * _depr_rate_for_sector(sector)
            depr_estimated = True
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
        # FCFF 정통 공식: EBIT(1-Tc) + 감가상각 - CapEx - ΔWC (운전자본 ΔWC=0 가정).
        # 감가상각은 위에서 파싱 실패 시 업종 추정값(depr_estimated)이 들어와 있다.
        if op_inc > 0:
            tc_eff = (tax_expense / op_inc) if tax_expense > 0 else 0.22
            tc_eff = min(max(tc_eff, 0.10), 0.30)   # 10~30% 범위로 클립 (이상치 방지)
            dep_eff = depr if depr > 0 else op_inc * 0.05
            cap_eff = capex if capex > 0 else dep_eff * 0.8
            fcf_calc = op_inc * (1 - tc_eff) + dep_eff - cap_eff
            # 그래도 음수면(추정 D&A < 실제 CapEx) 보수 폴백: 영업이익 × (1-Tc) × 0.75
            fcf = fcf_calc if fcf_calc > 0 else op_inc * (1 - tc_eff) * 0.75
        else:
            fcf = 0

        if revenue <= 0 and op_inc <= 0 and net_inc <= 0:
            return None

        result = {
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
        # 성공 결과만 24h 캐시 (위 None 반환 경로는 캐시 안 함 → 한도 복구 후 재시도)
        if _cache is not None:
            try:
                _cache.set(cache_key, result, ttl_sec=86400, source="dart")
            except Exception:
                pass
        return result

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

    @staticmethod
    def _fetch_naver_market_cap(stock_code: str, timeout: int = 5) -> float:
        """Naver polling API 로 시가총액 가져오기 (배치용).

        polling.finance.naver.com — DART OpenAPI 와 무관, 별도 호출.
        실패 시 0 반환 (피어 매칭에서 size_proxy 폴백).
        """
        try:
            url = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{stock_code}"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            d = (data.get("datas") or [None])[0]
            if not d:
                return 0.0
            mcap = float(d.get("marketValueFullRaw") or 0)
            return mcap
        except Exception:
            return 0.0

    def build_listed_universe(
        self,
        max_workers: int = 5,
        log_progress: bool = False,
    ) -> list[dict[str, Any]]:
        """KRX 전 상장사 universe 빌더 (주 1회 배치).

        corp_codes 매핑(약 2,500개) 을 돌며 다음 데이터 수집:
        - DART company.json: induty_code(KSIC), 시장구분
        - Naver polling: 시가총액 (피어 size_proxy 용)

        결과는 data/cache/dart_universe.json 에 저장. 7일 TTL.
        병렬 5-worker 로 약 5~7분 소요 (DART + Naver 2회 호출 / 종목).
        DART rate-limit (~20,000 req/day) 한도 내.
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
            # 시총 — Naver polling (DART 와 무관, 별도 호출)
            mcap = self._fetch_naver_market_cap(stock)
            return {
                "ticker": stock,
                "name": (info.get("corp_name") or "").strip(),
                "induty_code": induty,
                "sector": map_induty(induty),
                "market": MARKET_MAP.get(cls, "ETC"),
                "market_cap": mcap,
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
