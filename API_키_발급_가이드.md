# OpenAI API 키 발급 및 설정 가이드

## 🔑 API 키 발급 방법

### 1단계: OpenAI 플랫폼 접속

1. 브라우저에서 **https://platform.openai.com** 접속
2. 로그인 (이미 계정이 있다면 로그인)

### 2단계: API Keys 메뉴로 이동

1. 왼쪽 사이드바에서 **"API keys"** 클릭
   - 또는 직접 링크: https://platform.openai.com/api-keys

### 3단계: 새 API 키 생성

1. **"+ Create new secret key"** 버튼 클릭
2. 키 이름 입력 (선택사항, 예: "macro_bot")
3. **"Create secret key"** 클릭
4. **⚠️ 중요: API 키가 한 번만 표시됩니다!**
   - 즉시 복사하세요!
   - 이 창을 닫으면 다시 볼 수 없습니다

### 4단계: API 키 복사

생성된 API 키를 복사하세요.
- 형식: `sk-`로 시작하는 긴 문자열
- 예시: `sk-1234567890abcdefghijklmnopqrstuvwxyz`

## 📝 .env 파일에 입력하기

### 방법 1: 직접 수정 (추천)

1. 프로젝트 폴더에서 `.env` 파일 찾기
2. 메모장으로 열기
3. 다음 줄을 찾아서 수정:

```env
OPENAI_API_KEY=여기에_API_키_붙여넣기
```

**예시:**
```env
OPENAI_API_KEY=sk-1234567890abcdefghijklmnopqrstuvwxyz
```

4. 저장 (Ctrl + S)

### 방법 2: 제가 수정해드리기

API 키를 알려주시면 제가 `.env` 파일에 직접 입력해드릴 수 있습니다!

**예시:**
```
"API 키는 sk-1234567890abcdefghijklmnopqrstuvwxyz 입니다"
```

## ✅ 확인 방법

프로그램을 실행하면:
- API 키가 있으면: `[AI] 댓글 생성 완료: ...` 메시지가 표시됩니다
- API 키가 없으면: `[경고] OpenAI API 키가 없습니다. 기본 댓글을 사용합니다.` 메시지가 표시됩니다

## 🔒 보안 주의사항

- ⚠️ **API 키는 절대 공유하지 마세요!**
- ⚠️ **`.env` 파일을 Git에 커밋하지 마세요!**
- ⚠️ **다른 사람에게 `.env` 파일을 전달하지 마세요!**

## 💰 비용 확인

API 사용량과 비용은 다음에서 확인할 수 있습니다:
- https://platform.openai.com/usage

## 🆘 문제 해결

### API 키가 작동하지 않아요
- API 키가 올바르게 복사되었는지 확인
- 앞뒤 공백이 없는지 확인
- `.env` 파일 저장이 제대로 되었는지 확인

### 비용이 걱정돼요
- GPT-3.5-turbo 모델 사용 (비용 효율적)
- 댓글 하나당 약 $0.0001 ~ $0.0002
- 사용량 제한 설정 가능 (OpenAI 플랫폼에서)

