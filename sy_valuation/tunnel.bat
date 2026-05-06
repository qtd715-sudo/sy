@echo off
REM 외부(인터넷)에서 접속 가능한 임시 공개 URL 만들기.
REM 사용 전 sy_valuation\run.py 가 실행 중이어야 함.
REM
REM 주의: 회사 네트워크에서 Cloudflare 포트(7844) 가 막혀 있을 수 있습니다.
REM       그 경우 모바일 핫스팟 또는 자택망에서 실행하거나, Render.com 클라우드 배포를 권장.

setlocal
set HERE=%~dp0
set LOCAL_CF=%HERE%bin\cloudflared.exe

REM 1) 로컬 bin 의 cloudflared 우선 사용
if exist "%LOCAL_CF%" (
    echo [cloudflared, 로컬 바이너리] 임시 터널 시작...
    "%LOCAL_CF%" tunnel --url http://localhost:8765 --no-autoupdate
    goto :eof
)

REM 2) PATH 의 cloudflared 시도
where cloudflared >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [cloudflared] 임시 터널 시작...
    cloudflared tunnel --url http://localhost:8765
    goto :eof
)

REM 2) ngrok 시도 (계정 필요)
where ngrok >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [ngrok] 터널 시작...
    ngrok http 8765
    goto :eof
)

echo [안내] 외부 접속 터널 도구가 설치되어 있지 않습니다.
echo.
echo 추천 1: cloudflared (무료, 회원가입 불필요, 가장 간단)
echo   - 다운로드: https://github.com/cloudflare/cloudflared/releases/latest
echo   - 설치 후 다시 sy_valuation\tunnel.bat 실행
echo.
echo 추천 2: ngrok (계정 필요, 안정적)
echo   - 다운로드: https://ngrok.com/download
echo   - 가입 후 토큰 등록: ngrok config add-authtoken ^<TOKEN^>
echo.
echo 추천 3: 같은 Wi-Fi 안에서만 접속 (간단)
echo   - 서버 실행 시 표시되는 LAN URL을 폰/태블릿에서 열기
echo.
pause
