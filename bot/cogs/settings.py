import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.welcome import WelcomeView
from utils.invite import build_invite_url
from utils.storage import (
    ensure_guild,
    get_guild,
    get_metric_totals,
    record_metric,
    update_guild,
)
from utils.welcome_message import build_welcome_embed
from utils.validation import is_http_url


LOGGER = logging.getLogger(__name__)
REQUIRED_CHANNEL_PERMISSIONS = (
    ("view_channel", "채널 보기"),
    ("send_messages", "메시지 보내기"),
    ("embed_links", "링크 임베드"),
    ("attach_files", "파일 첨부"),
)


def is_guild_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


def resolve_welcome_channel(guild: discord.Guild, config: dict):
    channel_id = config.get("welcome_channel_id")
    if channel_id:
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            return channel
    if isinstance(guild.system_channel, discord.TextChannel):
        return guild.system_channel
    return None


def missing_channel_permissions(channel: discord.TextChannel) -> list[str]:
    bot_member = channel.guild.me
    if bot_member is None:
        return ["봇 멤버 정보"]
    permissions = channel.permissions_for(bot_member)
    return [
        label
        for attribute, label in REQUIRED_CHANNEL_PERMISSIONS
        if not getattr(permissions, attribute, False)
    ]


def build_setup_embed(guild: discord.Guild) -> discord.Embed:
    config = get_guild(guild.id)
    channel = resolve_welcome_channel(guild, config)
    embed = discord.Embed(
        title="연삼이 초기 설정",
        description=(
            "아래 순서로 설정하면 바로 사용할 수 있습니다.\n"
            "1. 환영 채널 선택\n"
            "2. 환영 문구와 안내 링크 입력\n"
            "3. 권한 진단 후 테스트 발송"
        ),
        color=0x5865F2,
    )
    embed.add_field(
        name="환영 채널",
        value=channel.mention if channel else "설정되지 않음",
        inline=False,
    )
    embed.add_field(
        name="환영 문구",
        value=config["welcome_message"][:1024],
        inline=False,
    )
    embed.add_field(
        name="안내 링크",
        value=config["link"] or "설정되지 않음",
        inline=False,
    )
    return embed


def build_permission_embed(guild: discord.Guild) -> discord.Embed:
    config = get_guild(guild.id)
    channel = resolve_welcome_channel(guild, config)
    bot_member = guild.me
    embed = discord.Embed(title="연삼이 권한 진단", color=0x57F287)

    if channel is None:
        embed.color = 0xED4245
        embed.description = "환영 채널을 찾을 수 없습니다. 먼저 채널을 선택하세요."
        return embed

    missing = missing_channel_permissions(channel)
    embed.add_field(name="확인 채널", value=channel.mention, inline=False)
    embed.add_field(
        name="메시지 권한",
        value="정상" if not missing else f"누락: {', '.join(missing)}",
        inline=False,
    )

    nickname_ok = bool(
        bot_member and bot_member.guild_permissions.manage_nicknames
    )
    embed.add_field(
        name="닉네임 변경",
        value=(
            "권한 있음 — 단, 봇보다 높은 역할과 서버 소유자의 닉네임은 변경할 수 없습니다."
            if nickname_ok
            else "Manage Nicknames 권한 또는 봇 역할 순서를 확인하세요."
        ),
        inline=False,
    )
    if missing or not nickname_ok:
        embed.color = 0xFEE75C
    return embed


class SetupMessageModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="환영 메시지 설정")
        self.guild_id = guild_id
        config = get_guild(guild_id)
        self.message = discord.ui.TextInput(
            label="환영 문구",
            default=config["welcome_message"][:1000],
            placeholder="{server}는 서버 이름으로 바뀝니다.",
            max_length=1000,
        )
        self.link = discord.ui.TextInput(
            label="규칙·안내 링크 (선택)",
            default=config["link"][:1000],
            placeholder="https://...",
            required=False,
            max_length=1000,
        )
        self.add_item(self.message)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_guild_admin(interaction) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "서버 관리자만 이 설정을 변경할 수 있습니다.",
                ephemeral=True,
            )
            return

        message = self.message.value.strip()
        link = self.link.value.strip()
        if not message:
            await interaction.response.send_message(
                "환영 문구는 공백으로만 저장할 수 없습니다.",
                ephemeral=True,
            )
            return
        if not is_http_url(link):
            await interaction.response.send_message(
                "안내 링크는 `https://` 또는 `http://` 주소만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        update_guild(self.guild_id, "welcome_message", message)
        update_guild(self.guild_id, "link", link)
        record_metric("setup_message_saved", self.guild_id)
        await interaction.response.edit_message(
            embed=build_setup_embed(interaction.guild),
            view=SetupView(self.guild_id, interaction.user.id),
        )


class WelcomeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="1. 환영 메시지를 보낼 채널 선택",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, SetupView) or not view.can_manage(interaction):
            await interaction.response.send_message(
                "이 설정 화면을 연 서버 관리자만 변경할 수 있습니다.",
                ephemeral=True,
            )
            return

        channel = self.values[0]
        update_guild(view.guild_id, "welcome_channel_id", channel.id)
        record_metric("setup_channel_saved", view.guild_id)
        await interaction.response.edit_message(
            embed=build_setup_embed(interaction.guild),
            view=SetupView(view.guild_id, view.user_id),
        )


class SetupMessageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="2. 문구·링크 입력",
            style=discord.ButtonStyle.primary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, SetupView) or not view.can_manage(interaction):
            await interaction.response.send_message(
                "이 설정 화면을 연 서버 관리자만 변경할 수 있습니다.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(SetupMessageModal(view.guild_id))


class PermissionCheckButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="3. 권한 진단",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, SetupView) or not view.can_manage(interaction):
            await interaction.response.send_message(
                "이 설정 화면을 연 서버 관리자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return
        record_metric("permission_check", view.guild_id)
        await interaction.response.send_message(
            embed=build_permission_embed(interaction.guild),
            ephemeral=True,
        )


class WelcomeTestButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="테스트 발송",
            style=discord.ButtonStyle.success,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, SetupView) or not view.can_manage(interaction):
            await interaction.response.send_message(
                "이 설정 화면을 연 서버 관리자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        config = get_guild(view.guild_id)
        channel = resolve_welcome_channel(interaction.guild, config)
        if channel is None:
            await interaction.response.send_message(
                "환영 채널을 찾을 수 없습니다. 먼저 채널을 선택하세요.",
                ephemeral=True,
            )
            return

        missing = missing_channel_permissions(channel)
        if missing:
            await interaction.response.send_message(
                f"{channel.mention}에서 다음 권한이 필요합니다: {', '.join(missing)}",
                ephemeral=True,
            )
            return

        try:
            await channel.send(
                embed=build_welcome_embed(interaction.guild, interaction.user),
                view=WelcomeView(),
            )
        except discord.HTTPException:
            LOGGER.exception("Failed to send welcome test for guild %s", view.guild_id)
            record_metric("welcome_test_failed", view.guild_id)
            await interaction.response.send_message(
                "Discord가 테스트 메시지 전송을 거부했습니다. 채널과 봇 권한을 확인하세요.",
                ephemeral=True,
            )
            return

        record_metric("welcome_test_sent", view.guild_id)
        record_metric("setup_completed", view.guild_id)
        await interaction.response.send_message(
            f"{channel.mention}에 테스트 메시지를 보냈습니다. 초기 설정이 완료되었습니다.",
            ephemeral=True,
        )


class SetupView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.user_id = user_id
        self.add_item(WelcomeChannelSelect())
        self.add_item(SetupMessageButton())
        self.add_item(PermissionCheckButton())
        self.add_item(WelcomeTestButton())

    def can_manage(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.guild is not None
            and interaction.guild.id == self.guild_id
            and interaction.user.id == self.user_id
            and is_guild_admin(interaction)
        )


class SetupPromptButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="연삼이 초기 설정",
            style=discord.ButtonStyle.primary,
            custom_id="setup:open",
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 초기 설정을 열 수 있습니다.",
                ephemeral=True,
            )
            return
        ensure_guild(interaction.guild.id)
        record_metric("setup_started", interaction.guild.id)
        await interaction.response.send_message(
            embed=build_setup_embed(interaction.guild),
            view=SetupView(interaction.guild.id, interaction.user.id),
            ephemeral=True,
        )


