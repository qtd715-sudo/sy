"""B2B 계층 — 결정론적 계산 API(v1) + MCP 서버.

모바일 앱용 조회 API(/api/sy/evaluate 등)와 달리, 이 계층은 외부 시스템·AI 에이전트가
직접 붙는 것을 전제로 한다.

    POST /api/v1/valuations/compute   가정(assumptions)·재무(inputs)를 받아 재계산
    GET  /api/v1/openapi.json         OpenAPI 3.1 스펙 (에이전트/코드젠용)
    POST /mcp                         MCP(Model Context Protocol) JSON-RPC 엔드포인트

핵심 계약
  - 같은 입력(input_hash) → 항상 같은 출력. LLM 은 계산에 관여하지 않는다.
  - `inputs` 를 직접 주면 외부 데이터 호출 없이 순수 계산만 한다 (비상장사·딜 타깃 평가).
  - `ticker` 만 주면 DART/Naver 에서 재무를 가져와 기본 입력을 만든 뒤 계산한다.

환경변수
  SY_API_KEYS            쉼표 구분 API 키. 설정 시 /api/v1/*, /mcp 는 키 필수. 미설정 = 공개 데모.
  SY_RATE_LIMIT_PER_MIN  키(또는 IP)당 분당 호출 한도 (기본 300).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import threading
import time
import uuid
from collections import deque
from typing import Any

from .valuation.sy_method import (
    SyInputs, evaluate_sy, calculate_wacc, calculate_growth_rate,
)
from .valuation.sy_builder import SECTOR_BETA, FALLBACK_WACC

ENGINE_VERSION = "sy-engine/1.0.0"
MCP_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_BODY_BYTES = 256 * 1024

_FIELDS = {f.name: f for f in dataclasses.fields(SyInputs)}
_TEXT_FIELDS = {"ticker", "name", "sector", "peer_source"}
_NON_NUMERIC = _TEXT_FIELDS | {"peers", "normalization"}

# 가정으로 덮어쓸 수 있는 필드와 허용 범위 (min, max)
ASSUMPTION_BOUNDS: dict[str, tuple[float, float]] = {
    "wacc": (0.01, 0.50),
    "growth_rate_short": (-0.50, 1.00),
    "growth_rate_long": (-0.50, 1.00),
    "terminal_growth": (-0.05, 0.10),
    "forecast_years": (1, 30),
    "beta": (0.0, 5.0),
    "tax_rate": (0.0, 0.60),
    "risk_free_rate": (0.0, 0.20),
    "market_risk_premium": (0.0, 0.20),
    "dividend_payout_ratio": (0.0, 1.0),
    "liquidation_discount": (0.0, 1.0),
    "peer_per_avg": (0.0, 500.0),
    "peer_pbr_avg": (0.0, 100.0),
    "peer_psr_avg": (0.0, 100.0),
    "peer_ev_ebitda_avg": (0.0, 200.0),
}
SENSITIVITY_METRICS = {
    "fair_price_mid", "fair_price_min", "fair_price_max",
    "enterprise_mid", "enterprise_min", "enterprise_max",
    "income_dcf", "income_mid", "asset_mid", "market_mid",
    "market_per", "market_ev_ebitda", "income_ebitda_multiple",
}
_WACC_DRIVERS = {"beta", "tax_rate", "risk_free_rate", "market_risk_premium"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


# ---------- 인증 · 호출 한도 ----------

_rate_lock = threading.Lock()
_rate_hits: dict[str, deque] = {}


def _api_keys() -> set[str]:
    return {k.strip() for k in os.environ.get("SY_API_KEYS", "").split(",") if k.strip()}


def authorize(headers: Any, client_ip: str) -> str:
    """요청 주체(키 또는 IP) 식별자를 돌려준다. 실패 시 ApiError."""
    keys = _api_keys()
    token = (headers.get("X-API-Key") or "").strip()
    auth = headers.get("Authorization") or ""
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if keys:
        if token not in keys:
            raise ApiError(401, "unauthorized", "유효한 API 키가 필요합니다 (Authorization: Bearer <key>).")
        principal = "key:" + hashlib.sha256(token.encode()).hexdigest()[:12]
    else:
        principal = "ip:" + (client_ip or "unknown")

    limit = int(os.environ.get("SY_RATE_LIMIT_PER_MIN", "300") or 300)
    now = time.time()
    with _rate_lock:
        q = _rate_hits.setdefault(principal, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            raise ApiError(429, "rate_limited", f"분당 호출 한도({limit})를 초과했습니다.",
                           retry_after_sec=int(60 - (now - q[0])) + 1)
        q.append(now)
        if len(_rate_hits) > 5000:  # 메모리 보호
            for k in [k for k, v in _rate_hits.items() if not v or now - v[-1] > 60]:
                _rate_hits.pop(k, None)
    return principal


# ---------- 입력 구성 ----------

def _num(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(422, "invalid_input", f"'{name}' 은(는) 숫자여야 합니다.", field=name)
    if value != value or value in (float("inf"), float("-inf")):
        raise ApiError(422, "invalid_input", f"'{name}' 값이 유효하지 않습니다.", field=name)
    return float(value)


def _inputs_from_dict(d: dict[str, Any], app: Any) -> SyInputs:
    """클라이언트가 준 재무 dict → SyInputs. 빠진 가정은 엔진 기본 규칙으로 채운다."""
    if not isinstance(d, dict):
        raise ApiError(422, "invalid_input", "'inputs' 는 객체여야 합니다.")
    unknown = sorted(k for k in d if k not in _FIELDS)
    if unknown:
        raise ApiError(422, "unknown_field", f"알 수 없는 입력 필드: {', '.join(unknown)}",
                       allowed=sorted(_FIELDS))
    kw: dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if k in _TEXT_FIELDS:
            kw[k] = str(v)[:80]
        elif k == "peers":
            kw[k] = v if isinstance(v, list) else []
        elif k == "normalization":
            kw[k] = v if isinstance(v, dict) else {}
        elif k == "forecast_years" or k == "base_year":
            kw[k] = int(_num(k, v))
        else:
            kw[k] = _num(k, v)
    kw.setdefault("ticker", "CUSTOM")
    kw.setdefault("name", "Custom Company")
    kw.setdefault("sector", "기타")

    price = kw.get("current_price", 0.0)
    shares = kw.get("shares_outstanding", 0.0)
    if not kw.get("market_cap"):
        kw["market_cap"] = price * shares  # 비상장이면 0 → 상승률 계산 생략
    if not kw.get("total_equity") and kw.get("total_assets") and kw.get("total_liabilities") is not None:
        kw["total_equity"] = kw["total_assets"] - kw.get("total_liabilities", 0.0)

    # 피어 멀티플: 입력 > 섹터 표준 > 기본값
    sector_mults: dict[str, float] = {}
    try:
        sector_mults = (app.repo.sector_table() or {}).get(kw["sector"], {}) or {}
    except Exception:
        pass
    for field, key, default in (
        ("peer_per_avg", "per", 12.0), ("peer_pbr_avg", "pbr", 1.0),
        ("peer_psr_avg", "psr", 1.0), ("peer_ev_ebitda_avg", "ev_ebitda", 8.0),
    ):
        if not kw.get(field):
            kw[field] = float(sector_mults.get(key, default))

    if "beta" not in kw:
        kw["beta"] = SECTOR_BETA.get(kw["sector"], 1.0)
    if "growth_rate_short" not in kw:
        kw["growth_rate_short"] = calculate_growth_rate(
            kw.get("net_income", 0.0), kw.get("total_equity", 0.0),
            kw.get("dividend_payout_ratio", 0.30))
    if "growth_rate_long" not in kw:
        kw["growth_rate_long"] = kw["growth_rate_short"] * 0.5
    inp = SyInputs(**kw)
    if "wacc" not in kw:
        inp.wacc = _derive_wacc(inp)
    return inp


def _derive_wacc(inp: SyInputs) -> float:
    if inp.market_cap <= 0:
        return FALLBACK_WACC
    return calculate_wacc(
        market_cap=inp.market_cap, net_debt=inp.net_debt,
        interest_expense=inp.interest_expense, tax_rate=inp.tax_rate,
        beta=inp.beta, rf=inp.risk_free_rate, mrp=inp.market_risk_premium,
    )


def _apply_assumptions(inp: SyInputs, assumptions: dict[str, Any]) -> tuple[SyInputs, dict[str, Any]]:
    if not assumptions:
        return inp, {}
    if not isinstance(assumptions, dict):
        raise ApiError(422, "invalid_input", "'assumptions' 는 객체여야 합니다.")
    applied: dict[str, Any] = {}
    for k, v in assumptions.items():
        if k not in ASSUMPTION_BOUNDS:
            raise ApiError(422, "unknown_assumption", f"조정할 수 없는 가정: {k}",
                           allowed=sorted(ASSUMPTION_BOUNDS))
        lo, hi = ASSUMPTION_BOUNDS[k]
        x = _num(k, v)
        if not lo <= x <= hi:
            raise ApiError(422, "out_of_range", f"'{k}' 는 {lo}~{hi} 범위여야 합니다.", field=k)
        applied[k] = int(x) if k == "forecast_years" else x
    out = dataclasses.replace(inp, **applied)
    # 파생 규칙: 엔진 기본 빌더와 동일하게 유지
    if "growth_rate_short" in applied and "growth_rate_long" not in applied:
        out.growth_rate_long = out.growth_rate_short * 0.5
        applied["growth_rate_long"] = out.growth_rate_long
    if "wacc" not in applied and _WACC_DRIVERS & applied.keys():
        out.wacc = _derive_wacc(out)
        applied["wacc"] = out.wacc
    if out.wacc <= out.terminal_growth:
        raise ApiError(422, "invalid_assumption",
                       "WACC 는 영구성장률(terminal_growth)보다 커야 합니다.",
                       wacc=out.wacc, terminal_growth=out.terminal_growth)
    return out, applied


def _input_hash(inp: SyInputs) -> str:
    canon = json.dumps(dataclasses.asdict(inp), sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _evaluate(inp: SyInputs) -> dict[str, Any]:
    out = evaluate_sy(inp).to_dict()
    if inp.market_cap <= 0:
        # 시가총액 없음(비상장) — 시총 대비 상승률·등급은 의미 없음
        for k in ("upside_min", "upside_mid", "upside_max", "upside_per_share"):
            out[k] = None
        out["market_cap"] = 0
        out["rating"] = "N/A"
        out["notes"] = (out.get("notes") or []) + ["시가총액 미입력 — 상승률·등급 산출 생략 (절대가치만 제공)"]
    return out


def _headline(out: dict[str, Any]) -> float:
    return out.get("fair_price_mid") or out.get("enterprise_mid") or 0.0


# ---------- 민감도 ----------

def _default_axis(name: str, base: float) -> list[float]:
    step = {"wacc": 0.005, "terminal_growth": 0.0025, "growth_rate_short": 0.01,
            "growth_rate_long": 0.005}.get(name, abs(base) * 0.1 or 0.1)
    lo, hi = ASSUMPTION_BOUNDS[name]
    vals = [round(base + step * i, 6) for i in (-2, -1, 0, 1, 2)]
    return [v for v in vals if lo <= v <= hi]


def _sensitivity(inp: SyInputs, spec: Any) -> dict[str, Any]:
    spec = spec if isinstance(spec, dict) else {}
    x, y = spec.get("x", "wacc"), spec.get("y", "terminal_growth")
    for axis in (x, y):
        if axis not in ASSUMPTION_BOUNDS or axis == "forecast_years":
            raise ApiError(422, "invalid_sensitivity", f"민감도 축으로 쓸 수 없는 가정: {axis}")
    if x == y:
        raise ApiError(422, "invalid_sensitivity", "민감도의 x, y 축은 서로 달라야 합니다.")

    def axis_values(name: str, key: str) -> list[float]:
        vals = spec.get(key)
        if vals is None:
            return _default_axis(name, float(getattr(inp, name)))
        if not isinstance(vals, list) or not 1 <= len(vals) <= 9:
            raise ApiError(422, "invalid_sensitivity", f"'{key}' 는 1~9개 숫자 배열이어야 합니다.")
        lo, hi = ASSUMPTION_BOUNDS[name]
        out = [_num(key, v) for v in vals]
        if any(not lo <= v <= hi for v in out):
            raise ApiError(422, "out_of_range", f"'{key}' 값은 {lo}~{hi} 범위여야 합니다.")
        return out

    xs, ys = axis_values(x, "x_values"), axis_values(y, "y_values")
    # 종합 적정가는 접근법별 중앙값의 평균이라 단일 가정에 둔감할 수 있다.
    # metric 으로 개별 모델 값(예: income_dcf)을 지정하면 그 모델의 민감도를 본다.
    has_shares = inp.shares_outstanding > 0 or inp.current_price > 0
    metric = spec.get("metric") or ("fair_price_mid" if has_shares else "enterprise_mid")
    if metric not in SENSITIVITY_METRICS:
        raise ApiError(422, "invalid_sensitivity", f"지원하지 않는 metric: {metric}",
                       allowed=sorted(SENSITIVITY_METRICS))
    grid: list[list[float | None]] = []
    for yv in ys:
        row: list[float | None] = []
        for xv in xs:
            trial = dataclasses.replace(inp, **{x: xv, y: yv})
            if x == "growth_rate_short" or y == "growth_rate_short":
                trial.growth_rate_long = trial.growth_rate_short * 0.5
            row.append(None if trial.wacc <= trial.terminal_growth else _evaluate(trial).get(metric))
        grid.append(row)
    return {"x": x, "y": y, "x_values": xs, "y_values": ys, "metric": metric, "grid": grid}


# ---------- 공개 진입점 ----------

def compute(app: Any, body: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_request", "요청 본문은 JSON 객체여야 합니다.")
    ticker, raw_inputs = body.get("ticker"), body.get("inputs")
    if not ticker and raw_inputs is None:
        raise ApiError(422, "missing_input", "'ticker' 또는 'inputs' 중 하나는 필요합니다.")

    provenance: dict[str, Any] = {"engine": ENGINE_VERSION}
    if raw_inputs is not None:
        base_inp = _inputs_from_dict(raw_inputs, app)
        provenance["source"] = "client_inputs"
    else:
        fetched = app.sy_evaluate(str(ticker), normalize=body.get("normalize", True) is not False)
        if fetched.get("error"):
            raise ApiError(404, "not_found", fetched["error"], suggestions=fetched.get("suggestions", []))
        base_inp = SyInputs(**{k: v for k, v in fetched["inputs"].items() if k in _FIELDS})
        provenance.update(source="market_data",
                          financials_basis=fetched.get("financials_basis"),
                          price_as_of=fetched.get("price_as_of"))

    scenario_inp, applied = _apply_assumptions(base_inp, body.get("assumptions") or {})
    result = _evaluate(scenario_inp)
    resp: dict[str, Any] = {
        "request_id": "req_" + uuid.uuid4().hex[:16],
        "engine_version": ENGINE_VERSION,
        "deterministic": True,
        "input_hash": _input_hash(scenario_inp),
        "provenance": provenance,
        "assumptions_applied": applied,
        "result": result,
    }
    if applied:
        base = _evaluate(base_inp)
        b, s = _headline(base), _headline(result)
        resp["baseline"] = {
            "input_hash": _input_hash(base_inp),
            "fair_price_mid": base.get("fair_price_mid"),
            "enterprise_mid": base.get("enterprise_mid"),
            "income_mid": base.get("income_mid"),
            "asset_mid": base.get("asset_mid"),
            "market_mid": base.get("market_mid"),
            "wacc": base_inp.wacc,
            "growth_rate_short": base_inp.growth_rate_short,
            "terminal_growth": base_inp.terminal_growth,
        }
        resp["delta"] = {"abs": s - b, "pct": ((s - b) / b) if b else None}
    if body.get("sensitivity"):
        resp["sensitivity"] = _sensitivity(scenario_inp, body["sensitivity"])
    return resp


# ---------- MCP (JSON-RPC 2.0 over HTTP) ----------

_ASSUMPTION_SCHEMA = {
    "type": "object",
    "description": "덮어쓸 평가 가정. 비율은 소수(0.09 = 9%).",
    "properties": {k: {"type": "number", "minimum": lo, "maximum": hi}
                   for k, (lo, hi) in ASSUMPTION_BOUNDS.items()},
    "additionalProperties": False,
}

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_company",
        "description": "한국 상장기업을 이름 또는 종목코드로 검색해 ticker 를 찾는다. "
                       "다른 도구를 부르기 전에 ticker 를 확정할 때 사용.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "기업명 또는 6자리 종목코드"},
                           "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}},
            "required": ["query"],
        },
    },
    {
        "name": "get_valuation",
        "description": "상장기업의 기업가치를 수익·자산·상대가치 3접근법으로 계산한다. "
                       "DART 최신 공시 TTM 재무 기준. 모든 숫자는 결정론적 계산 결과이므로 "
                       "그대로 인용하고 임의로 재계산하지 말 것. 단위: 원.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "6자리 종목코드 또는 기업명"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "compute_valuation",
        "description": "가정(WACC·성장률·피어 멀티플 등)을 바꾸거나 재무를 직접 넣어 기업가치를 재계산한다. "
                       "'만약 WACC 가 10% 라면?' 같은 시나리오, 비상장사·M&A 타깃 평가에 사용. "
                       "ticker 또는 inputs 중 하나 필수. sensitivity 를 주면 2축 민감도 표를 함께 반환.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "inputs": {"type": "object",
                           "description": "직접 입력 재무(원 단위). 예: revenue, operating_income, net_income, "
                                          "ebitda, fcf, total_assets, total_liabilities, net_debt, "
                                          "shares_outstanding, sector"},
                "assumptions": _ASSUMPTION_SCHEMA,
                "sensitivity": {
                    "type": "object",
                    "properties": {"x": {"type": "string", "default": "wacc"},
                                   "y": {"type": "string", "default": "terminal_growth"},
                                   "x_values": {"type": "array", "items": {"type": "number"}},
                                   "y_values": {"type": "array", "items": {"type": "number"}}},
                },
            },
        },
    },
    {
        "name": "screen_undervalued",
        "description": "전 종목을 SY 평가법으로 평가한 결과 중 저평가 상위 종목을 반환한다 (배치 캐시 기준).",
        "inputSchema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}},
        },
    },
]


def _slim_valuation(out: dict[str, Any]) -> dict[str, Any]:
    """에이전트 컨텍스트 절약: 피어 상세·원시 입력 전체는 빼고 핵심만."""
    inputs = out.get("inputs") or {}
    keep_inputs = ("wacc", "growth_rate_short", "growth_rate_long", "terminal_growth", "beta",
                   "tax_rate", "peer_per_avg", "peer_pbr_avg", "peer_psr_avg", "peer_ev_ebitda_avg",
                   "revenue", "operating_income", "net_income", "ebitda", "fcf", "net_debt",
                   "normalized_fcf", "normalized_operating_income",
                   "normalized_net_income", "normalized_ebitda", "peer_source",
                   "total_assets", "total_liabilities", "total_equity")
    slim = {k: v for k, v in out.items() if k != "inputs"}
    slim["assumptions"] = {k: inputs.get(k) for k in keep_inputs if k in inputs}
    slim["peers"] = [p.get("name") or p.get("ticker") for p in (inputs.get("peers") or [])][:10]
    slim["normalization"] = {k: v for k, v in (inputs.get("normalization") or {}).items()
                             if k in ("applied", "cycle", "reason", "ttm_margin", "normal_margin")}
    slim["unit"] = "KRW"
    return slim


def _call_tool(app: Any, name: str, args: dict[str, Any]) -> Any:
    if name == "search_company":
        return app.search(str(args.get("query", "")), limit=int(args.get("limit", 5)))
    if name == "get_valuation":
        out = app.sy_evaluate(str(args.get("ticker", "")))
        if out.get("error"):
            raise ApiError(404, "not_found", out["error"], suggestions=out.get("suggestions", []))
        slim = _slim_valuation(out)
        slim.update(engine_version=ENGINE_VERSION, deterministic=True)
        return slim
    if name == "compute_valuation":
        resp = compute(app, args)
        resp["result"] = _slim_valuation(resp["result"])
        return resp
    if name == "screen_undervalued":
        return app.sy_undervalued(n=max(1, min(int(args.get("n", 10)), 50)))
    raise ApiError(404, "unknown_tool", f"알 수 없는 도구: {name}")


def _rpc_error(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle_mcp(app: Any, msg: Any) -> dict[str, Any] | None:
    """JSON-RPC 메시지 1건 처리. 알림(notification)이면 None."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _rpc_error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    rid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:
        return None  # notifications/initialized 등

    if method == "initialize":
        wanted = params.get("protocolVersion")
        version = wanted if wanted in MCP_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSIONS[0]
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "sy-valuation", "title": "SY Valuation Engine", "version": "1.0.0"},
            "instructions": "한국 상장·비상장 기업가치평가 엔진. 모든 수치는 결정론적 계산 결과다. "
                            "수치를 직접 계산하거나 추정하지 말고 도구 결과를 그대로 인용하라. "
                            "결과는 투자 권유가 아니라 계산 근거 자료다.",
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(args, dict):
            return _rpc_error(rid, -32602, "Invalid params")
        if name not in {t["name"] for t in MCP_TOOLS}:
            return _rpc_error(rid, -32602, f"Unknown tool: {name}")
        try:
            data = _call_tool(app, name, args)
            payload = data if isinstance(data, dict) else {"items": data}
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                "structuredContent": payload,
                "isError": False,
            }}
        except ApiError as e:
            err = e.to_dict()
        except Exception as e:  # 도구 실행 오류는 프로토콜 오류가 아니라 결과로 전달
            err = {"error": {"code": "internal_error", "message": str(e)}}
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(err, ensure_ascii=False)}],
            "isError": True,
        }}
    return _rpc_error(rid, -32601, f"Method not found: {method}")


