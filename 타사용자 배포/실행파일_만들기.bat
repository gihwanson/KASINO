@echo off
chcp 65001 >nul
echo ========================================
echo 실행 파일(.exe) 생성 도구
echo ========================================
echo.
echo 이 도구는 Python 스크립트를 실행 파일로 변환합니다.
echo Python 설치 없이 다른 사용자가 바로 실행할 수 있습니다.
echo.
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

echo [1/3] PyInstaller 설치 확인 중...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller가 설치되어 있지 않습니다.
    echo PyInstaller를 설치하는 중...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [오류] PyInstaller 설치 실패
        pause
        exit /b 1
    )
    echo PyInstaller 설치 완료!
) else (
    echo PyInstaller가 이미 설치되어 있습니다.
)

echo.
echo [2/3] 이전 빌드 파일 정리 중...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist 매크로봇.spec del /q 매크로봇.spec

echo.
echo [3/3] 실행 파일 생성 중...
echo (시간이 다소 걸릴 수 있습니다...)
echo.

python -m PyInstaller --onefile --name "매크로봇" --icon=NONE macro_bot.py

if errorlevel 1 (
    echo.
    echo [오류] 실행 파일 생성 실패
    pause
    exit /b 1
)

echo.
echo ========================================
echo 실행 파일 생성 완료!
echo ========================================
echo.
echo 생성된 파일 위치: dist\매크로봇.exe
echo.
echo 배포할 파일들:
echo - dist\매크로봇.exe
echo - 설정하기.bat
echo - update_env.py
echo - env.example
echo - AI_프롬프트_설정.json (AI 학습 설정 파일 - 중요! 모든 학습 데이터 포함)
echo - 브라우저_설치.bat (선택사항, 브라우저 자동 설치 실패 시)
echo - README_간단버전.md
echo.
echo ⚠️ 주의: .env 파일은 절대 포함하지 마세요!
echo.
echo ✅ AI 학습 파일 확인:
if exist "AI_프롬프트_설정.json" (
    echo   - ✅ AI_프롬프트_설정.json 발견됨 (모든 학습 데이터 포함)
    echo   - 이 파일 하나에 도박 용어 사전, 좋은 댓글 예시, 나쁜 댓글 예시가 모두 포함되어 있습니다
) else (
    echo   - ⚠️ AI_프롬프트_설정.json 없음 (기본 프롬프트 사용)
    echo   - AI 학습을 위해 이 파일을 생성하세요!
)
echo.
pause

