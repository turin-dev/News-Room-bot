"""봇 엔트리포인트."""

import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from .config import Settings
from .log import setup_logger


class NewsRoomBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings

    async def setup_hook(self):
        """봇이 시작되기 직전에 실행되는 훅 (비동기)."""
        logging.getLogger("news_bot").info("--- 봇 셋업 시작 ---")
        await self.load_extension("news_room_bot.cogs.news_room")

        try:
            await self.tree.sync()
            logging.getLogger("news_bot").info("✓ 슬래시 커맨드 동기화 완료!")
        except Exception as e:
            logging.getLogger("news_bot").error(f"✗ 슬래시 커맨드 동기화 실패: {e}")

    async def on_ready(self):
        logging.getLogger("news_bot").info(
            f"\n{self.user.name} 봇이 성공적으로 로그인했습니다! (ID: {self.user.id})"
        )


def main():
    load_dotenv(".env")
    setup_logger()

    settings = Settings.from_env()
    if not settings.discord_token:
        raise ValueError("오류: .env 파일에서 DISCORD_BOT_TOKEN을 찾을 수 없습니다.")

    bot = NewsRoomBot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
