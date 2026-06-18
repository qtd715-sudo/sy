# SY Valuation — 모바일 앱 (Capacitor)

기존 `sy_valuation` 웹앱(Render 운영)을 **iOS / Android 네이티브 앱**으로 감싸는
Capacitor 프로젝트입니다. 별도의 프론트엔드를 새로 만들지 않고, 운영 중인 라이브
서버(`https://sy-valuation.onrender.com`)를 그대로 WebView 로 로드합니다.

```
sy_valuation_app/
├─ package.json            # Capacitor 의존성 + 스크립트
├─ capacitor.config.json   # 앱 설정 (appId, server.url, 스플래시 등)
├─ www/                    # 로컬 폴백 셸 (오프라인/콜드스타트 시 노출)
│   └─ index.html
├─ assets/                 # 아이콘·스플래시 소스 (SVG)
│   ├─ logo.svg            # 앱 아이콘 (1024)
│   └─ splash.svg          # 스플래시 (2732)
├─ android/                # `cap add android` 로 생성 (git 미포함)
└─ ios/                    # `cap add ios` 로 생성 (git 미포함, macOS 필요)
```

## 동작 방식

- `capacitor.config.json` 의 `server.url` 이 라이브 서버를 가리킵니다.
  앱을 켜면 WebView 가 곧장 운영 사이트를 로드 → 웹과 100% 동일한 화면·기능
  (다중모델 평가 / SY 평가법 / 뉴스 / 원자재 등), 코드 중복·드리프트 없음.
- 서버가 잠들어 있거나(무료 플랜 15분 후 sleep → 첫 요청 ~30초) 오프라인일 때만
  `www/index.html` 폴백 셸이 보이고, `api/ping` 으로 기상 여부를 확인한 뒤
  자동으로 본 앱으로 진입합니다. "다시 시도" 버튼도 제공.

> **번들 모드로 바꾸려면**: 정적 프론트엔드를 앱에 내장하고 API만 원격 호출하는
> 방식도 가능합니다. `capacitor.config.json` 에서 `server.url` 을 제거하고
> `sy_valuation/static/*` 을 `www/` 로 복사한 뒤, 프론트의 `fetch("/api/...")` 가
> 절대경로(Render)로 가도록 API origin 을 주입해야 합니다. 현재 기본값(live)이
> 데이터 최신성·유지보수 면에서 가장 단순합니다.

---

## 사전 준비

| 대상 | 필요한 것 |
|------|-----------|
| 공통 | [Node.js](https://nodejs.org) LTS (18+), npm |
| Android | [Android Studio](https://developer.android.com/studio) (SDK + 에뮬레이터 또는 실기기 USB 디버깅) |
| iOS | macOS + [Xcode](https://developer.apple.com/xcode/) + CocoaPods (`sudo gem install cocoapods`) |

> Windows 에서는 **Android 빌드만** 가능합니다. iOS 는 macOS + Xcode 필수.

---

## 빌드 & 실행

```bash
cd sy_valuation_app

# 1) 의존성 설치
npm install

# 2) 아이콘 / 스플래시 생성  (assets/*.svg → 각 플랫폼 리소스)
npm run assets

# 3) 네이티브 플랫폼 추가  (한 번만)
npx cap add android      # Android
npx cap add ios          # iOS (macOS only)

# 4) 웹 자산 + 설정 동기화
npx cap sync

# 5) IDE 로 열어서 실기기/에뮬레이터에 실행
npx cap open android     # Android Studio 가 열림 → ▶ Run
npx cap open ios         # Xcode 가 열림 → ▶ Run
```

`npm run assets` 가 SVG 소스를 거부하면(환경에 따라), `assets/logo.svg` 를
1024×1024 PNG(`assets/logo.png`)로, `assets/splash.svg` 를 2732×2732
PNG(`assets/splash.png`)로 내보낸 뒤 다시 실행하세요. (아이콘은 빌드 필수 요소가
아니므로 건너뛰어도 앱은 동작합니다 — 기본 Capacitor 아이콘 사용.)

---

## 배포용 빌드

### Android (APK / AAB)
Android Studio → **Build → Generate Signed Bundle / APK**
- 내부 테스트/사이드로드: APK
- Play 스토어 업로드: AAB (`.aab`)
- 키스토어가 없으면 마법사에서 새로 생성

CLI 로:
```bash
cd android
./gradlew assembleRelease     # APK  → android/app/build/outputs/apk/release/
./gradlew bundleRelease       # AAB  → android/app/build/outputs/bundle/release/
```

### iOS (App Store / TestFlight)
Xcode → **Product → Archive** → Organizer 에서 App Store Connect 업로드.
(Apple Developer 계정 + 서명 프로비저닝 필요)

---

## 서버 URL / 앱 식별자 변경

`capacitor.config.json`:
- `server.url` 과 `server.allowNavigation` — 다른 서버(예: 자체 도메인, fly.io 백업)로 교체
- `appId` (`com.sy.valuation`) — 스토어 패키지명. 변경 시 네이티브 폴더 재생성 권장
- `appName` — 홈 화면 표시 이름

설정을 바꾼 뒤에는 항상 `npx cap sync` 로 네이티브에 반영하세요.

---

## 자주 겪는 이슈

- **첫 실행이 흰 화면/오래 걸림**: Render 무료 플랜이 sleep 상태라 기상에 ~30초.
  폴백 셸이 자동으로 ping 후 진입합니다. (유료 플랜 또는 keep-alive cron 으로 완화)
- **`cap add` 시 SDK 못 찾음**: Android Studio 에서 SDK 경로를 한 번 열어 설정하고
  `ANDROID_HOME` 환경변수 등록.
- **혼합 콘텐츠 차단**: 서버는 HTTPS(`onrender.com`) 라 문제 없음. 자체 HTTP 서버로
  바꾸면 `android.allowMixedContent` / `server.cleartext` 조정 필요.
