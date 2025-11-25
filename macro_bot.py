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
    try:
        # 브라우저가 설치되어 있는지 확인
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                return True
            except Exception:
                # 브라우저가 없으면 설치
                print("[알림] Playwright 브라우저가 설치되어 있지 않습니다.")
                print("[알림] 브라우저를 자동으로 설치하는 중... (처음 실행 시 한 번만 설치됩니다)")
                print("      (이 작업은 몇 분 정도 걸릴 수 있습니다)")
                print()
                
                # playwright install chromium 실행
                try:
                    if getattr(sys, 'frozen', False):
                        # 실행 파일인 경우
                        # PyInstaller로 만든 실행 파일에서는 playwright install을 직접 실행하기 어려움
                        # 대신 playwright의 내부 설치 메커니즘 사용 시도
                        try:
                            # playwright의 설치 함수 직접 호출
                            from playwright.sync_api import sync_playwright
                            # playwright install은 내부적으로 처리됨
                            # 하지만 직접 호출이 어려우므로 subprocess로 시도
                            # 실행 파일 자체를 Python 인터프리터처럼 사용
                            result = subprocess.run(
                                [sys.executable, "-c", "import subprocess, sys; subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'])"],
                                check=True,
                                timeout=600  # 10분 타임아웃
                            )
                        except Exception:
                            # 실패하면 사용자에게 안내
                            raise Exception("자동 설치 실패")
                    else:
                        # Python 스크립트인 경우
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
                    print("[오류] 브라우저 설치 시간 초과")
                    print("[안내] 네트워크 연결을 확인하고 다시 시도하세요.")
                    return False
                except subprocess.CalledProcessError as e:
                    print(f"[오류] 브라우저 설치 실패")
                    print()
                    print("[안내] 수동 설치 방법:")
                    if getattr(sys, 'frozen', False):
                        print("  1. Python을 설치하세요 (https://www.python.org/downloads/)")
                        print("  2. 다음 명령어 실행: python -m playwright install chromium")
                    else:
                        print("  python -m playwright install chromium")
                    print()
                    return False
                except Exception as install_error:
                    print(f"[오류] 브라우저 설치 중 오류 발생: {install_error}")
                    print()
                    print("[안내] 수동 설치 방법:")
                    if getattr(sys, 'frozen', False):
                        print("  1. Python을 설치하세요 (https://www.python.org/downloads/)")
                        print("  2. 다음 명령어 실행: python -m playwright install chromium")
                    else:
                        print("  python -m playwright install chromium")
                    print()
                    return False
    except Exception as e:
        print(f"[경고] 브라우저 확인 중 오류 발생: {e}")
        print("[안내] 브라우저가 제대로 작동하지 않을 수 있습니다.")
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
        """댓글이 긍정적인지 판별"""
        if not comment_text:
            return False
        positive_keywords = ['화이팅', '좋아', '대박', '축하', '부럽', '좋네', '좋다', '멋져', '최고', '응원', '파이팅']
        return any(keyword in comment_text for keyword in positive_keywords)
    
    def _is_negative_comment(self, comment_text: str) -> bool:
        """댓글이 부정적인지 판별"""
        if not comment_text:
            return False
        negative_keywords = ['아쉽', '슬프', '힘들', '후회', '아깝', '위로', '공감']
        return any(keyword in comment_text for keyword in negative_keywords)

    def enhance_tone_variation(self, comment_text: str, post_content: str = '') -> str:
        """물결/느낌표/ㅠㅠ 등을 다양하게 섞되 과한 특수문자 사용은 제한"""
        if not comment_text:
            return comment_text
        comment = comment_text.strip()
        
        # 이미 어미가 있는지 확인 (요, 죠, 네요, 어요, 해요, 되요, 다요, 야요, 까요, 나요, 세요 등)
        # 물음표는 어미가 아니므로 제외하고 체크
        comment_without_question = comment.rstrip('?')
        # 정규식으로 어미 확인 (반말 어미 포함: 야, 다, 어, 해, 되, 까, 나, 세, 지, 네 등)
        has_ending = bool(re.search(r'(요|죠|네요|어요|해요|되요|다요|야요|까요|나요|세요|지요|네|어|해|되|다|야|까|나|세|지)$', comment_without_question))
        # "야"로 끝나는 경우 명시적으로 체크 (정규식이 놓칠 수 있으므로)
        if not has_ending and comment_without_question.endswith('야'):
            has_ending = True
        
        # 특수 문자 개수 제한
        special_chars = ['~', '!', 'ㅠ', 'ㅜ']
        special_count = sum(comment.count(ch) for ch in special_chars)
        if special_count > 2:
            for ch in special_chars:
                while comment.count(ch) > 1:
                    comment = comment.replace(ch, '', 1)
        
        # 존댓말 섞기 (너무 반말만 나오는 것 방지) - 이미 어미가 있으면 추가하지 않음
        if not has_ending and '요' not in comment and random.random() < 0.4:
            suffix_options = ['요', '요~', '요!']  # '용' 제거
            suffix = random.choice(suffix_options)
            if len(comment) + len(suffix) <= 10:
                comment += suffix
            elif len(comment) < 10:
                comment = (comment + suffix)[:10]
        
        # 댓글 내용에 따라 적절한 특수 기호 추가
        if not any(ch in comment for ch in ['~', '!', 'ㅠ']):
            # 존댓말 어미로 끝나는 경우 (요, 세요, 네요, 어요, 해요 등)
            if re.search(r'(요|세요|네요|어요|해요|되요|다요|까요|나요|지요)$', comment_without_question):
                # 부정적인 댓글 (아쉽, 슬프 등) → ㅠ 추가
                if self._is_negative_comment(comment):
                    candidate = 'ㅠ'
                    if len(comment) + len(candidate) <= 10:
                        comment += candidate
                    elif len(comment) < 10:
                        comment = (comment + candidate)[:10]
                # 긍정적인 댓글 (화이팅, 좋아, 대박 등) → ! 추가
                elif self._is_positive_comment(comment):
                    candidate = '!'
                    if len(comment) + len(candidate) <= 10:
                        comment += candidate
                    elif len(comment) < 10:
                        comment = (comment + candidate)[:10]
                # 일반적인 댓글 → ~ 추가 (부드러운 느낌)
                else:
                    # 80% 확률로 물결표 추가
                    if random.random() < 0.8:
                        if len(comment) + 1 <= 10:
                            comment += '~'
                        elif len(comment) < 10:
                            comment = (comment + '~')[:10]
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
                # 그 외의 경우 물결표나 느낌표 추가
                else:
                    candidate = random.choice(['~', '!'])
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
        
        # 이미 물결표로 끝나는데 추가 변화를 주고 싶은 경우 (확률 낮춤)
        if comment.endswith('~') and random.random() < 0.1:
            comment = comment[:-1] + random.choice(['~!', '요~', '요!'])
        
        return comment[:10]

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
            alt_comment = self.enhance_tone_variation(alt_comment, post_content)
            comment_text = alt_comment
            attempts += 1
        print(f"[경고] 댓글이 계속 반복되어 기본 댓글로 전환합니다. 원본: {original}")
        fallback = self.generate_style_matched_comment(existing_comments or [], post_content or '')
        if fallback == original:
            fallback += '~'
        if not self.has_meaningful_content(fallback):
            fallback = "지치네요"
        fallback = self.enhance_tone_variation(fallback, post_content)
        return fallback

    def build_board_page_url(self, page_number: int) -> str:
        """페이지 번호에 맞는 게시판 URL 생성"""
        page_number = max(1, page_number)
        base_url = self.config['board_url']
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
        await self.page.goto(target_url, wait_until='networkidle')
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
        if not self.playwright:
            self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            slow_mo=500  # 동작을 천천히 (디버깅용)
        )
        self.page = await self.browser.new_page()
        # 봇 탐지 방지를 위한 User-Agent 설정
        await self.page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

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
            # 사용자명 입력 필드
            username_selector = self.config.get('username_selector', 'input[name="username"]')
            print(f"[로그인] 사용자명 입력 필드 찾는 중: {username_selector}")
            
            # 요소가 로드될 때까지 대기
            await self.page.wait_for_selector(username_selector, timeout=10000)
            
            # 필드를 클릭해서 포커스 주기
            await self.page.click(username_selector)
            await self.random_delay(0.3, 0.5)
            
            # 기존 내용 지우고 입력
            await self.page.fill(username_selector, '')
            await self.page.type(username_selector, self.config['username'], delay=100)
            print(f"[로그인] 사용자명 입력 완료: {self.config['username']}")
            await self.random_delay(0.5, 1.0)
            
            # 비밀번호 입력 필드
            password_selector = self.config.get('password_selector', 'input[name="password"]')
            print(f"[로그인] 비밀번호 입력 필드 찾는 중: {password_selector}")
            
            # 요소가 로드될 때까지 대기
            await self.page.wait_for_selector(password_selector, timeout=10000)
            
            # 필드를 클릭해서 포커스 주기
            await self.page.click(password_selector)
            await self.random_delay(0.3, 0.5)
            
            # 기존 내용 지우고 입력
            await self.page.fill(password_selector, '')
            await self.page.type(password_selector, self.config['password'], delay=100)
            print("[로그인] 비밀번호 입력 완료")
            await self.random_delay(0.5, 1.0)
            
            # 로그인 버튼 클릭
            login_button_selector = self.config.get('login_button_selector', 'button[type="submit"]')
            print(f"[로그인] 로그인 버튼 찾는 중: {login_button_selector}")
            
            await self.page.wait_for_selector(login_button_selector, timeout=10000)
            await self.page.click(login_button_selector)
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
    
    async def get_post_date(self, post_url: str) -> datetime:
        """게시글의 작성 시간 가져오기"""
        try:
            # 게시글 페이지 접속
            await self.page.goto(post_url, wait_until='networkidle')
            await self.random_delay(1, 2)
            
            # 작성 시간을 찾는 여러 방법 시도
            date_text = await self.page.evaluate("""
                () => {
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
                    const datePattern = /\\d{4}[.-/]\\d{1,2}[.-/]\\d{1,2}/;
                    const match = allText.match(datePattern);
                    if (match) {
                        return match[0];
                    }
                    
                    return null;
                }
            """)
            
            if not date_text:
                return None
            
            # 날짜 파싱 시도
            date_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y.%m.%d %H:%M',
                '%Y/%m/%d %H:%M',
                '%Y-%m-%d',
                '%Y.%m.%d',
                '%Y/%m/%d',
            ]
            
            for fmt in date_formats:
                try:
                    return datetime.strptime(date_text, fmt)
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
        post_date = await self.get_post_date(post_url)
        
        if not post_date:
            print("[경고] 게시글 작성 시간을 확인할 수 없습니다. 댓글을 작성합니다.")
            return True  # 시간을 확인할 수 없으면 작성
        
        now = datetime.now()
        time_diff = now - post_date
        
        if time_diff <= timedelta(hours=24):
            print(f"[확인] 게시글 작성 시간: {post_date.strftime('%Y-%m-%d %H:%M')} ({(time_diff.total_seconds() / 3600):.1f}시간 전)")
            return True
        else:
            hours_ago = time_diff.total_seconds() / 3600
            print(f"[건너뛰기] 게시글이 24시간을 초과했습니다. ({hours_ago:.1f}시간 전, 작성 시간: {post_date.strftime('%Y-%m-%d %H:%M')})")
            return False
    
    async def get_next_post_link(self, processed_urls: set) -> str:
        """게시판에서 다음 게시글 링크 하나만 가져오기 (24시간 이내만)"""
        # 게시판이 이미 열려있는지 확인하고, 아니면 접속
        current_url = self.page.url
        if self.config['board_url'] not in current_url:
            print(f"[게시판] {self.config['board_url']} 접속 중...")
            await self.page.goto(self.config['board_url'], wait_until='networkidle')
            await self.random_delay(2, 4)
        
        # 페이지가 완전히 로드될 때까지 대기
        await self.page.wait_for_load_state('networkidle')
        await self.random_delay(1, 2)
        
        try:
            print("[게시판] 게시글 링크를 찾는 중... (24시간 이내 게시글만 선택)")
            
            # 방법 1: JavaScript로 모든 링크 가져오기 (가장 확실한 방법)
            all_urls = []
            
            # JavaScript를 사용해서 페이지의 모든 링크 가져오기
            links_data = await self.page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links.map(link => ({
                        href: link.href,
                        text: link.textContent.trim(),
                        innerHTML: link.innerHTML
                    }));
                }
            """)
            
            print(f"[게시판] JavaScript로 {len(links_data)}개의 링크를 발견했습니다.")
            
            # 게시글 링크 패턴: /bbs/free/숫자 형식
            post_pattern = re.compile(r'/bbs/free/\d+')
            
            for link_data in links_data:
                href = link_data.get('href', '')
                if not href:
                    continue
                
                # 게시글 링크 패턴 확인
                if post_pattern.search(href) or '/bbs/free/' in href:
                    # 숫자로 끝나는 링크만 선택 (게시글 ID)
                    if re.search(r'/bbs/free/\d+$', href) or re.search(r'/bbs/free/\d+\?', href) or re.search(r'/bbs/free/\d+#', href):
                        # URL 정규화 (쿼리 파라미터 제거)
                        clean_url = href.split('?')[0].split('#')[0]
                        if clean_url not in processed_urls:
                            all_urls.append(clean_url)
            
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
                
                # 발견된 링크 샘플 출력
                sample_links = [link['href'] for link in links_data[:20] if link.get('href')]
                print(f"[디버깅] 발견된 링크 샘플 (처음 10개):")
                for i, link in enumerate(sample_links[:10], 1):
                    print(f"  {i}. {link}")
                
                # 스크린샷 저장
                await self.page.screenshot(path='board_debug.png')
                print("[디버깅] 스크린샷 저장: board_debug.png")
                
                return None
            
            print(f"[게시판] {len(all_urls)}개의 게시글 링크를 찾았습니다.")
            
            # 순서 선택 (기본값: 최신순)
            order = self.config.get('post_order', 'latest')
            
            # 24시간 이내 게시글만 필터링
            valid_urls = []
            max_check = min(20, len(all_urls))  # 최대 20개까지만 확인 (성능 고려)
            
            for url in all_urls[:max_check]:
                # 이미 댓글을 작성한 게시글은 건너뛰기
                if url in self.commented_posts:
                    print(f"[중복방지] 이미 댓글 작성한 게시글 건너뛰기: {url}")
                    continue
                
                if await self.is_post_within_24h(url):
                    valid_urls.append(url)
                    # 첫 번째 유효한 게시글을 찾으면 중단 (최신순일 때)
                    if order == 'latest':
                        break
            
            if not valid_urls:
                print("[게시판] 24시간 이내 게시글이 없습니다.")
                return None
            
            if order == 'random' and len(valid_urls) > 1:
                selected_url = random.choice(valid_urls)
                print(f"[게시판] 랜덤으로 게시글 선택: {selected_url}")
            else:
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
            # 게시글 제목 선택자들
            title_selectors = [
                '#bo_v_atc .bo_v_tit',     # 그누보드 제목
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
            
            # JavaScript로 직접 제목 찾기
            if not title_text:
                title_text = await self.page.evaluate("""
                    () => {
                        const selectors = [
                            '#bo_v_atc .bo_v_tit',
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
    
    def analyze_comment_style(self, existing_comments: list) -> dict:
        """기존 댓글들의 말투 스타일 분석"""
        if not existing_comments or len(existing_comments) == 0:
            return {
                'ending': '요',  # 기본값
                'tone': 'casual',  # casual, formal
                'has_emoji': False,
                'avg_length': 5
            }
        
        endings = []
        has_emoji_count = 0
        total_length = 0
        
        for comment in existing_comments[:10]:  # 최대 10개만 분석
            if not comment or len(comment.strip()) < 2:
                continue
            
            comment = comment.strip()
            total_length += len(comment)
            
            # 이모티콘 체크
            if any(emoji in comment for emoji in ['ㅠ', 'ㅜ', '~', '!', '?', 'ㅎ', 'ㅋ']):
                has_emoji_count += 1
            
            # 끝말 분석
            if comment.endswith('요') or comment.endswith('요!'):
                endings.append('요')
            elif comment.endswith('다') or comment.endswith('다!'):
                endings.append('다')
            elif comment.endswith('어') or comment.endswith('어!'):
                endings.append('어')
            elif comment.endswith('해') or comment.endswith('해!'):
                endings.append('해')
            elif comment.endswith('네요') or comment.endswith('네요!'):
                endings.append('네요')
            else:
                endings.append('요')  # 기본값
        
        # 가장 많이 사용된 끝말
        if endings:
            most_common_ending = max(set(endings), key=endings.count)
        else:
            most_common_ending = '요'
        
        avg_length = total_length // len(existing_comments) if existing_comments else 5
        has_emoji = has_emoji_count > len(existing_comments) * 0.3  # 30% 이상이면 이모티콘 사용
        
        return {
            'ending': most_common_ending,
            'tone': 'casual',  # 도박 게시판은 대부분 반말/캐주얼
            'has_emoji': has_emoji,
            'avg_length': avg_length
        }
    
    def generate_style_matched_comment(self, existing_comments: list, post_content: str = '') -> str:
        """기존 댓글 스타일에 맞춘 댓글 생성"""
        style = self.analyze_comment_style(existing_comments)
        
        # 기본 댓글 후보들
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
        base = random.choice(base_comments)
        
        # 스타일에 맞게 끝말 추가 (이모티콘 없이, "용" 어미 사용 금지)
        if style['ending'] == '요':
            comment = f"{base}요"  # "용" 어미 사용 금지
        elif style['ending'] == '다':
            comment = f"{base}다"
        elif style['ending'] == '어':
            comment = f"{base}어"
        elif style['ending'] == '해':
            comment = f"{base}해"
        elif style['ending'] == '네요':
            comment = f"{base}네요"
        else:
            comment = f"{base}요"
        
        # 가벼운 댓글도 추가 (기분 좋은 글용) - 이모티콘 제거
        if base in ['축하', '부럽', '대박', '좋아'] and random.random() > 0.7:  # 30% 확률
            light_comments = ['좋아요', '부럽네요', '대박이네요', '기쁘네요']
            comment = random.choice(light_comments)
        
        # 이모티콘 추가 제거 (이모티콘 사용 금지)
        # 이모티콘은 사용하지 않음
        
        # 길이 제한 (10글자)
        if len(comment) > 10:
            comment = comment[:10]
        
        if not self.has_meaningful_content(comment):
            comment = '지치네요'
        
        comment = self.enhance_tone_variation(comment, post_content)
        
        # 중복 어미 제거 (요요, 네요요 등)
        comment = self.clean_comment(comment)
        
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
                    
                    // 방법 1: article[id^="c_"] 태그로 댓글 찾기 (가장 정확)
                    const commentArticles = document.querySelectorAll('article[id^="c_"]');
                    commentArticles.forEach(article => {
                        // textarea[id^="save_comment_"]에서 댓글 텍스트 가져오기
                        const textarea = article.querySelector('textarea[id^="save_comment_"]');
                        if (textarea) {
                            const text = (textarea.value || textarea.textContent || '').trim();
                            if (text && text.length > 0) {
                                allComments.push(text);
                            }
                        } else {
                            // textarea가 없으면 .cmt_contents에서 텍스트 가져오기
                            const cmtContents = article.querySelector('.cmt_contents');
                            if (cmtContents) {
                                const text = (cmtContents.innerText || cmtContents.textContent || '').trim();
                                if (text && text.length > 0) {
                                    allComments.push(text);
                                }
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
            
            return comments[:10]  # 최대 10개만
            
        except Exception as e:
            print(f"[경고] 기존 댓글을 가져오는 중 오류: {e}")
            import traceback
            print(f"[경고] 상세 오류: {traceback.format_exc()}")
            return []
    
    def clean_comment(self, comment: str) -> str:
        """댓글에서 중복 어미, 이모티콘, 마침표, 불필요한 문자 제거"""
        import re
        
        if not comment:
            return comment
        
        # 1. 이모티콘/기호 제거 (물결표, 느낌표, ㅠㅠ 등)
        comment = re.sub(r'[~!ㅠㅜㅎㅋ]+', '', comment)
        
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
        
        if existing_comments:
            print(f"[AI] 기존 댓글 {len(existing_comments)}개 확인: {existing_comments[:3]}...")
        
        try:
            # 기존 댓글 정보 추가 (최우선 참고)
            if existing_comments and len(existing_comments) > 0:
                numbered_comments = "\n".join(
                    [f"{idx + 1}. {c}" for idx, c in enumerate(existing_comments[:8])]
                )
                comments_text = f"\n\n⭐⭐⭐ 가장 중요: 현재 댓글 흐름 (최근 {min(len(existing_comments), 8)}개):\n{numbered_comments}\n\n"
                comments_text += "⚠️ 반드시 위 댓글들을 우선적으로 분석하세요:\n"
                comments_text += "1. 위 댓글들의 말투 패턴을 정확히 파악 (존댓말/반말, 어미 패턴)\n"
                comments_text += "2. 위 댓글들의 스타일과 길이를 분석\n"
                comments_text += "3. 위 댓글들의 감정선과 톤을 파악\n"
                comments_text += "4. 위 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요\n"
                comments_text += "5. 본문보다 위 기존 댓글 스타일에 더 중점을 두세요\n"
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
4. 이모티콘 절대 사용 금지 (물결표, 느낌표, ㅠㅠ 등 모두 금지)
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
- 이모티콘 절대 사용 금지: 물결표(~), 느낌표(!), "ㅠㅠ" 등 모든 이모티콘/기호를 사용하지 마세요
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
4. 위 세 가지 정보를 합쳐 10글자 이내의 댓글을 설계합니다. 이모티콘은 절대 사용하지 않습니다.
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
                keywords_text = f"\n\n🔑 본문 핵심 키워드: {', '.join(keywords)}\n- 위 키워드들을 댓글에 자연스럽게 활용하세요.\n- 예: 본문에 '야식'이 있으면 '야식 좋지요'처럼 키워드를 포함한 댓글을 작성하세요.\n- 예: 본문에 '형님'이 있으면 '형님도 굿나잇입니다'처럼 키워드를 활용하세요.\n- 이모티콘은 절대 사용하지 마세요.\n"
            
            # 질문형 게시글 확인
            is_question = any(q in post_content for q in ['?', '?', '어떻게', '뭐가', '어떤', '언제', '어디', '누가', '왜', '몇시', '몇시쯤'])
            question_guide = ""
            if is_question:
                question_guide = "\n\n⚠️ 질문형 게시글입니다:\n- 질문에 대한 답을 모르면 댓글을 작성하지 마세요.\n- 답을 알고 있거나 공감할 수 있는 내용만 댓글로 작성하세요.\n- 예: '축구 오늘 몇시쯤에 하나요?' → 답을 모르면 댓글 작성하지 않음\n"
            
            # 프롬프트 생성 (도박 용어 사전 포함)
            # 기존 댓글을 우선적으로 강조
            comments_priority_text = "\n\n⭐⭐⭐ 중요: 기존 댓글들을 우선적으로 분석하고, 기존 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요. 본문보다 기존 댓글 스타일에 더 중점을 두세요.\n" if existing_comments and len(existing_comments) > 0 else ""
            
            title_section = f"\n게시글 제목:\n{post_title if post_title else '(제목 없음)'}\n" if post_title else ""
            prompt = f"""{base_prompt_section}{gambling_terms_text}{comments_priority_text}{keywords_text}{question_guide}

{title_section}게시글 본문:
{post_content[:500]}{comments_text}{few_shot_text}{bad_examples_text}

댓글:"""

            print("[AI] OpenAI API 호출 중...")
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
                            'content': '당신은 도박 관련 사이트의 자유게시판에서 게시글 작성자의 톤과 내용에 맞춰 친근하지만 자연스러운 댓글을 작성하는 도우미입니다. 자유게시판이므로 도박 관련 얘기뿐만 아니라 일상 수다도 올라올 수 있습니다. 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 댓글을 작성해야 합니다. 가장 중요한 것은: 1) 본문의 말투를 정확히 분석하는 것입니다 (본문이 "~할까요?" 같은 존댓말이면 댓글도 "~요", "~네요" 같은 높임말 사용, 본문이 반말이면 댓글도 반말 사용). 2) 본문의 핵심 키워드를 추출하여 댓글에 자연스럽게 활용하세요 (예: 본문에 "야식"이 있으면 "야식 좋지요"처럼 키워드를 포함). 3) 이모티콘(~, !, ㅠㅠ 등)은 절대 사용하지 마세요. 4) 마침표(.)는 절대 사용하지 마세요. 5) "용" 어미는 절대 사용하지 마세요 (예: "힘내용" ❌ → "힘내요" ✅). 6) 질문형 게시글에서 답을 모르면 댓글을 작성하지 마세요. 7) 기존 댓글들의 말투와 스타일을 분석하여 최대한 비슷하게 작성하세요. 8) 반드시 10글자 이내로 완성하고, 맞춤법을 정확하게 사용하세요. 9) 절대 "감사합니다", "감사해요", "감사" 같은 단어를 사용하지 말고, 형식적인 댓글을 사용하지 마세요.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'max_tokens': 80,  # 10자 이내 댓글을 위해 충분한 토큰 할당 (한국어는 토큰 효율이 낮음)
                    'temperature': 0.7  # 일관성 있는 댓글 생성을 위해 낮춤
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
                        comment = result['choices'][0]['message']['content'].strip()
                        
                        print(f"[AI] 원본 응답: {comment}")
                        
                        # 따옴표 제거
                        comment = comment.strip('"').strip("'")
                        
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
                        
                        # 10글자 초과 시 재시도 (잘라내지 말고 처음부터 10자 이내로 작성하도록)
                        if len(comment) > 10:
                            print(f"[경고] 댓글이 10글자를 초과했습니다 ({len(comment)}자): {comment}")
                            print(f"[경고] 10자 이내로 재생성합니다...")
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
                comments_text = f"\n\n⭐⭐⭐ 가장 중요: 현재 댓글 흐름 (최근 {min(len(existing_comments), 8)}개):\n{numbered_comments}\n\n위 댓글들을 우선적으로 분석하고, 위 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요. 본문보다 기존 댓글 스타일에 더 중점을 두세요."
            else:
                comments_text = "\n\n현재 댓글 흐름: (댓글 없음)"
            
            # 기존 댓글 우선 강조 텍스트
            comments_priority_text = "\n\n⭐⭐⭐ 가장 중요: 기존 댓글들을 우선적으로 분석하고, 기존 댓글들과 최대한 비슷한 스타일로 댓글을 작성하세요. 본문보다 기존 댓글 스타일에 더 중점을 두세요.\n" if existing_comments and len(existing_comments) > 0 else ""
            
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
            
            # 더 강력한 프롬프트 (통일된 버전)
            prompt = f"""다음 게시글 본문을 읽고, 작성자의 감정에 공감하는 댓글을 작성해주세요.

⚠️ 중요: 이 게시판은 도박 관련 사이트의 자유게시판입니다.
- 자유게시판이기 때문에 도박과 관련된 얘기뿐만 아니라 일상 수다도 올라올 수 있습니다
- 게시글 주제가 도박이든 일상이든 상관없이, 본문 내용과 기존 댓글 흐름에 맞춰 작성해야 합니다
- 댓글은 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 작성해야 합니다

🎯 핵심 원칙 (우선순위 순):
1. ⭐⭐⭐ 가장 중요: 기존 댓글들을 우선적으로 분석하세요!
   - 기존 댓글들의 말투, 스타일, 길이, 감정선을 정확히 파악
   - 기존 댓글들과 최대한 비슷한 스타일로 댓글 작성
   - 본문보다 기존 댓글 스타일에 더 중점을 두세요
2. 말투 매칭: 기존 댓글들의 말투 패턴을 우선 확인
   - 기존 댓글이 대부분 존댓말이면 존댓말로, 반말이면 반말로 작성
   - 본문 말투는 참고용으로만 사용
3. 본문의 핵심 키워드를 댓글에 활용 (선택적): 본문에 나온 주요 단어를 자연스럽게 포함
4. 이모티콘 절대 사용 금지: 물결표(~), 느낌표(!), "ㅠㅠ" 등 모든 이모티콘/기호 사용하지 마세요
5. 마침표(.) 절대 사용 금지
6. "용" 어미 절대 사용 금지
7. 질문형 게시글: 답을 모르면 댓글 작성하지 않음
8. 반드시 10글자 이내로 완성

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
- 이모티콘 절대 사용 금지: 물결표(~), 느낌표(!), "ㅠㅠ" 등 모든 이모티콘/기호를 사용하지 마세요
- 예: "힘내요" → "힘내요", "좋아요" → "좋아요", "대박이네요" → "대박이네요", "아쉽네요" → "아쉽네요"
- 기분 좋은 글이면 담담하게 축하하고, 힘든 글이면 현실적인 톤(예: "아 지치네요", "버텨야죠")도 괜찮음
- 맞춤법을 반드시 정확하게 사용
- 게시판이 도박 관련이라는 맥락을 고려
- 게시글 내용과 기존 댓글 흐름 모두에 자연스럽게 이어지는 댓글
- 반드시 10글자 이내로 완성해야 함 (10글자를 넘기면 안 됨)
- ~요 체나 반말체를 적절히 섞어서 사용 (너무 반말만 쓰지 않기)

추론 절차 (반드시 내부적으로 거친 뒤 마지막에 댓글 한 줄만 출력):
1. 본문에서 핵심 키워드와 감정을 2개 이상 파악하고 친구에게 말하듯 정리합니다. (생각만, 출력 금지)
2. 기존 댓글 말투/이모티콘/길이를 분석해 어떤 어미·감정선이 자연스러운지 결정합니다. (생각만, 출력 금지)
3. 위 정보를 합쳐 10글자 이내 댓글을 설계합니다. 이모티콘은 절대 사용하지 않습니다.
최종 출력은 댓글 한 줄만 해야 하며, 다른 문장은 포함하면 안 됩니다.

{comments_priority_text}게시글 본문:
{post_content[:500]}{comments_text}

댓글:"""

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
                            'content': '당신은 도박 관련 사이트의 자유게시판에서 게시글 작성자의 톤과 내용에 맞춰 친근하지만 자연스러운 댓글을 작성하는 도우미입니다. 자유게시판이므로 도박 관련 얘기뿐만 아니라 일상 수다도 올라올 수 있습니다. 페이스북, 네이버 등 일반 커뮤니티와 똑같은 스타일로 댓글을 작성해야 합니다. 가장 중요한 것은: 1) 본문의 말투를 정확히 분석하는 것입니다 (본문이 "~할까요?" 같은 존댓말이면 댓글도 "~요", "~네요" 같은 높임말 사용, 본문이 반말이면 댓글도 반말 사용). 2) 본문의 핵심 키워드를 추출하여 댓글에 자연스럽게 활용하세요 (예: 본문에 "야식"이 있으면 "야식 좋지요"처럼 키워드를 포함). 3) 이모티콘(~, !, ㅠㅠ 등)은 절대 사용하지 마세요. 4) 마침표(.)는 절대 사용하지 마세요. 5) "용" 어미는 절대 사용하지 마세요 (예: "힘내용" ❌ → "힘내요" ✅). 6) 질문형 게시글에서 답을 모르면 댓글을 작성하지 마세요. 7) 기존 댓글들의 말투와 스타일을 분석하여 최대한 비슷하게 작성하세요. 8) 반드시 10글자 이내로 완성하고, 맞춤법을 정확하게 사용하세요. 9) 절대 "감사합니다", "감사해요", "감사" 같은 단어를 사용하지 말고, 형식적인 댓글을 사용하지 마세요.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'max_tokens': 80,  # 10자 이내 댓글을 위해 충분한 토큰 할당 (한국어는 토큰 효율이 낮음)
                    'temperature': 0.7  # 일관성 있는 댓글 생성을 위해 낮춤
                }
                
                async with session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 200:
                        result = json.loads(await response.text())
                        comment = result['choices'][0]['message']['content'].strip()
                        comment = comment.strip('"').strip("'")
                        
                        # 중복 어미 및 불필요한 문자 제거
                        comment = self.clean_comment(comment)
                        
                        # 10글자 초과 시 재시도
                        if len(comment) > 10:
                            print(f"[경고] 재시도 댓글이 10글자를 초과했습니다 ({len(comment)}자): {comment}")
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
        try:
            # 페이지가 닫혔는지 확인
            if not self.page or self.page.is_closed():
                print("[오류] 페이지가 이미 닫혔습니다. 브라우저를 다시 초기화합니다.")
                await self.reset_browser(headless=False)
            
            print(f"[댓글] {post_url} 접속 중...")
            try:
                await self.page.goto(post_url, wait_until='networkidle')
            except AttributeError as attr_err:
                if "_object" in str(attr_err):
                    print("[오류] 페이지 객체가 손상되었습니다. 브라우저를 재시작합니다.")
                    await self.reset_browser(headless=False)
                    await self.page.goto(post_url, wait_until='networkidle')
                else:
                    raise
            except Exception as goto_error:
                if "_object" in str(goto_error):
                    print("[오류] 페이지 이동 중 Playwright 채널 오류가 발생했습니다. 브라우저를 재시작합니다.")
                    await self.reset_browser(headless=False)
                    await self.page.goto(post_url, wait_until='networkidle')
                else:
                    raise
            await self.random_delay(2, 4)
            
            # 페이지 로드 확인
            current_url = self.page.url
            print(f"[댓글] 현재 페이지 URL: {current_url}")
            
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
            
            # 15분 내 반복 댓글 방지
            comment_text = await self.ensure_non_repeating_comment(comment_text, post_content, existing_comments)
            if not comment_text:
                print("[오류] 반복 댓글을 회피할 새 문장을 만들지 못했습니다.")
                return False
            
            # 어미/기호 다양화
            comment_text = self.enhance_tone_variation(comment_text, post_content)
            
            # 최종 중복 어미 제거 (모든 처리 후 한 번 더)
            comment_text = self.clean_comment(comment_text)
            
            # 댓글 간 랜덤 대기
            await self.enforce_comment_gap()
            
            # 페이지가 닫혔는지 다시 확인
            if not self.page or self.page.is_closed():
                print("[오류] 페이지가 닫혔습니다. 댓글 작성 중단.")
                return False
            
            # 댓글 입력 필드 찾기
            comment_input_selector = self.config.get('comment_input_selector', 'textarea[name="comment"]')
            await self.page.wait_for_selector(comment_input_selector, timeout=10000)
            
            # 댓글 입력 필드 클릭해서 포커스 주기
            await self.page.click(comment_input_selector)
            await self.random_delay(0.3, 0.5)
            
            # 댓글 입력
            await self.page.fill(comment_input_selector, '')
            await self.page.type(comment_input_selector, comment_text, delay=100)
            await self.random_delay(1, 2)
            
            # 댓글 작성 버튼 찾기 및 클릭
            # 우선순위: id="btn_submit" > input[type="submit"] > 기타
            submit_button_selector = '#btn_submit'
            submit_button = None
            
            try:
                # 먼저 정확한 ID로 찾기
                await self.page.wait_for_selector(submit_button_selector, timeout=3000, state='visible')
                submit_button = await self.page.query_selector(submit_button_selector)
                print(f"[댓글] 등록 버튼 찾음: {submit_button_selector}")
            except Exception:
                # ID로 못 찾으면 다른 선택자 시도
                fallback_selectors = [
                    'input#btn_submit',
                    'input.btn_submit',
                    'input[type="submit"]',
                    'input[value="댓글등록"]',
                    'button[type="submit"]'
                ]
                for selector in fallback_selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                        submit_button = await self.page.query_selector(selector)
                        submit_button_selector = selector
                        print(f"[댓글] 등록 버튼 찾음: {selector}")
                        break
                    except Exception:
                        continue
            
            if not submit_button:
                raise RuntimeError("댓글 등록 버튼을 찾을 수 없습니다.")
            
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
            
            # 댓글 작성 성공 시 게시글 URL 저장 (중복 방지)
            self.save_commented_post(post_url)
            self.record_comment_usage(comment_text)
            
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
            if self.page and not self.page.is_closed():
                await self.navigate_to_board_page(self.current_page)
            else:
                print("[경고] 페이지가 이미 닫혔습니다.")
        except Exception as e:
            print(f"[경고] 게시판으로 돌아가는 중 오류: {e}")
    
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
                if await self.write_comment(post_url):
                    success_count += 1
                    processed_urls.add(post_url)
                else:
                    print("[경고] 댓글 작성에 실패했습니다. 다음 게시글을 시도합니다.")
                
                # 게시판으로 돌아가기
                await self.go_back_to_board()
                
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
        # 게시글 처리 순서: 'latest' (최신순) 또는 'random' (랜덤)
        'post_order': os.getenv('POST_ORDER', 'latest'),
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
    # 브라우저 자동 설치 확인 (경고 무시 - sync API를 async 함수에서 호출하지만 문제없음)
    try:
        ensure_playwright_browser()
    except Exception as e:
        # 경고는 무시하고 계속 진행
        pass
    
    config = load_config()
    
    # 설정 검증
    if not config['username'] or not config['password']:
        print("[오류] LOGIN_USERNAME과 PASSWORD를 .env 파일에 설정해주세요.")
        return
    
    bot = MacroBot(config)
    await bot.run(headless=False)  # headless=True로 하면 브라우저 창이 안 보임


if __name__ == '__main__':
    asyncio.run(main())

