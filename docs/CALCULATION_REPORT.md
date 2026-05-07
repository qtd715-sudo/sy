# SY Valuation 계산식 보고서

> **작성일**: 2026-05-07
> **버전**: v0.1 (커밋 `3bfee98` 기준)
> **운영 URL**: https://sy-valuation.onrender.com

본 문서는 SY Valuation 시스템의 **각 화면별 계산 로직**과 **데이터 출처(정적/자동)** 를 정직하게 정리한 보고서입니다.

---

## 📌 데이터 출처 — 솔직히

| 데이터 종류 | 출처 | 자동 갱신? | 비고 |
|---|---|---|---|
| **현재가/시세** | Naver Finance polling API | ✅ 5분 주기 | 한국 6자리 코드 1순위, Yahoo 폴백 |
| **시가총액** | 현재가 × 발행주식수 | ✅ 자동 계산 | |
| **EPS, BPS, PER, PBR** | Naver integration API (m.stock) | ⚠️ 일부 자동 | 비샘플 종목만 자동 |
| **EPS, BPS, ROE, 매출, 영업이익, 순이익** | `sample_financials.json` | ❌ 정적 (수동) | 샘플 55종목만 정확 |
| **EBITDA, FCF, 순부채** | `sample_financials.json` | ❌ 정적 | 매년 재무제표 발표 시 수동 갱신 필요 |
| **자산총계, 부채총계, 순자산** | `sample_financials.json` | ❌ 정적 | 일부 종목만 입력됨 |
| **섹터별 평균 멀티플** | `sample_financials.json` (sectors 항목) | ❌ 정적 | per/pbr/psr/ev_ebitda |
| **피어 그룹** | 자동 (같은 섹터 + 매출 0.3x~3x) | ✅ 자동 | sample 내에서만 매칭 |
| **뉴스** | Bing News RSS | ✅ 1시간 캐시 | |
| **원자재/지수/환율** | Yahoo Finance v8 chart | ✅ 5분 캐시 | |
| **KOSPI/KOSDAQ 전 종목 리스트** | Naver 시가총액 페이지 스크레이핑 | ✅ 24시간 캐시 | 검색용, 재무 X |

### 🚨 중요 한계
- **DCF / 자산가치 / EV-EBITDA 모델은 재무제표 항목 의존** → 현재 정적 데이터 → **내년 조회 시 동일 결과**
- 진짜 자동 갱신을 원하면 **DART OpenAPI 키 발급** 후 환경변수 `DART_API_KEY` 등록 필요 (5분 작업)
- 아니면 Naver 재무제표 페이지 스크레이핑 추가 구현 (현재 미구현)

---

## 1. 📊 대시보드 (`#/dashboard`)

### 표시 내용
1. **시장 종합 12 토픽 뉴스** — 코스피, 코스닥, 미국/유럽/일본/중국 증시, 환율, 금리, 채권, 원유/에너지, 금속/원자재, 농산물
2. **저평가 Top 5** — 저평가 TOP10 의 미리보기

### 계산식
- 뉴스: Bing News RSS 단일 키워드 검색
- 저평가 Top 5: 후술하는 [저평가 TOP10] 로직과 동일, 상위 5개

### 데이터 흐름
```
사용자 페이지 열기
   ↓
GET /api/news/market    → SQLite 캐시 (1시간 TTL)
GET /api/undervalued?n=5 → 캐시된 가격 + 정적 재무로 즉시 평가
```

---

## 2. 💎 저평가 TOP10 (`#/undervalued`)

### 핵심 로직 — 9개 모델 가중평균 적정주가

#### 모델별 계산식

##### a. DCF (잉여현금흐름 할인) — 가중치 20%
```
입력: FCF(현재), 순부채(net_debt), 발행주식수(shares), WACC(9%), g_high(8%), g_terminal(2.5%), N(5년)

PV_explicit = Σ_{t=1..N} [FCF × (1+g_high)^t] / (1+WACC)^t

FCF_terminal = FCF × (1+g_high)^N × (1+g_terminal)
TV = FCF_terminal / (WACC - g_terminal)
PV_TV = TV / (1+WACC)^N

기업가치(EV) = PV_explicit + PV_TV
자기자본가치 = EV - 순부채
주당가치 = 자기자본가치 / 발행주식수
```

