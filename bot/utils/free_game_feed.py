"""GamerPower feed parsing for limited-time paid games across platforms."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


GAMERPOWER_API_URL = "https://www.gamerpower.com/api/giveaways"
_GAMERPOWER_HOSTS = frozenset({"gamerpower.com", "www.gamerpower.com"})
_EXCLUDED_OFFER_TERMS = (
    "free trial",
    "free weekend",
    "play for free",
)
_WORTH_NUMBER_PATTERN = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)")


class FreeGameFeedError(RuntimeError):
    """Raised when the free-game feed cannot be fetched or parsed."""


@dataclass(frozen=True)
class FreeGameOffer:
    offer_id: str
    title: str
    claim_url: str
    ends_at: datetime | None
    worth: str
    platforms: tuple[str, ...] = ()


def build_gamerpower_url() -> str:
    query = urlencode(
        {
            "type": "game",
            "sort-by": "date",
        }
    )
    return f"{GAMERPOWER_API_URL}?{query}"


def parse_gamerpower_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or text.casefold() in {"n/a", "none", "null"}:
        return None

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_gamerpower_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in _GAMERPOWER_HOSTS


def _parse_platforms(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        raw_platforms = value
    else:
        raw_platforms = str(value or "").split(",")

    platforms: list[str] = []
    seen: set[str] = set()
    for item in raw_platforms:
        platform = " ".join(str(item).strip().split())
        normalized = platform.casefold()
        if platform and normalized not in seen:
            seen.add(normalized)
            platforms.append(platform)
    return tuple(platforms)


def _has_positive_worth(value: Any) -> bool:
    match = _WORTH_NUMBER_PATTERN.search(str(value or ""))
    if match is None:
        return False
    try:
        return float(match.group(1).replace(",", ".")) > 0
    except ValueError:
        return False


def _looks_like_temporary_access(item: dict) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "description", "instructions")
    ).casefold()
    return any(term in text for term in _EXCLUDED_OFFER_TERMS)


def parse_gamerpower_giveaways(
    payload: Any,
    *,
    now: datetime | None = None,
) -> list[FreeGameOffer]:
    """Normalize active, paid full-game giveaways and discard expired offers."""
    if isinstance(payload, dict) and payload.get("status") in (0, "0"):
        return []
    if not isinstance(payload, list):
        raise FreeGameFeedError("Unexpected GamerPower response shape")

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    offers_by_id: dict[str, FreeGameOffer] = {}

    for item in payload:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").casefold() != "active":
            continue
        if str(item.get("type") or "").casefold() != "game":
            continue
        platforms = _parse_platforms(item.get("platforms"))
        if not platforms:
            continue
        if not _has_positive_worth(item.get("worth")):
            continue
        if _looks_like_temporary_access(item):
            continue

        offer_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        claim_url = next(
            (
                str(item.get(key) or "").strip()
                for key in (
                    "open_giveaway_url",
                    "gamerpower_url",
                    "open_giveaway",
                )
                if _is_gamerpower_url(item.get(key))
            ),
            "",
        )
        if not offer_id or not title or not claim_url:
            continue

        ends_at = parse_gamerpower_datetime(item.get("end_date"))
        if ends_at is not None and ends_at <= current_time:
            continue

        offers_by_id[offer_id] = FreeGameOffer(
            offer_id=offer_id,
            title=title,
            claim_url=claim_url,
            ends_at=ends_at,
            worth=str(item.get("worth") or "").strip(),
            platforms=platforms,
        )

    return sorted(
        offers_by_id.values(),
        key=lambda offer: (
            offer.ends_at.timestamp() if offer.ends_at else float("inf"),
            offer.title.casefold(),
            offer.offer_id,
        ),
    )


def build_free_game_digest(offers: list[FreeGameOffer]) -> str:
    canonical = [
        {
            "id": offer.offer_id,
            "title": offer.title,
            "url": offer.claim_url,
            "ends_at": offer.ends_at.isoformat() if offer.ends_at else None,
            "worth": offer.worth,
            "platforms": offer.platforms,
        }
        for offer in sorted(offers, key=lambda item: item.offer_id)
    ]
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def fetch_free_game_offers(timeout: int = 15) -> list[FreeGameOffer]:
    request = Request(
        build_gamerpower_url(),
        headers={
            "Accept": "application/json",
            "User-Agent": "YeonsamBot/1.0 (Discord free-game alerts)",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (
        HTTPError,
        URLError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise FreeGameFeedError(f"Unable to fetch GamerPower feed: {error}") from error

    return parse_gamerpower_giveaways(payload)
