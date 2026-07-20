from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Article:
    section: str
    title: str
    summary: str
    publisher: str
    url: str
    published_at: str
    score: float = 0


def clean(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", "", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def publisher_from(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    labels = {
        "yna.co.kr": "연합뉴스", "chosun.com": "조선일보", "biz.chosun.com": "조선비즈",
        "joongang.co.kr": "중앙일보", "donga.com": "동아일보", "hani.co.kr": "한겨레",
        "khan.co.kr": "경향신문", "hankookilbo.com": "한국일보", "mk.co.kr": "매일경제",
        "hankyung.com": "한국경제", "sedaily.com": "서울경제", "fnnews.com": "파이낸셜뉴스",
        "mt.co.kr": "머니투데이", "edaily.co.kr": "이데일리", "asiae.co.kr": "아시아경제",
        "ajunews.com": "아주경제", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
        "dealsite.co.kr": "딜사이트", "thebell.co.kr": "더벨", "investchosun.com": "인베스트조선",
        "reuters.com": "로이터", "bloomberg.com": "블룸버그"
    }
    for domain, name in labels.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host.split(".")[0].upper() or "언론사"


def naver_search(query: str, client_id: str, client_secret: str, display: int = 100) -> list[dict]:
    params = urllib.parse.urlencode({"query": query, "display": display, "sort": "date"})
    req = urllib.request.Request(
        "https://openapi.naver.com/v1/search/news.json?" + params,
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret, "User-Agent": "KOREIT-Briefing/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response).get("items", [])


def parse_date(value: str) -> datetime | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.astimezone(KST)
    except (TypeError, ValueError):
        return None


def title_key(title: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", title.lower())[:60]


def similarity_text(article: Article | tuple[str, str]) -> str:
    if isinstance(article, Article):
        value = article.title + " " + article.summary
    else:
        value = article[0] + " " + article[1]
    value = re.sub(r"\[[^]]+\]|\([^)]*\)", " ", value.lower())
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def is_same_story(left: Article, right: Article) -> bool:
    lt, rt = title_key(left.title), title_key(right.title)
    if lt == rt:
        return True
    title_ratio = SequenceMatcher(None, lt, rt).ratio()
    if title_ratio >= 0.72:
        return True
    ls, rs = similarity_text(left), similarity_text(right)
    return SequenceMatcher(None, ls[:180], rs[:180]).ratio() >= 0.68


def deduplicate_ranked(candidates: list[Article]) -> list[Article]:
    """점수가 높은 주요 일간지·금융지 기사를 먼저 남기고 유사 기사를 제거합니다."""
    unique: list[Article] = []
    for article in sorted(candidates, key=lambda x: (x.score, x.published_at), reverse=True):
        if not any(is_same_story(article, saved) for saved in unique):
            unique.append(article)
    return unique


def score_item(section: str, title: str, summary: str, url: str, published: datetime, cfg: dict) -> float:
    text = (title + " " + summary).lower()
    domain = urllib.parse.urlparse(url).netloc.lower()
    age = max(0, (datetime.now(KST) - published).total_seconds() / 3600)
    score = max(0, 24 - age) * 0.15
    # 동일 사건이 여러 매체에 보도된 경우 주요 일간지·금융지가 확실히 우선되도록 큰 가중치를 부여합니다.
    score += 25 if any(domain.endswith(d) for d in cfg["preferred_domains"]) else 0
    score += min(12, len(title) / 10)
    if section == "부동산":
        for rank, keyword in enumerate(cfg["priority_keywords"]):
            if keyword.lower() in text:
                score += 35 - rank * 2
        if "대한토지신탁" in text or "대토신" in text:
            score += 100
    return score


def collect(cfg: dict) -> list[Article]:
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 필요합니다.")
    cutoff = datetime.now(KST) - timedelta(hours=cfg["lookback_hours"])
    chosen: list[Article] = []
    global_seen: set[str] = set()

    collection_order = list(cfg["sections"])
    for section in collection_order:
        queries = cfg["sections"][section]
        candidates: list[Article] = []
        for query in queries:
            for item in naver_search(query, client_id, client_secret):
                published = parse_date(item.get("pubDate", ""))
                if not published or published < cutoff:
                    continue
                title, summary = clean(item.get("title", "")), clean(item.get("description", ""))
                url = item.get("originallink") or item.get("link") or ""
                combined = (title + " " + summary).lower()
                if not title or not url or any(word.lower() in combined for word in cfg["exclude_keywords"]):
                    continue
                if summary and summary[-1] not in ".!?다요":
                    summary += "."
                candidates.append(Article(section, title, summary[:230], publisher_from(url), url, published.isoformat(), score_item(section, title, summary, url, published, cfg)))
        candidates = deduplicate_ranked(candidates)
        selected = []
        for candidate in candidates:
            if title_key(candidate.title) in global_seen:
                continue
            if any(is_same_story(candidate, previous) for previous in chosen):
                continue
            selected.append(candidate)
            if len(selected) >= cfg["max_articles_per_section"]:
                break
        for article in selected:
            global_seen.add(title_key(article.title))
        chosen.extend(selected)
        print(f"{section}: {len(selected)}건 선택 ({len(candidates)}건 후보)")
    return chosen


def load_articles(path: Path) -> list[Article]:
    return [Article(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def save_articles(path: Path, articles: Iterable[Article]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(a) for a in articles], ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=ROOT / "config.json", type=Path)
    parser.add_argument("--input", type=Path, help="수집 대신 기존 JSON 사용")
    parser.add_argument("--data-output", default=ROOT / "output/articles.json", type=Path)
    parser.add_argument("--pdf-output", default=ROOT / "output/pdf/대한토지신탁_뉴스클리핑.pdf", type=Path)
    parser.add_argument("--date", help="표시 날짜 YYYY-MM-DD")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    articles = load_articles(args.input) if args.input else collect(cfg)
    if not articles:
        raise RuntimeError("선정된 기사가 없습니다.")
    save_articles(args.data_output, articles)
    from src.pdf_report import build_pdf
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(KST).date()
    build_pdf(args.pdf_output, articles, report_date, cfg)
    print(args.pdf_output)


if __name__ == "__main__":
    main()
