"""IT 뉴스 여부를 판단하는 키워드 기반 1차 필터.

빠르고 결정적인(deterministic) 사전 필터다. 여기서 통과한 기사는
AI 요약 단계에서 한 번 더 검증된다(ai_service 참고).
"""

# 금융/증권/정치 배제 키워드 — 제목에 하나라도 있으면 즉시 탈락
EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "증권", "주가", "시세", "상장", "ipo", "코스피", "kospi", "코스닥", "kosdaq", "증시",
    "펀드", "채권", "금리", "환율", "재무", "cfo", "회계", "과징금", "자산운용", "사모펀드",
    "매수", "매도", "수익률", "배당", "완판", "공시강화", "의무공개매수", "합병가액", "종합투자계좌",
    "원자재", "일반주주", "경영권", "상장폐지", "월가", "블랙록", "투자", "investment", "투자자",
    "금융위", "금융감독원", "금감원", "공정위", "공정거래위원회", "m&a", "인수합병",
    "대통령", "정치", "선거", "국회", "의원", "부동산", "아파트", "집값",
)

# 순수 IT 핵심 키워드 — 개당 3점
CORE_IT_KEYWORDS: tuple[str, ...] = (
    # 인공지능 / AI / LLM
    "인공지능", "ai", "artificial intelligence", "머신러닝", "machine learning",
    "딥러닝", "deep learning", "생성형 ai", "generative ai", "llm", "거대언어모델",
    "gpt", "챗gpt", "chatgpt", "claude", "클로드", "gemini", "제미나이", "llama", "라마",
    "ai 에이전트", "ai agent", "온디바이스 ai", "on-device ai", "rag", "프롬프트 엔지니어링",
    # 소프트웨어 / 개발
    "소프트웨어", "software", "코딩", "coding", "프로그래밍", "programming",
    "소스코드", "source code", "api", "sdk", "개발자", "developer", "앱개발",
    "알고리즘", "algorithm", "깃허브", "github",
    # 사이버 보안 / 해킹
    "사이버보안", "cybersecurity", "해킹", "해커", "hacker", "랜섬웨어", "ransomware",
    "악성코드", "malware", "피싱", "phishing", "디도스", "ddos", "제로 트러스트", "zero trust",
    "방화벽", "firewall", "유출", "데이터유출", "정보유출", "기술유출",
    # 클라우드 / 인프라 / 네트워크
    "클라우드", "cloud", "saas", "paas", "iaas", "데이터센터", "data center",
    "서버", "server", "5g", "6g", "네트워크", "network", "iot", "사물인터넷",
    # 반도체 / 하드웨어
    "반도체", "semiconductor", "파운드리", "foundry", "팹리스", "fabless",
    "hbm", "고대역폭메모리", "cxl", "gpu", "npu", "tpu", "cpu", "칩", "chip",
    # 미래 기술 / 모빌리티
    "블록체인", "blockchain", "web3", "메타버스", "metaverse", "vr", "ar", "xr",
    "가상현실", "증강현실", "양자컴퓨팅", "quantum computing", "자율주행", "autonomous driving",
    "로봇공학", "robotics", "로봇", "robot",
)

# 글로벌 빅테크 및 플랫폼 브랜드 — 개당 1점
TECH_BRANDS: tuple[str, ...] = (
    "구글", "google", "애플", "apple", "마이크로소프트", "microsoft", "ms",
    "아마존", "amazon", "aws", "메타", "meta", "엔비디아", "nvidia", "인텔", "intel",
    "amd", "tsmc", "퀄컴", "qualcomm", "오픈ai", "openai", "앤스로픽", "anthropic",
    "네이버", "naver", "카카오", "kakao", "플랫폼", "platform", "디지털전환", "dx", "테크",
)

# 본문에 금융 흔적이 남아있을 때 허들을 올리는 트리거
FINANCE_TRACES: tuple[str, ...] = ("투자", "금융", "m&a")

TITLE_BONUS = 2          # 제목에 핵심 키워드 직접 노출 시 보너스
PASS_SCORE = 5           # 기본 통과 점수
STRICT_PASS_SCORE = 10   # 금융 흔적이 있을 때 통과 점수


def score_it_relevance(title: str, content: str) -> int:
    """제목·본문의 IT 관련도 점수를 계산한다."""
    title_lower = title.lower()
    combined = f"{title_lower} {content.strip().lower()}"

    score = 0
    for keyword in CORE_IT_KEYWORDS:
        if keyword in combined:
            score += 3
    for keyword in TECH_BRANDS:
        if keyword in combined:
            score += 1
    if any(keyword in title_lower for keyword in CORE_IT_KEYWORDS):
        score += TITLE_BONUS
    return score


def is_it_news(title: str, content: str) -> bool:
    """제목과 내용을 분석하여 순수 IT 관련 뉴스인지 판단한다."""
    title_lower = title.lower()
    content_lower = content.strip().lower()

    # [검증 1] 제목에 배제 키워드가 하나라도 있으면 즉시 탈락
    if any(keyword in title_lower for keyword in EXCLUDE_KEYWORDS):
        return False

    # [검증 2] 본문에 금융/투자 단어가 2개 이상 과도하게 언급되면 탈락
    exclude_count = sum(1 for keyword in EXCLUDE_KEYWORDS if keyword in content_lower)
    if exclude_count >= 2:
        return False

    score = score_it_relevance(title, content)

    # 본문에 금융/투자 흔적이 조금이라도 남아있다면 허들 상향
    combined = f"{title_lower} {content_lower}"
    if any(keyword in combined for keyword in FINANCE_TRACES):
        return score >= STRICT_PASS_SCORE

    return score >= PASS_SCORE
