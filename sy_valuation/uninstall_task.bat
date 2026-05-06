@echo off
set TASKNAME=SY Valuation Server
schtasks /end /tn "%TASKNAME%" >nul 2>&1
schtasks /delete /tn "%TASKNAME%" /f
echo [제거 완료]
