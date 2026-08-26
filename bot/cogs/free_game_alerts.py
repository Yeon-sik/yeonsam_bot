"""Automatic startup digest for limited-time paid games across platforms."""

import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.free_game_feed import (
    FreeGameFeedError,
    FreeGameOffer,
    build_free_game_digest,
    fetch_free_game_offers,
)
from utils.storage import (
    get_free_game_alert,
    list_free_game_alerts,
    record_metric,
    remove_free_game_alert,
    upsert_free_game_alert,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_FREE_GAME_POLL_INTERVAL_MINUTES = 360
EMBEDS_PER_MESSAGE = 10
OFFERS_PER_EMBED = 10


def free_game_poll_interval_minutes() -> int:
    raw_value = os.getenv(
        "FREE_GAME_POLL_INTERVAL_MINUTES",
        str(DEFAULT_FREE_GAME_POLL_INTERVAL_MINUTES),
    )
    try:
        interval = int(raw_value)
    except ValueError:
        interval = DEFAULT_FREE_GAME_POLL_INTERVAL_MINUTES
    return max(15, min(interval, 1440))


def is_guild_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


def free_game_channel_permission_error(channel: discord.TextChannel) -> str | None:
    bot_member = channel.guild.me
    if bot_member is None:
        return "봇의 서버 멤버 정보를 확인할 수 없습니다. 잠시 후 다시 시도하세요."

    permissions = channel.permissions_for(bot_member)
    missing = [
        label
        for attribute, label in (
            ("view_channel", "채널 보기"),
            ("send_messages", "메시지 보내기"),
            ("embed_links", "링크 임베드"),
        )
        if not getattr(permissions, attribute, False)
    ]
    if not missing:
        return None
    return f"{channel.mention}에서 다음 권한이 필요합니다: {', '.join(missing)}"


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def _offer_field_value(offer: FreeGameOffer) -> str:
    platform_label = " · ".join(offer.platforms) or "플랫폼 미상"
    worth_label = f"정가: {offer.worth}" if offer.worth else "정가 미상"
    if offer.ends_at is None:
        end_label = "종료 시각 미확인"
    else:
        unix_time = int(offer.ends_at.timestamp())
        end_label = f"종료: <t:{unix_time}:F> (<t:{unix_time}:R>)"
    return (
        f"플랫폼: {platform_label}\n{worth_label}\n{end_label}\n"
        f"[무료로 받기]({offer.claim_url})"
    )


def build_free_game_embeds(offers: list[FreeGameOffer]) -> list[discord.Embed]:
    if not offers:
        embed = discord.Embed(
            title="기간 한정 무료 게임",
            description=(
                "현재 [GamerPower](https://www.gamerpower.com/)에서 확인된 "
                "유료 게임의 기간 한정 무료 배포가 없습니다."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="출처: GamerPower")
        return [embed]

    page_count = (len(offers) + OFFERS_PER_EMBED - 1) // OFFERS_PER_EMBED
    embeds: list[discord.Embed] = []
    for page_index in range(page_count):
        start = page_index * OFFERS_PER_EMBED
        page_offers = offers[start : start + OFFERS_PER_EMBED]
        title = "기간 한정 무료 게임"
        if page_count > 1:
            title += f" ({page_index + 1}/{page_count})"
        embed = discord.Embed(
            title=title,
            description=(
                "[GamerPower](https://www.gamerpower.com/)에서 현재 활성으로 "
                "확인된 유료 게임의 기간 한정 무료 배포입니다. "
                "종료 전에 링크에서 조건을 다시 확인하세요."
            ),
            color=0x57F287,
        )
        for offer in page_offers:
            embed.add_field(
                name=_truncate(discord.utils.escape_markdown(offer.title), 256),
                value=_offer_field_value(offer),
                inline=False,
            )
        embed.set_footer(text=f"출처: GamerPower · 총 {len(offers)}개")
        embeds.append(embed)
    return embeds


async def send_free_game_embeds(
    destination,
    offers: list[FreeGameOffer],
    *,
    ephemeral: bool = False,
) -> None:
    embeds = build_free_game_embeds(offers)
    for index in range(0, len(embeds), EMBEDS_PER_MESSAGE):
        send_options = {
            "embeds": embeds[index : index + EMBEDS_PER_MESSAGE],
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        if ephemeral:
            send_options["ephemeral"] = True
        await destination.send(**send_options)


class FreeGameAlerts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Every process start intentionally sends one current digest. The map only
        # suppresses unchanged repeats while that process remains online.
        self._last_digest_by_guild: dict[int, str] = {}
        self._poll_lock = asyncio.Lock()
        self.free_game_poll_loop.change_interval(
            minutes=free_game_poll_interval_minutes()
        )

    async def cog_load(self):
        self.free_game_poll_loop.start()

    async def cog_unload(self):
        self.free_game_poll_loop.cancel()

    async def _fetch_offers(self) -> list[FreeGameOffer]:
        return await asyncio.to_thread(fetch_free_game_offers)

    async def _send_to_subscription(
        self,
        subscription: dict,
        offers: list[FreeGameOffer],
    ) -> None:
        channel = self.bot.get_channel(subscription["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            raise LookupError("Configured free-game alert channel is unavailable")
        await send_free_game_embeds(channel, offers)

    async def _poll_subscriptions(
        self,
        subscriptions: list[dict],
        *,
        force: bool = False,
    ) -> set[int]:
        if not subscriptions:
            return set()

        async with self._poll_lock:
            try:
                offers = await self._fetch_offers()
            except FreeGameFeedError:
                LOGGER.exception("Failed to fetch GamerPower free-game feed")
                for subscription in subscriptions:
                    record_metric("free_game_poll_failed", subscription["guild_id"])
                return set()
            except Exception:
                LOGGER.exception("Unexpected free-game polling failure")
                for subscription in subscriptions:
                    record_metric("free_game_poll_failed", subscription["guild_id"])
                return set()

            digest = build_free_game_digest(offers)
            delivered_guilds: set[int] = set()
            for subscription in subscriptions:
                guild_id = subscription["guild_id"]
                if not force and self._last_digest_by_guild.get(guild_id) == digest:
                    continue
                try:
                    await self._send_to_subscription(subscription, offers)
                except LookupError:
                    LOGGER.warning(
                        "Free-game alert channel unavailable guild_id=%s channel_id=%s",
                        guild_id,
                        subscription["channel_id"],
                    )
                    record_metric("free_game_channel_missing", guild_id)
                    continue
                except discord.HTTPException:
                    LOGGER.exception(
                        "Failed to deliver free-game digest guild_id=%s", guild_id
                    )
                    record_metric("free_game_delivery_failed", guild_id)
                    continue

                self._last_digest_by_guild[guild_id] = digest
                delivered_guilds.add(guild_id)
                record_metric("free_game_digest_sent", guild_id)
            return delivered_guilds

    @app_commands.command(
        name="무료알림설정",
        description="여러 플랫폼의 기간 한정 무료 게임 목록을 보낼 채널을 설정합니다.",
    )
    @app_commands.describe(channel="무료 게임 목록을 받을 채널")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def configure_alert(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 무료 게임 알림을 설정할 수 있습니다.",
                ephemeral=True,
            )
            return

        permission_error = free_game_channel_permission_error(channel)
        if permission_error:
            await interaction.response.send_message(permission_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_id = interaction.guild.id
        upsert_free_game_alert(guild_id, channel.id)
        record_metric("free_game_subscription_created", guild_id)
        delivered = await self._poll_subscriptions(
            [{"guild_id": guild_id, "channel_id": channel.id}],
            force=True,
        )
        if guild_id in delivered:
            message = (
                f"무료 게임 알림을 {channel.mention}에 설정하고 현재 목록을 보냈습니다."
            )
        else:
            message = (
                f"무료 게임 알림 채널은 {channel.mention}에 저장했습니다. "
                "현재 목록 전송은 실패했으며 다음 자동 검사에서 다시 시도합니다."
            )
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(
        name="무료알림해제",
        description="이 서버의 기간 한정 무료 게임 자동 알림을 해제합니다.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def remove_alert(self, interaction: discord.Interaction):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 무료 게임 알림을 해제할 수 있습니다.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        removed = remove_free_game_alert(guild_id)
        self._last_digest_by_guild.pop(guild_id, None)
        if removed:
            record_metric("free_game_subscription_removed", guild_id)
        message = (
            "무료 게임 자동 알림을 해제했습니다."
            if removed
            else "이 서버에는 설정된 무료 게임 알림이 없습니다."
        )
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(
        name="무료알림상태",
        description="이 서버의 기간 한정 무료 게임 알림 채널을 확인합니다.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def alert_status(self, interaction: discord.Interaction):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 무료 게임 알림 상태를 확인할 수 있습니다.",
                ephemeral=True,
            )
            return

        subscription = get_free_game_alert(interaction.guild.id)
        if subscription is None:
            message = "설정된 무료 게임 알림 채널이 없습니다."
        else:
            channel = interaction.guild.get_channel(subscription["channel_id"])
            message = (
                f"무료 게임 알림 채널: {channel.mention}"
                if isinstance(channel, discord.TextChannel)
                else "설정된 채널을 찾을 수 없습니다. 알림 채널을 다시 설정하세요."
            )
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(
        name="무료게임",
        description="현재 확인된 여러 플랫폼의 기간 한정 무료 게임을 조회합니다.",
    )
    @app_commands.guild_only()
    async def list_current_offers(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            offers = await self._fetch_offers()
        except FreeGameFeedError:
            LOGGER.exception("Failed to fetch GamerPower feed for manual command")
            record_metric("free_game_manual_failed", interaction.guild.id)
            await interaction.followup.send(
                "무료 게임 목록을 불러오지 못했습니다. 잠시 후 다시 시도하세요.",
                ephemeral=True,
            )
            return

        await send_free_game_embeds(interaction.followup, offers, ephemeral=True)
        record_metric("free_game_manual_viewed", interaction.guild.id)

    @tasks.loop(minutes=DEFAULT_FREE_GAME_POLL_INTERVAL_MINUTES)
    async def free_game_poll_loop(self):
        await self._poll_subscriptions(list_free_game_alerts())

    @free_game_poll_loop.before_loop
    async def before_free_game_poll(self):
        await self.bot.wait_until_ready()

    @free_game_poll_loop.error
    async def free_game_poll_error(self, error: Exception):
        LOGGER.exception(
            "Free-game polling loop stopped unexpectedly",
            exc_info=(type(error), error, error.__traceback__),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(FreeGameAlerts(bot))


__all__ = [
    "FreeGameAlerts",
    "build_free_game_embeds",
    "free_game_channel_permission_error",
    "free_game_poll_interval_minutes",
    "send_free_game_embeds",
    "setup",
]
