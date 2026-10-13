@echo off
title AHS Study Assistant - GitHub par bhejna
cd /d "%~dp0"

echo ===========================================
echo    Changes GitHub par bhej raha hoon...
echo ===========================================
echo.

git push
if errorlevel 1 (
    echo.
    echo PUSH NAHI HUA. Upar wala error parh kar Claude ko screenshot bhejein.
) else (
    echo.
    echo PUSH HO GAYA. 1-2 minute mein live app update ho jayegi.
)
echo.
pause
