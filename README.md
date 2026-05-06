# SY — 기업가치 평가 시스템

KTDS 24.07 기업가치 평가 시트 방법론을 웹 시스템으로 확장.

## 핵심 기능

- **다중 모델 가치평가**: DCF / RIM / PER · PBR · PSR · EV-EBITDA / Graham / Lynch (9개 모델 가중평균 적정주가)
- **SY 평가법** (KTDS 사례 기반): 수익가치 + 자산가치 + 상대가치 3접근법으로 기업가치 min/mid/max 산출
- **저평가 종목 스크리너**: 정량 필터(ROE·흑자·부채) + 가치 갭 점수
- **투자 추천**: 단기(매수/매도/손절가) · 장기(투자 사유 정량 근거)
- **시장 데이터**: 주요 지수 / 환율 / 채권금리 / 원자재 / 가상자산 (Yahoo Finance)
- **뉴스**: 13개 토픽 자동 분류 + 감성 분석 (Naver/Google News)
- **종목 커버리지**: 한국 KOSPI/KOSDAQ 130+, 미국 주식 60+, ETF 50+
- **자동완성 검색** + 실시간 가격 갱신 + DART/Yahoo 실시간 재무 fetch

## 어디서든 접속하기 (핸드폰/외부) — 클라우드 배포

> **권장**: Render.com (무료, 5분 셋업) + GitHub Actions cron (배치 자동 실행)
> 결과: `https://sy-valuation.onrender.com` 같은 고정 URL 로 어디서든 접속.

### 방법 ① Render.com (가장 쉬움, 추천 ⭐)

1. <https://render.com> 가입 (GitHub 계정으로 로그인)
2. Dashboard → **New +** → **Blueprint**
3. 저장소 선택 → `qtd715-sudo/sy` → **Apply**
4. 자동으로 [render.yaml](render.yaml) 읽어 배포 (3분)
5. 발급된 URL 복사 (예: `https://sy-valuation.onrender.com`)

**배치 매일 자동 실행** (서버 sleep 방지):
1. GitHub 저장소 → Settings → Secrets and variables → Actions → **Variables** 탭
2. **New repository variable** → Name: `SY_URL`, Value: 위에서 복사한 URL
3. 끝. [.github/workflows/keepalive.yml](.github/workflows/keepalive.yml) 이 매 14분 ping + 매일 03:00 KST 강제 prefetch

### 방법 ② Fly.io (always-on 무료, 카드 필요)

```powershell
# flyctl 설치: https://fly.io/docs/flyctl/install/
flyctl auth login
flyctl launch --copy-config --no-deploy
flyctl volumes create sy_data --region nrt --size 1
flyctl deploy
# → https://sy-valuation.fly.dev
```

설정: [fly.toml](fly.toml). 도쿄 리전 (한국과 가까움), 영속 볼륨 1GB.

### 방법 ③ 본인 PC + Cloudflare Tunnel (PC 켜둘 때만 동작)

```powershell
python sy_valuation\run.py
# 다른 터미널에서:
sy_valuation\tunnel.bat   # cloudflared/ngrok 자동
```

### 방법 ④ 로컬만 사용

```powershell
python sy_valuation\run.py
```

서버 실행 시 콘솔에 표시되는 URL:

| 접속 범위 | URL 예시 |
|---|---|
| 본인 PC | http://127.0.0.1:8765/ |
| 같은 Wi-Fi (LAN) | http://**172.10.53.92**:8765/ |

---

## 자동 데이터 갱신 (배치)

**클라우드 배포** 시:
- 서버 안 백그라운드 스케줄러 + GitHub Actions cron 이중 안전망
- 뉴스 1시간 / 원자재 5분 / 핫티커 30분 / 매일 03:00 강제 전체 prefetch
- SQLite (`data/cache.db`) 또는 Fly volume 에 영속 저장

**로컬 PC** 시:
- 동일 백그라운드 스케줄러 동작 (서버 켜져 있는 동안)
- 부팅 시 자동 시작: `sy_valuation\install_task.bat`

---

표준 라이브러리만으로 동작 (Python 3.10+). 외부 패키지 불필요.
상세 문서: [sy_valuation/README.md](sy_valuation/README.md)

## 페이지 구성

| 경로 | 내용 |
|------|------|
| `#/dashboard`     | 시장 개요 (지수/환율/채권/원자재/가상자산) + 시장뉴스 + 저평가 Top5 |
| `#/undervalued`   | 9개 모델 가중평균 적정주가 기준 저평가 Top 10 |
| `#/search`        | 종목 가치평가 (모델별 분포 + 핵심재무) |
| `#/recommend`     | 투자 추천 (단기 매수·매도·손절 / 장기 투자사유) |
| `#/sy-screener`   | **SY 평가법** 저평가 종목 (KTDS 사례 방식) |
| `#/sy-detail`     | **SY 평가법** 상세 분석 (3접근법 표) |
| `#/news`          | 토픽별 시장 뉴스 (코스피·미장·환율·반도체·2차전지·AI 등) |


## 부속 도구: 이메일 발송

`send_mail.py` 로 ssarang615@naver.com / qtd715@gmail.com 에게 메일 발송.

```bash
# Gmail 사용 시 (앱 비밀번호 필요)
export MAIL_PROVIDER=gmail
export MAIL_SENDER=qtd715@gmail.com
export MAIL_PASSWORD=xxxxxxxxxxxxxxxx   # Google 앱 비밀번호 16자리
python send_mail.py "제목" "본문"

# Naver 사용 시 (네이버 메일 SMTP 사용 설정 + 2단계 인증 비밀번호)
export MAIL_PROVIDER=naver
export MAIL_SENDER=ssarang615@naver.com
export MAIL_PASSWORD=네이버_SMTP_비밀번호
python send_mail.py "제목" "본문"
```

## GitHub 연결

```bash
git remote -v   # origin → https://github.com/qtd715-sudo/sy.git
git add .
git commit -m "메시지"
git push -u origin main
```
