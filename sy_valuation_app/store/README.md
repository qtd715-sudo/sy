# Play 스토어 등록 이미지 (SY Valuation)

Google Play Console → **스토어 등록정보(기본) → 그래픽** 에 올리는 자산 일체.
모두 24-bit PNG(알파 없음), Play 규격(가로/세로 비 2:1 이내, 휴대전화 최소 320px, 10인치 최소 1080px)을 맞췄다.

| 파일 | 규격 | Play Console 슬롯 |
|---|---|---|
| `icon-512.png` | 512 × 512 | 앱 아이콘 (512×512, ≤1MB) |
| `feature-graphic-1024x500.png` | 1024 × 500 | 그래픽 이미지 (feature graphic) |
| `screenshots/phone/01~06_*.png` | 1080 × 1920 (9:16) | 휴대전화 스크린샷 (2~8장) |
| `screenshots/tablet-7/01~03_*.png` | 1200 × 1920 (5:8) | 7인치 태블릿 스크린샷 |
| `screenshots/tablet-10/01~03_*.png` | 2560 × 1600 (16:10) | 10인치 태블릿 스크린샷 |

## 스크린샷 구성

각 장은 상단 헤드라인(개발 기능 요약) + 실제 앱 화면(디바이스 프레임) 구성.

| # | 휴대전화 | 화면 |
|---|---|---|
| 01 | 시장을 한 화면에 | `#/dashboard` — 지수·환율·원자재·가상자산·시장 뉴스·저평가 Top 5 |
| 02 | SY 평가법으로 적정주가 산출 | `#/sy?q=005930` — 수익·자산·상대가치 3접근법, 기업가치 min/mid/max |
| 03 | 전종목 저평가 스크리너 | `#/sy?tab=screener` — KOSPI·KOSDAQ 전종목, DART 재무 기반 |
| 04 | 9개 모델 적정주가를 한 번에 | `#/multi?q=005930` — DCF·RIM·PER·PBR·PSR·EV/EBITDA·Graham·Lynch |
| 05 | 종합 분석과 투자 판단 | `#/analysis?q=005930` — SY + 다중모델 + 단기/장기 추천 |
| 06 | 토픽별 시장 뉴스 | `#/news` — 토픽 자동 분류 + 감성 분석 |

7인치: dashboard / sy / multi 스크리너(세로). 10인치: dashboard / analysis / news(가로, 사이드바 레이아웃).

## 제작 방법 (재생성)

- 아이콘·그래픽 이미지: `assets/logo.svg` 마크 기반 (배경 `#0a0a0a`, 막대 `#fafaf9`, 적정가치 라인 `#22c55e`).
- 스크린샷: 로컬 서버(`python -m sy_valuation.run`)를 띄우고 헤드리스 Chrome(DevTools Protocol) 으로
  디바이스 메트릭(360×780@3x, 600×960@2x, 1280×800@2x)을 지정해 캡처한 뒤 HTML 템플릿으로 합성.
  스크립트: `tools/make_store_assets.py` (사용법은 파일 상단 docstring).
- 예시 종목은 삼성전자(005930). 시세/뉴스는 캡처 시점(2026-09-10) 기준.

> 이 폴더(`sy_valuation_app/store/**`)의 변경은 Android 빌드 워크플로를 트리거하지 않는다
> (`.github/workflows/android-build.yml` 의 paths 필터에서 제외).
