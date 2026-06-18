FROM python:3.13.0-slim

WORKDIR /app

COPY . ./

RUN pip install -e .
RUN playwright install chromium --with-deps

CMD ["python", "-m", "news_room_bot"]
