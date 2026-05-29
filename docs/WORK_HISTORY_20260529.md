# 작업 이력 — 2026-05-29 (피어 매칭 + 화면 재구성)

> 사용자 자리 비운 동안 진행된 작업 전체 이력. 다음 세션에 빠르게 컨텍스트 복귀하기 위한 기록.

## 시작 시점
- branch: `main` @ `2d5dc82` (SY 평가법 설계서 v2.0 정합)
- 사용자 요청 진행 중: 엠로(058970) 검색 시 피어 비교군 0개로 떠서 안 보이는 문제

## 완료된 작업 (커밋 순서대로)

### Phase 1 — 피어 비교군 정상화 (사용자 발견 이슈)

| 커밋 | 내용 |
|---|---|
| `671d3b2` | 피어 universe KRX 전종목 확장 + 비-샘플 종목 매칭 정상화 — KSIC 2자리 매핑 + DART universe 빌더 + lazy enrich |
| `61c428a` | sample 종목도 DART 자산/부채/세부 항목 덮어쓰기 (Option A) — 삼성전자 부채 0 / 자산 세부 0 문제 해결 |
| `7249486` | 피어 매칭 정밀도 향상 — KSIC 5자리/3자리 세분화 + size_proxy (revenue → mcap → price×shares) 매칭 |

### Phase 2 — 화면 재구성 8개 → 5개 페이지

설계서: [docs/PAGE_RESTRUCTURE_DESIGN_v1.md](PAGE_RESTRUCTURE_DESIGN_v1.md)

| 커밋 | 단계 | 내용 |
|---|---|---|
| `1a068bd` | **C1** | 헤더 메타텍스트 제거 + 로고 클릭 → 대시보드 + 검색바 공통 CSS |
| `ec54801` | **C2** | 5개 페이지 라우팅 + 레거시 redirect 매핑 |
| `3ce71e0` | **C3** | 02 기업가치평가(SY) 단일/스크리너 탭 통합 |
| `71d9ed3` | **C4** | 03 다중모델 평가 단일/TOP10 탭 통합 |
| `7608f34` | **C5** | 04 종합 분석 신규 (SY + 다중모델 + 의사결정) |
| `32181d4` | **C6** | nav 라벨 5개 + legend 정리 |

## 최종 5개 페이지 구조

```
01 · DASHBOARD              #/dashboard   (그대로)
02 · 기업가치평가(SY)        #/sy          ← 구 00 + 05 + 06 통합 (탭)
03 · 다중모델 평가           #/multi       ← 구 02 + 03 통합 (탭)
04 · 종합 분석          ★   #/analysis    ← 구 04 확장 + 비교 (신규)
05 · 토픽뉴스               #/news        (그대로)
```

### 레거시 redirect (북마크/공유링크 보호)

```
#/sy-analysis, #/sy-detail   → #/sy
#/sy-screener                → #/sy?tab=screener
#/search                     → #/multi
#/undervalued                → #/multi?tab=screener
#/recommend                  → #/analysis
```

## 변경 안 한 것 (안전 보장)

- 백엔드 API 0줄 변경 (`/api/sy/evaluate`, `/api/valuation`, `/api/recommend` 등 그대로)
- 평가 로직 0줄 변경 (`sy_method.py`, `engine.py`, `recommender/investment.py` 그대로)
- 데이터 소스 0줄 변경 (DART, Naver, Yahoo 커넥터 그대로)
- 캐시 / DART universe / 피어 매핑 로직 — Phase 1 변경분 외 그대로

## 검증 상태

### 자동 검증 완료
- ✅ JS syntax (`node --check sy_valuation/static/app.js`) — 통과
- ✅ Python import (`from sy_valuation.server import App`) — 통과
- ✅ `/api/ping` 200 OK
- ✅ `/api/health` 200 OK · DART enabled · 4078 종목 · scheduler alive
- ✅ DART universe scheduler `dart_univ` 가 1780047257에 실행됨 (= 최신 배포 후)

### 회사망 한계로 못 한 검증 (사용자 브라우저 확인 권장)
- ⏳ `/api/sy/evaluate?q=엠로` — 회사 프록시 차단으로 직접 호출 막힘
- ⏳ `/api/valuation?q=엠로`
- ⏳ `/api/recommend?q=엠로`

