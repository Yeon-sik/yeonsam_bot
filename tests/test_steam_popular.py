import asyncio
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bot"))

from cogs.steam_popular import build_popular_embed, format_rank_change  # noqa: E402
from utils.steam_popular import (  # noqa: E402
    STEAM_CHART_URL,
    SteamPopularError,
    SteamPopularGame,
    SteamPopularService,
    SteamPopularSnapshot,
    parse_app_metadata,
    parse_chart_payload,
)


def chart_payload(*rows):
    return {
        "response": {
            "rollup_date": 1_700_000_000,
            "ranks": list(rows),
        }
    }


def rank_row(rank, app_id, peak, last_week_rank=None):
    return {
        "rank": rank,
        "appid": app_id,
        "peak_in_game": peak,
        "last_week_rank": last_week_rank,
    }


class SteamPayloadTests(unittest.TestCase):
    def test_chart_parser_orders_rows_and_skips_malformed_duplicates(self):
        rollup, entries = parse_chart_payload(
            chart_payload(
                rank_row(2, 20, 2_000, 4),
                {"rank": "invalid", "appid": 99, "peak_in_game": 10},
                rank_row(1, 10, 3_000, 1),
                rank_row(3, 20, 1_000, 2),
            )
        )

        self.assertEqual(rollup, 1_700_000_000)
        self.assertEqual([entry.app_id for entry in entries], [10, 20])
        self.assertEqual(entries[1].last_week_rank, 4)

    def test_chart_parser_rejects_payload_without_usable_rows(self):
        with self.assertRaises(SteamPopularError):
            parse_chart_payload(chart_payload({"rank": 1}))

    def test_app_metadata_requires_successful_named_result_and_https_image(self):
        metadata = parse_app_metadata(
            {
                "10": {
                    "success": True,
                    "data": {
                        "name": " Test Game ",
                        "header_image": "http://example.com/header.jpg",
                    },
                }
            },
            10,
        )

        self.assertEqual(metadata.name, "Test Game")
        self.assertIsNone(metadata.header_image)
        self.assertIsNone(parse_app_metadata({"10": {"success": False}}, 10))


class SteamPopularServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_refreshes_chart_without_refetching_fresh_metadata(self):
        now = [100.0]
        calls: list[str] = []

        def fake_fetch(url, timeout):
            calls.append(url)
            if url == STEAM_CHART_URL:
                return chart_payload(rank_row(1, 10, 3_000, 2), rank_row(2, 20, 2_000, 1))
            app_id = int(parse_qs(urlsplit(url).query)["appids"][0])
            return {
                str(app_id): {
                    "success": True,
                    "data": {
                        "name": f"Game {app_id}",
                        "header_image": f"https://cdn.example.com/{app_id}.jpg",
                    },
                }
            }

        service = SteamPopularService(
            json_fetcher=fake_fetch,
            clock=lambda: now[0],
            wall_clock=lambda: 1_700_000_100,
            cache_ttl_seconds=10,
            metadata_ttl_seconds=100,
            error_retry_seconds=5,
        )

        first = await service.get_snapshot(2)
        second = await service.get_snapshot(1)
        self.assertEqual(len(first.games), 2)
        self.assertEqual(len(second.games), 1)
        self.assertEqual(len(calls), 3)

        now[0] = 111.0
        refreshed = await service.get_snapshot(2)
        self.assertEqual(len(refreshed.games), 2)
        self.assertEqual(calls.count(STEAM_CHART_URL), 2)
        self.assertEqual(len(calls), 4)

    async def test_expired_snapshot_is_returned_when_refresh_fails(self):
        now = [100.0]
        fail_chart = [False]

        def fake_fetch(url, timeout):
            if url == STEAM_CHART_URL:
                if fail_chart[0]:
                    raise SteamPopularError("offline")
                return chart_payload(rank_row(1, 10, 3_000, 1))
            return {
                "10": {
                    "success": True,
                    "data": {"name": "Cached Game", "header_image": None},
                }
            }

        service = SteamPopularService(
            json_fetcher=fake_fetch,
            clock=lambda: now[0],
            cache_ttl_seconds=10,
            metadata_ttl_seconds=100,
            error_retry_seconds=5,
        )
        await service.get_snapshot()

        now[0] = 111.0
        fail_chart[0] = True
        stale = await service.get_snapshot()
        self.assertTrue(stale.stale_cache)
        self.assertEqual(stale.games[0].name, "Cached Game")

    async def test_cold_start_failure_uses_retry_cooldown(self):
        now = [100.0]
        chart_calls = [0]

        def failing_fetch(url, timeout):
            chart_calls[0] += 1
            raise SteamPopularError("offline")

        service = SteamPopularService(
            json_fetcher=failing_fetch,
            clock=lambda: now[0],
            error_retry_seconds=5,
        )

        with self.assertRaises(SteamPopularError):
            await service.get_snapshot()
        with self.assertRaises(SteamPopularError):
            await service.get_snapshot()
        self.assertEqual(chart_calls[0], 1)

        now[0] = 106.0
        with self.assertRaises(SteamPopularError):
            await service.get_snapshot()
        self.assertEqual(chart_calls[0], 2)

    async def test_single_flight_prevents_duplicate_refreshes(self):
        chart_calls = [0]

        def fake_fetch(url, timeout):
            if url == STEAM_CHART_URL:
                chart_calls[0] += 1
                return chart_payload(rank_row(1, 10, 3_000, 1))
            return {"10": {"success": True, "data": {"name": "Game", "header_image": None}}}

        service = SteamPopularService(json_fetcher=fake_fetch)
        await asyncio.gather(service.get_snapshot(), service.get_snapshot())
        self.assertEqual(chart_calls[0], 1)


class SteamPopularEmbedTests(unittest.TestCase):
    def test_rank_change_and_embed_explain_metric_and_source_date(self):
        game = SteamPopularGame(
            rank=1,
            app_id=10,
            name="Test *Game*",
            last_week_rank=3,
            peak_players=123_456,
            header_image="https://cdn.example.com/header.jpg",
        )
        snapshot = SteamPopularSnapshot(
            rollup_timestamp=1_700_000_000,
            fetched_timestamp=1_700_000_100,
            games=(game,),
        )

        embed = build_popular_embed(snapshot)
        payload = embed.to_dict()
        self.assertEqual(format_rank_change(game), "지난주 대비 ▲ 2")
        self.assertIn("실시간 접속자가 아닌", payload["description"])
        self.assertIn("123,456명", payload["description"])
        self.assertIn("2023-11-14 UTC", payload["footer"]["text"])
        self.assertEqual(payload["thumbnail"]["url"], game.header_image)

    def test_embed_warns_when_steam_source_date_is_delayed(self):
        game = SteamPopularGame(
            rank=1,
            app_id=10,
            name="Test Game",
            last_week_rank=1,
            peak_players=123_456,
            header_image=None,
        )
        snapshot = SteamPopularSnapshot(
            rollup_timestamp=1_700_000_000,
            fetched_timestamp=1_700_400_000,
            games=(game,),
        )

        self.assertIn("원본의 집계일", build_popular_embed(snapshot).description)


if __name__ == "__main__":
    unittest.main()
