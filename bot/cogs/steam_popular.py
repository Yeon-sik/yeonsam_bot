"""Discord command for Steam's public Most Played chart."""

from datetime import datetime, timezone
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.steam_popular import (
    STEAM_MOST_PLAYED_URL,
    SteamPopularError,
    SteamPopularGame,
    SteamPopularService,
    SteamPopularSnapshot,
)
from utils.storage import record_metric


LOGGER = logging.getLogger(__name__)
STEAM_COLOR = 0x1B2838
SOURCE_DELAY_WARNING_SECONDS = 3 * 24 * 60 * 60
RESULT_CHOICES = [
    app_commands.Choice(name="TOP 5", value=5),
    app_commands.Choice(name="TOP 10", value=10),
]


def format_rank_change(game: SteamPopularGame) -> str:
    previous = game.last_week_rank
    if previous is None:
        return "신규 진입"
    if previous == game.rank:
        return "지난주와 동일"
    if previous > game.rank:
        return f"지난주 대비 ▲ {previous - game.rank}"
    return f"지난주 대비 ▼ {game.rank - previous}"


def build_popular_embed(snapshot: SteamPopularSnapshot) -> discord.Embed:
    lines: list[str] = []
    for game in snapshot.games:
        name = discord.utils.escape_markdown(game.name)
        lines.append(
            f"**{game.rank}. [{name}]({game.store_url})**\n"
            f"최근 최고 `{game.peak_players:,}명` · {format_rank_change(game)}"
        )

    rollup_date = datetime.fromtimestamp(
        snapshot.rollup_timestamp,
        tz=timezone.utc,
    ).strftime("%Y-%m-%d")
    notices: list[str] = []
    if snapshot.stale_cache:
        notices.append("⚠️ Steam 최신 조회에 실패해 마지막 정상 결과를 표시합니다.")
    if snapshot.fetched_timestamp - snapshot.rollup_timestamp > SOURCE_DELAY_WARNING_SECONDS:
        notices.append("⚠️ Steam 원본의 집계일이 현재 조회 시점보다 오래되었습니다.")
    notice_text = f"\n{' '.join(notices)}" if notices else ""
    embed = discord.Embed(
        title=f"Steam 인기 게임 TOP {len(snapshot.games)}",
        url=STEAM_MOST_PLAYED_URL,
        description=(
            "Steam 공식 Most Played 순위입니다. 숫자는 실시간 접속자가 아닌 "
            f"각 게임의 최근 최고 동시 접속자입니다.{notice_text}\n\n"
            + "\n\n".join(lines)
        ),
        color=STEAM_COLOR,
    )
    embed.set_footer(text=f"Steam 공식 차트 · 집계 기준 {rollup_date} UTC")
    first_image = next((game.header_image for game in snapshot.games if game.header_image), None)
    if first_image:
        embed.set_thumbnail(url=first_image)
    return embed


class SteamPopular(commands.Cog):
    def __init__(self, bot, service: SteamPopularService | None = None):
        self.bot = bot
        self.service = service or SteamPopularService()

    @app_commands.command(
        name="스팀인기게임",
        description="Steam 공식 Most Played 인기 게임 순위를 확인합니다.",
    )
    @app_commands.describe(count="한 번에 표시할 순위 개수입니다.")
    @app_commands.rename(count="표시개수")
    @app_commands.choices(count=RESULT_CHOICES)
    async def popular_games(
        self,
        interaction: discord.Interaction,
        count: int = 10,
    ):
        await interaction.response.defer(thinking=True)
        try:
            snapshot = await self.service.get_snapshot(count)
        except SteamPopularError:
            guild_id = interaction.guild.id if interaction.guild else None
            record_metric("steam_popular_unavailable", guild_id)
            LOGGER.warning("Steam popular chart is unavailable", exc_info=True)
            await interaction.followup.send(
                "Steam 인기 게임 순위를 불러오지 못했습니다. 잠시 후 다시 시도하세요."
            )
            return

        await interaction.followup.send(embed=build_popular_embed(snapshot))


async def setup(bot):
    await bot.add_cog(SteamPopular(bot))
