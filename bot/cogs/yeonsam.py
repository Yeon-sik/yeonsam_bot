import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from cogs.welcome import WelcomeView
from utils.game_content import list_games, load_game_data
from utils.profile import update_member_nickname
from utils.storage import FILE as GUILD_CONFIG_FILE
from utils.storage import get_guild, load_data, update_guild
from utils.welcome_message import build_welcome_embed


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def get_namespace_value(interaction: discord.Interaction, *keys: str) -> str | None:
    for key in keys:
        value = getattr(interaction.namespace, key, None)
        if value not in (None, ""):
            return value
    return None


def resolve_section(section: str | None) -> str:
    normalized = normalize_text(section)
    section_map = {
        "overview": "overview",
        "개요": "overview",
        "guides": "guides",
        "guide": "guides",
        "공략": "guides",
        "install": "install",
        "installation": "install",
        "설치": "install",
    }
    return section_map.get(normalized, "overview")


def get_section_entries(data: dict, section: str | None) -> list[dict]:
    resolved_section = resolve_section(section)
    if resolved_section == "guides":
        return data.get("guides", [])
    if resolved_section == "install":
        return data.get("install", [])
    return []


def monster_section_label(section: str) -> str:
    return {
        "inside": "내부",
        "outside": "외부",
        "dummy": "더미",
    }.get(section, section)


def page_section_label(section: str) -> str:
    return {
        "overview": "개요",
        "guides": "공략",
        "install": "설치",
    }.get(section, section)


