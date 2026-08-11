import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
GAMES_ROOT = ROOT / "docs" / "games"
GAME_NAMES = ("LethalCompany", "REPO")
EXPECTED_MONSTER_COUNTS = {"LethalCompany": 34, "REPO": 29}
FALLBACK_PATTERN = re.compile(
    r'<script id="game-data-fallback" type="application/json">(?P<payload>.*?)</script>',
    re.DOTALL,
)


def load_game(game_name: str) -> dict:
    path = GAMES_ROOT / game_name / f"{game_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_monster_guide(data: dict) -> dict:
    return next(guide for guide in data["guides"] if guide["id"] == "monsters")


def monsters_by_id(game_name: str) -> dict[str, dict]:
    guide = get_monster_guide(load_game(game_name))
    return {monster["id"]: monster for monster in guide["monsters"]}


class GameGuideDataTests(unittest.TestCase):
    def test_html_fallbacks_match_canonical_json(self):
        for game_name in GAME_NAMES:
            with self.subTest(game=game_name):
                html_path = GAMES_ROOT / f"{game_name}.html"
                html = html_path.read_text(encoding="utf-8-sig")
                match = FALLBACK_PATTERN.search(html)
                self.assertIsNotNone(match)
                self.assertEqual(load_game(game_name), json.loads(match.group("payload")))

    def test_monster_guides_have_versioned_sources_and_existing_images(self):
        for game_name in GAME_NAMES:
            data = load_game(game_name)
            guide = get_monster_guide(data)
            research = guide["research"]

            with self.subTest(game=game_name, field="research"):
                self.assertTrue(research["gameVersion"])
                self.assertRegex(research["verifiedAt"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertGreaterEqual(len(research["sources"]), 3)
                for source in research["sources"]:
                    self.assertTrue(source["label"])
                    self.assertTrue(source["url"].startswith("https://"))

            ids = [monster["id"] for monster in guide["monsters"]]
            self.assertEqual(len(ids), EXPECTED_MONSTER_COUNTS[game_name])
            self.assertEqual(len(ids), len(set(ids)))

            for monster in guide["monsters"]:
                with self.subTest(game=game_name, monster=monster["id"]):
                    for field in ("id", "name", "nameKr", "description", "strategy", "health", "spawn"):
                        self.assertTrue(monster.get(field), field)
                    if monster.get("image"):
                        image_path = GAMES_ROOT / monster["image"].removeprefix("./")
                        self.assertTrue(image_path.is_file(), image_path)
                    combined = " ".join(str(value) for value in monster.values())
                    self.assertNotIn("조사 중", combined)
                    self.assertNotIn("삽 ?", combined)

    def test_lethal_company_combat_and_section_fields(self):
        guide = get_monster_guide(load_game("LethalCompany"))
        allowed_sections = {"inside", "outside", "daytime", "company", "dummy"}

        for monster in guide["monsters"]:
            with self.subTest(monster=monster["id"]):
                self.assertIn(monster["section"], allowed_sections)
                self.assertTrue(monster.get("detection"))
                if monster["section"] != "dummy":
                    health = monster["health"]
                    self.assertTrue("삽" in health and "칼" in health)

    def test_repo_combat_fields(self):
        guide = get_monster_guide(load_game("REPO"))

        for monster in guide["monsters"]:
            with self.subTest(monster=monster["id"]):
                self.assertIn(monster["tier"], (1, 2, 3))
                for field in ("damage", "detection", "strength", "cashDrop"):
                    self.assertTrue(monster.get(field), field)

        tier_counts = {
            tier: sum(monster["tier"] == tier for monster in guide["monsters"])
            for tier in (1, 2, 3)
        }
        self.assertEqual(tier_counts, {1: 9, 2: 12, 3: 8})

    def test_high_risk_lethal_company_corrections_do_not_regress(self):
        monsters = monsters_by_id("LethalCompany")

        self.assertEqual(monsters["cadaver-bloom"]["health"], "삽 4회 / 칼 4회 / 샷건 4회")
        self.assertEqual(monsters["feiopar"]["health"], "삽 4회 / 칼 4회")
        self.assertEqual(monsters["mask-hornets"]["section"], "inside")
        self.assertIn("머리: 삽 6회", monsters["eyeless-dog"]["health"])
        self.assertIn("칼 1회", monsters["butler"]["health"])
        self.assertEqual(monsters["company-monster"]["section"], "company")
        self.assertEqual(monsters["lasso-man"]["section"], "dummy")

    def test_high_risk_repo_corrections_do_not_regress(self):
        monsters = monsters_by_id("REPO")

        self.assertEqual((monsters["elsa"]["tier"], monsters["elsa"]["health"]), (1, "600"))
        self.assertEqual((monsters["trudge"]["tier"], monsters["trudge"]["health"]), (3, "500"))
        self.assertEqual((monsters["peeper"]["tier"], monsters["peeper"]["health"]), (1, "30"))
        self.assertEqual(monsters["shadow-child"]["tier"], 1)
        self.assertEqual(monsters["cleanup-crew"]["tier"], 3)
        self.assertEqual(monsters["banger"]["cashDrop"], "없음")


if __name__ == "__main__":
    unittest.main()
