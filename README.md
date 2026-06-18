# News-Room-bot

IT 및 인공지능 관련 최신 뉴스를 자동으로 크롤링하여 디스코드 채널에 요약 및 전송해주는 디스코드 봇입니다.

## 주요 기능

1. **IT 뉴스 자동 수집**: 네이버 뉴스 API를 활용하여 최신 IT/테크 관련 뉴스를 가져옵니다.
2. **본문 추출 및 폴백 시스템**:
   - Cloudflare Browser Rendering API (설정 시)
   - `newspaper3k` 파싱
   - 로컬 `Playwright` 브라우저 렌더링을 통한 스크래핑 폴백 제공
   - 위 모든 방법이 실패할 시 네이버 API에서 제공하는 요약본 사용
3. **스마트 IT 뉴스 필터링**:
   - IT 핵심 키워드 및 기업명 가중치 기반 필터링
   - 제목 분석을 통한 불필요한 금융/주식/정치 기사 필터링 (오탐지 최소화)
4. **AI 뉴스 요약**: `Gemini` API를 연동하여 기사 본문을 보기 쉽게 요약하여 디스코드에 전송합니다.

## 시작하기

### 요구 사항

- Python 3.13 이상
- 외부 라이브러리 및 브라우저 환경 (`playwright install chromium --with-deps` 필요)

### 환경 변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 아래와 같이 설정합니다. (`.env.example` 참고)

```env
# 디스코드 봇 토큰 (디스코드 개발자 포털에서 발급)
DISCORD_BOT_TOKEN="your_discord_bot_token"

# 뉴스 메시지를 보낼 디스코드 채널의 ID
DISCORD_CHANNEL_ID="your_channel_id"

# 네이버 뉴스 수집 및 검색 API 인증값
NAVER_CLIENT_ID="your_naver_client_id"
NAVER_CLIENT_SECRET="your_naver_client_secret"

# Gemini API 키 (뉴스 요약용)
GEMINI_API_KEY="your_gemini_api_key"

# Cloudflare Browser Rendering API 토큰 (선택사항, 본문 추출용)
CLOUDFLARE_API_TOKEN="your_cloudflare_api_token"
```

### 실행 방법

#### 방법 1: Docker Compose 사용 (권장)

1. 도커 컨테이너 빌드 및 백그라운드 실행:
   ```bash
   docker-compose up -d --build
   # 또는 최신 도커 버전인 경우
   docker compose up -d --build
   ```

#### 방법 2: 로컬 환경에서 직접 실행

1. 의존성 패키지 설치:
   ```bash
   pip install -e .
   ```
2. Playwright 브라우저 및 필수 의존성 설치:
   ```bash
   playwright install chromium --with-deps
   ```
3. 봇 실행:
   ```bash
   python -m news_room_bot
   ```
