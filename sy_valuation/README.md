# SY Valuation — 기업가치평가 시스템

수익가치 + 자산가치 + 상대가치 3접근법 기반의 통합 가치평가 시스템.

## 빠른 시작

```powershell
# 1) 서버 실행 (외부 패키지 불필요, Python 3.10+ 만 있으면 됨)
python sy_valuation\run.py

# 2) 브라우저
http://127.0.0.1:8765/
```

## 기능

| 페이지 | 설명 |
|--------|------|
| **대시보드** | 주요 지수/환율, 원물 시세(WTI·금·구리·곡물), 시장뉴스 + 감성지수, 저평가 Top5 |
| **저평가 Top 10** | 적정주가 대비 저평가 + 정량 필터(ROE·흑자·부채) 통과 종목 랭킹 |
| **종목 가치평가** | 기업명/코드 → 9개 모델 가중평균 적정주가, 모델별 분포, 핵심 재무 |
| **투자 추천** | 가치평가 + 뉴스 감성 + 변동성 → 단기(매수/매도/손절가) / 장기(투자 사유) |

## 가치평가 모델 (9종)

| 모델 | 설명 | 기본 가중치 |
|------|------|------|
| DCF | 잉여현금흐름(FCF) 5년 명시기간 + 영구성장 | 20% |
| RIM (S-RIM) | 잔여이익모형, 한국 가치투자 표준 | 20% |
| PER 멀티플 | 섹터 평균 PER × EPS | 15% |
| PBR 멀티플 | 섹터 평균 PBR × BPS | 10% |
| PSR 멀티플 | 섹터 평균 PSR × 주당매출 | 5% |
| EV/EBITDA | 섹터 평균 × EBITDA - 순부채 | 10% |
| Graham # | √(22.5 × EPS × BPS) | 5% |
| Graham 본질가치 | EPS × (8.5 + 2g) × 4.4/Y | 5% |
| Lynch (PEG=1) | EPS × (성장률 + 배당수익률) | 10% |

가중치는 환경변수 또는 `valuation/engine.py:DEFAULT_WEIGHTS` 에서 조정.
산출 불가 모델(예: 적자 → PER 사용 불가)은 자동으로 가중치 0 처리 후 정규화.

## 데이터 소스

| 소스 | 키 필요 | 환경변수 | 폴백 |
|------|--------|----------|------|
| **샘플 재무** | × | — | `data/sample_financials.json` (기본 동작) |
| **DART** (재무제표) | ○ 무료 | `DART_API_KEY` | 샘플 재무 |
| **Naver 뉴스 API** | ○ 무료 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | Google News RSS (키 불필요) |
| **Yahoo Finance** (시세, 원물) | × | — | 0건 응답 |

### DART API 키 발급 (옵션)

1. <https://opendart.fss.or.kr/> 회원가입 → 인증키 발급
2. PowerShell 에서:

```powershell
$env:DART_API_KEY = "발급받은_40자리_키"
python sy_valuation\run.py
```

### Naver 검색 API 키 (옵션, 더 정확한 한국 뉴스)

1. <https://developers.naver.com/apps/> → 애플리케이션 등록 → 검색 API 사용 설정
2. PowerShell:

```powershell
$env:NAVER_CLIENT_ID = "..."
$env:NAVER_CLIENT_SECRET = "..."
```

## 폴더 구조

```
sy_valuation/
├── run.py                # 진입점
├── server.py             # http.server 기반 API 서버
├── requirements.txt      # 옵션 패키지 (기본 동작은 stdlib 만으로)
├── valuation/            # 가치평가 엔진
│   ├── engine.py         # 오케스트레이터 (9모델 가중평균)
│   ├── dcf.py            # DCF
│   ├── rim.py            # 잔여이익모형
│   ├── multiples.py      # PER/PBR/PSR/EV·EBITDA
│   ├── graham.py         # Graham
│   └── lynch.py          # Lynch PEG
├── data_sources/         # 외부 데이터 커넥터
│   ├── repository.py     # Financials 로더
│   ├── dart.py           # DART OpenAPI
│   ├── news.py           # 뉴스 (Naver API + Google RSS)
│   ├── price.py          # 주가 (Yahoo)
│   └── commodities.py    # 원물 시세 (Yahoo 선물)
├── recommender/          # 추천/스크리닝
│   ├── screener.py       # 저평가 Top N
│   └── investment.py     # 단기/장기 추천 + 매수/매도가
├── data/
│   └── sample_financials.json   # 오프라인 표본 (KOSPI 20종목)
└── static/               # 프론트엔드 (vanilla JS SPA)
    ├── index.html
    ├── style.css
    └── app.js
```

## API

```
GET /api/health                       시스템 상태
GET /api/tickers                      종목 리스트
GET /api/valuation?q=<name|ticker>    가치평가
GET /api/undervalued?n=10             저평가 Top N
GET /api/recommend?q=<name|ticker>    투자 추천
GET /api/news?q=<keyword>&n=10        뉴스 검색
GET /api/market-news?n=10             시장 뉴스 + 감성
GET /api/commodities                  원물/지수
GET /api/price?q=<ticker>             실시간 시세
GET /api/history?q=<ticker>           1년 종가 히스토리
```

## 보완할 점 (TODO 우선순위)

이미 구현했지만 더 강화할 수 있는 항목:

- [ ] **DART corp_code 캐시 자동 갱신** (현재는 최초 1회만)
- [ ] **분기 재무 → 4분기 합산 → TTM 환산** 로직 (현재는 연간 기준)
- [ ] **섹터 멀티플 자동 산출**: KRX 전체 종목 PER/PBR 중앙값 캐시
- [ ] **KRX OpenAPI / pykrx** 연동 (Yahoo 우회 시)
- [ ] **백테스트**: 과거 N년 가치평가 정확도 측정
- [ ] **사용자 가정 조정 UI**: WACC, 성장률, 가중치를 슬라이더로 조정
- [ ] **포트폴리오 추적**: 다종목 상관/리스크 분산
- [ ] **알림**: 적정가 도달 시 `send_mail.py` 활용 메일 알림 (이미 부모 폴더에 있음)
- [ ] **인증/세션**: 사용자별 워치리스트
- [ ] **SQLite 캐시**: DART 호출 일일 한도 보호

## 라이선스 / 주의

- 본 시스템은 **교육 및 자기 분석용**입니다. 투자 결정의 책임은 사용자에게 있습니다.
- 가치평가는 **가정 기반 추정치**이며 실제 가격을 보장하지 않습니다.
- 실시간 데이터는 외부 서비스 의존 — 네트워크/방화벽 환경에 따라 일부 기능 제한.
