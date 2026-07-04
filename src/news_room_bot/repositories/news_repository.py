"""전송·처리한 뉴스 URL 기록 저장소."""

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..cogs.models import NewsHistory

logger = logging.getLogger("news_bot")


class NewsRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.session_maker = session_maker

    async def is_url_processed(self, url: str) -> bool:
        """URL을 이미 처리(전송 또는 필터 탈락 기록)했는지 확인한다."""
        async with self.session_maker() as session:
            result = await session.execute(
                select(NewsHistory.id).where(NewsHistory.url == url).limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def mark_processed(self, url: str, message_id: str | None = None):
        """처리한 URL을 기록한다.

        message_id가 있으면 '전송 완료', None이면 '검토 후 탈락'을 의미한다.
        같은 URL이 동시에 두 번 기록되어도 UNIQUE 제약으로 안전하다.
        """
        async with self.session_maker() as session:
            session.add(NewsHistory(url=url, message_id=message_id))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.debug(f"이미 기록된 URL: {url}")

    async def get_total_count(self) -> int:
        """전체 뉴스 기록 수를 반환한다."""
        async with self.session_maker() as session:
            result = await session.execute(
                select(func.count()).select_from(NewsHistory)
            )
            return result.scalar_one()
