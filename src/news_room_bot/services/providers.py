"""뉴스 링크 → 언론사 이름 매핑."""

import re

# 도메인 → 언론사 이름.
PROVIDERS: dict[str, str] = {
    "chosun.com": "조선일보", "donga.com": "동아일보", "joongang.co.kr": "중앙일보",
    "joins.com": "중앙일보", "hani.co.kr": "한겨레", "kyunghyang.com": "경향신문",
    "khan.co.kr": "경향신문", "seoul.co.kr": "서울신문", "hankookilbo.com": "한국일보",
    "munhwa.com": "문화일보", "segye.com": "세계일보", "kmib.co.kr": "국민일보",
    "dt.co.kr": "디지털타임스", "naeil.com": "내일신문", "yna.co.kr": "연합뉴스",
    "newsis.com": "뉴시스", "news1.kr": "뉴스1", "newsen.com": "뉴스엔",
    "moneytoday.co.kr": "머니투데이", "pressian.com": "프레시안", "ohmynews.com": "오마이뉴스",
    "vop.co.kr": "민중의소리", "dailian.co.kr": "데일리안", "newdaily.co.kr": "뉴데일리",
    "mediatoday.co.kr": "미디어오늘", "sisain.co.kr": "시사IN", "wikitree.co.kr": "위키트리",
    "insight.co.kr": "인사이트", "newsof.co.kr": "뉴스오브", "newstapa.org": "뉴스타파",
    "newsnjoy.or.kr": "뉴스앤조이", "kukinews.com": "쿠키뉴스", "sportsq.co.kr": "스포츠Q",
    "breaknews.com": "브레이크뉴스", "dailysecu.com": "데일리시큐", "goodmorningcc.com": "굿모닝충청",
    "newsworker.co.kr": "뉴스워커", "newspower.co.kr": "뉴스파워", "newscj.com": "뉴스씨제이",
    "ablenews.co.kr": "에이블뉴스", "beminor.com": "비마이너", "rapportian.com": "라포르시안",
    "straightnews.co.kr": "스트레이트뉴스", "mk.co.kr": "매일경제", "hankyung.com": "한국경제",
    "mt.co.kr": "머니투데이", "news.mt.co.kr": "머니투데이", "sedaily.com": "서울경제",
    "etoday.co.kr": "이투데이", "edaily.co.kr": "이데일리", "fnnews.com": "파이낸셜뉴스",
    "heraldcorp.com": "헤럴드경제", "ajunews.com": "아주경제", "newspim.com": "뉴스핌",
    "newsway.co.kr": "뉴스웨이", "thebell.co.kr": "더벨", "businesspost.co.kr": "비즈니스포스트",
    "chosunbiz.com": "조선비즈", "biz.chosun.com": "조선비즈", "news.einfomax.co.kr": "연합인포맥스",
    "infostock.co.kr": "인포스탁", "tfmedia.co.kr": "더팩트", "thefact.co.kr": "더팩트",
    "tfnews.co.kr": "TF뉴스", "businesskorea.co.kr": "비즈니스코리아", "greened.kr": "환경일보",
    "ebn.co.kr": "EBN", "fortunekorea.co.kr": "포춘코리아", "motorgraph.com": "모터그래프",
    "autotimes.co.kr": "오토타임즈", "autoview.co.kr": "오토뷰", "autotribune.co.kr": "오토트리뷴",
    "dailycar.co.kr": "데일리카", "zdnet.co.kr": "ZDNet코리아", "etnews.com": "전자신문",
    "ddaily.co.kr": "디지털데일리", "bloter.net": "블로터", "itdonga.com": "IT동아",
    "betanews.net": "베타뉴스", "aitimes.com": "AI타임스", "aitimes.kr": "AI타임스",
    "boannews.com": "보안뉴스", "itworld.co.kr": "ITWorld", "ciokorea.com": "CIO Korea",
    "techm.kr": "테크M", "epnc.co.kr": "전자부품", "thelec.kr": "더일렉",
    "thelec.net": "더일렉", "digitaltoday.co.kr": "디지털투데이", "aving.net": "아빙뉴스",
    "datanet.co.kr": "데이터넷", "comworld.co.kr": "컴퓨터월드", "webtoday.co.kr": "웹투데이",
    "itbiznews.com": "IT비즈뉴스", "iconews.co.kr": "아이콘뉴스", "inven.co.kr": "인벤",
    "thisisgame.com": "디스이즈게임", "ruliweb.com": "루리웹", "gameshot.net": "게임샷",
    "gamefocus.co.kr": "게임포커스", "gamemeca.com": "게임메카", "gametoc.co.kr": "게임톡",
    "dailyesports.com": "데일리e스포츠", "fomos.co.kr": "포모스", "gamechosun.co.kr": "게임조선",
    "khgames.co.kr": "경향게임스", "kbs.co.kr": "KBS", "news.kbs.co.kr": "KBS뉴스",
    "mbc.co.kr": "MBC", "imnews.imbc.com": "MBC뉴스", "sbs.co.kr": "SBS",
    "news.sbs.co.kr": "SBS뉴스", "jtbc.co.kr": "JTBC", "news.jtbc.co.kr": "JTBC뉴스",
    "ytn.co.kr": "YTN", "mbn.co.kr": "MBN", "tvchosun.com": "TV조선",
    "ichannela.com": "채널A", "channela.com": "채널A", "news.chosun.com": "채널A",
    "ebs.co.kr": "EBS", "tbs.seoul.kr": "TBS", "obs.co.kr": "OBS",
    "wowtv.co.kr": "한국경제TV", "arirang.co.kr": "아리랑TV", "ntv.co.kr": "NTV",
    "gbs.or.kr": "경기방송", "gtb.co.kr": "경기티브이", "pbc.co.kr": "평화방송",
    "cpbc.co.kr": "평화방송", "bbs.or.kr": "불교방송", "febc.net": "극동방송",
    "gugakfm.co.kr": "국악방송", "tbsradio.co.kr": "교통방송", "naver.com": "네이버",
    "news.naver.com": "네이버뉴스", "m.news.naver.com": "네이버뉴스", "daum.net": "다음",
    "news.v.daum.net": "다음뉴스", "news.daum.net": "다음뉴스", "media.daum.net": "다음뉴스",
    "nate.com": "네이트", "news.nate.com": "네이트뉴스", "zum.com": "줌",
    "news.zum.com": "줌뉴스", "news.google.com": "구글뉴스", "google.com/news": "구글뉴스",
    "msn.com": "MSN뉴스", "news.yahoo.co.kr": "야후뉴스", "m-i.kr": "매일일보",
    "inthenews.co.kr": "인더뉴스",
}

_DOMAIN_RE = re.compile(r"https?://(?:www\.)?([^/]+)")

# 긴(구체적인) 도메인이 먼저 매칭되도록 정렬 — news.naver.com이 naver.com보다,
# biz.chosun.com이 chosun.com보다 우선한다.
_PROVIDERS_BY_SPECIFICITY: tuple[tuple[str, str], ...] = tuple(
    sorted(PROVIDERS.items(), key=lambda kv: len(kv[0]), reverse=True)
)


def get_news_provider(news_link: str) -> str:
    """뉴스 링크에서 언론사 이름을 추출한다. 매핑에 없으면 도메인 첫 조각을 대문자로."""
    for domain, name in _PROVIDERS_BY_SPECIFICITY:
        if domain in news_link:
            return name

    domain_match = _DOMAIN_RE.search(news_link)
    if domain_match:
        return domain_match.group(1).split(".")[0].upper()

    return "UNKNOWN"
