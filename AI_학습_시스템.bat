@echo off
chcp 65001 >nul
echo ========================================
echo AI 댓글 학습 시스템
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    pause
    exit /b 1
)

if not exist .env (
    echo [경고] .env 파일을 찾을 수 없습니다.
    echo.
)

python -c "import aiohttp" >nul 2>&1
if errorlevel 1 (
    echo [알림] 필요한 패키지를 설치하는 중...
    python -m pip install aiohttp python-dotenv
    echo.
)

python AI_학습_시스템.py

pause

