"""Gemini 기반 뉴스 요약 서비스.

요약과 동시에 IT 뉴스 여부를 2차 검증한다. 키워드 필터(news_filter)를
통과했더라도 AI가 IT 뉴스가 아니라고 판단하면 NOT_IT 판정을 돌려준다.
"""

import asyncio
import enum
import logging

import google.generativeai as genai

from ..config import Settings

logger = logging.getLogger("news_bot")

MAX_CONTENT_LENGTH = 10_000
REQUEST_TIMEOUT = 60.0
NOT_IT_SENTINEL = "NOT_IT"

# 모델이 규칙을 무시하고 붙이는 군더더기 서두/결말 감지용
UNWANTED_PHRASES: tuple[str, ...] = (
    "물론입니다", "IT 전문 뉴스 에디터", "기사 내용을",
    "핵심만 담아", "전문적으로 요약", "---",
    "다음은", "요약입니다", "요약본입니다",
)

PROMPT_TEMPLATE = """당신은 IT 전문 뉴스 에디터입니다. 아래 뉴스를 검토하고 요약해 주세요.

**판정 규칙:**
- 기사가 IT/기술 뉴스가 아니라면(정치, 금융/증권, 부동산, 연예, 스포츠 등) 다른 말 없이 정확히 `NOT_IT` 라고만 출력합니다.

**요약 규칙 (IT 뉴스인 경우):**
- 뉴스의 핵심만 2~3개 문단으로 요약합니다.
- 각 문단은 '>' 기호로 시작합니다.
- 문단과 문단 사이는 반드시 빈 줄 하나('> ')를 넣습니다.
- 다른 설명, 분석, 서론, 결론, 메타 정보 등은 절대 포함하지 않습니다.

**출력 형식:**
## **뉴스제목**
> 첫 번째 요약 문단
>
> 두 번째 요약 문단
>
> 세 번째 요약 문단(필요 시)

---
제목: {title}
내용: {content}
---
"""


class SummaryVerdict(enum.Enum):
    OK = "ok"            # 요약 성공
    NOT_IT = "not_it"    # AI가 IT 뉴스가 아니라고 판정 (재시도 불필요)
    ERROR = "error"      # 일시적 오류 (다음 주기에 재시도 가능)


class AIService:
    def __init__(self, settings: Settings):
        self._api_key = settings.gemini_api_key
        self.model = self._initialize_ai_model()

    @property
    def available(self) -> bool:
        return self.model is not None

    def _initialize_ai_model(self):
        """환경 변수 GEMINI_API_KEY로 AI 모델 초기화."""
        if not self._api_key:
            logger.warning("경고: GEMINI_API_KEY가 설정되지 않았습니다. AI 요약 기능이 작동하지 않습니다.")
            return None
        try:
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            logger.info("✓ Gemini 2.5 Flash 모델 초기화 완료.")
            return model
        except Exception as e:
            logger.error(f"✗ Gemini 모델 초기화 오류: {e}")
            return None

    async def summarize(self, title: str, content: str) -> tuple[SummaryVerdict, str | None]:
        """뉴스를 요약한다. (판정, 요약문) 튜플을 반환한다."""
        if not self.model or not title or not content:
            return SummaryVerdict.ERROR, None

        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH]

        prompt = PROMPT_TEMPLATE.format(title=title, content=content)

        try:
            response = await asyncio.wait_for(
                self.model.generate_content_async(prompt),
                timeout=REQUEST_TIMEOUT,
            )
            summary = response.text.strip()
        except asyncio.TimeoutError:
            logger.error("AI 요약 요청 시간 초과 (TimeoutError)")
            return SummaryVerdict.ERROR, None
        except Exception as e:
            logger.error(f"AI 요약 처리 중 오류: {e}")
            return SummaryVerdict.ERROR, None

        if summary.startswith(NOT_IT_SENTINEL):
            return SummaryVerdict.NOT_IT, None

        cleaned = self._strip_unwanted_lines(summary)
        return SummaryVerdict.OK, cleaned or summary

    @staticmethod
    def _strip_unwanted_lines(summary: str) -> str:
        """모델이 붙인 군더더기 서두/결말 줄을 제거한다."""
        cleaned_lines = [
            line for line in summary.split("\n")
            if not any(phrase in line.strip() for phrase in UNWANTED_PHRASES)
        ]
        return "\n".join(cleaned_lines).strip()