##### b. RIM (S-RIM, 잔여이익모형) — 가중치 20%
```
입력: BPS, ROE, cost_of_equity(8.5%), persistence(0.9), horizon(10년)

excess_return = ROE - cost_of_equity
ex_t (1년차) = BPS × excess_return

PV = Σ_{t=1..10} [ex_t / (1+cost_of_equity)^t]
ex_t는 매년 persistence 비율로 감쇠 (ex_{t+1} = ex_t × persistence)

영구가치 (10년차+) = ex_10 × persistence / (1 + cost_of_equity - persistence)
PV += 영구가치 / (1+cost_of_equity)^10

주당가치 = BPS + PV
```
> ROE ≤ 자본비용이면 BPS 그대로 (초과이익 0).

##### c. PER 멀티플 — 가중치 15%
```
주당가치 = EPS × 섹터_평균_PER
```
> EPS ≤ 0 이면 0 (적자기업 PER 사용 불가)

##### d. PBR 멀티플 — 가중치 10%
```
주당가치 = BPS × 섹터_평균_PBR
```

##### e. PSR 멀티플 — 가중치 5%
```
주당가치 = 주당매출(SPS) × 섹터_평균_PSR
```

##### f. EV/EBITDA — 가중치 10%
```
EV = EBITDA × 섹터_평균_EV/EBITDA
주당가치 = (EV - 순부채) / 발행주식수
```

##### g. Graham Number — 가중치 5%
```
주당가치 = √(22.5 × EPS × BPS)
```

##### h. Graham 본질가치 — 가중치 5%
```
주당가치 = EPS × (8.5 + 2g) × 4.4 / Y

g: 성장률 (% 단위, 예: 0.10 → 10)
Y: AAA 회사채 수익률 (4.5% 기본 가정)
```

##### i. Lynch (PEG = 1) — 가중치 10%
```
배당수익률 = 주당배당(DPS) / 현재가
적정 PER = 성장률(%) + 배당수익률(%)
주당가치 = EPS × 적정 PER
```

#### 종합 적정주가
```
산출 가능한 모델만 사용 (값 ≤ 0인 모델 제외)
정규화_가중치 = 가중치 / Σ(살아있는 모델 가중치)

적정주가 = Σ_{모델} 모델별주가 × 정규화_가중치
상승여력  = (적정주가 - 현재가) / 현재가
```

#### 등급
```
≥ +30%: STRONG_BUY
≥ +10%: BUY
≥ -10%: HOLD
<  -10%: SELL
```

#### 정량 필터 (가치 함정 방지)
다음 3개 모두 통과해야 후보:
```
ROE ≥ 5%
당기순이익 > 0
EBITDA > 0 이면 (순부채 / EBITDA) ≤ 4
```

#### 종합 점수 (정렬)
```
ROE_정규화      = clamp(ROE / 0.30, 0, 1)        ← 0~30% → 0~1
PBR_디스카운트  = 1 - (현재PBR / 섹터PBR), clamp -1~1
점수 = 0.6 × 상승여력 + 0.2 × ROE_정규화 + 0.2 × PBR_디스카운트
```

→ 점수 내림차순 정렬, 상위 N개 반환.

### 데이터 출처
- **EPS, BPS, ROE, FCF, EBITDA, 매출** : 정적 (sample_financials.json)
- **현재가** : Naver realtime (5분 캐시)
- **섹터 평균 멀티플** : 정적 (sectors 항목, 12 섹터 정의)

---

## 3. 🔍 기업 가치 평가 (`#/search`)

### 표시 내용
- 종목 1개 검색 → 9개 모델 결과 + 가중평균 적정주가
- 모델별 분포 막대 그래프
- 핵심 재무 (EPS, BPS, ROE, PER, PBR, EBITDA, FCF, 순부채)

### 계산식
[저평가 TOP10] 의 9-model 가중평균 로직과 동일.

### 데이터 처리
1. 샘플(`sample_financials.json`)에 있으면 → 정적 재무 + Naver 실시간 가격
2. 비샘플 한국 종목 → Naver Fundamentals (`m.stock.naver.com/api/stock/{code}/integration`) 에서 EPS/BPS/PER/PBR 자동 fetch
3. 미국/ETF → Yahoo Finance v10 quoteSummary
4. 둘 다 실패 → 종목 못 찾음 + 유사 종목 추천

### 비샘플 종목의 한계
Naver integration API 에서 가져오는 항목 (`058970` 엠로 등):
- ✅ EPS, BPS, PER, PBR, 시총
- ❌ EBITDA, FCF, 순부채, 자산총계, 부채총계 → DCF, EV/EBITDA 모델 작동 X
- → 9개 모델 중 PER/PBR/Graham/Lynch 4개만 사용 가능 (가중치 자동 정규화)

---

## 4. 🧭 투자 분석 (`#/recommend`)

### 입력
- 가치평가 결과 (위 9-model)
- 뉴스 감성 점수 (-1.0 ~ +1.0)
- 1년 일별 가격 (변동성 산출용)

