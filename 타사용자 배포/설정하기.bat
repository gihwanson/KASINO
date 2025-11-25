@echo off
chcp 65001 >nul
echo ========================================
echo 매크로 봇 초기 설정
echo ========================================
echo.

REM .env 파일이 있는지 확인
if exist .env (
    echo [알림] .env 파일이 이미 존재합니다.
    echo.
    
    REM Python이 있는지 확인하고 update_env.py 실행
    python --version >nul 2>&1
    if not errorlevel 1 (
        echo MAX_POSTS와 OPENAI_API_KEY를 기본값으로 업데이트합니다...
        echo.
        
        python update_env.py
        
        if errorlevel 1 (
            echo [경고] 자동 업데이트 실패. 수동으로 수정해주세요.
            echo.
        ) else (
            echo.
        )
    ) else (
        echo [알림] Python이 설치되어 있지 않아 자동 업데이트를 건너뜁니다.
        echo 수동으로 .env 파일을 수정하세요.
        echo.
    )
    
    echo .env 파일을 지금 열까요? (Y/N)
    set /p open="> "
    
    if /i "%open%"=="Y" (
        notepad .env
    )
    
    echo.
    pause
    exit /b 0
)

REM .env.example 또는 env.example 파일이 있는지 확인
if exist .env.example (
    set ENV_EXAMPLE=.env.example
) else if exist env.example (
    set ENV_EXAMPLE=env.example
) else (
    echo [오류] .env.example 또는 env.example 파일을 찾을 수 없습니다.
    pause
    exit /b 1
)

REM .env.example을 .env로 복사
echo %ENV_EXAMPLE% 파일을 .env로 복사 중...
copy %ENV_EXAMPLE% .env >nul

if errorlevel 1 (
    echo [오류] .env 파일 복사 실패
    echo %ENV_EXAMPLE% 파일이 존재하는지 확인하세요.
    pause
    exit /b 1
)

if exist .env (
    echo.
    echo ========================================
    echo 설정 파일 생성 완료!
    echo ========================================
    echo.
    echo 다음 단계:
    echo 1. .env 파일을 메모장으로 열기
    echo 2. 필수 항목 수정:
    echo    - LOGIN_USERNAME (아이디)
    echo    - PASSWORD (비밀번호)
    echo 3. 선택 항목 수정 (AI 댓글 사용 시):
    echo    - GEMINI_API_KEY (무료, 추천!)
    echo    - OPENAI_API_KEY (유료, 선택사항)
    echo 4. 저장
    echo.
    echo .env 파일을 지금 열까요? (Y/N)
    set /p open="> "
    
    if /i "%open%"=="Y" (
        echo.
        echo .env 파일을 메모장으로 엽니다...
        echo.
        echo ========================================
        echo [필수 설정]
        echo ========================================
        echo 1. LOGIN_USERNAME=INPUT_YOUR_ID_HERE 부분에 아이디 입력
        echo 2. PASSWORD=INPUT_YOUR_PASSWORD_HERE 부분에 비밀번호 입력
        echo.
        echo ========================================
        echo [선택 설정 - AI 댓글 사용 시]
        echo ========================================
        echo 3. GEMINI_API_KEY= 부분에 Gemini API 키 입력 (무료, 추천!)
        echo    발급 주소: https://makersuite.google.com/app/apikey
        echo.
        echo 4. OPENAI_API_KEY= 부분에 OpenAI API 키 입력 (유료, 선택사항)
        echo    발급 주소: https://platform.openai.com/api-keys
        echo.
        echo [참고]
        echo - AI API 키를 입력하지 않으면 기본 댓글이 사용됩니다.
        echo - Gemini API는 무료이므로 추천합니다!
        echo - OpenAI API는 유료이지만 할당량이 초과되면 자동으로 Gemini로 전환됩니다.
        echo.
        echo 5. 저장 (Ctrl + S)
        echo.
        pause
        notepad .env
    ) else (
        echo.
        echo .env 파일을 직접 열어서 수정하세요.
        echo.
        echo [필수] LOGIN_USERNAME, PASSWORD 입력
        echo [선택] GEMINI_API_KEY, OPENAI_API_KEY 입력 (AI 댓글 사용 시)
    )
) else (
    echo [오류] .env 파일 생성 실패
    pause
    exit /b 1
)

echo.
echo 설정이 완료되면 프로그램을 실행하세요!
pause

