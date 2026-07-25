import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.patch_feed import (
    PatchArticle,
    PatchFeedError,
    fetch_patch_articles,
    find_new_articles,
    load_patch_sources,
)
from utils.storage import (
    list_patch_subscriptions,
    record_metric,
    remove_patch_subscription,
    update_patch_last_seen,
    upsert_patch_subscription,
)


LOGGER = logging.getLogger(__name__)
PATCH_SOURCES = load_patch_sources()
GAME_CHOICES = [
    app_commands.Choice(name=source["name"], value=slug)
    for slug, source in PATCH_SOURCES.items()
]


def is_guild_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


def patch_poll_interval_minutes() -> int:
    raw_value = os.getenv("PATCH_POLL_INTERVAL_MINUTES", "30")
    try:
        value = int(raw_value)
    except ValueError:
        return 30
    return max(5, min(value, 1440))


def build_patch_embed(game_name: str, article: PatchArticle) -> discord.Embed:
    published_at = datetime.fromtimestamp(article.published_at, tz=timezone.utc)
    embed = discord.Embed(
        title=article.title,
        url=article.url,
        description=article.summary or "새 공식 업데이트가 등록되었습니다.",
        color=0x57F287,
        timestamp=published_at,
    )
    embed.set_author(name=f"{game_name} 패치·업데이트")
    if article.author:
        embed.set_footer(text=f"Steam 공식 소식 · {article.author}")
    else:
        embed.set_footer(text="Steam 공식 소식")
    return embed


def channel_permission_error(channel: discord.TextChannel) -> str | None:
    bot_member = channel.guild.me
    if bot_member is None:
        return "봇 멤버 정보를 확인할 수 없습니다."
    permissions = channel.permissions_for(bot_member)
    missing = []
    if not permissions.view_channel:
        missing.append("채널 보기")
    if not permissions.send_messages:
        missing.append("메시지 보내기")
    if not permissions.embed_links:
        missing.append("링크 임베드")
    if missing:
        return f"다음 권한이 필요합니다: {', '.join(missing)}"
    return None


