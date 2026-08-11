import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from cogs.free_game_alerts import (
    FreeGameAlerts,
    build_free_game_embeds,
    free_game_poll_interval_minutes,
    send_free_game_embeds,
)
from utils.free_game_feed import FreeGameOffer


def offer(offer_id="1", title="Free Game"):
    return FreeGameOffer(
        offer_id=offer_id,
        title=title,
        claim_url=f"https://www.gamerpower.com/open/{offer_id}",
        ends_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        worth="$9.99",
    )


class FreeGameEmbedTests(unittest.TestCase):
    def test_embed_displays_expiry_link_and_attribution(self):
        embed = build_free_game_embeds([offer()])[0]

        self.assertEqual(embed.title, "Steam 기간 한정 무료 게임")
        self.assertIn("<t:1786363200:F>", embed.fields[0].value)
        self.assertIn("https://www.gamerpower.com/open/1", embed.fields[0].value)
        self.assertIn("https://www.gamerpower.com/", embed.description)
        self.assertIn("GamerPower", embed.footer.text)

    def test_empty_feed_is_explicit(self):
        embed = build_free_game_embeds([])[0]

        self.assertIn("없습니다", embed.description)

    def test_large_feed_is_split_into_safe_embed_pages(self):
        embeds = build_free_game_embeds(
            [offer(str(index), f"Game {index}") for index in range(21)]
        )

        self.assertEqual([len(embed.fields) for embed in embeds], [10, 10, 1])

    def test_poll_interval_is_clamped(self):
        with patch.dict(os.environ, {"FREE_GAME_POLL_INTERVAL_MINUTES": "1"}):
            self.assertEqual(free_game_poll_interval_minutes(), 15)
        with patch.dict(os.environ, {"FREE_GAME_POLL_INTERVAL_MINUTES": "invalid"}):
            self.assertEqual(free_game_poll_interval_minutes(), 360)


class FreeGamePollingTests(unittest.IsolatedAsyncioTestCase):
    async def test_channel_send_does_not_receive_ephemeral_option(self):
        destination = AsyncMock()

        await send_free_game_embeds(destination, [offer()])

        self.assertNotIn("ephemeral", destination.send.await_args.kwargs)

    async def test_interaction_followup_can_be_ephemeral(self):
        destination = AsyncMock()

        await send_free_game_embeds(destination, [offer()], ephemeral=True)

        self.assertTrue(destination.send.await_args.kwargs["ephemeral"])

    async def test_unchanged_digest_is_sent_once_per_process(self):
        cog = FreeGameAlerts(object())
        cog._fetch_offers = AsyncMock(return_value=[offer()])
        cog._send_to_subscription = AsyncMock()
        subscription = {"guild_id": 100, "channel_id": 200}

        with patch("cogs.free_game_alerts.record_metric"):
            first = await cog._poll_subscriptions([subscription])
            second = await cog._poll_subscriptions([subscription])

        self.assertEqual(first, {100})
        self.assertEqual(second, set())
        cog._send_to_subscription.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
