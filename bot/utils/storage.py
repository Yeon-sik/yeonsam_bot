import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_GUILD_CONFIG = {
    "welcome_message": "Welcome to {server}",
    "link": "",
    "welcome_channel_id": None,
}
GUILD_CONFIG_KEYS = frozenset(DEFAULT_GUILD_CONFIG)
_LOCK = threading.RLock()
_INITIALIZED = False


def _resolve_data_dir() -> Path:
    data_dir = os.getenv("BOT_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "config"


DATA_DIR = _resolve_data_dir()
LEGACY_FILE = DATA_DIR / "guild_config.json"
DB_FILE = DATA_DIR / "yeonsam.sqlite3"
# 기존 디버그 코드가 FILE을 참조하므로 SQLite 경로를 같은 이름으로 공개합니다.
FILE = DB_FILE


def _patch_subscription_store():
    """Return the extracted store over the same on-disk SQLite database."""
    from steam_discord_patch_alerts import SQLitePatchSubscriptionStore

    return SQLitePatchSubscriptionStore(DB_FILE)


@contextmanager
def _connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_storage() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    with _LOCK:
        if _INITIALIZED:
            return

        with _connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id TEXT PRIMARY KEY,
                    welcome_message TEXT NOT NULL,
                    link TEXT NOT NULL DEFAULT '',
                    welcome_channel_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS daily_metrics (
                    metric_date TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (metric_date, guild_id, metric_name)
                );

                CREATE TABLE IF NOT EXISTS patch_subscriptions (
                    guild_id TEXT NOT NULL,
                    game_slug TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    last_seen_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, game_slug)
                );

                CREATE TABLE IF NOT EXISTS free_game_alerts (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runtime_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            _migrate_legacy_json(connection)

        _INITIALIZED = True


def _migrate_legacy_json(connection: sqlite3.Connection) -> None:
    migration_key = "migration:legacy_guild_config_json"
    migrated = connection.execute(
        "SELECT state_value FROM runtime_state WHERE state_key = ?",
        (migration_key,),
    ).fetchone()
    if migrated:
        return
    if not LEGACY_FILE.exists():
        connection.execute(
            "INSERT INTO runtime_state (state_key, state_value, updated_at) VALUES (?, ?, ?)",
            (migration_key, "done", _utc_timestamp()),
        )
        return

    try:
        with LEGACY_FILE.open("r", encoding="utf-8") as file:
            legacy_data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(legacy_data, dict):
        return

    now = _utc_timestamp()
    for guild_id, raw_config in legacy_data.items():
        if not isinstance(raw_config, dict):
            continue
        config = {**DEFAULT_GUILD_CONFIG, **raw_config}
        connection.execute(
            """
            INSERT OR IGNORE INTO guild_settings (
                guild_id, welcome_message, link, welcome_channel_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(guild_id),
                str(config["welcome_message"]),
                str(config["link"]),
                _optional_id(config.get("welcome_channel_id")),
                now,
                now,
            ),
        )
    connection.execute(
        "INSERT INTO runtime_state (state_key, state_value, updated_at) VALUES (?, ?, ?)",
        (migration_key, "done", now),
    )


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _optional_id(value) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _row_to_config(row: sqlite3.Row | None) -> dict:
    if row is None:
        return dict(DEFAULT_GUILD_CONFIG)
    return {
        "welcome_message": row["welcome_message"],
        "link": row["link"],
        "welcome_channel_id": int(row["welcome_channel_id"])
        if row["welcome_channel_id"]
        else None,
    }


def load_data() -> dict:
    init_storage()
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT guild_id, welcome_message, link, welcome_channel_id
            FROM guild_settings
            ORDER BY guild_id
            """
        ).fetchall()
    return {row["guild_id"]: _row_to_config(row) for row in rows}


def save_data(data: dict) -> None:
    """기존 호출 호환용 전체 설정 upsert입니다. 기존 행을 삭제하지 않습니다."""
    init_storage()
    if not isinstance(data, dict):
        raise TypeError("data must be a dictionary")

    with _LOCK, _connect() as connection:
        now = _utc_timestamp()
        for guild_id, raw_config in data.items():
            if not isinstance(raw_config, dict):
                continue
            config = {**DEFAULT_GUILD_CONFIG, **raw_config}
            connection.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, welcome_message, link, welcome_channel_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    welcome_message = excluded.welcome_message,
                    link = excluded.link,
                    welcome_channel_id = excluded.welcome_channel_id,
                    updated_at = excluded.updated_at
                """,
                (
                    str(guild_id),
                    str(config["welcome_message"]),
                    str(config["link"]),
                    _optional_id(config.get("welcome_channel_id")),
                    now,
                    now,
                ),
            )


def get_guild(guild_id) -> dict:
    init_storage()
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT welcome_message, link, welcome_channel_id
            FROM guild_settings
            WHERE guild_id = ?
            """,
            (str(guild_id),),
        ).fetchone()
    return _row_to_config(row)


def ensure_guild(guild_id) -> dict:
    init_storage()
    now = _utc_timestamp()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO guild_settings (
                guild_id, welcome_message, link, welcome_channel_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(guild_id),
                DEFAULT_GUILD_CONFIG["welcome_message"],
                DEFAULT_GUILD_CONFIG["link"],
                None,
                now,
                now,
            ),
        )
    return get_guild(guild_id)


