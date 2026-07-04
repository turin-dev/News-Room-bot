"""뉴스 수집 → 필터 → 요약 → 전송 파이프라인을 조율하는 Cog."""

import datetime
import html
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..config import Settings
from ..repositories.news_repository import NewsRepository
from ..services import news_filter, providers
from ..services.ai_service import AIService, SummaryVerdict
from ..services.crawling_service import CrawlingService
from .models import init_db

logger = logging.getLogger("news_bot")

TAG_RE = re.compile(r"<[^<]+?>")


class NewsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: Settings):
        self.bot = bot
        self.settings = settings

        self.crawling_service = CrawlingService(settings)
        self.ai_service = AIService(settings)
        self.news_repo: NewsRepository | None = None

    # ── 수명 주기 ──────────────────────────────────────────────
    # DB·서비스 초기화가 끝난 뒤에만 루프를 시작하므로, 기존 구현의
    # '루프가 repo 초기화보다 먼저 도는' 경쟁 상태가 없다.

    async def cog_load(self):
        session_maker = await init_db(self.settings.db_path)
        self.news_repo = NewsRepository(session_maker)
        count = await self.news_repo.get_total_count()
        logger.info(f"✓ 데이터베이스 초기화 완료. 경로: {self.settings.db_path} (총 {count}개 레코드)")

        await self.crawling_service.start()

        if self.settings.channel_id:
            self.send_news_loop.change_interval(minutes=self.settings.loop_minutes)
            self.send_news_loop.start()
            logger.info(f"✓ 뉴스 자동 전송 루프 시작. (주기: {self.settings.loop_minutes}분)")
        else:
            logger.warning("경고: DISCORD_CHANNEL_ID가 없어 자동 전송 루프를 시작하지 않습니다.")

    async def cog_unload(self):
        self.send_news_loop.cancel()
        await self.crawling_service.close()
        logger.info("뉴스 자동 전송 루프 중지.")

    # ── 자동/수동 트리거 ───────────────────────────────────────

    @tasks.loop(minutes=30.0)
    async def send_news_loop(self):
        """주기적으로 최신 뉴스를 확인하고 채널에 전송한다."""
        logger.info("\n--- 뉴스 자동 업데이트 시작 ---")
        try:
            await self.run_news_cycle()
        except Exception as e:
            logger.error(f"자동 업데이트 루프 중 치명적 오류 발생: {e}", exc_info=True)

    @send_news_loop.before_loop
    async def _wait_until_ready(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="뉴스검색", description="최신 IT 뉴스를 즉시 검색하여 전송합니다.")
    async def manual_news(self, interaction: discord.Interaction):
        """즉시 뉴스를 크롤링하여 전송하는 슬래시 명령어."""
        await interaction.response.defer(thinking=True)
        logger.info(f"-> 전송 요청자: {interaction.user} (명령어: /뉴스검색)")

        try:
            sent = await self.run_news_cycle()
            if sent:
                await interaction.followup.send("✅ 최신 뉴스를 성공적으로 찾아서 전송했습니다!")
            else:
                await interaction.followup.send("ℹ️ 새로운 뉴스가 없거나 조건에 맞는 뉴스를 찾지 못했습니다.")
        except Exception as e:
            logger.error(f"수동 업데이트 중 오류 발생: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {e}")

    # ── 파이프라인 ─────────────────────────────────────────────

    async def run_news_cycle(self) -> int:
        """새 IT 기사를 찾아 요약 후 전송한다. 전송한 기사 수를 반환한다.

        단계: 네이버 API 조회 → 중복 제거 → 본문 추출 → 키워드 필터
              → AI 요약(+2차 IT 판정) → 전송 → 처리 기록.
        필터에서 확정 탈락한 기사도 DB에 기록해 다음 주기에 다시
        추출·요약하지 않는다(기존 구현은 매 주기 재처리했다).
        """
        if not self.settings.channel_id:
            logger.error("환경 변수(DISCORD_CHANNEL_ID) 미설정. 업데이트 중단.")
            return 0
        if self.news_repo is None:
            logger.error("데이터베이스가 초기화되지 않았습니다. 업데이트 중단.")
            return 0

        channel = self.bot.get_channel(self.settings.channel_id)
        if channel is None:
            logger.error(f"오류: 채널 {self.settings.channel_id}를 찾을 수 없습니다.")
            return 0

        news_items = await self.crawling_service.fetch_naver_news()
        if not news_items:
            logger.info("새로운 IT 뉴스를 찾지 못했습니다.")
            return 0

        posted = 0
        for item in news_items:
            if posted >= self.settings.max_posts_per_cycle:
                break

            news_url = item.get("originallink", "") or item.get("link", "")
            if not news_url or await self.news_repo.is_url_processed(news_url):
                continue

            posted += await self._process_item(channel, news_url, item)

        return posted

    async def _process_item(self, channel, news_url: str, item: dict) -> int:
        """기사 하나를 처리한다. 전송했으면 1, 아니면 0을 반환한다."""
        news_provider = providers.get_news_provider(news_url)
        news_title = html.unescape(TAG_RE.sub("", item.get("title", "")))
        news_description = html.unescape(item.get("description", ""))

        logger.info(f"→ 새 기사 발견: {news_provider} - {news_title[:60]}...")

        content, extraction_method = await self.crawling_service.extract_article_content(news_url)

        # 1차: 키워드 필터 (확정 탈락 → 기록해서 재처리 방지)
        filter_content = content if content else news_description
        if not news_filter.is_it_news(news_title, filter_content):
            logger.info("  ✗ IT 뉴스가 아님(키워드 필터). 건너뜀.")
            await self.news_repo.mark_processed(news_url)
            return 0

        # 요약 생성 (본문 추출 성공 시 AI, 실패 시 API description 폴백)
        if content and self.ai_service.available:
            verdict, summary = await self.ai_service.summarize(news_title, content)
            if verdict is SummaryVerdict.NOT_IT:
                logger.info("  ✗ IT 뉴스가 아님(AI 판정). 건너뜀.")
                await self.news_repo.mark_processed(news_url)
                return 0
            if verdict is SummaryVerdict.ERROR or not summary:
                # 일시적 오류일 수 있으므로 기록하지 않고 다음 주기에 재시도
                logger.warning("  ✗ 요약 실패. 건너뜀.")
                return 0
        else:
            summary = self._format_description(news_description)
            if not summary:
                logger.warning("  ✗ 요약할 내용이 없음. 건너뜀.")
                await self.news_repo.mark_processed(news_url)
                return 0

        news_text = self._build_message(news_title, summary, news_provider, news_url)

        try:
            message = await channel.send(news_text)
        except Exception as e:
            logger.error(f"메시지 처리 오류: {e}")
            return 0

        logger.info(f"✓ 새 메시지 전송 완료 (ID: {message.id})")

        if isinstance(channel, discord.TextChannel) and channel.is_news():
            try:
                await message.publish()
            except Exception:
                pass

        await self.news_repo.mark_processed(news_url, str(message.id))
        return 1

    @staticmethod
    def _format_description(news_description: str) -> str:
        """API description을 인용 블록 형태로 정리한다 (본문 추출 실패 시 폴백)."""
        clean_description = TAG_RE.sub("", news_description).strip()
        if not clean_description:
            return ""

        sentences = re.split(r"\.(?=\s|$)", clean_description)
        valid_sentences = [s.strip() + "." for s in sentences if s.strip()]

        lines = []
        for i, sentence in enumerate(valid_sentences):
            lines.append(f"> {sentence}")
            if i < len(valid_sentences) - 1:
                lines.append("> ")
        return "\n".join(lines).strip()

    @staticmethod
    def _build_message(news_title: str, summary: str, news_provider: str, news_url: str) -> str:
        """디스코드 메시지 본문을 조립한다 (기존 출력 형식 유지)."""
        current_year = datetime.datetime.now().year
        news_text = f"{summary}\n" if summary.startswith("## **") else f"## **{news_title}**\n{summary}\n"
        news_text += "\n-# Published by Free Server Korea.\n"
        news_text += f"-# Copyright © {current_year} [{news_provider}]({news_url}) . All right reserved."
        return news_text


async def setup(bot):
    settings: Settings = getattr(bot, "settings", None) or Settings.from_env()
    await bot.add_cog(NewsCog(bot, settings))
