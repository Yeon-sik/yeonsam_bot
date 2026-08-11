import asyncio
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord
from discord import app_commands
from discord.ext import commands

from cogs.welcome import WelcomeView
from utils.invite import build_invite_url
from utils.storage import (
    delete_guild_data,
    ensure_guild,
    get_runtime_state,
    init_storage,
    record_metric,
    set_runtime_state,
)


# 멤버 입장 이벤트와 닉네임 변경 기능을 쓰기 위해 members intent를 켭니다.
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
initial_guild_sync_done = False
HEALTH_STATE = {"ready": False}
LOGGER = logging.getLogger("yeonsam")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_response(404)
            self.end_headers()
            return

        payload = json.dumps(
            {
                "status": "ok" if HEALTH_STATE["ready"] else "starting",
                "ready": HEALTH_STATE["ready"],
            }
        ).encode("utf-8")
        self.send_response(200 if HEALTH_STATE["ready"] else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


def start_health_server():
    # PORT가 주어진 배포 환경에서만 별도 스레드로 간단한 HTTP 헬스 서버를 띄웁니다.
    port = os.getenv("PORT")
    if not port:
        return

    server = ThreadingHTTPServer(("0.0.0.0", int(port)), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


async def sync_guild_commands(guild: discord.Guild):
    ensure_guild(guild.id)
    # 개발 환경에서만 길드 명령 동기화를 사용합니다. 운영은 전역 명령을 한 번만 동기화합니다.
    bot.tree.clear_commands(guild=guild)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    LOGGER.info(
        "Guild command sync completed guild_id=%s command_count=%s",
        guild.id,
        len(synced),
    )
    return synced


def guild_sync_enabled() -> bool:
    return os.getenv("SYNC_GUILD_COMMANDS", "").strip().lower() in {"1", "true", "yes"}


async def migrate_legacy_guild_commands(guild: discord.Guild) -> None:
    state_key = f"global_command_migration:{guild.id}"
    if get_runtime_state(state_key) == "done":
        return
    # 이전 버전이 복사한 길드 전용 명령을 한 번만 제거해 전역 명령 스키마를 사용하게 합니다.
    bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)
    set_runtime_state(state_key, "done")
    LOGGER.info("Legacy guild commands cleared guild_id=%s", guild.id)


@bot.event
async def on_ready():
    global initial_guild_sync_done

    app_info = await bot.application_info()
    HEALTH_STATE["ready"] = True
    LOGGER.info(
        "Bot ready bot_id=%s application_id=%s guild_count=%s invite_url=%s",
        bot.user.id,
        app_info.id,
        len(bot.guilds),
        build_invite_url(app_info.id),
    )

    if not initial_guild_sync_done:
        for guild in bot.guilds:
            ensure_guild(guild.id)
            if guild_sync_enabled():
                await sync_guild_commands(guild)
            else:
                await migrate_legacy_guild_commands(guild)
        initial_guild_sync_done = True


@bot.event
async def on_disconnect():
    HEALTH_STATE["ready"] = False


@bot.event
async def on_guild_join(guild: discord.Guild):
    ensure_guild(guild.id)
    record_metric("guild_joined", guild.id)
    if guild_sync_enabled():
        await sync_guild_commands(guild)
    LOGGER.info("Joined guild guild_id=%s guild_name=%s", guild.id, guild.name)


@bot.event
async def on_guild_available(guild: discord.Guild):
    LOGGER.info("Guild available guild_id=%s", guild.id)


@bot.event
async def on_guild_remove(guild: discord.Guild):
    record_metric("guild_removed")
    delete_guild_data(guild.id)
    LOGGER.info("Removed from guild guild_id=%s guild_name=%s", guild.id, guild.name)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    guild_id = interaction.guild.id if interaction.guild else None
    record_metric("app_command_error", guild_id)
    command_name = (
        getattr(interaction.command, "qualified_name", interaction.command.name)
        if interaction.command
        else "unknown"
    )
    LOGGER.error(
        "Application command failed command=%s guild_id=%s",
        command_name,
        guild_id,
        exc_info=(type(error), error, error.__traceback__),
    )
    message = "명령어 처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.event
async def on_app_command_completion(
    interaction: discord.Interaction,
    command: app_commands.Command | app_commands.ContextMenu,
):
    guild_id = interaction.guild.id if interaction.guild else None
    command_name = getattr(command, "qualified_name", command.name)
    record_metric(f"command_used:{command_name}", guild_id)


async def load_cogs():
    # 기능 단위 Cog를 등록해 명령어와 이벤트 리스너를 분리합니다.
    await bot.load_extension("cogs.yeonsam")
    await bot.load_extension("cogs.welcome")
    await bot.load_extension("cogs.settings")
    await bot.load_extension("cogs.patch_alerts")
    await bot.load_extension("cogs.free_game_alerts")


@bot.event
async def setup_hook():
    # 봇 시작 직후 Cog와 persistent view를 등록하고 전역 명령어를 동기화합니다.
    init_storage()
    await load_cogs()
    bot.add_view(WelcomeView())
    await bot.tree.sync()


async def main():
    # TOKEN은 배포 환경 변수로만 받습니다. 누락되면 조용히 실패하지 않고 바로 중단합니다.
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("TOKEN environment variable is required.")

    start_health_server()

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(main())
