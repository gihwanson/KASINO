"""
자동 로그인 및 댓글 작성 매크로 프로그램
"""
import asyncio
import random
import time
import re
import aiohttp
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Page, Browser
from dotenv import load_dotenv
import os

load_dotenv()


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

    def _is_negative_content(self, text: str) -> bool:
        """본문이 부정적인지 단순 판별"""
        if not text:
            return False
        negative_keywords = ['잃', '망', '눈물', '울', '아쉽', '후회', '슬프', 'ㅠ', 'ㅜ', '손실', '적자', '좌절', '힘들']
        return any(keyword in text for keyword in negative_keywords)

    def enhance_tone_variation(self, comment_text: str, post_content: str = '') -> str:
        """물결/느낌표/ㅠㅠ 등을 다양하게 섞되 과한 특수문자 사용은 제한"""
        if not comment_text:
            return comment_text
        comment = comment_text.strip()
        
        # 특수 문자 개수 제한
        special_chars = ['~', '!', 'ㅠ', 'ㅜ']
        special_count = sum(comment.count(ch) for ch in special_chars)
        if special_count > 2:
            for ch in special_chars:
                while comment.count(ch) > 1:
                    comment = comment.replace(ch, '', 1)
        
        # 존댓말 섞기 (너무 반말만 나오는 것 방지)
        if '요' not in comment and random.random() < 0.4:
            suffix_options = ['요', '요~', '용', '요!']
            suffix = random.choice(suffix_options)
            if len(comment) + len(suffix) <= 10:
                comment += suffix
            elif len(comment) < 10:
                comment = (comment + suffix)[:10]
            else:
                comment = comment[:-1] + '요'
        
        # 특수 기호 다양화
        if not any(ch in comment for ch in ['~', '!', 'ㅠ']):
            if self._is_negative_content(post_content or comment):
                candidate = random.choice(['ㅠ', 'ㅠㅠ'])
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
        
        if comment.endswith('~') and random.random() < 0.3:
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
                alt_comment = await self.generate_ai_comment_retry(post_content, existing_comments, attempts + 1)
            if not alt_comment:
                break
            if alt_comment == comment_text:
                alt_comment += '~'
            if not self.has_meaningful_content(alt_comment):
                alt_comment = self.generate_style_matched_comment(existing_comments or [], post_content or '')
                if not self.has_meaningful_content(alt_comment):
                    alt_comment = "그래알~"
            alt_comment = self.enhance_tone_variation(alt_comment, post_content)
            comment_text = alt_comment
            attempts += 1
        print(f"[경고] 댓글이 계속 반복되어 기본 댓글로 전환합니다. 원본: {original}")
        fallback = self.generate_style_matched_comment(existing_comments or [], post_content or '')
        if fallback == original:
            fallback += '~'
        if not self.has_meaningful_content(fallback):
            fallback = "그래알~"
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
        
        # 스타일에 맞게 끝말 추가 (물결표 포함)
        if style['ending'] == '요':
            comment = f"{base}용~" if base in ['힘내', '좋아', '대박'] else f"{base}요~"
        elif style['ending'] == '다':
            comment = f"{base}다~"
        elif style['ending'] == '어':
            comment = f"{base}어~"
        elif style['ending'] == '해':
            comment = f"{base}해~"
        elif style['ending'] == '네요':
            comment = f"{base}네요~"
        else:
            comment = f"{base}요~"
        
        # 가벼운 댓글도 추가 (기분 좋은 글용)
        if base in ['축하', '부럽', '대박', '좋아'] and random.random() > 0.7:  # 30% 확률
            light_comments = ['데헿~', 'ㅎㅎ~', '좋아~', '대박~']
            comment = random.choice(light_comments)
        
        # 이모티콘 추가 (항상 물결표나 느낌표 사용)
        emojis = ['~', '!', '~!', '~~']
        if random.random() > 0.3:  # 70% 확률로 이모티콘 추가 (더 친근하게)
            if not comment.endswith('~') and not comment.endswith('!'):
                comment += random.choice(emojis)
        
        # 길이 제한 (10글자)
        if len(comment) > 10:
            comment = comment[:10]
        
        if not self.has_meaningful_content(comment):
            comment = '그래알~'
        
        comment = self.enhance_tone_variation(comment, post_content)
        
        print(f"[댓글] 기존 댓글 스타일 분석: 끝말={style['ending']}, 이모티콘={style['has_emoji']}")
        print(f"[댓글] 스타일 맞춤 댓글 생성: {comment}")
        
        return comment
    
    async def get_existing_comments(self) -> list:
        """기존 댓글들 가져오기"""
        try:
            # 댓글 영역 선택자들
            comment_selectors = [
                '.comment',
                '.reply',
                '.comment_list',
                '[class*="comment"]',
                '[class*="reply"]',
                '[id*="comment"]',
                '[id*="reply"]',
            ]
            
            comments = []
            
            # JavaScript로 댓글 찾기
            comments_data = await self.page.evaluate("""
                () => {
                    // 댓글 영역 찾기
                    const commentContainers = [
                        '.comment_list',
                        '.reply_list',
                        '[class*="comment"]',
                        '[class*="reply"]',
                        '[id*="comment"]',
                        '[id*="reply"]'
                    ];
                    
                    let allComments = [];
                    
                    for (const selector of commentContainers) {
                        const container = document.querySelector(selector);
                        if (container) {
                            // 댓글 텍스트 찾기
                            const commentElements = container.querySelectorAll('.comment_text, .reply_text, [class*="text"], [class*="content"]');
                            commentElements.forEach(el => {
                                const text = (el.innerText || el.textContent || '').trim();
                                if (text && text.length > 3 && text.length < 200) {
                                    allComments.push(text);
                                }
                            });
                            
                            // 직접 텍스트 노드 찾기
                            const directText = container.innerText || container.textContent;
                            if (directText) {
                                const lines = directText.split('\\n').map(l => l.trim()).filter(l => l.length > 3 && l.length < 200);
                                allComments = allComments.concat(lines);
                            }
                        }
                    }
                    
                    // 중복 제거
                    return [...new Set(allComments)].slice(0, 10); // 최대 10개
                }
            """)
            
            if comments_data:
                comments = [c for c in comments_data if c and len(c.strip()) > 3]
            
            return comments[:10]  # 최대 10개만
            
        except Exception as e:
            print(f"[경고] 기존 댓글을 가져오는 중 오류: {e}")
            return []
    
    async def generate_ai_comment(self, post_content: str, existing_comments: list = None) -> str:
        """AI를 사용해서 게시글 본문과 기존 댓글을 고려하여 관련된 댓글 생성"""
        # 기존 댓글과 본문 정보 저장 (AI 실패 시 사용)
        self._last_post_content = post_content
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
            # 기존 댓글 정보 추가
            if existing_comments and len(existing_comments) > 0:
                numbered_comments = "\n".join(
                    [f"{idx + 1}. {c}" for idx, c in enumerate(existing_comments[:8])]
                )
                comments_text = f"\n\n현재 댓글 흐름 (최근 {min(len(existing_comments), 8)}개):\n{numbered_comments}\n\n위 댓글들의 말투와 감정선, 이모티콘 빈도를 참고해 자연스럽게 이어주세요."
            else:
                comments_text = "\n\n현재 댓글 흐름: (댓글 없음)"
            
            # 프롬프트 작성
            prompt = f"""다음 게시글 본문과 기존 댓글들을 읽고, 작성자의 감정에 공감하는 자연스러운 댓글을 작성해주세요.

⚠️ 중요: 이 게시판은 도박 관련 게시판입니다. 다양한 주제의 글이 올라오지만 메인 카테고리는 도박입니다.
- 도박으로 잃은 사람들, 많이 딴 사람들 등 도박 관련 경험을 공유하는 게시판
- 도박과 직접 관련 없는 글도 올라올 수 있지만, 게시판의 맥락은 도박입니다
- 댓글은 게시판의 맥락을 고려하면서도 게시글 내용에 맞게 작성해야 합니다

- 작성자의 톤과 감정을 정확히 파악하고 그에 맞춰 댓글 작성
- 친구 같은 느낌의 글 → 친구처럼 편하게 반말이나 캐주얼한 댓글
- 형식적인 글 → 형식적인 댓글 (하지만 "감사합니다" 같은 금지 단어는 사용하지 말 것)
- 시답잖은 소리 → 그냥 맞춰주기만 하면 됨 (꼭 긍정적일 필요 없음)
- 절망/후회하는 글 → "힘내용~", "아쉽네~", "다음엔 조심해~", "공감해~", "위로해~"
- 기쁨/성공한 글 → "축하해~", "부럽다~", "좋아~", "대박~", "데헿~" (할말 없을 때 가볍게)
- 아쉬운 글 → "아쉽네~", "다음엔 잘될 거야~", "아깝다~"
- 슬프거나 힘든 글 → "힘내~", "공감해~", "위로해~", "아쉽네~"
- 게시판이 도박 관련이라는 맥락을 고려하되, 게시글 내용과 톤에 맞는 댓글 작성
- 절대 형식적인 댓글을 사용하지 말 것 (예: "좋은 글 감사합니다", "좋은 정보 감사합니다", "유용한 정보네요", "잘 읽었습니다" 등)
- 게시글 내용뿐 아니라 기존 댓글 흐름과도 연관된 댓글이어야 함
- 기존 댓글과 자연스럽게 이어지는 톤과 스타일로 작성 (말투·이모티콘 빈도를 맞추기)
- 반드시 10글자 이내로 완성해야 함 (10글자를 넘기면 안 됨, 잘라내지 말고 처음부터 10글자 이내로 작성)
- ~입니다 체는 사용하지 말고 ~요 체나 반말체로 작성하되, 너무 반말만 쓰지 말고 "~요", "~용", "~요!"처럼 적당히 섞어서 사용
- 물결표(~), 느낌표(!), "ㅠㅠ" 같은 기호를 상황에 맞게 0~1회만 사용 (매크로 티 안 나게)
- 예: "힘내요" → "힘내용~", "좋아요" → "좋아~", "대박이네요" → "대박~", "아쉽네요" → "아쉽네ㅠㅠ"
- 격식이 조금 떨어져도 괜찮음, 오히려 더 자연스럽고 친근한 톤으로 작성
- 자연스럽고 친근한 톤으로 작성
- 기분 좋은 글인데 할말 없을 땐 "데헿~", "ㅎㅎ~", "좋아~" 같은 가벼운 댓글도 괜찮음
- 반드시 게시글 내용과 관련된 댓글이어야 함
- 기존 댓글과 너무 비슷하지 않게 작성
- 본문이 친구처럼 편하게 쓴 글이라면 친구처럼 편하게 댓글 작성
- 본문이 시답잖은 소리라면 그냥 맞춰주기만 하면 됨 (꼭 긍정적이거나 위로할 필요 없음)

추론 절차 (반드시 내부적으로 거친 뒤 마지막에 댓글 한 줄만 출력):
1. 본문에서 핵심 키워드와 감정을 2개 이상 파악하고, 그 감정을 친구에게 설명하듯 요약합니다. (생각만, 출력 금지)
2. 기존 댓글들의 말투/이모티콘/길이 패턴을 분석해 어떤 어미가 자연스럽고 어떤 감정선이 이어지는지 결정합니다. (생각만, 출력 금지)
3. 위 두 정보를 합쳐 10글자 이내의 댓글을 설계합니다. 물결표/느낌표 사용 여부도 함께 결정하되 과하게 반복하지 않습니다.
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

게시글 본문:
{post_content[:500]}{comments_text}

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
                            'content': '당신은 도박 관련 게시판에서 게시글 작성자의 톤과 내용에 맞춰 친근하고 캐주얼한 댓글을 작성하는 도우미입니다. 작성자가 친구처럼 편하게 썼다면 친구처럼 편하게, 형식적으로 썼다면 형식적으로, 시답잖은 소리면 그냥 맞춰주기만 하면 됩니다. 꼭 긍정적이거나 위로할 필요 없습니다. 물결표(~), 느낌표(!), "ㅠㅠ" 같은 기호는 상황에 맞게 0~1회만 사용해 과도하게 반복되지 않도록 하세요. "~요", "~용", "~요!" 같은 가벼운 존댓말도 적절히 섞어서 너무 반말만 사용하지 않도록 합니다. 기분 좋은 글인데 할말 없을 땐 "데헿~", "ㅎㅎ~" 같은 가벼운 댓글도 괜찮습니다. 반드시 10글자 이내로 완성해야 합니다 (10글자를 넘기면 안 됩니다). 절대 "감사합니다", "감사해요", "감사" 같은 단어를 사용하지 마세요. 절대 형식적인 댓글("좋은 글 감사합니다", "유용한 정보네요" 등)을 사용하지 마세요.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'max_tokens': 30,  # 10자 이내 댓글을 위해 토큰 수 감소
                    'temperature': 0.9
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
                            return await self.generate_ai_comment_retry(post_content, existing_comments, 1)
                        
                        # ~입니다 체 제거 및 ~요 체로 변경
                        comment = comment.replace('입니다', '요').replace('입니다.', '요').replace('입니다!', '요')
                        
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
    
    async def generate_ai_comment_retry(self, post_content: str, existing_comments: list = None, retry_count: int = 0) -> str:
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
                comments_text = f"\n\n현재 댓글 흐름 (최근 {min(len(existing_comments), 8)}개):\n{numbered_comments}\n\n위 댓글들의 말투와 감정선, 이모티콘 빈도를 참고해 자연스럽게 이어주세요."
            else:
                comments_text = "\n\n현재 댓글 흐름: (댓글 없음)"
            
            # 더 강력한 프롬프트
            prompt = f"""다음 게시글 본문을 읽고, 작성자의 감정에 공감하는 댓글을 작성해주세요.

