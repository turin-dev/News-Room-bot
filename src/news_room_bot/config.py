"""환경 변수 기반 설정.

모든 환경 변수 읽기는 이 모듈에서만 수행한다. 나머지 코드는
Settings 객체를 주입받아 사용하므로 테스트와 재사용이 쉽다.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Discord
    discord_token: str | None
    channel_id: int | None

    # 데이터베이스
    db_path: str

    # 네이버 뉴스 API
    naver_client_id: str | None
    naver_client_secret: str | None

    # AI 요약 (Gemini)
    gemini_api_key: str | None

    # Cloudflare Browser Rendering (선택)
    cloudflare_api_token: str | None

    # 크롤링 동작
    news_query: str
    fetch_display: int
    loop_minutes: float
    max_posts_per_cycle: int

    @classmethod
    def from_env(cls) -> "Settings":
        """환경 변수에서 설정을 읽는다. 잘못된 숫자 값은 기본값으로 대체한다."""
        return cls(
            discord_token=os.getenv("DISCORD_BOT_TOKEN"),
            channel_id=_int_or_none(os.getenv("DISCORD_CHANNEL_ID")),
            db_path=os.getenv("NEWS_DB_PATH", "/data/news_history.db"),
            naver_client_id=os.getenv("NAVER_CLIENT_ID"),
            naver_client_secret=os.getenv("NAVER_CLIENT_SECRET"),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN"),
            news_query=os.getenv(
                "NEWS_QUERY", "IT 기술 인공지능 소프트웨어 -경제 -주식 -투자"
            ),
            fetch_display=_int_or_default(os.getenv("NEWS_FETCH_DISPLAY"), 10),
            loop_minutes=_float_or_default(os.getenv("NEWS_LOOP_MINUTES"), 30.0),
            max_posts_per_cycle=_int_or_default(os.getenv("NEWS_MAX_POSTS_PER_CYCLE"), 1),
        )


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _int_or_default(value: str | None, default: int) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else default


def _float_or_default(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default
