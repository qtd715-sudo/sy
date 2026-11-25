# 라이브 쇼케이스 기획서 — 가정 시뮬레이터 · API/MCP 콘솔

작성일 2026-11-25 · 상태: 1차 구현 완료(로컬 검증), 운영 미배포

## 1. 목표

증권사 리서치센터장·대기업 M&A 전략기획팀장 앞에서 앱을 시연했을 때 **"이 엔진을 우리 시스템에 바로 붙이고 싶다"** 는 반응을 얻는다. 앱은 최종 상품이 아니라 API 의 살아있는 증명이다.

요청 메시지에서 두 기능의 목록이 누락되어, 현재 구조에서 그 반응을 가장 직접 끌어내는 두 가지를 선정했다. 다른 기능을 의도했다면 §7 후보와 교체할 수 있다.

| | 기능 | 시연에서 증명하는 것 |
|---|---|---|
| ① | **가정 시뮬레이터** (`#/sim`) | 엔진이 조회 API 가 아니라 **계산 API** 다. 우리 가정·우리 재무(비상장 딜 타깃)로 즉시 계산된다 |
| ② | **API · MCP 라이브 콘솔** (모든 화면 우하단) | 화면의 모든 숫자가 **호출 한 번**으로 재현된다. 사내 에이전트에는 설정 4줄로 붙는다 |

## 2. 기능 ① 가정 시뮬레이터

### 사용자 흐름
1. **상장사 모드** — 종목 검색 → 최신 공시(DART TTM) 재무로 기준 평가 로드.
2. **직접 입력 모드** — 매출·영업이익·EBITDA·FCF·자산·부채·순차입금·주식수 입력 → 외부 조회 없이 평가(비상장·딜 타깃).
3. 슬라이더 6개(WACC, 단기 성장률, 영구성장률, 피어 PER, 피어 EV/EBITDA, 청산 할인계수) 조정 → 180ms 디바운스 후 재계산.
4. 결과: 적정가(기준 대비 Δ), 접근법별 가치 범위(풋볼필드), DCF 민감도 표(WACC × 영구성장률 5×5), 11개 산식별 기준↔시나리오 비교, 요청 JSON.
5. 결과 카드에 `결정론적 계산` 배지 + `input_hash` + 엔진 버전 표시.

### API 계약 — `POST /api/v1/valuations/compute`

```jsonc
// 요청: ticker 또는 inputs 중 하나 필수
{
  "ticker": "005930",                      // 상장사: 시장 데이터로 기본 입력 구성
  "inputs": { "revenue": 5e10, "...": 0 }, // 직접 입력: 외부 조회 없는 순수 계산
  "assumptions": { "wacc": 0.10, "growth_rate_short": 0.08 },
  "sensitivity": { "x": "wacc", "y": "terminal_growth", "metric": "income_dcf" }
}
// 응답
{
  "request_id": "req_…", "engine_version": "sy-engine/1.0.0",
  "deterministic": true, "input_hash": "sha256:…",
  "provenance": { "source": "market_data", "financials_basis": "DART 2026 3분기 TTM" },
  "assumptions_applied": { "wacc": 0.10 },
  "result":   { "fair_price_mid": 0, "enterprise_mid": 0, "detail_rows": [], "inputs": {} },
  "baseline": { "fair_price_mid": 0, "wacc": 0.0829 },   // 가정을 바꿨을 때만
  "delta":    { "abs": 0, "pct": 0 },
  "sensitivity": { "x_values": [], "y_values": [], "grid": [[]] }
}
```

- 오류는 `{"error": {"code", "message", …}}` 형식: `missing_input` `unknown_field` `invalid_input` `out_of_range` `unknown_assumption` `invalid_assumption`(WACC ≤ 영구성장률) `not_found` `unauthorized` `rate_limited`.
- 파생 규칙은 기존 빌더와 동일: 단기 성장률만 바꾸면 장기 = 단기×0.5, β·세율·Rf·MRP 를 바꾸면 WACC 재산출.
- 시가총액이 없으면(비상장) 상승률·등급을 계산하지 않고 `rating: "N/A"`.

### 설계 결정
- **슬라이더 재계산은 `inputs` 를 그대로 재전송**한다. 서버가 DART/Naver 를 다시 부르지 않아 12~20ms 에 응답하고, DART 한도를 쓰지 않는다. 동시에 "상태 없는 순수 계산 API" 라는 판매 포인트를 그대로 보여준다.
- 민감도 지표를 `income_dcf` 로 둔 이유: 종합 적정가는 접근법별 중앙값의 평균이라 WACC 변화에 반응하지 않는 경우가 많다(§6).

## 3. 기능 ② API · MCP 라이브 콘솔

- `window.fetch` 를 감싸 앱이 보낸 `/api/*`, `/mcp` 호출을 최근 40건 기록(관리자·헬스체크 제외).
- 호출마다 3개 탭: **REST(curl)** · **MCP tool call**(동등한 JSON-RPC) · **응답 JSON**, 복사 버튼.
- **MCP 연결 테스트** 버튼: 실제 `initialize` → `tools/list` 를 수행해 서버 정보·도구 4종·클라이언트 설정 스니펫을 표시.
- API Key 입력란(브라우저 `localStorage` 보관) — 운영에서 키를 켠 뒤에도 시연 가능.

