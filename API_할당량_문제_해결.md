# OpenAI API 할당량 초과 문제 해결

## 🔴 현재 상황

**오류 메시지:**
```
You exceeded your current quota, please check your plan and billing details.
```

이것은 API 키가 잘못된 것이 아니라, **사용 가능한 크레딧(할당량)이 모두 소진**되었다는 의미입니다.

## 💰 할당량 확인 및 충전 방법

### 1. OpenAI 플랫폼 접속
1. https://platform.openai.com 접속
2. 로그인

### 2. Billing 메뉴 확인
1. 왼쪽 사이드바에서 **"Billing"** 또는 **"Usage"** 클릭
2. 현재 사용량과 남은 크레딧 확인

### 3. 크레딧 충전
1. **"Add payment method"** 또는 **"Add credits"** 클릭
2. 결제 정보 입력
3. 크레딧 충전

### 4. 할당량 확인
- **Usage** 메뉴에서 일일/월간 사용량 확인
- **Rate limits** 확인

## 🔄 임시 해결 방법

### 방법 1: 기본 댓글 사용 (무료)
- API 키를 제거하거나 비활성화
- 기본 댓글 목록 사용
- 비용 없이 계속 사용 가능

### 방법 2: 크레딧 충전 후 재시도
- OpenAI 계정에 크레딧 충전
- 프로그램 다시 실행

## 📊 비용 확인

- GPT-3.5-turbo: 약 $0.0005 ~ $0.0015 per 1K tokens
- 댓글 하나당 약 50 tokens 사용
- 1000개 댓글 ≈ $0.05 ~ $0.15

## ⚙️ 프로그램 수정

할당량 초과 시 자동으로 기본 댓글을 사용하도록 프로그램이 수정되어 있습니다.

