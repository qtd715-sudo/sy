@echo off
REM Windows 작업스케줄러에 SY Valuation 서버 등록.
REM 부팅 시 자동 실행 + 사용자 로그인 시 항상 백그라운드 동작.
REM
REM 등록 후: schtasks /run /tn "SY Valuation Server"  로 즉시 실행
REM 제거:    sy_valuation\uninstall_task.bat

setlocal
set TASKNAME=SY Valuation Server
set HERE=%~dp0
set ROOT=%HERE%..
for %%I in ("%ROOT%") do set ROOTABS=%%~fI

REM Python 경로 자동 탐지
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "delims=" %%P in ('where python') do (
        set PYEXE=%%P
        goto :pyfound
    )
)
echo [오류] python 이 PATH 에 없습니다. Python 3.10+ 설치 후 다시 시도하세요.
exit /b 1

:pyfound
echo [등록] %TASKNAME%
echo   Python:   %PYEXE%
echo   Working:  %ROOTABS%
echo.

REM 기존 작업 제거
schtasks /query /tn "%TASKNAME%" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [기존 작업 제거 중...]
    schtasks /delete /tn "%TASKNAME%" /f >nul
)

REM 새 작업 등록 (사용자 로그인 시 자동 시작)
schtasks /create ^
    /tn "%TASKNAME%" ^
    /tr "\"%PYEXE%\" -m sy_valuation.run --host 0.0.0.0 --port 8765" ^
    /sc onlogon ^
    /rl highest ^
    /f ^
    /it
if %ERRORLEVEL% NEQ 0 (
    echo [오류] 작업 등록 실패. 관리자 권한으로 실행해 보세요.
    exit /b 1
)

REM 작업 디렉토리 설정 (XML 패치)
schtasks /run /tn "%TASKNAME%" >nul

echo.
echo [완료] 다음 로그인부터 SY Valuation 서버가 자동 시작됩니다.
echo        지금 실행:  schtasks /run /tn "%TASKNAME%"
echo        지금 중지:  schtasks /end /tn "%TASKNAME%"
echo        제거:       sy_valuation\uninstall_task.bat
echo.
endlocal
