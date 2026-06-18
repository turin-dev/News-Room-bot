from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class NewsHistory(Base):
    __tablename__ = 'news_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False, index=True)
    message_id = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

# 데이터베이스 엔진 및 세션 설정
async def init_db(db_path: str = "news_history.db"):
    """데이터베이스 초기화"""
    db_file = Path(db_path)
    if db_file.parent != Path('.'):
        db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
