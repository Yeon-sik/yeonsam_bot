import unittest

from utils.patch_feed import (
    PatchArticle,
    build_steam_news_url,
    clean_patch_summary,
    find_new_articles,
    parse_steam_news,
)


class PatchFeedTests(unittest.TestCase):
    def test_parse_steam_news_skips_incomplete_items(self):
        payload = {
            "appnews": {
                "newsitems": [
                    {
                        "gid": "3",
                        "title": "Museum Update",
                        "url": "https://example.com/3",
                        "contents": "<b>New</b> rooms &amp; items",
                        "date": 123,
                        "author": "Developer",
                    },
                    {"gid": "", "title": "Broken", "url": "https://example.com"},
                ]
            }
        }

        articles = parse_steam_news(payload)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].article_id, "3")
        self.assertEqual(articles[0].summary, "New rooms & items")

    def test_find_new_articles_returns_oldest_first(self):
        articles = [
            PatchArticle("3", "Three", "https://example.com/3", "", 3, ""),
            PatchArticle("2", "Two", "https://example.com/2", "", 2, ""),
            PatchArticle("1", "One", "https://example.com/1", "", 1, ""),
        ]

        result = find_new_articles(articles, "1")

        self.assertEqual([article.article_id for article in result], ["2", "3"])

    def test_unknown_cursor_does_not_backfill_old_articles(self):
        articles = [
            PatchArticle("3", "Three", "https://example.com/3", "", 3, ""),
            PatchArticle("2", "Two", "https://example.com/2", "", 2, ""),
        ]

        self.assertEqual(find_new_articles(articles, "missing"), [])

    def test_url_contains_official_steam_parameters(self):
        url = build_steam_news_url(
            {
                "provider": "steam",
                "app_id": 1966720,
                "feed": "steam_community_announcements",
            }
        )

        self.assertIn("appid=1966720", url)
        self.assertIn("feeds=steam_community_announcements", url)

    def test_summary_is_limited(self):
        summary = clean_patch_summary("<p>" + ("a" * 600) + "</p>", limit=100)

        self.assertEqual(len(summary), 100)
        self.assertTrue(summary.endswith("…"))


if __name__ == "__main__":
    unittest.main()
