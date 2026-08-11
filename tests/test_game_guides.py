import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
GAMES_ROOT = ROOT / "docs" / "games"
GAME_NAMES = ("LethalCompany", "REPO")
EXPECTED_MONSTER_COUNTS = {"LethalCompany": 34, "REPO": 29}
EXPECTED_ITEM_COUNTS = {"LethalCompany": 14, "REPO": 40}
EXPECTED_MOD_COUNTS = {"LethalCompany": 13, "REPO": 12}
FALLBACK_PATTERN = re.compile(
    r'<script id="game-data-fallback" type="application/json">(?P<payload>.*?)</script>',
    re.DOTALL,
)


def load_game(game_name: str) -> dict:
    path = GAMES_ROOT / game_name / f"{game_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_monster_guide(data: dict) -> dict:
    return next(guide for guide in data["guides"] if guide["id"] == "monsters")


def get_guide(data: dict, guide_id: str) -> dict:
    return next(guide for guide in data["guides"] if guide["id"] == guide_id)


def flatten_record_entries(guide: dict) -> list[tuple[dict, dict]]:
    return [
        (group, entry)
        for group in guide.get("groups", [])
        for entry in group.get("entries", [])
    ]


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

    def test_item_and_mod_guides_have_current_sources_and_local_images(self):
        thunderstore_categories = {"LethalCompany": "lethal-company", "REPO": "repo"}

        for game_name in GAME_NAMES:
            data = load_game(game_name)
            item_guide = get_guide(data, "items")
            mod_guide = get_guide(data, "mods")
            item_entries = flatten_record_entries(item_guide)
            mod_entries = flatten_record_entries(mod_guide)

            with self.subTest(game=game_name, guide="items"):
                self.assertEqual(len(item_entries), EXPECTED_ITEM_COUNTS[game_name])
                self.assertEqual(len({entry["id"] for _, entry in item_entries}), len(item_entries))
                self.assertRegex(item_guide["research"]["verifiedAt"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertGreaterEqual(len(item_guide["research"]["sources"]), 1)

            with self.subTest(game=game_name, guide="mods"):
                self.assertEqual(len(mod_entries), EXPECTED_MOD_COUNTS[game_name])
                self.assertEqual(len({entry["id"] for _, entry in mod_entries}), len(mod_entries))
                self.assertRegex(mod_guide["research"]["verifiedAt"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertGreaterEqual(len(mod_guide["research"]["sources"]), 3)

            for guide in (item_guide, mod_guide):
                for source in guide["research"]["sources"]:
                    self.assertTrue(source.get("label"))
                    self.assertTrue(source.get("url", "").startswith("https://"))

            for _, entry in item_entries:
                with self.subTest(game=game_name, item=entry["id"]):
                    for field in ("id", "name", "nameKr", "image", "description", "usage", "stats"):
                        self.assertTrue(entry.get(field), field)
                    self.assertTrue(entry.get("price") is not None or entry.get("priceRange"))
                    image_path = GAMES_ROOT / entry["image"].removeprefix("./")
                    self.assertTrue(image_path.is_file(), image_path)
                    if game_name == "REPO":
                        self.assertTrue(entry.get("imageSource", "").startswith("https://"))
                    else:
                        self.assertGreaterEqual(len(entry.get("sources", [])), 1)

            install_prefix = f"https://thunderstore.io/c/{thunderstore_categories[game_name]}/p/"
            for _, entry in mod_entries:
                with self.subTest(game=game_name, mod=entry["id"]):
                    for field in ("id", "name", "nameKr", "image", "description", "usage", "aliases", "stats", "sources"):
                        self.assertTrue(entry.get(field), field)
                    self.assertTrue(entry.get("installLink", "").startswith(install_prefix))
                    image_path = GAMES_ROOT / entry["image"].removeprefix("./")
                    self.assertTrue(image_path.is_file(), image_path)
                    for source in entry["sources"]:
                        self.assertTrue(source.get("label"))
                        self.assertTrue(source.get("url", "").startswith("https://"))
                        self.assertRegex(source.get("checkedAt", ""), r"^\d{4}-\d{2}-\d{2}$")

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

    def test_high_risk_item_and_mod_corrections_do_not_regress(self):
        lethal = load_game("LethalCompany")
        lethal_items = {entry["id"]: entry for _, entry in flatten_record_entries(get_guide(lethal, "items"))}
        lethal_mods = {entry["id"]: entry for _, entry in flatten_record_entries(get_guide(lethal, "mods"))}

        self.assertEqual(lethal_items["walkie-talkie"]["price"], 10)
        self.assertEqual(lethal_items["pro-flashlight"]["price"], 28)
        self.assertEqual(lethal_items["tzp-inhalant"]["price"], 80)
        self.assertEqual(lethal_items["jetpack"]["price"], 900)
        self.assertEqual(lethal_items["shovel"]["nameKr"], "삽")
        self.assertNotIn("latecompany", lethal_mods)
        self.assertNotIn("shiploot", lethal_mods)
        self.assertIn("몬스터", lethal_mods["sell-bodies-fixed"]["description"])

        repo = load_game("REPO")
        repo_item_guide = get_guide(repo, "items")
        repo_items = {entry["id"]: (group, entry) for group, entry in flatten_record_entries(repo_item_guide)}
        repo_mods = {entry["id"]: entry for _, entry in flatten_record_entries(get_guide(repo, "mods"))}

        self.assertEqual(repo_items["stun-mine"][1]["name"], "Trapzap")
        self.assertEqual(repo_items["gun"][1]["priceRange"], "$18,000~$20,000")
        self.assertEqual(repo_items["energy-crystal"][1]["priceRange"], "$5,000~$24,000")
        self.assertEqual(repo_items["scout"][0]["id"], "vehicles")
        self.assertEqual(repo_items["hauler"][0]["id"], "vehicles")
        self.assertNotIn("드론", repo_items["hauler"][1]["nameKr"])
        for deprecated_id in ("moreplayers", "sharedupgrades", "latejoin", "customcolors", "moreshopitems", "repo-hd"):
            self.assertNotIn(deprecated_id, repo_mods)

    def test_item_guides_have_local_images_and_expected_critical_entries(self):
        expected_counts = {"LethalCompany": 14, "REPO": 40}

        for game_name, expected_count in expected_counts.items():
            guide = get_guide(load_game(game_name), "items")
            entries = [entry for group in guide["groups"] for entry in group.get("entries", [])]

            with self.subTest(game=game_name, field="count"):
                self.assertEqual(len(entries), expected_count)
                self.assertRegex(guide["research"]["verifiedAt"], r"^\d{4}-\d{2}-\d{2}$")

            for entry in entries:
                with self.subTest(game=game_name, entry=entry["id"]):
                    self.assertTrue(entry.get("name"))
                    self.assertTrue(entry.get("image"))
                    image_path = GAMES_ROOT / entry["image"].removeprefix("./")
                    self.assertTrue(image_path.is_file(), image_path)

        lethal_items = {
            entry["id"]: entry
            for group in get_guide(load_game("LethalCompany"), "items")["groups"]
            for entry in group.get("entries", [])
        }
        self.assertEqual(lethal_items["walkie-talkie"]["price"], 10)
        self.assertEqual(lethal_items["pro-flashlight"]["price"], 28)
        self.assertEqual(lethal_items["tzp-inhalant"]["price"], 80)
        self.assertEqual(lethal_items["jetpack"]["price"], 900)
        self.assertEqual(lethal_items["inverse-teleporter"]["stats"][0]["value"], "210초")

        repo_items_guide = get_guide(load_game("REPO"), "items")
        repo_groups = {group["id"]: group for group in repo_items_guide["groups"]}
        repo_items = {
            entry["id"]: entry
            for group in repo_items_guide["groups"]
            for entry in group.get("entries", [])
        }
        self.assertEqual(repo_items["stun-mine"]["name"], "Trapzap")
        self.assertIn("Stun Mine", repo_items["stun-mine"].get("aliases", []))
        self.assertEqual([entry["id"] for entry in repo_groups["vehicles"]["entries"]], ["scout", "hauler"])
        self.assertEqual(repo_items["scout"]["stats"][0]["value"], "탑승형 차량")
        self.assertEqual(repo_items["hauler"]["stats"][0]["value"], "탑승형 차량")
        self.assertEqual(repo_items["energy-crystal"]["priceRange"], "$5,000~$24,000")
        self.assertEqual(repo_items["semibot-walkies"]["stats"][2]["value"], "제한 없음")

    def test_mod_guides_have_install_links_local_images_and_no_deprecated_recommendations(self):
        deprecated_ids = {
            "LethalCompany": {"latecompany", "shiploot"},
            "REPO": {"moreplayers", "sharedupgrades", "latejoin", "customcolors", "moreshopitems", "repo-hd"},
        }

        for game_name in ("LethalCompany", "REPO"):
            guide = get_guide(load_game(game_name), "mods")
            entries = [entry for group in guide["groups"] for entry in group.get("entries", [])]

            with self.subTest(game=game_name, field="research"):
                self.assertRegex(guide["research"]["verifiedAt"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertGreaterEqual(len(guide["research"]["sources"]), 3)

            for entry in entries:
                with self.subTest(game=game_name, mod=entry["id"]):
                    self.assertTrue(entry.get("image"))
                    self.assertTrue(entry.get("installLink", "").startswith("https://thunderstore.io/"))
                    self.assertGreaterEqual(len(entry.get("sources", [])), 1)
                    image_path = GAMES_ROOT / entry["image"].removeprefix("./")
                    self.assertTrue(image_path.is_file(), image_path)

            entry_ids = {entry["id"] for entry in entries}
            self.assertTrue(deprecated_ids[game_name].isdisjoint(entry_ids))

        lethal_mods = {
            entry["id"]: entry
            for group in get_guide(load_game("LethalCompany"), "mods")["groups"]
            for entry in group.get("entries", [])
        }
        self.assertEqual(lethal_mods["bepinexpack"]["installLink"], "https://thunderstore.io/c/lethal-company/p/BepInEx/BepInExPack/")
        self.assertEqual(lethal_mods["lategame-upgrades"]["stats"][0]["value"], "3.14.1 · 2026-08-10")

        repo_mods = {
            entry["id"]: entry
            for group in get_guide(load_game("REPO"), "mods")["groups"]
            for entry in group.get("entries", [])
        }
        self.assertEqual(repo_mods["repolib"]["installLink"], "https://thunderstore.io/c/repo/p/Zehs/REPOLib/")
        self.assertIn("v0.4.4", " ".join(stat["value"] for stat in repo_mods["more-players-simple"]["stats"]))
        self.assertEqual(repo_mods["repo-fidelity"]["installLink"], "https://thunderstore.io/c/repo/p/Vippy/REPOFidelity/")


if __name__ == "__main__":
    unittest.main()
