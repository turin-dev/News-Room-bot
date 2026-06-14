FROM python:3.13.0-slim

WORKDIR /app

ENV NEWS_DB_PATH=/data/news_history.db

COPY . ./

RUN pip install -e .
RUN python -m playwright install --with-deps chromium
RUN mkdir -p /data

VOLUME ["/data"]

CMD ["python", "-m", "news_room_bot"]
