"""Steam's public Most Played chart with bounded caching and validation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


STEAM_CHART_URL = (
    "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
)
STEAM_MOST_PLAYED_URL = "https://store.steampowered.com/charts/mostplayed"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_STORE_APP_URL = "https://store.steampowered.com/app/{app_id}"
DEFAULT_RESULT_LIMIT = 10
MAX_RESULT_LIMIT = 10
DEFAULT_CACHE_TTL_SECONDS = 15 * 60
DEFAULT_METADATA_TTL_SECONDS = 24 * 60 * 60
DEFAULT_ERROR_RETRY_SECONDS = 60
DEFAULT_REQUEST_TIMEOUT_SECONDS = 12
MAX_METADATA_CONCURRENCY = 4
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = "YeonsamBot/1.0 (+https://github.com/Yeon-sik/yeonsam_bot)"

JsonFetcher = Callable[[str, float], object]
Clock = Callable[[], float]


class SteamPopularError(RuntimeError):
    """Raised when a usable Steam chart cannot be retrieved."""


@dataclass(frozen=True)
class SteamChartEntry:
    rank: int
    app_id: int
    last_week_rank: int | None
    peak_players: int


@dataclass(frozen=True)
class SteamAppMetadata:
    name: str
    header_image: str | None


@dataclass(frozen=True)
class SteamPopularGame:
    rank: int
    app_id: int
    name: str
    last_week_rank: int | None
    peak_players: int
    header_image: str | None

    @property
    def store_url(self) -> str:
        return STEAM_STORE_APP_URL.format(app_id=self.app_id)


@dataclass(frozen=True)
class SteamPopularSnapshot:
    rollup_timestamp: int
    fetched_timestamp: int
    games: tuple[SteamPopularGame, ...]
    stale_cache: bool = False

    def limited(
        self,
        limit: int,
        *,
        stale_cache: bool | None = None,
    ) -> "SteamPopularSnapshot":
        return replace(
            self,
            games=self.games[:limit],
            stale_cache=self.stale_cache if stale_cache is None else stale_cache,
        )


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def fetch_json(url: str, timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS) -> object:
    """Fetch one bounded JSON response without adding another runtime dependency."""
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise SteamPopularError("Steam 응답을 불러오지 못했습니다.") from error

    if len(raw) > MAX_RESPONSE_BYTES:
        raise SteamPopularError("Steam 응답 크기가 허용 범위를 넘었습니다.")

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SteamPopularError("Steam 응답을 해석하지 못했습니다.") from error


def parse_chart_payload(
    payload: object,
    limit: int = MAX_RESULT_LIMIT,
) -> tuple[int, tuple[SteamChartEntry, ...]]:
    """Validate Steam's chart response and return ordered, unique entries."""
    if not 1 <= limit <= MAX_RESULT_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RESULT_LIMIT}")
    if not isinstance(payload, dict):
        raise SteamPopularError("Steam 차트 응답 형식이 올바르지 않습니다.")

    response = payload.get("response")
    if not isinstance(response, dict):
        raise SteamPopularError("Steam 차트 응답에 response가 없습니다.")

    rollup_timestamp = _positive_int(response.get("rollup_date"))
    ranks = response.get("ranks")
    if rollup_timestamp is None or not isinstance(ranks, list):
        raise SteamPopularError("Steam 차트 집계 정보를 확인할 수 없습니다.")

    entries: list[SteamChartEntry] = []
    seen_ranks: set[int] = set()
    seen_app_ids: set[int] = set()
    for item in ranks:
        if not isinstance(item, dict):
            continue

        rank = _positive_int(item.get("rank"))
        app_id = _positive_int(item.get("appid"))
        peak_players = _positive_int(item.get("peak_in_game"))
        if rank is None or app_id is None or peak_players is None:
            continue
        if rank in seen_ranks or app_id in seen_app_ids:
            continue

        last_week_rank = _positive_int(item.get("last_week_rank"))
        entries.append(
            SteamChartEntry(
                rank=rank,
                app_id=app_id,
                last_week_rank=last_week_rank,
                peak_players=peak_players,
            )
        )
        seen_ranks.add(rank)
        seen_app_ids.add(app_id)

    entries.sort(key=lambda item: item.rank)
    if not entries:
        raise SteamPopularError("Steam 차트에 표시할 게임이 없습니다.")
    return rollup_timestamp, tuple(entries[:limit])


def build_app_details_url(app_id: int) -> str:
    if app_id <= 0:
        raise ValueError("app_id must be positive")
    return f"{STEAM_APP_DETAILS_URL}?{urlencode({'appids': app_id, 'l': 'koreana', 'cc': 'KR'})}"


def parse_app_metadata(payload: object, app_id: int) -> SteamAppMetadata | None:
    if not isinstance(payload, dict):
        return None
    result = payload.get(str(app_id))
    if not isinstance(result, dict) or result.get("success") is not True:
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    header_image = data.get("header_image")
    if not isinstance(header_image, str) or not _is_https_url(header_image):
        header_image = None
    return SteamAppMetadata(name=name.strip(), header_image=header_image)


