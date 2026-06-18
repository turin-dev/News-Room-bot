import re
import asyncio
import aiohttp
import logging
import os
import nltk
from newspaper import Article as Article3k
from playwright.async_api import async_playwright

# NLTK 초기화
nltk.download('punkt_tab', quiet=True)
nltk.download('punkt', quiet=True)

logger = logging.getLogger('news_bot')

class CrawlingService:
    def __init__(self):
        self.naver_client_id = os.getenv("NAVER_CLIENT_ID")
        self.naver_client_secret = os.getenv("NAVER_CLIENT_SECRET")
        self.cloudflare_api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.use_cloudflare = bool(self.cloudflare_api_token)
        
        self.newspaper_available = True
        self.playwright_available = True
        
        # 선택자 목록 (추출 효율화)
        self.selectors = [
            'article',
            '.article_body',
            '.article-body',
            '#articleBodyContents',
            '#articeBody',
            '.news_end',
            '.article_view',
            '#newsContent',
            '.article-content',
            'div[itemprop="articleBody"]',
            '#content',
            '.content'
        ]

    async def fetch_naver_news(self, query="IT 기술 인공지능 소프트웨어 -경제 -주식 -투자", display=10):
        """네이버 뉴스 API에서 IT 기술 뉴스 검색"""
        if not self.naver_client_id or not self.naver_client_secret:
            logger.warning("네이버 API 클라이언트 ID 또는 시크릿이 설정되지 않았습니다. 뉴스 검색을 건너뜁니다.")
            return []
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": self.naver_client_id,
            "X-Naver-Client-Secret": self.naver_client_secret
        }
        params = {
            "query": query,
            "display": display,
            "sort": "date"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("items", [])
                    else:
                        error_text = await response.text()
                        logger.error(f"네이버 API 오류 발생: Status {response.status}, Error: {error_text}")
                        return []
            except Exception as e:
                logger.error(f"네이버 API 요청 중 오류 발생: {e}")
                return []

    async def extract_article_content(self, url: str) -> tuple[str, str]:
        """
        뉴스 기사 본문 추출 (4단계 폴백)
        1. Cloudflare Browser Rendering (환경변수 설정 시)
        2. newspaper3k 시도
        3. 로컬 playwright 시도
        4. 실패 시 None 반환
        """
        
        # 1단계: Cloudflare Browser Rendering 시도
        if self.use_cloudflare and self.cloudflare_api_token:
            try:
                logger.info(f"  -> [0단계] Cloudflare Browser Rendering 시도...")
                content = await self._extract_with_cloudflare(url)
                if content:
                    logger.info(f"     ✓ Cloudflare 성공 (길이: {len(content)})")
                    return content, "cloudflare"
            except Exception as e:
                logger.warning(f"     ✗ Cloudflare 오류: {e}")

        # 2단계: newspaper3k 시도
        try:
            logger.info(f"  -> [1단계] newspaper3k로 본문 추출 시도...")
            article = Article3k(url, language='ko')
            await asyncio.wait_for(asyncio.to_thread(article.download), timeout=10.0)
            await asyncio.wait_for(asyncio.to_thread(article.parse), timeout=5.0)
            
            content = article.text.strip()
            if content and len(content) > 100:
                logger.info(f"     ✓ newspaper3k 성공 (길이: {len(content)})")
                return content, "newspaper3k"
        except Exception as e:
            logger.warning(f"     ✗ newspaper3k 오류 또는 데이터 부족")

        # 3단계: 로컬 Playwright 시도
        try:
            logger.info(f"  -> [2단계] 로컬 playwright로 본문 추출 시도...")
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=15000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                
                content = await self._find_content_with_selectors(page)
                await browser.close()
                
                if content:
                    logger.info(f"     ✓ 로컬 playwright 성공 (길이: {len(content)})")
                    return content, "playwright"
        except Exception as e:
            logger.error(f"     ✗ 로컬 playwright 오류: {e}")

        return None, "failed"

    async def _extract_with_cloudflare(self, url: str) -> str:
        """Cloudflare의 Browser Rendering API를 사용하여 페이지 추출"""
        async with async_playwright() as p:
            # Cloudflare Browser Rendering 연결
            browser = await p.chromium.connect_over_cdp(
                f"wss://browser.cloudflare.com/v1?token={self.cloudflare_api_token}"
            )
            page = await browser.new_page()
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000) # JS 로딩 대기
            
            content = await self._find_content_with_selectors(page)
            await browser.close()
            return content

    async def _find_content_with_selectors(self, page) -> str:
        """페이지에서 선택자를 사용하여 본문 텍스트 추출"""
        for selector in self.selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and len(text.strip()) > 100:
                        return text.strip()
            except:
                continue
        return None

    @staticmethod
    def get_news_provider(news_link: str) -> str:
        """뉴스 링크에서 언론사 이름 추출"""
        # (기존 logic 유지)
        providers = {
            "chosun.com": "조선일보", "donga.com": "동아일보", "joongang.co.kr": "중앙일보",
            "joins.com": "중앙일보", "hani.co.kr": "한겨레", "kyunghyang.com": "경향신문",
            "khan.co.kr": "경향신문", "seoul.co.kr": "서울신문", "hankookilbo.com": "한국일보",
            "munhwa.com": "문화일보", "segye.com": "세계일보", "kmib.co.kr": "국민일보",
            "dt.co.kr": "디지털타임스", "naeil.com": "내일신문", "yna.co.kr": "연합뉴스",
            "newsis.com": "뉴시스", "news1.kr": "뉴스1", "newsen.com": "뉴스엔",
            "moneytoday.co.kr": "머니투데이", "pressian.com": "프레시안", "ohmynews.com": "오마이뉴스",
            "vop.co.kr": "민중의소리", "dailian.co.kr": "데일리안", "newdaily.co.kr": "뉴데일리",
            "mediatoday.co.kr": "미디어오늘", "sisain.co.kr": "시사IN", "wikitree.co.kr": "위키트리",
            "insight.co.kr": "인사이트", "newsof.co.kr": "뉴스오브", "newstapa.org": "뉴스타파",
            "newsnjoy.or.kr": "뉴스앤조이", "kukinews.com": "쿠키뉴스", "sportsq.co.kr": "스포츠Q",
            "breaknews.com": "브레이크뉴스", "dailysecu.com": "데일리시큐", "goodmorningcc.com": "굿모닝충청",
            "newsworker.co.kr": "뉴스워커", "newspower.co.kr": "뉴스파워", "newscj.com": "뉴스씨제이",
            "ablenews.co.kr": "에이블뉴스", "beminor.com": "비마이너", "rapportian.com": "라포르시안",
            "straightnews.co.kr": "스트레이트뉴스", "mk.co.kr": "매일경제", "hankyung.com": "한국경제",
            "mt.co.kr": "머니투데이", "news.mt.co.kr": "머니투데이", "sedaily.com": "서울경제",
            "etoday.co.kr": "이투데이", "edaily.co.kr": "이데일리", "fnnews.com": "파이낸셜뉴스",
            "heraldcorp.com": "헤럴드경제", "ajunews.com": "아주경제", "newspim.com": "뉴스핌",
            "newsway.co.kr": "뉴스웨이", "thebell.co.kr": "더벨", "businesspost.co.kr": "비즈니스포스트",
            "chosunbiz.com": "조선비즈", "biz.chosun.com": "조선비즈", "news.einfomax.co.kr": "연합인포맥스",
            "infostock.co.kr": "인포스탁", "tfmedia.co.kr": "더팩트", "thefact.co.kr": "더팩트",
            "tfnews.co.kr": "TF뉴스", "businesskorea.co.kr": "비즈니스코리아", "greened.kr": "환경일보",
            "ebn.co.kr": "EBN", "fortunekorea.co.kr": "포춘코리아", "motorgraph.com": "모터그래프",
            "autotimes.co.kr": "오토타임즈", "autoview.co.kr": "오토뷰", "autotribune.co.kr": "오토트리뷴",
            "dailycar.co.kr": "데일리카", "zdnet.co.kr": "ZDNet코리아", "etnews.com": "전자신문",
            "ddaily.co.kr": "디지털데일리", "bloter.net": "블로터", "itdonga.com": "IT동아",
            "betanews.net": "베타뉴스", "aitimes.com": "AI타임스", "aitimes.kr": "AI타임스",
            "boannews.com": "보안뉴스", "itworld.co.kr": "ITWorld", "ciokorea.com": "CIO Korea",
            "techm.kr": "테크M", "epnc.co.kr": "전자부품", "thelec.kr": "더일렉",
            "thelec.net": "더일렉", "digitaltoday.co.kr": "디지털투데이", "aving.net": "아빙뉴스",
            "datanet.co.kr": "데이터넷", "comworld.co.kr": "컴퓨터월드", "webtoday.co.kr": "웹투데이",
            "itbiznews.com": "IT비즈뉴스", "iconews.co.kr": "아이콘뉴스", "inven.co.kr": "인벤",
            "thisisgame.com": "디스이즈게임", "ruliweb.com": "루리웹", "gameshot.net": "게임샷",
            "gamefocus.co.kr": "게임포커스", "gamemeca.com": "게임메카", "gametoc.co.kr": "게임톡",
            "dailyesports.com": "데일리e스포츠", "fomos.co.kr": "포모스", "gamechosun.co.kr": "게임조선",
            "khgames.co.kr": "경향게임스", "kbs.co.kr": "KBS", "news.kbs.co.kr": "KBS뉴스",
            "mbc.co.kr": "MBC", "imnews.imbc.com": "MBC뉴스", "sbs.co.kr": "SBS",
            "news.sbs.co.kr": "SBS뉴스", "jtbc.co.kr": "JTBC", "news.jtbc.co.kr": "JTBC뉴스",
            "ytn.co.kr": "YTN", "mbn.co.kr": "MBN", "tvchosun.com": "TV조선",
            "ichannela.com": "채널A", "channela.com": "채널A", "news.chosun.com": "채널A",
            "ebs.co.kr": "EBS", "tbs.seoul.kr": "TBS", "obs.co.kr": "OBS",
            "wowtv.co.kr": "한국경제TV", "arirang.co.kr": "아리랑TV", "ntv.co.kr": "NTV",
            "gbs.or.kr": "경기방송", "gtb.co.kr": "경기티브이", "pbc.co.kr": "평화방송",
            "cpbc.co.kr": "평화방송", "bbs.or.kr": "불교방송", "febc.net": "극동방송",
            "gugakfm.co.kr": "국악방송", "tbsradio.co.kr": "교통방송", "naver.com": "네이버",
            "news.naver.com": "네이버뉴스", "m.news.naver.com": "네이버뉴스", "daum.net": "다음",
            "news.v.daum.net": "다음뉴스", "news.daum.net": "다음뉴스", "media.daum.net": "다음뉴스",
            "nate.com": "네이트", "news.nate.com": "네이트뉴스", "zum.com": "줌",
            "news.zum.com": "줌뉴스", "news.google.com": "구글뉴스", "google.com/news": "구글뉴스",
            "msn.com": "MSN뉴스", "news.yahoo.co.kr": "야후뉴스", "m-i.kr": "매일일보",
            "inthenews.co.kr": "인더뉴스"
        }
        
        for domain, name in providers.items():
            if domain in news_link:
                return name
        
        domain_match = re.search(r'https?://(?:www\.)?([^/]+)', news_link)
        if domain_match:
            domain = domain_match.group(1)
            return domain.split('.')[0].upper()
            
        return "UNKNOWN"

    @staticmethod
    def is_it_news(title: str, content: str) -> bool:
        """제목과 내용을 분석하여 IT 관련 뉴스인지 판단"""
        core_it_keywords = [
            '인공지능', 'ai', 'artificial intelligence', '머신러닝', 'machine learning',
            '딥러닝', 'deep learning', 'gpt', '챗gpt', 'chatgpt', 'claude', '클로드',
            'gemini', '제미나이', 'llama', '라마', 'ai 에이전트', 'ai agent',
            '소프트웨어', 'software', '프로그래밍', 'programming', '코딩', 'coding',
            '개발자', 'developer', 'software engineer', '앱개발', 'app development',
            '사이버보안', 'cybersecurity', '해킹', 'hacking', '해커', 'hacker',
            '랜섬웨어', 'ransomware', '악성코드', 'malware', '제로 트러스트', 'zero trust',
            '데이터유출', 'data breach', '블록체인', 'blockchain', '암호화폐', 'cryptocurrency',
            '비트코인', 'bitcoin', '이더리움', 'ethereum', '솔라나', 'solana', 'nft', 'web3',
            '디파이', 'defi', '메타버스', 'metaverse', 'vr', 'virtual reality', '가상현실',
            'ar', 'augmented reality', '증강현실', 'mr', 'mixed reality', 'xr',
            '반도체', 'semiconductor', '칩', 'chip', 'cpu', 'gpu', 'npu', 'tpu', 'lpu',
            '클라우드', 'cloud', '데이터센터', 'data center', 'saas', 'paas', 'iaas',
            '자율주행', 'autonomous driving', 'fsd', 'autopilot', '오토파일럿',
            '드론기술', 'drone', '로봇공학', 'robotics', '로봇', 'robot', '휴머노이드', 'humanoid',
            '오픈ai', 'openai', '앤스로픽', 'anthropic', '딥마인드', 'deepmind',
            '빅데이터', 'big data', '데이터분석', 'data analysis', '알고리즘', 'algorithm',
            'hbm', '고대역폭메모리', 'high bandwidth memory', 'cxl', 'pim', '온디바이스 ai',
            'on-device ai', 'edge ai', '생성형 ai', 'generative ai', 'rag', '검색 증강 생성',
            '파인튜닝', 'fine-tuning', '미세조정', '프롬프트 엔지니어링', 'prompt engineering'
        ]
        
        general_it_keywords = [
            '애플리케이션', 'application', '플랫폼', 'platform', 'api', '5g', '6g',
            '통신기술', 'telecommunication', 'iot', 'internet of things', '사물인터넷',
            '게임개발', 'game development', '게임엔진', 'game engine', 'unity', '유니티',
            'unreal engine', '언리얼 엔진', 'e스포츠', 'esports', '스마트폰', 'smartphone',
            '태블릿', 'tablet', '웨어러블', 'wearable', '전기차', 'ev', 'electric vehicle',
            '배터리기술', 'battery technology', '보안패치', 'security patch', '암호화', 'encryption',
            '인증', 'authentication', '스타트업', 'startup', '테크기업', 'tech company',
            '유니콘', 'unicorn', '디지털전환', 'dx', 'digital transformation', '디지털화'
        ]
        
        support_it_keywords = [
            '구글', 'google', 'alphabet', '알파벳', '애플', 'apple', '마이크로소프트', 'microsoft',
            'ms', '아마존', 'amazon', 'aws', '메타', 'meta', 'facebook', '페이스북',
            '테슬라', 'tesla', '네이버', 'naver', '카카오', 'kakao', '삼성전자', 'samsung',
            'sk하이닉스', 'sk hynix', '하이닉스', 'hynix', 'lg전자', 'lg electronics',
            '엔비디아', 'nvidia', '인텔', 'intel', 'amd', 'tsmc', '퀄컴', 'qualcomm',
            '브로드컴', 'broadcom', 'asml', 'arm', '암', '슈퍼마이크로', 'smci',
            '스노우플레이크', 'snowflake', '데이터브릭스', 'databricks', '허깅페이스', 'hugging face',
            '넷플릭스', 'netflix', '오라클', 'oracle', 'ibm', '어도비', 'adobe',
            'salesforce', '세일즈포스', '기술', 'technology', '서비스', 'service',
            '온라인', 'online', '인터넷', 'internet', '웹', 'web', '디지털', 'digital',
            'it', '정보기술', 'information technology', '게임', 'game', 'pc',
            '데이터', 'data', '네트워크', 'network', '보안', 'security'
        ]
        
        exclude_keywords = [
            '주가', '시세', '상장', 'ipo', '코스피', 'kospi', '코스닥', 'kosdaq', '증시',
            '투자', 'investment', '매수', 'buy', '매도', 'sell', '수익률', 'yield',
            '배당', 'dividend', '주주총회', 'shareholders meeting', '분기실적', 'quarterly results',
            '영업이익', 'operating profit', '순이익', 'net profit', '매출액', 'revenue',
            '실적발표', 'earnings release', '증권', 'securities', '펀드', 'fund',
            '채권', 'bond', '금리', 'interest rate', '환율', 'exchange rate',
            '대통령', 'president', '국회', 'assembly', '정치', 'politics', '선거', 'election',
            '의원', 'lawmaker', '부동산', 'real estate', '아파트', 'apartment', '집값'
        ]
        
        title_lower = title.lower()
        exclude_count = sum(1 for keyword in exclude_keywords if keyword.lower() in title_lower)
        if exclude_count >= 2:
            return False
            
        combined_text = f"{title} {content}".lower()
        score = 0
        for keyword in core_it_keywords:
            if keyword.lower() in combined_text: score += 3
        for keyword in general_it_keywords:
            if keyword.lower() in combined_text: score += 2
        for keyword in support_it_keywords:
            if keyword.lower() in combined_text: score += 1
            
        for keyword in core_it_keywords:
            if keyword.lower() in title_lower:
                score += 2
                break
                
        return score >= 5
