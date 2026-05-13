import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord
from discord.ext import commands

from cogs.welcome import WelcomeView
from utils.storage import ensure_guild


intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
initial_guild_sync_done = False


def build_invite_url(application_id: int) -> str:
    return (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={application_id}"
        "&scope=bot%20applications.commands"
        "&permissions=8"
    )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = os.getenv("PORT")
    if not port:
        return

    server = ThreadingHTTPServer(("0.0.0.0", int(port)), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


async def sync_guild_commands(guild: discord.Guild):
    ensure_guild(guild.id)
    # Push an empty guild command set first, then copy globals back in.
    # This forces Discord to drop any stale option schema from older versions.
    bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)

    bot.tree.clear_commands(guild=guild)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"[Guild Sync] {guild.name} ({guild.id}) -> {len(synced)} commands")
    return synced


@bot.event
async def on_ready():
    global initial_guild_sync_done

    app_info = await bot.application_info()
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print(f"Application: {app_info.name} ({app_info.id})")
    print(f"Invite URL: {build_invite_url(app_info.id)}")
    print(f"Guild count: {len(bot.guilds)}")
    for guild in bot.guilds:
        print(f"- {guild.name} ({guild.id})")

    if not initial_guild_sync_done:
        for guild in bot.guilds:
            await sync_guild_commands(guild)
        initial_guild_sync_done = True


@bot.event
async def on_guild_join(guild: discord.Guild):
    synced = await sync_guild_commands(guild)
    print(f"[Guild Join] Added to {guild.name} ({guild.id})")
    print(f"[Guild Join] Synced {len(synced)} commands for the guild.")


@bot.event
async def on_guild_available(guild: discord.Guild):
    print(f"[Guild Available] {guild.name} ({guild.id})")


@bot.event
async def on_guild_remove(guild: discord.Guild):
    print(f"[Guild Remove] {guild.name} ({guild.id})")


async def load_cogs():
    await bot.load_extension("cogs.yeonsam")
    await bot.load_extension("cogs.welcome")


@bot.event
async def setup_hook():
    await load_cogs()
    bot.add_view(WelcomeView())
    await bot.tree.sync()


async def main():
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("TOKEN environment variable is required.")

    start_health_server()

    async with bot:
        await bot.start(token)


asyncio.run(main())
