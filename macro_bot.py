"""
자동 로그인 및 댓글 작성 매크로 프로그램
"""
import asyncio
import random
import time
import re
import aiohttp
import json
import subprocess
import sys
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Page, Browser
from dotenv import load_dotenv
import os

load_dotenv()


def ensure_playwright_browser():
    """Playwright 브라우저가 설치되어 있는지 확인하고 없으면 자동 설치"""
    # 실행파일인 경우 즉시 확인만 하고 설치 시도하지 않음
    is_frozen = getattr(sys, 'frozen', False)
    
    # 실행파일인 경우 브라우저 확인을 건너뛰고 바로 False 반환
    if is_frozen:
        return False
    
    try:
        # 브라우저가 설치되어 있는지 확인
        from playwright.sync_api import sync_playwright
        
        # 먼저 브라우저 실행 가능 여부 확인
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                    browser.close()
                    return True
                except Exception as launch_error:
                    # 브라우저 실행 실패 - Python 스크립트인 경우 설치 시도
                    error_msg = str(launch_error).lower()
                    if "executable doesn't exist" in error_msg or "browser not found" in error_msg:
                        # 브라우저가 없으면 설치 시도
                        pass
                    else:
                        # 다른 오류인 경우
                        print(f"[경고] 브라우저 실행 오류: {launch_error}")
                        return False
        except Exception as sync_error:
            # sync_playwright 자체가 실패한 경우
            print(f"[경고] Playwright 초기화 오류: {sync_error}")
            return False
        
        # Python 스크립트인 경우에만 설치 시도
        print("[알림] Playwright 브라우저가 설치되어 있지 않습니다.")
        print("[알림] 브라우저를 자동으로 설치하는 중... (처음 실행 시 한 번만 설치됩니다)")
        print("      (이 작업은 몇 분 정도 걸릴 수 있습니다)")
        print()
                
        # playwright install chromium 실행
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                timeout=600,  # 10분 타임아웃
                capture_output=True,
                text=True
            )
            
            print("[완료] 브라우저 설치가 완료되었습니다!")
            print()
            return True
        except subprocess.TimeoutExpired:
            if not is_frozen:
                print("[오류] 브라우저 설치 시간 초과")
                print("[안내] 네트워크 연결을 확인하고 다시 시도하세요.")
            return False
        except subprocess.CalledProcessError as e:
            if not is_frozen:
                print(f"[오류] 브라우저 설치 실패")
                print()
                print("[안내] 수동 설치 방법:")
                print("  python -m playwright install chromium")
                print()
            return False
        except Exception as install_error:
            # Python 스크립트인 경우에만 메시지 출력
            if not is_frozen:
                print(f"[오류] 브라우저 설치 중 오류 발생: {install_error}")
                print()
                print("[안내] 수동 설치 방법:")
                print("  python -m playwright install chromium")
                print()
            return False
    except Exception as e:
        # 실행파일인 경우 즉시 False 반환 (메시지는 main에서 출력)
        if is_frozen:
            return False
        
        error_msg = str(e)
        print(f"[경고] 브라우저 확인 중 오류 발생: {e}")
        
        # "Could not find platform independent libraries" 오류 처리
        if "platform independent libraries" in error_msg or "prefix" in error_msg.lower():
            print()
            print("=" * 60)
            print("[오류] Python 환경 문제가 감지되었습니다.")
            print("=" * 60)
            print()
            print("해결 방법:")
            print("1. Python을 재설치하세요 (https://www.python.org/downloads/)")
            print("2. 또는 다음 명령어로 Playwright 브라우저를 수동 설치하세요:")
            print("   python -m playwright install chromium")
            print()
            print("3. 가상 환경을 사용하는 경우:")
            print("   - 가상 환경을 비활성화하고 다시 시도하세요")
            print("   - 또는 새로운 가상 환경을 만들고 다시 설치하세요")
            print()
            print("=" * 60)
        else:
            print("[안내] 브라우저가 제대로 작동하지 않을 수 있습니다.")
            print("[안내] 수동 설치 방법: python -m playwright install chromium")
        
        return False


