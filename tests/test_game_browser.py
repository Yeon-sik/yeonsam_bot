from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = ROOT / "bot"
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

from cogs.yeonsam import (  # noqa: E402
    GameBrowserView,
    build_game_browser_embed,
    build_search_candidates,
    select_monster_research_sources,
)
from utils.game_content import load_game_data  # noqa: E402


GAME_NAMES = ("LethalCompany", "REPO")


def get_monster_guide(game_name: str) -> dict:
    data = load_game_data(game_name)
    return next(guide for guide in data["guides"] if guide["id"] == "monsters")


class GameBrowserTests(unittest.TestCase):
    def test_search_index_contains_every_monster(self):
        candidate_routes = {str(candidate["route"]) for candidate in build_search_candidates()}

        for game_name in GAME_NAMES:
            for monster in get_monster_guide(game_name)["monsters"]:
                with self.subTest(game=game_name, monster=monster["id"]):
                    expected_route = f"{game_name}|guides|monsters|{monster['id']}"
                    self.assertIn(expected_route, candidate_routes)

    def test_selected_monster_outside_first_25_remains_visible(self):
        view = GameBrowserView(
            user_id=1,
            game="LethalCompany",
            section="guides",
            topic="monsters",
            entry="company-monster",
        )

        selected_options = [option.value for option in view.entry_options() if option.default]
        self.assertEqual(selected_options, ["company-monster"])

    def test_monster_embeds_stay_within_discord_limits(self):
        for game_name in GAME_NAMES:
            for monster in get_monster_guide(game_name)["monsters"]:
                embed = build_game_browser_embed(
                    game=game_name,
                    section="guides",
                    topic="monsters",
                    entry=monster["id"],
                )
                field_values = [str(field.value) for field in embed.fields]
                total_length = (
                    len(embed.title or "")
                    + len(embed.description or "")
                    + sum(len(field.name) + len(value) for field, value in zip(embed.fields, field_values))
                )

                with self.subTest(game=game_name, monster=monster["id"]):
                    self.assertLessEqual(len(embed.fields), 25)
                    self.assertTrue(all(len(value) <= 1024 for value in field_values))
                    self.assertLessEqual(total_length, 6000)

    def test_compact_sources_include_official_data_and_practical_guides(self):
        for game_name in GAME_NAMES:
            research = get_monster_guide(game_name)["research"]
            selected = select_monster_research_sources(research["sources"])
            selected_types = [str(source.get("type", "")) for source in selected]

            with self.subTest(game=game_name):
                self.assertTrue(any(source_type == "official" for source_type in selected_types))
                self.assertTrue(
                    any("wiki" in source_type or "community-data" in source_type for source_type in selected_types)
                )
                self.assertTrue(any("practical" in source_type for source_type in selected_types))


if __name__ == "__main__":
    unittest.main()