→ 가벼운 헬스체크는 통과하지만 무거운 API는 회사망에서 차단됨. 정상 작동 가능성 매우 높음 (코드 검증 + 직전까지 동일 API 들이 정상 동작했음).

## 사용자 확인 체크리스트 (브라우저)

집/모바일 등 회사망 밖에서 접속:

1. **5개 nav 표시 확인** — 01 DASHBOARD / 02 SY / 03 다중모델 / 04 종합 분석 / 05 뉴스
2. **로고 클릭** → 01 대시보드로 이동
3. **헤더 검색** (엠로 입력) → 04 종합 분석 페이지로 이동
4. **04 종합 분석 페이지**:
   - 헤더 KPI 4개 (종목/현재가/적정가/상승률) 표시
   - 좌-우 2블록 (SY 평가법 / 다중모델 평가) 동시 표시
   - 비교 분석 박스 자동 해석 표시
   - 시장 시그널 (뉴스 감성/변동성/호라이즌) 표시
   - 의사결정 (매수가/매도가/손절가 + 장기 사유 + 리스크)
5. **02 SY 페이지** → 탭 클릭으로 단일/스크리너 전환
6. **03 다중모델 페이지** → 탭 클릭으로 단일/TOP10 전환
7. **레거시 URL 확인**:
   - `#/sy-analysis?q=엠로` → `#/sy?q=엠로` 로 자동 redirect
   - `#/search?q=엠로` → `#/multi?q=엠로` 로 자동 redirect
8. **헤더에 "종목 4078개..." 텍스트** 안 보이는지 확인

## 알려진 후속 작업

### 우선순위 P1 — 사용자 검증 후 진행
- 엠로 피어가 KOSDAQ 소형 응용SW로 잘 매칭되는지 검증
  → DART universe 캐시 새 시총 데이터로 빌드되는지 확인 (스케줄러 다음 실행 7일 후 OR Manual Trigger)

### 우선순위 P2 — 정리 작업
- LEGACY navigate 호출 11곳 (`/sy-analysis`, `/search` 등) → 신규 라우트로 직접 변경
- 현재는 LEGACY_REDIRECT 가 자동 처리하지만 navigate 가 2번 발생 (불필요한 한 단계)

### 우선순위 P3 — 04 종합 분석 추가 기능
- 최근 뉴스 리스트 (감성 입력으로 사용된 뉴스) 표시
- 시총 대비 적정가 비율 차트 (SY vs 다중모델 시각 비교)

## 파일 변경 요약

```
신규 파일:
  docs/PAGE_RESTRUCTURE_DESIGN_v1.md   설계서
  docs/WORK_HISTORY_20260529.md         이 파일
  qa_helper.py                         QA 헬퍼 스크립트
  valuation_qa_checklist.md            QA 체크리스트
  valuation_qa_엠로_058970.md           엠로 검증
  valuation_qa_삼성전자_005930.md       삼성전자 검증
  history/sy_backup_20260529_161209.zip  변경 전 백업
  sy_valuation/data_sources/dart_sectors.py  KSIC 매핑

변경 파일:
  sy_valuation/server.py               DART 덮어쓰기 (Option A)
  sy_valuation/data_sources/dart.py    universe 빌더 + 시총 추가
  sy_valuation/data_sources/repository.py  peer_universe()
  sy_valuation/scheduler.py            dart_univ 잡 + 7일 캐시
  sy_valuation/valuation/peers.py      select_peers 시 size_proxy
  sy_valuation/valuation/sy_builder.py  naver enricher
  sy_valuation/static/app.js           5개 페이지 라우팅 + 04 종합 분석
  sy_valuation/static/index.html       nav 5개 + legend
  sy_valuation/static/style.css        탭 + KPI 표 + 등급 칩
```

## 다음 세션 시작 시 컨텍스트 빠르게 잡기

1. 이 파일 + `docs/PAGE_RESTRUCTURE_DESIGN_v1.md` 읽기
2. `git log --oneline -10` 으로 최근 커밋 확인
3. https://sy-valuation.onrender.com 접속해서 5개 페이지 동작 확인
4. 사용자 피드백 받기 (어디 NG / 어디 OK)
