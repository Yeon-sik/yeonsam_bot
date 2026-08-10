import unittest
from unittest.mock import patch


class GuideSearchContractTests(unittest.TestCase):
    def test_every_selectable_json_entry_is_searchable(self):
        # 봇 모듈은 storage 테스트가 BOT_DATA_DIR을 설정한 뒤 불러와 테스트 간 경로 오염을 막습니다.
        from cogs.yeonsam import (
            build_search_candidates,
            build_search_route,
            category_has_record_entries,
            flatten_category_entries,
        )
        from utils.game_content import list_games, load_game_data

        candidate_routes = {
            str(candidate["route"])
            for candidate in build_search_candidates()
        }
        missing_routes = []

        for game_slug in list_games():
            data = load_game_data(game_slug)
            for topic in data.get("guides", []):
                entries = []
                if topic.get("monsters"):
                    entries = topic["monsters"]
                elif category_has_record_entries(topic):
                    entries = [entry for _, entry in flatten_category_entries(topic)]
                elif topic.get("groups") and topic.get("entrySelectable") is not False:
                    entries = topic["groups"]

                for entry in entries:
                    entry_id = entry.get("id") or entry.get("title")
                    route = build_search_route(game_slug, "guides", topic.get("id"), entry_id)
                    if route not in candidate_routes:
                        missing_routes.append(route)

        self.assertEqual(missing_routes, [])

    def test_alias_query_prefers_exact_record_route(self):
        from cogs.yeonsam import resolve_search_selection

        sample_data = {
            "slug": "PUBG",
            "name": "PUBG: BATTLEGROUNDS",
            "guides": [
                {
                    "id": "akm",
                    "label": "AKM",
                    "title": "AKM 가이드",
                    "groups": [],
                },
                {
                    "id": "weapons",
                    "label": "무기",
                    "title": "무기",
                    "groups": [
                        {
                            "title": "돌격소총",
                            "entries": [
                                {
                                    "id": "akm-weapon",
                                    "name": "AKM",
                                    "nameKr": "AKM",
                                    "aliases": ["7탄AKM"],
                                }
                            ],
                        }
                    ],
                },
            ],
        }

        with patch("cogs.yeonsam.list_games", return_value=["PUBG"]), patch(
            "cogs.yeonsam.load_game_data",
            return_value=sample_data,
        ):
            self.assertEqual(
                resolve_search_selection("7탄AKM"),
                ("PUBG", "guides", "weapons", "akm-weapon"),
            )
            self.assertEqual(
                resolve_search_selection("AKM"),
                ("PUBG", "guides", "weapons", "akm-weapon"),
            )

    def test_record_entry_embed_includes_stats_and_sources(self):
        import discord

        from cogs.yeonsam import add_record_entry_fields

        embed = discord.Embed(title="test")
        add_record_entry_fields(
            embed=embed,
            data={"slug": "PUBG", "pagePath": "PUBG.html"},
            category_id="weapons",
            group={"title": "돌격소총"},
            item={
                "id": "akm",
                "name": "AKM",
                "nameKr": "에이케이엠",
                "stats": [
                    {"label": "탄약", "value": "7.62mm"},
                    {"label": "데미지", "value": "49"},
                ],
                "sources": [
                    {
                        "label": "PUBG Wiki [AKM]",
                        "url": "https://example.com/akm",
                        "checkedAt": "2026-08-10",
                    },
                    {
                        "label": "invalid",
                        "url": "ftp://example.com/akm",
                        "checkedAt": "2026-08-10",
                    },
                ],
            },
        )

        field_map = {field.name: field.value for field in embed.fields}
        self.assertIn("핵심 정보", field_map)
        self.assertEqual(field_map["핵심 정보"], "- 탄약: 7.62mm\n- 데미지: 49")
        self.assertIn("출처", field_map)
        self.assertEqual(
            field_map["출처"],
            "- [PUBG Wiki (AKM)](https://example.com/akm) (2026-08-10)",
        )


if __name__ == "__main__":
    unittest.main()