⚠️ 중요: 이 게시판은 도박 관련 게시판입니다. 다양한 주제의 글이 올라오지만 메인 카테고리는 도박입니다.
- 도박으로 잃은 사람들, 많이 딴 사람들 등 도박 관련 경험을 공유하는 게시판
- 도박과 직접 관련 없는 글도 올라올 수 있지만, 게시판의 맥락은 도박입니다
- 게시판의 맥락을 고려하면서도 게시글 내용에 맞는 댓글 작성

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
- 물결표(~), 느낌표(!), "ㅠㅠ" 같은 기호를 상황에 맞게 0~1회만 사용 (과도하게 반복하지 말 것)
- 예: "힘내요" → "힘내용~", "좋아요" → "좋아~", "대박이네요" → "대박~", "아쉽네요" → "아쉽네ㅠㅠ"
- 기분 좋은 글인데 할말 없을 땐 "데헿~", "ㅎㅎ~", "좋아~" 같은 가벼운 댓글도 괜찮음
- 게시판이 도박 관련이라는 맥락을 고려
- 게시글 내용과 기존 댓글 흐름 모두에 자연스럽게 이어지는 댓글
- 반드시 10글자 이내로 완성해야 함 (10글자를 넘기면 안 됨)
- ~요 체나 반말체를 적절히 섞어서 사용 (너무 반말만 쓰지 않기)

