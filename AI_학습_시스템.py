"""
AI 댓글 학습 시스템
Few-shot learning과 피드백 기반 프롬프트 개선
"""
import os
import json
import asyncio
import aiohttp
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

LEARNING_DATA_FILE = 'ai_learning_data.json'

def load_learning_data():
    """학습 데이터 불러오기"""
    if os.path.exists(LEARNING_DATA_FILE):
        with open(LEARNING_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'version': 1,
        'few_shot_examples': [],  # 좋은 댓글 예시들
        'bad_examples': [],  # 나쁜 댓글 예시들
        'improved_prompt': '',  # 개선된 프롬프트
        'feedback_history': []
    }

def save_learning_data(data):
    """학습 데이터 저장"""
    with open(LEARNING_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_gambling_terms():
    """도박 용어 사전 불러오기"""
    try:
        terms_file = '도박용어_사전.json'
        if os.path.exists(terms_file):
            with open(terms_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[경고] 도박 용어 사전 로드 실패: {e}")
    return None

def get_gambling_terms_prompt():
    """도박 용어 사전을 프롬프트 형식으로 변환"""
    terms_data = load_gambling_terms()
    if not terms_data:
        return ""
    
    prompt_sections = []
    prompt_sections.append("\n\n🎰 도박 용어 사전 (이 용어들을 자연스럽게 사용하세요):\n")
    
    categories = terms_data.get('categories', {})
    for category_name, terms in categories.items():
        category_display = category_name.replace('_', ' ').title()
        prompt_sections.append(f"\n【{category_display}】")
        
        for term, info in terms.items():
            meaning = info.get('의미', '')
            examples = info.get('예문', [])
            prompt_sections.append(f"- {term}: {meaning}")
            if examples:
                prompt_sections.append(f"  예: {', '.join(examples[:2])}")
    
    prompt_sections.append("\n💡 중요: 게시글에서 이 용어들이 나오면 그 맥락을 이해하고, 필요시 댓글에도 자연스럽게 사용하세요.")
    prompt_sections.append("예: '정배 찍었는데 터졌어' → '정배 찍었는데 아쉽네요' 같은 식으로 자연스럽게 반응하세요.")
    
    return "\n".join(prompt_sections)

def get_base_prompt():
    """기본 프롬프트"""
    gambling_terms = get_gambling_terms_prompt()
    return f"""다음 게시글 본문과 기존 댓글들을 읽고, 작성자의 감정에 공감하는 자연스러운 댓글을 작성해주세요.

⚠️ 중요: 이 게시판은 도박 관련 사이트의 자유게시판입니다.{gambling_terms}
- 자유게시판이기 때문에 도박과 관련된 얘기만 하는 것이 아니라 단순 수다를 떨 때도 있습니다
- 게시글 주제가 도박이든 일상이든 상관없이, 본문 내용과 기존 댓글 흐름에 맞춰 작성해야 합니다
- 댓글은 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 작성해야 합니다

🎯 말투 매칭 규칙 (매우 중요):
- 본문이 존댓말이면 댓글도 반드시 높임말을 사용해야 합니다
- 예: 본문이 "~할까요?", "~인가요?", "~일까요?" 같은 높임말 → 댓글은 "~요 입니다", "~요", "~네요", "~어요" 같은 높임말 사용
- 예: 본문이 "~할까?", "~인가?", "~일까?" 같은 반말 → 댓글은 "~야", "~다", "~어" 같은 반말 사용
- 본문의 말투를 정확히 분석하고 그에 맞춰 댓글 말투를 결정해야 합니다

📝 댓글 작성 원칙:
- 작성자의 톤과 감정을 정확히 파악하고 그에 맞춰 댓글 작성
- 본문 내용과 기존 댓글 흐름을 잘 분석한 뒤, 최대한 기존에 달려있는 댓글과 비슷하게 작성
- 기존 댓글들의 말투, 이모티콘 사용 패턴, 길이, 감정선을 분석하여 자연스럽게 이어지는 댓글 작성
- 친구 같은 느낌의 글 → 친구처럼 편하게 반말이나 캐주얼한 댓글
- 존댓말로 쓴 글 → 존댓말로 댓글 작성 (예: "~요", "~네요", "~어요")
- 형식적인 글 → 형식적인 댓글 (하지만 "감사합니다" 같은 금지 단어는 사용하지 말 것)
- 시답잖은 소리 → 그냥 맞춰주기만 하면 됨 (꼭 긍정적일 필요 없음)
- 절망/후회하는 글 → "힘내용~", "아쉽네~", "다음엔 조심해~", "공감해~", "위로해~"
- 기쁨/성공한 글 → "축하해~", "부럽다~", "좋아~", "대박~"
- 아쉬운 글 → "아쉽네~", "다음엔 잘될 거야~", "아깝다~"
- 슬프거나 힘든 글 → "힘내~", "공감해~", "위로해~", "아쉽네~"
- 절대 형식적인 댓글을 사용하지 말 것
- 반드시 10글자 이내로 완성해야 함
- ~입니다 체는 사용하지 말고 ~요 체나 반말체로 작성
- 물결표(~), 느낌표(!), "ㅠㅠ" 같은 기호를 상황에 맞게 0~1회만 사용
- 맞춤법을 반드시 정확하게 사용
- 반드시 게시글 내용과 관련된 댓글이어야 함
- 기존 댓글과 너무 비슷하지 않게 작성하되, 말투와 스타일은 비슷하게 유지

추론 절차:
1. 본문의 말투를 분석합니다 (존댓말인지 반말인지)
2. 본문에서 핵심 키워드와 감정을 파악합니다
3. 기존 댓글들의 말투/이모티콘/길이 패턴을 분석합니다
4. 위 정보를 합쳐 10글자 이내의 댓글을 설계합니다

금지 사항:
- "감사합니다", "감사해요", "감사" 같은 단어
- "좋은 글 감사합니다", "유용한 정보네요" 같은 형식적인 댓글"""

async def generate_comment(post_content: str, existing_comments: list = None, learning_data: dict = None):
    """AI 댓글 생성 (Few-shot learning 포함)"""
    api_key = os.getenv('OPENAI_API_KEY', '')
    
    if not api_key:
        return None, "API 키가 설정되지 않았습니다."
    
    learning_data = learning_data or load_learning_data()
    existing_comments = existing_comments or []
    
    # Few-shot 예시 구성
    few_shot_examples = learning_data.get('few_shot_examples', [])
    few_shot_text = ""
    if few_shot_examples:
        few_shot_text = "\n\n📚 좋은 댓글 예시 (이런 스타일로 작성하세요):\n"
        for i, example in enumerate(few_shot_examples[:5], 1):  # 최대 5개
            few_shot_text += f"\n예시 {i}:\n"
            few_shot_text += f"본문: {example.get('post', '')[:100]}...\n"
            few_shot_text += f"기존 댓글: {', '.join(example.get('existing', [])[:3])}\n"
            few_shot_text += f"좋은 댓글: {example.get('good_comment', '')}\n"
    
    # 나쁜 예시 (피해야 할 것)
    bad_examples = learning_data.get('bad_examples', [])
    bad_examples_text = ""
    if bad_examples:
        bad_examples_text = "\n\n❌ 피해야 할 댓글 예시:\n"
        for bad in bad_examples[:3]:  # 최대 3개
            bad_examples_text += f"- {bad.get('comment', '')} (이유: {bad.get('reason', '')})\n"
    
    comments_text = ""
    if existing_comments:
        comments_text = f"\n\n기존 댓글들:\n" + "\n".join([f"- {c}" for c in existing_comments[:10]])
    
    # 개선된 프롬프트가 있으면 사용
    base_prompt = learning_data.get('improved_prompt', '') or get_base_prompt()
    
    full_prompt = f"""{base_prompt}{few_shot_text}{bad_examples_text}

게시글 본문:
{post_content[:500]}{comments_text}

댓글:"""
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {api_key.strip()}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'gpt-4o',
                'messages': [
                    {
                        'role': 'system',
                        'content': '당신은 도박 관련 사이트의 자유게시판에서 게시글 작성자의 톤과 내용에 맞춰 친근하지만 자연스러운 댓글을 작성하는 도우미입니다. 자유게시판이므로 도박 관련 얘기뿐만 아니라 일상 수다도 올라올 수 있습니다. 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 댓글을 작성해야 합니다. 가장 중요한 것은 본문의 말투를 정확히 분석하는 것입니다: 본문이 "~할까요?", "~인가요?" 같은 존댓말이면 댓글도 반드시 "~요", "~네요", "~어요" 같은 높임말을 사용해야 하고, 본문이 반말이면 댓글도 반말로 작성해야 합니다. 또한 기존 댓글들의 말투, 스타일, 이모티콘 사용 패턴을 분석하여 최대한 기존 댓글과 비슷하게 작성해야 합니다. 작성자가 친구처럼 편하게 썼다면 편하게, 지친 톤이라면 담담하게, 형식적이면 맞춰서 작성하세요. 꼭 긍정적일 필요 없으며, 현실적인 피로감("아 지치네요", "버텨야죠") 같은 표현도 허용되지만 맞춤법은 반드시 정확해야 합니다. 물결표(~), 느낌표(!), "ㅠㅠ" 같은 기호는 상황에 맞게 0~1회만 사용해 과도하게 반복되지 않도록 하세요. 반드시 10글자 이내로 완성해야 합니다. 절대 "감사합니다", "감사해요", "감사" 같은 단어를 사용하지 말고, 형식적인 댓글("좋은 글 감사합니다", "유용한 정보네요" 등)을 사용하지 마세요.'
                    },
                    {
                        'role': 'user',
                        'content': full_prompt
                    }
                ],
                'max_tokens': 30,
                'temperature': 0.9
            }
            
            async with session.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    comment = result['choices'][0]['message']['content'].strip()
                    comment = comment.strip('"').strip("'")
                    return comment, None
                else:
                    error_text = await response.text()
                    return None, f"API 오류: {response.status}"
    except Exception as e:
        return None, f"오류 발생: {str(e)}"

async def chat_with_ai(user_message: str, conversation_history: list = None):
    """AI 조교와 대화"""
    api_key = os.getenv('OPENAI_API_KEY', '')
    
    if not api_key:
        return None, "API 키가 설정되지 않았습니다."
    
    conversation_history = conversation_history or []
    
    messages = [
        {
            'role': 'system',
            'content': '당신은 댓글 작성 AI의 교육을 도와주는 조교입니다. 사용자가 댓글 품질에 대한 피드백을 주면, 그 피드백을 바탕으로 프롬프트를 어떻게 개선할지 구체적으로 제안해주세요. Few-shot learning 예시를 추가하거나 프롬프트를 수정하는 방법을 제안하세요.'
        }
    ]
    
    for conv in conversation_history[-10:]:
        messages.append({'role': 'user', 'content': conv.get('user', '')})
        if conv.get('assistant'):
            messages.append({'role': 'assistant', 'content': conv.get('assistant', '')})
    
    messages.append({'role': 'user', 'content': user_message})
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {api_key.strip()}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'gpt-4o',
                'messages': messages,
                'max_tokens': 500,
                'temperature': 0.7
            }
            
            async with session.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    reply = result['choices'][0]['message']['content'].strip()
                    return reply, None
                else:
                    return None, f"API 오류: {response.status}"
    except Exception as e:
        return None, f"오류 발생: {str(e)}"

