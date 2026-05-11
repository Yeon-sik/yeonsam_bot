import json
import re
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[2] / "docs" / "games"


def _normalize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def list_games() -> list[str]:
    return sorted(path.stem for path in DATA_ROOT.glob("*/*.json"))


def load_game_data(game: str) -> dict:
    normalized_target = _normalize_slug(game)

    for path in DATA_ROOT.glob("*/*.json"):
        if _normalize_slug(path.stem) == normalized_target:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)

    raise FileNotFoundError(game)
