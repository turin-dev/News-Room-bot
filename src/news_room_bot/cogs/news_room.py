import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import datetime
import re
import html
import logging
from logging.handlers import RotatingFileHandler

from .models import init_db
from ..services.crawling_service import CrawlingService
from ..services.ai_service import AIService
from ..repositories.news_repository import NewsRepository

# 로깅 설정
def setup_logger():
    """로거 설정 - 파일과 콘솔에 동시 출력"""
    logger = logging.getLogger('news_bot')
    logger.setLevel(logging.INFO)
    
    # 이미 핸들러가 있으면 추가하지 않음 (중복 방지)
    if logger.handlers:
        return logger
    
    # 로그 포맷 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 파일 핸들러 (최대 10MB, 5개 백업 파일 유지)
    file_handler = RotatingFileHandler(
        'news_bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 로커 초기화
logger = setup_logger()

class NewsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_id_str = os.getenv("DISCORD_CHANNEL_ID")
        self.db_path = os.getenv("NEWS_DB_PATH", "/data/news_history.db")
        self.channel_id = None

        if self.channel_id_str:
            try:
                self.channel_id = int(self.channel_id_str)
            except ValueError:
                logger.error(f"오류: DISCORD_CHANNEL_ID가 올바른 숫자 형식이 아닙니다. (값: {self.channel_id_str})")
        
        # 서비스 및 리포지토리 초기화
        self.crawling_service = CrawlingService()
        self.ai_service = AIService()
        self.db_session_maker = None
        self.news_repo = None
        
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self._init_database())

    async def _init_database(self):
        """데이터베이스 및 리포지토리 초기화"""
        await self.bot.wait_until_ready()
        try:
            self.db_session_maker = await init_db(self.db_path)
            self.news_repo = NewsRepository(self.db_session_maker)
            count = await self.news_repo.get_total_count()
            logger.info(f"✓ 데이터베이스 초기화 완료. 경로: {self.db_path} (총 {count}개 레코드)")
        except Exception as e:
            logger.error(f"데이터베이스 초기화 오류: {e}")

    async def cog_load(self):
        """Cog가 로드될 때 실행"""
        if self.channel_id:
            self.send_news_loop.start()
            logger.info("✓ 뉴스 자동 전송 루프 시작.")
        else:
            logger.warning("경고: DISCORD_CHANNEL_ID가 없어 자동 전송 루프를 시작하지 않습니다.")

    async def cog_unload(self):
        """Cog가 언로드될 때 실행"""
        self.send_news_loop.stop()
        logger.info("뉴스 자동 전송 루프 중지.")

    @tasks.loop(minutes=30.0)
    async def send_news_loop(self):
        """30분마다 최신 뉴스를 확인하고 채널에 전송"""
        await self.bot.wait_until_ready()
        logger.info("\n--- 뉴스 자동 업데이트 시작 ---")
        try:
            await self.fetch_and_send_news()
        except Exception as e:
            logger.error(f"자동 업데이트 루프 중 치명적 오류 발생: {e}", exc_info=True)

    @app_commands.command(name="뉴스검색", description="최신 IT 뉴스를 즉시 검색하여 전송합니다.")
    async def manual_news(self, interaction: discord.Interaction):
        """즉시 뉴스를 크롤링하여 전송하는 슬래시 명령어"""
        await interaction.response.defer(thinking=True)
        logger.info(f"-> 전송 요청자: {interaction.user} (명령어: /뉴스검색)")
        
        try:
            # 뉴스 가져오기 및 전송 실행
            sent = await self.fetch_and_send_news()
            
            if sent:
                await interaction.followup.send("✅ 최신 뉴스를 성공적으로 찾아서 전송했습니다!")
            else:
                await interaction.followup.send("ℹ️ 새로운 뉴스가 없거나 조건에 맞는 뉴스를 찾지 못했습니다.")
        except Exception as e:
            logger.error(f"수동 업데이트 중 오류 발생: {e}")
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {e}")

    async def fetch_and_send_news(self) -> bool:
        """새 IT 기사를 찾아 AI 요약 후 채널에 전송. 전송 성공 여부를 반환."""
        if not self.channel_id:
            logger.error("환경 변수(CHANNEL_ID) 미설정. 업데이트 중단.")
            return False
    
        news_items = await self.crawling_service.fetch_naver_news(display=10)
        if not news_items:
            logger.info("새로운 IT 뉴스를 찾지 못했습니다.")
            return False
    
        news_sent_count = 0
        for item in news_items:
            news_url = item.get("originallink", "") or item.get("link", "")
            
            # 이미 전송된 뉴스인지 확인
            if await self.news_repo.is_url_sent(news_url):
                continue
    
            news_provider = self.crawling_service.get_news_provider(news_url)
            news_title = re.sub('<[^<]+?>', '', item.get("title", ""))
            news_title = html.unescape(news_title)
            news_description = html.unescape(item.get("description", ""))
    
            logger.info(f"→ 새 기사 발견: {news_provider} - {news_title[:60]}...")
            
            # 본문 추출 시도
            content_to_summarize, extraction_method = await self.crawling_service.extract_article_content(news_url)
            
            # IT 뉴스 필터링
            filter_content = content_to_summarize if content_to_summarize else news_description
            if not self.crawling_service.is_it_news(news_title, filter_content):
                logger.info(f"  ✗ IT 뉴스가 아님. 건너뜀.")
                continue
    
            # 요약 생성
            if not content_to_summarize:
                # API description 사용
                clean_description = re.sub('<[^<]+?>', '', news_description)
                sentences = re.split(r'\.(?=\s|$)', clean_description)
                valid_sentences = [s.strip() + '.' for s in sentences if s.strip()]
                
                formatted_content = ""
                for i, sentence in enumerate(valid_sentences):
                    formatted_content += f"> {sentence}\n"
                    if i < len(valid_sentences) - 1: formatted_content += "> \n"
                summary = formatted_content.strip()
            else:
                # AI 요약 수행
                summary = await self.ai_service.summarize_with_ai(news_title, content_to_summarize)
                if not summary or summary.startswith("오류:"):
                    logger.warning("✗ 요약 실패. 건너뜀.")
                    continue
    
            # 메시지 구성
            current_year = datetime.datetime.now().year
            news_text = f"{summary}\n" if summary.startswith("## **") else f"## **{news_title}**\n{summary}\n"
            news_text += f"\n-# Published by Free Server Korea.\n"
            news_text += f"-# Copyright © {current_year} [{news_provider}]({news_url}) . All right reserved."
    
            try:
                channel = self.bot.get_channel(self.channel_id)
                if not channel:
                    logger.error(f"오류: 채널 {self.channel_id}를 찾을 수 없습니다.")
                    return False
    
                message = await channel.send(news_text)
                logger.info(f"✓ 새 메시지 전송 완료 (ID: {message.id})")
                
                if isinstance(channel, discord.TextChannel) and channel.is_news():
                    try:
                        await message.publish()
                    except:
                        pass
                
                await self.news_repo.save_sent_url(news_url, str(message.id))
                news_sent_count += 1
                
                # 하나 처리 후 종료 (기존 로직 유지)
                return True
            
            except Exception as e:
                logger.error(f"메시지 처리 오류: {e}")
    
        return news_sent_count > 0

async def setup(bot):
    await bot.add_cog(NewsCog(bot))
