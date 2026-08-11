import json
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sync_game_fallbacks import discover_game_sources, read_inline_fallback  # noqa: E402


class _LocalAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = {"href"} if tag == "a" or tag == "link" else {"src"}
        for name, value in attrs:
            if name in names and value:
                self.references.append(value)


def _is_remote_reference(reference: str) -> bool:
    return urlsplit(reference).scheme in {"http", "https"}


def _has_matching_image_signature(path: Path) -> bool:
    header = path.read_bytes()[:16]
    suffix = path.suffix.lower()
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    return True


def _iter_nested_image_references(node: object, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    matches: list[tuple[tuple[str, ...], str]] = []

    if isinstance(node, dict):
        for key, value in node.items():
            next_path = (*path, str(key))
            if key in {"profileImage", "image"} and isinstance(value, str) and value:
                matches.append((next_path, value))
            matches.extend(_iter_nested_image_references(value, next_path))
        return matches

    if isinstance(node, list):
        for index, value in enumerate(node):
            matches.extend(_iter_nested_image_references(value, (*path, str(index))))

    return matches


class StaticSiteContractTests(unittest.TestCase):
    def test_inline_game_fallbacks_match_shared_json(self):
        sources = discover_game_sources()
        self.assertGreater(len(sources), 0)

        for json_path, page_path, data in sources:
            with self.subTest(json=json_path.name, page=page_path.name):
                self.assertEqual(read_inline_fallback(page_path), data)

    def test_local_html_assets_exist(self):
        for page_path in DOCS_ROOT.rglob("*.html"):
            parser = _LocalAssetParser()
            parser.feed(page_path.read_text(encoding="utf-8"))

            for reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.scheme or reference.startswith("#"):
                    continue
                target = (page_path.parent / unquote(parsed.path)).resolve()
                with self.subTest(page=page_path.name, reference=reference):
                    self.assertTrue(target.is_file(), f"로컬 파일을 찾을 수 없습니다: {target}")

    def test_game_json_local_image_assets_exist(self):
        for json_path, page_path, data in discover_game_sources():
            for data_path, reference in _iter_nested_image_references(data):
                if _is_remote_reference(reference):
                    continue

                target = (page_path.parent / unquote(urlsplit(reference).path)).resolve()
                with self.subTest(json=json_path.name, field=".".join(data_path), reference=reference):
                    self.assertTrue(target.is_file(), f"Missing local game asset: {target}")

    def test_local_game_image_extensions_match_file_signatures(self):
        for image_path in DOCS_ROOT.joinpath("games").rglob("*"):
            if not image_path.is_file() or image_path.suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg", ".gif"}:
                continue
            with self.subTest(image=image_path.relative_to(DOCS_ROOT)):
                self.assertTrue(
                    _has_matching_image_signature(image_path),
                    f"Image extension does not match payload: {image_path}",
                )

    def test_game_json_is_valid_utf8(self):
        for json_path, _, data in discover_game_sources():
            with self.subTest(json=json_path.name):
                self.assertIsInstance(data, dict)
                self.assertTrue(data.get("name"))
                self.assertIsInstance(data.get("guides"), list)
                json_path.read_text(encoding="utf-8")

    def test_landing_page_documents_real_public_features(self):
        index_html = (DOCS_ROOT / "index.html").read_text(encoding="utf-8")
        for command in (
            "/설정",
            "/도움",
            "/초대",
            "/무료게임",
            "/무료알림설정",
            "/패치알림설정",
            "/패치알림테스트",
            "/스팀인기게임",
            "/연삼통계",
        ):
            with self.subTest(command=command):
                self.assertIn(command, index_html)
        self.assertIn("일반 할인율 추적이 아니라", index_html)

    def test_pubg_canonical_name_and_korean_alias_are_consistent(self):
        json_path = DOCS_ROOT / "games" / "PUBG" / "PUBG.json"
        page_path = DOCS_ROOT / "games" / "PUBG.html"
        index_html = (DOCS_ROOT / "index.html").read_text(encoding="utf-8")
        data = json.loads(json_path.read_text(encoding="utf-8"))
        page_html = page_path.read_text(encoding="utf-8")

        self.assertEqual(data["name"], "PUBG BATTLE GROUND")
        self.assertEqual(data["aliases"], ["배그"])
        self.assertIn("<title>PUBG BATTLE GROUND</title>", page_html)
        self.assertIn("<strong>PUBG BATTLE GROUND</strong>", index_html)


if __name__ == "__main__":
    unittest.main()
