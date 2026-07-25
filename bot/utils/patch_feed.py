"""Compatibility imports for the extracted steam-discord-patch-alerts package."""

from pathlib import Path

from steam_discord_patch_alerts.feed import (
    PatchArticle,
    PatchFeedError,
    build_steam_news_url,
    clean_patch_summary,
    fetch_patch_articles,
    find_new_articles,
    parse_steam_news,
)
from steam_discord_patch_alerts.config import load_patch_sources as _load_patch_sources


SOURCE_FILE = Path(__file__).resolve().parent.parent / "config" / "patch_sources.json"


def load_patch_sources(path: Path = SOURCE_FILE) -> dict[str, dict]:
    """Load the bot's existing source configuration through the reusable package."""
    return _load_patch_sources(path)


__all__ = [
    "PatchArticle",
    "PatchFeedError",
    "SOURCE_FILE",
    "build_steam_news_url",
    "clean_patch_summary",
    "fetch_patch_articles",
    "find_new_articles",
    "load_patch_sources",
    "parse_steam_news",
]
