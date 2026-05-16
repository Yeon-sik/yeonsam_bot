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

GUIDE_BASE_URL = "https://yeon-sik.github.io/yeonsam_bot/games"
SECTION_CHOICES = [
    ("개요", "overview"),
    ("공략", "guides"),
    ("설치", "install"),
]


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def resolve_section(section: str | None) -> str | None:
    normalized = normalize_text(section)
    if not normalized:
        return None

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
    return section_map.get(normalized)


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


def monster_category_label(monster: dict) -> str:
    section = normalize_text(monster.get("section"))
    if section:
        return monster_section_label(section)

    tier = monster.get("tier")
    if tier not in (None, ""):
        return f"Tier {tier}"

    return "-"


def page_section_label(section: str) -> str:
    return {
        "overview": "개요",
        "guides": "공략",
        "install": "설치",
    }.get(section, section)


def count_monster_sections(monsters: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for monster in monsters:
        label = monster_category_label(monster)
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


def build_game_page_name(data: dict) -> str:
    page_path = data.get("pagePath")
    if page_path:
        return str(page_path)

    return f"{data['slug']}.html"


def build_monster_guide_link(data: dict, monster_id: str) -> str:
    return f"{GUIDE_BASE_URL}/{build_game_page_name(data)}#monster-{monster_id}"


def build_category_entry_link(data: dict, category_id: str, entry_id: str) -> str:
    return f"{GUIDE_BASE_URL}/{build_game_page_name(data)}#{category_id}-{entry_id}"


def shorten_text(value: str | None, limit: int = 100) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def list_game_catalog() -> list[dict[str, str]]:
    catalog: list[dict[str, str]] = []
    for slug in list_games():
        try:
            data = load_game_data(slug)
        except FileNotFoundError:
            continue

        description = data.get("description", {})
        catalog.append(
            {
                "slug": slug,
                "name": data.get("name", slug),
                "summary": description.get("summary", ""),
            }
        )

    return catalog


def resolve_selected_monster(monsters: list[dict], entry: str | None) -> dict | None:
    normalized_entry = normalize_text(entry)
    if not normalized_entry:
        return None

    return next(
        (
            monster
            for monster in monsters
            if normalize_text(monster.get("id")) == normalized_entry
            or normalize_text(monster.get("name")) == normalized_entry
            or normalize_text(monster.get("nameKr")) == normalized_entry
        ),
        None,
    )


def resolve_selected_group(groups: list[dict], entry: str | None) -> dict | None:
    normalized_entry = normalize_text(entry)
    if not normalized_entry:
        return None

    return next(
        (group for group in groups if normalize_text(group.get("title")) == normalized_entry),
        None,
    )


def category_has_record_entries(category: dict) -> bool:
    return any(group.get("entries") for group in category.get("groups", []))


def flatten_category_entries(category: dict) -> list[tuple[dict, dict]]:
    flattened: list[tuple[dict, dict]] = []
    for group in category.get("groups", []):
        for item in group.get("entries", []):
            flattened.append((group, item))
    return flattened


def resolve_selected_record_entry(category: dict, entry: str | None) -> tuple[dict, dict] | None:
    normalized_entry = normalize_text(entry)
    if not normalized_entry:
        return None

    for group, item in flatten_category_entries(category):
        haystacks = [
            item.get("id"),
            item.get("name"),
            item.get("nameKr"),
            item.get("terminalCommand"),
        ]
        if any(normalize_text(value) == normalized_entry for value in haystacks if value):
            return group, item

    return None


def build_record_group_summary(group: dict) -> str:
    entries = group.get("entries", [])
    if not entries:
        return "등록된 항목이 없습니다."

    preview = ", ".join(
        f"`{item['id']}` ({item.get('nameKr') or item.get('name') or item['id']})"
        for item in entries[:5]
    )
    suffix = "" if len(entries) <= 5 else f" 외 {len(entries) - 5}개"
    return f"{preview}{suffix}"


def build_spawn_lines(spawns: list[dict]) -> str:
    if not spawns:
        return "-"

    return "\n".join(
        f"- {item.get('nameKr') or item.get('name', '-')}: {item.get('chance', '-')}"
        for item in spawns
    )


def add_record_entry_fields(embed: discord.Embed, data: dict, category_id: str, group: dict, item: dict):
    name = item.get("name", item.get("id", "-"))
    name_kr = item.get("nameKr")
    if name_kr:
        embed.add_field(name="한글 이름", value=name_kr, inline=False)
        embed.add_field(name="영문 이름", value=name, inline=False)
    else:
        embed.add_field(name="이름", value=name, inline=False)

    if group.get("title"):
        embed.add_field(name="구분", value=group["title"], inline=False)

    if category_id == "maps":
        embed.add_field(name="입장료", value=str(item.get("price", "-")), inline=False)
    elif "price" in item:
        embed.add_field(name="가격", value=str(item.get("price", "-")), inline=False)
    elif "priceRange" in item:
        embed.add_field(name="가격대", value=str(item.get("priceRange", "-")), inline=False)

    if item.get("terminalCommand"):
        embed.add_field(name="터미널 명령어", value=item["terminalCommand"], inline=False)

    if item.get("description"):
        embed.add_field(name="설명", value=item["description"], inline=False)

    if item.get("usage"):
        embed.add_field(name="사용법", value=item["usage"], inline=False)

    if item.get("spawnMonsters"):
        embed.add_field(name="출현 몬스터 및 확률", value=build_spawn_lines(item["spawnMonsters"]), inline=False)

    install_link = item.get("installLink")
    if install_link:
        embed.add_field(name="설치 링크", value=install_link, inline=False)

    embed.add_field(
        name="페이지 바로가기",
        value=build_category_entry_link(data, category_id, item["id"]),
        inline=False,
    )


def build_game_browser_embed(
    game: str | None = None,
    section: str | None = None,
    topic: str | None = None,
    entry: str | None = None,
) -> discord.Embed:
    if not game:
        embed = discord.Embed(
            title="연삼 게임 탐색기",
            description="아래 선택 메뉴에서 게임을 고르면 `구역 -> 주제 -> 항목` 순서로 이어서 클릭할 수 있습니다.",
            color=0xFF00FF,
        )
        catalog = list_game_catalog()
        if catalog:
            embed.add_field(
                name="등록된 게임",
                value=", ".join(item["name"] for item in catalog[:25]),
                inline=False,
            )
        return embed

    data = load_game_data(game)
    embed = discord.Embed(title=data["name"], color=0xFF00FF)
    resolved_section = resolve_section(section)

    if resolved_section is None:
        description = data["description"]
        embed.description = description["summary"]
        embed.add_field(name="장르", value=description["genre"], inline=False)
        embed.add_field(
            name="핵심 포인트",
            value="\n".join(f"- {item}" for item in description["details"]),
            inline=False,
        )
        embed.add_field(
            name="다음 단계",
            value="`구역 선택` 메뉴에서 `개요`, `공략`, `설치` 중 하나를 고르세요.",
            inline=False,
        )
        return embed

    if resolved_section == "overview":
        description = data["description"]
        embed.description = description["summary"]
        embed.add_field(name="장르", value=description["genre"], inline=False)
        embed.add_field(
            name="핵심 포인트",
            value="\n".join(f"- {item}" for item in description["details"]),
            inline=False,
        )
        return embed

    entries = get_section_entries(data, resolved_section)
    matched_entry = resolve_topic_entry(entries, topic)
    embed.description = f"{data['name']} {page_section_label(resolved_section)}"

    if matched_entry is None:
        embed.add_field(
            name="선택 가능한 주제",
            value=", ".join(f"`{item['id']}` ({item['label']})" for item in entries[:25]) or "없음",
            inline=False,
        )

        for item in entries[:25]:
            if item["id"] == "monsters" and item.get("monsters"):
                value = "\n".join(
                    f"- {name}: {count}"
                    for name, count in count_monster_sections(item["monsters"]).items()
                )
            else:
                value = f"{len(item.get('groups', []))}개 그룹"

            embed.add_field(
                name=item["title"],
                value=value,
                inline=False,
            )

        return embed

    embed.description = f"{data['name']} - {matched_entry['label']}"

    if matched_entry["id"] == "monsters" and matched_entry.get("monsters"):
        monsters = matched_entry["monsters"]
        matched_monster = resolve_selected_monster(monsters, entry)

        if matched_monster is None:
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
                )
                or "없음",
                inline=False,
            )
            return embed

        embed.description = f"{data['name']} - {matched_entry['label']} - {matched_monster['name']}"
        embed.add_field(name="영문 이름", value=matched_monster["name"], inline=False)
        embed.add_field(
            name="한글 이름",
            value=matched_monster.get("nameKr", "-"),
            inline=False,
        )
        embed.add_field(
            name="분류",
            value=monster_category_label(matched_monster),
            inline=False,
        )
        embed.add_field(name="설명", value=matched_monster["description"], inline=False)
        embed.add_field(name="공략", value=matched_monster["strategy"], inline=False)
        if matched_monster.get("health"):
            embed.add_field(name="체력", value=str(matched_monster["health"]), inline=False)
        if matched_monster.get("threatLevel"):
            embed.add_field(name="위협도", value=str(matched_monster["threatLevel"]), inline=False)
        if matched_monster.get("cashDrop"):
            embed.add_field(name="드롭", value=str(matched_monster["cashDrop"]), inline=False)
        embed.add_field(
            name="안내 링크",
            value=build_monster_guide_link(data, matched_monster["id"]),
            inline=False,
        )
        return embed

    if category_has_record_entries(matched_entry):
        selected_record = resolve_selected_record_entry(matched_entry, entry)
        if selected_record is None:
            for group in matched_entry.get("groups", [])[:25]:
                embed.add_field(
                    name=group["title"],
                    value=build_record_group_summary(group),
                    inline=False,
                )
            return embed

        matched_group, matched_item = selected_record
        display_name = matched_item.get("nameKr") or matched_item.get("name") or matched_item["id"]
        embed.description = f"{data['name']} - {matched_entry['label']} - {display_name}"
        add_record_entry_fields(embed, data, matched_entry["id"], matched_group, matched_item)
        return embed

    groups = matched_entry.get("groups", [])
    matched_group = resolve_selected_group(groups, entry)
    if matched_group is None:
        for group in groups[:25]:
            embed.add_field(
                name=group["title"],
                value="\n".join(f"- {item}" for item in group["items"]),
                inline=False,
            )
        return embed

    embed.description = f"{data['name']} - {matched_entry['label']} - {matched_group['title']}"
    embed.add_field(
        name=matched_group["title"],
        value="\n".join(f"- {item}" for item in matched_group["items"]),
        inline=False,
    )
    return embed


