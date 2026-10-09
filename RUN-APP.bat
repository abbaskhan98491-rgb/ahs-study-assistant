@echo off
title AHS Study Assistant
cd /d "%~dp0"

echo ===========================================
echo    AHS Study Assistant - local server
echo ===========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo PYTHON NAHI MILA.
    echo.
    echo python.org se Python install karein. Install karte waqt
    echo "Add Python to PATH" par tick lagana na bhoolein.
    echo.
    pause
    exit /b 1
)

if not exist "app.py" (
    echo app.py is folder me nahi mili.
    echo Ye file project folder ke andar honi chahiye.
    echo.
    pause
    exit /b 1
)

python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo Pehli baar chal raha hai. Packages install ho rahe hain.
    echo 5 se 10 minute lag sakte hain. Window band mat karein.
    echo.
    python -m pip install -r requirements.txt
    echo.
    python -c "import streamlit" >nul 2>&1
    if errorlevel 1 (
        echo Install poora nahi hua. Upar wala error padhein.
        echo.
        pause
        exit /b 1
    )
)

echo App khul raha hai. Browser khud khulega.
echo Pehli baar 1 se 2 minute lagte hain - model load hota hai.
echo.
echo BAND KARNE KE LIYE: is window me Ctrl aur C saath dabayen.
echo.

python -m streamlit run app.py --server.fileWatcherType none

echo.
echo App band ho gaya.
pause
