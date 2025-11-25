@echo off
chcp 65001 >nul
echo ========================================
echo 매크로 봇 실행
echo ========================================
echo.

REM .env 파일 확인
if not exist .env (
    echo [오류] .env 파일을 찾을 수 없습니다.
    echo.
    echo 먼저 "설정하기.bat"를 실행하여 설정 파일을 만드세요.
    echo.
    pause
    exit /b 1
)

REM Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo Python을 설치한 후 다시 시도하세요.
    echo.
    pause
    exit /b 1
)

REM 필요한 라이브러리 확인 및 설치
echo 필요한 라이브러리를 확인하는 중...
python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo.
    echo 필요한 라이브러리를 설치하는 중...
    echo (처음 실행 시 한 번만 설치됩니다)
    echo.
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [오류] 라이브러리 설치 실패
        pause
        exit /b 1
    )
    echo.
    echo Playwright 브라우저를 설치하는 중...
    python -m playwright install chromium
    echo.
)

echo.
echo ========================================
echo 프로그램 실행 중...
echo ========================================
echo.
python macro_bot.py

echo.
echo 프로그램이 종료되었습니다.
pause