def _is_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


class SteamPopularService:
    """Single-flight async service with fresh and last-successful snapshot caches."""

    def __init__(
        self,
        *,
        json_fetcher: JsonFetcher = fetch_json,
        clock: Clock = time.monotonic,
        wall_clock: Clock = time.time,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        metadata_ttl_seconds: float = DEFAULT_METADATA_TTL_SECONDS,
        error_retry_seconds: float = DEFAULT_ERROR_RETRY_SECONDS,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if min(
            cache_ttl_seconds,
            metadata_ttl_seconds,
            error_retry_seconds,
            request_timeout_seconds,
        ) <= 0:
            raise ValueError("cache and timeout values must be positive")

        self._json_fetcher = json_fetcher
        self._clock = clock
        self._wall_clock = wall_clock
        self._cache_ttl_seconds = cache_ttl_seconds
        self._metadata_ttl_seconds = metadata_ttl_seconds
        self._error_retry_seconds = error_retry_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._snapshot: SteamPopularSnapshot | None = None
        self._snapshot_cached_at = 0.0
        self._retry_after = 0.0
        self._metadata_cache: dict[int, tuple[float, SteamAppMetadata]] = {}
        self._lock = asyncio.Lock()
        self._metadata_semaphore = asyncio.Semaphore(MAX_METADATA_CONCURRENCY)

    async def get_snapshot(self, limit: int = DEFAULT_RESULT_LIMIT) -> SteamPopularSnapshot:
        if not 1 <= limit <= MAX_RESULT_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_RESULT_LIMIT}")

        now = self._clock()
        self._raise_if_cold_start_is_cooling_down(now)
        cached = self._cached_snapshot(now, limit)
        if cached is not None:
            return cached

        async with self._lock:
            now = self._clock()
            self._raise_if_cold_start_is_cooling_down(now)
            cached = self._cached_snapshot(now, limit)
            if cached is not None:
                return cached

            try:
                snapshot = await self._refresh_snapshot()
            except SteamPopularError:
                self._retry_after = now + self._error_retry_seconds
                if self._snapshot is not None:
                    return self._snapshot.limited(limit, stale_cache=True)
                raise

            self._snapshot = snapshot
            self._snapshot_cached_at = now
            self._retry_after = 0.0
            return snapshot.limited(limit)

    def _raise_if_cold_start_is_cooling_down(self, now: float) -> None:
        if self._snapshot is None and now < self._retry_after:
            raise SteamPopularError("Steam 차트 재시도 대기 중입니다.")

    def _cached_snapshot(
        self,
        now: float,
        limit: int,
    ) -> SteamPopularSnapshot | None:
        if self._snapshot is None:
            return None
        if now - self._snapshot_cached_at < self._cache_ttl_seconds:
            return self._snapshot.limited(limit)
        if now < self._retry_after:
            return self._snapshot.limited(limit, stale_cache=True)
        return None

    async def _refresh_snapshot(self) -> SteamPopularSnapshot:
        chart_payload = await asyncio.to_thread(
            self._json_fetcher,
            STEAM_CHART_URL,
            self._request_timeout_seconds,
        )
        rollup_timestamp, entries = parse_chart_payload(chart_payload)
        metadata = await asyncio.gather(
            *(self._get_app_metadata(entry.app_id) for entry in entries)
        )
        games = tuple(
            SteamPopularGame(
                rank=entry.rank,
                app_id=entry.app_id,
                name=app_metadata.name,
                last_week_rank=entry.last_week_rank,
                peak_players=entry.peak_players,
                header_image=app_metadata.header_image,
            )
            for entry, app_metadata in zip(entries, metadata)
        )
        return SteamPopularSnapshot(
            rollup_timestamp=rollup_timestamp,
            fetched_timestamp=int(self._wall_clock()),
            games=games,
        )

    async def _get_app_metadata(self, app_id: int) -> SteamAppMetadata:
        now = self._clock()
        cached = self._metadata_cache.get(app_id)
        if cached is not None and now - cached[0] < self._metadata_ttl_seconds:
            return cached[1]

        try:
            async with self._metadata_semaphore:
                payload = await asyncio.to_thread(
                    self._json_fetcher,
                    build_app_details_url(app_id),
                    self._request_timeout_seconds,
                )
        except SteamPopularError:
            if cached is not None:
                return cached[1]
            return SteamAppMetadata(name=f"Steam App {app_id}", header_image=None)

        metadata = parse_app_metadata(payload, app_id)
        if metadata is None:
            if cached is not None:
                return cached[1]
            return SteamAppMetadata(name=f"Steam App {app_id}", header_image=None)

        self._metadata_cache[app_id] = (now, metadata)
        return metadata