def count_monster_sections(monsters: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for monster in monsters:
        label = monster_section_label(monster.get("section", "-"))
        counts[label] = counts.get(label, 0) + 1
    return counts


def resolve_topic_entry(entries: list[dict], topic: str | None) -> dict | None:
    normalized_topic = normalize_text(topic)
    if not normalized_topic:
        return None

    return next(
        (
            item
            for item in entries
            if normalize_text(item.get("id")) == normalized_topic
            or normalize_text(item.get("label")) == normalized_topic
            or normalize_text(item.get("title")) == normalized_topic
        ),
        None,
    )


async def autocomplete_game(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    current_lower = normalize_text(current)
    choices: list[app_commands.Choice[str]] = []

    for slug in list_games():
        try:
            data = load_game_data(slug)
            display_name = data.get("name", slug)
        except Exception:
            display_name = slug

        haystack = f"{slug} {display_name}".lower()
        if current_lower and current_lower not in haystack:
            continue

        choices.append(app_commands.Choice(name=f"{display_name} ({slug})", value=slug))

    return choices[:25]


async def autocomplete_topic(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    game = get_namespace_value(interaction, "게임", "game") or "LethalCompany"
    section = resolve_section(get_namespace_value(interaction, "구역", "section"))

    if section == "overview":
        return []

    try:
        data = load_game_data(game)
    except FileNotFoundError:
        return []

    entries = get_section_entries(data, section)
    current_lower = normalize_text(current)
    choices: list[app_commands.Choice[str]] = []

    for item in entries:
        label = item["label"]
        title = item["title"]
        extra_count = len(item.get("monsters", item.get("groups", [])))
        haystack = f"{item['id']} {label} {title}".lower()

        if current_lower and current_lower not in haystack:
            continue

        choices.append(
            app_commands.Choice(
                name=f"{label} ({item['id']}) - {extra_count}개",
                value=item["id"],
            )
        )

    return choices[:25]


async def autocomplete_entry(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    game = get_namespace_value(interaction, "게임", "game") or "LethalCompany"
    section = resolve_section(get_namespace_value(interaction, "구역", "section"))
    topic = get_namespace_value(interaction, "주제", "topic")

    if section == "overview" or not topic:
        return []

    try:
        data = load_game_data(game)
    except FileNotFoundError:
        return []

    matched_entry = resolve_topic_entry(get_section_entries(data, section), topic)
    if matched_entry is None:
        return []

    current_lower = normalize_text(current)

    if matched_entry["id"] == "monsters" and matched_entry.get("monsters"):
        choices: list[app_commands.Choice[str]] = []
        for monster in matched_entry["monsters"]:
            name = monster["name"]
            name_kr = monster.get("nameKr", "-")
            section_name = monster_section_label(monster.get("section", "-"))
            haystack = f"{monster['id']} {name} {name_kr} {section_name}".lower()

            if current_lower and current_lower not in haystack:
                continue

            choices.append(
                app_commands.Choice(
                    name=f"{name} / {name_kr} [{section_name}]",
                    value=monster["id"],
                )
            )

        return choices[:25]

    choices: list[app_commands.Choice[str]] = []
    for group in matched_entry.get("groups", []):
        haystack = group["title"].lower()
        if current_lower and current_lower not in haystack:
            continue
        choices.append(app_commands.Choice(name=group["title"], value=group["title"]))

    return choices[:25]


class EditMessageModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="안내 메시지 수정")
        self.guild_id = guild_id

        config = get_guild(guild_id)

        self.message = discord.ui.TextInput(
            label="환영 메시지",
            default=config["welcome_message"],
        )
        self.link = discord.ui.TextInput(
            label="링크 (선택)",
            default=config["link"],
            required=False,
        )

        self.add_item(self.message)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        update_guild(self.guild_id, "welcome_message", self.message.value)
        update_guild(self.guild_id, "link", self.link.value)

        config = get_guild(self.guild_id)
        guild_name = interaction.guild.name if interaction.guild else "서버"
        message = config["welcome_message"].replace("{server}", guild_name)
        link = config["link"]

        embed = discord.Embed(
            title="연삼 봇 미리보기",
            description=message,
            color=0x5865F2,
        )

        if link:
            embed.add_field(name="안내 링크", value=link, inline=False)

        await interaction.response.send_message(
            content="설정을 저장했습니다.",
            embed=embed,
            ephemeral=True,
        )


class EditMessageButton(discord.ui.Button):
    def __init__(self, guild_id: int):
        super().__init__(label="안내 메시지 수정", style=discord.ButtonStyle.primary)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditMessageModal(self.guild_id))


class ProfileButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="서버 프로필 수정",
            style=discord.ButtonStyle.secondary,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ProfileModal())


class ProfileModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="서버 프로필 수정")

        self.nickname = discord.ui.TextInput(
            label="닉네임",
            placeholder="이 서버에서 사용할 닉네임",
            max_length=32,
        )
        self.add_item(self.nickname)

    async def on_submit(self, interaction: discord.Interaction):
        _, message = await update_member_nickname(interaction, self.nickname.value)
        await interaction.response.send_message(message, ephemeral=True)


class YeonsamView(discord.ui.View):
    def __init__(self, guild_id: int, is_admin: bool):
        super().__init__()

        if is_admin:
            self.add_item(EditMessageButton(guild_id))

        self.add_item(ProfileButton())