async def main():
    """메인 학습 루프"""
    print("=" * 70)
    print("AI 댓글 학습 시스템 - Few-shot Learning")
    print("=" * 70)
    print()
    print("효율적인 학습 방법:")
    print("1. 좋은 댓글 예시를 추가하면 AI가 그 스타일을 학습합니다")
    print("2. 나쁜 댓글 예시를 추가하면 AI가 피하도록 학습합니다")
    print("3. 피드백을 주면 프롬프트가 자동으로 개선됩니다")
    print()
    
    learning_data = load_learning_data()
    conversations = learning_data.get('feedback_history', [])
    
    print(f"현재 버전: v{learning_data.get('version', 1)}")
    print(f"좋은 예시: {len(learning_data.get('few_shot_examples', []))}개")
    print(f"나쁜 예시: {len(learning_data.get('bad_examples', []))}개")
    print()
    
    current_post = None
    current_comments = None
    
    while True:
        print("-" * 70)
        print("명령어: '테스트', '좋은예시', '나쁜예시', '프롬프트', '히스토리', '종료'")
        user_input = input("당신: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() == '종료':
            break
        
        elif user_input.lower() == '테스트':
            print()
            print("게시글 본문을 입력하세요 (여러 줄 입력 가능, 빈 줄 입력 시 종료):")
            post_lines = []
            while True:
                line = input()
                if not line.strip():
                    break
                post_lines.append(line)
            
            if not post_lines:
                continue
            
            current_post = "\n".join(post_lines)
            print()
            
            print("기존 댓글들을 입력하세요 (없으면 엔터):")
            comment_lines = []
            while True:
                line = input()
                if not line.strip():
                    break
                comment_lines.append(line)
            
            current_comments = comment_lines if comment_lines else []
            print()
            
            print("AI 댓글 생성 중...")
            comment, error = await generate_comment(current_post, current_comments, learning_data)
            
            if error:
                print(f"[오류] {error}")
                continue
            
            print()
            print("=" * 70)
            print("생성된 댓글:")
            print("=" * 70)
            print(f"  {comment}")
            print("=" * 70)
            print()
        
        elif user_input.lower() == '좋은예시':
            if not current_post:
                print("[경고] 먼저 '테스트'로 댓글을 생성하세요.")
                continue
            
            print()
            print("이 댓글이 좋은 예시라고 평가하시겠습니까? (Y/N)")
            if input("> ").strip().upper() == 'Y':
                good_comment = input("좋은 댓글을 입력하세요 (또는 엔터로 생성된 댓글 사용): ").strip()
                if not good_comment:
                    print("[경고] 좋은 댓글이 필요합니다.")
                    continue
                
                example = {
                    'post': current_post[:200],
                    'existing': current_comments[:5],
                    'good_comment': good_comment,
                    'timestamp': datetime.now().isoformat()
                }
                
                learning_data.setdefault('few_shot_examples', []).append(example)
                learning_data['version'] = learning_data.get('version', 1) + 1
                save_learning_data(learning_data)
                print(f"✅ 좋은 예시가 추가되었습니다! (버전 v{learning_data['version']})")
        
        elif user_input.lower() == '나쁜예시':
            if not current_post:
                print("[경고] 먼저 '테스트'로 댓글을 생성하세요.")
                continue
            
            print()
            bad_comment = input("나쁜 댓글을 입력하세요: ").strip()
            if not bad_comment:
                continue
            
            reason = input("왜 나쁜지 이유를 입력하세요: ").strip()
            
            example = {
                'comment': bad_comment,
                'reason': reason or '형식적이거나 부적절함',
                'timestamp': datetime.now().isoformat()
            }
            
            learning_data.setdefault('bad_examples', []).append(example)
            learning_data['version'] = learning_data.get('version', 1) + 1
            save_learning_data(learning_data)
            print(f"✅ 나쁜 예시가 추가되었습니다! (버전 v{learning_data['version']})")
        
        elif user_input.lower() == '프롬프트':
            print()
            print("현재 프롬프트를 수정하시겠습니까? (Y/N)")
            if input("> ").strip().upper() == 'Y':
                print("개선 사항을 입력하세요:")
                feedback = input("> ").strip()
                
                if feedback:
                    # AI 조교에게 개선 방법 물어보기
                    print("AI 조교가 개선 방법을 제안하는 중...")
                    ai_reply, error = await chat_with_ai(
                        f"다음 피드백을 바탕으로 프롬프트를 개선하는 방법을 제안해주세요:\n{feedback}",
                        conversations
                    )
                    
                    if error:
                        print(f"[오류] {error}")
                    else:
                        print()
                        print("=" * 70)
                        print("AI 조교 제안:")
                        print("=" * 70)
                        print(ai_reply)
                        print("=" * 70)
                        print()
                        
                        print("이 제안을 반영하시겠습니까? (Y/N)")
                        if input("> ").strip().upper() == 'Y':
                            new_prompt = input("개선된 프롬프트를 입력하세요 (여러 줄, 빈 줄 입력 시 종료):\n").strip()
                            if new_prompt:
                                learning_data['improved_prompt'] = new_prompt
                                learning_data['version'] = learning_data.get('version', 1) + 1
                                save_learning_data(learning_data)
                                print(f"✅ 프롬프트가 업데이트되었습니다! (버전 v{learning_data['version']})")
        
        elif user_input.lower() == '히스토리':
            print()
            print("=" * 70)
            print("학습 히스토리:")
            print("=" * 70)
            print(f"버전: v{learning_data.get('version', 1)}")
            print(f"좋은 예시: {len(learning_data.get('few_shot_examples', []))}개")
            for i, ex in enumerate(learning_data.get('few_shot_examples', [])[-5:], 1):
                print(f"  {i}. {ex.get('good_comment', '')}")
            print(f"나쁜 예시: {len(learning_data.get('bad_examples', []))}개")
            for i, ex in enumerate(learning_data.get('bad_examples', [])[-5:], 1):
                print(f"  {i}. {ex.get('comment', '')} - {ex.get('reason', '')}")
            print("=" * 70)
            print()
        
        else:
            # 일반 대화
            print("AI 조교가 생각하는 중...")
            ai_reply, error = await chat_with_ai(user_input, conversations)
            
            if error:
                print(f"[오류] {error}")
                continue
            
            print()
            print("=" * 70)
            print("AI 조교:")
            print("=" * 70)
            print(ai_reply)
            print("=" * 70)
            print()
            
            conversations.append({
                'timestamp': datetime.now().isoformat(),
                'user': user_input,
                'assistant': ai_reply
            })
            
            learning_data['feedback_history'] = conversations[-50:]
            save_learning_data(learning_data)

if __name__ == '__main__':
    asyncio.run(main())

