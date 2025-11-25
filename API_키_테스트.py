"""
OpenAI API 키 테스트 스크립트
"""
import os
from dotenv import load_dotenv
import aiohttp
import asyncio
import json

load_dotenv()

async def test_api_key():
    """API 키 테스트"""
    print("=" * 50)
    print("OpenAI API 키 테스트")
    print("=" * 50)
    print()
    
    # .env 파일에서 API 키 읽기
    api_key = os.getenv('OPENAI_API_KEY', '')
    
    # API 키 확인
    print("[1단계] API 키 확인")
    print("-" * 50)
    if not api_key:
        print("❌ API 키를 찾을 수 없습니다!")
        print("   .env 파일에 OPENAI_API_KEY를 설정해주세요.")
        return False
    
    if not api_key.strip():
        print("❌ API 키가 비어있습니다!")
        return False
    
    print(f"✅ API 키 발견!")
    print(f"   길이: {len(api_key)}자")
    print(f"   처음 20자: {api_key[:20]}...")
    print(f"   마지막 10자: ...{api_key[-10:]}")
    print()
    
    # API 키 형식 확인
    print("[2단계] API 키 형식 확인")
    print("-" * 50)
    if api_key.startswith('sk-'):
        print("✅ API 키 형식이 올바릅니다 (sk-로 시작)")
    else:
        print("⚠️ API 키 형식이 일반적이지 않습니다 (sk-로 시작하지 않음)")
    print()
    
    # 실제 API 호출 테스트
    print("[3단계] OpenAI API 호출 테스트")
    print("-" * 50)
    print("API 호출 중...")
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {api_key.strip()}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'gpt-3.5-turbo',
                'messages': [
                    {
                        'role': 'user',
                        'content': '안녕하세요'
                    }
                ],
                'max_tokens': 10
            }
            
            async with session.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    result = json.loads(response_text)
                    reply = result['choices'][0]['message']['content'].strip()
                    print("✅ API 호출 성공!")
                    print(f"   응답: {reply}")
                    print()
                    print("=" * 50)
                    print("✅ API 키가 정상적으로 작동합니다!")
                    print("=" * 50)
                    return True
                else:
                    print(f"❌ API 호출 실패!")
                    print(f"   상태 코드: {response.status}")
                    print(f"   응답 내용: {response_text[:200]}")
                    print()
                    
                    if response.status == 401:
                        print("⚠️ 인증 실패: API 키가 유효하지 않거나 만료되었습니다.")
                    elif response.status == 429:
                        print("⚠️ 요청 한도 초과: 잠시 후 다시 시도하세요.")
                    elif response.status == 500:
                        print("⚠️ OpenAI 서버 오류: 잠시 후 다시 시도하세요.")
                    
                    print("=" * 50)
                    print("❌ API 키에 문제가 있습니다.")
                    print("=" * 50)
                    return False
                    
    except asyncio.TimeoutError:
        print("❌ API 호출 시간 초과 (10초)")
        print("   인터넷 연결을 확인하세요.")
        return False
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    asyncio.run(test_api_key())
    print()
    input("아무 키나 누르면 종료됩니다...")

