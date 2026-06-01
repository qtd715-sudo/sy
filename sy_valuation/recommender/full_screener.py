"""전종목 저평가 스크리너 — 배치 평가 + 파일 캐시.

보통주(KOSPI+KOSDAQ) 전체를 병렬로 평가해 결과를 파일에 저장한다.
화면 요청은 이 캐시만 읽어 **즉시** 응답한다 (종목별 실시간 계산 안 함).

산출물 (둘 다 upside = 현재가 대비 적정가 상승율 내림차순 정렬):
  - items_9model : find_undervalued(=9모델 가중평균) 결과 (ScreenResult.to_dict 모양)
  - items_sy     : sy_evaluate(=SY 3접근법) 결과 (SyValuationResult.to_dict 모양)

기존 단일종목 평가 함수(app.repo.get_or_build_financials + find_undervalued,
app.sy_evaluate)를 그대로 재사용 → 단일종목 화면과 결과가 100% 일치한다.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .screener import find_undervalued

# 캐시는 git 추적 경로에 저장 (data/cache/ 는 gitignore라 GitHub Actions가 커밋 불가).
# GitHub Actions 가 이 파일을 4시간마다 갱신·커밋 → Render 가 그대로 서빙.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CACHE_FILE = _DATA_DIR / "screener_cache.json"

# 동시 빌드 방지 (스케줄러 + 수동 트리거 충돌 차단)
_build_lock = threading.Lock()
_building = False

_KST = timezone(timedelta(hours=9))

# 상승여력 상한 — 이보다 크면 거의 확실히 데이터 오류 (재무 누락/주가 이상)로 간주해 제외.
# Naver 실시간 데이터만으로는 적정가가 부풀려지는 종목이 있어 노이즈 차단용.
MAX_UPSIDE = 3.0  # 300%


def is_common_stock(meta: dict[str, Any]) -> bool:
    """보통주(KOSPI/KOSDAQ)만 통과 — ETF·우선주·스팩·외국기업 제외.

    한국 보통주 코드는 6자리 + 끝자리 0. 우선주는 끝자리 5/7/9, 외국주권/KDR은 9로 시작 → 제외.
    """
    if meta.get("asset") != "stock":
        return False
    if meta.get("exchange") not in ("KOSPI", "KOSDAQ"):
        return False
    code = str(meta.get("ticker", ""))
    if not (len(code) == 6 and code.isdigit()):
        return False
    if code[0] == "9":       # 외국주권/KDR (재무 신뢰도 낮음) 제외
        return False
    if code[-1] != "0":      # 우선주 등 제외 (보통주는 끝자리 0)
        return False
    name = str(meta.get("name", ""))
    if "스팩" in name or "기업인수목적" in name:
        return False
    return True


def _sane_upside(u: float) -> bool:
    """상승여력 정상 범위 (0 초과 ~ MAX_UPSIDE 이하). 극단 outlier=데이터 오류 제외."""
    return 0.0 < u <= MAX_UPSIDE


def universe_tickers(app) -> list[dict[str, Any]]:
    """평가 대상 보통주 메타 리스트."""
    return [m for m in app.repo.list_tickers() if is_common_stock(m)]


def _eval_one(app, meta: dict[str, Any]):
    """한 종목 평가 → (Financials | None, sy_result_dict | None).

    9모델용 Financials 와 SY 평가 결과를 각각 수집. 어느 한쪽이 실패해도 나머지는 사용.
    """
    tk = meta["ticker"]
    fin = None
    sy_row = None

    # 1) 9모델용 Financials (실시간 가격 반영)
    try:
        fin = app.repo.get_or_build_financials(
            tk, live=app.live, naver=app.naver, dart=app.dart, naver_fin=app.naver_fin,
        )
        if fin:
            try:
                q = app.price.quote(tk)
                if q and q.price > 0:
                    fin.current_price = q.price
            except Exception:
                pass
    except Exception:
        fin = None

    # 2) SY 3접근법 (단일종목 화면과 동일 로직)
    try:
        s = app.sy_evaluate(tk)
        if (isinstance(s, dict) and not s.get("error")
                and s.get("fair_price_mid", 0) > 0
                and s.get("current_price", 0) > 0
                and s.get("upside_per_share", 0) > 0):
            sy_row = s
    except Exception:
        sy_row = None

    return fin, sy_row


def build_cache(app, max_workers: int = 10, limit: int | None = None,
                log=None) -> dict[str, Any]:
    """전종목 배치 평가 → 캐시 파일 저장. 요약 dict 반환.

    limit: 테스트용 — 앞에서 N개만 평가.
    """
    global _building
    with _build_lock:
        if _building:
            return {"skipped": "already building"}
        _building = True

    def _log(msg: str):
        if log:
            log(msg)

    try:
        metas = universe_tickers(app)
        if limit:
            metas = metas[:limit]
        total = len(metas)
        _log(f"전종목 스크리너 배치 시작: {total}종목 (workers={max_workers})")

        t0 = time.time()
        fins: list[Any] = []
        sy_rows: list[dict[str, Any]] = []
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for fin, sy_row in ex.map(lambda m: _eval_one(app, m), metas):
                if fin is not None:
                    fins.append(fin)
                if sy_row is not None:
                    sy_rows.append(sy_row)
                done += 1
                if log and done % 200 == 0:
                    _log(f"  진행: {done}/{total} ({time.time()-t0:.0f}s)")

        built_at = time.time()
        built_at_str = datetime.fromtimestamp(built_at, _KST).strftime("%Y-%m-%d %H:%M")
        as_of_iso = datetime.fromtimestamp(built_at, _KST).isoformat()

        # 9모델: 정량필터 + upside 정렬은 find_undervalued 가 담당 (top_n=전체).
        # 화면 표(renderScreenTable)에 필요한 필드만 슬림하게 저장 (git 커밋 파일 크기↓).
        results = find_undervalued(fins, top_n=len(fins), strict=True)
        items_9 = []
        for r in results:
            d = r.to_dict()
            v = d.get("valuation", {})
            if not _sane_upside(v.get("upside", 0.0)):
                continue  # 극단 outlier(데이터 오류) 제외
            items_9.append({
                "valuation": {k: v.get(k) for k in
                              ("ticker", "name", "sector", "current_price", "fair_price", "upside", "rating")},
                "roe": d.get("roe"), "per_now": d.get("per_now"), "pbr_now": d.get("pbr_now"),
                "score": d.get("score"), "price_as_of": as_of_iso,
            })

        # SY: 극단 outlier 제외 후 upside(주당 상승여력) 내림차순. 표에 필요한 필드만 저장.
        SY_KEYS = ("ticker", "name", "sector", "current_price", "fair_price_mid",
                   "upside_per_share", "market_cap", "enterprise_mid", "rating")
        sy_rows = [r for r in sy_rows if _sane_upside(r.get("upside_per_share", 0.0))]
        sy_rows.sort(key=lambda r: r.get("upside_per_share", 0.0), reverse=True)
        sy_rows = [{**{k: r.get(k) for k in SY_KEYS}, "price_as_of": as_of_iso} for r in sy_rows]

        payload = {
            "built_at": built_at,
            "built_at_str": built_at_str,
            "duration_sec": round(built_at - t0, 1),
            "universe_count": total,
            "evaluated_9model": len(fins),
            "count_9model": len(items_9),
            "count_sy": len(sy_rows),
            "items_9model": items_9,
            "items_sy": sy_rows,
        }
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_CACHE_FILE)  # 원자적 교체 — 읽는 중 깨짐 방지

        summary = {k: payload[k] for k in (
            "built_at_str", "duration_sec", "universe_count",
            "count_9model", "count_sy")}
        _log(f"전종목 스크리너 배치 완료: {summary}")
        return summary
    finally:
        _building = False


def load_cache() -> dict[str, Any] | None:
    """캐시 파일 로드 (없거나 깨졌으면 None)."""
    if not _CACHE_FILE.exists():
        return None
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def top_9model(n: int = 10) -> list[dict[str, Any]] | None:
    """9모델 저평가 상위 N — 캐시 없으면 None."""
    c = load_cache()
    if not c:
        return None
    return c.get("items_9model", [])[:n]


def top_sy(n: int = 10) -> list[dict[str, Any]] | None:
    """SY 평가법 저평가 상위 N — 캐시 없으면 None."""
    c = load_cache()
    if not c:
        return None
    return c.get("items_sy", [])[:n]


def cache_age_sec() -> float | None:
    """캐시 파일 나이(초) — 없으면 None."""
    if not _CACHE_FILE.exists():
        return None
    return time.time() - _CACHE_FILE.stat().st_mtime