추론 절차 (반드시 내부적으로 거친 뒤 마지막에 댓글 한 줄만 출력):
1. 본문에서 핵심 키워드와 감정을 2개 이상 파악하고 친구에게 말하듯 정리합니다. (생각만, 출력 금지)
2. 기존 댓글 말투/이모티콘/길이를 분석해 어떤 어미·감정선이 자연스러운지 결정합니다. (생각만, 출력 금지)
3. 위 정보를 합쳐 10글자 이내 댓글을 설계하고 물결표/느낌표 사용 여부를 정하되, 과하게 반복하지 않습니다.
최종 출력은 댓글 한 줄만 해야 하며, 다른 문장은 포함하면 안 됩니다.

게시글 본문:
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
                            'content': '당신은 도박 관련 게시판에서 게시글 작성자의 감정에 공감하는 친근한 댓글을 작성하는 도우미입니다. 작성자가 친구처럼 편하게 썼다면 친구처럼 편하게, 형식적으로 썼다면 형식적으로, 시답잖은 소리면 그냥 맞춰주기만 하면 됩니다. 물결표(~), 느낌표(!), "ㅠㅠ" 같은 기호는 상황에 맞게 0~1회만 사용하고, "~요", "~용", "~요!" 같은 가벼운 존댓말도 적절히 섞어 너무 반말만 나오지 않게 해주세요. 게시판의 맥락을 고려하면서도 게시글 내용에 맞는 댓글을 작성해야 합니다. 절대 "감사합니다", "감사해요", "감사" 같은 단어를 사용하지 마세요. 절대 형식적인 댓글("좋은 글 감사합니다", "유용한 정보네요" 등)을 사용하지 마세요. 반드시 게시글 내용과 감정에 관련된 댓글이어야 합니다.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'max_tokens': 30,  # 10자 이내 댓글을 위해 토큰 수 감소
                    'temperature': 1.0  # 더 창의적으로
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
                        
                        # 10글자 초과 시 재시도
                        if len(comment) > 10:
                            print(f"[경고] 재시도 댓글이 10글자를 초과했습니다 ({len(comment)}자): {comment}")
                            print(f"[경고] 기존 댓글 스타일로 댓글 생성...")
                            return self.generate_style_matched_comment(existing_comments or [], post_content)
                        
                        comment = comment.replace('입니다', '요').replace('입니다.', '요')
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
                print(f"[경고] 댓글 읽기 함수를 확인하세요!")
                print(f"[경고] ========================================")
            
            if post_content and len(post_content.strip()) > 10:
                print(f"[댓글] 본문 읽기 성공! (길이: {len(post_content)}자)")
                print(f"[댓글] 본문 미리보기: {post_content[:100]}...")
                
                # AI로 댓글 생성 (본문 + 기존 댓글 고려)
                print("[댓글] ⭐ AI 댓글 생성 시작...")
                comment_text = await self.generate_ai_comment(post_content, existing_comments)
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
                comment_text = "그래알~"
            
            # 15분 내 반복 댓글 방지
            comment_text = await self.ensure_non_repeating_comment(comment_text, post_content, existing_comments)
            if not comment_text:
                print("[오류] 반복 댓글을 회피할 새 문장을 만들지 못했습니다.")
                return False
            
            # 어미/기호 다양화
            comment_text = self.enhance_tone_variation(comment_text, post_content)
            
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
            
            # 댓글 작성 버튼 클릭
            submit_button_candidates = self.config.get(
                'submit_button_selector',
                'input#btn_submit, #btn_submit, input.btn_submit, button.btn_submit, button[type="submit"], input[type="submit"]'
            )
            
            selector_list = [s.strip() for s in submit_button_candidates.split(',') if s.strip()]
            # 필수 기본 후보들 추가
            selector_list.extend([
                '#btn_submit', 'input#btn_submit', 'input[value="댓글등록"]',
                'input[value*="댓글"]', 'button#btn_submit', 'button.btn_submit'
            ])
            
            submit_button = None
            last_selector = None
            for selector in selector_list:
                last_selector = selector
                try:
                    await self.page.wait_for_selector(selector, timeout=3000, state='visible')
                    submit_button = await self.page.query_selector(selector)
                except Exception:
                    submit_button = None
                if submit_button:
                    break
            
            if not submit_button:
                raise RuntimeError(f"댓글 등록 버튼을 찾을 수 없습니다. 마지막 시도 선택자: {last_selector}")
            
            print(f"[댓글] 등록 버튼 선택자: {last_selector}")
            
            await submit_button.scroll_into_view_if_needed()
            await self.random_delay(0.3, 0.6)
            print("[댓글] 등록 버튼 클릭 시도")
            
            clicked = False
            try:
                await submit_button.hover()
                await submit_button.click(force=True, timeout=5000)
                clicked = True
            except Exception as click_error:
                print(f"[경고] 기본 클릭 실패: {click_error}")
            
            if not clicked:
                print("[댓글] 클릭 실패로 JavaScript 이벤트를 직접 호출합니다.")
                await self.page.eval_on_selector(
                    last_selector,
                    """(btn) => {
                        btn.removeAttribute('disabled');
                        if (btn.click) {
                            btn.click();
                        } else if (btn.form) {
                            btn.form.submit();
                        }
                    }"""
                )
            
            # 버튼 클릭이 제대로 되었는지 확인 (폼 제출/댓글 반영 대기)
            try:
                await self.page.wait_for_function(
                    """(inputSelector) => {
                        const input = document.querySelector(inputSelector);
                        if (!input) return false;
                        if ((input.value || '').trim().length === 0) return true;
                        const form = input.closest('form');
                        if (form && form.dataset.submitVisualized === 'done') return true;
                        const btn = document.querySelector('#btn_submit, input#btn_submit, button#btn_submit');
                        if (btn && btn.dataset.clicked) return true;
                        return false;
                    }""",
                    comment_input_selector,
                    timeout=5000
                )
            except Exception:
                # 입력창이 그대로면 잠시 더 대기하고 최후에 폼 직접 제출
                await self.random_delay(0.5, 1.0)
                try:
                    await self.page.eval_on_selector(
                        comment_input_selector,
                        """(input) => {
                            const form = input.closest('form');
                            if (form) {
                                form.submit();
                                form.dataset.submitVisualized = 'done';
                            }
                        }"""
                    )
                except Exception as submit_err:
                    print(f"[경고] 폼 강제 제출 중 오류: {submit_err}")
            
            # 제출 완료 대기
            await self.random_delay(2, 4)
            
            print(f"[댓글] 댓글 작성 완료: {comment_text}")
            
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
    config = load_config()
    
    # 설정 검증
    if not config['username'] or not config['password']:
        print("[오류] LOGIN_USERNAME과 PASSWORD를 .env 파일에 설정해주세요.")
        return
    
    bot = MacroBot(config)
    await bot.run(headless=False)  # headless=True로 하면 브라우저 창이 안 보임


if __name__ == '__main__':
    asyncio.run(main())

