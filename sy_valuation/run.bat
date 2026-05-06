@echo off
REM SY 기업가치평가 시스템 실행 스크립트 (Windows)
REM
REM 옵션 환경변수:
REM   set DART_API_KEY=...
REM   set NAVER_CLIENT_ID=...
REM   set NAVER_CLIENT_SECRET=...

set PYTHONIOENCODING=utf-8
cd /d "%~dp0\.."
python -m sy_valuation.run %*