class Yeonsam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="연삼", description="연삼 봇 안내를 표시합니다.")
    async def yeonsam(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "이 명령어는 서버 안에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        config = get_guild(guild.id)
        message = config["welcome_message"].replace("{server}", guild.name)
        link = config["link"]

        embed = discord.Embed(
            title="연삼 봇",
            description=message,
            color=0x5865F2,
        )

        if link:
            embed.add_field(name="안내 링크", value=link, inline=False)

        is_admin = interaction.user.guild_permissions.administrator
        await interaction.response.send_message(
            embed=embed,
            view=YeonsamView(guild.id, is_admin),
            ephemeral=True,
        )

    @app_commands.command(name="연삼도움말", description="연삼 봇 명령어 사용법을 봅니다.")
    async def yeonsam_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="연삼 봇 사용법",
            description="주요 명령어와 추천 입력 흐름입니다.",
            color=0xFF00FF,
        )
        embed.add_field(
            name="/연삼",
            value="현재 서버용 연삼 봇 안내와 빠른 설정 버튼을 표시합니다.",
            inline=False,
        )
        embed.add_field(
            name="/연삼게임",
            value=(
                "`게임`은 자동완성으로 선택할 수 있습니다.\n"
                "`구역`은 개요 / 공략 / 설치 중에서 고릅니다.\n"
                "`주제`는 선택한 게임과 구역에 맞는 목록이 자동완성으로 나옵니다.\n"
                "`항목`은 선택한 주제 안의 세부 항목이 자동완성으로 나옵니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="예시",
            value=(
                "/연삼게임 게임:LethalCompany 구역:공략 주제:monsters\n"
                "/연삼게임 게임:LethalCompany 구역:공략 주제:monsters 항목:lasso-man"
            ),
            inline=False,
        )
        embed.add_field(
            name="/연삼환영디버그",
            value="환영 메시지 UI를 현재 서버 기준으로 테스트합니다.",
            inline=False,
        )
        embed.add_field(
            name="/연삼코드",
            value="길드 수, 등록 명령어, 현재 서버 설정을 JSON으로 출력합니다.",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="연삼게임", description="게임 JSON 데이터를 봅니다.")
    @app_commands.rename(
        game="게임",
        section="구역",
        topic="주제",
        entry="항목",
    )
    @app_commands.describe(
        game="게임 선택",
        section="개요, 공략, 설치 중 하나를 고릅니다.",
        topic="선택한 구역의 세부 주제",
        entry="선택한 주제 안의 세부 항목",
    )
    @app_commands.choices(
        section=[
            app_commands.Choice(name="개요", value="overview"),
            app_commands.Choice(name="공략", value="guides"),
            app_commands.Choice(name="설치", value="install"),
        ]
    )
    @app_commands.autocomplete(
        game=autocomplete_game,
        topic=autocomplete_topic,
        entry=autocomplete_entry,
    )
    async def yeonsam_game(
        self,
        interaction: discord.Interaction,
        game: str = "LethalCompany",
        section: str = "overview",
        topic: str | None = None,
        entry: str | None = None,
    ):
        try:
            data = load_game_data(game)
        except FileNotFoundError:
            games = ", ".join(list_games()) or "없음"
            await interaction.response.send_message(
                f"게임 데이터를 찾지 못했습니다. 사용 가능한 게임: {games}",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title=data["name"], color=0xFF00FF)

        resolved_section = resolve_section(section)

        if resolved_section == "overview":
            description = data["description"]
            embed.description = description["summary"]
            embed.add_field(name="장르", value=description["genre"], inline=False)
            embed.add_field(
                name="핵심 포인트",
                value="\n".join(f"- {item}" for item in description["details"]),
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        entries = get_section_entries(data, resolved_section)
        embed.description = f"{data['name']} {page_section_label(resolved_section)}"

        if topic:
            matched_entry = resolve_topic_entry(entries, topic)
            if matched_entry is None:
                available_topics = ", ".join(item["label"] for item in entries)
                await interaction.response.send_message(
                    f"주제 '{topic}'을 찾지 못했습니다. 사용 가능한 주제: {available_topics}",
                    ephemeral=True,
                )
                return

            embed.description = f"{data['name']} - {matched_entry['label']}"

            if matched_entry["id"] == "monsters" and matched_entry.get("monsters"):
                monsters = matched_entry["monsters"]

                if entry:
                    normalized_entry = normalize_text(entry)
                    matched_monster = next(
                        (
                            monster
                            for monster in monsters
                            if normalize_text(monster.get("id")) == normalized_entry
                            or normalize_text(monster.get("name")) == normalized_entry
                            or normalize_text(monster.get("nameKr")) == normalized_entry
                        ),
                        None,
                    )

                    if matched_monster is None:
                        available_monsters = ", ".join(
                            f"{monster['name']} / {monster.get('nameKr', '-')}"
                            for monster in monsters
                        )
                        await interaction.response.send_message(
                            f"몬스터 '{entry}'을(를) 찾지 못했습니다. 사용 가능한 몬스터: {available_monsters}",
                            ephemeral=True,
                        )
                        return

                    embed.description = (
                        f"{data['name']} - {matched_entry['label']} - {matched_monster['name']}"
                    )
                    embed.add_field(name="영문 이름", value=matched_monster["name"], inline=False)
                    embed.add_field(
                        name="한글 이름",
                        value=matched_monster.get("nameKr", "-"),
                        inline=False,
                    )
                    embed.add_field(
                        name="분류",
                        value=monster_section_label(matched_monster.get("section", "-")),
                        inline=False,
                    )
                    embed.add_field(name="설명", value=matched_monster["description"], inline=False)
                    embed.add_field(name="공략", value=matched_monster["strategy"], inline=False)
                    embed.add_field(name="체력", value=matched_monster["health"], inline=False)
                else:
                    section_counts = count_monster_sections(monsters)
                    embed.add_field(
                        name="몬스터 가짓수",
                        value="\n".join(f"- {name}: {count}" for name, count in section_counts.items()),
                        inline=False,
                    )
                    embed.add_field(
                        name="선택 가능한 항목",
                        value=", ".join(
                            f"`{monster['id']}` ({monster['name']} / {monster.get('nameKr', '-')})"
                            for monster in monsters[:25]
                        ),
                        inline=False,
                    )
            else:
                for group in matched_entry["groups"]:
                    embed.add_field(
                        name=group["title"],
                        value="\n".join(f"- {item}" for item in group["items"]),
                        inline=False,
                    )
        else:
            embed.add_field(
                name="선택 가능한 주제",
                value=", ".join(f"`{item['id']}` ({item['label']})" for item in entries),
                inline=False,
            )

            for item in entries:
                if item["id"] == "monsters" and item.get("monsters"):
                    value = "\n".join(
                        f"- {name}: {count}"
                        for name, count in count_monster_sections(item["monsters"]).items()
                    )
                else:
                    value = f"{len(item['groups'])}개 그룹"

                embed.add_field(
                    name=item["title"],
                    value=value,
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="연삼환영디버그", description="환영 메시지 화면을 테스트합니다.")
    @app_commands.default_permissions(administrator=True)
    async def yeonsam_debug(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "이 명령어는 서버 안에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        embed = build_welcome_embed(guild, member)
        await interaction.response.send_message(
            embed=embed,
            view=WelcomeView(),
            ephemeral=True,
        )

    @app_commands.command(name="연삼코드", description="디버깅용 상태 코드를 출력합니다.")
    @app_commands.default_permissions(administrator=True)
    async def yeonsam_code(self, interaction: discord.Interaction):
        guild = interaction.guild
        guild_config = get_guild(guild.id) if guild else {}
        guild_lines = [f"{item.name} ({item.id})" for item in self.bot.guilds] or ["없음"]
        command_names = sorted(command.name for command in self.bot.tree.get_commands())

        payload = {
            "bot_user": str(self.bot.user) if self.bot.user else None,
            "bot_id": self.bot.user.id if self.bot.user else None,
            "guild_count": len(self.bot.guilds),
            "guilds": guild_lines,
            "current_guild": {
                "name": guild.name if guild else None,
                "id": guild.id if guild else None,
            },
            "guild_config_file": str(Path(GUILD_CONFIG_FILE)),
            "current_guild_config": guild_config,
            "registered_commands": command_names,
            "saved_guild_config_count": len(load_data()),
        }

        debug_text = json.dumps(payload, ensure_ascii=False, indent=2)
        await interaction.response.send_message(
            f"```json\n{debug_text}\n```",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Yeonsam(bot))
