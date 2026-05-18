import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord
from discord.ext import commands

from cogs.welcome import WelcomeView
from utils.storage import ensure_guild


# 멤버 입장 이벤트와 닉네임 변경 기능을 쓰기 위해 members intent를 켭니다.
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
initial_guild_sync_done = False


def build_invite_url(application_id: int) -> str:
    # 관리자 권한으로 봇과 슬래시 명령어를 함께 초대하는 URL을 만듭니다.
    return (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={application_id}"
        "&scope=bot%20applications.commands"
        "&permissions=8"
    )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 호스팅 플랫폼의 헬스 체크가 봇 프로세스 생존 여부를 확인하는 경로입니다.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

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
    # 길드별 설정 파일을 먼저 보장한 뒤, 슬래시 명령어 스키마를 최신 상태로 맞춥니다.
    ensure_guild(guild.id)
    # 먼저 길드 명령어를 비운 뒤 전역 명령어를 복사하면 오래된 옵션 스키마가 남지 않습니다.
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

    # 재접속 때마다 중복 동기화하지 않도록 첫 ready 이벤트에서만 전체 길드를 동기화합니다.
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
    # 기능 단위 Cog를 등록해 명령어와 이벤트 리스너를 분리합니다.
    await bot.load_extension("cogs.yeonsam")
    await bot.load_extension("cogs.welcome")


@bot.event
async def setup_hook():
    # 봇 시작 직후 Cog와 persistent view를 등록하고 전역 명령어를 동기화합니다.
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


asyncio.run(main())
