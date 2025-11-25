@echo off
chcp 65001 >nul
echo ========================================
echo OpenAI API 키 테스트
echo ========================================
echo.

REM Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo Python을 먼저 설치하세요.
    echo.
    pause
    exit /b 1
)

REM pip 설치 확인
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [오류] pip가 설치되어 있지 않습니다.
    echo.
    echo pip를 먼저 설치해야 합니다.
    echo "pip_설치.bat" 파일을 실행하거나, Python을 다시 설치하세요.
    echo.
    echo Python 재설치 시:
    echo - "Add Python to PATH" 체크
    echo - "Install pip" 옵션 체크
    echo.
    pause
    exit /b 1
)

REM 필요한 패키지 확인
python -c "import aiohttp" >nul 2>&1
if errorlevel 1 (
    echo [알림] 필요한 패키지를 설치하는 중...
    python -m pip install aiohttp python-dotenv
    if errorlevel 1 (
        echo [오류] 패키지 설치 실패
        pause
        exit /b 1
    )
    echo.
)

REM .env 파일 확인
if not exist .env (
    echo [경고] .env 파일을 찾을 수 없습니다.
    echo 설정하기.bat를 먼저 실행하세요.
    echo.
    pause
    exit /b 1
)

echo 테스트 시작...
echo.
python API_키_테스트.py
if errorlevel 1 (
    echo.
    echo [오류] 테스트 실행 중 오류가 발생했습니다.
    echo.
)

echo.
pause