def update_guild(guild_id, key: str, value) -> dict:
    if key not in GUILD_CONFIG_KEYS:
        raise ValueError(f"Unsupported guild setting: {key}")

    ensure_guild(guild_id)
    normalized_value = _optional_id(value) if key == "welcome_channel_id" else str(value or "")
    with _LOCK, _connect() as connection:
        connection.execute(
            f"UPDATE guild_settings SET {key} = ?, updated_at = ? WHERE guild_id = ?",
            (normalized_value, _utc_timestamp(), str(guild_id)),
        )
    return get_guild(guild_id)


def record_metric(metric_name: str, guild_id=None, amount: int = 1) -> None:
    if not metric_name or amount == 0:
        return

    init_storage()
    metric_date = datetime.now(timezone.utc).date().isoformat()
    metric_guild_id = str(guild_id) if guild_id is not None else "global"
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO daily_metrics (
                metric_date, guild_id, metric_name, metric_value
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(metric_date, guild_id, metric_name) DO UPDATE SET
                metric_value = metric_value + excluded.metric_value
            """,
            (metric_date, metric_guild_id, metric_name, int(amount)),
        )


def get_metric_totals(days: int = 7, guild_id=None) -> dict[str, int]:
    init_storage()
    safe_days = max(1, min(int(days), 90))
    start_date = (
        datetime.now(timezone.utc).date() - timedelta(days=safe_days - 1)
    ).isoformat()
    params: list[str] = [start_date]
    guild_filter = ""
    if guild_id is not None:
        guild_filter = "AND guild_id = ?"
        params.append(str(guild_id))

    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT metric_name, SUM(metric_value) AS total
            FROM daily_metrics
            WHERE metric_date >= ? {guild_filter}
            GROUP BY metric_name
            ORDER BY metric_name
            """,
            params,
        ).fetchall()
    return {row["metric_name"]: int(row["total"]) for row in rows}


def upsert_patch_subscription(
    guild_id,
    game_slug: str,
    channel_id,
    last_seen_id: str | None = None,
) -> None:
    _patch_subscription_store().upsert(guild_id, game_slug, channel_id, last_seen_id)


def remove_patch_subscription(guild_id, game_slug: str) -> bool:
    return _patch_subscription_store().remove(guild_id, game_slug)


def list_patch_subscriptions(guild_id=None) -> list[dict]:
    return _patch_subscription_store().list(guild_id)


def update_patch_last_seen(guild_id, game_slug: str, last_seen_id: str) -> None:
    _patch_subscription_store().update_last_seen(guild_id, game_slug, last_seen_id)


def upsert_free_game_alert(guild_id, channel_id) -> None:
    init_storage()
    now = _utc_timestamp()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO free_game_alerts (
                guild_id, channel_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                updated_at = excluded.updated_at
            """,
            (str(guild_id), str(channel_id), now, now),
        )


def get_free_game_alert(guild_id) -> dict | None:
    init_storage()
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT guild_id, channel_id
            FROM free_game_alerts
            WHERE guild_id = ?
            """,
            (str(guild_id),),
        ).fetchone()
    if row is None:
        return None
    return {
        "guild_id": int(row["guild_id"]),
        "channel_id": int(row["channel_id"]),
    }


def list_free_game_alerts() -> list[dict]:
    init_storage()
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT guild_id, channel_id
            FROM free_game_alerts
            ORDER BY guild_id
            """
        ).fetchall()
    return [
        {
            "guild_id": int(row["guild_id"]),
            "channel_id": int(row["channel_id"]),
        }
        for row in rows
    ]


def remove_free_game_alert(guild_id) -> bool:
    init_storage()
    with _LOCK, _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM free_game_alerts WHERE guild_id = ?",
            (str(guild_id),),
        )
    return cursor.rowcount > 0


def get_runtime_state(state_key: str) -> str | None:
    init_storage()
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT state_value FROM runtime_state WHERE state_key = ?",
            (str(state_key),),
        ).fetchone()
    return row["state_value"] if row else None


def set_runtime_state(state_key: str, state_value: str) -> None:
    init_storage()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO runtime_state (state_key, state_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                state_value = excluded.state_value,
                updated_at = excluded.updated_at
            """,
            (str(state_key), str(state_value), _utc_timestamp()),
        )


def delete_guild_data(guild_id) -> None:
    init_storage()
    guild_id_text = str(guild_id)
    with _LOCK, _connect() as connection:
        connection.execute(
            "DELETE FROM free_game_alerts WHERE guild_id = ?",
            (guild_id_text,),
        )
        connection.execute(
            "DELETE FROM patch_subscriptions WHERE guild_id = ?",
            (guild_id_text,),
        )
        connection.execute(
            "DELETE FROM daily_metrics WHERE guild_id = ?",
            (guild_id_text,),
        )
        connection.execute(
            "DELETE FROM guild_settings WHERE guild_id = ?",
            (guild_id_text,),
        )
        connection.execute(
            "DELETE FROM runtime_state WHERE state_key = ?",
            (f"global_command_migration:{guild_id_text}",),
        )
