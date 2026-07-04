"""데이터베이스 모델 및 초기화.

스키마는 기존과 동일하다(news_history: id, url, message_id, sent_at).
기존 DB 파일을 그대로 사용할 수 있다.
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NewsHistory(Base):
    __tablename__ = "news_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False, index=True)
    # 실제로 전송된 경우에만 채워진다. None이면 '처리했지만 게시하지 않음'(필터 탈락 등).
    message_id = Column(String, nullable=True)
    sent_at = Column(DateTime, default=_utcnow)


async def init_db(db_path: str = "news_history.db") -> async_sessionmaker[AsyncSession]:
    """데이터베이스를 초기화하고 세션 메이커를 반환한다."""
    db_file = Path(db_path)
    if db_file.parent != Path("."):
        db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