def build_disabled_select_options(label: str) -> list[discord.SelectOption]:
    return [discord.SelectOption(label=label, value="__disabled__")]


class GameBrowserView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        game: str | None = None,
        section: str | None = None,
        topic: str | None = None,
        entry: str | None = None,
    ):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.game = game
        self.section = resolve_section(section)
        self.topic = topic
        self.entry = entry
        self.catalog = list_game_catalog()
        self.data: dict | None = None
        self.topic_entry: dict | None = None
        self._normalize_state()
        self._build_items()

    def _normalize_state(self):
        if not self.game:
            self.section = None
            self.topic = None
            self.entry = None
            return

        try:
            self.data = load_game_data(self.game)
        except FileNotFoundError:
            self.game = None
            self.section = None
            self.topic = None
            self.entry = None
            return

        if self.section is None:
            self.topic = None
            self.entry = None
            return

        if self.section == "overview":
            self.topic = None
            self.entry = None
            return

        entries = get_section_entries(self.data, self.section)
        self.topic_entry = resolve_topic_entry(entries, self.topic)
        if self.topic_entry is None:
            self.topic = None
            self.entry = None
            return

        if self.topic_entry["id"] == "monsters" and self.topic_entry.get("monsters"):
            if resolve_selected_monster(self.topic_entry["monsters"], self.entry) is None:
                self.entry = None
            return

        if category_has_record_entries(self.topic_entry):
            if resolve_selected_record_entry(self.topic_entry, self.entry) is None:
                self.entry = None
            return

        if resolve_selected_group(self.topic_entry.get("groups", []), self.entry) is None:
            self.entry = None

    def _build_items(self):
        self.add_item(GameSelect(self))
        self.add_item(SectionSelect(self))
        self.add_item(TopicSelect(self))
        self.add_item(EntrySelect(self))
        self.add_item(QueryGameBrowserButton())
        self.add_item(ResetGameBrowserButton())

    def build_embed(self) -> discord.Embed:
        return build_game_browser_embed(
            game=self.game,
            section=self.section,
            topic=self.topic,
            entry=self.entry,
        )

    def game_options(self) -> list[discord.SelectOption]:
        options: list[discord.SelectOption] = []
        for item in self.catalog[:25]:
            options.append(
                discord.SelectOption(
                    label=item["name"][:100],
                    value=item["slug"],
                    description=shorten_text(item["summary"], 100) or item["slug"],
                    default=item["slug"] == self.game,
                )
            )
        return options

    def section_options(self) -> list[discord.SelectOption]:
        options: list[discord.SelectOption] = []
        for label, value in SECTION_CHOICES:
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=f"{label} 정보 보기",
                    default=value == self.section,
                )
            )
        return options

    def topic_options(self) -> list[discord.SelectOption]:
        if not self.data or not self.section or self.section == "overview":
            return build_disabled_select_options("먼저 게임과 구역을 선택하세요")

        options: list[discord.SelectOption] = []
        for item in get_section_entries(self.data, self.section)[:25]:
            extra_count = len(item.get("monsters", item.get("groups", [])))
            options.append(
                discord.SelectOption(
                    label=item["label"][:100],
                    value=item["id"],
                    description=shorten_text(f"{item['title']} · {extra_count}개 세부 항목", 100),
                    default=item["id"] == self.topic,
                )
            )
        return options or build_disabled_select_options("선택 가능한 주제가 없습니다")

    def entry_options(self) -> list[discord.SelectOption]:
        if not self.topic_entry:
            return build_disabled_select_options("먼저 주제를 선택하세요")

        if self.topic_entry["id"] == "monsters" and self.topic_entry.get("monsters"):
            options: list[discord.SelectOption] = []
            for monster in self.topic_entry["monsters"][:25]:
                label = monster.get("nameKr") or monster["name"]
                description = shorten_text(
                    f"{monster['name']} · {monster_category_label(monster)}",
                    100,
                )
                options.append(
                    discord.SelectOption(
                        label=label[:100],
                        value=monster["id"],
                        description=description,
                        default=monster["id"] == self.entry,
                    )
                )
            return options or build_disabled_select_options("선택 가능한 항목이 없습니다")

        if category_has_record_entries(self.topic_entry):
            options = []
            for group, item in flatten_category_entries(self.topic_entry)[:25]:
                label = item.get("nameKr") or item.get("name") or item["id"]
                description_parts = [group.get("title", "")]
                if item.get("price") is not None:
                    price_label = "입장료" if self.topic_entry.get("id") == "maps" else "가격"
                    description_parts.append(f"{price_label} {item['price']}")
                if item.get("terminalCommand"):
                    description_parts.append(item["terminalCommand"])

                options.append(
                    discord.SelectOption(
                        label=label[:100],
                        value=item["id"],
                        description=shorten_text(" · ".join(part for part in description_parts if part), 100),
                        default=item["id"] == self.entry,
                    )
                )

            return options or build_disabled_select_options("선택 가능한 항목이 없습니다")

        options = []
        for group in self.topic_entry.get("groups", [])[:25]:
            options.append(
                discord.SelectOption(
                    label=group["title"][:100],
                    value=group["title"],
                    description=shorten_text(f"{len(group['items'])}개 항목", 100),
                    default=group["title"] == self.entry,
                )
            )
        return options or build_disabled_select_options("선택 가능한 항목이 없습니다")

    async def refresh_message(self, interaction: discord.Interaction):
        view = GameBrowserView(
            user_id=self.user_id,
            game=self.game,
            section=self.section,
            topic=self.topic,
            entry=self.entry,
        )
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def refresh_controls(self, interaction: discord.Interaction):
        view = GameBrowserView(
            user_id=self.user_id,
            game=self.game,
            section=self.section,
            topic=self.topic,
            entry=self.entry,
        )
        await interaction.response.edit_message(view=view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "이 선택 메뉴는 명령을 실행한 사용자만 사용할 수 있어요.",
                ephemeral=True,
            )
            return False
        return True


