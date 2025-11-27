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

REM pip 설치 확인 및 설치
echo pip를 확인하는 중...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo pip가 설치되어 있지 않습니다. pip를 설치하는 중...
    echo.
    REM 방법 1: ensurepip 시도
    python -m ensurepip --upgrade
    REM ensurepip 실행 후 pip가 실제로 설치되었는지 다시 확인
    python -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo ensurepip로 설치되지 않았습니다. get-pip.py를 다운로드하여 설치 시도 중...
        REM 방법 2: get-pip.py 다운로드 및 실행 (PowerShell 사용)
        powershell -Command "try { Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py' -ErrorAction Stop; exit 0 } catch { exit 1 }"
        if exist get-pip.py (
            python get-pip.py
            del get-pip.py
            REM get-pip.py 실행 후 pip가 실제로 설치되었는지 다시 확인
            python -m pip --version >nul 2>&1
            if errorlevel 1 (
                echo.
                echo [오류] pip 설치 실패
                echo.
                echo 해결 방법:
                echo 1. Python을 재설치하세요 (설치 시 "Add Python to PATH" 체크)
                echo 2. 또는 다음 명령어를 수동으로 실행하세요:
                echo    python -m ensurepip --upgrade
                echo.
                pause
                exit /b 1
            )
        ) else (
            REM get-pip.py 다운로드 실패했지만, 혹시 pip가 설치되었는지 다시 확인
            python -m pip --version >nul 2>&1
            if errorlevel 1 (
                echo.
                echo [오류] get-pip.py 다운로드 실패 및 pip 설치 확인 실패
                echo 인터넷 연결을 확인하거나 Python을 재설치해주세요.
                echo.
                pause
                exit /b 1
            )
        )
    )
    echo pip 설치 완료!
    echo.
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