class PatchAlerts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.patch_poll_loop.change_interval(minutes=patch_poll_interval_minutes())

    async def cog_load(self):
        self.patch_poll_loop.start()

    async def cog_unload(self):
        self.patch_poll_loop.cancel()

    async def fetch_articles(self, game_slug: str) -> list[PatchArticle]:
        source = PATCH_SOURCES[game_slug]
        return await asyncio.to_thread(fetch_patch_articles, source)

    @app_commands.command(
        name="패치알림설정",
        description="게임의 공식 패치·업데이트 소식을 지정 채널에 자동으로 알립니다.",
    )
    @app_commands.describe(game="알림을 받을 게임", channel="알림을 보낼 채널")
    @app_commands.choices(game=GAME_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def configure_alert(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 이 명령어를 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        permission_error = channel_permission_error(channel)
        if permission_error:
            await interaction.response.send_message(permission_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        last_seen_id = None
        warning = ""
        try:
            articles = await self.fetch_articles(game.value)
            if articles:
                last_seen_id = articles[0].article_id
            else:
                warning = "\n현재 피드에 소식이 없어 다음 업데이트부터 감지합니다."
        except PatchFeedError:
            LOGGER.exception("Failed to seed patch feed for %s", game.value)
            warning = "\n현재 Steam 피드 확인에 실패했지만 설정은 저장했습니다."

        upsert_patch_subscription(
            interaction.guild.id,
            game.value,
            channel.id,
            last_seen_id=last_seen_id,
        )
        record_metric("patch_subscription_created", interaction.guild.id)
        await interaction.followup.send(
            f"**{game.name}** 패치·업데이트 알림을 {channel.mention}에 설정했습니다."
            f"{warning}",
            ephemeral=True,
        )

    @app_commands.command(
        name="패치알림해제",
        description="게임의 자동 패치·업데이트 알림을 해제합니다.",
    )
    @app_commands.describe(game="알림을 해제할 게임")
    @app_commands.choices(game=GAME_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def remove_alert(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
    ):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 이 명령어를 사용할 수 있습니다.",
                ephemeral=True,
            )
            return
        removed = remove_patch_subscription(interaction.guild.id, game.value)
        if removed:
            record_metric("patch_subscription_removed", interaction.guild.id)
        await interaction.response.send_message(
            (
                f"**{game.name}** 알림을 해제했습니다."
                if removed
                else f"**{game.name}**에 설정된 알림이 없습니다."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="패치알림목록",
        description="현재 서버의 패치·업데이트 알림 설정을 확인합니다.",
    )
    @app_commands.default_permissions(administrator=True)
    async def list_alerts(self, interaction: discord.Interaction):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 이 명령어를 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        subscriptions = list_patch_subscriptions(interaction.guild.id)
        embed = discord.Embed(title="패치·업데이트 자동 알림", color=0x5865F2)
        if not subscriptions:
            embed.description = "`/패치알림설정`으로 게임과 채널을 지정하세요."
        else:
            lines = []
            for subscription in subscriptions:
                source = PATCH_SOURCES.get(subscription["game_slug"], {})
                game_name = source.get("name", subscription["game_slug"])
                channel = interaction.guild.get_channel(subscription["channel_id"])
                channel_label = channel.mention if channel else "삭제되었거나 접근할 수 없는 채널"
                lines.append(f"- **{game_name}** → {channel_label}")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="패치알림테스트",
        description="현재 최신 공식 업데이트를 지정된 알림 채널에 테스트 발송합니다.",
    )
    @app_commands.describe(game="테스트할 게임")
    @app_commands.choices(game=GAME_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def test_alert(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
    ):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 이 명령어를 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        subscription = next(
            (
                item
                for item in list_patch_subscriptions(interaction.guild.id)
                if item["game_slug"] == game.value
            ),
            None,
        )
        if subscription is None:
            await interaction.response.send_message(
                "먼저 `/패치알림설정`으로 알림 채널을 지정하세요.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(subscription["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "설정된 채널을 찾을 수 없습니다. 알림을 다시 설정하세요.",
                ephemeral=True,
            )
            return

        permission_error = channel_permission_error(channel)
        if permission_error:
            await interaction.response.send_message(permission_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            articles = await self.fetch_articles(game.value)
        except PatchFeedError:
            LOGGER.exception("Failed to fetch patch feed test for %s", game.value)
            await interaction.followup.send(
                "Steam 공식 업데이트 피드를 불러오지 못했습니다. 잠시 후 다시 시도하세요.",
                ephemeral=True,
            )
            return

        if not articles:
            await interaction.followup.send(
                "현재 발송할 공식 업데이트가 없습니다.",
                ephemeral=True,
            )
            return

        await channel.send(
            embed=build_patch_embed(game.name, articles[0]),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        record_metric("patch_test_sent", interaction.guild.id)
        await interaction.followup.send(
            f"{channel.mention}에 최신 업데이트를 테스트 발송했습니다.",
            ephemeral=True,
        )

    @tasks.loop(minutes=30)
    async def patch_poll_loop(self):
        subscriptions_by_game: dict[str, list[dict]] = defaultdict(list)
        for subscription in list_patch_subscriptions():
            if subscription["game_slug"] in PATCH_SOURCES:
                subscriptions_by_game[subscription["game_slug"]].append(subscription)

        for game_slug, subscriptions in subscriptions_by_game.items():
            try:
                articles = await self.fetch_articles(game_slug)
            except PatchFeedError:
                LOGGER.exception("Failed to poll patch feed for %s", game_slug)
                for subscription in subscriptions:
                    record_metric("patch_poll_failed", subscription["guild_id"])
                continue

            if not articles:
                continue

            source = PATCH_SOURCES[game_slug]
            article_ids = {article.article_id for article in articles}
            newest_id = articles[0].article_id
            for subscription in subscriptions:
                last_seen_id = subscription["last_seen_id"]
                if not last_seen_id or last_seen_id not in article_ids:
                    update_patch_last_seen(
                        subscription["guild_id"],
                        game_slug,
                        newest_id,
                    )
                    if last_seen_id:
                        record_metric(
                            "patch_cursor_resynced",
                            subscription["guild_id"],
                        )
                    continue

                new_articles = find_new_articles(articles, last_seen_id)
                if not new_articles:
                    continue

                channel = self.bot.get_channel(subscription["channel_id"])
                if not isinstance(channel, discord.TextChannel):
                    record_metric("patch_channel_missing", subscription["guild_id"])
                    continue

                delivered_id = last_seen_id
                for article in new_articles:
                    try:
                        await channel.send(
                            embed=build_patch_embed(source["name"], article),
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    except discord.HTTPException:
                        LOGGER.exception(
                            "Failed to deliver patch alert for guild %s and game %s",
                            subscription["guild_id"],
                            game_slug,
                        )
                        record_metric(
                            "patch_delivery_failed",
                            subscription["guild_id"],
                        )
                        break
                    delivered_id = article.article_id
                    record_metric("patch_alert_sent", subscription["guild_id"])

                if delivered_id != last_seen_id:
                    update_patch_last_seen(
                        subscription["guild_id"],
                        game_slug,
                        delivered_id,
                    )

    @patch_poll_loop.before_loop
    async def before_patch_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PatchAlerts(bot))
