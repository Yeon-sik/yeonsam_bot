import json
import os
from pathlib import Path


def _resolve_file() -> Path:
    data_dir = os.getenv("BOT_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser().resolve() / "guild_config.json"

    return Path(__file__).resolve().parent.parent / "config" / "guild_config.json"


FILE = _resolve_file()


def load_data():
    if not FILE.exists():
        return {}
    with FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    with FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_guild(guild_id):
    data = load_data()
    return data.get(
        str(guild_id),
        {
            "welcome_message": "Welcome to {server}",
            "link": "",
        },
    )


def ensure_guild(guild_id):
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
    data = load_data()
    gid = str(guild_id)

    if gid not in data:
        data[gid] = {}

    data[gid][key] = value
    save_data(data)