### 호라이즌 결정
```
long_attractive  = (상승여력 ≥ 20%) AND (ROE ≥ 8%)
short_attractive = (상승여력 ≥ 5%) AND (news_sentiment ≥ 0.10)

장기+단기 (BUY, 신뢰도 0.85) : 둘 다 만족
장기만   (BUY, 신뢰도 0.75) : long만
단기만   (BUY, 신뢰도 0.55) : short만
단기 SELL (신뢰도 0.60)     : 상승여력 ≤ -10%
관망 HOLD (신뢰도 0.40)     : 그 외
```

### 단기 가격대
```
buy_zone   = min(현재가, 적정주가) × 0.95
sell_zone  = 적정주가 × 1.02
stop_loss  = buy_zone × 0.92
```

### 변동성 (연환산)
```
일간_수익률 = (P_t - P_{t-1}) / P_{t-1}    ← 1년치 일별 종가
σ = pstdev(일간_수익률)
연환산_변동성(%) = σ × √252 × 100
```

### 장기 투자 사유 (자동 생성)
다음 조건 만족 시 사유 추가:
```
상승여력 ≥ 20% → "적정주가 X원 대비 상승여력 Y%"
ROE > 자본비용 → "ROE X% > CoE Y% — 가치 창출 진행 중"
PBR < 섹터PBR  → "자산가치 디스카운트"
PER < 섹터PER  → "이익 멀티플 디스카운트"
FCF > 0 + 순이익 > 0 → "FCF 흑자 — 본질적 현금창출력"
성장률 ≥ 10% → "EPS 성장 모멘텀"
```

### 리스크 자동 추출
```
ROE < 5%               → "낮은 ROE"
순이익 ≤ 0             → "적자"
순부채/EBITDA > 3       → "부채부담"
변동성 > 40%            → "단기 트레이딩 리스크"
news_sentiment ≤ -0.20 → "뉴스 흐름 부정적"
적정가/현재가 > 3       → "적정가 추정 과대 — 가정 민감도 검토"
```

### 뉴스 감성 점수
```
사전 키워드 매칭:
positive = ["상승","급등","호조","최대","흑자","성장","돌파","수혜","상향"]
negative = ["하락","급락","부진","적자","감소","리스크","충격","하향","둔화","악화"]

뉴스 10건의 title+description 에서 카운트
score = (pos - neg) / (pos + neg)   ∈ [-1, +1]
```

---

## 5. ⭐ SY 평가법 저평가 (`#/sy-screener`)

### 핵심 로직 — 3접근법 종합

#### 접근법 ① 수익가치 (Income Approach)

##### a-1. DCF (FCFF 10년 + 영구가치)
```
입력: FCF, WACC(섹터별 표준), g_단기(2.5%), g_장기(2.5%), g_영구(0.5%)

1~5년차:  FCFF_t = FCFF × Π(1+g_단기) ^ t
6~10년차: FCFF_t = FCFF_5 × Π(1+g_장기) ^ (t-5)
PV_t     = FCFF_t / (1+WACC)^t

영구가치 = FCFF_10 × (1+g_영구) / (WACC - g_영구)
PV_영구  = 영구가치 / (1+WACC)^10

기업가치_DCF = Σ PV_t + PV_영구
```

##### a-2. EBITDA × 동종 EV/EBITDA 멀티플
```
기업가치 = EBITDA × 피어_평균_EV/EBITDA
```

##### a-3. 영업이익 × 10배 (간이 추정)
```
기업가치 = 영업이익 × 10
```

→ **수익가치 min / mid(중앙값) / max** = min/median/max(a-1, a-2, a-3)

#### 접근법 ② 자산가치 (Asset Approach)
```
순자산가치 = 자산총계 - 부채총계 (= 자본총계)
청산가치   = 순자산 × 0.7 (보수계수)
```
> 입력: total_equity (있으면 그대로), 없으면 BPS × 발행주식수로 추정

#### 접근법 ③ 상대가치 (Market Approach)
```
PER 모델     = 피어_평균_PER × 당기순이익
PBR 모델     = 피어_평균_PBR × 순자산
PSR 모델     = 피어_평균_PSR × 매출
EV/EBITDA    = (피어_평균_EV/EBITDA × EBITDA) - 순부채

상대가치 min/mid/max = min/median/max(위 4개)
```

