import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAMES_ROOT = ROOT / "docs" / "games"
FALLBACK_TAG = '<script id="game-data-fallback" type="application/json">'


def sync_game_fallback(game_name: str) -> Path:
    json_path = GAMES_ROOT / game_name / f"{game_name}.json"
    html_path = GAMES_ROOT / f"{game_name}.html"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")
    tag_start = html.index(FALLBACK_TAG)
    content_start = tag_start + len(FALLBACK_TAG)
    content_end = html.index("</script>", content_start)
    line_start = html.rfind("\n", 0, tag_start) + 1
    indent = html[line_start:tag_start]

    payload = json.dumps(data, ensure_ascii=False, indent=4)
    updated = (
        html[:content_start]
        + "\n"
        + payload
        + "\n"
        + indent
        + html[content_end:]
    )
    html_path.write_text(updated, encoding="utf-8")
    return html_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy canonical game JSON into each HTML file's offline fallback block."
    )
    parser.add_argument(
        "games",
        nargs="*",
        help="Game folder names. Defaults to every docs/games/<name>/<name>.json pair.",
    )
    args = parser.parse_args()

    games = args.games or sorted(path.name for path in GAMES_ROOT.iterdir() if path.is_dir())
    for game_name in games:
        json_path = GAMES_ROOT / game_name / f"{game_name}.json"
        html_path = GAMES_ROOT / f"{game_name}.html"
        if not json_path.is_file() or not html_path.is_file():
            continue
        synced_path = sync_game_fallback(game_name)
        print(synced_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
