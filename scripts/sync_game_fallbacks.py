import argparse
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GAMES_ROOT = REPO_ROOT / "docs" / "games"
FALLBACK_PATTERN = re.compile(
    r'(?P<open><script\b[^>]*\bid=["\']game-data-fallback["\'][^>]*>)'
    r'(?P<payload>.*?)'
    r'(?P<close></script>)',
    re.DOTALL,
)


def discover_game_sources() -> list[tuple[Path, Path, dict]]:
    sources = []
    for json_path in sorted(GAMES_ROOT.glob("*/*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        page_name = Path(str(data.get("pagePath") or f"{json_path.stem}.html")).name
        sources.append((json_path, GAMES_ROOT / page_name, data))
    return sources


def read_inline_fallback(page_path: Path) -> dict:
    html = page_path.read_text(encoding="utf-8")
    match = FALLBACK_PATTERN.search(html)
    if not match:
        raise ValueError(f"inline fallback을 찾을 수 없습니다: {page_path}")
    return json.loads(match.group("payload"))


def synchronize_page(page_path: Path, data: dict) -> bool:
    html = page_path.read_text(encoding="utf-8")
    match = FALLBACK_PATTERN.search(html)
    if not match:
        raise ValueError(f"inline fallback을 찾을 수 없습니다: {page_path}")

    payload = match.group("payload")
    if json.loads(payload) == data:
        return False

    leading = payload[: len(payload) - len(payload.lstrip())]
    trailing = payload[len(payload.rstrip()) :]
    rendered = json.dumps(data, ensure_ascii=False, indent=4)
    replacement = f"{match.group('open')}{leading}{rendered}{trailing}{match.group('close')}"
    updated = f"{html[:match.start()]}{replacement}{html[match.end():]}"
    page_path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="게임 JSON과 HTML inline fallback의 의미상 동등성을 유지합니다."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="파일을 수정하지 않고 불일치가 있으면 실패합니다.",
    )
    args = parser.parse_args()

    mismatches = []
    for json_path, page_path, data in discover_game_sources():
        if not page_path.is_file():
            raise FileNotFoundError(f"게임 페이지가 없습니다: {page_path}")
        if read_inline_fallback(page_path) == data:
            continue
        mismatches.append((json_path, page_path, data))

    if args.check:
        if mismatches:
            for json_path, page_path, _ in mismatches:
                print(f"불일치: {json_path.relative_to(REPO_ROOT)} -> {page_path.relative_to(REPO_ROOT)}")
            return 1
        print(f"게임 fallback {len(discover_game_sources())}개 일치")
        return 0

    for _, page_path, data in mismatches:
        synchronize_page(page_path, data)
        print(f"동기화: {page_path.relative_to(REPO_ROOT)}")
    if not mismatches:
        print("동기화할 게임 fallback이 없습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
