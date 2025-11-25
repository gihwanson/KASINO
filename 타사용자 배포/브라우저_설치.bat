@echo off
chcp 65001 >nul
echo ========================================
echo Playwright 브라우저 설치
echo ========================================
echo.
echo 이 도구는 매크로 프로그램에 필요한 브라우저를 설치합니다.
echo (처음 한 번만 설치하면 됩니다)
echo.
echo ========================================
echo.

REM Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo 브라우저를 설치하려면 Python이 필요합니다.
    echo Python을 설치한 후 다시 시도하세요.
    echo.
    echo Python 다운로드: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM playwright 설치 확인
python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo [알림] playwright 패키지를 먼저 설치하는 중...
    python -m pip install playwright
    if errorlevel 1 (
        echo [오류] playwright 설치 실패
        pause
        exit /b 1
    )
)

echo.
echo 브라우저를 설치하는 중...
echo (이 작업은 몇 분 정도 걸릴 수 있습니다)
echo.

python -m playwright install chromium

if errorlevel 1 (
    echo.
    echo [오류] 브라우저 설치 실패
    echo 인터넷 연결을 확인하고 다시 시도하세요.
    pause
    exit /b 1
)

echo.
echo ========================================
echo 브라우저 설치 완료!
echo ========================================
echo.
echo 이제 매크로 프로그램을 실행할 수 있습니다.
echo.
pause