class GameSelect(discord.ui.Select):
    def __init__(self, game_view: GameBrowserView):
        self.game_view = game_view
        super().__init__(
            placeholder="게임 선택",
            min_values=1,
            max_values=1,
            options=game_view.game_options() or build_disabled_select_options("등록된 게임이 없습니다"),
            row=0,
            disabled=not game_view.catalog,
        )

    async def callback(self, interaction: discord.Interaction):
        self.game_view.game = self.values[0]
        self.game_view.section = None
        self.game_view.topic = None
        self.game_view.entry = None
        await self.game_view.refresh_controls(interaction)


class SectionSelect(discord.ui.Select):
    def __init__(self, game_view: GameBrowserView):
        self.game_view = game_view
        has_game = game_view.game is not None
        super().__init__(
            placeholder="구역 선택",
            min_values=1,
            max_values=1,
            options=game_view.section_options() if has_game else build_disabled_select_options("먼저 게임을 선택하세요"),
            row=1,
            disabled=not has_game,
        )

    async def callback(self, interaction: discord.Interaction):
        self.game_view.section = self.values[0]
        self.game_view.topic = None
        self.game_view.entry = None
        await self.game_view.refresh_controls(interaction)


class TopicSelect(discord.ui.Select):
    def __init__(self, game_view: GameBrowserView):
        self.game_view = game_view
        enabled = game_view.data is not None and game_view.section not in (None, "overview")
        super().__init__(
            placeholder="주제 선택",
            min_values=1,
            max_values=1,
            options=game_view.topic_options(),
            row=2,
            disabled=not enabled,
        )

    async def callback(self, interaction: discord.Interaction):
        self.game_view.topic = self.values[0]
        self.game_view.entry = None
        await self.game_view.refresh_controls(interaction)


