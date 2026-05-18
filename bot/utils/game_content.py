import json
import re
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[2] / "docs" / "games"


def _normalize_slug(value: str) -> str:
    # 파일명/사용자 입력의 공백, 대소문자, 특수문자 차이를 없애 같은 게임으로 비교합니다.
    return re.sub(r"[^a-z0-9]", "", value.lower())


def list_games() -> list[str]:
    # docs/games/<게임>/<게임>.json 구조를 게임 카탈로그의 원천으로 사용합니다.
    return sorted(path.stem for path in DATA_ROOT.glob("*/*.json"))


def load_game_data(game: str) -> dict:
    # 슬래시 명령어 입력값과 실제 JSON 파일명을 느슨하게 매칭해 게임 데이터를 찾습니다.
    normalized_target = _normalize_slug(game)

    for path in DATA_ROOT.glob("*/*.json"):
        if _normalize_slug(path.stem) == normalized_target:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)

    raise FileNotFoundError(game)
