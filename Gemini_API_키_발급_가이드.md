# Google Gemini API 키 발급 가이드 (무료!)

## 🆓 무료 AI 댓글 생성

Google Gemini API는 **무료 티어**를 제공합니다! OpenAI의 할당량이 초과되었거나 비용이 걱정되면 Gemini API를 사용하세요.

## 🔑 Gemini API 키 발급 방법

### 1단계: Google AI Studio 접속

1. 브라우저에서 **https://makersuite.google.com/app/apikey** 접속
2. Google 계정으로 로그인

### 2단계: API 키 생성

1. **"Create API Key"** 또는 **"Get API Key"** 버튼 클릭
2. 프로젝트 선택 (새 프로젝트 생성 가능)
3. API 키 생성
4. **⚠️ 중요: API 키를 복사하세요!**

### 3단계: .env 파일에 추가

`.env` 파일을 열어서 다음 줄을 추가:

```env
GEMINI_API_KEY=여기에_API_키_붙여넣기
```

**예시:**
```env
GEMINI_API_KEY=AIzaSyAbc123def456ghi789jkl012mno345pqr678stu
```

## ✨ 특징

- ✅ **완전 무료** (일일 사용량 제한 있음)
- ✅ OpenAI와 동일한 품질의 댓글 생성
- ✅ 할당량 초과 걱정 없음
- ✅ 프로그램이 자동으로 Gemini를 우선 사용

## 📊 사용량 제한

- 무료 티어: 분당 60회 요청
- 일일 제한: 약 1,500회 요청
- 대부분의 사용자에게 충분합니다!

## 🔄 우선순위

프로그램은 다음 순서로 AI를 사용합니다:

1. **Gemini API** (무료, 우선 사용)
2. OpenAI API (유료, Gemini가 없을 때)
3. 기본 댓글 (AI 키가 없을 때)

## 💡 팁

- Gemini API 키만 설정해도 무료로 AI 댓글을 사용할 수 있습니다!
- OpenAI와 Gemini 둘 다 설정하면 Gemini를 우선 사용합니다
- 할당량 초과 걱정 없이 사용 가능합니다

## 🆘 문제 해결

### API 키가 작동하지 않아요
- API 키가 올바르게 복사되었는지 확인
- Google AI Studio에서 API 키가 활성화되어 있는지 확인

### 요청 한도 초과
- 잠시 기다린 후 다시 시도
- 일일 제한이 초과되었을 수 있습니다

