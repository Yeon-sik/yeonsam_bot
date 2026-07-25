import json
import os
import tempfile
import threading
import unittest
from pathlib import Path


TEST_DATA_DIR = tempfile.TemporaryDirectory()
os.environ["BOT_DATA_DIR"] = TEST_DATA_DIR.name
Path(TEST_DATA_DIR.name, "guild_config.json").write_text(
    json.dumps(
        {
            "100": {
                "welcome_message": "{server}에 오신 것을 환영합니다.",
                "link": "https://example.com/rules",
            }
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

from utils import storage  # noqa: E402


class StorageTests(unittest.TestCase):
    def test_legacy_json_is_migrated(self):
        config = storage.get_guild(100)

        self.assertEqual(config["welcome_message"], "{server}에 오신 것을 환영합니다.")
        self.assertEqual(config["link"], "https://example.com/rules")
        self.assertIsNone(config["welcome_channel_id"])
        self.assertTrue(storage.DB_FILE.exists())

    def test_guild_settings_round_trip(self):
        storage.ensure_guild(200)
        storage.update_guild(200, "welcome_channel_id", 300)
        storage.update_guild(200, "link", "https://example.com")

        config = storage.get_guild(200)

        self.assertEqual(config["welcome_channel_id"], 300)
        self.assertEqual(config["link"], "https://example.com")

    def test_patch_subscription_round_trip(self):
        storage.upsert_patch_subscription(200, "REPO", 400, "article-1")

        subscriptions = storage.list_patch_subscriptions(200)

        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0]["channel_id"], 400)
        self.assertEqual(subscriptions[0]["last_seen_id"], "article-1")

        storage.update_patch_last_seen(200, "REPO", "article-2")
        self.assertEqual(
            storage.list_patch_subscriptions(200)[0]["last_seen_id"],
            "article-2",
        )
        self.assertTrue(storage.remove_patch_subscription(200, "REPO"))

    def test_metrics_are_atomic_across_threads(self):
        threads = [
            threading.Thread(
                target=lambda: [
                    storage.record_metric("concurrent_test", 200) for _ in range(25)
                ]
            )
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        totals = storage.get_metric_totals(days=1, guild_id=200)

        self.assertEqual(totals["concurrent_test"], 100)

    def test_runtime_state_round_trip(self):
        storage.set_runtime_state("migration:test", "done")

        self.assertEqual(storage.get_runtime_state("migration:test"), "done")

    def test_delete_guild_data_removes_settings_and_subscriptions(self):
        storage.ensure_guild(700)
        storage.upsert_patch_subscription(700, "REPO", 701, "article-1")
        storage.record_metric("delete_test", 700)

        storage.delete_guild_data(700)

        self.assertEqual(storage.get_guild(700), storage.DEFAULT_GUILD_CONFIG)
        self.assertEqual(storage.list_patch_subscriptions(700), [])
        self.assertEqual(storage.get_metric_totals(days=1, guild_id=700), {})


if __name__ == "__main__":
    unittest.main()
