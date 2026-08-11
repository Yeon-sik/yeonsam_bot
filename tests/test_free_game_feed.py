import unittest
from datetime import datetime, timezone

from utils.free_game_feed import (
    FreeGameFeedError,
    FreeGameOffer,
    build_free_game_digest,
    build_gamerpower_url,
    parse_gamerpower_giveaways,
)


NOW = datetime(2026, 8, 9, 0, 0, tzinfo=timezone.utc)


def giveaway(**overrides):
    item = {
        "id": 10,
        "title": "Example Steam Giveaway",
        "type": "Game",
        "platforms": "PC, Steam",
        "status": "Active",
        "end_date": "2026-08-10 12:00:00",
        "worth": "$9.99",
        "description": "Claim this game and keep it.",
        "instructions": "Open the giveaway page.",
        "open_giveaway_url": "https://www.gamerpower.com/open/example",
        "gamerpower_url": "https://www.gamerpower.com/example",
    }
    item.update(overrides)
    return item


class FreeGameFeedTests(unittest.TestCase):
    def test_url_targets_only_steam_full_games(self):
        url = build_gamerpower_url()

        self.assertIn("platform=steam", url)
        self.assertIn("type=game", url)
        self.assertIn("sort-by=date", url)

    def test_parser_keeps_only_active_unexpired_steam_games(self):
        payload = [
            giveaway(id=1, title="Valid"),
            giveaway(id=2, status="Expired"),
            giveaway(id=3, type="Loot"),
            giveaway(id=4, platforms="PC, Epic Games Store"),
            giveaway(id=5, end_date="2026-08-08 23:59:59"),
            giveaway(id=6, description="Play for free this weekend"),
            giveaway(
                id=7,
                open_giveaway_url="https://malicious.example/free",
                gamerpower_url="https://malicious.example/fallback",
            ),
        ]

        offers = parse_gamerpower_giveaways(payload, now=NOW)

        self.assertEqual([offer.offer_id for offer in offers], ["1"])
        self.assertEqual(offers[0].title, "Valid")
        self.assertEqual(
            offers[0].ends_at,
            datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        )

    def test_unknown_end_date_stays_unknown(self):
        offers = parse_gamerpower_giveaways(
            [giveaway(end_date="N/A")],
            now=NOW,
        )

        self.assertEqual(len(offers), 1)
        self.assertIsNone(offers[0].ends_at)

    def test_no_active_status_payload_returns_empty_list(self):
        self.assertEqual(
            parse_gamerpower_giveaways(
                {"status": 0, "status_message": "No giveaways found"},
                now=NOW,
            ),
            [],
        )

    def test_unexpected_payload_raises(self):
        with self.assertRaises(FreeGameFeedError):
            parse_gamerpower_giveaways("invalid", now=NOW)

    def test_digest_is_order_independent_and_tracks_offer_changes(self):
        first = FreeGameOffer(
            "1",
            "One",
            "https://www.gamerpower.com/one",
            datetime(2026, 8, 10, tzinfo=timezone.utc),
            "$9.99",
        )
        second = FreeGameOffer(
            "2",
            "Two",
            "https://www.gamerpower.com/two",
            None,
            "$4.99",
        )

        self.assertEqual(
            build_free_game_digest([first, second]),
            build_free_game_digest([second, first]),
        )
        changed = FreeGameOffer(
            first.offer_id,
            first.title,
            first.claim_url,
            datetime(2026, 8, 11, tzinfo=timezone.utc),
            first.worth,
        )
        self.assertNotEqual(
            build_free_game_digest([first, second]),
            build_free_game_digest([changed, second]),
        )


if __name__ == "__main__":
    unittest.main()
