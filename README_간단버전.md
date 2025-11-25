# 매크로 봇 - 빠른 시작 가이드

## ⚡ 3단계로 시작하기

### 1. 설정 파일 만들기
`설정하기.bat` 파일을 더블클릭
- 자동으로 `.env` 파일이 생성되고 메모장이 열립니다

### 2. 로그인 정보 입력
메모장에서:
- `LOGIN_USERNAME=INPUT_YOUR_ID_HERE` → 아이디 입력
- `PASSWORD=INPUT_YOUR_PASSWORD_HERE` → 비밀번호 입력
- 저장 (Ctrl + S)

**예시:**
```env
LOGIN_USERNAME=myusername
PASSWORD=mypassword123!
```

### 3. 실행
`실행하기.bat` 파일을 더블클릭
- 처음 실행 시 필요한 라이브러리가 자동으로 설치됩니다
- 그 다음부터는 바로 실행됩니다

**끝!** 🎉

---

## 📋 파일 설명

- `설정하기.bat`: 초기 설정 파일 생성 (처음 한 번만 실행)
- `실행하기.bat`: 프로그램 실행
- `.env`: 설정 파일 (로그인 정보 입력)
- `.env.example`: 설정 예시 파일

## 📚 더 자세한 정보

- `처음_사용하기.md`: 상세한 사용 가이드

## ⚠️ 주의사항

- `.env` 파일에는 비밀번호가 포함되므로 절대 공유하지 마세요
- 웹사이트의 이용약관을 확인하고 준수하세요

## 🆘 문제 해결

### Python이 설치되어 있지 않아요
- https://www.python.org/downloads/ 에서 Python 설치
- 설치 시 "Add Python to PATH" 체크

### 라이브러리 설치 오류
- 인터넷 연결 확인
- Python이 올바르게 설치되었는지 확인