class SetupPromptView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SetupPromptButton())


class InviteView(discord.ui.View):
    def __init__(self, application_id: int):
        super().__init__()
        self.add_item(
            discord.ui.Button(
                label="다른 서버에 연삼이 추가",
                style=discord.ButtonStyle.link,
                url=build_invite_url(application_id),
            )
        )


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="설정", description="연삼이 환영 기능을 3단계로 설정합니다.")
    @app_commands.default_permissions(administrator=True)
    async def setup_command(self, interaction: discord.Interaction):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 이 명령어를 사용할 수 있습니다.",
                ephemeral=True,
            )
            return
        ensure_guild(interaction.guild.id)
        record_metric("setup_started", interaction.guild.id)
        await interaction.response.send_message(
            embed=build_setup_embed(interaction.guild),
            view=SetupView(interaction.guild.id, interaction.user.id),
            ephemeral=True,
        )

    @app_commands.command(name="초대", description="연삼이를 다른 서버에 추가하는 링크를 봅니다.")
    async def invite_command(self, interaction: discord.Interaction):
        application_id = self.bot.application_id
        if not application_id:
            await interaction.response.send_message(
                "애플리케이션 정보를 아직 불러오지 못했습니다. 잠시 후 다시 시도하세요.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "아래 버튼으로 필요한 최소 권한만 요청하는 설치 화면을 열 수 있습니다.",
            view=InviteView(application_id),
            ephemeral=True,
        )

    @app_commands.command(name="연삼통계", description="최근 7일의 서버별 사용 지표를 확인합니다.")
    @app_commands.default_permissions(administrator=True)
    async def metrics_command(self, interaction: discord.Interaction):
        if not is_guild_admin(interaction):
            await interaction.response.send_message(
                "서버 관리자만 이 명령어를 사용할 수 있습니다.",
                ephemeral=True,
            )
            return
        totals = get_metric_totals(days=7, guild_id=interaction.guild.id)
        embed = discord.Embed(
            title="연삼이 최근 7일 사용 지표",
            description="개인 사용자 ID를 저장하지 않는 서버 단위 집계입니다.",
            color=0x5865F2,
        )
        if totals:
            embed.add_field(
                name="집계",
                value="\n".join(f"- {name}: {value}" for name, value in totals.items()),
                inline=False,
            )
        else:
            embed.add_field(name="집계", value="아직 기록된 사용량이 없습니다.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        bot_member = guild.me
        if bot_member is None:
            record_metric("setup_prompt_failed", guild.id)
            return
        channel = guild.system_channel
        if (
            channel is None
            or not channel.permissions_for(bot_member).send_messages
            or not channel.permissions_for(bot_member).embed_links
        ):
            channel = next(
                (
                    item
                    for item in guild.text_channels
                    if item.permissions_for(bot_member).send_messages
                    and item.permissions_for(bot_member).embed_links
                ),
                None,
            )
        if channel is None:
            record_metric("setup_prompt_failed", guild.id)
            return

        embed = discord.Embed(
            title="연삼이가 서버에 추가되었습니다.",
            description=(
                "관리자는 아래 버튼 또는 `/설정` 명령어로 환영 채널, 문구, 안내 링크를 "
                "설정하고 테스트할 수 있습니다."
            ),
            color=0x5865F2,
        )
        try:
            await channel.send(embed=embed, view=SetupPromptView())
            record_metric("setup_prompt_sent", guild.id)
        except discord.HTTPException:
            LOGGER.exception("Failed to send setup prompt for guild %s", guild.id)
            record_metric("setup_prompt_failed", guild.id)


async def setup(bot):
    bot.add_view(SetupPromptView())
    await bot.add_cog(Settings(bot))
