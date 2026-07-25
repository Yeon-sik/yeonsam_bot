import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SOURCE_FILE = Path(__file__).resolve().parent.parent / "config" / "patch_sources.json"
STEAM_NEWS_ENDPOINT = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
BBCODE_PATTERN = re.compile(r"\[(?:/?[a-z]+)(?:=[^\]]+)?\]", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")


class PatchFeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class PatchArticle:
    article_id: str
    title: str
    url: str
    summary: str
    published_at: int
    author: str


def load_patch_sources(path: Path = SOURCE_FILE) -> dict[str, dict]:
    with path.open("r", encoding="utf-8") as file:
        raw_sources = json.load(file)

    sources: dict[str, dict] = {}
    for slug, source in raw_sources.items():
        if not isinstance(source, dict):
            continue
        if source.get("provider") != "steam" or not source.get("app_id"):
            continue
        sources[str(slug)] = {
            "name": str(source.get("name") or slug),
            "provider": "steam",
            "app_id": int(source["app_id"]),
            "feed": str(source.get("feed") or "steam_community_announcements"),
        }
    return sources


def build_steam_news_url(source: dict, count: int = 10, maxlength: int = 700) -> str:
    query = urlencode(
        {
            "appid": int(source["app_id"]),
            "count": max(1, min(int(count), 20)),
            "maxlength": max(100, min(int(maxlength), 2000)),
            "feeds": source.get("feed", "steam_community_announcements"),
        }
    )
    return f"{STEAM_NEWS_ENDPOINT}?{query}"


def fetch_patch_articles(source: dict, timeout: int = 15) -> list[PatchArticle]:
    if source.get("provider") != "steam":
        raise PatchFeedError(f"지원하지 않는 패치 공급자입니다: {source.get('provider')}")

    request = Request(
        build_steam_news_url(source),
        headers={"User-Agent": "yeonsam-bot/1.0 (+https://github.com/Yeon-sik/yeonsam_bot)"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise PatchFeedError(f"Steam 업데이트 피드를 불러오지 못했습니다: {error}") from error

    return parse_steam_news(payload)


def parse_steam_news(payload: dict) -> list[PatchArticle]:
    raw_items = payload.get("appnews", {}).get("newsitems", [])
    articles: list[PatchArticle] = []
    for item in raw_items:
        article_id = str(item.get("gid") or "").strip()
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not article_id or not title or not url:
            continue
        articles.append(
            PatchArticle(
                article_id=article_id,
                title=title,
                url=url,
                summary=clean_patch_summary(item.get("contents")),
                published_at=int(item.get("date") or 0),
                author=str(item.get("author") or "").strip(),
            )
        )
    return articles


def clean_patch_summary(value, limit: int = 500) -> str:
    text = html.unescape(str(value or ""))
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = BBCODE_PATTERN.sub(" ", text)
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def find_new_articles(
    articles: list[PatchArticle],
    last_seen_id: str | None,
    limit: int = 3,
) -> list[PatchArticle]:
    if not articles or not last_seen_id:
        return []

    new_articles: list[PatchArticle] = []
    for article in articles:
        if article.article_id == last_seen_id:
            break
        new_articles.append(article)
    else:
        # 마지막 발송 지점이 조회 범위를 벗어났다면 오래된 글을 한꺼번에 보내지 않습니다.
        return []

    return list(reversed(new_articles[: max(1, limit)]))
