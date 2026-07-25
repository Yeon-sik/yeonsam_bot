"""Yeonsam Bot adapter for the standalone steam-discord-patch-alerts package."""

import os
from pathlib import Path

# Keep the existing bot-specific source file and slash-command choices intact.
os.environ.setdefault(
    "PATCH_ALERT_SOURCES_FILE",
    str(Path(__file__).resolve().parent.parent / "config" / "patch_sources.json"),
)

from steam_discord_patch_alerts.discord_bot import (
    DiscordPatchAlerts as PatchAlerts,
    GAME_CHOICES,
    PATCH_SOURCES,
    build_patch_embed,
    channel_permission_error,
    patch_poll_interval_minutes,
    setup as setup_discord_patch_alerts,
)

from utils.storage import DB_FILE, record_metric


async def setup(bot):
    """Register the extracted Discord Cog against Yeonsam's existing SQLite file."""
    await setup_discord_patch_alerts(
        bot,
        database_path=DB_FILE,
        metric_recorder=record_metric,
    )


__all__ = [
    "GAME_CHOICES",
    "PATCH_SOURCES",
    "PatchAlerts",
    "build_patch_embed",
    "channel_permission_error",
    "patch_poll_interval_minutes",
    "setup",
]
