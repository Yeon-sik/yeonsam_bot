import json
import os
from pathlib import Path


def _resolve_file() -> Path:
    # 배포 환경에서는 BOT_DATA_DIR을 우선 사용하고, 로컬에서는 저장소 안의 기본 설정 파일을 씁니다.
    data_dir = os.getenv("BOT_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser().resolve() / "guild_config.json"

    return Path(__file__).resolve().parent.parent / "config" / "guild_config.json"


FILE = _resolve_file()


def load_data():
    # 설정 파일이 아직 없으면 빈 설정으로 시작해 첫 저장 시 파일을 생성합니다.
    if not FILE.exists():
        return {}
    with FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    # 상위 디렉터리를 먼저 만든 뒤 한글 메시지가 깨지지 않도록 UTF-8 JSON으로 저장합니다.
    FILE.parent.mkdir(parents=True, exist_ok=True)
    with FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_guild(guild_id):
    # 길드별 설정이 없을 때도 명령어가 동작하도록 기본 환영 문구를 반환합니다.
    data = load_data()
    return data.get(
        str(guild_id),
        {
            "welcome_message": "Welcome to {server}",
            "link": "",
        },
    )


def ensure_guild(guild_id):
    # 봇이 새 길드에 들어갔을 때 기본 설정을 실제 파일에 기록합니다.
    data = load_data()
    gid = str(guild_id)

    if gid not in data:
        data[gid] = {
            "welcome_message": "Welcome to {server}",
            "link": "",
        }
        save_data(data)

    return data[gid]


def update_guild(guild_id, key, value):
    # 모달에서 수정한 단일 설정 값을 기존 길드 설정에 병합해 저장합니다.
    data = load_data()
    gid = str(guild_id)

    if gid not in data:
        data[gid] = {}

    data[gid][key] = value
    save_data(data)