#### 자동 피어 그룹 선정
```
1) 같은 섹터 (반도체, IT서비스, 자동차 등 12 섹터)
2) 매출 0.3x ~ 3x 범위 (비슷한 규모) 안의 기업
3) 매출 거리 가까운 순 정렬
4) 최대 8개 선정 (최소 3개)
5) 각 피어의 PER/PBR/PSR/EV-EBITDA 계산 (개별)
6) 이상치 제외 후 평균
   - PER 0~100, PBR 0~20, PSR 0~20, EV/EBITDA 0~50
```

#### 종합 기업가치 (3접근법 묶음)
```
enterprise_min = min(수익_min, 자산_book, 상대_min)
enterprise_mid = median(수익_mid, 자산_book, 상대_mid)
enterprise_max = max(수익_max, 자산_book, 상대_max)
```

#### ⭐ 주당 적정가 (사용자 요청 핵심)
```
주당 적정가 (mid) = enterprise_mid / 발행주식수
주당 적정가 (min) = enterprise_min / 발행주식수
주당 적정가 (max) = enterprise_max / 발행주식수

주당 상승여력 = (주당 적정가_mid - 현재가) / 현재가
```

#### 시총 대비 등급 (mid 기준)
```
upside_mid = (enterprise_mid - 시총) / 시총

≥ +200%: STRONG_BUY
≥  +50%: BUY
≥  +10%: ACCUMULATE
≥  -10%: HOLD
<  -10%: SELL
```
> Top10 임계점(+30%/+10%)보다 보수적 — 자산/멀티플 비중이 높아 격차가 크게 나타나기 때문

#### 제외 종목
- **KT (030200)** : 통신사 자산-부채 구조로 모델 노이즈 큼

### 데이터 출처
- 모든 재무 항목: 정적 (sample_financials.json) — 55종목만 정확
- 현재가/시총: Naver realtime (5분 캐시)
- 비샘플 종목: Naver integration API 로 부분 빌드 (자산/부채/EBITDA 부재 → 자산가치/일부 수익가치 계산 불가)

---

## 6. 📋 SY 평가법 가치평가 (`#/sy-detail`)

### 표시 내용
- KPI 4개: 종목, 현재가+시총, **주당 적정가 mid (큰 글씨)**, 주당 상승여력+등급
- **계산 카드**: 종합 기업가치 ÷ 발행주식수 = 주당 적정가 (KTDS 시트 형태)
- 3접근법 결과 표 (수익/자산/상대 + 종합 행)
- 모델별 산출 내역 (9개 행 각각)
- 입력값 요약 (매출/영업이익/EBITDA/자산/부채/WACC/성장률 등)
- 피어 비교군 표 (자동 선정된 3~8개 피어)

### 계산식
[SY 평가법 저평가] 와 동일 (단일 종목 상세 표시).

---

## 7. 📰 토픽 뉴스 (`#/news`)

### 22 토픽 (요청 순서)
```
[상위 — 정책/금융]
1. 금융           "금융 은행 보험"
2. 부동산         "부동산"
3. 정부정책       "정부정책"
4. 경제정책       "경제정책"
5. 청년정책       "청년정책"
6. 주택정책       "주택정책"
7. 청약           "주택 청약"

[산업/테마 — 반도체부터]
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

[하위]
18. 가상자산      "비트코인"
19. 서울청년정책  "서울 청년수당"
20. 세제          "세제개편"
21. 노동/일자리   "일자리"
22. 복지          "복지정책"
```

### 데이터 흐름
```
키워드 → Bing News RSS (https://www.bing.com/news/search?q=KEYWORD&format=rss&setLang=ko)
   ↓
XML 파싱 → NewsItem (title, link, description, published, source)
   ↓
SQLite 캐시 (1시간 TTL, 키 = "news:topic:토픽명")
   ↓
화면 노출
```

### 갱신 주기
- 백그라운드 스케줄러: 1시간마다 force_refresh
- 매일 03:00 KST: GitHub Actions cron 이 강제 prefetch
- 사용자 요청: 캐시 우선 (즉시 응답)

### Bing News RSS 한계
- "OR" 구문 미지원 → 단일 키워드만 사용
- 결과 5~10건/토픽 (한국 중심 정렬)
- 감성 점수: 한국어 키워드 매칭 (positive/negative)

---

## 📈 자동 갱신 인프라

### 백그라운드 스케줄러 (서버 내부)
```
매 5분  : 원자재/지수/환율 (Yahoo) + 모든 샘플 종목 가격 (Naver)
매 1시간: 22 토픽 뉴스 + 12 시장 뉴스 (Bing)
매 24시간: KOSPI/KOSDAQ 전 종목 리스트 (Naver 시가총액 페이지 스크레이핑)
```

### GitHub Actions cron
```
매 14분    : /api/health 핑 (Render free tier sleep 방지)
매일 03:00 KST: /api/prefetch 호출 (전체 데이터 강제 갱신)
```