class MacroBot:
    def __init__(self, config: dict):
        """
        매크로 봇 초기화
        
        Args:
            config: 설정 딕셔너리
                - url: 대상 사이트 URL
                - login_url: 로그인 페이지 URL
                - username: 사용자명
                - password: 비밀번호
                - board_url: 게시판 URL
                - comment_texts: 댓글 텍스트 리스트
                - delay_min: 최소 대기 시간 (초)
                - delay_max: 최대 대기 시간 (초)
        """
        self.config = config
        self.browser: Browser = None
        self.page: Page = None
        self.playwright = None
        self.commented_posts_file = 'commented_posts.txt'  # 댓글 작성한 게시글 목록 파일
        self.commented_posts = self.load_commented_posts()  # 이미 댓글 작성한 게시글 목록
        self.main_page = None  # 원본 Page 객체 (iframe 사용 시 구분)
        self.current_page = 1  # 현재 보고 있는 게시판 페이지
        self.page_direction = 1  # 1: 다음 페이지로, -1: 이전 페이지로 이동
        self.comment_history = []  # (comment_text, timestamp)
        self.last_comment_time = None
        self.min_repeat_interval = self.config.get('min_repeat_interval_sec', 900)
        self.max_delay_seconds = 10  # 최대 랜덤 대기 제한
        self._last_post_content = ""  # AI 실패 시 사용할 본문
        self._last_post_title = ""  # AI 실패 시 사용할 제목
        self._last_existing_comments = []  # AI 실패 시 사용할 기존 댓글
        
        # AI 프롬프트 설정 로드 확인 (우선순위 1)
        prompt_config = self.load_prompt_config()
        if prompt_config:
            good_examples = len(prompt_config.get('좋은_댓글_예시', []))
            bad_examples = len(prompt_config.get('나쁜_댓글_예시', []))
            print(f"[AI] 프롬프트 설정 로드 완료 (좋은 예시: {good_examples}개, 나쁜 예시: {bad_examples}개)")
            self.learning_data = None  # AI_프롬프트_설정.json을 사용하므로 learning_data는 None
        else:
            print("[AI] 프롬프트 설정 파일 없음 (기본 프롬프트 사용)")
            # AI_프롬프트_설정.json이 없을 때만 기존 학습 데이터 로드 (하위 호환성)
            self.learning_data = self.load_learning_data()
            if self.learning_data:
                print(f"[AI] 학습 데이터 로드 완료 (버전 v{self.learning_data.get('version', 1)})")
                print(f"[AI] 좋은 예시: {len(self.learning_data.get('few_shot_examples', []))}개")
                print(f"[AI] 나쁜 예시: {len(self.learning_data.get('bad_examples', []))}개")
            else:
                print("[AI] 학습 데이터 없음 (기본 프롬프트 사용)")
        
        # 도박 용어 사전 로드 확인 (AI_프롬프트_설정.json에서)
        prompt_config = self.load_prompt_config()
        if prompt_config:
            gambling_terms = prompt_config.get('도박_용어_사전', {})
            if gambling_terms:
                categories = gambling_terms.get('카테고리', {})
                if categories:
                    total_terms = sum(len(terms) for terms in categories.values())
                    print(f"[AI] 도박 용어 사전 로드 완료 ({total_terms}개 용어)")
                else:
                    print("[AI] 도박 용어 사전 없음")
            else:
                print("[AI] 도박 용어 사전 없음")
        else:
            print("[AI] 도박 용어 사전 없음 (프롬프트 설정 파일 없음)")
    
    def load_learning_data(self):
        """학습 데이터 불러오기"""
        try:
            learning_file = 'ai_learning_data.json'
            if os.path.exists(learning_file):
                with open(learning_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[경고] 학습 데이터 로드 실패: {e}")
        return None
    
    def load_prompt_config(self):
        """AI 프롬프트 설정 파일 불러오기"""
        try:
            config_file = 'AI_프롬프트_설정.json'
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[경고] AI 프롬프트 설정 로드 실패: {e}")
        return None
    
    def get_gambling_terms_prompt(self):
        """도박 용어 사전을 프롬프트 형식으로 변환 (AI_프롬프트_설정.json에서 가져옴)"""
        prompt_config = self.load_prompt_config()
        if not prompt_config:
            return ""
        
        gambling_terms = prompt_config.get('도박_용어_사전', {})
        if not gambling_terms:
            return ""
        
        categories = gambling_terms.get('카테고리', {})
        if not categories:
            return ""
        
        prompt_sections = []
        prompt_sections.append("\n\n🎰 도박 용어 사전 (이 용어들을 자연스럽게 사용하세요):\n")
        
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
    
    def load_commented_posts(self) -> set:
        """파일에서 이미 댓글을 작성한 게시글 목록 불러오기"""
        try:
            if os.path.exists(self.commented_posts_file):
                with open(self.commented_posts_file, 'r', encoding='utf-8') as f:
                    posts = set(line.strip() for line in f if line.strip())
                print(f"[중복방지] 이미 댓글 작성한 게시글 {len(posts)}개 불러옴")
                return posts
            else:
                print("[중복방지] 댓글 작성 기록 파일이 없습니다. 새로 시작합니다.")
                return set()
        except Exception as e:
            print(f"[경고] 댓글 작성 기록 불러오기 실패: {e}")
            return set()
    
    def save_commented_post(self, post_url: str):
        """댓글을 작성한 게시글을 파일에 저장"""
        try:
            # 메모리에 추가
            self.commented_posts.add(post_url)
            
            # 파일에 추가 (append 모드)
            with open(self.commented_posts_file, 'a', encoding='utf-8') as f:
                f.write(f"{post_url}\n")
            
            print(f"[중복방지] 게시글 저장: {post_url}")
        except Exception as e:
            print(f"[경고] 게시글 저장 실패: {e}")

    def _cleanup_comment_history(self):
        """최근 댓글 기록 정리"""
        now = time.time()
        self.comment_history = [
            (text, ts) for text, ts in self.comment_history
            if now - ts < max(self.min_repeat_interval, 60)
        ]

    def is_comment_recent(self, comment_text: str):
        """같은 댓글이 최근에 사용됐는지 확인"""
        self._cleanup_comment_history()
        now = time.time()
        for text, ts in self.comment_history:
            if text == comment_text and (now - ts) < self.min_repeat_interval:
                remaining = self.min_repeat_interval - (now - ts)
                return True, max(0, remaining)
        return False, 0

    def record_comment_usage(self, comment_text: str):
        """댓글 사용 이력 저장"""
        now = time.time()
        self._cleanup_comment_history()
        self.comment_history.append((comment_text, now))
        self.last_comment_time = now

    def has_meaningful_content(self, comment_text: str) -> bool:
        """단순 'ㅎㅎ', 'ㅋㅋ' 등만 있는 댓글을 필터링"""
        if not comment_text:
            return False
        stripped = comment_text.strip()
        if len(stripped) < 2:
            return False
        cleaned = re.sub(r'[ㅎㅋ~!?\s\.\,\-_\^\*]+', '', stripped)
        return len(cleaned) >= 2
    
    def extract_keywords_from_post(self, post_content: str, post_title: str = None) -> list:
        """본문에서 핵심 키워드 추출 (명사, 주요 단어) - 개선된 버전"""
        import re
        
        if not post_content:
            return []
        
        # 본문과 제목 합치기
        full_text = post_content
        if post_title:
            full_text = f"{post_title} {post_content}"
        
        # 특수문자 제거 (한글, 영문, 숫자만)
        cleaned = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', full_text)
        
        # 단어 추출
        words = cleaned.split()
        keywords = []
        
        # 제외할 단어들 (조사, 접속사, 일반적인 단어)
        stop_words = {
            '그리고', '그런데', '하지만', '그래서', '그러나', '그런', '이런', '저런',
            '이것', '그것', '저것', '이거', '그거', '저거',
            '오늘', '어제', '내일', '지금', '그때', '이때',
            '있어', '없어', '하는', '하는데', '해서', '하고',
            '좋아', '나쁘', '많이', '조금', '너무', '정말',
            '뭐', '어떤', '어떻게', '언제', '어디', '누가', '왜',
            '것', '거', '게', '건', '걸'
        }
        
        # 명사/주요 단어 추출 (2~5글자, 의미 있는 단어만)
        for word in words:
            word = word.strip()
            # 길이 체크 (2~5글자)
            if len(word) < 2 or len(word) > 5:
                continue
            
            # 한글이 포함된 단어만
            if not re.search(r'[가-힣]', word):
                continue
            
            # 제외 단어 필터링
            if word in stop_words:
                continue
            
            # 숫자만 있는 단어 제외
            if re.match(r'^[0-9]+$', word):
                continue
            
            keywords.append(word)
        
        # 중복 제거 및 빈도순 정렬
        from collections import Counter
        keyword_counts = Counter(keywords)
        # 빈도가 높은 순으로 정렬 (최대 7개로 증가)
        top_keywords = [word for word, count in keyword_counts.most_common(7)]
        
        return top_keywords
    
    def is_comment_relevant_to_post(self, comment_text: str, post_content: str, post_title: str = None) -> bool:
        """댓글이 게시글 제목/본문과 관련이 있는지 확인 (완화된 기준)"""
        if not comment_text or not post_content:
            return False
        
        import re
        
        # 기본 원칙: AI가 생성한 댓글은 기본적으로 허용 (AI가 이미 본문을 분석했으므로)
        # 정말 명백하게 무관한 경우만 거부
        
        # 댓글과 본문/제목을 정리
        comment_clean = re.sub(r'[~!?ㅎㅋㅠㅜ\s\.\,\-]+', '', comment_text)
        post_clean = re.sub(r'[~!?ㅎㅋㅠㅜ\s\.\,\-]+', '', post_content)
        title_clean = re.sub(r'[~!?ㅎㅋㅠㅜ\s\.\,\-]+', '', post_title) if post_title else ""
        
        # 1. 본문이 너무 짧거나 의미 없으면 허용
        if len(post_clean) < 5:
            return True  # 짧은 본문도 허용
        
        # 2. 본문이 의미 없는 경우 (예: "ㅎㅎ", "...", "ㅋㅋ" 등) 허용
        meaningless_patterns = ['ㅎ', 'ㅋ', 'ㅠ', 'ㅜ', '...', '..', '.']
        meaningless_count = sum(post_clean.count(p) for p in meaningless_patterns)
        meaningless_ratio = meaningless_count / max(len(post_clean), 1)
        if meaningless_ratio > 0.5:  # 50% 이상이 의미 없는 문자
            return True  # 의미 없는 본문도 허용
        
        # 3. 일반적인 공감 댓글은 자유게시판 특성상 허용
        # 자유게시판에서는 본문과 직접적인 키워드 매칭이 없어도 감정적으로 공감하는 댓글이 자연스러움
        common_empathy_comments = ['힘내', '아쉽', '공감', '위로', '좋아', '응원', '화이팅', 
                                   '축하', '부럽', '대박', '지치네요', '다음엔', '조심']
        comment_normalized = comment_clean.replace('요', '').replace('네', '').replace('어', '').replace('다', '').replace('해', '').replace('용', '')
        if comment_normalized in common_empathy_comments:
            return True  # 일반적인 공감 댓글은 허용
        
        # 4. 공통 키워드가 있으면 관련성 있음 (참고용, 없어도 OK)
        def extract_keywords(text, min_len=2, max_len=3):
            """텍스트에서 2~3글자 키워드 추출 (간단하게)"""
            keywords = set()
            for i in range(len(text) - min_len + 1):
                for length in range(min_len, min(max_len + 1, len(text) - i + 1)):
                    keyword = text[i:i+length]
                    if len(keyword) >= min_len:
                        keywords.add(keyword)
            return keywords
        
        post_keywords = extract_keywords(post_clean)
        title_keywords = extract_keywords(title_clean) if title_clean else set()
        comment_keywords = extract_keywords(comment_clean)
        
        common_with_post = comment_keywords & post_keywords
        common_with_title = comment_keywords & title_keywords if title_keywords else set()
        
        if len(common_with_post) > 0 or len(common_with_title) > 0:
            return True  # 공통 키워드가 있으면 확실히 관련 있음
        
        # 5. 본문/제목의 핵심 단어가 댓글에 포함되어 있는지 확인 (부분 일치)
        post_important_words = [post_clean[i:i+3] for i in range(len(post_clean)-2)]
        title_important_words = [title_clean[i:i+3] for i in range(len(title_clean)-2)] if title_clean else []
        
        for word in post_important_words + title_important_words:
            if word in comment_clean:
                return True
        
        # 6. 기본적으로 허용 (AI가 생성한 댓글이므로 본문을 분석했을 것으로 가정)
        # 정말 명백하게 무관한 경우만 거부하는데, 현재는 그런 경우를 찾기 어려우므로 기본적으로 허용
        return True  # 기본적으로 허용 (자유게시판 특성상 감정적 공감 댓글도 자연스러움)

    def _is_negative_content(self, text: str) -> bool:
        """본문이 부정적인지 단순 판별"""
        if not text:
            return False
        negative_keywords = ['잃', '망', '눈물', '울', '아쉽', '후회', '슬프', 'ㅠ', 'ㅜ', '손실', '적자', '좌절', '힘들']
        return any(keyword in text for keyword in negative_keywords)
    
    def _is_positive_comment(self, comment_text: str) -> bool:
        """댓글이 긍정적인지 판별 (젊은층 표현 포함)"""
        if not comment_text:
            return False
        positive_keywords = ['화이팅', '좋아', '대박', '축하', '부럽', '좋네', '좋다', '멋져', '최고', '응원', '파이팅', 
                            '와', '헐', '진짜', '개좋', '짱', '허걱', '와우']
        return any(keyword in comment_text for keyword in positive_keywords)
    
    def _is_negative_comment(self, comment_text: str) -> bool:
        """댓글이 부정적인지 판별"""
        if not comment_text:
            return False
        negative_keywords = ['아쉽', '슬프', '힘들', '후회', '아깝', '위로', '공감']
        return any(keyword in comment_text for keyword in negative_keywords)

    def enhance_tone_variation(self, comment_text: str, post_content: str = '', existing_comments: list = None) -> str:
        """물결/느낌표/ㅠㅠ 등을 다양하게 섞되 과한 특수문자 사용은 제한 (기존 댓글 스타일 반영)"""
        if not comment_text:
            return comment_text
        comment = comment_text.strip()
        
        # 기존 댓글 스타일 분석 (있으면)
        style = None
        if existing_comments and len(existing_comments) > 0:
            style = self.analyze_comment_style(existing_comments)
        
        # 이미 어미가 있는지 확인 (요, 죠, 네요, 어요, 해요, 되요, 다요, 야요, 까요, 나요, 세요 등)
        # 물음표는 어미가 아니므로 제외하고 체크
        comment_without_question = comment.rstrip('?')
        # 정규식으로 어미 확인 (반말 어미 포함: 야, 다, 어, 해, 되, 까, 나, 세, 지, 네 등)
        has_ending = bool(re.search(r'(요|죠|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요|네|어|해|되|다|야|까|나|세|지)$', comment_without_question))
        # "야"로 끝나는 경우 명시적으로 체크 (정규식이 놓칠 수 있으므로)
        if not has_ending and comment_without_question.endswith('야'):
            has_ending = True
        
        # 특수 문자 개수 제한 (젊은층 톤을 위해 조금 더 허용)
        special_chars = ['~', '!', 'ㅠ', 'ㅜ']
        special_count = sum(comment.count(ch) for ch in special_chars)
        # 젊은층은 특수 기호를 더 많이 사용하므로 3개까지 허용
        if special_count > 3:
            for ch in special_chars:
                while comment.count(ch) > 2:
                    comment = comment.replace(ch, '', 1)
        
        # ⚠️ "요" 강제 추가 로직 제거 - AI가 생성한 댓글을 그대로 유지
        # 기존 댓글 스타일을 모방하도록 AI에게 지시했으므로, 여기서 추가로 수정하지 않음
        
        # 댓글 내용에 따라 적절한 특수 기호 추가 (기존 댓글 스타일 반영)
        if not any(ch in comment for ch in ['~', '!', 'ㅠ']):
            # 기존 댓글 스타일이 있으면 그에 맞춰 특수 기호 추가
            should_add_emoji = True
            emoji_probability = 0.95  # 기본 확률
            
            if style:
                # 기존 댓글에서 특수 기호 사용 비율에 따라 조정
                if style['emoji_usage_rate'] < 0.1:  # 10% 미만이면 특수 기호 거의 사용 안 함
                    emoji_probability = 0.3  # 확률 낮춤
                elif style['emoji_usage_rate'] < 0.3:  # 30% 미만이면 적당히 사용
                    emoji_probability = 0.7
                elif style['emoji_usage_rate'] >= 0.5:  # 50% 이상이면 많이 사용
                    emoji_probability = 0.98
                
                # 기존 댓글이 특수 기호를 거의 사용하지 않으면 추가하지 않음
                if not style['has_emoji'] and style['emoji_usage_rate'] < 0.1:
                    should_add_emoji = False
            
            if should_add_emoji and random.random() < emoji_probability:
                # 존댓말 어미로 끝나는 경우 (요, 세요, 네요, 어요, 해요 등)
                if re.search(r'(요|세요|네요|어요|해요|되요|다요|까요|나요|지요)$', comment_without_question):
                    # 기존 댓글 스타일에 맞춰 특수 기호 선택
                    if style:
                        # 기존 댓글에서 많이 사용하는 특수 기호 우선
                        if style['has_ㅠ'] and self._is_negative_comment(comment):
                            candidate = 'ㅠ'
                        elif style['has_exclamation'] and self._is_positive_comment(comment):
                            candidate = '!'
                        elif style['has_tilde']:
                            candidate = '~'
                        # 기존 댓글 스타일이 없으면 내용에 따라 결정
                        elif self._is_negative_comment(comment):
                            candidate = 'ㅠ'
                        elif self._is_positive_comment(comment):
                            candidate = '!'
                        else:
                            candidate = '~'
                    else:
                        # 기존 댓글 스타일 정보가 없으면 내용에 따라 결정
                        if self._is_negative_comment(comment):
                            candidate = 'ㅠ'
                        elif self._is_positive_comment(comment):
                            candidate = '!'
                        else:
                            candidate = '~'
                    
                    if len(comment) + len(candidate) <= 10:
                        comment += candidate
                    elif len(comment) < 10:
                        comment = (comment + candidate)[:10]
            # 존댓말 어미가 아닌 경우
            else:
                # 부정적인 내용이면 ㅠ 추가
                if self._is_negative_content(post_content or comment) or self._is_negative_comment(comment):
                    candidate = random.choice(['ㅠ', 'ㅠㅠ'])
                    if len(comment) + len(candidate) <= 10:
                        comment += candidate
                    elif len(comment) < 10:
                        comment = (comment + candidate)[:10]
                    else:
                        comment = comment[:-len(candidate)] + candidate
                # 긍정적인 댓글이면 ! 추가
                elif self._is_positive_comment(comment):
                    candidate = '!'
                    if len(comment) + len(candidate) <= 10:
                        comment += candidate
                    elif len(comment) < 10:
                        comment = (comment + candidate)[:10]
                # 그 외의 경우 물결표나 느낌표 추가 (젊은층 톤)
                else:
                    # 젊은층은 물결표를 더 선호
                    candidate = random.choice(['~', '~', '!'])  # 물결표 확률 2배
                    if len(comment) + len(candidate) <= 10:
                        comment += candidate
                    elif len(comment) < 10:
                        comment = (comment + candidate)[:10]
                    else:
                        comment = comment[:-len(candidate)] + candidate
        
        # 중복된 물결/느낌표 정리
        while '~~' in comment:
            comment = comment.replace('~~', '~')
        while '!!' in comment:
            comment = comment.replace('!!', '!')
        
        # 이미 특수 기호가 있는 경우에도 젊은층 톤을 위해 다양화 (확률 증가)
        if comment.endswith('~') and random.random() < 0.3:
            comment = comment[:-1] + random.choice(['~!', '요~', '요!'])
        elif comment.endswith('!') and random.random() < 0.2:
            # 느낌표 뒤에 물결표 추가 (예: "화이팅이요!~")
            if len(comment) + 1 <= 10:
                comment += '~'
        
        # 의도적인 오타 추가 (사람처럼 보이게, 25% 확률)
        comment = self.add_natural_typos(comment)
        
        # ⚠️ 길이 제한: 완전한 문장인지 확인 후 자르기
        # 어미가 있는 완전한 문장은 보존하되, 10글자 초과 시 어미를 유지한 채 앞부분만 조정
        if len(comment) > 10:
            # 어미가 있는지 확인 (요, 네요, 어요, 해요, 되요, 다요, 세요, 까요, 나요, 지요, 죠, 다, 어, 해, 되, 까, 나, 세, 지, 야 등)
            comment_clean = comment.rstrip('~!?ㅠㅜㅎㅋ').strip()
            has_ending = bool(re.search(r'(요|죠|네요|어요|해요|되요|다요|세요|까요|나요|지요|다|어|해|되|까|나|세|지|야)$', comment_clean))
            
            if has_ending:
                # 어미가 있으면 어미를 보존하면서 앞부분만 자르기
                # 어미 부분 찾기
                ending_match = re.search(r'(요|죠|네요|어요|해요|되요|다요|세요|까요|나요|지요|다|어|해|되|까|나|세|지|야)$', comment_clean)
                if ending_match:
                    ending = ending_match.group(1)
                    # 특수 기호도 보존
                    special_suffix = comment[len(comment_clean):]  # ~, !, ㅠ 등
                    # 앞부분만 자르기 (어미 + 특수기호 제외)
                    max_body_length = 10 - len(ending) - len(special_suffix)
                    if max_body_length > 0:
                        body = comment_clean[:-len(ending)]
                        comment = body[:max_body_length] + ending + special_suffix
                    else:
                        # 어미 + 특수기호가 10글자를 넘으면 어미만 보존
                        comment = ending + special_suffix
            else:
                # 어미가 없으면 그냥 10글자로 자르기 (하지만 이 경우는 AI가 잘못 생성한 것이므로 경고)
                print(f"[경고] 댓글이 완전한 문장으로 끝맺어지지 않습니다: '{comment}' (길이: {len(comment)}자)")
                comment = comment[:10]
        
        return comment
    
    def add_natural_typos(self, comment: str) -> str:
        """의도적인 오타를 추가해서 더 자연스럽게 (젊은층이 자주 쓰는 오타 패턴)"""
        if not comment or len(comment) < 2:
            return comment
        
        # 25% 확률로 오타 추가 (너무 자주 하면 부자연스러움)
        if random.random() > 0.25:
            return comment
        
        original_comment = comment
        
        # 젊은층이 자주 쓰는 오타 패턴들 (우선순위 순)
        # 긴 패턴부터 먼저 체크해야 함 (예: "네요"가 "요"보다 먼저)
        if re.search(r'네요$', comment):
            comment = re.sub(r'네요$', random.choice(['네욘', '네용', '네요']), comment)
        elif re.search(r'어요$', comment):
            comment = re.sub(r'어요$', random.choice(['어욘', '어용', '어요']), comment)
        elif re.search(r'해요$', comment):
            comment = re.sub(r'해요$', random.choice(['해욘', '해용', '해요']), comment)
        elif re.search(r'되요$', comment):
            comment = re.sub(r'되요$', random.choice(['되욘', '되용', '되요']), comment)
        elif re.search(r'다요$', comment):
            comment = re.sub(r'다요$', random.choice(['다욘', '다용', '다요']), comment)
        elif re.search(r'까요$', comment):
            comment = re.sub(r'까요$', random.choice(['까욘', '까용', '까요']), comment)
        elif re.search(r'나요$', comment):
            comment = re.sub(r'나요$', random.choice(['나욘', '나용', '나요']), comment)
        elif re.search(r'세요$', comment):
            comment = re.sub(r'세요$', random.choice(['세욘', '세용', '세요']), comment)
        elif re.search(r'지요$', comment):
            comment = re.sub(r'지요$', random.choice(['지욘', '지용', '지요']), comment)
        elif re.search(r'요$', comment):
            # "요"로 끝나는 경우 (다른 패턴에 해당하지 않는 경우)
            comment = re.sub(r'요$', random.choice(['욘', '용', '요']), comment)
        
        # 단어 내부 오타 (가끔, 이미 어미 오타를 적용하지 않은 경우만)
        if comment == original_comment:
            if '좋아' in comment and random.random() < 0.3:
                comment = comment.replace('좋아', '조아', 1)
            elif '맞아' in comment and random.random() < 0.2:
                comment = comment.replace('맞아', '마자', 1)
            elif '그래' in comment and random.random() < 0.2:
                comment = comment.replace('그래', '그레', 1)
            elif '화이팅' in comment and random.random() < 0.15:
                comment = comment.replace('화이팅', '파이팅', 1)
        
        # 길이 제한 확인 (10글자 초과 시 원래대로)
        if len(comment) > 10:
            comment = original_comment
        
        return comment

    async def enforce_comment_gap(self):
        """댓글 간 랜덤 대기 (리캡챠 회피용)"""
        min_gap = max(1, min(self.config.get('comment_gap_min', 1), self.max_delay_seconds))
        max_gap = max(1, min(self.config.get('comment_gap_max', 5), self.max_delay_seconds))
        if min_gap >= max_gap:
            max_gap = min(self.max_delay_seconds, min_gap + 1)
        if self.last_comment_time is None:
            return
        elapsed = time.time() - self.last_comment_time
        target_gap = random.uniform(min_gap, max_gap)
        if elapsed < target_gap:
            wait_time = target_gap - elapsed
            jitter = random.uniform(0, min(1, wait_time))
            total_wait = min(self.max_delay_seconds, wait_time + jitter)
            if total_wait > 0:
                print(f"[대기] 리캡챠 회피를 위해 {total_wait:.1f}초 대기합니다.")
                await asyncio.sleep(total_wait)

    async def ensure_non_repeating_comment(self, comment_text: str, post_content: str, existing_comments: list) -> str:
        """15분 내 반복 댓글 방지"""
        attempts = 0
        max_attempts = 3
        original = comment_text
        while attempts < max_attempts:
            is_recent, wait_sec = self.is_comment_recent(comment_text)
            if not is_recent:
                return comment_text
            print(f"[경고] 동일 댓글을 {self.min_repeat_interval/60:.1f}분 내에 재사용할 수 없습니다. 남은 시간: {wait_sec:.1f}초")
            if attempts == max_attempts - 1:
                alt_comment = self.generate_style_matched_comment(existing_comments or [], post_content or '')
            else:
                alt_comment = await self.generate_ai_comment_retry(post_content, existing_comments, attempts + 1, post_title=getattr(self, '_last_post_title', None))
            if not alt_comment:
                break
            if alt_comment == comment_text:
                alt_comment += '~'
                if not self.has_meaningful_content(alt_comment):
                    alt_comment = self.generate_style_matched_comment(existing_comments or [], post_content or '')
                    if not self.has_meaningful_content(alt_comment):
                        alt_comment = "지치네요"
            alt_comment = self.enhance_tone_variation(alt_comment, post_content, existing_comments)
            comment_text = alt_comment
            attempts += 1
        print(f"[경고] 댓글이 계속 반복되어 기본 댓글로 전환합니다. 원본: {original}")
        fallback = self.generate_style_matched_comment(existing_comments or [], post_content or '')
        if fallback == original:
            fallback += '~'
        if not self.has_meaningful_content(fallback):
            fallback = "지치네요"
        fallback = self.enhance_tone_variation(fallback, post_content, existing_comments)
        return fallback

    def build_board_page_url(self, page_number: int) -> str:
        """페이지 번호에 맞는 게시판 URL 생성"""
        page_number = max(1, page_number)
        base_url = self.config['board_url']
        
        # URL 유효성 검증
        if not base_url or not isinstance(base_url, str):
            raise ValueError(f"[오류] 게시판 URL이 설정되지 않았거나 잘못되었습니다: {base_url}")
        
        # URL 형식 검증 (http:// 또는 https://로 시작해야 함)
        if not base_url.startswith(('http://', 'https://')):
            raise ValueError(f"[오류] 게시판 URL 형식이 잘못되었습니다. http:// 또는 https://로 시작해야 합니다.\n현재 값: {base_url}\n.env 파일의 BOARD_URL을 확인하세요.")
        
        # 기존 page 파라미터 제거
        clean_url = re.sub(r'([?&])page=\d+', r'\1', base_url).rstrip('?&')
        
        if page_number == 1:
            return clean_url
        
        separator = '&' if '?' in clean_url else '?'
        return f"{clean_url}{separator}page={page_number}"

    async def navigate_to_board_page(self, page_number: int):
        """지정한 게시판 페이지로 이동"""
        target_url = self.build_board_page_url(page_number)
        print(f"[게시판] 페이지 {page_number} 접속 중... ({target_url})")
        
        # Frame을 사용 중이면 원본 page로 복원
        page_to_use = self.main_page if self.main_page else self.page
        if page_to_use:
            # Frame이면 원본 page로 복원
            if hasattr(page_to_use, 'goto'):
                await page_to_use.goto(target_url, wait_until='networkidle')
                self.page = page_to_use  # 원본 page로 복원
            else:
                # Frame인 경우 부모 page 사용
                if self.main_page:
                    await self.main_page.goto(target_url, wait_until='networkidle')
                    self.page = self.main_page
                else:
                    raise Exception("페이지 객체를 찾을 수 없습니다.")
        else:
            raise Exception("페이지 객체를 찾을 수 없습니다.")
        
        await self.random_delay(2, 4)

    async def switch_board_page(self, reason: str = '') -> bool:
        """다음/이전 게시판 페이지로 이동"""
        max_pages = max(1, self.config.get('max_board_pages', 1))
        
        if max_pages == 1:
            print("[게시판] 이동 가능한 추가 페이지가 없습니다.")
            return False
        
        if reason:
            print(f"[게시판] 페이지 전환 사유: {reason}")
        
        next_page = self.current_page + self.page_direction
        
        if next_page > max_pages:
            self.page_direction = -1
            next_page = max_pages - 1 if max_pages > 1 else 1
        elif next_page < 1:
            self.page_direction = 1
            next_page = 2 if max_pages > 1 else 1
        
        self.current_page = max(1, min(max_pages, next_page))
        direction_text = '다음' if self.page_direction == 1 else '이전'
        print(f"[게시판] 페이지 {self.current_page}로 이동 ({direction_text} 방향 순환)")
        await self.navigate_to_board_page(self.current_page)
        return True
    
    async def init_browser(self, headless: bool = False):
        """브라우저 초기화"""
        try:
            if not self.playwright:
                self.playwright = await async_playwright().start()
            
            # 실행파일인 경우 브라우저 경로를 명시적으로 찾기
            is_frozen = getattr(sys, 'frozen', False)
            launch_options = {
                'headless': headless,
                'slow_mo': 500  # 동작을 천천히 (디버깅용)
            }
            
            if is_frozen:
                # 실행파일인 경우 시스템에 설치된 브라우저 경로 찾기
                import platform
                if platform.system() == 'Windows':
                    # Windows에서 Playwright 브라우저 경로 찾기
                    user_home = os.path.expanduser('~')
                    import glob
                    
                    # 가능한 경로 패턴들
                    possible_patterns = [
                        os.path.join(user_home, 'AppData', 'Local', 'ms-playwright', 'chromium-*', 'chrome-win', 'chrome.exe'),
                        os.path.join(user_home, '.cache', 'ms-playwright', 'chromium-*', 'chrome-win', 'chrome.exe'),
                    ]
                    
                    # 실제 경로 찾기
                    browser_path = None
                    for pattern in possible_patterns:
                        matches = glob.glob(pattern)
                        if matches:
                            # 가장 최신 버전 찾기 (경로에 버전 번호가 포함됨)
                            browser_path = sorted(matches, reverse=True)[0]
                            if os.path.exists(browser_path):
                                break
                    
                    if browser_path and os.path.exists(browser_path):
                        launch_options['executable_path'] = browser_path
                        print(f"[정보] 브라우저 경로를 찾았습니다: {browser_path}")
                    else:
                        # 브라우저 경로를 찾지 못한 경우
                        print("[경고] 브라우저 경로를 자동으로 찾지 못했습니다.")
                        print("[경고] Playwright가 기본 경로에서 브라우저를 찾으려고 시도합니다.")
            
            self.browser = await self.playwright.chromium.launch(**launch_options)
            self.page = await self.browser.new_page()
            self.main_page = self.page  # 원본 page 저장
            # 봇 탐지 방지를 위한 User-Agent 설정
            await self.page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
        except Exception as e:
            error_msg = str(e).lower()
            if "executable doesn't exist" in error_msg or "browser not found" in error_msg or "chromium" in error_msg:
                print()
                print("=" * 60)
                print("[오류] 브라우저를 찾을 수 없습니다.")
                print("=" * 60)
                print()
                print("브라우저가 설치되어 있지 않거나 찾을 수 없습니다.")
                print()
                print("해결 방법:")
                print("  방법 1 (Python이 설치된 경우 - 권장):")
                print("    - '브라우저_설치_단독.py' 파일을 더블클릭하여 실행")
                print("    - 또는 '브라우저_설치_단독.bat' 파일을 더블클릭하여 실행")
                print()
                print("  방법 2 (Python이 없는 경우):")
                print("    1. Python을 설치하세요 (https://www.python.org/downloads/)")
                print("    2. 위 방법 1을 사용하세요")
                print()
                raise Exception("브라우저를 찾을 수 없습니다. 위 방법으로 브라우저를 설치하세요.")
            else:
                raise

    async def reset_browser(self, headless: bool = False):
        """브라우저를 완전히 재시작"""
        print("[브라우저] 브라우저를 재시작합니다.")
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception as e:
            print(f"[브라우저] 페이지 종료 중 오류: {e}")
        try:
            if self.browser:
                await self.browser.close()
        except Exception as e:
            print(f"[브라우저] 브라우저 종료 중 오류: {e}")
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            print(f"[브라우저] Playwright 종료 중 오류: {e}")
        finally:
            self.playwright = None
        await self.init_browser(headless=headless)
        if not await self.login():
            raise RuntimeError("브라우저 재시작 후 로그인에 실패했습니다.")
        self.current_page = 1
        self.page_direction = 1
        await self.navigate_to_board_page(self.current_page)
    
    async def login(self):
        """사이트에 로그인"""
        print(f"[로그인] {self.config['login_url']} 접속 중...")
        await self.page.goto(self.config['login_url'], wait_until='networkidle')
        
        # 랜덤 대기 (봇 탐지 방지)
        await self.random_delay(1, 3)
        
        # 로그인 폼 찾기 및 입력
        # 실제 사이트에 맞게 선택자를 수정해야 합니다
        try:
            # 사용자명 입력 필드 - 여러 선택자 시도
            username_selector = self.config.get('username_selector', 'input[name="username"]')
            print(f"[로그인] 사용자명 입력 필드 찾는 중: {username_selector}")
            
            # 여러 선택자 시도
            possible_selectors = [
                username_selector,
                'input[type="text"]',
                'input[id*="id"]',
                'input[id*="user"]',
                'input[name*="id"]',
                'input[name*="user"]',
                'input.mb_id',
                'input#mb_id',
                'input[name="mb_id"]',
            ]
            
            found_selector = None
            for selector in possible_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    found_selector = selector
                    print(f"[로그인] 사용자명 필드 찾음: {selector}")
                    break
                except:
                    continue
            
            if not found_selector:
                # 모든 선택자 실패 시 페이지 HTML 확인
                print("[디버깅] 페이지의 모든 input 요소 확인 중...")
                inputs = await self.page.query_selector_all('input')
                print(f"[디버깅] 발견된 input 요소 수: {len(inputs)}")
                for i, inp in enumerate(inputs[:5]):  # 처음 5개만
                    try:
                        input_info = await inp.evaluate('el => ({type: el.type, name: el.name, id: el.id, class: el.className})')
                        print(f"[디버깅] Input {i+1}: {input_info}")
                    except:
                        pass
                raise Exception(f"사용자명 입력 필드를 찾을 수 없습니다. 시도한 선택자: {possible_selectors}")
            
            username_selector = found_selector
            
            # 필드를 클릭해서 포커스 주기
            await self.page.click(username_selector)
            await self.random_delay(0.3, 0.5)
            
            # 기존 내용 지우고 입력
            await self.page.fill(username_selector, '')
            await self.page.type(username_selector, self.config['username'], delay=100)
            print(f"[로그인] 사용자명 입력 완료: {self.config['username']}")
            await self.random_delay(0.5, 1.0)
            
            # 비밀번호 입력 필드 - 여러 선택자 시도
            password_selector = self.config.get('password_selector', 'input[name="password"]')
            print(f"[로그인] 비밀번호 입력 필드 찾는 중: {password_selector}")
            
            # 여러 선택자 시도
            possible_password_selectors = [
                password_selector,
                'input[type="password"]',
                'input[id*="pw"]',
                'input[id*="pass"]',
                'input[name*="pw"]',
                'input[name*="pass"]',
                'input.mb_password',
                'input#mb_password',
                'input[name="mb_password"]',
            ]
            
            found_password_selector = None
            for selector in possible_password_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    found_password_selector = selector
                    print(f"[로그인] 비밀번호 필드 찾음: {selector}")
                    break
                except:
                    continue
            
            if not found_password_selector:
                raise Exception(f"비밀번호 입력 필드를 찾을 수 없습니다. 시도한 선택자: {possible_password_selectors}")
            
            password_selector = found_password_selector
            
            # 필드를 클릭해서 포커스 주기
            await self.page.click(password_selector)
            await self.random_delay(0.3, 0.5)
            
            # 기존 내용 지우고 입력
            await self.page.fill(password_selector, '')
            await self.page.type(password_selector, self.config['password'], delay=100)
            print("[로그인] 비밀번호 입력 완료")
            await self.random_delay(0.5, 1.0)
            
            # 로그인 버튼 클릭 - 여러 선택자 시도
            login_button_selector = self.config.get('login_button_selector', 'button[type="submit"]')
            print(f"[로그인] 로그인 버튼 찾는 중: {login_button_selector}")
            
            # 여러 선택자 시도
            possible_button_selectors = [
                login_button_selector,
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("로그인")',
                'button:has-text("Login")',
                'input[value*="로그인"]',
                'input[value*="Login"]',
                'button.btn_login',
                'input.btn_login',
                'button#login',
                'input#login',
            ]
            
            found_button_selector = None
            for selector in possible_button_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    found_button_selector = selector
                    print(f"[로그인] 로그인 버튼 찾음: {selector}")
                    break
                except:
                    continue
            
            if not found_button_selector:
                raise Exception(f"로그인 버튼을 찾을 수 없습니다. 시도한 선택자: {possible_button_selectors}")
            
            await self.page.click(found_button_selector)
            print("[로그인] 로그인 버튼 클릭 완료")
            
            # 로그인 완료 대기
            await self.page.wait_for_load_state('networkidle')
            await self.random_delay(2, 4)
            
            print("[로그인] 로그인 완료")
            return True
            
        except Exception as e:
            print(f"[오류] 로그인 실패: {e}")
            # 스크린샷 저장 (디버깅용)
            await self.page.screenshot(path='login_error.png')
            print("[디버깅] 오류 스크린샷 저장: login_error.png")
            return False
    
    async def get_post_links(self) -> list:
        """게시판에서 게시글 링크 목록 가져오기 (전체)"""
        print(f"[게시판] {self.config['board_url']} 접속 중...")
        await self.page.goto(self.config['board_url'], wait_until='networkidle')
        await self.random_delay(2, 4)
        
        # 게시글 링크 선택자 (실제 사이트에 맞게 수정 필요)
        post_link_selector = self.config.get('post_link_selector', 'a.post-link')
        
        try:
            # 게시글 링크들 가져오기
            links = await self.page.query_selector_all(post_link_selector)
            post_urls = []
            
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    # 상대 경로를 절대 경로로 변환
                    if href.startswith('/'):
                        base_url = self.config['url']
                        full_url = f"{base_url.rstrip('/')}{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        continue
                    
                    post_urls.append(full_url)
            
            # 중복 제거
            post_urls = list(set(post_urls))
            print(f"[게시판] {len(post_urls)}개의 게시글을 찾았습니다.")
            return post_urls[:self.config.get('max_posts', 10)]  # 최대 개수 제한
            
        except Exception as e:
            print(f"[오류] 게시글 링크 가져오기 실패: {e}")
            return []
    
    async def get_post_date_from_current_page(self) -> datetime:
        """현재 페이지에서 게시글 작성 시간 가져오기"""
        try:
            # 작성 시간을 찾는 여러 방법 시도 (oncapan.com 구조 반영)
            date_text = await self.page.evaluate("""
                () => {
                    // oncapan.com 작성 시간 선택자 (우선순위 1)
                    const oncapanSelectors = [
                        'strong.if_date',           // oncapan.com 작성일
                        '.if_date',                 // oncapan.com 작성일 (변형)
                        'strong[class*="date"]',    // 날짜 관련 strong 태그
                    ];
                    
                    for (const sel of oncapanSelectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            // 텍스트 내용에서 날짜/시간 추출
                            const text = el.textContent || el.innerText;
                            if (text) {
                                // "25-11-26 13:22" 형식 추출 (oncapan.com 형식)
                                const dateMatch = text.match(/\\d{2}-\\d{2}-\\d{2}\\s+\\d{1,2}:\\d{2}/);
                                if (dateMatch) {
                                    return dateMatch[0];
                                }
                                // "25-11-26" 형식 (시간 없음)
                                const dateMatch2 = text.match(/\\d{2}-\\d{2}-\\d{2}/);
                                if (dateMatch2) {
                                    return dateMatch2[0] + ' 00:00';  // 시간이 없으면 00:00으로 설정
                                }
                            }
                        }
                    }
                    
                    // 일반적인 작성 시간 선택자들
                    const selectors = [
                        '.date',
                        '.datetime',
                        '.write_date',
                        '[class*="date"]',
                        '[class*="time"]',
                        'time',
                        '[datetime]'
                    ];
                    
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            // datetime 속성 확인
                            if (el.getAttribute('datetime')) {
                                return el.getAttribute('datetime');
                            }
                            // 텍스트 내용 확인
                            const text = el.textContent || el.innerText;
                            if (text && text.trim()) {
                                return text.trim();
                            }
                        }
                    }
                    
                    // 모든 시간 관련 텍스트 찾기
                    const allText = document.body.innerText || document.body.textContent;
                    const datePattern = /\\d{2}-\\d{2}-\\d{2}\\s+\\d{1,2}:\\d{2}/;  // oncapan.com 형식 우선
                    const match = allText.match(datePattern);
                    if (match) {
                        return match[0];
                    }
                    
                    // 다른 형식도 시도
                    const datePattern2 = /\\d{4}[.-/]\\d{1,2}[.-/]\\d{1,2}/;
                    const match2 = allText.match(datePattern2);
                    if (match2) {
                        return match2[0];
                    }
                    
                    return null;
                }
            """)
            
            if not date_text:
                return None
            
            # 날짜 파싱 (oncapan.com 형식 우선)
            date_formats = [
                '%y-%m-%d %H:%M',           # oncapan.com 형식: "25-11-26 13:22" (우선순위 1)
                '%y-%m-%d %H:%M:%S',        # oncapan.com 형식: "25-11-26 13:22:00"
                '%Y-%m-%d %H:%M:%S',        # 표준 형식: "2025-11-26 13:22:00"
                '%Y-%m-%d %H:%M',           # 표준 형식: "2025-11-26 13:22"
                '%Y.%m.%d %H:%M',           # 점 구분: "2025.11.26 13:22"
                '%Y/%m/%d %H:%M',           # 슬래시 구분: "2025/11/26 13:22"
                '%y-%m-%d',                 # oncapan.com 날짜만: "25-11-26"
                '%Y-%m-%d',                 # 표준 날짜만: "2025-11-26"
            ]
            
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_text, fmt)
                    # 2자리 연도(YY)인 경우 2000년대로 변환
                    if fmt.startswith('%y'):
                        current_year = datetime.now().year
                        parsed_year = parsed_date.year
                        # 1900년대면 2000년대로 변환
                        if parsed_year < 2000:
                            parsed_date = parsed_date.replace(year=parsed_year + 100)
                    return parsed_date
                except:
                    continue
            
            return None
            
        except Exception as e:
            print(f"[경고] 현재 페이지에서 게시글 작성 시간을 가져오는 중 오류: {e}")
            return None
    
    async def get_post_date(self, post_url: str = None) -> datetime:
        """게시글의 작성 시간 가져오기 (현재 페이지 또는 지정된 URL)"""
        try:
            # post_url이 없으면 현재 페이지에서 가져오기
            if not post_url:
                return await self.get_post_date_from_current_page()
            
            # 게시글 페이지 접속
            await self.page.goto(post_url, wait_until='networkidle')
            await self.random_delay(1, 2)
            
            # 현재 페이지에서 작성 시간 가져오기
            return await self.get_post_date_from_current_page()
            
            # 작성 시간을 찾는 여러 방법 시도 (oncapan.com 구조 반영)
            date_text = await self.page.evaluate("""
                () => {
                    // oncapan.com 작성 시간 선택자 (우선순위 1)
                    const oncapanSelectors = [
                        'strong.if_date',           // oncapan.com 작성일
                        '.if_date',                 // oncapan.com 작성일 (변형)
                        'strong[class*="date"]',    // 날짜 관련 strong 태그
                    ];
                    
                    for (const sel of oncapanSelectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            // 텍스트 내용에서 날짜/시간 추출
                            const text = el.textContent || el.innerText;
                            if (text) {
                                // "25-11-26 13:22" 형식 추출 (oncapan.com 형식)
                                const dateMatch = text.match(/\\d{2}-\\d{2}-\\d{2}\\s+\\d{1,2}:\\d{2}/);
                                if (dateMatch) {
                                    return dateMatch[0];
                                }
                                // "25-11-26" 형식 (시간 없음)
                                const dateMatch2 = text.match(/\\d{2}-\\d{2}-\\d{2}/);
                                if (dateMatch2) {
                                    return dateMatch2[0] + ' 00:00';  // 시간이 없으면 00:00으로 설정
                                }
                            }
                        }
                    }
                    
                    // 일반적인 작성 시간 선택자들
                    const selectors = [
                        '.date',
                        '.datetime',
                        '.write_date',
                        '[class*="date"]',
                        '[class*="time"]',
                        'time',
                        '[datetime]'
                    ];
                    
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            // datetime 속성 확인
                            if (el.getAttribute('datetime')) {
                                return el.getAttribute('datetime');
                            }
                            // 텍스트 내용 확인
                            const text = el.textContent || el.innerText;
                            if (text && text.trim()) {
                                return text.trim();
                            }
                        }
                    }
                    
                    // 모든 시간 관련 텍스트 찾기
                    const allText = document.body.innerText || document.body.textContent;
                    const datePattern = /\\d{2}-\\d{2}-\\d{2}\\s+\\d{1,2}:\\d{2}/;  // oncapan.com 형식 우선
                    const match = allText.match(datePattern);
                    if (match) {
                        return match[0];
                    }
                    
                    // 다른 형식도 시도
                    const datePattern2 = /\\d{4}[.-/]\\d{1,2}[.-/]\\d{1,2}/;
                    const match2 = allText.match(datePattern2);
                    if (match2) {
                        return match2[0];
                    }
                    
                    return null;
                }
            """)
            
            if not date_text:
                return None
            
            # 날짜 파싱 시도 (oncapan.com 형식 포함)
            date_formats = [
                '%y-%m-%d %H:%M',           # oncapan.com 형식: "25-11-25 22:06" (우선순위 1)
                '%y-%m-%d %H:%M:%S',        # oncapan.com 형식: "25-11-25 22:06:00"
                '%Y-%m-%d %H:%M:%S',        # 표준 형식: "2025-11-25 22:06:00"
                '%Y-%m-%d %H:%M',           # 표준 형식: "2025-11-25 22:06"
                '%Y.%m.%d %H:%M',           # 점 구분: "2025.11.25 22:06"
                '%Y/%m/%d %H:%M',           # 슬래시 구분: "2025/11/25 22:06"
                '%y-%m-%d',                 # oncapan.com 날짜만: "25-11-25"
                '%Y-%m-%d',                 # 표준 날짜만: "2025-11-25"
                '%Y.%m.%d',                 # 점 구분 날짜만: "2025.11.25"
                '%Y/%m/%d',                 # 슬래시 구분 날짜만: "2025/11/25"
            ]
            
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_text, fmt)
                    # 2자리 연도(YY)인 경우 2000년대로 변환
                    if fmt.startswith('%y'):
                        # 현재 연도 기준으로 가까운 연도 선택
                        current_year = datetime.now().year
                        parsed_year = parsed_date.year
                        # 1900년대면 2000년대로 변환
                        if parsed_year < 2000:
                            parsed_date = parsed_date.replace(year=parsed_year + 100)
                        # 현재 연도보다 크면 과거 연도로 간주 (예: 25년이면 2025년)
                        elif parsed_year > current_year:
                            # 이미 올바른 연도일 수 있음
                            pass
                    return parsed_date
                except:
                    continue
            
            # 상대 시간 파싱 (예: "1시간 전", "2일 전")
            relative_patterns = [
                (r'(\d+)분\s*전', 'minutes'),
                (r'(\d+)시간\s*전', 'hours'),
                (r'(\d+)일\s*전', 'days'),
                (r'(\d+)주\s*전', 'weeks'),
            ]
            
            for pattern, unit in relative_patterns:
                match = re.search(pattern, date_text)
                if match:
                    value = int(match.group(1))
                    if unit == 'minutes':
                        return datetime.now() - timedelta(minutes=value)
                    elif unit == 'hours':
                        return datetime.now() - timedelta(hours=value)
                    elif unit == 'days':
                        return datetime.now() - timedelta(days=value)
                    elif unit == 'weeks':
                        return datetime.now() - timedelta(weeks=value)
            
            return None
            
        except Exception as e:
            print(f"[경고] 게시글 작성 시간을 가져오는 중 오류: {e}")
            return None
    
    async def is_post_within_24h(self, post_url: str) -> bool:
        """게시글이 24시간 이내인지 확인"""
        # 현재 URL 저장 (게시판 복귀용)
        current_url_before = self.page.url
        
        try:
            post_date = await self.get_post_date(post_url)
            
            if not post_date:
                print("[경고] 게시글 작성 시간을 확인할 수 없습니다. 댓글을 작성합니다.")
                # 게시판으로 복귀
                if self.config['board_url'] not in current_url_before:
                    # 원래 게시판이었으면 복귀
                    if 'board' in current_url_before.lower() or 'bbs' in current_url_before.lower():
                        try:
                            await self.page.goto(current_url_before, wait_until='networkidle', timeout=10000)
                        except:
                            await self.page.goto(self.config['board_url'], wait_until='networkidle', timeout=10000)
                    else:
                        await self.page.goto(self.config['board_url'], wait_until='networkidle', timeout=10000)
                else:
                    await self.page.goto(self.config['board_url'], wait_until='networkidle', timeout=10000)
                return True  # 시간을 확인할 수 없으면 작성
            
            now = datetime.now()
            time_diff = now - post_date
            
            # 게시판으로 복귀
            if self.config['board_url'] not in current_url_before:
                # 원래 게시판이었으면 복귀
                if 'board' in current_url_before.lower() or 'bbs' in current_url_before.lower():
                    try:
                        await self.page.goto(current_url_before, wait_until='networkidle', timeout=10000)
                    except:
                        await self.page.goto(self.config['board_url'], wait_until='networkidle', timeout=10000)
                else:
                    await self.page.goto(self.config['board_url'], wait_until='networkidle', timeout=10000)
            else:
                await self.page.goto(self.config['board_url'], wait_until='networkidle', timeout=10000)
            
            if time_diff <= timedelta(hours=24):
                print(f"[확인] 게시글 작성 시간: {post_date.strftime('%Y-%m-%d %H:%M')} ({(time_diff.total_seconds() / 3600):.1f}시간 전)")
                return True
            else:
                hours_ago = time_diff.total_seconds() / 3600
                print(f"[건너뛰기] 게시글이 24시간을 초과했습니다. ({hours_ago:.1f}시간 전, 작성 시간: {post_date.strftime('%Y-%m-%d %H:%M')})")
                return False
        except Exception as e:
            print(f"[경고] 시간 확인 중 오류: {e}. 게시판으로 복귀합니다.")
            # 오류 발생 시 게시판으로 복귀
            try:
                await self.page.goto(self.config['board_url'], wait_until='networkidle', timeout=10000)
            except:
                pass
            return True  # 오류 시 작성 허용
    
    async def get_next_post_link(self, processed_urls: set) -> str:
        """게시판에서 다음 게시글 링크 하나만 가져오기 (24시간 이내만)"""
        # 게시판이 이미 열려있는지 확인하고, 아니면 접속
        # 중요: 반드시 게시판 페이지에서만 게시글을 선택해야 함
        current_url = self.page.url
        if self.config['board_url'] not in current_url:
            print(f"[게시판] 현재 게시판이 아닙니다. 게시판으로 이동 중... (현재 URL: {current_url})")
            await self.page.goto(self.config['board_url'], wait_until='networkidle')
            await self.random_delay(2, 4)
        else:
            print(f"[게시판] 게시판 페이지 확인됨: {current_url}")
        
        # 페이지가 완전히 로드될 때까지 대기
        await self.page.wait_for_load_state('networkidle')
        await self.random_delay(1, 2)
        
        try:
            print("[게시판] 게시글 링크를 찾는 중... (24시간 이내 게시글만 선택)")
            
            # 방법 1: JavaScript로 모든 링크 가져오기 (가장 확실한 방법)
            all_urls = []
            
            # JavaScript를 사용해서 게시글 링크와 시간 정보를 함께 가져오기
            posts_data = await self.page.evaluate("""
                () => {
                    const posts = [];
                    // 게시글 목록 li 태그 찾기
                    const listItems = document.querySelectorAll('.list_01 li, #bo_list li, li.bo_notice, li:not(.bo_notice)');
                    
                    for (const li of listItems) {
                        // 게시글 링크 찾기
                        const link = li.querySelector('a[href*="/bbs/free/"]');
                        if (!link) continue;
                        
                        const href = link.href;
                        // 게시글 ID 패턴 확인
                        if (!/\\/bbs\\/free\\/\\d+/.test(href)) continue;
                        
                        // 시간 정보 찾기 (여러 패턴 시도)
                        let timeText = null;
                        
                        // 방법 1: float: right 스타일의 div에서 찾기
                        const timeDivs = li.querySelectorAll('div[style*="float: right"], div[style*="float:right"]');
                        for (const div of timeDivs) {
                            const text = div.textContent.trim();
                            // 시간 형식 확인: "16:25" 또는 "11-21" 형식
                            if (/\\d{1,2}:\\d{2}/.test(text) || /\\d{2}-\\d{2}/.test(text)) {
                                timeText = text;
                                break;
                            }
                        }
                        
                        // 방법 2: li 내부의 모든 텍스트에서 시간 패턴 찾기
                        if (!timeText) {
                            const liText = li.textContent || li.innerText;
                            // "16:25" 형식 찾기
                            const timeMatch = liText.match(/\\d{1,2}:\\d{2}/);
                            if (timeMatch) {
                                timeText = timeMatch[0];
                            } else {
                                // "11-21" 형식 찾기
                                const dateMatch = liText.match(/\\d{2}-\\d{2}/);
                                if (dateMatch) {
                                    timeText = dateMatch[0];
                                }
                            }
                        }
                        
                        posts.push({
                            href: href.split('?')[0].split('#')[0],  // 쿼리 파라미터 제거
                            timeText: timeText
                        });
                    }
                    
                    return posts;
                }
            """)
            
            print(f"[게시판] JavaScript로 {len(posts_data)}개의 게시글을 발견했습니다.")
            
            # 게시글 링크와 시간 정보를 함께 저장
            posts_with_time = []
            for post_data in posts_data:
                href = post_data.get('href', '')
                time_text = post_data.get('timeText', '')
                
                if not href:
                    continue
                
                # 게시글 링크 패턴 확인
                if re.search(r'/bbs/free/\d+', href):
                    if href not in processed_urls:
                        posts_with_time.append({
                            'url': href,
                            'time': time_text
                        })
            
            # 시간 정보로 24시간 이내 게시글 필터링
            now = datetime.now()
            all_urls = []
            
            for post_info in posts_with_time:
                url = post_info['url']
                time_text = post_info['time']
                
                if not time_text:
                    # 시간 정보가 없으면 일단 추가 (나중에 게시글 페이지에서 확인)
                    all_urls.append(url)
                    continue
                
                # 시간 파싱
                is_within_24h = False
                
                try:
                    # 형식 1: "16:25" (오늘 시간)
                    if re.match(r'^\d{1,2}:\d{2}$', time_text):
                        hour, minute = map(int, time_text.split(':'))
                        post_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        
                        # 오늘 시간이면 그대로 사용
                        # 어제 시간일 수도 있으므로 24시간 범위 확인
                        time_diff = now - post_time
                        if time_diff.total_seconds() < 0:
                            # 미래 시간이면 어제로 간주
                            post_time = post_time - timedelta(days=1)
                            time_diff = now - post_time
                        
                        is_within_24h = time_diff.total_seconds() <= 24 * 3600
                    
                    # 형식 2: "11-21" (월-일 형식)
                    elif re.match(r'^\d{2}-\d{2}$', time_text):
                        month, day = map(int, time_text.split('-'))
                        current_year = now.year
                        post_time = datetime(current_year, month, day, 0, 0, 0)
                        
                        # 올해가 아니면 작년으로 간주
                        if post_time > now:
                            post_time = datetime(current_year - 1, month, day, 0, 0, 0)
                        
                        time_diff = now - post_time
                        is_within_24h = time_diff.total_seconds() <= 24 * 3600
                    
                    # 형식 3: "25-11-26 13:22" (oncapan.com 형식)
                    elif re.match(r'^\d{2}-\d{2}-\d{2}\s+\d{1,2}:\d{2}', time_text):
                        try:
                            post_time = datetime.strptime(time_text, '%y-%m-%d %H:%M')
                            # 2자리 연도 처리
                            if post_time.year < 2000:
                                post_time = post_time.replace(year=post_time.year + 100)
                            time_diff = now - post_time
                            is_within_24h = time_diff.total_seconds() <= 24 * 3600
                        except:
                            # 파싱 실패 시 추가 (나중에 확인)
                            all_urls.append(url)
                            continue
                    
                    if is_within_24h:
                        all_urls.append(url)
                        print(f"[필터링] 24시간 이내 게시글 발견: {url} (시간: {time_text})")
                    else:
                        print(f"[필터링] 24시간 초과 게시글 제외: {url} (시간: {time_text})")
                
                except Exception as e:
                    # 시간 파싱 실패 시 일단 추가 (나중에 게시글 페이지에서 확인)
                    print(f"[경고] 시간 파싱 실패 ({time_text}): {e}, 게시글 페이지에서 재확인 예정")
                    all_urls.append(url)
            
            # 중복 제거 (순서 유지)
            all_urls = list(dict.fromkeys(all_urls))
            
            if not all_urls:
                # 방법 2: CSS 선택자로 다시 시도
                print("[게시판] CSS 선택자로 다시 시도 중...")
                post_link_selector = self.config.get('post_link_selector', 'a[href*="/bbs/free/"]')
                
                try:
                    links = await self.page.query_selector_all(post_link_selector)
                    print(f"[게시판] CSS 선택자로 {len(links)}개의 링크를 발견했습니다.")
                    
                    for link in links:
                        href = await link.get_attribute('href')
                        if not href:
                            continue
                        
                        # 절대 URL로 변환
                        if href.startswith('/'):
                            base_url = self.config['url']
                            full_url = f"{base_url.rstrip('/')}{href}"
                        elif href.startswith('http'):
                            full_url = href
                        else:
                            continue
                        
                        # 게시글 링크 패턴 확인
                        if post_pattern.search(full_url):
                            clean_url = full_url.split('?')[0].split('#')[0]
                            if clean_url not in processed_urls:
                                all_urls.append(clean_url)
                    
                    # 중복 제거
                    all_urls = list(dict.fromkeys(all_urls))
                except Exception as e:
                    print(f"[게시판] CSS 선택자 시도 실패: {e}")
            
            if not all_urls:
                # 디버깅: 페이지 정보 출력
                print("[게시판] 게시글 링크를 찾을 수 없습니다.")
                print("[디버깅] 페이지 분석 중...")
                
                # 페이지 제목 확인
                page_title = await self.page.title()
                print(f"[디버깅] 페이지 제목: {page_title}")
                
                # 현재 URL 확인
                print(f"[디버깅] 현재 URL: {self.page.url}")
                
                # 발견된 게시글 샘플 출력
                sample_posts = [post['href'] for post in posts_data[:20] if post.get('href')]
                print(f"[디버깅] 발견된 게시글 샘플 (처음 10개):")
                for i, post_url in enumerate(sample_posts[:10], 1):
                    print(f"  {i}. {post_url}")
                
                # 스크린샷 저장
                await self.page.screenshot(path='board_debug.png')
                print("[디버깅] 스크린샷 저장: board_debug.png")
                
                return None
            
            print(f"[게시판] {len(all_urls)}개의 게시글 링크를 찾았습니다.")
            
            # 순서 선택 (기본값: 랜덤)
            order = self.config.get('post_order', 'random')
            
            # 24시간 이내 게시글만 필터링
            valid_urls = []
            # 랜덤 모드일 때는 더 많은 게시글을 확인 (전체 범위에서 랜덤 선택)
            if order == 'random':
                max_check = min(50, len(all_urls))  # 랜덤 모드: 최대 50개 확인
            else:
                max_check = min(20, len(all_urls))  # 최신순/오래된순: 최대 20개 확인 (성능 고려)
            
            print(f"[게시판] {max_check}개의 게시글을 확인 중... (모드: {order})")
            
            for url in all_urls[:max_check]:
                # 이미 댓글을 작성한 게시글은 건너뛰기
                if url in self.commented_posts:
                    print(f"[중복방지] 이미 댓글 작성한 게시글 건너뛰기: {url}")
                    continue
                
                # 이번 실행에서 이미 처리한 게시글은 건너뛰기
                if url in processed_urls:
                    print(f"[중복방지] 이번 실행에서 이미 처리한 게시글 건너뛰기: {url}")
                    continue
                
                # 목록 페이지에서 이미 24시간 이내 게시글만 필터링했으므로
                # 여기서는 중복 확인만 수행
                valid_urls.append(url)
                
                # 최신순 모드에서는 첫 번째 유효한 게시글을 찾으면 중단
                if order == 'latest':
                    break
            
            if not valid_urls:
                print("[게시판] 24시간 이내 게시글이 없습니다.")
                return None
            
            # 게시글 선택
            if order == 'random':
                selected_url = random.choice(valid_urls)
                print(f"[게시판] 랜덤으로 게시글 선택: {selected_url} (후보 {len(valid_urls)}개 중)")
            elif order == 'oldest':
                # 가장 오래된 게시글 선택 (리스트의 마지막)
                selected_url = valid_urls[-1]
                print(f"[게시판] 오래된 순으로 게시글 선택: {selected_url} (후보 {len(valid_urls)}개 중)")
            else:  # latest
                selected_url = valid_urls[0]
                print(f"[게시판] 최신순으로 게시글 선택: {selected_url}")
            
            return selected_url
            
        except Exception as e:
            print(f"[오류] 다음 게시글 링크 가져오기 실패: {e}")
            import traceback
            traceback.print_exc()
            # 스크린샷 저장
            try:
                await self.page.screenshot(path='error_debug.png')
                print("[디버깅] 오류 스크린샷 저장: error_debug.png")
            except:
                pass
            return None
    
    # Gemini 함수 제거됨 - OpenAI만 사용
    
    async def get_post_title(self) -> str:
        """게시글 제목 가져오기"""
        try:
            # 게시글 제목 선택자들 (oncapan.com 구조 반영)
            title_selectors = [
                'span.bo_v_tit',            # oncapan.com 제목 (우선순위 1)
                '#bo_v .bo_v_tit',          # oncapan.com 제목 (우선순위 2)
                '#bo_v_atc .bo_v_tit',      # 그누보드 제목
                '#bo_v_title .bo_v_tit',    # 그누보드 제목 변형
                'h2#bo_v_title .bo_v_tit',  # 그누보드 제목 변형 2
                '.view_title',              # 일반적인 제목
                '.board_title',             # 게시판 제목
                'h1',                       # HTML5 h1 태그
                'h2',                       # HTML5 h2 태그
                '.title',                   # title 클래스
                '#title',                   # title ID
                '[class*="title"]',         # title이 포함된 클래스
                '[id*="title"]',            # title이 포함된 ID
                '.subject',                 # subject 클래스
                '#subject',                 # subject ID
            ]
            
            title_text = ""
            
            for selector in title_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        title_text = await element.inner_text()
                        if title_text and len(title_text.strip()) > 0:
                            title_text = title_text.strip()
                            print(f"[제목] ✅ 제목 찾음: {title_text[:50]}...")
                            break
                except Exception:
                    continue
            
            # JavaScript로 직접 제목 찾기 (oncapan.com 구조 반영)
            if not title_text:
                title_text = await self.page.evaluate("""
                    () => {
                        const selectors = [
                            'span.bo_v_tit',           // oncapan.com 제목 (우선순위 1)
                            '#bo_v .bo_v_tit',         // oncapan.com 제목 (우선순위 2)
                            '#bo_v_atc .bo_v_tit',     // 그누보드 제목
                            '#bo_v_title .bo_v_tit',   // 그누보드 제목 변형
                            'h2#bo_v_title .bo_v_tit', // 그누보드 제목 변형 2
                            '.view_title',
                            '.board_title',
                            'h1',
                            'h2',
                            '.title',
                            '#title',
                            '[class*="title"]',
                            '[id*="title"]',
                            '.subject',
                            '#subject'
                        ];
                        
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el) {
                                const text = (el.innerText || el.textContent || '').trim();
                                if (text && text.length > 0) {
                                    return text;
                                }
                            }
                        }
                        return '';
                    }
                """)
                
                if title_text:
                    print(f"[제목] ✅ JavaScript로 제목 찾음: {title_text[:50]}...")
            
            return title_text.strip() if title_text else ""
            
        except Exception as e:
            print(f"[경고] 게시글 제목을 가져오는 중 오류: {e}")
            return ""
    
    async def get_post_content(self) -> str:
        """게시글 본문 내용 가져오기"""
        try:
            print("[본문] 본문 추출 시작...")
            
            # 게시글 본문 선택자 (oncapan.com 및 일반적인 선택자들)
            content_selectors = [
                '#bo_v_con',           # 그누보드 기본 본문 영역
                '.view_content',       # 일반적인 본문 영역
                '.board_content',      # 게시판 본문
                '.wr_content',         # 그누보드 본문
                '#wr_content',         # 그누보드 본문 ID
                '.content',             # 일반적인 content 클래스
                'article',              # HTML5 article 태그
                '[class*="content"]',  # content가 포함된 클래스
                '[id*="content"]',      # content가 포함된 ID
                '[class*="view"]',      # view가 포함된 클래스
                '[id*="view"]',         # view가 포함된 ID
            ]
            
            content_text = ""
            used_selector = None
            
            for selector in content_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        content_text = await element.inner_text()
                        if content_text and len(content_text.strip()) > 10:
                            used_selector = selector
                            print(f"[본문] ✅ 선택자 성공: {selector}")
                            print(f"[본문] 읽은 본문 길이: {len(content_text)}자")
                            print(f"[본문] 본문 미리보기: {content_text[:100]}...")
                            break
                except Exception as e:
                    print(f"[본문] 선택자 {selector} 시도 실패: {e}")
                    continue
            
            # JavaScript로 직접 본문 찾기 (CSS 선택자 실패 시)
            if not content_text or len(content_text.strip()) < 10:
                print("[본문] CSS 선택자 실패, JavaScript로 본문 찾기 시도...")
                content_text = await self.page.evaluate("""
                    () => {
                        // 그누보드 및 일반적인 본문 영역 찾기
                        const selectors = [
                            '#bo_v_con',
                            '.view_content',
                            '.board_content',
                            '.wr_content',
                            '#wr_content',
                            'article',
                            '[class*="content"]',
                            '[id*="content"]',
                            '[class*="view"]',
                            '[id*="view"]'
                        ];
                        
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el) {
                                const text = el.innerText || el.textContent;
                                if (text && text.trim().length > 10) {
                                    console.log('본문 찾음:', sel, '길이:', text.trim().length);
                                    return text.trim();
                                }
                            }
                        }
                        
                        // 본문이 없으면 body에서 긴 텍스트 찾기
                        const bodyText = document.body.innerText || document.body.textContent;
                        if (bodyText && bodyText.trim().length > 10) {
                            console.log('Body에서 본문 추출, 길이:', bodyText.trim().length);
                            return bodyText.trim();
                        }
                        return '';
                    }
                """)
                
                if content_text and len(content_text.strip()) > 10:
                    print(f"[본문] ✅ JavaScript로 본문 찾기 성공")
                    print(f"[본문] 읽은 본문 길이: {len(content_text)}자")
                    print(f"[본문] 본문 미리보기: {content_text[:100]}...")
            
            # 본문 정리 (너무 길면 앞부분만)
            if content_text:
                content_text = content_text.strip()
                original_length = len(content_text)
                
                # 최대 500자까지만 (AI 프롬프트에 전달)
                if len(content_text) > 500:
                    content_text = content_text[:500] + "..."
                    print(f"[본문] 본문 길이 제한: {original_length}자 → 500자")
                
                print(f"[본문] ✅ 최종 본문 길이: {len(content_text)}자")
                if used_selector:
                    print(f"[본문] 사용된 선택자: {used_selector}")
            else:
                print("[본문] ❌ 본문을 찾을 수 없습니다!")
                # 디버깅: 페이지 구조 확인
                page_info = await self.page.evaluate("""
                    () => {
                        return {
                            title: document.title,
                            url: window.location.href,
                            bodyTextLength: (document.body.innerText || document.body.textContent || '').trim().length,
                            hasBoVCon: !!document.querySelector('#bo_v_con'),
                            hasViewContent: !!document.querySelector('.view_content'),
                            hasWrContent: !!document.querySelector('.wr_content, #wr_content')
                        };
                    }
                """)
                print(f"[본문] 페이지 정보: {page_info}")
            
            return content_text
            
        except Exception as e:
            print(f"[경고] 게시글 본문을 가져오는 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def analyze_post_emotion(self, post_content: str, post_title: str = "") -> dict:
        """게시글 감정/상황 분석 (단순 휴리스틱)"""
        combined_text = f"{post_title}\n{post_content}".lower()
        
        emotion_keywords = {
            'joy': ['대박', '성공', '축하', '행복', '웃', '기쁘', '따았', '수익', '이겼', '복구'],
            'sadness': ['망했', '후회', '슬프', '지쳤', '박살', '손실', '털렸', '아쉽', '0텅장', '텅장'],
            'anger': ['빡치', '짜증', '화나', '열받', '미치겠', '싫다'],
            'anxiety': ['불안', '무섭', '걱정', '떨리', '조심', '긴장'],
            'complaint': ['신고', '먹튀', '문제', '크레임', '사기', '제보', '주의']
        }
        
        question_keywords = ['?', '어디', '어떻게', '뭐', '무엇', '언제', '왜', '몇', '알려', '추천', '찾']
        celebration_keywords = ['이벤트', '축하', '나눔', '뿌리', '선물', '페이백']
        
        scores = {k: 0 for k in emotion_keywords.keys()}
        for emotion, keywords in emotion_keywords.items():
            for word in keywords:
                if word in combined_text:
                    scores[emotion] += 1
        
        dominant_emotion = max(scores, key=scores.get) if scores else 'neutral'
        intensity = min(1.0, scores.get(dominant_emotion, 0) / 3) if scores else 0.0
        
        is_question = any(word in combined_text for word in question_keywords)
        is_celebration = any(word in combined_text for word in celebration_keywords)
        is_complaint = scores.get('complaint', 0) > 0
        
        return {
            'emotion': dominant_emotion if scores.get(dominant_emotion, 0) > 0 else 'neutral',
            'intensity': round(intensity, 2),
            'is_question': is_question,
            'needs_answer': is_question,
            'is_celebration': is_celebration or dominant_emotion == 'joy',
            'is_complaint': is_complaint,
            'raw_scores': scores
        }
    
    def classify_post_type(self, post_content: str, post_title: str = "") -> str:
        """게시글 유형 분류"""
        combined_text = f"{post_title}\n{post_content}"
        lower_text = combined_text.lower()
        
        if any(word in lower_text for word in ['?', '어디', '어떻게', '뭐', '무엇', '언제', '왜', '도와', '알려']):
            return 'question'
        if any(word in lower_text for word in ['후기', '정보', '추천', '정리', '공유']):
            return 'information'
        if any(word in lower_text for word in ['축하', '이벤트', '나눔', '페이백', '선물']):
            return 'event'
        if any(word in lower_text for word in ['힘들', '지쳤', '행복', '기쁘', '슬프', '화나', '눈물']):
            return 'emotion'
        return 'casual'
    
    def build_post_context_text(self, emotion_data: dict, post_type: str, temporal_context: dict = None, max_length: int = 10, community_terms: list = None) -> str:
        """프롬프트에 사용할 게시글 감정/유형 정보 생성"""
        if not emotion_data:
            return ""
        
        emotion_label_map = {
            'joy': '기쁨/축하',
            'sadness': '슬픔/후회',
            'anger': '분노/불만',
            'anxiety': '불안/긴장',
            'complaint': '신고/제보',
            'neutral': '중립'
        }
        emotion_label = emotion_label_map.get(emotion_data.get('emotion', 'neutral'), '중립')
        
        context_lines = ["\n\n🧠 게시글 감정/상황 분석:"]
        context_lines.append(f"- 감정 상태: {emotion_label} (강도 {int(emotion_data.get('intensity', 0)*100)}%)")
        context_lines.append(f"- 게시글 유형: {post_type}")
        
        if emotion_data.get('is_question'):
            context_lines.append("- 게시글이 질문을 포함하므로, 가능한 경우 짧게 답변하거나 공감하세요")
        if emotion_data.get('is_celebration'):
            context_lines.append("- 축하/행복한 분위기이므로, 이를 함께 기뻐하는 톤이 자연스럽습니다")
        if emotion_data.get('is_complaint'):
            context_lines.append("- 불만/신고 성격이 있으므로 진지하게 공감하거나 주의 메시지를 덧붙이세요")
        
        if temporal_context:
            time_label = temporal_context.get('time_greeting')
            if time_label:
                context_lines.append(f"- 현재 작성 시간: {time_label} (시간대 고려)")
            if temporal_context.get('is_weekend'):
                context_lines.append("- 주말 분위기이므로 가볍고 편한 톤이 자연스럽습니다")
        
        if community_terms:
            context_lines.append(f"- 커뮤니티 특수 용어: {', '.join(community_terms)} (자연스럽게 사용할 수 있으면 활용)")
        
        context_lines.append(f"- 댓글 길이는 최대 {max_length}글자 이내로 유지하세요 (기본 10글자)")
        context_lines.append("- 감정선과 게시글 톤을 자연스럽게 이어가세요")
        
        return "\n".join(context_lines) + "\n"
    
    def get_temporal_context(self, post_date: datetime = None) -> dict:
        """게시글 작성 시간 기반 맥락"""
        if not post_date:
            return {}
        
        hour = post_date.hour
        if 0 <= hour < 5:
            time_greeting = '심야 시간'
        elif 5 <= hour < 12:
            time_greeting = '아침 시간'
        elif 12 <= hour < 18:
            time_greeting = '오후 시간'
        else:
            time_greeting = '저녁 시간'
        
        return {
            'hour': hour,
            'day_of_week': post_date.weekday(),
            'is_night': hour >= 22 or hour < 6,
            'is_weekend': post_date.weekday() >= 5,
            'time_greeting': time_greeting
        }
    
    def get_optimal_comment_length(self, existing_comments: list, base_limit: int = 10) -> int:
        """기존 댓글 길이에 따라 최대 길이 조정 (최대 15자)"""
        if not existing_comments:
            return base_limit
        
        valid_comments = [len(c.strip()) for c in existing_comments if c and len(c.strip()) >= 2]
        if not valid_comments:
            return base_limit
        
        avg_length = sum(valid_comments) / len(valid_comments)
        if avg_length <= base_limit:
            return base_limit
        
        adjusted = min(15, int(round(avg_length * 1.1)))
        return max(base_limit, adjusted)
    
    def analyze_comment_flow(self, existing_comments: list) -> dict:
        """댓글 흐름/중복도 분석"""
        from difflib import SequenceMatcher
        
        recent = [c for c in (existing_comments or []) if c and len(c.strip()) >= 2][-5:]
        if not recent:
            return {
                'needs_diversity': False,
                'average_similarity': 0.0,
                'recent_theme': ''
            }
        
        similarities = []
        for i in range(len(recent) - 1):
            a, b = recent[i], recent[i + 1]
            ratio = SequenceMatcher(None, a, b).ratio()
            similarities.append(ratio)
        
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        
        return {
            'needs_diversity': avg_similarity >= 0.7,
            'average_similarity': round(avg_similarity, 2),
            'recent_theme': 'repetitive' if avg_similarity >= 0.7 else 'varied'
        }
    
    def is_comment_too_similar(self, comment: str, existing_comments: list, threshold: float = 0.75) -> bool:
        """댓글이 기존 댓글과 지나치게 유사한지 확인"""
        if not comment or not existing_comments:
            return False
        
        from difflib import SequenceMatcher
        recent = [c for c in existing_comments if c and len(c.strip()) >= 2][-8:]
        for prev in recent:
            ratio = SequenceMatcher(None, comment, prev).ratio()
            if ratio >= threshold:
                return True
        return False
    
    def extract_community_terms(self, text: str) -> list:
        """도박 커뮤니티 특수 용어 감지"""
        if not text:
            return []
        
        terms = [
            '노돌', '노발', '댓노', '포거래', '텅장', '역배', '정배', '환전', '먹튀', '페이백',
            '야식쿱', '깡', '픽', '슬롯', '바카라', '포바', '부주력', '몰빵', '똥배', '정형'
        ]
        found = []
        lower_text = text.lower()
        for term in terms:
            if term.lower() in lower_text:
                found.append(term)
        return found[:5]
    
    def extract_common_words_from_comments(self, existing_comments: list) -> list:
        """기존 댓글들에서 자주 사용되는 핵심 단어/표현 추출"""
        if not existing_comments or len(existing_comments) == 0:
            return []
        
        import re
        from collections import Counter
        
        # 모든 댓글을 합쳐서 단어 추출
        all_text = " ".join(existing_comments[:10])
        
        # 특수 기호 제거하지 않고 단어 추출 (한글, 영문, 숫자, 특수기호 포함)
        # 2-5글자 단어 추출
        words = re.findall(r'[가-힣]{2,5}|[a-zA-Z]{2,5}', all_text)
        
        # 빈도수 계산
        word_counts = Counter(words)
        
        # 2번 이상 나타나는 단어만 선택
        common_words = [word for word, count in word_counts.most_common(10) if count >= 2]
        
        # 의미 있는 단어만 필터링 (너무 일반적인 단어 제외)
        meaningful_words = []
        stop_words = ['그리고', '그런데', '하지만', '그래서', '그러나', '그럼', '그래', '이거', '저거', '그거']
        
        for word in common_words:
            if word not in stop_words and len(word) >= 2:
                meaningful_words.append(word)
        
        return meaningful_words[:5]  # 상위 5개만 반환
    
    async def log_ai_comment_process(self, post_content: str, post_title: str, existing_comments: list, 
                                     prompt: str, ai_response: str, reason: str, final_comment: str):
        """AI 댓글 생성 과정을 메모장 파일에 기록"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            log_file = 'AI_댓글_생성_로그.txt'
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"시간: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                
                f.write("【게시글 제목】\n")
                f.write(f"{post_title or '(제목 없음)'}\n\n")
                
                f.write("【게시글 본문】\n")
                f.write(f"{post_content[:500]}\n\n")
                
                f.write("【기존 댓글들】\n")
                if existing_comments and len(existing_comments) > 0:
                    for i, comment in enumerate(existing_comments[:10], 1):
                        f.write(f"{i}. {comment}\n")
                else:
                    f.write("(댓글 없음)\n")
                f.write("\n")
                
                f.write("【AI가 받은 프롬프트】\n")
                f.write(f"{prompt[:1000]}...\n\n")
                
                f.write("【AI 원본 응답】\n")
                f.write(f"{ai_response}\n\n")
                
                f.write("【AI가 댓글을 이렇게 쓴 이유】\n")
                f.write(f"{reason}\n\n")
                
                f.write("【최종 댓글】\n")
                f.write(f"{final_comment}\n\n")
                
                f.write("=" * 80 + "\n\n")
            
            print(f"[로그] AI 댓글 생성 과정이 '{log_file}' 파일에 기록되었습니다.")
        except Exception as e:
            print(f"[경고] 로그 기록 실패: {e}")
    
    async def log_final_comment(self, post_content: str, post_title: str, existing_comments: list, 
                                ai_original_comment: str, final_comment: str, changes: list):
        """최종 댓글 작성 직전에 기록 (후처리 후 실제 작성되는 댓글)"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            log_file = 'AI_댓글_생성_로그.txt'
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"⏰ 최종 댓글 작성 시각: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                
                f.write("【게시글 제목】\n")
                f.write(f"{post_title or '(제목 없음)'}\n\n")
                
                f.write("【게시글 본문】\n")
                f.write(f"{post_content[:500]}\n\n")
                
                f.write("【기존 댓글들】\n")
                if existing_comments and len(existing_comments) > 0:
                    for i, comment in enumerate(existing_comments[:10], 1):
                        f.write(f"{i}. {comment}\n")
                else:
                    f.write("(댓글 없음)\n")
                f.write("\n")
                
                f.write("【AI가 생성한 원본 댓글】\n")
                f.write(f"{ai_original_comment}\n\n")
                
                # 댓글 변경 이력 기록
                f.write("【댓글 변경 이력】\n")
                changed = False
                for step_name, before, after in changes:
                    if after and before != after:
                        f.write(f"- {step_name}: '{before}' → '{after}'\n")
                        changed = True
                if not changed:
                    f.write("(변경 없음)\n")
                f.write("\n")
                
                f.write("【⚠️ 실제로 작성된 최종 댓글】\n")
                f.write(f"{final_comment}\n\n")
                
                if ai_original_comment != final_comment:
                    f.write("【⚠️ 주의】\n")
                    f.write(f"AI가 생성한 댓글('{ai_original_comment}')이 후처리 과정에서 '{final_comment}'로 변경되었습니다.\n")
                    f.write("변경 이유는 위 '댓글 변경 이력'을 확인하세요.\n\n")
                
                f.write("=" * 80 + "\n\n")
            
            if ai_original_comment != final_comment:
                print(f"[경고] ⚠️ AI가 생성한 댓글이 변경되었습니다!")
                print(f"[경고] 원본: '{ai_original_comment}'")
                print(f"[경고] 최종: '{final_comment}'")
            print(f"[로그] 최종 댓글이 '{log_file}' 파일에 기록되었습니다: {final_comment}")
        except Exception as e:
            print(f"[경고] 최종 댓글 로그 기록 실패: {e}")
    
    def log_comment_feedback(self, post_title: str, post_content: str, existing_comments: list, comment_text: str):
        """작성된 댓글을 학습용 피드백 로그로 저장"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                '제목': post_title or '',
                '본문': (post_content or '')[:500],
                '기존_댓글': existing_comments[:5] if existing_comments else [],
                '작성_댓글': comment_text
            }
            log_file = 'ai_feedback_log.json'
            data = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = []
            data.append(log_entry)
            # 최근 200개만 유지
            data = data[-200:]
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("[학습] 댓글 피드백 로그에 기록했습니다.")
        except Exception as e:
            print(f"[경고] 피드백 로그 저장 실패: {e}")
    
    def analyze_comment_style(self, existing_comments: list) -> dict:
        """기존 댓글들의 말투 스타일 분석 (더 정확하게)"""
        if not existing_comments or len(existing_comments) == 0:
            return {
                'ending': '',  # 기본값 없음 (강제하지 않음)
                'tone': 'casual',  # casual, formal
                'has_emoji': False,
                'has_tilde': False,
                'has_exclamation': False,
                'has_ㅠ': False,
                'emoji_usage_rate': 0.0,
                'avg_length': 5,
                'common_endings': []
            }
        
        endings = []
        has_emoji_count = 0
        has_tilde_count = 0
        has_exclamation_count = 0
        has_ㅠ_count = 0
        total_length = 0
        
        for comment in existing_comments[:15]:  # 최대 15개 분석 (더 많은 샘플)
            if not comment or len(comment.strip()) < 2:
                continue
            
            comment = comment.strip()
            total_length += len(comment)
            
            # 특수 기호 체크 (더 정확하게)
            if '~' in comment:
                has_tilde_count += 1
                has_emoji_count += 1
            if '!' in comment:
                has_exclamation_count += 1
                has_emoji_count += 1
            if 'ㅠ' in comment or 'ㅜ' in comment:
                has_ㅠ_count += 1
                has_emoji_count += 1
            
            # 끝말 분석 (더 정확하게)
            comment_clean = comment.rstrip('~!?ㅠㅜㅎㅋ')
            if comment_clean.endswith('요'):
                endings.append('요')
            elif comment_clean.endswith('네요'):
                endings.append('네요')
            elif comment_clean.endswith('어요'):
                endings.append('어요')
            elif comment_clean.endswith('해요'):
                endings.append('해요')
            elif comment_clean.endswith('되요'):
                endings.append('되요')
            elif comment_clean.endswith('다요'):
                endings.append('다요')
            elif comment_clean.endswith('세요'):
                endings.append('세요')
            elif comment_clean.endswith('까요'):
                endings.append('까요')
            elif comment_clean.endswith('나요'):
                endings.append('나요')
            elif comment_clean.endswith('지요'):
                endings.append('지요')
            elif comment_clean.endswith('죠'):
                endings.append('죠')
            elif comment_clean.endswith('다'):
                endings.append('다')
            elif comment_clean.endswith('어'):
                endings.append('어')
            elif comment_clean.endswith('해'):
                endings.append('해')
            elif comment_clean.endswith('야'):
                endings.append('야')
            # 끝말이 없는 경우도 허용 (예: "냠냠꾼!", "천포 냠냠~~")
            # 기본값을 강제하지 않음
        
        # 가장 많이 사용된 끝말들 (상위 3개)
        from collections import Counter
        ending_counts = Counter(endings)
        common_endings = [ending for ending, count in ending_counts.most_common(3)]
        
        if endings:
            most_common_ending = ending_counts.most_common(1)[0][0]
        else:
            most_common_ending = ''  # 끝말이 없으면 빈 문자열 (강제하지 않음)
        
        total_comments = len([c for c in existing_comments[:15] if c and len(c.strip()) >= 2])
        avg_length = total_length // total_comments if total_comments > 0 else 5
        emoji_usage_rate = has_emoji_count / total_comments if total_comments > 0 else 0.0
        has_emoji = emoji_usage_rate > 0.2  # 20% 이상이면 특수 기호 사용
        
        return {
            'ending': most_common_ending,
            'tone': 'casual',  # 도박 게시판은 대부분 반말/캐주얼
            'has_emoji': has_emoji,
            'has_tilde': has_tilde_count > total_comments * 0.2,  # 20% 이상이면 물결표 사용
            'has_exclamation': has_exclamation_count > total_comments * 0.2,  # 20% 이상이면 느낌표 사용
            'has_ㅠ': has_ㅠ_count > total_comments * 0.15,  # 15% 이상이면 ㅠ 사용
            'emoji_usage_rate': emoji_usage_rate,
            'avg_length': avg_length,
            'common_endings': common_endings
        }
    
    def generate_style_matched_comment(self, existing_comments: list, post_content: str = '') -> str:
        """기존 댓글 스타일에 맞춘 댓글 생성 - 기존 댓글의 핵심 단어를 그대로 사용"""
        if not existing_comments or len(existing_comments) == 0:
            return "지치네요"
        
        # 기존 댓글에서 핵심 단어 추출
        common_words = self.extract_common_words_from_comments(existing_comments)
        
        # 기존 댓글에서 직접 단어/표현 추출 (더 정확하게)
        style = self.analyze_comment_style(existing_comments)
        
        # 기존 댓글들을 분석하여 실제 사용된 표현 추출
        comment_candidates = []
        for comment in existing_comments[:10]:
            if comment and len(comment.strip()) >= 2:
                # 특수기호 제거한 버전
                clean_comment = comment.strip().rstrip('~!?ㅠㅜㅎㅋ')
                # 2-8글자 범위의 의미 있는 부분 추출
                if 2 <= len(clean_comment) <= 10:
                    comment_candidates.append(clean_comment)
                # 댓글에서 핵심 부분만 추출 (앞부분 2-6글자)
                if len(clean_comment) > 6:
                    comment_candidates.append(clean_comment[:6])
        
        # 기존 댓글에서 직접 가져온 표현 우선 사용
        if comment_candidates:
            # 기존 댓글과 비슷하되 중복되지 않게 선택
            selected = random.choice(comment_candidates)
            # 길이 제한 - 완전한 문장인지 확인 후 자르기
            if len(selected) > 10:
                # 어미가 있는지 확인
                selected_clean = selected.rstrip('~!?ㅠㅜㅎㅋ').strip()
                has_ending = bool(re.search(r'(요|죠|네요|어요|해요|되요|다요|세요|까요|나요|지요|다|어|해|되|까|나|세|지|야)$', selected_clean))
                
                if has_ending:
                    # 어미가 있으면 어미를 보존하면서 앞부분만 자르기
                    ending_match = re.search(r'(요|죠|네요|어요|해요|되요|다요|세요|까요|나요|지요|다|어|해|되|까|나|세|지|야)$', selected_clean)
                    if ending_match:
                        ending = ending_match.group(1)
                        special_suffix = selected[len(selected_clean):]
                        max_body_length = 10 - len(ending) - len(special_suffix)
                        if max_body_length > 0:
                            body = selected_clean[:-len(ending)]
                            selected = body[:max_body_length] + ending + special_suffix
                        else:
                            selected = ending + special_suffix
                else:
                    # 어미가 없으면 그냥 10글자로 자르기
                    selected = selected[:10]
            
            # 기존 댓글 스타일에 맞춰 특수 기호 추가
            comment = self.enhance_tone_variation(selected, post_content, existing_comments)
            comment = self.clean_comment_final_only(comment)
            
            print(f"[댓글] 기존 댓글에서 직접 추출: {comment}")
            return comment
        
        # 기존 댓글에서 추출 실패 시 기본 댓글 사용 (끝말 강제 추가하지 않음)
        base_comments = [
            '힘내', '아쉽', '공감', '위로', '좋아', '응원', '화이팅',
            '다음엔', '조심', '축하', '부럽', '대박'
        ]
        
        # 본문 내용에 맞는 키워드 추출
        if post_content:
            if any(word in post_content for word in ['잃', '후회', '참담', '정신차리', '못하겠']):
                base_comments = ['힘내', '아쉽', '공감', '위로', '다음엔', '조심']
            elif any(word in post_content for word in ['땄', '성공', '이득', '좋아']):
                base_comments = ['축하', '부럽', '대박', '좋아', '응원']
        
        # 랜덤 선택
        comment = random.choice(base_comments)
        
        # 끝말 강제 추가하지 않음 - 기존 댓글 스타일을 따라야 함
        # 기존 댓글들이 특수 기호를 사용하면 추가
        if style['has_emoji']:
            if style['has_tilde'] and random.random() < 0.5:
                comment += '~'
            elif style['has_exclamation'] and random.random() < 0.5:
                comment += '!'
        
        # 길이 제한 (10글자) - 완전한 문장인지 확인 후 자르기
        if len(comment) > 10:
            # 어미가 있는지 확인
            comment_clean = comment.rstrip('~!?ㅠㅜㅎㅋ').strip()
            has_ending = bool(re.search(r'(요|죠|네요|어요|해요|되요|다요|세요|까요|나요|지요|다|어|해|되|까|나|세|지|야)$', comment_clean))
            
            if has_ending:
                # 어미가 있으면 어미를 보존하면서 앞부분만 자르기
                ending_match = re.search(r'(요|죠|네요|어요|해요|되요|다요|세요|까요|나요|지요|다|어|해|되|까|나|세|지|야)$', comment_clean)
                if ending_match:
                    ending = ending_match.group(1)
                    special_suffix = comment[len(comment_clean):]
                    max_body_length = 10 - len(ending) - len(special_suffix)
                    if max_body_length > 0:
                        body = comment_clean[:-len(ending)]
                        comment = body[:max_body_length] + ending + special_suffix
                    else:
                        comment = ending + special_suffix
            else:
                # 어미가 없으면 그냥 10글자로 자르기
                comment = comment[:10]
        
        if not self.has_meaningful_content(comment):
            comment = '지치네요'
        
        # 기존 댓글 스타일에 맞춰 특수 기호 추가 (기존 댓글 스타일 반영)
        comment = self.enhance_tone_variation(comment, post_content, existing_comments)
        
        # 중복 어미만 제거 (특수 기호는 보존)
        comment = self.clean_comment_final_only(comment)
        
        print(f"[댓글] 기존 댓글 스타일 분석: 끝말={style['ending']}, 이모티콘={style['has_emoji']}")
        print(f"[댓글] 스타일 맞춤 댓글 생성: {comment}")
        
        return comment
    
    async def get_existing_comments(self) -> list:
        """기존 댓글들 가져오기"""
        try:
            comments = []
            
            # JavaScript로 댓글 찾기 (정확한 구조 기반)
            comments_data = await self.page.evaluate("""
                () => {
                    let allComments = [];
                    
                    // 방법 1: article[id^="c_"] 태그로 댓글 찾기 (oncapan.com 구조, 가장 정확)
                    const commentArticles = document.querySelectorAll('article[id^="c_"]');
                    commentArticles.forEach(article => {
                        // 우선순위 1: textarea[id^="save_comment_"]에서 댓글 텍스트 가져오기 (oncapan.com)
                        const textarea = article.querySelector('textarea[id^="save_comment_"]');
                        if (textarea) {
                            const text = (textarea.value || textarea.textContent || '').trim();
                            if (text && text.length > 0) {
                                allComments.push(text);
                                return; // 찾았으면 다음 댓글로
                            }
                        }
                        
                        // 우선순위 2: .cmt_contents > p 태그에서 텍스트 가져오기 (oncapan.com)
                        const cmtContents = article.querySelector('.cmt_contents');
                        if (cmtContents) {
                            // p 태그 내부 텍스트 우선
                            const pTag = cmtContents.querySelector('p');
                            if (pTag) {
                                const text = (pTag.innerText || pTag.textContent || '').trim();
                                if (text && text.length > 0) {
                                    allComments.push(text);
                                    return;
                                }
                            }
                            // p 태그가 없으면 .cmt_contents 전체 텍스트
                            const text = (cmtContents.innerText || cmtContents.textContent || '').trim();
                            if (text && text.length > 0) {
                                allComments.push(text);
                            }
                        }
                    });
                    
                    // 방법 2: textarea[id^="save_comment_"] 직접 찾기 (백업 방법)
                    if (allComments.length === 0) {
                        const saveCommentTextareas = document.querySelectorAll('textarea[id^="save_comment_"]');
                        saveCommentTextareas.forEach(textarea => {
                            const text = (textarea.value || textarea.textContent || '').trim();
                            if (text && text.length > 0) {
                                allComments.push(text);
                            }
                        });
                    }
                    
                    // 방법 3: .cmt_contents 클래스로 찾기 (백업 방법)
                    if (allComments.length === 0) {
                        const cmtContents = document.querySelectorAll('.cmt_contents');
                        cmtContents.forEach(el => {
                            const text = (el.innerText || el.textContent || '').trim();
                            if (text && text.length > 0) {
                                // 댓글 입력 필드나 버튼 텍스트 제외
                                if (!text.includes('댓글 입력') && !text.includes('댓글등록') && 
                                    !text.includes('작성') && !text.includes('등록')) {
                                    allComments.push(text);
                                }
                            }
                        });
                    }
                    
                    // 필터링: 의미 있는 댓글만 (너무 짧거나 의미 없는 것 제외)
                    const filtered = allComments.filter(c => {
                        const trimmed = c.trim();
                        return trimmed.length >= 1 && trimmed.length <= 200 && 
                               !trimmed.match(/^\\s*$/) && // 공백만 있는 것 제외
                               !trimmed.match(/^\\d+$/) && // 숫자만 있는 것 제외
                               !trimmed.includes('댓글 입력') && 
                               !trimmed.includes('댓글등록') &&
                               !trimmed.includes('작성') &&
                               !trimmed.includes('등록');
                    });
                    
                    return filtered;
                }
            """)
            
            if comments_data:
                comments = [c for c in comments_data if c and len(c.strip()) > 0]
            
            print(f"[댓글] 실제 발견된 댓글 수: {len(comments)}개")
            if comments:
                for i, comment in enumerate(comments[:5], 1):
                    print(f"  {i}. {comment[:50]}...")
            
            # 디버깅: 댓글을 찾지 못한 경우 페이지 구조 분석
            if not comments or len(comments) == 0:
                print("[디버깅] 댓글을 찾지 못했습니다. 페이지 구조를 분석합니다...")
                page_structure = await self.page.evaluate("""
                    () => {
                        const info = {
                            title: document.title,
                            url: window.location.href,
                            bodyClasses: document.body.className,
                            bodyId: document.body.id,
                            allIds: Array.from(document.querySelectorAll('[id]')).map(el => el.id).slice(0, 20),
                            allClasses: Array.from(document.querySelectorAll('[class]')).map(el => el.className).slice(0, 30),
                            forms: Array.from(document.querySelectorAll('form')).map(f => ({
                                id: f.id,
                                class: f.className,
                                action: f.action
                            })),
                            textareas: Array.from(document.querySelectorAll('textarea')).map(t => ({
                                id: t.id,
                                class: t.className,
                                placeholder: t.placeholder
                            })),
                            buttons: Array.from(document.querySelectorAll('button, input[type="submit"]')).map(b => ({
                                id: b.id,
                                class: b.className,
                                value: b.value || b.textContent
                            }))
                        };
                        return info;
                    }
                """)
                print(f"[디버깅] 페이지 제목: {page_structure.get('title', 'N/A')}")
                print(f"[디버깅] 페이지 URL: {page_structure.get('url', 'N/A')}")
                print(f"[디버깅] 발견된 ID들 (처음 10개): {page_structure.get('allIds', [])[:10]}")
                print(f"[디버깅] 발견된 클래스들 (처음 15개): {page_structure.get('allClasses', [])[:15]}")
                print(f"[디버깅] 발견된 폼들: {page_structure.get('forms', [])}")
                print(f"[디버깅] 발견된 textarea들: {page_structure.get('textareas', [])}")
                print(f"[디버깅] 발견된 버튼들: {page_structure.get('buttons', [])}")
                print("[디버깅] 위 정보를 개발자에게 알려주시면 댓글 위치를 정확히 찾을 수 있습니다.")
            
            return comments[:20]  # 최대 20개까지 사용
            
        except Exception as e:
            print(f"[경고] 기존 댓글을 가져오는 중 오류: {e}")
            import traceback
            print(f"[경고] 상세 오류: {traceback.format_exc()}")
            return []
    
    def clean_comment(self, comment: str) -> str:
        """댓글에서 중복 어미, 마침표, 불필요한 문자 제거 (특수 기호는 보존)"""
        import re
        
        if not comment:
            return comment
        
        # 1. 특수 기호는 제거하지 않음 (젊은층 톤을 위해 보존)
        # 과도한 특수 기호만 정리 (3개 이상 연속된 경우만 제거)
        comment = re.sub(r'[~]{3,}', '~', comment)  # ~~~ 이상은 ~로
        comment = re.sub(r'[!]{3,}', '!', comment)  # !!! 이상은 !로
        comment = re.sub(r'[ㅠ]{3,}', 'ㅠㅠ', comment)  # ㅠㅠㅠ 이상은 ㅠㅠ로
        # ㅎㅋ 같은 이모티콘은 제거 (너무 많으면 부자연스러움)
        comment = re.sub(r'[ㅎㅋ]{2,}', '', comment)
        
        # 2. 마침표 제거
        comment = re.sub(r'\.+', '', comment)  # 모든 마침표 제거
        
        # 3. 물음표 위치 정리: 물음표가 중간에 있으면 끝으로 이동
        # 예: "일어나셨?어요" -> "일어나셨어요?"
        if '?' in comment:
            # 물음표가 끝에 있지 않으면 끝으로 이동
            if not comment.endswith('?'):
                comment = comment.replace('?', '') + '?'
        
        # 4. "용" 어미 제거 (예: "힘내용" -> "힘내요", "좋아용" -> "좋아요")
        comment = re.sub(r'(\S+)용$', r'\1요', comment)  # 끝에 있는 "용" -> "요"
        comment = re.sub(r'(\S+)용\s', r'\1요 ', comment)  # 중간에 있는 "용" -> "요"
        
        # 5. 어미 뒤에 추가 어미가 붙는 경우 제거
        # 예: "노곤하죠여?" -> "노곤하죠?"
        # 예: "노곤하죠요?" -> "노곤하죠?"
        # 예: "일어나셨어요?" -> "일어나셨어요?" (정상)
        comment = re.sub(r'(죠|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요|세요)(여|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요)(\?|$)', r'\1\3', comment)
        comment = re.sub(r'(죠|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요)(여|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요)$', r'\1', comment)
        
        # 6. 중복 어미 제거: "요요", "네요요", "어요요" 등 (모든 위치에서)
        comment = re.sub(r'요요+', '요', comment)  # "요요" -> "요", "요요요" -> "요"
        comment = re.sub(r'네요요+', '네요', comment)  # "네요요" -> "네요"
        comment = re.sub(r'어요요+', '어요', comment)  # "어요요" -> "어요"
        comment = re.sub(r'해요요+', '해요', comment)  # "해요요" -> "해요"
        comment = re.sub(r'되요요+', '되요', comment)  # "되요요" -> "되요"
        comment = re.sub(r'다요요+', '다요', comment)  # "다요요" -> "다요"
        comment = re.sub(r'야요요+', '야요', comment)  # "야요요" -> "야요"
        comment = re.sub(r'죠요+', '죠', comment)  # "죠요" -> "죠"
        comment = re.sub(r'죠요요+', '죠', comment)  # "죠요요" -> "죠"
        
        # 7. 댓글 끝에 "요"가 중복되거나 어색하게 붙는 경우 정리
        # 예: "화이팅요요" -> "화이팅요" (위에서 처리)
        # 예: "힘내요 요" -> "힘내요"
        comment = re.sub(r'(\S+)요\s*요', r'\1요', comment)  # "힘내요 요" -> "힘내요"
        comment = re.sub(r'(\S+)\s*요$', r'\1요', comment)  # "화이팅 요" -> "화이팅요"
        
        # 8. 불필요한 공백 제거 (예: "화이팅  요" -> "화이팅요")
        comment = re.sub(r'\s+([요])', r'\1', comment)
        
        # 9. 연속된 공백 제거
        comment = re.sub(r'\s+', ' ', comment)
        comment = comment.strip()
        
        return comment
    
    def clean_comment_final_only(self, comment: str) -> str:
        """최종 정리: 중복 어미만 제거하고 특수 기호는 완전히 보존"""
        import re
        
        if not comment:
            return comment
        
        # 특수 기호는 절대 건드리지 않음
        # 중복 어미만 제거
        comment = re.sub(r'요요+', '요', comment)
        comment = re.sub(r'네요요+', '네요', comment)
        comment = re.sub(r'어요요+', '어요', comment)
        comment = re.sub(r'해요요+', '해요', comment)
        comment = re.sub(r'되요요+', '되요', comment)
        comment = re.sub(r'다요요+', '다요', comment)
        comment = re.sub(r'야요요+', '야요', comment)
        comment = re.sub(r'죠요+', '죠', comment)
        comment = re.sub(r'죠요요+', '죠', comment)
        
        # 어미 뒤에 추가 어미가 붙는 경우 제거
        comment = re.sub(r'(죠|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요)(여|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요)(\?|$)', r'\1\3', comment)
        comment = re.sub(r'(죠|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요)(여|요|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요)$', r'\1', comment)
        
        # 공백 정리만
        comment = re.sub(r'\s+', ' ', comment)
        comment = comment.strip()
        
        return comment
    
    async def generate_ai_comment(self, post_content: str, existing_comments: list = None, post_title: str = None) -> str:
        """AI를 사용해서 게시글 제목, 본문과 기존 댓글을 고려하여 관련된 댓글 생성"""
        # 기존 댓글과 본문 정보 저장 (AI 실패 시 사용)
        self._last_post_content = post_content
        self._last_post_title = post_title or ""
        self._last_existing_comments = existing_comments or []
        
        # OpenAI API 키 확인
        openai_api_key = self.config.get('openai_api_key', '')
        
        # API 키 확인
        print(f"[AI] ========================================")
        print(f"[AI] AI API 키 확인 중...")
        
        if openai_api_key and openai_api_key.strip():
            print(f"[AI] ✅ OpenAI API 키 발견: {openai_api_key[:20]}... (처음 20자, 전체 길이: {len(openai_api_key)}자)")
            print(f"[AI] ========================================")
            api_key = openai_api_key  # api_key 변수 할당
        else:
            print(f"[AI] ❌ AI API 키가 없습니다!")
            print(f"[AI] ========================================")
            print("[경고] AI API 키가 없습니다. 기존 댓글 스타일을 참고하여 댓글 생성...")
            # 기존 댓글 스타일에 맞춰 댓글 생성
            return self.generate_style_matched_comment(existing_comments or [], post_content)
        
        print(f"[AI] ========================================")
        
        if not post_content or len(post_content.strip()) < 10:
            print("[경고] 게시글 본문이 너무 짧습니다. 기존 댓글 스타일로 댓글 생성...")
            return self.generate_style_matched_comment(existing_comments or [], post_content)
        
        print(f"[AI] 게시글 본문 분석 중... (길이: {len(post_content)}자)")
        print(f"[AI] 본문 내용: {post_content[:100]}...")
        
        # 게시글 감정/유형 분석
        post_emotion = self.analyze_post_emotion(post_content, post_title)
        post_type = self.classify_post_type(post_content, post_title)
        post_date = getattr(self, '_last_post_date', None)
        temporal_context = self.get_temporal_context(post_date)
        max_comment_length = self.get_optimal_comment_length(existing_comments)
        community_terms = self.extract_community_terms(f"{post_title or ''}\n{post_content or ''}")
        post_context_text = self.build_post_context_text(post_emotion, post_type, temporal_context, max_comment_length, community_terms)
        
        if existing_comments:
            print(f"[AI] 기존 댓글 {len(existing_comments)}개 확인: {existing_comments[:3]}...")
        
        try:
            # 기존 댓글 정보 추가 (최우선 참고)
            if existing_comments and len(existing_comments) > 0:
                # 기존 댓글 스타일 분석
                style = self.analyze_comment_style(existing_comments)
                
                numbered_comments = "\n".join(
                    [f"{idx + 1}. {c}" for idx, c in enumerate(existing_comments[:8])]
                )
                # 기존 댓글들의 핵심 단어/표현 추출
                common_words = self.extract_common_words_from_comments(existing_comments)
                
                comments_text = f"\n\n⭐⭐⭐ 가장 중요: 현재 댓글 흐름 (최근 {min(len(existing_comments), 8)}개):\n{numbered_comments}\n\n"
                
                if common_words:
                    comments_text += f"🔑 기존 댓글들이 자주 사용하는 핵심 단어/표현:\n"
                    for word in common_words[:5]:
                        comments_text += f"- \"{word}\"\n"
                    comments_text += f"\n⚠️⚠️⚠️⚠️⚠️ 가장 중요: 반드시 위 단어/표현들을 사용하여 댓글을 작성하세요!\n"
                    comments_text += f"⚠️⚠️⚠️ 절대 새로운 단어를 만들어내지 마세요! 위에 나온 단어만 사용하세요!\n"
                    comments_text += f"⚠️⚠️⚠️ 기존 댓글에 \"맛피자\", \"바리맨\", \"꾼스\" 같은 단어가 있으면 당신도 반드시 그 단어를 사용하세요!\n"
                    comments_text += f"예: 기존 댓글에 \"천포\", \"냠냠\"이 있으면 당신도 반드시 \"천포\", \"냠냠\" 같은 단어 사용\n"
                    comments_text += f"예: 기존 댓글에 \"맛피자\", \"바리맨\"이 있으면 당신도 반드시 \"맛피자\", \"바리맨\" 같은 단어 사용\n"
                    comments_text += f"예: 기존 댓글에 \"아이구\", \"에고\"가 있으면 당신도 \"아이고\", \"아이구\" 같은 표현 사용\n"
                    comments_text += f"예: 기존 댓글에 \"맛담\"이 있으면 당신도 \"맛담\" 관련 표현 사용\n"
                    comments_text += f"⚠️⚠️⚠️ 위 단어들을 사용하지 않고 일반적인 표현(예: \"피자 가 될 것 같아요\")을 사용하면 안 됩니다!\n\n"
                
                comments_text += "⚠️⚠️⚠️ 반드시 위 댓글들을 우선적으로 분석하세요:\n"
                comments_text += "1. ⭐⭐⭐ 가장 중요: 위 댓글들이 사용하는 핵심 단어/표현을 파악하고 반드시 그대로 사용하세요\n"
                comments_text += "   - 예: 위 댓글에 \"맛피자\", \"바리맨\", \"꾼스\"가 있으면 당신도 반드시 그 단어들을 사용\n"
                comments_text += "   - 예: 위 댓글에 \"천포\", \"냠냠\"이 있으면 당신도 반드시 \"천포\", \"냠냠\" 사용\n"
                comments_text += "   - ⚠️ 절대 일반적인 표현(예: \"피자 가 될 것 같아요\")을 사용하지 마세요!\n"
                comments_text += "2. 위 댓글들의 말투 패턴을 정확히 파악 (존댓말/반말, 어미 패턴)\n"
                comments_text += "3. 위 댓글들의 스타일과 길이를 분석\n"
                comments_text += "4. 위 댓글들의 감정선과 톤을 파악\n"
                comments_text += "5. 위 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요\n"
                comments_text += "6. 본문보다 위 기존 댓글 스타일에 더 중점을 두세요\n"
                comments_text += "7. ✅ 가장 중요: 위 댓글들이 말하는 핵심 내용/키워드를 그대로 유지하고, 말투만 자연스럽게 바꿔 표현하세요.\n"
                comments_text += "8. 새로운 주장이나 정보를 추가하지 말고, 기존 댓글과 같은 메시지를 짧게 변형하세요.\n"
                comments_text += "9. ⚠️⚠️⚠️ 반드시 10글자 이내로 완전한 문장을 작성하세요. 어미(요, 네요, 어요, 해요, 되요, 다요, 세요, 까요, 나요, 지요, 죠, 다, 어, 해, 되, 까, 나, 세, 지, 야 등)로 끝나야 합니다!\n\n"
                
                # 분석된 스타일 정보 추가
                comments_text += f"📊 기존 댓글 스타일 분석 결과:\n"
                comments_text += f"- 가장 많이 사용된 어미: {style['ending']}\n"
                comments_text += f"- 자주 사용되는 어미들: {', '.join(style['common_endings'][:3])}\n"
                comments_text += f"- 평균 댓글 길이: 약 {style['avg_length']}자\n"
                if style['has_emoji']:
                    comments_text += f"- 특수 기호 사용: {style['emoji_usage_rate']*100:.0f}%의 댓글이 특수 기호 사용 (~, !, ㅠ 등)\n"
                    if style['has_tilde']:
                        comments_text += f"  → 물결표(~) 사용 빈도 높음\n"
                    if style['has_exclamation']:
                        comments_text += f"  → 느낌표(!) 사용 빈도 높음\n"
                    if style['has_ㅠ']:
                        comments_text += f"  → ㅠ 사용 빈도 높음\n"
                    comments_text += f"- ⚠️ 중요: 위 기존 댓글들이 특수 기호를 사용한다면, 당신도 비슷한 스타일로 작성하세요.\n"
                else:
                    comments_text += f"- 특수 기호 사용: 거의 사용하지 않음 ({style['emoji_usage_rate']*100:.0f}%)\n"
                comments_text += f"- ⚠️ 중요: 위 기존 댓글들이 특수 기호를 사용하지 않으므로, 당신도 특수 기호 없이 작성하세요.\n"
                
                comment_flow = self.analyze_comment_flow(existing_comments)
                if comment_flow.get('needs_diversity'):
                    comments_text += "- 최근 댓글들이 서로 비슷하니 다른 표현이나 관점을 사용하세요.\n"
                    comments_text += "- 같은 단어/어미 반복을 피하고 새로운 단어를 사용하세요.\n"
            else:
                comments_text = "\n\n현재 댓글 흐름: (댓글 없음)"
            
            # 도박 용어 사전 가져오기
            gambling_terms_text = self.get_gambling_terms_prompt()
            if gambling_terms_text:
                print("[AI] 도박 용어 사전 로드 완료")
            
            # AI 프롬프트 설정 파일에서 Few-shot 예시 가져오기
            few_shot_text = ""
            bad_examples_text = ""
            base_prompt_section = ""
            
            prompt_config = self.load_prompt_config()
            
            # 1순위: AI_프롬프트_설정.json 파일 사용
            if prompt_config:
                # 좋은 댓글 예시 추가 (기존 댓글 스타일 반영 필수)
                good_examples = prompt_config.get('좋은_댓글_예시', [])
                if good_examples:
                    few_shot_text = "\n\n📚 좋은 댓글 예시 (반드시 기존 댓글 스타일과 비슷하게 작성하세요):\n"
                    few_shot_text += "⚠️ 중요: 아래 예시들은 모두 기존 댓글들의 스타일을 따라 작성된 것입니다.\n"
                    few_shot_text += "당신도 반드시 현재 게시글의 기존 댓글들을 먼저 분석하고, 그 스타일과 비슷하게 댓글을 작성해야 합니다.\n\n"
                    for i, example in enumerate(good_examples[:10], 1):  # 최대 10개로 확대
                        few_shot_text += f"\n예시 {i}:\n"
                        existing = example.get('기존_댓글_예시', []) or example.get('기존_댓글', [])
                        if existing:
                            few_shot_text += f"기존 댓글: {', '.join(existing[:3])}\n"
                            few_shot_text += f"→ 좋은 댓글 (기존 댓글 스타일 반영): {example.get('좋은_댓글', '')}\n"
                            few_shot_text += f"※ 이 댓글은 위 기존 댓글들의 말투, 스타일, 길이를 따라 작성되었습니다.\n"
                        else:
                            few_shot_text += f"본문: {example.get('본문_예시', '')[:100]}...\n"
                            few_shot_text += f"좋은 댓글: {example.get('좋은_댓글', '')}\n"
                        reason = example.get('이유', '')
                        if reason:
                            few_shot_text += f"이유: {reason}\n"
                
                # 나쁜 예시 추가
                bad_examples = prompt_config.get('나쁜_댓글_예시', [])
                if bad_examples:
                    bad_examples_text = "\n\n❌ 피해야 할 댓글 예시:\n"
                    for bad in bad_examples[:3]:  # 최대 3개
                        bad_examples_text += f"- {bad.get('댓글', '')} (이유: {bad.get('이유', '')})\n"
                
                # 개선된 프롬프트가 있으면 사용
                improved_prompt = prompt_config.get('프롬프트_개선_내용', '')
                if improved_prompt:
                    base_prompt_section = improved_prompt
                    print("[AI] 프롬프트 설정 파일의 개선 프롬프트 사용 중...")
            
            # 2순위: ai_learning_data.json 파일 사용 (기존 학습 데이터)
            elif hasattr(self, 'learning_data') and self.learning_data:
                # Few-shot 예시 추가 (기존 댓글 스타일 반영 필수)
                few_shot_examples = self.learning_data.get('few_shot_examples', [])
                if few_shot_examples:
                    few_shot_text = "\n\n📚 좋은 댓글 예시 (반드시 기존 댓글 스타일과 비슷하게 작성하세요):\n"
                    few_shot_text += "⚠️ 중요: 아래 예시들은 모두 기존 댓글들의 스타일을 따라 작성된 것입니다.\n"
                    few_shot_text += "당신도 반드시 현재 게시글의 기존 댓글들을 먼저 분석하고, 그 스타일과 비슷하게 댓글을 작성해야 합니다.\n\n"
                    for i, example in enumerate(few_shot_examples[:10], 1):  # 최대 10개로 확대
                        few_shot_text += f"\n예시 {i}:\n"
                        existing = example.get('existing', [])
                        if existing:
                            few_shot_text += f"기존 댓글: {', '.join(existing[:3])}\n"
                            few_shot_text += f"→ 좋은 댓글 (기존 댓글 스타일 반영): {example.get('good_comment', '')}\n"
                            few_shot_text += f"※ 이 댓글은 위 기존 댓글들의 말투, 스타일, 길이를 따라 작성되었습니다.\n"
                        else:
                            few_shot_text += f"본문: {example.get('post', '')[:100]}...\n"
                            few_shot_text += f"좋은 댓글: {example.get('good_comment', '')}\n"
                
                # 나쁜 예시 추가
                bad_examples = self.learning_data.get('bad_examples', [])
                if bad_examples:
                    bad_examples_text = "\n\n❌ 피해야 할 댓글 예시:\n"
                    for bad in bad_examples[:3]:  # 최대 3개
                        bad_examples_text += f"- {bad.get('comment', '')} (이유: {bad.get('reason', '')})\n"
                
                # 개선된 프롬프트가 있으면 사용
                improved_prompt = self.learning_data.get('improved_prompt', '')
                if improved_prompt:
                    base_prompt_section = improved_prompt
                    print("[AI] 학습된 개선 프롬프트 사용 중...")
            
            # 기본 프롬프트 (설정 파일이나 학습 데이터가 없을 때)
            if not base_prompt_section:
                # 프롬프트 설정 파일에서 기본 규칙 가져오기
                if prompt_config:
                    basic_rules = prompt_config.get('기본_규칙', {})
                    board_type = basic_rules.get('게시판_특성', '도박 관련 사이트의 자유게시판')
                    comment_style = basic_rules.get('댓글_스타일', '페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일')
                    max_length = basic_rules.get('최대_길이', '10글자 이내')
                    tone_matching = basic_rules.get('말투_매칭', '본문이 존댓말이면 댓글도 존댓말, 본문이 반말이면 댓글도 반말')
                    
                    # 본문 및 댓글 분석 가이드 가져오기
                    analysis_guide = ""
                    if prompt_config:
                        # 본문 분석 가이드
                        post_analysis = prompt_config.get('본문_분석_가이드', {})
                        if post_analysis:
                            analysis_items = post_analysis.get('분석_항목', {})
                            if analysis_items:
                                analysis_guide += "\n\n📖 본문 분석 방법 (반드시 이 순서로 분석하세요):\n"
                                # 말투 분석
                                tone_analysis = analysis_items.get('1_말투_분석', {})
                                if tone_analysis:
                                    analysis_guide += f"\n1️⃣ 말투 분석:\n"
                                    analysis_guide += f"- 목적: {tone_analysis.get('목적', '')}\n"
                                    checklist = tone_analysis.get('체크리스트', [])
                                    for item in checklist:
                                        analysis_guide += f"  • {item}\n"
                                
                                # 감정 분석
                                emotion_analysis = analysis_items.get('2_감정_분석', {})
                                if emotion_analysis:
                                    analysis_guide += f"\n2️⃣ 감정 분석:\n"
                                    analysis_guide += f"- 목적: {emotion_analysis.get('목적', '')}\n"
                                    categories = emotion_analysis.get('감정_카테고리', {})
                                    for cat_name, cat_info in list(categories.items())[:3]:  # 최대 3개
                                        keywords = cat_info.get('키워드', [])
                                        tone = cat_info.get('댓글_톤', '')
                                        example = cat_info.get('예시', '')
                                        analysis_guide += f"  • {cat_name}: 키워드 {', '.join(keywords[:3])} → {tone}\n"
                                
                                # 핵심 키워드 추출
                                keyword_analysis = analysis_items.get('3_핵심_키워드_추출', {})
                                if keyword_analysis:
                                    analysis_guide += f"\n3️⃣ 핵심 키워드 추출:\n"
                                    analysis_guide += f"- 목적: {keyword_analysis.get('목적', '')}\n"
                                    methods = keyword_analysis.get('방법', [])
                                    for method in methods[:3]:  # 최대 3개
                                        analysis_guide += f"  • {method}\n"
                        
                        # 댓글 흐름 분석 가이드
                        comment_analysis = prompt_config.get('댓글_흐름_분석_가이드', {})
                        if comment_analysis:
                            analysis_items = comment_analysis.get('분석_항목', {})
                            if analysis_items:
                                analysis_guide += "\n\n💬 댓글 흐름 분석 방법 (기존 댓글들을 이렇게 분석하세요):\n"
                                # 말투 패턴 분석
                                tone_pattern = analysis_items.get('1_말투_패턴_분석', {})
                                if tone_pattern:
                                    analysis_guide += f"\n1️⃣ 말투 패턴 분석:\n"
                                    analysis_guide += f"- 목적: {tone_pattern.get('목적', '')}\n"
                                    checklist = tone_pattern.get('체크리스트', [])
                                    for item in checklist[:3]:  # 최대 3개
                                        analysis_guide += f"  • {item}\n"
                                
                                # 감정선 분석
                                emotion_flow = analysis_items.get('2_감정선_분석', {})
                                if emotion_flow:
                                    analysis_guide += f"\n2️⃣ 감정선 분석:\n"
                                    analysis_guide += f"- 목적: {emotion_flow.get('목적', '')}\n"
                                    checklist = emotion_flow.get('체크리스트', [])
                                    for item in checklist[:3]:  # 최대 3개
                                        analysis_guide += f"  • {item}\n"
                                
                                # 이모티콘/기호 패턴
                                emoji_pattern = analysis_items.get('3_이모티콘_및_기호_패턴', {})
                                if emoji_pattern:
                                    analysis_guide += f"\n3️⃣ 이모티콘/기호 패턴:\n"
                                    analysis_guide += f"- 목적: {emoji_pattern.get('목적', '')}\n"
                                    checklist = emoji_pattern.get('체크리스트', [])
                                    for item in checklist[:3]:  # 최대 3개
                                        analysis_guide += f"  • {item}\n"
                        
                        # 본문-댓글 관계 가이드
                        relationship_guide = prompt_config.get('본문_댓글_관계_이해_가이드', {})
                        if relationship_guide:
                            relationship_types = relationship_guide.get('관계_유형', {})
                            if relationship_types:
                                analysis_guide += "\n\n🔗 본문-댓글 관계 이해:\n"
                                for rel_name, rel_info in list(relationship_types.items())[:2]:  # 최대 2개
                                    analysis_guide += f"\n• {rel_name}: {rel_info.get('설명', '')}\n"
                    
                    # 본문이 의미 없는지 확인
                    is_meaningless = False
                    if post_content:
                        meaningless_patterns = [
                            len(post_content.strip()) < 10,  # 너무 짧음
                            post_content.strip() in ['', ' ', '.', '..', '...'],  # 거의 비어있음
                            len(set(post_content.strip().split())) < 3,  # 단어가 너무 적음
                        ]
                        # 의미 없는 패턴 체크
                        meaningless_keywords = ['ㅎ', 'ㅋ', 'ㅠ', 'ㅜ', '...', '..', '.']
                        if len(post_content.strip()) < 20:
                            meaningless_count = sum(1 for kw in meaningless_keywords if kw in post_content)
                            if meaningless_count >= len(post_content.strip()) * 0.5:  # 50% 이상이 의미 없는 문자
                                is_meaningless = True
                    
                    meaningless_guide = ""
                    if is_meaningless:
                        meaningless_guide = "\n\n⚠️ 특별 상황: 게시글 본문이 의미 없거나 내용이 거의 없습니다.\n- 이런 경우 간단하고 무난한 댓글을 작성하세요\n- 예: '그렇네요', '맞아요', '알겠어요', '응', 'ㅇㅇ'\n- 과도하게 긍정적이거나 형식적인 댓글은 피하세요\n- 기존 댓글이 있으면 그 스타일에 맞춰 작성하세요\n"
                    
                    base_prompt_section = f"""다음 게시글 본문과 기존 댓글들을 읽고, 작성자의 감정에 공감하는 자연스러운 댓글을 작성해주세요.

⚠️ 중요: 이 게시판은 {board_type}입니다.
- 자유게시판이기 때문에 도박과 관련된 얘기만 하는 것이 아니라 단순 수다를 떨 때도 있습니다
- 게시글 주제가 도박이든 일상이든 상관없이, 본문 내용과 기존 댓글 흐름에 맞춰 작성해야 합니다
- 댓글은 {comment_style}로 작성해야 합니다{meaningless_guide}

🎯 핵심 규칙 (반드시 지켜야 함):
1. ⭐⭐⭐ 가장 중요: 기존 댓글들을 우선적으로 분석하세요!
   - 기존 댓글들의 말투, 스타일, 길이, 감정선을 정확히 파악
   - 기존 댓글들과 최대한 비슷한 스타일로 댓글 작성
   - 본문보다 기존 댓글 스타일에 더 중점을 두세요
2. 말투 매칭: {tone_matching}
   - 기존 댓글들의 말투 패턴을 우선 확인
   - 기존 댓글이 대부분 존댓말이면 존댓말로, 반말이면 반말로 작성
   - 본문 말투는 참고용으로만 사용
3. 본문의 핵심 키워드를 댓글에 자연스럽게 활용 (선택적)
4. 특수 기호 사용: 기존 댓글들이 특수 기호(~, !, ㅠ 등)를 사용한다면 그에 맞춰 사용하고, 사용하지 않는다면 사용하지 마세요
5. 마침표(.) 절대 사용 금지
6. "용" 어미 절대 사용 금지
7. 반드시 {max_length}로 완성
8. 맞춤법 정확하게 사용
9. 형식적인 댓글 금지 ("감사합니다", "좋은 글" 등)

📝 댓글 작성 방법 (우선순위 - 반드시 이 순서로):
1. ⭐⭐⭐ 가장 먼저: 기존 댓글들을 정확히 분석
   - 기존 댓글들의 말투 패턴 파악 (존댓말/반말, 어미 패턴)
   - 기존 댓글들의 스타일과 길이 분석
   - 기존 댓글들의 감정선과 톤 파악
2. ⭐⭐ 두 번째: 기존 댓글들과 최대한 비슷한 스타일로 댓글 설계
   - 기존 댓글들의 말투 패턴을 따라 작성
   - 기존 댓글들의 길이와 스타일을 따라 작성
   - 기존 댓글들의 감정선을 자연스럽게 이어가기
3. ⭐ 세 번째: 본문의 말투, 감정, 핵심 키워드를 참고 (선택적)
   - 기존 댓글 스타일을 유지하면서 본문 내용만 참고
4. 기존 댓글과 너무 비슷하지 않게 작성하되, 스타일은 반드시 일치시켜야 함

최종 출력은 댓글 한 줄만 해야 하며, 다른 문장은 포함하면 안 됩니다."""
                else:
                    # 기본 프롬프트 (설정 파일이 없을 때)
                    base_prompt_section = """다음 게시글 본문과 기존 댓글들을 읽고, 작성자의 감정에 공감하는 자연스러운 댓글을 작성해주세요.

⚠️ 중요: 이 게시판은 도박 관련 사이트의 자유게시판입니다.
- 자유게시판이기 때문에 도박과 관련된 얘기만 하는 것이 아니라 단순 수다를 떨 때도 있습니다
- 게시글 주제가 도박이든 일상이든 상관없이, 본문 내용과 기존 댓글 흐름에 맞춰 작성해야 합니다
- 댓글은 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 작성해야 합니다

🎯 말투 매칭 규칙 (매우 중요):
- 본문이 존댓말이면 댓글도 반드시 높임말을 사용해야 합니다
- 예: 본문이 "~할까요?", "~인가요?", "~일까요?" 같은 높임말 → 댓글은 "~요 입니다", "~요", "~네요", "~어요" 같은 높임말 사용
- 예: 본문이 "~할까?", "~인가?", "~일까?" 같은 반말 → 댓글은 "~야", "~다", "~어" 같은 반말 사용
- 본문의 말투를 정확히 분석하고 그에 맞춰 댓글 말투를 결정해야 합니다

📝 댓글 작성 원칙 (우선순위):
1. ⭐⭐⭐ 가장 중요: 기존 댓글들을 우선적으로 분석하고, 기존 댓글들과 최대한 비슷한 스타일로 작성
   - 기존 댓글들의 말투, 스타일, 길이, 감정선을 정확히 파악
   - 기존 댓글들의 패턴을 따라 댓글 작성
   - 본문보다 기존 댓글 스타일에 더 중점을 두세요
2. 본문 내용은 참고용으로만 사용 (기존 댓글 스타일을 유지하면서)
- 친구 같은 느낌의 글 → 친구처럼 편하게 반말이나 캐주얼한 댓글
- 존댓말로 쓴 글 → 존댓말로 댓글 작성 (예: "~요", "~네요", "~어요")
- 형식적인 글 → 형식적인 댓글 (하지만 "감사합니다" 같은 금지 단어는 사용하지 말 것)
- 시답잖은 소리 → 그냥 맞춰주기만 하면 됨 (꼭 긍정적일 필요 없음)
- 절망/후회하는 글 → "힘내요", "아쉽네요", "다음엔 조심해요", "공감해요", "위로해요"
- 기쁨/성공한 글 → "축하해요", "부럽네요", "좋아요", "대박이네요"
- 아쉬운 글 → "아쉽네요", "다음엔 잘될 거예요", "아깝네요"
- 슬프거나 힘든 글 → "힘내요", "공감해요", "위로해요", "아쉽네요"
- 절대 형식적인 댓글을 사용하지 말 것 (예: "좋은 글 감사합니다", "좋은 정보 감사합니다", "유용한 정보네요", "잘 읽었습니다" 등)
- 게시글 내용뿐 아니라 기존 댓글 흐름과도 연관된 댓글이어야 함
- 반드시 10글자 이내로 완성해야 함 (10글자를 넘기면 안 됨, 잘라내지 말고 처음부터 10글자 이내로 작성)
- ~입니다 체는 사용하지 말고 ~요 체나 반말체로 작성하되, 본문 말투에 맞춰 결정
- 특수 기호 사용: 기존 댓글들이 특수 기호(~, !, ㅠ 등)를 사용한다면 그에 맞춰 사용하고, 사용하지 않는다면 사용하지 마세요
- 예: "힘내요" → "힘내요", "좋아요" → "좋아요", "대박이네요" → "대박이네요", "아쉽네요" → "아쉽네요"
- 격식이 조금 떨어져도 괜찮음, 오히려 더 자연스럽고 친근한 톤으로 작성
- 자연스럽고 친근한 톤으로 작성
- 기분 좋은 글이면 담담하게 축하하고, 힘든 글이면 솔직히 지친 느낌이나 현실적인 톤도 가능 (예: "아 지치네요", "버텨야죠")
- 맞춤법을 반드시 정확하게 사용
- 반드시 게시글 내용과 관련된 댓글이어야 함
- 기존 댓글과 너무 비슷하지 않게 작성하되, 말투와 스타일은 비슷하게 유지
- 본문이 친구처럼 편하게 쓴 글이라면 친구처럼 편하게 댓글 작성
- 본문이 시답잖은 소리라면 그냥 맞춰주기만 하면 됨 (꼭 긍정적이거나 위로할 필요 없음)

추론 절차 (반드시 이 순서로 내부적으로 거친 뒤 마지막에 댓글 한 줄만 출력):
1. ⭐⭐⭐ 가장 먼저: 기존 댓글들을 정확히 분석합니다.
   - 기존 댓글들의 말투 패턴을 파악합니다 (존댓말/반말, 어미 패턴)
   - 기존 댓글들의 스타일과 길이를 분석합니다
   - 기존 댓글들의 감정선과 톤을 파악합니다
   - 기존 댓글들이 어떤 패턴으로 작성되었는지 정확히 이해합니다. (생각만, 출력 금지)
2. ⭐⭐ 두 번째: 기존 댓글 스타일을 따라 댓글을 설계합니다.
   - 기존 댓글들의 말투 패턴을 따라 작성합니다
   - 기존 댓글들의 길이와 스타일을 따라 작성합니다
   - 기존 댓글들의 감정선을 자연스럽게 이어갑니다. (생각만, 출력 금지)
3. ⭐ 세 번째: 본문의 말투와 핵심 키워드를 참고합니다 (선택적).
   - 기존 댓글 스타일을 유지하면서 본문 내용만 참고합니다
   - 본문의 말투는 기존 댓글 말투와 다를 수 있으므로, 기존 댓글 말투를 우선합니다. (생각만, 출력 금지)
4. 위 세 가지 정보를 합쳐 10글자 이내의 댓글을 설계합니다. 기존 댓글들이 특수 기호를 사용한다면 그에 맞춰 사용하세요.
최종 출력은 댓글 한 줄만 해야 하며, 다른 문장은 포함하면 안 됩니다.

금지 사항 (절대 사용 금지):
- "좋은 글 감사합니다"
- "좋은 정보 감사합니다"
- "유용한 정보네요"
- "잘 읽었습니다"
- "도움이 되었어요" (절대 사용하지 말 것)
- "도움이 됐어요" (절대 사용하지 말 것)
- "도움이 되었습니다" (절대 사용하지 말 것)
- "감사합니다" (절대 사용하지 말 것)
- "감사해요" (절대 사용하지 말 것)
- "감사" (절대 사용하지 말 것)
- "감사합니다"라는 단어가 포함된 모든 댓글
- 기타 형식적이고 일반적인 댓글

⚠️ 매우 중요 - 중복 어미 및 불필요한 문자 금지:
- 절대 "요요", "네요요", "어요요", "해요요" 같은 중복 어미를 사용하지 말 것
- 절대 "ㅠㅠ 요", "~ 요", "! 요" 같이 이모티콘/기호 뒤에 공백 + "요"를 붙이지 말 것
- 절대 마침표(.)를 사용하지 말 것
- 절대 "용" 어미를 사용하지 말 것 (예: "힘내용" ❌ → "힘내요" ✅, "좋아용" ❌ → "좋아요" ✅)
- 댓글 끝에 "요"는 한 번만 사용하고, 이미 어미가 있으면 추가하지 말 것
- 예: "화이팅요요" ❌ → "화이팅요" ✅
- 예: "화이팅ㅠㅠ 요" ❌ → "화이팅요" ✅

게시글 본문:
{post_content[:500]}{comments_text}{few_shot_text}{bad_examples_text}

댓글:"""
            
            # 본문에서 핵심 키워드 추출
            keywords = self.extract_keywords_from_post(post_content, post_title)
            keywords_text = ""
            if keywords:
                keywords_text = f"\n\n🔑 본문 핵심 키워드: {', '.join(keywords)}\n- 위 키워드들을 댓글에 자연스럽게 활용하세요.\n- 예: 본문에 '야식'이 있으면 '야식 좋지요'처럼 키워드를 포함한 댓글을 작성하세요.\n- 예: 본문에 '형님'이 있으면 '형님도 굿나잇입니다'처럼 키워드를 활용하세요.\n"
            
            # 질문형 게시글 확인
            is_question = any(q in post_content for q in ['?', '?', '어떻게', '뭐가', '어떤', '언제', '어디', '누가', '왜', '몇시', '몇시쯤'])
            question_guide = ""
            if is_question:
                question_guide = "\n\n⚠️ 질문형 게시글입니다:\n- 질문에 대한 답을 모르면 댓글을 작성하지 마세요.\n- 답을 알고 있거나 공감할 수 있는 내용만 댓글로 작성하세요.\n- 예: '축구 오늘 몇시쯤에 하나요?' → 답을 모르면 댓글 작성하지 않음\n"
            
            # 프롬프트 생성 (도박 용어 사전 포함)
            # 기존 댓글을 우선적으로 강조
            comments_priority_text = "\n\n⭐⭐⭐ 중요: 기존 댓글들을 우선적으로 분석하고, 기존 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요. 본문보다 기존 댓글 스타일에 더 중점을 두세요. 기존 댓글의 의미와 핵심 단어를 유지하고 말투만 자연스럽게 바꾸세요.\n" if existing_comments and len(existing_comments) > 0 else ""
            
            title_section = f"\n게시글 제목:\n{post_title if post_title else '(제목 없음)'}\n" if post_title else ""
            context_block = post_context_text if post_context_text else ""
            length_instruction = f"\n\n📏 댓글 길이 가이드: 기본 10글자, 최대 {max_comment_length}글자 이내로 작성하세요.\n"
            
            # 댓글을 본문보다 먼저 배치하여 우선 확인하도록 변경
            if existing_comments and len(existing_comments) > 0:
                # 댓글이 있으면 댓글을 먼저, 본문을 나중에 배치
                prompt = f"""{base_prompt_section}{gambling_terms_text}{context_block}{length_instruction}{comments_priority_text}

⭐⭐⭐ 가장 먼저 확인: 기존 댓글들 (본문보다 우선!)
{comments_text}

{title_section}게시글 본문 (참고용):
{post_content[:500]}{keywords_text}{question_guide}{few_shot_text}{bad_examples_text}

댓글:"""
            else:
                # 댓글이 없으면 기존 순서 유지
                prompt = f"""{base_prompt_section}{gambling_terms_text}{context_block}{length_instruction}{comments_priority_text}{keywords_text}{question_guide}

{title_section}게시글 본문:
{post_content[:500]}{comments_text}{few_shot_text}{bad_examples_text}

댓글:"""

            print("[AI] OpenAI API 호출 중...")
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {api_key.strip()}',
                    'Content-Type': 'application/json'
                }
                
                system_prompt = (
                    "당신은 도박 관련 사이트의 자유게시판에서 게시글 작성자의 톤과 내용에 맞춰 친근하지만 자연스러운 댓글을 작성하는 도우미입니다. "
                    "자유게시판이므로 도박 관련 얘기뿐만 아니라 일상 수다도 올라올 수 있습니다. 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 댓글을 작성해야 합니다. "
                    "가장 중요한 것은: 1) ⭐ 기존 댓글들이 사용하는 핵심 단어/표현을 그대로 사용하세요. 예: 기존 댓글에 \"아이구\", \"에고\"가 있으면 당신도 \"아이고\", \"아이구\" 같은 표현 사용. "
                    "2) 기존 댓글들의 스타일을 우선적으로 분석하고 그에 맞춰 작성하세요. 기존 댓글들이 특수 기호(~, !, ㅠ 등)를 사용한다면 당신도 사용하고, 사용하지 않는다면 사용하지 마세요. "
                    "3) 본문의 말투를 정확히 분석하는 것입니다 (본문이 \"~할까요?\" 같은 존댓말이면 댓글도 \"~요\", \"~네요\" 같은 높임말 사용, 본문이 반말이면 댓글도 반말 사용). "
                    "4) 본문의 핵심 키워드를 추출하여 댓글에 자연스럽게 활용하세요 (예: 본문에 \"야식\"이 있으면 \"야식 좋지요\"처럼 키워드를 포함). "
                    "5) 마침표(.)는 절대 사용하지 마세요. 6) \"용\" 어미는 절대 사용하지 마세요 (예: \"힘내용\" ❌ → \"힘내요\" ✅). "
                    "7) 질문형 게시글에서 답을 모르면 댓글을 작성하지 마세요. 8) 기존 댓글들의 말투와 스타일을 분석하여 최대한 비슷하게 작성하세요. "
                    f"9) 반드시 {max_comment_length}글자 이내로 완성하고, 맞춤법을 정확하게 사용하세요. "
                    "10) 절대 \"감사합니다\", \"감사해요\", \"감사\" 같은 단어를 사용하지 말고, 형식적인 댓글을 사용하지 마세요. "
                    "11) 기존 댓글들이 말하는 핵심 내용과 키워드를 벗어나지 말고, 말투만 자연스럽게 바꿔 표현하세요. 새로운 정보나 다른 주제를 추가하지 마세요. "
                    "12) ⚠️⚠️⚠️ 반드시 \"이유:\"와 \"댓글:\" 두 줄로 출력하세요. 댓글만 출력하면 안 됩니다! "
                    "13) ⚠️⚠️⚠️ \"이유:\" 필드에는 반드시 논리적인 이유를 작성하세요. 예: \"기존 댓글들이 '아이구', '에고' 같은 공감 표현을 사용하므로 비슷한 공감 표현으로 작성\" 또는 \"기존 댓글들이 '천포', '냠냠' 같은 단어를 사용하므로 동일한 단어를 활용\" 등. 절대 \"이유 없음\"이라고 작성하지 마세요! "
                    "14) ⚠️⚠️⚠️ 댓글은 반드시 완전한 문장으로 끝맺어야 합니다. 예: \"밖에 엄청\" ❌ → \"밖에 엄청 추워요\" ✅, \"한번씩 하시\" ❌ → \"한번씩 하시네요\" ✅. 댓글이 중간에 끊기거나 어눌하게 끝나면 안 됩니다!"
                )
                
                data = {
                    'model': 'gpt-3.5-turbo',
                    'messages': [
                        {
                            'role': 'system',
                            'content': system_prompt
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'max_tokens': 150,  # 이유 설명 포함하여 토큰 증가
                    'temperature': 0.9  # 다양성 증가 (0.7 -> 0.9로 통일)
                }
                
                async with session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    response_text = await response.text()
                    
                    if response.status == 200:
                        result = json.loads(response_text)
                        ai_response = result['choices'][0]['message']['content'].strip()
                        
                        print(f"[AI] 원본 응답: {ai_response}")
                        
                        # 이유와 댓글 파싱
                        reason = ""
                        comment = ""
                        
                        if "이유:" in ai_response and "댓글:" in ai_response:
                            # 이유와 댓글이 모두 있는 경우
                            parts = ai_response.split("댓글:")
                            if len(parts) == 2:
                                reason_part = parts[0].replace("이유:", "").strip()
                                comment = parts[1].strip()
                                reason = reason_part
                                
                                # 이유가 비어있거나 "이유 없음"이면 재시도
                                if not reason or reason == "이유 없음" or len(reason.strip()) < 5:
                                    print(f"[경고] AI가 이유를 제대로 작성하지 않았습니다: '{reason}'")
                                    print(f"[경고] AI에게 다시 요청합니다...")
                                    return await self.generate_ai_comment_retry(post_content, existing_comments, retry_count=1)
                        elif "댓글:" in ai_response:
                            # 댓글만 있는 경우 - 재시도
                            print(f"[경고] AI가 '이유:' 필드를 작성하지 않았습니다.")
                            print(f"[경고] AI에게 다시 요청합니다...")
                            return await self.generate_ai_comment_retry(post_content, existing_comments, retry_count=1)
                        else:
                            # 기존 형식 (댓글만) - 재시도
                            print(f"[경고] AI가 올바른 형식('이유:'와 '댓글:')으로 응답하지 않았습니다.")
                            print(f"[경고] AI에게 다시 요청합니다...")
                            return await self.generate_ai_comment_retry(post_content, existing_comments, retry_count=1)
                        
                        # 댓글이 완전한 문장으로 끝맺어지는지 확인
                        # 어미로 끝나지 않거나 중간에 끊긴 것처럼 보이는 경우 체크
                        comment_clean = comment.rstrip('~!?ㅠㅜㅎㅋ').strip()
                        # 한글 어미로 끝나는지 확인 (요, 네요, 어요, 해요, 되요, 다요, 세요, 까요, 나요, 지요, 죠, 다, 어, 해, 되, 까, 나, 세, 지, 야 등)
                        has_proper_ending = bool(re.search(r'(요|네요|어요|해요|되요|다요|세요|까요|나요|지요|죠|다|어|해|되|까|나|세|지|야)$', comment_clean))
                        
                        # 댓글이 너무 짧거나(2글자 미만) 어미가 없으면 재시도
                        if len(comment_clean) < 2 or (len(comment_clean) >= 3 and not has_proper_ending):
                            print(f"[경고] 댓글이 완전한 문장으로 끝맺어지지 않았습니다: '{comment}'")
                            print(f"[경고] AI에게 다시 요청합니다...")
                            return await self.generate_ai_comment_retry(post_content, existing_comments, retry_count=1)
                        
                        # 따옴표 제거
                        comment = comment.strip('"').strip("'")
                        
                        # 로그 파일에 기록
                        await self.log_ai_comment_process(
                            post_content=post_content,
                            post_title=post_title,
                            existing_comments=existing_comments,
                            prompt=prompt,
                            ai_response=ai_response,
                            reason=reason,
                            final_comment=comment
                        )
                        
                        # 형식적인 댓글 필터링
                        forbidden_comments = [
                            '좋은 글 감사합니다',
                            '좋은 정보 감사합니다',
                            '유용한 정보네요',
                            '유용한 정보 감사합니다',
                            '잘 읽었습니다',
                            '도움이 되었어요',
                            '도움이 됐어요',
                            '도움이 되었습니다',
                            '감사합니다',
                            '감사해요',
                            '감사',
                            '좋은 글',
                            '유용한 정보',
                        ]
                        
                        comment_lower = comment.lower()
                        
                        # "감사" 단어가 포함된 댓글 필터링
                        if '감사' in comment:
                            print(f"[경고] '감사' 단어가 포함된 댓글 감지: {comment}")
                            print(f"[경고] AI에게 다시 요청합니다...")
                            return await self.generate_ai_comment_retry(post_content, existing_comments, retry_count=1)
                        
                        # 형식적인 댓글 필터링
                        for forbidden in forbidden_comments:
                            if forbidden in comment_lower:
                                print(f"[경고] 형식적인 댓글 감지: {comment}")
                                print(f"[경고] AI에게 다시 요청합니다...")
                                return await self.generate_ai_comment_retry(post_content, existing_comments, retry_count=1)
                        
                        comment_lower = comment.lower()
                        for forbidden in forbidden_comments:
                            if forbidden in comment_lower:
                                print(f"[경고] 형식적인 댓글 감지: {comment}")
                                print(f"[경고] AI에게 다시 요청합니다...")
                                # 다시 시도 (한 번만)
                                return await self.generate_ai_comment_retry(post_content, existing_comments, retry_count=1)
                        
                        # 길이 초과 시 재시도 (잘라내지 말고 처음부터 제한 길이 이내로 작성하도록)
                        if len(comment) > max_comment_length:
                            print(f"[경고] 댓글이 최대 길이({max_comment_length}자)를 초과했습니다 ({len(comment)}자): {comment}")
                            print(f"[경고] 길이 제한에 맞춰 재생성합니다...")
                            return await self.generate_ai_comment_retry(post_content, existing_comments, 1, post_title=getattr(self, '_last_post_title', None))
                        
                        # ~입니다 체 제거 및 ~요 체로 변경
                        comment = comment.replace('입니다', '요').replace('입니다.', '요').replace('입니다!', '요')
                        
                        # 중복 어미 및 불필요한 문자 제거
                        comment = self.clean_comment(comment)
                        
                        # 최종 필터링: "감사" 단어 재확인 (절대 안전장치)
                        if '감사' in comment:
                            print(f"[경고] ⚠️⚠️ 최종 필터링: '감사' 단어가 포함된 댓글 감지: {comment}")
                            print(f"[경고] AI 재시도 실패, 기존 댓글 스타일로 댓글 생성...")
                            return self.generate_style_matched_comment(existing_comments or [], post_content)
                        
                        if existing_comments and self.is_comment_too_similar(comment, existing_comments):
                            print(f"[경고] 최근 댓글과 유사도가 높아 재생성 시도: {comment}")
                            regenerated = await self.generate_ai_comment_retry(
                                post_content,
                                existing_comments,
                                retry_count=1,
                                post_title=post_title
                            )
                            if regenerated and not self.is_comment_too_similar(regenerated, existing_comments):
                                comment = regenerated
                            else:
                                print("[경고] 재생성 댓글도 비슷하거나 실패하여 기본 스타일 댓글로 전환합니다.")
                                return self.generate_style_matched_comment(existing_comments or [], post_content)
                        
                        print(f"[AI] 댓글 생성 완료: {comment}")
                        return comment
                    else:
                        print(f"[오류] AI 댓글 생성 실패!")
                        print(f"[오류] 상태 코드: {response.status}")
                        print(f"[오류] 응답 내용: {response_text[:500]}")
                        
                        # 401 오류 처리 (권한 문제)
                        if response.status == 401:
                            print(f"[경고] ⚠️ OpenAI API 권한 오류 (401)!")
                            print(f"[경고] API 키에 모델 사용 권한이 없습니다.")
                            print(f"[경고] 해결 방법:")
                            print(f"[경고] 1. OpenAI 계정에 로그인: https://platform.openai.com")
                            print(f"[경고] 2. API Keys 페이지로 이동: https://platform.openai.com/api-keys")
                            print(f"[경고] 3. 새로운 API 키 생성 (Owner 또는 Writer 권한 필요)")
                            print(f"[경고] 4. 생성한 새 API 키를 .env 파일에 입력")
                            if api_key:
                                print(f"[경고] 현재 API 키: {api_key[:20]}... (처음 20자)")
                        
                        # 할당량 초과 오류 처리
                        if response.status == 429:
                            if 'quota' in response_text.lower() or 'exceeded' in response_text.lower():
                                print(f"[경고] ⚠️ OpenAI API 할당량이 초과되었습니다!")
                                print(f"[경고] OpenAI 계정에서 크레딧을 충전하세요.")
                                print(f"[경고] 할당량 확인: https://platform.openai.com/usage")
                        
                        if api_key:
                            print(f"[오류] API 키 확인: {api_key[:20]}... (처음 20자)")
                        else:
                            print(f"[오류] API 키가 None입니다!")
                        
                        import traceback
                        traceback.print_exc()
                        print(f"[댓글] 기존 댓글 스타일을 참고하여 댓글 생성...")
                        return self.generate_style_matched_comment(existing_comments or [], post_content)
                        
        except asyncio.TimeoutError:
            print("[경고] AI 댓글 생성 시간 초과 (15초). 기존 댓글 스타일로 댓글 생성...")
            return self.generate_style_matched_comment(existing_comments or [], post_content)
        except Exception as e:
            print(f"[오류] AI 댓글 생성 중 오류 발생!")
            print(f"[오류] 오류 내용: {e}")
            if api_key:
                print(f"[오류] API 키 확인: {api_key[:20]}... (처음 20자)")
            else:
                print(f"[오류] API 키가 None입니다!")
            import traceback
            traceback.print_exc()
            print(f"[댓글] 기존 댓글 스타일을 참고하여 댓글 생성...")
            return self.generate_style_matched_comment(existing_comments or [], post_content)
    
    async def generate_ai_comment_retry(self, post_content: str, existing_comments: list = None, retry_count: int = 0, post_title: str = None) -> str:
        """AI 댓글 생성 재시도 (형식적인 댓글 필터링 후)"""
        if retry_count <= 0:
            # 재시도 횟수 초과 시 기존 댓글 스타일로 댓글 생성
            print("[경고] 재시도 횟수 초과. 기존 댓글 스타일로 댓글 생성...")
            return self.generate_style_matched_comment(existing_comments or [], post_content)
        
        api_key = self.config.get('openai_api_key')
        
        try:
            if existing_comments and len(existing_comments) > 0:
                numbered_comments = "\n".join(
                    [f"{idx + 1}. {c}" for idx, c in enumerate(existing_comments[:8])]
                )
                comments_text = f"\n\n⭐⭐⭐ 가장 중요: 현재 댓글 흐름 (최근 {min(len(existing_comments), 8)}개):\n{numbered_comments}\n\n위 댓글들을 우선적으로 분석하고, 위 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요. 본문보다 기존 댓글 스타일에 더 중점을 두세요.\n- 위 댓글들이 사용하는 핵심 단어와 감정을 그대로 유지하고, 말투만 자연스럽게 바꿔 작성하세요.\n- 새로운 정보나 다른 주제를 절대 추가하지 마세요.\n"
            else:
                comments_text = "\n\n현재 댓글 흐름: (댓글 없음)"
            
            # 기존 댓글 우선 강조 텍스트
            comments_priority_text = "\n\n⭐⭐⭐ 가장 중요: 기존 댓글들을 우선적으로 분석하고, 기존 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요. 본문보다 기존 댓글 스타일에 더 중점을 두세요. 기존 댓글의 핵심 내용과 키워드를 유지하고 말투만 자연스럽게 바꾸세요.\n" if existing_comments and len(existing_comments) > 0 else ""
            
            # 본문에서 핵심 키워드 추출
            keywords = self.extract_keywords_from_post(post_content, post_title)
            keywords_text = ""
            if keywords:
                keywords_text = f"\n\n🔑 본문 핵심 키워드: {', '.join(keywords)}\n- 위 키워드들을 댓글에 자연스럽게 활용하세요.\n- 예: 본문에 '야식'이 있으면 '야식 좋지요'처럼 키워드를 포함한 댓글을 작성하세요.\n"
            
            # 질문형 게시글 확인
            is_question = any(q in post_content for q in ['?', '?', '어떻게', '뭐가', '어떤', '언제', '어디', '누가', '왜', '몇시', '몇시쯤'])
            question_guide = ""
            if is_question:
                question_guide = "\n\n⚠️ 질문형 게시글입니다:\n- 질문에 대한 답을 모르면 댓글을 작성하지 마세요.\n- 답을 알고 있거나 공감할 수 있는 내용만 댓글로 작성하세요.\n"
            
            post_emotion = self.analyze_post_emotion(post_content, post_title or "")
            post_type = self.classify_post_type(post_content, post_title or "")
            post_date = getattr(self, '_last_post_date', None)
            temporal_context = self.get_temporal_context(post_date)
            max_comment_length = self.get_optimal_comment_length(existing_comments)
            community_terms = self.extract_community_terms(f"{post_title or ''}\n{post_content or ''}")
            context_block = self.build_post_context_text(post_emotion, post_type, temporal_context, max_comment_length, community_terms)
            length_instruction = f"\n- 현재 최대 길이: {max_comment_length}글자 (기본 10글자)\n"
            
            # 더 강력한 프롬프트 (통일된 버전)
            prompt = f"""다음 게시글 본문을 읽고, 작성자의 감정에 공감하는 댓글을 작성해주세요.

⚠️ 중요: 이 게시판은 도박 관련 사이트의 자유게시판입니다.
- 자유게시판이기 때문에 도박과 관련된 얘기뿐만 아니라 일상 수다도 올라올 수 있습니다
- 게시글 주제가 도박이든 일상이든 상관없이, 본문 내용과 기존 댓글 흐름에 맞춰 작성해야 합니다
- 댓글은 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 작성해야 합니다

🎯 핵심 원칙 (우선순위 순 - 반드시 이 순서로 진행):
1. ⭐⭐⭐ 가장 중요: 기존 댓글들을 먼저 분석하세요! (본문보다 우선!)
   - 기존 댓글들의 말투, 스타일, 길이, 감정선을 정확히 파악
   - 기존 댓글들과 최대한 비슷한 스타일로 댓글 작성
   - 본문은 나중에 참고용으로만 사용
2. ⭐⭐ 두 번째: 기존 댓글 스타일을 따라 댓글 설계
   - 기존 댓글들의 말투 패턴을 우선 확인
   - 기존 댓글이 대부분 존댓말이면 존댓말로, 반말이면 반말로 작성
   - 본문 말투는 무시하고 기존 댓글 말투를 따라야 함
3. 본문은 참고용으로만 사용 (기존 댓글 스타일 유지하면서)
   - 본문의 핵심 키워드만 선택적으로 활용
   - 본문 말투는 기존 댓글 말투와 다를 수 있으므로 무시
4. 특수 기호 사용: 기존 댓글들이 특수 기호(~, !, ㅠ 등)를 사용한다면 그에 맞춰 사용하고, 사용하지 않는다면 사용하지 마세요
5. 마침표(.) 절대 사용 금지
6. "용" 어미 절대 사용 금지
7. 질문형 게시글: 답을 모르면 댓글 작성하지 않음
8. 반드시 {max_comment_length}글자 이내로 완성 (기본 10글자, 현재 한도 {max_comment_length}글자)

절대 사용하지 말 것 (금지):
- "좋은 글 감사합니다"
- "유용한 정보 감사합니다"  
- "유용한 정보네요"
- "잘 읽었습니다"
- "도움이 되었어요" (절대 금지)
- "도움이 됐어요" (절대 금지)
- "도움이 되었습니다" (절대 금지)
- "감사합니다" (절대 금지)
- "감사해요" (절대 금지)
- "감사" (절대 금지)
- "감사"라는 단어가 포함된 모든 댓글

반드시 해야 할 것:
- 작성자의 톤과 감정을 파악하고 그에 맞춰 댓글 작성
- 친구처럼 편하게 쓴 글 → 친구처럼 편하게 반말이나 캐주얼한 댓글
- 형식적인 글 → 형식적인 댓글 (하지만 "감사합니다" 같은 금지 단어는 사용하지 말 것)
- 시답잖은 소리 → 그냥 맞춰주기만 하면 됨 (꼭 긍정적일 필요 없음)
- 특수 기호 사용: 기존 댓글들이 특수 기호(~, !, ㅠ 등)를 사용한다면 그에 맞춰 사용하고, 사용하지 않는다면 사용하지 마세요
- 예: "힘내요" → "힘내요", "좋아요" → "좋아요", "대박이네요" → "대박이네요", "아쉽네요" → "아쉽네요"
- 기분 좋은 글이면 담담하게 축하하고, 힘든 글이면 현실적인 톤(예: "아 지치네요", "버텨야죠")도 괜찮음
- 맞춤법을 반드시 정확하게 사용
- 게시판이 도박 관련이라는 맥락을 고려
- 게시글 내용과 기존 댓글 흐름 모두에 자연스럽게 이어지는 댓글
- 댓글 길이는 {max_comment_length}글자 이내로 작성 (기본 10글자)
- ~요 체나 반말체를 적절히 섞어서 사용 (너무 반말만 쓰지 않기)

추론 절차 (반드시 내부적으로 거친 뒤 마지막에 댓글 한 줄만 출력):
1. ⭐⭐⭐ 가장 먼저: 기존 댓글들을 정확히 분석합니다 (본문보다 우선!)
   - 기존 댓글들의 말투 패턴을 파악합니다 (존댓말/반말, 어미 패턴)
   - 기존 댓글들의 스타일과 길이를 분석합니다
   - 기존 댓글들의 감정선과 톤을 파악합니다
   - 기존 댓글들이 어떤 패턴으로 작성되었는지 정확히 이해합니다. (생각만, 출력 금지)
2. ⭐⭐ 두 번째: 기존 댓글 스타일을 따라 댓글을 설계합니다
   - 기존 댓글들의 말투 패턴을 따라 작성합니다
   - 기존 댓글들의 길이와 스타일을 따라 작성합니다
   - 기존 댓글들의 감정선을 자연스럽게 이어갑니다. (생각만, 출력 금지)
3. 본문은 참고용으로만 사용합니다 (기존 댓글 스타일을 유지하면서)
   - 본문의 핵심 키워드만 참고합니다 (말투는 기존 댓글 말투를 우선)
   - 기존 댓글 말투와 본문 말투가 다를 수 있으므로, 기존 댓글 말투를 우선합니다. (생각만, 출력 금지)
4. 위 정보를 합쳐 {max_comment_length}글자 이내 댓글을 설계합니다. 기존 댓글들이 특수 기호를 사용한다면 그에 맞춰 사용하세요.
최종 출력은 댓글 한 줄만 해야 하며, 다른 문장은 포함하면 안 됩니다.

{comments_priority_text}{context_block}{length_instruction}

게시글 본문:
{post_content[:500]}{comments_text}

댓글:"""

            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {api_key.strip()}',
                    'Content-Type': 'application/json'
                }
                
                system_prompt_retry = (
                    "당신은 도박 관련 사이트의 자유게시판에서 게시글 작성자의 톤과 내용에 맞춰 친근하지만 자연스러운 댓글을 작성하는 도우미입니다. "
                    "자유게시판이므로 도박 관련 얘기뿐만 아니라 일상 수다도 올라올 수 있습니다. 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 댓글을 작성해야 합니다. "
                    "가장 중요한 것은: 1) ⭐ 기존 댓글들이 사용하는 핵심 단어/표현을 그대로 사용하세요. 예: 기존 댓글에 \"아이구\", \"에고\"가 있으면 당신도 \"아이고\", \"아이구\" 같은 표현 사용. "
                    "2) 기존 댓글들의 스타일을 우선적으로 분석하고 그에 맞춰 작성하세요. 기존 댓글들이 특수 기호(~, !, ㅠ 등)를 사용한다면 당신도 사용하고, 사용하지 않는다면 사용하지 마세요. "
                    "3) 본문의 말투를 정확히 분석하는 것입니다 (본문이 \"~할까요?\" 같은 존댓말이면 댓글도 \"~요\", \"~네요\" 같은 높임말 사용, 본문이 반말이면 댓글도 반말 사용). "
                    "4) 본문의 핵심 키워드를 추출하여 댓글에 자연스럽게 활용하세요 (예: 본문에 \"야식\"이 있으면 \"야식 좋지요\"처럼 키워드를 포함). "
                    "5) 마침표(.)는 절대 사용하지 마세요. 6) \"용\" 어미는 절대 사용하지 마세요 (예: \"힘내용\" ❌ → \"힘내요\" ✅). "
                    "7) 질문형 게시글에서 답을 모르면 댓글을 작성하지 마세요. 8) 기존 댓글들의 말투와 스타일을 분석하여 최대한 비슷하게 작성하세요. "
                    f"9) 반드시 {max_comment_length}글자 이내로 완성하고, 맞춤법을 정확하게 사용하세요. "
                    "10) 절대 \"감사합니다\", \"감사해요\", \"감사\" 같은 단어를 사용하지 말고, 형식적인 댓글을 사용하지 마세요. "
                    "11) 기존 댓글들이 말하는 핵심 내용과 키워드를 벗어나지 말고, 말투만 자연스럽게 바꿔 표현하세요. 새로운 정보나 다른 주제를 추가하지 마세요. "
                    "12) ⚠️⚠️⚠️ 반드시 \"이유:\"와 \"댓글:\" 두 줄로 출력하세요. 댓글만 출력하면 안 됩니다! "
                    "13) ⚠️⚠️⚠️ \"이유:\" 필드에는 반드시 논리적인 이유를 작성하세요. 예: \"기존 댓글들이 '아이구', '에고' 같은 공감 표현을 사용하므로 비슷한 공감 표현으로 작성\" 또는 \"기존 댓글들이 '천포', '냠냠' 같은 단어를 사용하므로 동일한 단어를 활용\" 등. 절대 \"이유 없음\"이라고 작성하지 마세요! "
                    "14) ⚠️⚠️⚠️ 댓글은 반드시 완전한 문장으로 끝맺어야 합니다. 예: \"밖에 엄청\" ❌ → \"밖에 엄청 추워요\" ✅, \"한번씩 하시\" ❌ → \"한번씩 하시네요\" ✅. 댓글이 중간에 끊기거나 어눌하게 끝나면 안 됩니다!"
                )
                
                data = {
                    'model': 'gpt-3.5-turbo',
                    'messages': [
                        {
                            'role': 'system',
                            'content': system_prompt_retry
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'max_tokens': 150,  # 이유 설명 포함하여 토큰 증가
                    'temperature': 0.9  # 다양성 증가 (0.7 -> 0.9로 통일)
                }
                
                async with session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 200:
                        result = json.loads(await response.text())
                        ai_response = result['choices'][0]['message']['content'].strip()
                        
                        print(f"[AI] 재시도 원본 응답: {ai_response}")
                        
                        # 이유와 댓글 파싱
                        reason = ""
                        comment = ""
                        
                        if "이유:" in ai_response and "댓글:" in ai_response:
                            # 이유와 댓글이 모두 있는 경우
                            parts = ai_response.split("댓글:")
                            if len(parts) == 2:
                                reason_part = parts[0].replace("이유:", "").strip()
                                comment = parts[1].strip()
                                reason = reason_part
                                
                                # 이유가 비어있거나 "이유 없음"이면 재시도
                                if not reason or reason == "이유 없음" or len(reason.strip()) < 5:
                                    print(f"[경고] 재시도: AI가 이유를 제대로 작성하지 않았습니다: '{reason}'")
                                    print(f"[경고] 기존 댓글 스타일로 댓글 생성...")
                                    return self.generate_style_matched_comment(existing_comments or [], post_content)
                        elif "댓글:" in ai_response:
                            # 댓글만 있는 경우
                            parts = ai_response.split("댓글:")
                            if len(parts) == 2:
                                comment = parts[1].strip()
                                reason = "이유 없음"
                        else:
                            # 기존 형식 (댓글만)
                            comment = ai_response
                            reason = "이유 없음"
                        
                        # 댓글이 완전한 문장으로 끝맺어지는지 확인
                        comment_clean = comment.rstrip('~!?ㅠㅜㅎㅋ').strip()
                        has_proper_ending = bool(re.search(r'(요|네요|어요|해요|되요|다요|세요|까요|나요|지요|죠|다|어|해|되|까|나|세|지|야)$', comment_clean))
                        
                        # 댓글이 너무 짧거나(2글자 미만) 어미가 없으면 기존 스타일 사용
                        if len(comment_clean) < 2 or (len(comment_clean) >= 3 and not has_proper_ending):
                            print(f"[경고] 재시도: 댓글이 완전한 문장으로 끝맺어지지 않았습니다: '{comment}'")
                            print(f"[경고] 기존 댓글 스타일로 댓글 생성...")
                            return self.generate_style_matched_comment(existing_comments or [], post_content)
                        
                        # 따옴표 제거
                        comment = comment.strip('"').strip("'")
                        
                        # 중복 어미 및 불필요한 문자 제거
                        comment = self.clean_comment(comment)
                        
                        # 길이 초과 시 기존 스타일 사용
                        if len(comment) > max_comment_length:
                            print(f"[경고] 재시도 댓글이 최대 길이({max_comment_length}자)를 초과했습니다 ({len(comment)}자): {comment}")
                            print(f"[경고] 기존 댓글 스타일로 댓글 생성...")
                            return self.generate_style_matched_comment(existing_comments or [], post_content)
                        
                        comment = comment.replace('입니다', '요').replace('입니다.', '요')
                        # 다시 한 번 정리 (replace 후에도 중복이 생길 수 있음)
                        comment = self.clean_comment(comment)
                        print(f"[AI] 재시도 댓글 생성 완료: {comment}")
                        return comment
                    else:
                        print(f"[댓글] 기존 댓글 스타일을 참고하여 댓글 생성...")
                        return self.generate_style_matched_comment(existing_comments or [], post_content)
        except Exception as e:
            print(f"[오류] OpenAI 재시도 오류: {e}")
            print(f"[댓글] 기존 댓글 스타일을 참고하여 댓글 생성...")
            return self.generate_style_matched_comment(existing_comments or [], post_content)
    
    async def write_comment(self, post_url: str):
        """게시글에 댓글 작성"""
        print(f"[댓글] ========================================")
        print(f"[댓글] write_comment 함수 시작: {post_url}")
        print(f"[댓글] 현재 페이지 URL: {self.page.url}")
        print(f"[댓글] ========================================")
        try:
            # 페이지가 닫혔는지 확인 (Frame과 Page 구분)
            page_closed = False
            if not self.page:
                page_closed = True
            else:
                try:
                    # Page 객체인 경우
                    if hasattr(self.page, 'is_closed'):
                        page_closed = self.page.is_closed()
                    # Frame 객체인 경우 (is_closed 메서드 없음) - main_page 확인
                    elif self.main_page and hasattr(self.main_page, 'is_closed'):
                        page_closed = self.main_page.is_closed()
                except:
                    page_closed = True
            
            if page_closed:
                print("[오류] 페이지가 이미 닫혔습니다. 브라우저를 다시 초기화합니다.")
                await self.reset_browser(headless=False)
            
            print(f"[댓글] {post_url} 접속 중...")
            try:
                await self.page.goto(post_url, wait_until='networkidle', timeout=30000)
                # 페이지 로드 후 추가 대기
                await self.random_delay(2, 3)
                # 스크롤하여 댓글 영역이 보이도록
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await self.random_delay(1, 2)
            except AttributeError as attr_err:
                if "_object" in str(attr_err):
                    print("[오류] 페이지 객체가 손상되었습니다. 브라우저를 재시작합니다.")
                    await self.reset_browser(headless=False)
                    await self.page.goto(post_url, wait_until='networkidle', timeout=30000)
                    await self.random_delay(2, 3)
                    await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await self.random_delay(1, 2)
                else:
                    raise
            except Exception as goto_error:
                if "_object" in str(goto_error):
                    print("[오류] 페이지 이동 중 Playwright 채널 오류가 발생했습니다. 브라우저를 재시작합니다.")
                    await self.reset_browser(headless=False)
                    await self.page.goto(post_url, wait_until='networkidle', timeout=30000)
                    await self.random_delay(2, 3)
                    await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await self.random_delay(1, 2)
                else:
                    raise
            await self.random_delay(2, 4)
            
            # 페이지 로드 확인
            current_url = self.page.url
            print(f"[댓글] 현재 페이지 URL: {current_url}")
            
            # 게시글 작성 시간 확인 (24시간 이내인지 체크)
            print("[댓글] ========================================")
            print("[댓글] 게시글 작성 시간 확인 중...")
            print("[댓글] ========================================")
            try:
                # 현재 페이지에서 작성 시간 가져오기
                post_date = await self.get_post_date_from_current_page()
                self._last_post_date = post_date
                if post_date:
                    now = datetime.now()
                    time_diff = now - post_date
                    hours_ago = time_diff.total_seconds() / 3600
                    
                    print(f"[댓글] 게시글 작성 시간: {post_date.strftime('%Y-%m-%d %H:%M')} ({hours_ago:.1f}시간 전)")
                    
                    if hours_ago > 24:
                        print(f"[건너뛰기] 게시글이 24시간을 초과했습니다. ({hours_ago:.1f}시간 전)")
                        print(f"[댓글] 댓글 작성을 건너뜁니다.")
                        return False
                    else:
                        print(f"[확인] 게시글이 24시간 이내입니다. ({hours_ago:.1f}시간 전) - 댓글 작성 진행")
                else:
                    print("[경고] 게시글 작성 시간을 확인할 수 없습니다. 댓글을 작성합니다.")
                    self._last_post_date = None
            except Exception as e:
                print(f"[경고] 게시글 작성 시간 확인 중 오류: {e}")
                import traceback
                traceback.print_exc()
                print("[경고] 댓글을 작성합니다.")
            
            # 게시글 제목 가져오기
            print("[댓글] ========================================")
            print("[댓글] 게시글 제목을 읽는 중...")
            print("[댓글] ========================================")
            post_title = await self.get_post_title()
            if post_title:
                print(f"[댓글] ✅ 제목 읽기 성공: {post_title}")
            else:
                print(f"[경고] 제목을 찾을 수 없습니다.")
            
            # 게시글 본문 가져오기
            print("[댓글] ========================================")
            print("[댓글] 게시글 본문을 읽는 중...")
            print("[댓글] ========================================")
            post_content = await self.get_post_content()
            
            print("[댓글] ========================================")
            print(f"[댓글] 본문 읽기 결과: 길이={len(post_content) if post_content else 0}자")
            if post_content and len(post_content.strip()) > 10:
                print(f"[댓글] ✅ 본문 읽기 성공!")
                print(f"[댓글] 본문 전체 내용 (처음 500자):")
                print(f"  {post_content[:500]}")
                print(f"[댓글] ========================================")
            else:
                print(f"[경고] ⚠️⚠️⚠️ 본문이 비어있거나 너무 짧습니다!")
                print(f"[경고] 본문 내용: '{post_content}'")
                print(f"[경고] 본문 읽기 함수를 확인하세요!")
                print(f"[경고] ========================================")
            
            # 기존 댓글들 가져오기
            print("[댓글] ========================================")
            print("[댓글] 기존 댓글들을 확인하는 중...")
            print("[댓글] ========================================")
            # 댓글 영역까지 스크롤하여 모든 댓글이 로드되도록 보장
            try:
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await self.random_delay(1, 2)
            except Exception:
                pass
            
            existing_comments = await self.get_existing_comments()
            
            print("[댓글] ========================================")
            print(f"[댓글] 댓글 읽기 결과: {len(existing_comments) if existing_comments else 0}개 발견")
            if existing_comments and len(existing_comments) > 0:
                print(f"[댓글] ✅ 기존 댓글 {len(existing_comments)}개 발견")
                for i, comment in enumerate(existing_comments[:5], 1):
                    print(f"  {i}. {comment[:100]}")
                print(f"[댓글] ========================================")
            else:
                print(f"[경고] ⚠️⚠️⚠️ 기존 댓글이 없습니다!")
                print(f"[경고] 댓글이 없는 게시글에는 댓글을 작성하지 않습니다.")
                print(f"[경고] ========================================")
                # 댓글이 없는 게시글은 댓글 작성하지 않음
                # 재방문 방지를 위해 URL 저장
                current_url = self.page.url
                self.save_commented_post(current_url)
                print(f"[중복방지] 댓글이 없는 게시글을 기록했습니다: {current_url}")
                return False
            
            if post_content and len(post_content.strip()) > 10:
                print(f"[댓글] 본문 읽기 성공! (길이: {len(post_content)}자)")
                print(f"[댓글] 본문 미리보기: {post_content[:100]}...")
                
                # AI로 댓글 생성 (제목 + 본문 + 기존 댓글 고려)
                print("[댓글] ⭐ AI 댓글 생성 시작...")
                comment_text = await self.generate_ai_comment(post_content, existing_comments, post_title)
                print(f"[댓글] AI 생성 댓글: {comment_text}")
                
                # 최종 확인: "감사" 단어가 있으면 기본 댓글 사용 (절대 안전장치)
                if '감사' in comment_text:
                    print(f"[경고] ⚠️⚠️⚠️ 최종 확인: '감사' 단어가 포함된 댓글 감지: {comment_text}")
                    print(f"[경고] AI가 '감사' 단어를 사용했습니다. 기존 댓글 스타일로 댓글 생성")
                    # 기존 댓글 스타일에 맞춰 댓글 생성
                    comment_text = self.generate_style_matched_comment(existing_comments, post_content)
            else:
                # 본문이 없으면 기존 댓글 스타일로 댓글 생성
                print("[경고] 게시글 본문을 찾을 수 없거나 너무 짧습니다.")
                if post_content:
                    print(f"[경고] 읽은 본문: {post_content[:50]}...")
                # 기존 댓글 스타일에 맞춰 댓글 생성
                comment_text = self.generate_style_matched_comment(existing_comments, post_content)
            
            # 내용이 없는 댓글 방지
            clean_attempts = 0
            while not self.has_meaningful_content(comment_text) and clean_attempts < 3:
                print(f"[경고] 내용이 부족한 댓글 감지: {comment_text}")
                if clean_attempts == 0:
                    comment_text = await self.generate_ai_comment_retry(post_content, existing_comments, 1)
                elif clean_attempts == 1:
                    comment_text = await self.generate_ai_comment_retry(post_content, existing_comments, 2)
                else:
                    comment_text = self.generate_style_matched_comment(existing_comments or [], post_content or '')
                clean_attempts += 1
            
            if not self.has_meaningful_content(comment_text):
                print("[경고] 의미 있는 댓글을 생성하지 못했습니다. 기본 문장을 사용합니다.")
                comment_text = "지치네요"
            
            # 중복 어미 제거 (요요, 네요요 등) - 모든 댓글에 적용
            comment_text = self.clean_comment(comment_text)
            
            # 댓글이 본문/제목과 관련이 있는지 확인
            if not self.is_comment_relevant_to_post(comment_text, post_content, post_title):
                print("[경고] ⚠️⚠️⚠️ 댓글이 게시글 제목/본문과 관련이 없거나 이해하지 못한 것으로 판단됩니다.")
                print("[경고] 이 게시글에는 댓글을 작성하지 않고 건너뜁니다.")
                # 이해할 수 없는 게시글도 기록하여 재방문 방지
                current_url = self.page.url
                self.save_commented_post(current_url)
                print(f"[중복방지] 이해할 수 없는 게시글을 기록했습니다: {current_url}")
                return False  # 댓글 작성하지 않고 건너뛰기
            
            # AI가 생성한 원본 댓글 저장
            ai_original_comment = comment_text
            
            # 15분 내 반복 댓글 방지
            comment_before_repeat_check = comment_text
            comment_text = await self.ensure_non_repeating_comment(comment_text, post_content, existing_comments)
            if comment_text != comment_before_repeat_check:
                print(f"[변경] 반복 방지로 댓글 변경: '{comment_before_repeat_check}' → '{comment_text}'")
            if not comment_text:
                print("[오류] 반복 댓글을 회피할 새 문장을 만들지 못했습니다.")
                return False
            
            # 어미/기호 다양화 (젊은층 톤 적용) - 특수 기호 추가 (기존 댓글 스타일 반영)
            comment_before_enhance = comment_text
            comment_text = self.enhance_tone_variation(comment_text, post_content, existing_comments)
            if comment_text != comment_before_enhance:
                print(f"[변경] 톤 다양화로 댓글 변경: '{comment_before_enhance}' → '{comment_text}'")
            
            # 최종 중복 어미만 제거 (특수 기호는 보존)
            # enhance_tone_variation 이후에는 특수 기호를 제거하지 않음
            comment_before_clean = comment_text
            comment_text = self.clean_comment_final_only(comment_text)
            if comment_text != comment_before_clean:
                print(f"[변경] 정리로 댓글 변경: '{comment_before_clean}' → '{comment_text}'")
            
            # 최종 댓글 로그 기록 (댓글 작성 직전)
            await self.log_final_comment(
                post_content=post_content,
                post_title=post_title,
                existing_comments=existing_comments,
                ai_original_comment=ai_original_comment,
                final_comment=comment_text,
                changes=[
                    ("반복 방지", comment_before_repeat_check, comment_text if comment_text != comment_before_repeat_check else None),
                    ("톤 다양화", comment_before_enhance, comment_text if comment_text != comment_before_enhance else None),
                    ("정리", comment_before_clean, comment_text if comment_text != comment_before_clean else None)
                ]
            )
            
            # 댓글 간 랜덤 대기
            await self.enforce_comment_gap()
            
            # 페이지가 닫혔는지 다시 확인 (Frame과 Page 구분)
            page_closed = False
            if not self.page:
                page_closed = True
            else:
                try:
                    # Page 객체인 경우
                    if hasattr(self.page, 'is_closed'):
                        page_closed = self.page.is_closed()
                    # Frame 객체인 경우 (is_closed 메서드 없음) - main_page 확인
                    elif self.main_page and hasattr(self.main_page, 'is_closed'):
                        page_closed = self.main_page.is_closed()
                except:
                    page_closed = True
            
            if page_closed:
                print("[오류] 페이지가 닫혔습니다. 댓글 작성 중단.")
                return False
            
            # 댓글 입력 필드 찾기 - 여러 선택자 시도
            comment_input_selector = self.config.get('comment_input_selector', 'textarea[name="wr_content"]')
            print(f"[댓글] 댓글 입력 필드 찾는 중: {comment_input_selector}")
            
            # 여러 선택자 시도 (실제 사이트 구조에 맞게 우선순위 조정)
            possible_comment_selectors = [
                # 실제 사이트의 정확한 선택자 (최우선)
                'textarea[name="wr_content"]',
                'textarea#wr_content',
                'textarea.wr_content',
                # 일반적인 댓글 필드 선택자
                comment_input_selector,
                'textarea[name="comment"]',
                'textarea[id*="comment"]',
                'textarea[id*="reply"]',
                'textarea[name*="comment"]',
                'textarea[name*="reply"]',
                'textarea[name*="content"]',  # wr_content도 매칭됨
                'textarea.comment',
                'textarea#comment',
                'textarea#reply',
                'textarea[placeholder*="댓글"]',
                'textarea[placeholder*="comment"]',
                'textarea[placeholder*="reply"]',
                # 폴백 선택자
                'textarea',
                'input[name="comment"]',
                'input[id*="comment"]',
                'input[type="text"][name*="comment"]',
                'input[type="text"][id*="comment"]',
                'div[contenteditable="true"]',  # contenteditable div
                'div[contenteditable="true"][id*="comment"]',
                'div[contenteditable="true"][class*="comment"]',
            ]
            
            found_comment_selector = None
            
            # 먼저 iframe 확인 (원본 page 저장)
            original_page = self.page
            if self.main_page is None:
                self.main_page = self.page
            
            try:
                # main_page가 있으면 그것을 사용, 없으면 현재 page 사용
                page_to_check = self.main_page if self.main_page else self.page
                frames = page_to_check.frames
                print(f"[디버깅] 페이지에 {len(frames)}개의 frame이 있습니다.")
                for i, frame in enumerate(frames):
                    try:
                        for selector in possible_comment_selectors[:5]:  # 처음 5개만 iframe에서 시도
                            try:
                                await frame.wait_for_selector(selector, timeout=1000, state='visible')
                                found_comment_selector = selector
                                print(f"[댓글] 댓글 입력 필드를 iframe {i}에서 찾음: {selector}")
                                # iframe에서 찾았으면 해당 frame 사용 (하지만 main_page는 유지)
                                self.page = frame
                                break
                            except:
                                continue
                        if found_comment_selector:
                            break
                    except:
                        continue
            except:
                pass
            
            # 메인 페이지에서 찾기
            if not found_comment_selector:
                for selector in possible_comment_selectors:
                    try:
                        # visible 상태로 찾기 시도
                        await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                        found_comment_selector = selector
                        print(f"[댓글] 댓글 입력 필드 찾음: {selector}")
                        break
                    except:
                        try:
                            # visible이 실패하면 attached 상태로 시도
                            await self.page.wait_for_selector(selector, timeout=1000, state='attached')
                            # 요소가 숨겨져 있을 수 있으니 강제로 보이게 만들기
                            element = await self.page.query_selector(selector)
                            if element:
                                await self.page.evaluate("""
                                    (el) => {
                                        el.style.display = 'block';
                                        el.style.visibility = 'visible';
                                        el.style.opacity = '1';
                                    }
                                """, element)
                                found_comment_selector = selector
                                print(f"[댓글] 댓글 입력 필드 찾음 (숨겨진 요소 활성화): {selector}")
                                break
                        except:
                            continue
            
            if not found_comment_selector:
                # 모든 선택자 실패 시 페이지 HTML 확인
                print("[디버깅] 페이지의 모든 textarea 요소 확인 중...")
                textareas = await self.page.query_selector_all('textarea')
                print(f"[디버깅] 발견된 textarea 요소 수: {len(textareas)}")
                for i, ta in enumerate(textareas[:10]):  # 처음 10개
                    try:
                        textarea_info = await ta.evaluate('el => ({type: el.type, name: el.name, id: el.id, class: el.className, placeholder: el.placeholder, visible: el.offsetParent !== null})')
                        print(f"[디버깅] Textarea {i+1}: {textarea_info}")
                    except:
                        pass
                
                # input 요소도 확인
                print("[디버깅] 페이지의 모든 input 요소 확인 중...")
                inputs = await self.page.query_selector_all('input')
                print(f"[디버깅] 발견된 input 요소 수: {len(inputs)}")
                for i, inp in enumerate(inputs[:10]):  # 처음 10개
                    try:
                        input_info = await inp.evaluate('el => ({type: el.type, name: el.name, id: el.id, class: el.className, placeholder: el.placeholder, visible: el.offsetParent !== null})')
                        print(f"[디버깅] Input {i+1}: {input_info}")
                    except:
                        pass
                
                # 페이지 HTML 일부 저장
                try:
                    page_html = await self.page.content()
                    # 댓글 관련 부분만 추출
                    import re
                    comment_section = re.search(r'(?i)(<form[^>]*>.*?</form>|<div[^>]*(?:comment|reply|댓글)[^>]*>.*?</div>)', page_html, re.DOTALL)
                    if comment_section:
                        with open('comment_section_debug.html', 'w', encoding='utf-8') as f:
                            f.write(comment_section.group(0))
                        print("[디버깅] 댓글 섹션 HTML 저장: comment_section_debug.html")
                    else:
                        # 전체 HTML 저장 (크기가 클 수 있음)
                        with open('page_debug.html', 'w', encoding='utf-8') as f:
                            f.write(page_html[:50000])  # 처음 50KB만
                        print("[디버깅] 페이지 HTML 일부 저장: page_debug.html")
                except Exception as html_error:
                    print(f"[디버깅] HTML 저장 실패: {html_error}")
                
                # 스크린샷 저장
                try:
                    await self.page.screenshot(path='comment_field_debug.png', full_page=True)
                    print("[디버깅] 스크린샷 저장: comment_field_debug.png")
                except:
                    pass
                
                raise Exception(f"댓글 입력 필드를 찾을 수 없습니다. 시도한 선택자: {possible_comment_selectors}")
            
            comment_input_selector = found_comment_selector
            
            # 찾은 필드가 실제로 댓글 필드인지 확인 (wr_content 또는 comment 관련)
            try:
                element_info = await self.page.evaluate(f"""
                    (selector) => {{
                        const el = document.querySelector(selector);
                        if (!el) return null;
                        return {{
                            name: el.name,
                            id: el.id,
                            placeholder: el.placeholder,
                            className: el.className,
                            isVisible: el.offsetParent !== null,
                            isInForm: el.closest('form') !== null
                        }};
                    }}
                """, comment_input_selector)
                
                if element_info:
                    print(f"[댓글] 찾은 필드 정보: name={element_info.get('name')}, id={element_info.get('id')}")
                    # wr_content가 아니고 comment도 아닌 경우 경고
                    if 'wr_content' not in element_info.get('name', '') and 'wr_content' not in element_info.get('id', ''):
                        if 'comment' not in element_info.get('name', '').lower() and 'comment' not in element_info.get('id', '').lower():
                            print(f"[경고] 찾은 필드가 댓글 필드가 아닐 수 있습니다: {element_info}")
            except:
                pass
            
            # 댓글 입력 필드 클릭해서 포커스 주기
            await self.page.click(comment_input_selector)
            await self.random_delay(0.3, 0.5)
            
            # 댓글 입력
            await self.page.fill(comment_input_selector, '')
            await self.page.type(comment_input_selector, comment_text, delay=100)
            await self.random_delay(1, 2)
            
            # 입력 확인
            try:
                input_value = await self.page.input_value(comment_input_selector)
                if input_value and comment_text in input_value:
                    print(f"[댓글] 댓글 입력 확인 완료: '{input_value[:50]}...'")
                else:
                    print(f"[경고] 입력된 내용이 예상과 다릅니다. 입력값: '{input_value}'")
            except:
                pass
            
            # 댓글 작성 버튼 찾기 및 클릭 - 여러 선택자 시도
            submit_button_selector = self.config.get('submit_button_selector', '#btn_submit')
            print(f"[댓글] 댓글 등록 버튼 찾는 중: {submit_button_selector}")
            
            # 여러 선택자 시도
            possible_submit_selectors = [
                submit_button_selector,
                '#btn_submit',
                'input#btn_submit',
                'button#btn_submit',
                'input.btn_submit',
                'button.btn_submit',
                'input[type="submit"]',
                'button[type="submit"]',
                'input[value*="등록"]',
                'input[value*="댓글"]',
                'button:has-text("등록")',
                'button:has-text("댓글")',
                'input[value="댓글등록"]',
                'input[value="등록"]',
                'button[value*="등록"]',
                'a.btn_submit',
                'a:has-text("등록")',
            ]
            
            found_submit_selector = None
            submit_button = None
            
            for selector in possible_submit_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    submit_button = await self.page.query_selector(selector)
                    if submit_button:
                        found_submit_selector = selector
                        print(f"[댓글] 댓글 등록 버튼 찾음: {selector}")
                        break
                except:
                    continue
            
            if not submit_button or not found_submit_selector:
                # 모든 선택자 실패 시 페이지 HTML 확인
                print("[디버깅] 페이지의 모든 버튼/input 요소 확인 중...")
                buttons = await self.page.query_selector_all('button, input[type="submit"], input[type="button"]')
                print(f"[디버깅] 발견된 버튼 요소 수: {len(buttons)}")
                for i, btn in enumerate(buttons[:10]):  # 처음 10개만
                    try:
                        btn_info = await btn.evaluate('el => ({tag: el.tagName, type: el.type, id: el.id, name: el.name, value: el.value, class: el.className, text: el.textContent?.substring(0, 20)})')
                        print(f"[디버깅] Button/Input {i+1}: {btn_info}")
                    except:
                        pass
                raise RuntimeError(f"댓글 등록 버튼을 찾을 수 없습니다. 시도한 선택자: {possible_submit_selectors}")
            
            submit_button_selector = found_submit_selector
            
            # 버튼이 보이도록 스크롤
            await submit_button.scroll_into_view_if_needed()
            await self.random_delay(0.5, 1.0)
            
            # 현재 URL 저장 (제출 후 변경 확인용)
            url_before_submit = self.page.url
            print(f"[댓글] 제출 전 URL: {url_before_submit}")
            
            # 폼 제출 방법 1: 버튼 클릭
            print("[댓글] 등록 버튼 클릭 시도...")
            try:
                # 버튼이 disabled 상태인지 확인하고 해제
                is_disabled = await self.page.evaluate("""(selector) => {
                    const btn = document.querySelector(selector);
                    return btn ? btn.disabled : false;
                }""", submit_button_selector)
                
                if is_disabled:
                    print("[댓글] 버튼이 disabled 상태입니다. 해제 중...")
                    await self.page.evaluate("""(selector) => {
                        const btn = document.querySelector(selector);
                        if (btn) btn.disabled = false;
                    }""", submit_button_selector)
                
                # 버튼 클릭
                await submit_button.click(timeout=5000)
                print("[댓글] 버튼 클릭 완료")
            except Exception as click_error:
                print(f"[경고] 버튼 클릭 실패: {click_error}")
                print("[댓글] JavaScript로 폼 제출 시도...")
                
                # 폼 제출 방법 2: JavaScript로 직접 제출
                await self.page.evaluate("""(selector) => {
                    const btn = document.querySelector(selector);
                    if (btn) {
                        // disabled 해제
                        btn.disabled = false;
                        // 폼 찾기
                        const form = btn.closest('form');
                        if (form) {
                            // 폼 제출
                            form.submit();
                        } else if (btn.type === 'submit') {
                            // 버튼이 form 안에 없으면 클릭 이벤트 발생
                            btn.click();
                        }
                    }
                }""", submit_button_selector)
                print("[댓글] JavaScript 폼 제출 완료")
            
            # 폼 제출 후 대기 (페이지 변경 또는 댓글 등록 확인)
            print("[댓글] 댓글 등록 대기 중...")
            await self.random_delay(2, 3)
            
            # 댓글 등록 확인: 입력 필드가 비워졌는지 확인
            try:
                input_value = await self.page.input_value(comment_input_selector)
                if input_value and input_value.strip() != '':
                    print(f"[경고] 입력 필드가 아직 비워지지 않았습니다: '{input_value}'")
                    # 추가 대기
                    await self.random_delay(1, 2)
                    input_value = await self.page.input_value(comment_input_selector)
                    if input_value and input_value.strip() != '':
                        print("[경고] 댓글 등록이 완료되지 않은 것 같습니다. 폼을 다시 제출합니다.")
                        # 폼 강제 제출
                        await self.page.evaluate("""(selector) => {
                            const input = document.querySelector(selector);
                            if (input) {
                                const form = input.closest('form');
                                if (form) form.submit();
                            }
                        }""", comment_input_selector)
                        await self.random_delay(2, 3)
                else:
                    print("[댓글] ✅ 입력 필드가 비워졌습니다. 댓글 등록 성공으로 추정.")
            except Exception as check_error:
                print(f"[경고] 입력 필드 확인 중 오류: {check_error}")
            
            # 페이지 URL 변경 확인
            url_after_submit = self.page.url
            if url_after_submit != url_before_submit:
                print(f"[댓글] ✅ 페이지 URL이 변경되었습니다: {url_after_submit}")
                print("[댓글] 댓글 등록 성공으로 추정.")
            else:
                print(f"[댓글] 페이지 URL 변경 없음 (현재: {url_after_submit})")
            
            # 추가 대기 (서버 처리 시간)
            await self.random_delay(2, 3)
            
            # 댓글 등록 최종 확인
            print("[댓글] 댓글 등록 최종 확인 중...")
            comment_registered = False
            
            # 방법 1: 입력 필드가 비워졌는지 확인
            try:
                input_value = await self.page.input_value(comment_input_selector)
                if not input_value or input_value.strip() == '':
                    comment_registered = True
                    print("[댓글] ✅ 입력 필드가 비워졌습니다.")
            except Exception:
                pass
            
            # 방법 2: 새 댓글이 목록에 추가되었는지 확인
            if not comment_registered:
                try:
                    comments_after = await self.get_existing_comments()
                    if comments_after:
                        # 댓글 개수 증가 확인
                        if len(comments_after) > len(existing_comments or []):
                            comment_registered = True
                            print(f"[댓글] ✅ 새 댓글이 추가되었습니다! (이전: {len(existing_comments or [])}개, 현재: {len(comments_after)}개)")
                        # 작성한 댓글 내용이 목록에 있는지 확인
                        elif comment_text in str(comments_after):
                            comment_registered = True
                            print("[댓글] ✅ 작성한 댓글이 목록에 있습니다!")
                except Exception:
                    pass
            
            if comment_registered:
                print(f"[댓글] ✅ 댓글 등록 성공: {comment_text}")
            else:
                print(f"[경고] ⚠️ 댓글 등록 확인 실패")
                print("[경고] 하지만 계속 진행합니다. (다음 게시글에서 다시 시도 가능)")
            
            # 추가 안전 대기
            await self.random_delay(1, 2)
            
            print(f"[댓글] 댓글 작성 프로세스 완료: {comment_text}")
            
            # Frame을 사용했다면 원본 page로 복원
            if self.main_page and self.page != self.main_page:
                print("[댓글] 원본 페이지로 복원 중...")
                self.page = self.main_page
            
            # 댓글 작성 성공 시 게시글 URL 저장 (중복 방지)
            self.save_commented_post(post_url)
            self.record_comment_usage(comment_text)
            self.log_comment_feedback(post_title, post_content, existing_comments, comment_text)
            
            return True
            
        except Exception as e:
            print(f"[오류] 댓글 작성 실패 ({post_url}): {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def go_back_to_board(self):
        """게시판으로 돌아가기"""
        try:
            print("[게시판] 게시판으로 돌아가는 중...")
            
            # 페이지 상태 확인 (Frame과 Page 구분)
            page_ok = False
            if self.page:
                try:
                    # Page 객체인 경우
                    if hasattr(self.page, 'is_closed'):
                        page_ok = not self.page.is_closed()
                    # Frame 객체인 경우 - main_page 확인
                    elif self.main_page and hasattr(self.main_page, 'is_closed'):
                        page_ok = not self.main_page.is_closed()
                    else:
                        page_ok = True  # Frame이면 일단 시도
                except:
                    page_ok = False
            
            if page_ok:
                # 명시적으로 게시판 목록 페이지로 이동
                board_url = self.build_board_page_url(self.current_page)
                print(f"[게시판] 게시판 목록 페이지로 이동: {board_url}")
                
                # main_page가 있으면 그것을 사용, 없으면 현재 page 사용
                page_to_use = self.main_page if self.main_page else self.page
                if page_to_use and hasattr(page_to_use, 'goto'):
                    await page_to_use.goto(board_url, wait_until='networkidle', timeout=30000)
                    self.page = page_to_use  # 원본 page로 복원
                    await self.random_delay(2, 3)
                    print(f"[게시판] 게시판 복귀 완료: {self.page.url}")
                else:
                    await self.navigate_to_board_page(self.current_page)
            else:
                print("[경고] 페이지가 이미 닫혔습니다.")
        except Exception as e:
            print(f"[경고] 게시판으로 돌아가는 중 오류: {e}")
            import traceback
            traceback.print_exc()
    
    async def random_delay(self, min_sec: float = None, max_sec: float = None):
        """랜덤 대기 시간"""
        min_sec = min_sec if min_sec is not None else self.config.get('delay_min', 1)
        max_sec = max_sec if max_sec is not None else self.config.get('delay_max', 3)
        min_sec = max(1, min(min_sec, self.max_delay_seconds))
        max_sec = max(1, min(max_sec, self.max_delay_seconds))
        if min_sec >= max_sec:
            max_sec = min(self.max_delay_seconds, min_sec + 1)
        delay = random.uniform(min_sec, max_sec)
        print(f"[대기] {delay:.2f}초 대기 (무작위)")
        await asyncio.sleep(delay)
    
    async def run(self, headless: bool = False):
        """매크로 실행"""
        try:
            # 브라우저 초기화
            await self.init_browser(headless=headless)
            
            # 로그인
            if not await self.login():
                print("[오류] 로그인 실패로 프로그램을 종료합니다.")
                return
            
            # 게시판 접속 (1페이지부터 시작)
            self.current_page = 1
            self.page_direction = 1
            await self.navigate_to_board_page(self.current_page)
            
            # 처리한 게시글 URL 추적
            processed_urls = set(self.commented_posts)  # 이번 실행에서 처리한 게시글 추적
            success_count = 0
            max_posts = self.config.get('max_posts', 10)
            max_board_pages = max(1, self.config.get('max_board_pages', 1))
            # 안전장치: 모든 페이지를 여러 번 순회했는데도 댓글을 달 수 없으면 종료
            max_attempts = max_posts * max_board_pages * 5
            attempts = 0
            
            # 각 게시글에 댓글 작성 (게시판 → 게시글 → 댓글 작성 → 게시판 → 다음 게시글)
            while success_count < max_posts and attempts < max_attempts:
                attempts += 1
                print(f"\n[{success_count + 1}/{max_posts}] 게시글 처리 시도 (현재 페이지: {self.current_page})")
                
                # 게시판에서 다음 게시글 링크 가져오기
                post_url = await self.get_next_post_link(processed_urls)
                
                if not post_url:
                    print(f"[알림] 페이지 {self.current_page}에서 처리할 게시글이 없습니다.")
                    if not await self.switch_board_page("현재 페이지에 유효한 게시글 없음"):
                        print("[알림] 더 이상 이동할 페이지가 없어 프로그램을 종료합니다.")
                        break
                    continue
                
                # 게시글에 댓글 작성
                print(f"[진행] ========================================")
                print(f"[진행] 게시글 댓글 작성 시도: {post_url}")
                print(f"[진행] 현재 URL 확인: {self.page.url}")
                print(f"[진행] 게시판 페이지인지 확인: {'게시판' if self.config['board_url'] in self.page.url else '게시판 아님'}")
                print(f"[진행] ========================================")
                
                # 댓글 작성 함수 호출
                print(f"[진행] write_comment 함수 호출 시작...")
                comment_result = await self.write_comment(post_url)
                print(f"[진행] write_comment 함수 호출 완료. 결과: {comment_result}")
                
                if comment_result:
                    success_count += 1
                    processed_urls.add(post_url)
                    print(f"[성공] 댓글 작성 완료! (성공: {success_count}/{max_posts})")
                else:
                    print(f"[경고] 댓글 작성에 실패했습니다. 다음 게시글을 시도합니다. (실패한 URL: {post_url})")
                
                # 댓글 작성 후 반드시 게시판으로 돌아가기
                print(f"[게시판] 댓글 작성 후 게시판 복귀 전 URL: {self.page.url}")
                await self.go_back_to_board()
                print(f"[게시판] 게시판 복귀 후 URL: {self.page.url}")
                
                # 게시판 복귀 확인
                if self.config['board_url'] not in self.page.url:
                    print(f"[경고] 게시판 복귀 실패! 강제로 게시판으로 이동합니다.")
                    await self.page.goto(self.config['board_url'], wait_until='networkidle')
                    await self.random_delay(2, 4)
                
                # 다음 게시글 전 대기
                if success_count < max_posts:
                    await self.random_delay(
                        self.config.get('delay_min', 3),
                        self.config.get('delay_max', 6)
                    )
            
            if attempts >= max_attempts and success_count < max_posts:
                print("[경고] 여러 페이지를 순환했지만 게시글을 충분히 처리하지 못했습니다. 새 게시글이 올라오면 다시 실행해주세요.")
            
            print(f"\n[완료] 총 {success_count}개 댓글 작성 완료")
            
        except Exception as e:
            print(f"[오류] 실행 중 오류 발생: {e}")
        finally:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()


def load_config():
    """환경 변수에서 설정 로드"""
    return {
        'url': os.getenv('SITE_URL', 'https://example.com'),
        'login_url': os.getenv('LOGIN_URL', 'https://example.com/login'),
        'username': os.getenv('LOGIN_USERNAME', ''),
        'password': os.getenv('PASSWORD', ''),
        'board_url': os.getenv('BOARD_URL', 'https://example.com/board'),
        'comment_texts': [
            '좋아요!',
            '응원해요!',
            '화이팅!',
            '힘내세요!',
            '좋아요~',
        ],
        'delay_min': float(os.getenv('DELAY_MIN', '1')),
        'delay_max': float(os.getenv('DELAY_MAX', '10')),
        'max_posts': int(os.getenv('MAX_POSTS', '10')),
        'max_board_pages': int(os.getenv('MAX_BOARD_PAGES', '3')),
        'comment_gap_min': int(os.getenv('COMMENT_GAP_MIN', '1')),
        'comment_gap_max': int(os.getenv('COMMENT_GAP_MAX', '10')),
        'min_repeat_interval_sec': int(os.getenv('MIN_REPEAT_INTERVAL_SEC', '900')),
        # 게시글 처리 순서: 'latest' (최신순), 'oldest' (오래된순), 또는 'random' (랜덤)
        'post_order': os.getenv('POST_ORDER', 'random'),
        # OpenAI API 키 (선택사항, 없으면 기본 댓글 사용)
        'openai_api_key': os.getenv('OPENAI_API_KEY', ''),
        # Gemini API 키 제거됨 - OpenAI만 사용
        # CSS 선택자들 (실제 사이트에 맞게 수정 필요)
        'username_selector': os.getenv('USERNAME_SELECTOR', 'input[name="username"]'),
        'password_selector': os.getenv('PASSWORD_SELECTOR', 'input[name="password"]'),
        'login_button_selector': os.getenv('LOGIN_BUTTON_SELECTOR', 'button[type="submit"]'),
        'post_link_selector': os.getenv('POST_LINK_SELECTOR', 'a.post-link'),
        'comment_input_selector': os.getenv('COMMENT_INPUT_SELECTOR', 'textarea[name="comment"]'),
        'submit_button_selector': os.getenv('SUBMIT_BUTTON_SELECTOR', 'input#btn_submit, #btn_submit, input.btn_submit, button.btn_submit, button[type="submit"], input[type="submit"]'),
    }


async def main():
    """메인 함수"""
    # 실행파일인 경우 브라우저 확인을 건너뛰고 바로 진행
    # (실제 브라우저 사용 시 오류가 발생하면 그때 처리)
    is_frozen = getattr(sys, 'frozen', False)
    
    if not is_frozen:
        # Python 스크립트인 경우에만 브라우저 확인
        try:
            loop = asyncio.get_event_loop()
            browser_ok = await loop.run_in_executor(None, ensure_playwright_browser)
            
            if not browser_ok:
                print()
                print("=" * 60)
                print("[경고] 브라우저 확인에 실패했습니다.")
                print("=" * 60)
                print()
                print("브라우저가 이미 설치되어 있다면 프로그램이 정상 작동할 수 있습니다.")
                print("브라우저 설치 문제를 해결하려면:")
                print("  python -m playwright install chromium")
                print()
                user_input = input("계속 진행하시겠습니까? (y/n): ").strip().lower()
                if user_input != 'y':
                    print("프로그램을 종료합니다.")
                    return
                print()
        except Exception as e:
            print(f"[경고] 브라우저 확인 중 오류: {e}")
            print("[경고] 계속 진행하지만 문제가 발생할 수 있습니다.")
            print()
    
    config = load_config()
    
    # 설정 검증
    if not config['username'] or not config['password']:
        print("[오류] LOGIN_USERNAME과 PASSWORD를 .env 파일에 설정해주세요.")
        return
    
    # URL 검증
    urls_to_check = {
        'SITE_URL': config['url'],
        'LOGIN_URL': config['login_url'],
        'BOARD_URL': config['board_url']
    }
    
    for url_name, url_value in urls_to_check.items():
        if not url_value or not isinstance(url_value, str):
            print(f"[오류] {url_name}이 설정되지 않았거나 잘못되었습니다: {url_value}")
            print(f".env 파일의 {url_name}을 확인하세요.")
            return
        if not url_value.startswith(('http://', 'https://')):
            print(f"[오류] {url_name} 형식이 잘못되었습니다.")
            print(f"http:// 또는 https://로 시작해야 합니다.")
            print(f"현재 값: {url_value}")
            print(f".env 파일의 {url_name}을 올바른 URL 형식으로 수정하세요.")
            return
    
    bot = MacroBot(config)
    await bot.run(headless=False)  # headless=True로 하면 브라우저 창이 안 보임


if __name__ == '__main__':
    asyncio.run(main())

