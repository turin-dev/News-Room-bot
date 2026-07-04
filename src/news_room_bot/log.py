"""로깅 설정."""

import logging
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "news_bot"


def setup_logger() -> logging.Logger:
    """파일(회전)과 콘솔에 동시 출력하는 로거를 반환한다. 중복 호출에 안전."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        "news_bot.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