# ---------- OpenAPI ----------

def openapi_spec() -> dict[str, Any]:
    num = {"type": "number"}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "SY Valuation API",
            "version": "1.0.0",
            "description": "결정론적 기업가치평가 계산 엔진. 같은 input_hash 는 항상 같은 결과를 낸다.",
        },
        "paths": {
            "/api/v1/valuations/compute": {"post": {
                "operationId": "computeValuation",
                "summary": "가정·재무를 받아 3접근법 기업가치를 계산",
                "security": [{"bearerAuth": []}],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "상장사 종목코드/기업명"},
                        "inputs": {"type": "object", "description": "직접 입력 재무 (원 단위)",
                                   "properties": {k: ({"type": "string"} if k in _TEXT_FIELDS else
                                                      {"type": "array"} if k == "peers" else
                                                      {"type": "object"} if k == "normalization" else num)
                                                  for k in _FIELDS}},
                        "assumptions": _ASSUMPTION_SCHEMA,
                        "normalize": {"type": "boolean", "default": True,
                                      "description": "사이클 정점일 때 정상화 이익 적용 (ticker 경로)"},
                        "sensitivity": {"oneOf": [{"type": "boolean"}, {"type": "object"}]},
                    },
                    "anyOf": [{"required": ["ticker"]}, {"required": ["inputs"]}],
                }}}},
                "responses": {
                    "200": {"description": "계산 결과 (result, baseline, delta, sensitivity)"},
                    "401": {"description": "API 키 누락/오류"},
                    "404": {"description": "종목 없음"},
                    "422": {"description": "입력 검증 실패"},
                    "429": {"description": "호출 한도 초과"},
                },
            }},
        },
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "x-mcp": {"endpoint": "/mcp", "transport": "streamable-http",
                  "tools": [t["name"] for t in MCP_TOOLS]},
    }