### Render 자동 재배포
- main 브랜치 push 시 자동 빌드 + 재배포 (3분 이내)

---

## ⚠️ 현재 시스템 한계 (정직)

### 1. 재무제표 정적 데이터
- 매년 자동 갱신 ❌
- DART API 키 또는 Naver 재무제표 스크레이핑 추가 구현 필요
- 현 상태: 55개 샘플 종목만 정확, 그 외 비샘플은 PER/PBR/Graham/Lynch 4개 모델만 작동

### 2. 비샘플 종목의 SY 평가법
- Naver integration API 에서 EBITDA/FCF/자산/부채 미제공
- → DCF, 자산가치, EV-EBITDA 모델 작동 안 함
- → 상대가치 (PER/PBR) 만으로 평가 → 결과 신뢰도 ↓

### 3. 피어 그룹 — 샘플 내에서만 매칭
- 자동 피어는 sample_financials.json 의 55종목 안에서만 선정
- 같은 섹터 종목이 1~3개밖에 없을 수 있음 (예: 반도체는 삼성전자/SK하이닉스 2개)
- → 더 정확한 비교를 위해서는 사용자 정의 피어 또는 KRX 전체 평균 데이터 필요

### 4. 뉴스 감성 점수
- 단순 키워드 매칭 (사전 19개 단어)
- 문맥/뉘앙스 감지 안 됨
- → 본격적으로 쓰려면 한국어 NLP 모델 (KoBERT 등) 필요

### 5. 변동성 - 비샘플 종목
- Yahoo Finance 1년 일별 종가 사용
- 한국 비샘플 종목은 Yahoo 미커버 시 변동성 0%

### 6. SY 평가법 임계점
- 등급 임계점 (+200%/+50%) 은 KTDS 사례 기반 보수적 설정
- 종목/섹터별로 적정 임계점이 다를 수 있음

---

## 🔧 개선 로드맵 (우선순위)

| 우선 | 작업 | 기대 효과 |
|---|---|---|
| 1 | DART API 키 등록 → 분기 재무제표 자동 갱신 | 매분기 EBITDA/FCF/자산/부채 fresh |
| 2 | Naver 재무제표 페이지 스크레이핑 추가 (DART 폴백) | 키 없이도 자동 갱신 |
| 3 | KRX 전체 종목 PER/PBR 통계 캐시 → 섹터별 진짜 평균 | 멀티플 정확도 ↑ |
| 4 | 사용자 정의 피어 그룹 UI | 더 정밀한 상대가치 |
| 5 | 한국어 뉴스 감성 NLP 모델 | 단기 매수/매도 시그널 정확도 ↑ |
| 6 | 백테스트 도구 (과거 N년 가치평가 정확도 측정) | 가중치 튜닝 근거 |
| 7 | DART 공시 알림 + 메일 발송 (`send_mail.py` 활용) | 매수 타이밍 자동 알림 |

---

## 📚 코드 위치 매핑

| 화면 | 백엔드 핸들러 | 핵심 로직 |
|---|---|---|
| 대시보드 | [server.py:market_topics, undervalued](sy_valuation/server.py) | [recommender/screener.py](sy_valuation/recommender/screener.py) |
| 저평가 TOP10 | `App.undervalued()` | [recommender/screener.py:find_undervalued](sy_valuation/recommender/screener.py) |
| 기업 가치 평가 | `App.valuation()` | [valuation/engine.py:value_company](sy_valuation/valuation/engine.py) |
| 투자 분석 | `App.recommend()` | [recommender/investment.py:recommend_investment](sy_valuation/recommender/investment.py) |
| SY 평가법 | `App.sy_undervalued()` | [valuation/sy_method.py:evaluate_sy](sy_valuation/valuation/sy_method.py) |
| SY 가치평가 | `App.sy_evaluate()` | [valuation/sy_method.py](sy_valuation/valuation/sy_method.py) + [valuation/peers.py](sy_valuation/valuation/peers.py) |
| 토픽 뉴스 | `App.news_topics()` | [data_sources/news.py:NewsConnector](sy_valuation/data_sources/news.py) |

각 파일은 한국어 docstring + 인라인 주석 포함.

---

## 📞 문의/기여
- 저장소: https://github.com/qtd715-sudo/sy
- 이메일: qtd715@gmail.com (저장소 소유자)
- 메일 발송 도구: [send_mail.py](send_mail.py)

---

*본 문서는 시스템의 현 상태를 정직하게 기록한 것입니다. 미구현 항목/한계점도 모두 명시했습니다. 투자 의사결정의 책임은 사용자에게 있습니다.*