class EntrySelect(discord.ui.Select):
    def __init__(self, game_view: GameBrowserView):
        self.game_view = game_view
        super().__init__(
            placeholder="항목 선택",
            min_values=1,
            max_values=1,
            options=game_view.entry_options(),
            row=3,
            disabled=game_view.topic_entry is None,
        )

    async def callback(self, interaction: discord.Interaction):
        self.game_view.entry = self.values[0]
        await self.game_view.refresh_controls(interaction)


class QueryGameBrowserButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="조회",
            style=discord.ButtonStyle.primary,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        game_view = self.view
        if not isinstance(game_view, GameBrowserView):
            await interaction.response.defer()
            return

        await game_view.refresh_message(interaction)


class ResetGameBrowserButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="처음부터 다시 선택",
            style=discord.ButtonStyle.secondary,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        view = GameBrowserView(user_id=interaction.user.id)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


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
                "명령어 입력 후 선택 메뉴가 열립니다.\n"
                "`게임 -> 구역 -> 주제 -> 항목` 순서로 클릭해서 탐색합니다.\n"
                "게임 JSON만 추가하면 같은 UI에 자동으로 포함되도록 구성되어 있습니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="예시",
            value=(
                "1. `/연삼게임` 입력\n"
                "2. `게임 선택`에서 Lethal Company 클릭\n"
                "3. `구역 -> 주제 -> 항목` 순서로 선택"
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

    @app_commands.command(name="연삼게임", description="게임 JSON 데이터를 선택형 UI로 봅니다.")
    async def yeonsam_game(self, interaction: discord.Interaction):
        view = GameBrowserView(user_id=interaction.user.id)
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )

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
