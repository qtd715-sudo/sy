# SY Valuation 계산식 + 기술 보고서

> **작성일**: 2026-05-08 (UI 리디자인 + 일일 cron + 삼프로TV 폴백 추가)
> **버전**: v0.1 (커밋 `5da7b72` 기준)
> **운영 URL**: https://sy-valuation.onrender.com
> **저장소**: https://github.com/qtd715-sudo/sy

본 문서는 SY Valuation 시스템의 **기술 스택**, **각 화면별 계산 로직**, **데이터 출처(정적/자동)** 를 정직하게 정리한 보고서입니다.

## 🆕 최근 변경 (2026-05-08)

| 변경 | 상세 |
|---|---|
| **UI 리디자인** | Warm minimal monochrome (#fafaf9 + #0a0a0a). Inter + JetBrains Mono + Noto Sans KR. 잡지 스타일 KPI / 1px 헤어라인 / 번호 라벨 메뉴 (`01·DASHBOARD`) |
| **페이지 헤드 날짜** | 모든 페이지 meta-strip 에 KST 오늘 날짜 + 현재 시각 자동 표시 |
| **뉴스 시각 KST** | RSS pubDate (GMT) → `05.08 01:37 KST` 변환 |
| **일일 자동 갱신 시간 분리** | KST 06:00 시장 데이터 / KST 09:00 뉴스 (GitHub Actions cron 2개) |
| **`/api/prefetch?type=`** | `market` / `news` / `all` 분기 처리 |
| **삼프로TV 다중 폴백** | RSS → Invidious public API → 채널 페이지 HTML 스크레이핑 |
| **삼프로TV 최신 영상 요약** | YouTube watch 페이지의 `shortDescription` 추출 → 800자 요약 카드 (페이지 상단) |
| **DART 통합** | `DART_API_KEY` 등록 시 정식 재무제표 자동 사용 (1순위, Naver 폴백) |
| **0/null 데이터 → "-" 표시** | 화면 전체 일관 처리 (해외 비샘플 종목 대응) |

---

## 📑 목차

1. [기술 스택 (언어/라이브러리/호스팅)](#-기술-스택)
2. [프로젝트 통계](#-프로젝트-통계)
3. [아키텍처 다이어그램](#-아키텍처)
4. [데이터 출처 — 솔직히](#-데이터-출처--솔직히)
5. [화면별 계산식](#-화면별-계산식)
   - [1. 대시보드](#1--대시보드)
   - [2. 저평가 TOP10](#2--저평가-top10)
   - [3. 기업 가치 평가](#3--기업-가치-평가)
   - [4. 투자 분석](#4--투자-분석)
   - [5. SY 평가법 저평가](#5--sy-평가법-저평가)
   - [6. SY 평가법 가치평가](#6--sy-평가법-가치평가)
   - [7. 삼프로TV](#7--삼프로tv)
   - [8. 토픽 뉴스](#8--토픽-뉴스)
6. [자동 갱신 인프라](#-자동-갱신-인프라)
7. [환경변수 (옵션 키)](#-환경변수-옵션-키)
8. [현재 한계](#%EF%B8%8F-현재-한계)
9. [개선 로드맵](#-개선-로드맵)
10. [코드 위치 매핑](#-코드-위치-매핑)

---

## 🛠 기술 스택

### 언어
| 언어 | 용도 | 비중 |
|---|---|---|
| **Python 3.10+** | 백엔드 서버, 가치평가 엔진, 데이터 커넥터, 스케줄러 | ~70% (3,500 라인) |
| **JavaScript (Vanilla)** | 프론트엔드 SPA, 라우팅, 자동완성 | ~20% (1,000 라인) |
| **HTML / CSS** | 화면 마크업, 다크 테마, 반응형 (모바일/PC) | ~5% |
| **YAML / TOML / Bash / Batch** | 배포·인프라 설정 (Render/Fly.io/cron/install) | ~5% |

### Python — 표준 라이브러리만 사용 ✨
**외부 패키지 0개** (의존성 없음, 즉시 실행 가능).

| 모듈 | 용도 |
|---|---|
| `http.server`, `socketserver` | HTTP 서버 (ThreadingHTTPServer) |
| `urllib.request`, `urllib.parse` | HTTP 요청 / URL 파싱 |
| `subprocess` | curl 폴백 (urllib 가 SSL renegotiation 못 처리할 때) |
| `json`, `xml.etree.ElementTree` | JSON / RSS XML 파싱 |
| `sqlite3` | 영속 캐시 (data/cache.db) |
| `threading`, `concurrent.futures` | 병렬 fetch (뉴스 토픽, 가격) |
| `dataclasses` | 도메인 모델 (Financials, ValuationResult, NewsItem 등) |
| `pathlib` | 파일 경로 |
| `re` | 정규식 (Naver HTML 파싱, 키워드 추출) |
| `statistics` | 변동성 계산 (pstdev) |
| `datetime` | 타임스탬프 |
| `math` | √, 로그 등 (Graham 모델) |
| `mimetypes` | 정적 파일 Content-Type |
| `os`, `ssl` | 환경변수, TLS 설정 |
| `zipfile`, `io` | DART corp_codes ZIP 압축해제 |
| `argparse` | CLI 인자 파싱 |
| `logging` | 스케줄러 로그 |

### 프론트엔드 — Vanilla JS (프레임워크 X)
- **빌드 도구 없음** (webpack/vite/babel X)
- **외부 JS 라이브러리 0개**
- 해시 라우팅 (`#/dashboard` 등) 으로 SPA 동작
- `fetch()` API 로 백엔드 호출
- `Intl.NumberFormat` 으로 한국어 통화 포맷
- CSS 변수 (`--bg`, `--accent` 등) 로 다크 테마

### 데이터 / 외부 API
| 출처 | 인증 | 용도 |
|---|---|---|
| **Naver Finance polling API** | 키 불필요 | 한국 종목 실시간 가격 (장중 7초 주기) |
| **Naver Finance integration API** | 키 불필요 | 한국 종목 PER/PBR/EPS/BPS/시총 |
| **Naver Finance annual/quarter API** | 키 불필요 | 연간/분기 재무제표 (16개 지표) |
| **Naver 시가총액 페이지** | 키 불필요 | KOSPI/KOSDAQ 전 종목 리스트 (스크레이핑) |
| **Yahoo Finance v8 chart** | 키 불필요 | 글로벌 시세, 1년 종가 (변동성용), 원자재 |
| **Yahoo Finance v10 quoteSummary** | 키 불필요 | 미국 주식 재무 요약 |
| **Bing News RSS** | 키 불필요 | 한국어 뉴스 검색 (Google News 차단 시 폴백) |
| **YouTube RSS feed** | 키 불필요 | 삼프로TV 등 채널 영상 목록 |
| **DART OpenAPI** | 키 필요 (무료) | 정식 재무제표, 공시 (옵션) |
| **Naver 검색 API** | 키 필요 (무료) | 정확한 한국 뉴스 (옵션) |

### 호스팅 / 배포
| 인프라 | 용도 | 비용 |
|---|---|---|
| **Render.com** (free tier) | Python 서버 호스팅 (sy-valuation.onrender.com) | $0 |
| **GitHub Pages** | 정적 포트폴리오 (qtd715-sudo.github.io/sy) | $0 |
| **GitHub Actions** | keep-alive cron (매 14분) + 일일 prefetch (매일 03:00 KST) | $0 |
| **GitHub Repo** | 코드 저장소 (qtd715-sudo/sy) | $0 |

옵션 (현재 미사용):
- **Fly.io** — Always-on 무료 티어 (Dockerfile + fly.toml 준비됨)
- **Cloudflare Tunnel** — 본인 PC 임시 공개 URL (cloudflared.exe 다운로드됨)

### 인프라 설정 파일
| 파일 | 역할 |
|---|---|
| [render.yaml](render.yaml) | Render Blueprint (1-click 배포) |
| [Dockerfile](Dockerfile) | 컨테이너 이미지 (Python 3.11 slim + curl) |
| [fly.toml](fly.toml) | Fly.io 배포 설정 (도쿄 리전, 영속 볼륨) |
| [Procfile](Procfile) | Heroku-style 실행 명령 |
| [.github/workflows/keepalive.yml](.github/workflows/keepalive.yml) | GitHub Actions cron (매 14분 ping + 매일 03:00 prefetch) |
| [sy_valuation/install_task.bat](sy_valuation/install_task.bat) | Windows 작업스케줄러 등록 (PC 부팅 시 자동 시작) |
| [sy_valuation/run.bat](sy_valuation/run.bat) | Windows 실행 헬퍼 |
| [sy_valuation/tunnel.bat](sy_valuation/tunnel.bat) | cloudflared/ngrok 자동 터널 |

---

## 📊 프로젝트 통계

```
파일 36개 (.py + .html + .css + .js + .json + .md)
코드 약 5,010 라인 (.py + .html + .css + .js)

Python 모듈 22개:
   ├─ valuation/        (8 파일) — 9개 가치평가 모델 + SY 평가법 + 자동 피어
   ├─ data_sources/     (10 파일) — 외부 데이터 커넥터 + 캐시 + HTTP util
   ├─ recommender/      (3 파일) — 저평가 스크리너 + 투자 분석
   ├─ scheduler.py      — 백그라운드 prefetch
   ├─ server.py         — HTTP API 라우터
   └─ run.py            — CLI 진입점

프론트엔드:
   ├─ static/index.html (60 라인)
   ├─ static/style.css  (270 라인) — 반응형 (≤900px / ≤600px)
   └─ static/app.js     (920 라인) — 7+1 페이지 SPA

데이터:
   ├─ data/sample_financials.json (55 종목 정밀 데이터)
   └─ data/tickers.json (240+ 종목 경량 검색용)

문서:
   ├─ README.md (루트, 배포 안내)
   ├─ sy_valuation/README.md (기능 안내)
   └─ docs/CALCULATION_REPORT.md (이 문서)
```

---

## 🏗 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                  사용자 브라우저 (PC/핸드폰/해외)                  │
│                  https://sy-valuation.onrender.com               │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│           Render.com (Singapore region, Python 3.11)             │
│                                                                   │
│  ┌─────────────┐   ┌──────────────────────────────────────────┐ │
│  │  Frontend   │   │           HTTP Server (server.py)        │ │
│  │  Vanilla JS │◄──┤  /api/health, /api/search, /api/...     │ │
│  │  SPA        │   │  GET 라우팅 + JSON 응답                  │ │
│  └─────────────┘   └─────────────────────┬────────────────────┘ │
│                                           │                       │
│  ┌──────────────────────────────────────┐ │                       │
│  │     Background Scheduler (Thread)    │ │                       │
│  │  • news prefetch (1h)                │ │                       │
│  │  • commodity quotes (5min)           │ │                       │
│  │  • ticker prices (5min)              │ │                       │
│  │  • KRX universe (24h)                │ │                       │
│  │  • DART corp_codes (7d, key 있을때)  │ │                       │
│  └──────────────────┬───────────────────┘ │                       │
│                     │                      │                       │
│         ┌───────────▼───────────┐         │                       │
│         │  SQLite Cache (WAL)   │◄────────┘                       │
│         │  data/cache.db        │                                  │
│         │  - news:topic:*        │                                  │
│         │  - price:ticker        │                                  │
│         │  - market:groups       │                                  │
│         │  - krx:universe        │                                  │
│         │  - youtube:channelId   │                                  │
│         │  - naver_fin:code:*    │                                  │
│         └───────────────────────┘                                  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              Valuation Engine (가치평가 핵심)                │ │
│  │                                                                │ │
│  │  ┌─────────────────┐    ┌──────────────────────────┐        │ │
│  │  │  9 Models       │    │  SY Method (3 Approaches)│        │ │
│  │  │  • DCF          │    │  • Income (DCF/EBITDA/OP)│        │ │
│  │  │  • RIM (S-RIM)  │    │  • Asset (book/liq)      │        │ │
│  │  │  • PER/PBR/PSR  │    │  • Market (PER/PBR/PSR/  │        │ │
│  │  │  • EV/EBITDA    │    │           EV-EBITDA)     │        │ │
│  │  │  • Graham # / 본질│   │  → min/mid/max 기업가치 │        │ │
│  │  │  • Lynch (PEG=1)│    │  → 주당 적정가 = ÷ 주식수│        │ │
│  │  └─────────────────┘    └──────────────────────────┘        │ │
│  │                                                                │ │
│  │  자동 피어 (peers.py): 같은 섹터 + 매출 0.3x~3x              │ │
│  │  스크리너 (screener.py): 정량필터 + 종합점수 정렬             │ │
│  │  추천 (investment.py): 호라이즌/가격대/사유/리스크            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                External Data Connectors                       │ │
│  │  HTTP util (urllib + curl 폴백) — SSL renegotiation 우회     │ │
│  │   ├─ NaverPrice (실시간 시세)                                 │ │
│  │   ├─ NaverFundamentals (PER/PBR/EPS/BPS)                     │ │
│  │   ├─ NaverFinancials (연간/분기 재무제표)                    │ │
│  │   ├─ DartConnector (정식 재무제표, 키 필요)                  │ │
│  │   ├─ LiveFinancials (Yahoo)                                  │ │
│  │   ├─ CommodityConnector (Yahoo, 원자재/지수/환율)            │ │
│  │   ├─ NewsConnector (Naver API → Bing News RSS → Google)     │ │
│  │   ├─ YoutubeChannel (RSS feed, 삼프로TV 등)                  │ │
│  │   └─ KrxUniverse (Naver 시가총액 스크레이핑)                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS (outbound)
                           ▼
        ┌──────────────────────────────────────────┐
        │  External Services                       │
        │  • Naver Finance (polling, integration)  │
        │  • Yahoo Finance v8/v10                  │
        │  • Bing News RSS                         │
        │  • YouTube RSS feed                      │
        │  • DART OpenAPI (옵션, 키 필요)          │
        └──────────────────────────────────────────┘

           ┌──────────────────────────────────────────┐
           │  GitHub Actions (cron, 외부)             │
           │  • 매 14분: keep-alive ping (sleep 방지) │
           │  • 매일 03:00 KST: 강제 prefetch         │
           └──────────────────────────────────────────┘
```

---

## 📌 데이터 출처 — 솔직히

### 핵심: 종목별 평가 동작 흐름

```
사용자 검색
   ↓
1) 샘플 (sample_financials.json, 55종목) — 가장 빠르고 정확
2) DART_API_KEY 있으면 → DART 정식 재무제표 (모든 KOSPI/KOSDAQ)
3) Naver 연간 재무제표 API (모든 한국 6자리 코드)
4) Naver 기본 정보 API (PER/PBR/EPS/BPS)
5) Yahoo Finance quoteSummary (해외 종목)
6) Yahoo chart meta (마지막 폴백, 가격/시총만)
   ↓
계산 가능한 모델만 작동, 부족한 항목은 "-" 표시
```

### 데이터 항목별 출처

| 데이터 종류 | 출처 | 자동 갱신? | 커버리지 |
|---|---|---|---|
| **현재가/시세** | Naver Finance polling | ✅ 5분 주기 | 한국 전 종목 + Yahoo (글로벌) |
| **시가총액** | 현재가 × 발행주식수 | ✅ 자동 계산 | 전체 |
| **EPS, BPS, PER, PBR** | Naver integration API | ✅ 자동 | 모든 한국 종목 |
| **매출, 영업이익, 순이익, ROE, 부채비율, 당좌비율, 유보율, 배당** | Naver finance/annual API (16지표) | ✅ 자동 | 모든 한국 6자리 코드 |
| **EBITDA** | DART: 영업이익+감가상각 (정확) / Naver: 영업이익×1.3 (추정) | ✅ DART 정확 / ⚠ Naver 추정 | DART 키 등록 시 모든 종목 정확 |
| **FCF** | DART: OCF-CAPEX (정확) / Naver: 순이익×0.85 (추정) | ✅ DART 정확 / ⚠ Naver 추정 | DART 키 등록 시 모든 종목 정확 |
| **자산총계, 부채총계, 순자산, 순부채** | DART (정확) | ✅ DART 키 있을 때 | 모든 KOSPI/KOSDAQ |
| **샘플 보강 데이터 (55종목)** | `sample_financials.json` (수동 큐레이션) | ❌ 정적 | 한국 블루칩 55종목 |
| **섹터별 평균 멀티플 (12 섹터)** | `sample_financials.json` (sectors) | ❌ 정적 | 12 섹터 |
| **피어 그룹** | 자동 (같은 섹터 + 매출 0.3x~3x) | ✅ 자동 | sample 55종목 풀에서 매칭 |
| **글로벌 종목 재무 (US/ETF)** | Yahoo Finance v10 quoteSummary | ⚠ Render IP 일부 차단 | quoteSummary 막힐 때 chart meta 폴백 (가격만) |
| **뉴스 (29 토픽)** | Bing News RSS (한국어) | ✅ 1시간 캐시 + 매일 KST 09:00 강제 갱신 | OR 미지원 → 단일 키워드 |
| **삼프로TV 영상** | RSS → Invidious API → 채널 페이지 HTML (3단 폴백) | ✅ 30분 캐시 | YouTube 측 RSS 차단 시 자동 우회 |
| **원자재/지수/환율** | Yahoo Finance v8 chart | ✅ 5분 캐시 + 매일 KST 06:00 강제 갱신 | 64종 (지수 13/환율 8/채권 4/원자재 15/가상자산 7) |
| **KOSPI/KOSDAQ 전 종목 리스트** | Naver 시가총액 페이지 스크레이핑 | ✅ 24시간 캐시 | 약 4,089종목 |
| **DART corp_codes 매핑** | DART OpenAPI (키 필요) | ✅ 7일 갱신 | 모든 등록 법인 |

### "55종목만 정확" 의 진짜 의미 (오해 정정)

**잘못된 이해**: 55종목 외에는 평가 불가
**정확한 이해**:
- 샘플 55종목은 자산/부채까지 **수동으로 큐레이션** → 모든 9개 모델 + SY 평가법 100% 정밀 작동
- **나머지 한국 4,000+ 종목**: Naver 연간 재무제표 API 로 16개 지표 자동 fetch → DCF/RIM/PER/PBR/PSR/Lynch 등 대부분 모델 자동 작동. EBITDA/FCF 는 추정값 사용
- **DART_API_KEY 등록 시**: 모든 KOSPI/KOSDAQ 의 EBITDA/FCF/자산/부채까지 정식 데이터 → SY 평가법까지 정확히 작동
- **해외 종목 (AAPL 등)**: Yahoo quoteSummary 작동 시 모든 모델 작동. Render IP 에서 일부 차단되면 chart meta 폴백 → 가격/시총만 표시, 다른 항목은 "-"

→ **계산 가능한 부분까지 보여주고, 부족한 항목은 "-"** (사용자 요청대로 일관 적용)

---

## 📺 화면별 계산식

### 1. 📊 대시보드

**경로**: `#/dashboard`

#### 표시 내용
1. 시장 종합 12 토픽 뉴스 — 코스피, 코스닥, 미국/유럽/일본/중국 증시, 환율, 금리, 채권, 원유/에너지, 금속/원자재, 농산물
2. 저평가 Top 5 (저평가 TOP10 의 미리보기)

#### 계산식 / 데이터 흐름
```
GET /api/news/market    → SQLite 캐시 (1시간 TTL) → Bing News RSS
GET /api/undervalued?n=5 → 캐시된 가격 + 정적 재무 → 9-model 가중평균 → 정렬
```

---

### 2. 💎 저평가 TOP10

**경로**: `#/undervalued`

#### 9개 모델 가중평균 적정주가

##### a. DCF (잉여현금흐름 할인) — 가중치 20%
```
입력: FCF, 순부채, 발행주식수, WACC(9%), g_high(8%), g_terminal(2.5%), N(5년)

PV_explicit = Σ_{t=1..N} [FCF × (1+g_high)^t] / (1+WACC)^t
FCF_terminal = FCF × (1+g_high)^N × (1+g_terminal)
TV = FCF_terminal / (WACC - g_terminal)
PV_TV = TV / (1+WACC)^N
EV = PV_explicit + PV_TV
주당가치 = (EV - 순부채) / 발행주식수
```

##### b. RIM (S-RIM) — 가중치 20%
```
ex_t = BPS × (ROE - cost_of_equity), persistence 0.9 로 매년 감쇠
PV = Σ ex_t / (1+CoE)^t  (10년) + 영구가치
주당가치 = BPS + PV
```

##### c. PER 멀티플 — 15%
```
주당가치 = EPS × 섹터_평균_PER
```

##### d. PBR 멀티플 — 10%
```
주당가치 = BPS × 섹터_평균_PBR
```

##### e. PSR 멀티플 — 5%
```
주당가치 = SPS × 섹터_평균_PSR
```

##### f. EV/EBITDA — 10%
```
주당가치 = (EBITDA × 섹터_평균 - 순부채) / 발행주식수
```

##### g. Graham Number — 5%
```
주당가치 = √(22.5 × EPS × BPS)
```

##### h. Graham 본질가치 — 5%
```
주당가치 = EPS × (8.5 + 2g) × 4.4 / Y    (Y=AAA 4.5%)
```

##### i. Lynch (PEG=1) — 10%
```
배당수익률 = DPS / 현재가
주당가치 = EPS × (성장률% + 배당수익률%)
```

#### 종합
```
산출 가능한 모델만 사용 → 가중치 정규화
적정주가 = Σ (모델별주가 × 정규화가중치)
상승여력 = (적정주가 - 현재가) / 현재가
```

#### 등급
```
≥ +30%: STRONG_BUY    ≥ +10%: BUY    ≥ -10%: HOLD    < -10%: SELL
```

#### 정량 필터
```
ROE ≥ 5%
당기순이익 > 0
EBITDA > 0 이면 (순부채 / EBITDA) ≤ 4
```

#### 종합 점수 (정렬)
```
점수 = 0.6 × 상승여력
     + 0.2 × clamp(ROE/0.30, 0, 1)
     + 0.2 × (1 - 현재PBR/섹터PBR)
```

---

### 3. 🔍 기업 가치 평가

**경로**: `#/search`

#### 표시 내용
- 자동완성 검색 (한국 4,000+ 종목 + 미국 + ETF)
- 9개 모델 결과 + 가중평균 적정주가
- 모델별 분포 막대 그래프
- 핵심 재무 지표

#### 데이터 처리 우선순위
```
1) 샘플 (sample_financials.json) — 55종목, 가장 정확
2) DART (DART_API_KEY 있을 때) — 정식 재무제표
3) Naver 연간 재무제표 API — 16개 지표
4) Naver integration API — PER/PBR/EPS/BPS
5) Yahoo Finance — 글로벌 종목
6) → 모두 실패 시 "종목 못찾음" + 유사 종목 추천
```

---

### 4. 🧭 투자 분석

**경로**: `#/recommend`

#### 호라이즌 결정
```
long_attractive  = (상승여력 ≥ 20%) AND (ROE ≥ 8%)
short_attractive = (상승여력 ≥ 5%) AND (news_sentiment ≥ 0.10)

장기+단기 (BUY, 신뢰도 0.85): 둘 다 만족
장기      (BUY, 신뢰도 0.75): long만
단기      (BUY, 신뢰도 0.55): short만
단기 SELL (신뢰도 0.60): 상승여력 ≤ -10%
관망 HOLD (신뢰도 0.40): 그 외
```

#### 단기 가격대
```
buy_zone   = min(현재가, 적정가) × 0.95
sell_zone  = 적정가 × 1.02
stop_loss  = buy_zone × 0.92
```

#### 변동성 (연환산)
```
일간_수익률 = (P_t - P_{t-1}) / P_{t-1}
σ = pstdev(일간_수익률)
연환산_변동성(%) = σ × √252 × 100
```

#### 뉴스 감성 점수
```
키워드 매칭 (positive 9개, negative 10개 사전)
score = (pos - neg) / (pos + neg) ∈ [-1, +1]
```

---

### 5. ⭐ SY 평가법 저평가

**경로**: `#/sy-screener`

#### 3접근법

**① 수익가치** (3 모델)
```
DCF (FCFF 10년 + 영구):
  1~5년: g_단기 (2.5%), 6~10년: g_장기, 영구: g_영구 (0.5%)
  PV = Σ FCFF_t / (1+WACC)^t + 영구가치 / (1+WACC)^10
  WACC: 섹터별 표준 (반도체 8.5%, IT 9%, 자동차 9.5%, 은행 7.5%, 통신 7%)

EBITDA × 동종 EV/EBITDA 멀티플
영업이익 × 10배 (간이)

→ 수익가치 min / mid / max
```

**② 자산가치**
```
순자산 = 자산총계 - 부채총계
청산가치 = 순자산 × 0.7
```

**③ 상대가치** (4 모델, 자동 피어 평균 사용)
```
PER 모델     = 피어_평균_PER × 당기순이익
PBR 모델     = 피어_평균_PBR × 순자산
PSR 모델     = 피어_평균_PSR × 매출
EV/EBITDA   = (피어_평균 × EBITDA) - 순부채
→ 상대가치 min / mid / max
```

#### 자동 피어 그룹
```
1) 같은 섹터 (12 섹터)
2) 매출 0.3x ~ 3x 범위
3) 매출 거리 가까운 순, 최대 8개
4) 이상치 제외 후 평균 (PER 0~100, PBR 0~20, PSR 0~20, EV/EBITDA 0~50)
```

#### 종합 기업가치
```
enterprise_min = min(수익_min, 자산_book, 상대_min)
enterprise_mid = median(수익_mid, 자산_book, 상대_mid)
enterprise_max = max(수익_max, 자산_book, 상대_max)
```

#### ⭐ 주당 적정가 (사용자 요청 핵심)
```
주당 적정가 (mid) = enterprise_mid / 발행주식수
주당 상승여력 = (주당 적정가_mid - 현재가) / 현재가
```

#### 등급 (mid upside)
```
≥ +200%: STRONG_BUY
≥  +50%: BUY
≥  +10%: ACCUMULATE
≥  -10%: HOLD
<  -10%: SELL
```

#### 제외
- KT (030200): 통신사 자산-부채 구조로 모델 노이즈

---

### 6. 📋 SY 평가법 가치평가

**경로**: `#/sy-detail`

#### 표시 내용
- KPI 4개: 종목, 현재가+시총, **주당 적정가 mid**, 주당 상승여력+등급
- 계산 카드: 종합 기업가치 ÷ 발행주식수 = 주당 적정가
- 3접근법 결과 표
- 모델별 9개 산출 내역
- 입력값 요약 (매출/EBITDA/자산/부채/WACC/성장률)
- 자동 피어 비교군 표

#### 계산식
[SY 평가법 저평가] 와 동일.

---

### 7. 🎬 삼프로TV

**경로**: `#/sampro`

#### 표시 내용
1. **★ 최신 영상 요약 카드** (페이지 상단) — 가장 최근 영상의 풀 description 800자 + 큰 썸네일
2. 삼프로TV YouTube 채널 최신 20개 영상 (전체 시간순 / 토픽별 토글)
3. 영상별: 썸네일 + 제목 + 토픽 라벨 + 발행 시각

#### 데이터 흐름 (3단 폴백)
```
1) RSS feed: https://www.youtube.com/feeds/videos.xml?channel_id=UCxxx
   ↓ (404/empty 시)
2) Invidious public API: /api/v1/channels/{id}/videos
   - 5개 인스턴스 순회 (invidious.fdn.fr / yewtu.be / ...)
   ↓ (모두 실패 시)
3) YouTube channel 페이지 HTML 의 ytInitialData JSON 정규식 추출
   ↓
SQLite 캐시 (30분 TTL, 빈 결과는 캐시 안 함)
   ↓
토픽 자동 분류 (제목 키워드 매칭) → 화면 노출
```

#### 최신 영상 요약 (NEW)
```
GET /api/youtube/latest
   ↓
1) 최신 영상 1개 가져오기
2) https://www.youtube.com/watch?v={id} HTML fetch
3) ytInitialData 의 "shortDescription" 정규식 추출 (RSS description 보다 풍부)
4) JSON 이스케이프 풀고 첫 800자 → 페이지 상단 카드에 표시
5) 24시간 캐시
```

#### 토픽 자동 분류 (8 카테고리)
```
주식/시황   : 코스피, 코스닥, 주식, 증시, 지수, 상한가, 하한가, 급등, 급락
거시/경제   : FOMC, 금리, 기준금리, 인플레, GDP, 한은, 연준
채권/외환   : 국채, 환율, 달러, 원화, 엔화, 위안화
부동산      : 부동산, 아파트, 분양, 청약, 전세, 매매가
글로벌      : 미국, 중국, 일본, 유럽, 글로벌, 원자재, 원유
기업분석    : 기업분석, 실적, 어닝, 실적발표, 재무
기술/AI     : AI, 반도체, 테크, 엔비디아, TSMC
정치        : 대통령, 정부, 정책, 국회, 선거
기타        : 위 키워드 미매칭
```

#### 요약
- 영상 description 첫 200자 (RSS feed 에서 받은 그대로)
- 자막 기반 본문 요약은 미구현 (YouTube Data API + LLM 필요)

#### 다중 채널 지원
```
환경변수 YT_CHANNELS = "이름1:UCxxx,이름2:UCyyy" 로 채널 추가 가능
환경변수 SAMPRO_CHANNEL_ID 로 기본 채널 변경 가능
```

---

### 8. 📰 토픽 뉴스

**경로**: `#/news`

#### 22 토픽 (요청 순서)

```
[정책/금융 — 상위 7]
1. 금융           "금융 은행 보험"
2. 부동산         "부동산"
3. 정부정책       "정부정책"
4. 경제정책       "경제정책"
5. 청년정책       "청년정책"
6. 주택정책       "주택정책"
7. 청약           "주택 청약"

[산업/테마 — 8~17]
8.  반도체        "반도체"
9.  2차전지       "2차전지"
10. AI            "인공지능"
11. 바이오        "바이오 신약"
12. 자동차        "전기차"
13. 조선/방산     "K-방산"
14. 엔터/콘텐츠   "K팝"
15. ETF           "ETF"
16. 글로벌        "글로벌 경제"
17. IT            "IT 소프트웨어"

[하위 18~22]
18. 가상자산      "비트코인"
19. 서울청년정책  "서울 청년수당"
20. 세제          "세제개편"
21. 노동/일자리   "일자리"
22. 복지          "복지정책"
```

#### 데이터 흐름
```
키워드 → Bing News RSS → XML 파싱 → NewsItem
   ↓
SQLite 캐시 (1시간 TTL)
   ↓
화면 노출
```

---

## ⏰ 자동 갱신 인프라

### 백그라운드 스케줄러 (서버 내부, 별도 thread)
```
매 5분  : 원자재/지수/환율 (Yahoo) + 모든 샘플 종목 가격 (Naver) — 스크리너 즉시 응답용
매 1시간: 22 토픽 뉴스 + 12 시장 뉴스 (Bing News RSS)
매 24시간: KOSPI/KOSDAQ 전 종목 리스트 (Naver 시가총액 스크레이핑)
매 7일  : DART corp_code 매핑 (DART_API_KEY 있을 때만)
```

부팅 시 모든 잡을 병렬로 실행 (서로 독립 thread).

### GitHub Actions cron (외부, UTC 기준)
```
매 14분        : /api/health 핑 (Render free tier sleep 방지)
매일 KST 06:00 : /api/prefetch?type=market — 시세/원자재/지수 강제 갱신
매일 KST 09:00 : /api/prefetch?type=news   — 뉴스 강제 갱신
수동 트리거    : workflow_dispatch (mode=all|market|news|ping 선택)
```

cron UTC 변환:
- KST 06:00 → UTC 21:00 (전날) → cron `0 21 * * *`
- KST 09:00 → UTC 00:00 (당일) → cron `0 0 * * *`

### Render 자동 재배포
- main 브랜치 push 시 자동 빌드 + 재배포 (3분)

---

## 🔑 환경변수 (옵션 키)

모두 옵션. 등록 시 자동화 효과 ↑.

| 변수명 | 발급처 | 효과 | 등록 위치 |
|---|---|---|---|
| `DART_API_KEY` | https://opendart.fss.or.kr/ (무료) | KOSPI/KOSDAQ 정식 재무제표 자동 갱신 | Render Environment |
| `NAVER_CLIENT_ID` + `NAVER_CLIENT_SECRET` | https://developers.naver.com/apps/ (무료) | 정확한 한국 뉴스 (Bing 폴백 대신) | Render Environment |
| `SAMPRO_CHANNEL_ID` | YouTube 채널 ID | 기본 삼프로TV 채널 변경 | Render Environment |
| `YT_CHANNELS` | `이름1:UCxxx,이름2:UCyyy` | 추가 YouTube 채널 (다중) | Render Environment |
| `SY_DISABLE_SCHEDULER` | `1` | 백그라운드 prefetch 비활성화 (디버깅) | Render Environment |
| `PORT` | 자동 (Render 가 주입) | HTTP 포트 | 자동 |

### Render 등록 단계
1. https://dashboard.render.com → **sy-valuation** 서비스
2. 좌측 메뉴 **Environment**
3. **+ Add Environment Variable** → Key/Value 입력 → Save
4. 1~2분 후 자동 재배포

---

## ⚠️ 현재 한계

### 1. DART 키 미등록 시 EBITDA/FCF 추정
- Naver 재무제표 API 는 EBITDA/FCF 직접 제공 X
- 현재 추정: EBITDA = 영업이익 × 1.3, FCF = 순이익 × 0.85
- **DART 키 등록 시 정확한 값으로 자동 교체** (영업이익 + 감가상각, OCF - CAPEX)

### 2. 비샘플 종목의 SY 평가법
- 샘플 55종목 외 종목은 자산/부채 데이터 부족
- → DCF, 자산가치 모델 작동 제한
- DART 키 등록 시 모든 종목 자동 보강

### 3. 피어 그룹 — 샘플 내 매칭
- 자동 피어는 sample_financials.json 의 55종목 내에서만 선정
- 같은 섹터가 1~3개일 수 있음 (예: 반도체 = 삼성전자/SK하이닉스 2개)
- → KRX 전체 평균 통계 캐시로 보완 가능 (개선 로드맵 #3)

### 4. 뉴스 감성 — 단순 키워드
- 사전 19개 단어 매칭 (positive 9개, negative 10개)
- 문맥/뉘앙스 감지 X
- → 한국어 NLP 모델 (KoBERT 등) 필요 (개선 로드맵 #5)

### 5. 변동성 — 비샘플 종목
- Yahoo Finance 1년 일별 종가 사용
- 한국 비샘플 종목 Yahoo 미커버 시 변동성 0%

### 6. 삼프로TV 영상 요약
- 현재: description 첫 200자
- 본문/자막 기반 요약은 미구현 (YouTube Data API + LLM 비용)

### 7. 등급 임계점 고정
- 종목/섹터별 적정 임계점이 다를 수 있음
- 현재는 일괄 적용

---

## 🔧 개선 로드맵 (우선순위)

| 우선 | 작업 | 기대 효과 | 상태 |
|---|---|---|---|
| 1 | DART API 키 등록 → 분기 재무제표 자동 갱신 | 매분기 EBITDA/FCF/자산/부채 fresh | ⏸ 키 발급 + Render 등록 대기 (코드는 완료) |
| 2 | Naver 재무제표 페이지 스크레이핑 (DART 폴백) | 키 없이도 자동 갱신 | ✅ 완료 (NaverFinancials) |
| 3 | KRX 전체 종목 PER/PBR 통계 캐시 | 멀티플 정확도 ↑ | 미착수 |
| 4 | 사용자 정의 피어 그룹 UI | 더 정밀한 상대가치 | 미착수 |
| 5 | 한국어 뉴스 감성 NLP 모델 (KoBERT) | 단기 시그널 정확도 ↑ | 미착수 |
| 6 | 백테스트 도구 (과거 N년 정확도 측정) | 가중치 튜닝 근거 | 미착수 |
| 7 | DART 공시 알림 + 메일 발송 (`send_mail.py`) | 매수 타이밍 자동 알림 | 미착수 |
| 8 | 삼프로TV 자막 기반 진짜 요약 (LLM) | 영상 요약 품질 ↑ | 미착수 |

---

## 📚 코드 위치 매핑

### 화면별
| 화면 | 핸들러 | 핵심 로직 |
|---|---|---|
| 대시보드 | [server.py:market_topics, undervalued](sy_valuation/server.py) | [recommender/screener.py](sy_valuation/recommender/screener.py) |
| 저평가 TOP10 | `App.undervalued()` | [recommender/screener.py](sy_valuation/recommender/screener.py) |
| 기업 가치 평가 | `App.valuation()` | [valuation/engine.py](sy_valuation/valuation/engine.py) |
| 투자 분석 | `App.recommend()` | [recommender/investment.py](sy_valuation/recommender/investment.py) |
| SY 평가법 | `App.sy_undervalued()` | [valuation/sy_method.py](sy_valuation/valuation/sy_method.py) |
| SY 가치평가 | `App.sy_evaluate()` | [valuation/sy_method.py](sy_valuation/valuation/sy_method.py) + [valuation/peers.py](sy_valuation/valuation/peers.py) |
| 삼프로TV | `App.youtube_videos()` | [data_sources/youtube.py](sy_valuation/data_sources/youtube.py) |
| 토픽 뉴스 | `App.news_topics()` | [data_sources/news.py](sy_valuation/data_sources/news.py) |

### 데이터 커넥터
| 커넥터 | 파일 | 역할 |
|---|---|---|
| Repository | [data_sources/repository.py](sy_valuation/data_sources/repository.py) | 샘플/티커 DB 통합 + 우선순위 폴백 |
| 가격 (실시간) | [data_sources/price.py](sy_valuation/data_sources/price.py) | Naver polling + Yahoo |
| Naver 기본 | [data_sources/naver_fundamentals.py](sy_valuation/data_sources/naver_fundamentals.py) | PER/PBR/EPS/BPS |
| Naver 재무제표 | [data_sources/naver_financials.py](sy_valuation/data_sources/naver_financials.py) | 연간/분기 재무 16지표 |
| DART | [data_sources/dart.py](sy_valuation/data_sources/dart.py) | 정식 재무제표 (옵션, 키 필요) |
| 글로벌 (Yahoo) | [data_sources/live.py](sy_valuation/data_sources/live.py) | 미국/ETF |
| 원자재/지수 | [data_sources/commodities.py](sy_valuation/data_sources/commodities.py) | 5개 그룹 64종 |
| 뉴스 | [data_sources/news.py](sy_valuation/data_sources/news.py) | Naver API → Bing → Google |
| YouTube | [data_sources/youtube.py](sy_valuation/data_sources/youtube.py) | RSS feed 파서 |
| KRX 전종목 | [data_sources/krx_universe.py](sy_valuation/data_sources/krx_universe.py) | Naver 시가총액 스크레이핑 |
| HTTP util | [data_sources/http_util.py](sy_valuation/data_sources/http_util.py) | urllib + curl 폴백 |
| Cache | [data_sources/cache.py](sy_valuation/data_sources/cache.py) | SQLite WAL |

### 가치평가 엔진
| 모듈 | 파일 | 역할 |
|---|---|---|
| 9-model 통합 | [valuation/engine.py](sy_valuation/valuation/engine.py) | 가중평균 + 등급 |
| DCF | [valuation/dcf.py](sy_valuation/valuation/dcf.py) | FCFF 5년 + 영구가치 |
| RIM | [valuation/rim.py](sy_valuation/valuation/rim.py) | S-RIM 잔여이익 |
| Multiples | [valuation/multiples.py](sy_valuation/valuation/multiples.py) | PER/PBR/PSR/EV-EBITDA |
| Graham | [valuation/graham.py](sy_valuation/valuation/graham.py) | √(22.5×EPS×BPS), 본질가치 |
| Lynch | [valuation/lynch.py](sy_valuation/valuation/lynch.py) | PEG=1 |
| SY 평가법 | [valuation/sy_method.py](sy_valuation/valuation/sy_method.py) | 3접근법 min/mid/max |
| SY 빌더 | [valuation/sy_builder.py](sy_valuation/valuation/sy_builder.py) | raw → SyInputs |
| 자동 피어 | [valuation/peers.py](sy_valuation/valuation/peers.py) | 같은 섹터 + 매출 비슷 |

### 인프라
| 모듈 | 파일 | 역할 |
|---|---|---|
| HTTP 서버 | [server.py](sy_valuation/server.py) | 라우팅 + 정적파일 |
| 진입점 | [run.py](sy_valuation/run.py) | CLI |
| 스케줄러 | [scheduler.py](sy_valuation/scheduler.py) | 백그라운드 prefetch |

### 프론트엔드
| 파일 | 라인 | 역할 |
|---|---|---|
| [static/index.html](sy_valuation/static/index.html) | 60 | 마크업, 네비 |
| [static/style.css](sy_valuation/static/style.css) | 270 | 다크 테마 + 반응형 |
| [static/app.js](sy_valuation/static/app.js) | 920 | SPA 라우팅 + 8개 페이지 |

---

## 📞 문의/기여
- 저장소: https://github.com/qtd715-sudo/sy
- 이메일: qtd715@gmail.com (저장소 소유자)
- 메일 발송 도구: [send_mail.py](send_mail.py)

---

*본 문서는 시스템의 현 상태를 정직하게 기록한 것입니다. 미구현 항목/한계점도 모두 명시했습니다. 투자 의사결정의 책임은 사용자에게 있습니다.*