### MCP 서버 — `POST /mcp`
JSON-RPC 2.0, Streamable HTTP(단일 JSON 응답), 프로토콜 `2025-06-18`(하위 2개 버전 협상).

| 도구 | 용도 |
|---|---|
| `search_company` | 기업명/코드 → ticker 확정 |
| `get_valuation` | 상장사 3접근법 평가(컨텍스트 절약형 요약 응답) |
| `compute_valuation` | 가정 변경·직접 입력 재계산, 민감도 |
| `screen_undervalued` | 전 종목 배치 평가 상위 N |

서버 `instructions` 와 도구 설명에 "수치를 재계산하지 말고 그대로 인용", 단위(원), "투자 권유 아님" 을 명시.

## 4. 구현 내역

| 파일 | 변경 |
|---|---|
| `sy_valuation/b2b_api.py` (신규) | 계산 API, 입력 검증, 민감도, API 키·호출 한도, MCP 핸들러, OpenAPI |
| `sy_valuation/server.py` | `do_POST`·`do_OPTIONS`, `GET /api/v1/openapi.json` |
| `sy_valuation/static/showcase.js` · `showcase.css` (신규) | 콘솔 + 시뮬레이터 |
| `static/index.html` · `app.js` · `sw.js` | 메뉴 06, `#/sim` 라우트, 종합분석의 "가정 바꿔보기" 링크, SW 캐시 v8 |
| `sy_valuation/tests/test_b2b_api.py` (신규) | 9개 테스트(결정론·검증·민감도·MCP) |

환경변수: `SY_API_KEYS`(쉼표 구분, 미설정 시 공개 데모), `SY_RATE_LIMIT_PER_MIN`(기본 300).

검증: 단위 테스트 20건 통과(기존 11 + 신규 9). 로컬 서버에서 상장사(005930)·직접 입력 두 모드, 슬라이더 재계산, MCP 연결 테스트, 콘솔 3개 탭, 모바일 폭(375px)을 브라우저로 확인. **Render 운영 환경·Capacitor 앱(AAB)에서는 미확인.**

## 5. 데모 시나리오 (각 3분)

**A. 리서치센터장** — 종합분석에서 삼성전자 검색 → "가정 바꿔보기" → WACC 를 하우스 뷰로 이동 → 민감도 표 → 콘솔을 열어 "이 화면은 이 호출 하나" → MCP 탭 → "귀사 리서치 어시스턴트는 이 도구를 호출합니다. LLM 은 숫자를 만들지 않습니다."

**B. M&A 전략기획팀장** — 직접 입력 모드에 검토 중인 타깃 재무 입력(저장되지 않음을 안내) → 30초 만에 3접근법 범위 → 피어 멀티플·청산 할인 조정 → "이 입력을 사내 딜 검토 포털이 그대로 보내면 됩니다."

**C. AI/IT 담당** — 콘솔의 MCP 연결 테스트 → 설정 스니펫 복사 → `input_hash` 설명: 같은 해시는 감사 시점에 다시 호출해도 같은 값.

## 6. 시연 전 반드시 고칠 것

1. **삼성전자 DCF 약 5,760조원(시총의 5.6배), 종합 +90% STRONG_BUY.** 시연 첫 화면에서 신뢰를 잃는다. 기본 가정 재보정 전에는 시나리오 A 를 쓰지 말 것(직접 입력 모드 B 가 안전).
   - *2026-11-25 갱신:* 사이클 정상화(`valuation/normalize.py`) 적용 후 DCF 2,293조원(시총의 2.25배), 종합 +68% STRONG_BUY. 절반 이하로 줄었지만 아직 시연에 쓸 수준이 아니다. 남은 원인은 단기 성장률 10%와 소형주 피어 PER 20.9배.
   - *같은 날 2차 갱신:* 성장률 상한(20%→10%), 피어 선정 보정(같은 기준 규모 비교·중앙값·표본 3개 미만 시 섹터 표준), 정점 시 PER·EBITDA 계열에도 정상화 이익 적용 후 **삼성전자 종합 1,062조원(+4%, HOLD)**, SK하이닉스 +7%. 시나리오 A 사용 가능. 단, 피어 멀티플의 원천인 샘플 재무(가격·EPS)가 고정값이라는 한계는 남아 있다.
2. **종합 적정가가 WACC 에 반응하지 않는 경우.** 중앙값 집계의 특성. "왜 안 움직이느냐" 는 질문에 대비하거나, 가중 평균 옵션을 먼저 넣는다.
3. 등급(`STRONG_BUY`) 노출은 B2B 데모에서 끄는 것을 권장(규제 포지션).
4. 운영에 올리면 `/api/v1/*`, `/mcp` 가 공개된다. 배포 전 `SY_API_KEYS` 설정 여부를 결정할 것.

## 7. 다음 후보 (우선순위순)

- **근거 추적 뷰** — 각 숫자를 누르면 산식·중간값·DART 접수번호.
- **피어 비교·딜 멀티플 리포트** — 피어 선정 근거와 분포, PDF/엑셀 내보내기.
- **에이전트 대화 데모** — 앱 안에서 "LLM 단독 답변 vs MCP 연결 답변" 을 나란히.
- **고객 가정 프로파일** — 하우스 WACC·가중치 저장 후 일괄 적용.
