import json
from pathlib import Path
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.welcome import WelcomeView
from utils.game_content import DATA_ROOT, list_games, load_game_data
from utils.profile import update_member_nickname
from utils.storage import FILE as GUILD_CONFIG_FILE
from utils.storage import get_guild, load_data, record_metric, update_guild
from utils.validation import is_http_url
from utils.welcome_message import build_welcome_embed

GUIDE_BASE_URL = "https://yeon-sik.github.io/yeonsam_bot/games"
GUIDE_IMAGE_LIMIT = 10
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SEARCH_ROUTE_SEPARATOR = "|"
RANDOM_NUMBER_LIMIT = 100
EMBED_FIELD_LIMIT = 25
SECTION_CHOICES = [
    ("개요", "overview"),
    ("공략", "guides"),
]


# 게임/가이드 JSON을 디스코드 선택 메뉴와 임베드에 맞게 해석하는 공통 유틸리티입니다.
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
    }
    return section_map.get(normalized)


def get_section_entries(data: dict, section: str | None) -> list[dict]:
    resolved_section = resolve_section(section)
    if resolved_section == "guides":
        return data.get("guides", [])
    return []


def monster_section_label(section: str) -> str:
    return {
        "inside": "내부",
        "outside": "외부",
        "daytime": "주간",
        "company": "회사 건물",
        "dummy": "더미",
    }.get(section, section)


def add_monster_research_fields(embed: discord.Embed, research: dict | None):
    if not research:
        return

    version = research.get("gameVersion")
    verified_at = research.get("verifiedAt")
    if version or verified_at:
        embed.add_field(
            name="검증 기준",
            value=clamp_field_value(
                " · ".join(str(value) for value in (version, verified_at) if value)
            ),
            inline=False,
        )

    source_lines = []
    for source in select_monster_research_sources(research.get("sources", [])):
        url = str(source.get("url", ""))
        if not url.startswith("https://") or not is_http_url(url):
            continue
        label = str(source.get("label") or url).replace("]", "")
        source_lines.append(f"- [{label}]({url})")

    if source_lines:
        embed.add_field(
            name="근거 자료",
            value=clamp_field_value("\n".join(source_lines)),
            inline=False,
        )


def select_monster_research_sources(sources: list[dict], limit: int = 5) -> list[dict]:
    """Pick a balanced official/data/practical source set for Discord's compact embed."""
    selected: list[dict] = []
    source_groups = (
        lambda source_type: source_type == "official",
        lambda source_type: "build" in source_type or "mirror" in source_type,
        lambda source_type: "wiki" in source_type or "community-data" in source_type,
        lambda source_type: "practical" in source_type,
        lambda source_type: "technical" in source_type or "mechanics" in source_type,
    )

    for matches_group in source_groups:
        match = next(
            (
                source
                for source in sources
                if source not in selected and matches_group(str(source.get("type", "")))
            ),
            None,
        )
        if match is not None:
            selected.append(match)

    for source in sources:
        if len(selected) >= limit:
            break
        if source not in selected:
            selected.append(source)

    return selected[:limit]


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


def build_game_page_link(data: dict) -> str:
    return f"{GUIDE_BASE_URL}/{build_game_page_name(data)}"


def build_category_entry_link(data: dict, category_id: str, entry_id: str) -> str:
    return f"{GUIDE_BASE_URL}/{build_game_page_name(data)}#{category_id}-{entry_id}"


def shorten_text(value: str | None, limit: int = 100) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def flatten_entry_aliases(entry: dict) -> list[str]:
    aliases = entry.get("aliases", [])
    if not isinstance(aliases, list):
        return []
    return [str(alias).strip() for alias in aliases if str(alias).strip()]


def build_search_keywords(*values: object) -> list[str]:
    keywords: list[str] = []
    for value in values:
        normalized = normalize_text(str(value) if value is not None else None)
        if normalized:
            keywords.append(normalized)
    return keywords


def build_search_route(
    game: str,
    section: str | None = None,
    topic: str | None = None,
    entry: str | None = None,
) -> str:
    return SEARCH_ROUTE_SEPARATOR.join((game, section or "", topic or "", entry or ""))


def parse_search_route(value: str | None) -> tuple[str, str | None, str | None, str | None] | None:
    if not value or SEARCH_ROUTE_SEPARATOR not in value:
        return None

    parts = value.split(SEARCH_ROUTE_SEPARATOR, 3)
    if len(parts) != 4:
        return None

    game, section, topic, entry = parts
    if not game:
        return None

    return game, section or None, topic or None, entry or None


def build_search_choice_name(display_name: str, game_name: str, context: str) -> str:
    return shorten_text(f"{display_name} · {game_name} · {context}", 100)


def create_search_candidate(
    *,
    game_slug: str,
    game_name: str,
    context: str,
    display_name: str,
    section: str | None = None,
    topic: str | None = None,
    entry: str | None = None,
    keywords: list[str],
) -> dict[str, object]:
    return {
        "route": build_search_route(game_slug, section, topic, entry),
        "choice_name": build_search_choice_name(display_name, game_name, context),
        "display_name": display_name,
        "context": f"{game_name} · {context}",
        "keywords": build_search_keywords(*keywords),
    }


def build_search_candidates() -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []

    for game_slug in list_games():
        try:
            data = load_game_data(game_slug)
        except FileNotFoundError:
            continue

        game_name = data.get("name", game_slug)
        game_aliases = flatten_entry_aliases(data)
        candidates.append(
            create_search_candidate(
                game_slug=game_slug,
                game_name=game_name,
                context="게임 홈",
                display_name="전체 가이드",
                keywords=[game_slug, game_name, *game_aliases],
            )
        )
        for topic_entry in data.get("guides", []):
            topic_context = str(topic_entry.get("label") or topic_entry.get("title") or "공략")
            topic_keywords = [
                game_name,
                topic_entry.get("id"),
                topic_entry.get("label"),
                topic_entry.get("title"),
            ]

            candidates.append(
                create_search_candidate(
                    game_slug=game_slug,
                    game_name=game_name,
                    context=topic_context,
                    display_name=str(topic_entry.get("label") or topic_entry.get("title") or topic_context),
                    section="guides",
                    topic=topic_entry.get("id"),
                    keywords=topic_keywords,
                )
            )

            if topic_entry.get("monsters"):
                # 자동완성 응답만 25개로 제한하고, 후보 색인에는 전체 몬스터를 넣습니다.
                # 그래야 Discord Select의 25개 제한 밖에 있는 몬스터도 이름 검색으로 열 수 있습니다.
                for monster in topic_entry["monsters"]:
                    display_name = str(monster.get("nameKr") or monster.get("name") or monster["id"])
                    candidates.append(
                        create_search_candidate(
                            game_slug=game_slug,
                            game_name=game_name,
                            context="몬스터",
                            display_name=display_name,
                            section="guides",
                            topic=topic_entry.get("id"),
                            entry=monster.get("id"),
                            keywords=[
                                game_name,
                                topic_entry.get("label"),
                                monster.get("id"),
                                monster.get("name"),
                                monster.get("nameKr"),
                            ],
                        )
                    )
                continue

            if category_has_record_entries(topic_entry):
                for _, item in flatten_category_entries(topic_entry):
                    display_name = str(item.get("nameKr") or item.get("name") or item["id"])
                    candidates.append(
                        create_search_candidate(
                            game_slug=game_slug,
                            game_name=game_name,
                            context=topic_context,
                            display_name=display_name,
                            section="guides",
                            topic=topic_entry.get("id"),
                            entry=item.get("id"),
                            keywords=[
                                game_name,
                                topic_entry.get("label"),
                                item.get("id"),
                                item.get("name"),
                                item.get("nameKr"),
                                item.get("terminalCommand"),
                                *flatten_entry_aliases(item),
                            ],
                        )
                    )
                continue

            if topic_entry.get("groups") and topic_entry.get("entrySelectable") is not False:
                for group in topic_entry.get("groups", []):
                    display_name = str(group.get("title") or group.get("label") or "항목")
                    candidates.append(
                        create_search_candidate(
                            game_slug=game_slug,
                            game_name=game_name,
                            context=topic_context,
                            display_name=display_name,
                            section="guides",
                            topic=topic_entry.get("id"),
                            entry=group.get("title"),
                            keywords=[
                                game_name,
                                topic_entry.get("label"),
                                group.get("title"),
                                group.get("label"),
                            ],
                        )
                    )

    return candidates


def score_search_candidate(candidate: dict[str, object], query: str) -> tuple[int, int] | None:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return 3, len(str(candidate["choice_name"]))

    keywords = candidate.get("keywords", [])
    if not isinstance(keywords, list):
        return None

    best_score: int | None = None
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword:
            continue
        if keyword == normalized_query:
            best_score = 0 if best_score is None else min(best_score, 0)
        elif keyword.startswith(normalized_query):
            best_score = 1 if best_score is None else min(best_score, 1)
        elif normalized_query in keyword:
            best_score = 2 if best_score is None else min(best_score, 2)

    if best_score is None:
        return None

    return best_score, len(str(candidate["choice_name"]))


def find_search_candidates(query: str, *, limit: int = 25) -> list[dict[str, object]]:
    scored_matches: list[tuple[tuple[int, int], dict[str, object]]] = []
    for candidate in build_search_candidates():
        score = score_search_candidate(candidate, query)
        if score is None:
            continue
        scored_matches.append((score, candidate))

    scored_matches.sort(key=lambda item: (item[0][0], item[0][1], str(item[1]["choice_name"])))
    return [candidate for _, candidate in scored_matches[:limit]]


def resolve_search_selection(search_value: str | None) -> tuple[str, str | None, str | None, str | None] | None:
    route = parse_search_route(search_value)
    if route is not None:
        return route

    if not search_value:
        return None

    matches = find_search_candidates(search_value, limit=5)
    if len(matches) == 1:
        return parse_search_route(str(matches[0]["route"]))

    normalized_query = normalize_text(search_value)
    exact_matches = [
        candidate
        for candidate in matches
        if normalized_query in candidate.get("keywords", [])
    ]
    if len(exact_matches) == 1:
        return parse_search_route(str(exact_matches[0]["route"]))
    if exact_matches:
        ranked_matches = sorted(
            exact_matches,
            key=lambda candidate: (search_candidate_resolution_rank(candidate), str(candidate.get("choice_name", ""))),
        )
        if len(ranked_matches) == 1 or search_candidate_resolution_rank(ranked_matches[0]) < search_candidate_resolution_rank(
            ranked_matches[1]
        ):
            return parse_search_route(str(ranked_matches[0]["route"]))

    return None


def search_candidate_resolution_rank(candidate: dict[str, object]) -> tuple[int, int, int]:
    route = parse_search_route(str(candidate.get("route")))
    if route is None:
        return (3, 3, 3)

    _, section, topic, entry = route
    # Exact record selections should win over broader topic matches when the query is identical.
    return (
        0 if entry else 1,
        0 if topic else 1,
        0 if section else 1,
    )


def build_search_results_embed(search_value: str) -> discord.Embed:
    embed = discord.Embed(
        title="항목 검색 결과",
        description=f"`{search_value}`와 일치하는 후보입니다. `/도움`의 `항목검색` 자동완성에서 선택하면 바로 열 수 있어요.",
        color=0xFF00FF,
    )
    matches = find_search_candidates(search_value, limit=10)

    if not matches:
        embed.add_field(name="검색 결과", value="일치하는 항목이 없습니다.", inline=False)
        return embed

    lines = [
        f"- {candidate['display_name']} ({candidate['context']})"
        for candidate in matches
    ]
    embed.add_field(name="일치 후보", value="\n".join(lines), inline=False)
    return embed


def resolve_local_image_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None

    normalized = str(raw_path).strip()
    if not normalized or normalized.startswith(("http://", "https://")):
        return None

    relative_path = Path(normalized.lstrip("./\\"))
    candidate = (DATA_ROOT / relative_path).resolve()

    try:
        candidate.relative_to(DATA_ROOT.resolve())
    except ValueError:
        return None

    if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
        return candidate

    return None


def append_unique_image_path(image_paths: list[Path], raw_path: str | None):
    resolved_path = resolve_local_image_path(raw_path)
    if resolved_path and resolved_path not in image_paths:
        image_paths.append(resolved_path)


def collect_group_image_paths(groups: list[dict], image_paths: list[Path]):
    for group in groups[:25]:
        append_unique_image_path(image_paths, group.get("image"))


def collect_section_image_paths(sections: list[dict], image_paths: list[Path]):
    for section in sections[:25]:
        for card in section.get("cards", [])[:25]:
            append_unique_image_path(image_paths, card.get("image"))


def collect_record_entry_image_paths(topic_entry: dict, image_paths: list[Path]):
    for group, item in flatten_category_entries(topic_entry)[:GUIDE_IMAGE_LIMIT]:
        append_unique_image_path(image_paths, item.get("image"))


def collect_topic_image_paths(topic_entry: dict, image_paths: list[Path], entry: str | None = None):
    if topic_entry["id"] == "monsters" and topic_entry.get("monsters"):
        matched_monster = resolve_selected_monster(topic_entry["monsters"], entry)
        if matched_monster is not None:
            append_unique_image_path(image_paths, matched_monster.get("image"))
            return

        for monster in topic_entry["monsters"][:GUIDE_IMAGE_LIMIT]:
            append_unique_image_path(image_paths, monster.get("image"))
        return

    if category_has_record_entries(topic_entry):
        selected_record = resolve_selected_record_entry(topic_entry, entry)
        if selected_record is not None:
            _, matched_item = selected_record
            append_unique_image_path(image_paths, matched_item.get("image"))
            return

        collect_record_entry_image_paths(topic_entry, image_paths)
        return

    if topic_entry.get("sections"):
        collect_section_image_paths(topic_entry.get("sections", []), image_paths)
        return

    groups = topic_entry.get("groups", [])
    if topic_entry.get("entrySelectable") is False:
        collect_group_image_paths(groups, image_paths)
        return

    matched_group = resolve_selected_group(groups, entry)
    if matched_group is not None:
        append_unique_image_path(image_paths, matched_group.get("image"))
        return

    collect_group_image_paths(groups, image_paths)


def collect_game_browser_image_paths(
    game: str | None = None,
    section: str | None = None,
    topic: str | None = None,
    entry: str | None = None,
) -> list[Path]:
    if not game:
        return []

    data = load_game_data(game)
    image_paths: list[Path] = []
    resolved_section = resolve_section(section)
    profile_image = data.get("profileImage")

    if resolved_section in (None, "overview"):
        append_unique_image_path(image_paths, profile_image)
        return image_paths[:GUIDE_IMAGE_LIMIT]

    entries = get_section_entries(data, resolved_section)
    matched_entry = resolve_topic_entry(entries, topic)

    if should_render_all_guides_in_bot(data, resolved_section):
        for item in entries[:25]:
            collect_topic_image_paths(item, image_paths)
            if len(image_paths) >= GUIDE_IMAGE_LIMIT:
                break
        return image_paths[:GUIDE_IMAGE_LIMIT]

    if matched_entry is None:
        append_unique_image_path(image_paths, profile_image)
        return image_paths[:GUIDE_IMAGE_LIMIT]

    collect_topic_image_paths(matched_entry, image_paths, entry)
    return image_paths[:GUIDE_IMAGE_LIMIT]


def build_discord_image_files(image_paths: list[Path]) -> list[discord.File]:
    files: list[discord.File] = []
    for index, image_path in enumerate(image_paths[:GUIDE_IMAGE_LIMIT], start=1):
        filename = f"guide-image-{index}{image_path.suffix.lower()}"
        files.append(discord.File(str(image_path), filename=filename))
    return files


def build_game_browser_response(
    game: str | None = None,
    section: str | None = None,
    topic: str | None = None,
    entry: str | None = None,
) -> tuple[discord.Embed, list[discord.File]]:
    embed = build_game_browser_embed(game=game, section=section, topic=topic, entry=entry)
    data = load_game_data(game) if game else None
    resolved_section = resolve_section(section)

    if data and data.get("slug") == "Thunderstore" and resolved_section == "guides":
        embed.add_field(
            name="이미지 포함 게시물",
            value=build_game_page_link(data),
            inline=False,
        )
        return embed, []

    image_paths = collect_game_browser_image_paths(game=game, section=section, topic=topic, entry=entry)
    files = build_discord_image_files(image_paths)

    if files:
        embed.set_image(url=f"attachment://{files[0].filename}")
    elif game:
        embed.set_footer(text="이미지 없음")

    return embed, files


def list_game_catalog() -> list[dict[str, str]]:
    # docs/games 아래 JSON을 훑어 선택 메뉴에 표시할 최소 카탈로그 정보만 뽑습니다.
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


def topic_has_entries(topic_entry: dict) -> bool:
    if topic_entry.get("entrySelectable") is False:
        return False
    if topic_entry.get("id") == "monsters" and topic_entry.get("monsters"):
        return True
    if category_has_record_entries(topic_entry):
        return True
    return bool(topic_entry.get("groups"))


def build_group_display_value(group: dict) -> str:
    lines = [f"- {item}" for item in group.get("items", [])]
    if group.get("image"):
        lines.append(f"- 이미지: {group['image']}")
    return "\n".join(lines) or "-"


def build_section_display_value(section: dict) -> str:
    lines = [f"- {item}" for item in section.get("items", [])]
    for card in section.get("cards", [])[:25]:
        lines.append(f"- {format_bot_card_label(card)}")
        for item in card.get("items", []):
            if item:
                lines.append(f"  - {item}")
    return "\n".join(lines) or "-"


def format_bot_card_label(card: dict) -> str:
    label = str(card.get("label") or "").strip()
    if label:
        return label

    title = str(card.get("title") or "항목").strip()
    prefix = title.split(".", 1)[0].strip()
    return prefix or title


def should_render_all_guides_in_bot(data: dict, resolved_section: str | None) -> bool:
    return bool(data.get("botRenderAllGuides")) and resolved_section == "guides"


def clamp_field_value(value: str, limit: int = 1000) -> str:
    collapsed = value.strip()
    if len(collapsed) <= limit:
        return collapsed or "-"
    return f"{collapsed[: limit - 1]}…"


def safe_add_embed_field(embed: discord.Embed, *, name: str, value: str, inline: bool = False) -> bool:
    if len(embed.fields) >= EMBED_FIELD_LIMIT:
        return False
    embed.add_field(name=name[:256], value=clamp_field_value(value), inline=inline)
    return True


def build_entry_stats_field_value(entry: dict) -> str | None:
    stats = entry.get("stats", [])
    if not isinstance(stats, list):
        return None

    lines: list[str] = []
    for stat in stats:
        if not isinstance(stat, dict):
            continue
        label = " ".join(str(stat.get("label") or "").split())
        value = " ".join(str(stat.get("value") or "").split())
        if not label or not value:
            continue
        lines.append(f"- {label}: {value}")

    return "\n".join(lines) or None


def sanitize_discord_link_label(value: str | None) -> str:
    label = " ".join((value or "").split())
    return label.replace("[", "(").replace("]", ")") or "출처"


def build_entry_sources_field_value(entry: dict) -> str | None:
    sources = entry.get("sources", [])
    if not isinstance(sources, list):
        return None

    lines: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if not is_http_url(url):
            continue

        label = sanitize_discord_link_label(source.get("label"))
        checked_at = " ".join(str(source.get("checkedAt") or "").split())
        line = f"- [{label}]({url})"
        if checked_at:
            line = f"{line} ({checked_at})"
        lines.append(line)

    return "\n".join(lines) or None


def add_topic_fields_to_embed(embed: discord.Embed, topic_entry: dict):
    # Discord 임베드의 필드 제한을 고려해 섹션/본문/그룹 데이터를 최대 25개씩만 추가합니다.
    if topic_entry.get("sections"):
        for section in topic_entry.get("sections", [])[:25]:
            if not safe_add_embed_field(
                embed,
                name=f"{topic_entry['label']} · {section['title']}",
                value=clamp_field_value(build_section_display_value(section)),
                inline=False,
            ):
                return
        return

    if topic_entry.get("content"):
        for item in topic_entry.get("content", [])[:25]:
            body = item.get("body") or "-"
            if not safe_add_embed_field(
                embed,
                name=f"{topic_entry['label']} · {item.get('title', topic_entry['title'])}",
                value=clamp_field_value(body),
                inline=False,
            ):
                return
        return

    if topic_entry.get("groups"):
        for group in topic_entry.get("groups", [])[:25]:
            if not safe_add_embed_field(
                embed,
                name=f"{topic_entry['label']} · {group['title']}",
                value=clamp_field_value(build_group_display_value(group)),
                inline=False,
            ):
                return


def category_has_record_entries(category: dict) -> bool:
    return any(group.get("entries") for group in category.get("groups", []))


def flatten_category_entries(category: dict) -> list[tuple[dict, dict]]:
    # 지도/아이템/모드처럼 group.entries 구조인 카테고리를 선택 메뉴용 단일 목록으로 펼칩니다.
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
            *flatten_entry_aliases(item),
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
    # 구조화된 레코드 항목을 가격, 명령어, 설명, 링크 순서로 Discord 임베드 필드에 배치합니다.
    name = item.get("name", item.get("id", "-"))
    name_kr = item.get("nameKr")
    if name_kr:
        safe_add_embed_field(embed, name="한글 이름", value=name_kr, inline=False)
        safe_add_embed_field(embed, name="영문 이름", value=name, inline=False)
    else:
        safe_add_embed_field(embed, name="이름", value=name, inline=False)

    if group.get("title"):
        safe_add_embed_field(embed, name="구분", value=group["title"], inline=False)

    stats_value = build_entry_stats_field_value(item)
    if stats_value:
        safe_add_embed_field(embed, name="핵심 정보", value=stats_value, inline=False)

    if category_id == "maps":
        safe_add_embed_field(embed, name="입장료", value=str(item.get("price", "-")), inline=False)
    elif "price" in item:
        safe_add_embed_field(embed, name="가격", value=str(item.get("price", "-")), inline=False)
    elif "priceRange" in item:
        safe_add_embed_field(embed, name="가격대", value=str(item.get("priceRange", "-")), inline=False)

    if item.get("terminalCommand"):
        safe_add_embed_field(embed, name="터미널 명령어", value=item["terminalCommand"], inline=False)

    if item.get("description"):
        safe_add_embed_field(embed, name="설명", value=item["description"], inline=False)

    if item.get("usage"):
        safe_add_embed_field(embed, name="사용법", value=item["usage"], inline=False)

    if item.get("spawnMonsters"):
        safe_add_embed_field(embed, name="출현 몬스터 및 확률", value=build_spawn_lines(item["spawnMonsters"]), inline=False)

    install_link = item.get("installLink")
    if install_link:
        safe_add_embed_field(embed, name="설치 링크", value=install_link, inline=False)

    sources_value = build_entry_sources_field_value(item)
    if sources_value:
        safe_add_embed_field(embed, name="출처", value=sources_value, inline=False)

    safe_add_embed_field(
        embed,
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
    # 현재 선택 상태(game/section/topic/entry)에 맞춰 탐색 화면 또는 상세 화면 임베드를 생성합니다.
    if not game:
        embed = discord.Embed(
            title="연삼이의 도움말",
            description="아래 선택 메뉴에서 문서를 고르면 `구역 -> 주제 -> 항목` 순서로 이어서 클릭할 수 있습니다.",
            color=0xFF00FF,
        )
        catalog = list_game_catalog()
        if catalog:
            embed.add_field(
                name="등록된 문서",
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
            value="`구역 선택` 메뉴에서 `개요`, `공략` 중 하나를 고르세요.",
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

    if should_render_all_guides_in_bot(data, resolved_section):
        embed.description = f"{data['name']} - 전체 가이드"
        for item in entries[:25]:
            add_topic_fields_to_embed(embed, item)
        return embed

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
            add_monster_research_fields(embed, matched_entry.get("research"))
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
        if matched_monster.get("health"):
            embed.add_field(
                name="체력·처치",
                value=clamp_field_value(str(matched_monster["health"])),
                inline=False,
            )
        if matched_monster.get("spawn"):
            embed.add_field(
                name="출현",
                value=clamp_field_value(str(matched_monster["spawn"])),
                inline=False,
            )
        if matched_monster.get("detection"):
            embed.add_field(
                name="감지·발동",
                value=clamp_field_value(str(matched_monster["detection"])),
                inline=False,
            )
        if matched_monster.get("damage"):
            embed.add_field(
                name="피해",
                value=clamp_field_value(str(matched_monster["damage"])),
                inline=False,
            )
        if matched_monster.get("strength"):
            embed.add_field(
                name="잡기 요구 힘",
                value=clamp_field_value(str(matched_monster["strength"])),
                inline=False,
            )
        if matched_monster.get("stun"):
            embed.add_field(
                name="기절",
                value=clamp_field_value(str(matched_monster["stun"])),
                inline=False,
            )
        embed.add_field(
            name="설명",
            value=clamp_field_value(str(matched_monster["description"])),
            inline=False,
        )
        embed.add_field(
            name="공략",
            value=clamp_field_value(str(matched_monster["strategy"])),
            inline=False,
        )
        if matched_monster.get("threatLevel"):
            embed.add_field(name="위협도", value=str(matched_monster["threatLevel"]), inline=False)
        if matched_monster.get("cashDrop"):
            embed.add_field(
                name="드롭",
                value=clamp_field_value(str(matched_monster["cashDrop"])),
                inline=False,
            )
        if matched_monster.get("loot"):
            embed.add_field(
                name="전리품",
                value=clamp_field_value(str(matched_monster["loot"])),
                inline=False,
            )
        if matched_monster.get("versionNote"):
            embed.add_field(
                name="버전 주의",
                value=clamp_field_value(str(matched_monster["versionNote"])),
                inline=False,
            )
        add_monster_research_fields(embed, matched_entry.get("research"))
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

    if matched_entry.get("content"):
        embed.add_field(
            name=matched_entry["title"],
            value="\n".join(f"- {item}" for item in matched_entry["content"]),
            inline=False,
        )
        return embed

    if matched_entry.get("sections"):
        for section in matched_entry.get("sections", [])[:25]:
            embed.add_field(
                name=section["title"],
                value=build_section_display_value(section),
                inline=False,
            )
        return embed

    groups = matched_entry.get("groups", [])
    if matched_entry.get("entrySelectable") is False:
        for group in groups[:25]:
            embed.add_field(
                name=group["title"],
                value=build_group_display_value(group),
                inline=False,
            )
        return embed

    matched_group = resolve_selected_group(groups, entry)
    if matched_group is None:
        for group in groups[:25]:
            embed.add_field(
                name=group["title"],
                value=build_group_display_value(group),
                inline=False,
            )
        return embed

    embed.description = f"{data['name']} - {matched_entry['label']} - {matched_group['title']}"
    embed.add_field(
        name=matched_group["title"],
        value=build_group_display_value(matched_group),
        inline=False,
    )
    return embed


def build_disabled_select_options(label: str) -> list[discord.SelectOption]:
    return [discord.SelectOption(label=label, value="__disabled__")]


def draw_random_numbers(start: int, end: int, count: int) -> list[int]:
    return [random.randint(start, end) for _ in range(count)]


def build_random_numbers_embed(
    start: int,
    end: int,
    count: int,
    numbers: list[int] | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="랜덤 숫자",
        color=0x57F287,
    )
    embed.add_field(name="범위", value=f"{start} ~ {end}", inline=True)
    embed.add_field(name="개수", value=str(count), inline=True)

    if numbers is None:
        embed.description = "버튼을 눌러 숫자를 뽑아보세요."
        return embed

    if count == 1:
        embed.description = f"**{numbers[0]}**"
        return embed

    embed.description = ", ".join(str(number) for number in numbers)
    return embed


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
        # 선택 메뉴가 바뀐 뒤 더 이상 유효하지 않은 하위 선택값을 정리합니다.
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

        if should_render_all_guides_in_bot(self.data, self.section):
            self.topic = None
            self.entry = None
            return

        entries = get_section_entries(self.data, self.section)
        self.topic_entry = resolve_topic_entry(entries, self.topic)
        if self.topic_entry is None:
            self.topic = None
            self.entry = None
            return

        if not topic_has_entries(self.topic_entry):
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
        # 게임 -> 구역 -> 주제 -> 항목 순서의 Select와 조회/초기화 버튼을 한 화면에 배치합니다.
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

    def build_response(self) -> tuple[discord.Embed, list[discord.File]]:
        return build_game_browser_response(
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
            return build_disabled_select_options("먼저 문서와 구역을 선택하세요")

        options: list[discord.SelectOption] = []
        for item in get_section_entries(self.data, self.section)[:25]:
            extra_count = len(item.get("monsters", item.get("groups", []))) or len(item.get("content", []))
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

        if not topic_has_entries(self.topic_entry):
            return build_disabled_select_options("선택 가능한 항목이 없습니다")

        if self.topic_entry["id"] == "monsters" and self.topic_entry.get("monsters"):
            options: list[discord.SelectOption] = []
            monsters = self.topic_entry["monsters"]
            visible_monsters = monsters[:25]
            selected_monster = resolve_selected_monster(monsters, self.entry)
            if selected_monster is not None and selected_monster not in visible_monsters:
                visible_monsters = [*visible_monsters[:24], selected_monster]

            for monster in visible_monsters:
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
        # 조회 버튼은 현재 선택 상태를 반영한 새 임베드까지 함께 갱신합니다.
        view = GameBrowserView(
            user_id=self.user_id,
            game=self.game,
            section=self.section,
            topic=self.topic,
            entry=self.entry,
        )
        embed, files = view.build_response()
        await interaction.response.edit_message(embed=embed, attachments=files, view=view)

    async def refresh_controls(self, interaction: discord.Interaction):
        # Select 변경 중에는 임베드 본문을 유지하고 다음 단계 컨트롤만 갱신합니다.
        view = GameBrowserView(
            user_id=self.user_id,
            game=self.game,
            section=self.section,
            topic=self.topic,
            entry=self.entry,
        )
        await interaction.response.edit_message(view=view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # 다른 사용자가 남의 탐색 메뉴를 조작하지 못하게 ephemeral 경고로 막습니다.
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
            placeholder="문서 선택",
            min_values=1,
            max_values=1,
            options=game_view.game_options() or build_disabled_select_options("등록된 문서가 없습니다"),
            row=0,
            disabled=not game_view.catalog,
        )

    async def callback(self, interaction: discord.Interaction):
        # 상위 게임이 바뀌면 하위 선택은 모두 이전 게임 기준이므로 초기화합니다.
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
            options=game_view.section_options() if has_game else build_disabled_select_options("먼저 문서를 선택하세요"),
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
        enabled = (
            game_view.data is not None
            and game_view.section not in (None, "overview")
            and not should_render_all_guides_in_bot(game_view.data, game_view.section)
        )
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
            disabled=game_view.topic_entry is None or not topic_has_entries(game_view.topic_entry),
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
        embed, files = view.build_response()
        await interaction.response.edit_message(embed=embed, attachments=files, view=view)


class RandomNumberView(discord.ui.View):
    def __init__(self, user_id: int, start: int, end: int, count: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.start = start
        self.end = end
        self.count = count
        self.add_item(DrawRandomNumbersButton())

    def build_embed(self, numbers: list[int] | None = None) -> discord.Embed:
        return build_random_numbers_embed(
            start=self.start,
            end=self.end,
            count=self.count,
            numbers=numbers,
        )

    async def refresh_message(self, interaction: discord.Interaction):
        numbers = draw_random_numbers(self.start, self.end, self.count)
        await interaction.response.edit_message(
            embed=self.build_embed(numbers),
            view=self,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "이 버튼은 명령어를 실행한 사용자만 사용할 수 있어요.",
                ephemeral=True,
            )
            return False
        return True


class DrawRandomNumbersButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="숫자 뽑기",
            style=discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, RandomNumberView):
            await interaction.response.defer()
            return

        await view.refresh_message(interaction)


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
        # 관리자 모달 입력값을 길드 설정에 저장하고 즉시 미리보기 임베드를 돌려줍니다.
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

        # 관리자에게만 환영 메시지 설정 버튼을 노출하고, 일반 사용자는 프로필 수정만 제공합니다.
        if is_admin:
            self.add_item(EditMessageButton(guild_id))

        self.add_item(ProfileButton())


class Yeonsam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="랜덤", description="입력한 범위와 개수로 랜덤 숫자를 출력합니다.")
    @app_commands.describe(
        start="시작 숫자입니다. 최소 1입니다.",
        end="끝 숫자입니다. 최대 100입니다.",
        count="한 번에 출력할 숫자 개수입니다.",
    )
    @app_commands.rename(start="시작", end="끝", count="개수")
    async def random_numbers(
        self,
        interaction: discord.Interaction,
        start: app_commands.Range[int, 1, RANDOM_NUMBER_LIMIT] = 1,
        end: app_commands.Range[int, 1, RANDOM_NUMBER_LIMIT] = RANDOM_NUMBER_LIMIT,
        count: app_commands.Range[int, 1, RANDOM_NUMBER_LIMIT] = 1,
    ):
        if start > end:
            await interaction.response.send_message(
                "시작 숫자는 끝 숫자보다 클 수 없어요.",
                ephemeral=True,
            )
            return

        view = RandomNumberView(
            user_id=interaction.user.id,
            start=start,
            end=end,
            count=count,
        )
        numbers = draw_random_numbers(start, end, count)
        await interaction.response.send_message(
            embed=view.build_embed(numbers),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="연삼", description="연삼 봇 안내를 표시합니다.")
    async def yeonsam(self, interaction: discord.Interaction):
        # 길드별 안내 문구와 설정 버튼을 보여주는 기본 진입 명령어입니다.
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
            name="/설정 · /초대",
            value=(
                "관리자는 `/설정`에서 환영 채널, 문구·링크, 권한 진단과 테스트 발송을 순서대로 진행합니다.\n"
                "`/초대`는 연삼이를 다른 서버에 설치하는 최소 권한 링크를 표시합니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="/도움 [항목검색]",
            value=(
                "명령어 입력 후 선택 메뉴가 열립니다.\n"
                "`문서 -> 구역 -> 주제 -> 항목` 순서로 클릭해서 탐색합니다.\n"
                "예: `항목검색: 배그`를 입력하면 PUBG BATTLE GROUND 가이드를 바로 엽니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="/무료게임 · /무료알림설정",
            value=(
                "현재 Steam 기간 한정 무료 배포 목록은 `/무료게임`으로 조회합니다.\n"
                "관리자는 `/무료알림설정`, `/무료알림상태`, `/무료알림해제`로 자동 알림 채널을 관리합니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="/패치알림설정",
            value=(
                "관리자가 Lethal Company 또는 R.E.P.O.의 공식 Steam 업데이트 알림 채널을 지정합니다.\n"
                "`/패치알림목록`, `/패치알림테스트`, `/패치알림해제`로 점검·관리할 수 있습니다."
            ),
            inline=False,
        )
        embed.add_field(
            name="/스팀인기게임 [표시개수]",
            value="Steam 공식 Most Played 기준 인기 게임 TOP 5 또는 TOP 10을 확인합니다.",
            inline=False,
        )
        embed.add_field(
            name="예시",
            value=(
                "1. `/설정`으로 환영 메시지를 테스트 발송\n"
                "2. `/무료알림설정` 또는 `/패치알림설정`으로 운영 채널 연결\n"
                "3. `/도움 항목검색: 배그`처럼 원하는 공략을 바로 검색"
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

    async def help_search_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        matches = find_search_candidates(current, limit=25)
        return [
            app_commands.Choice(name=str(candidate["choice_name"]), value=str(candidate["route"]))
            for candidate in matches
        ]

    @app_commands.command(name="도움", description="등록된 문서를 선택형 UI로 보거나 항목검색으로 바로 엽니다.")
    @app_commands.describe(search_query="항목 이름을 입력하면 자동완성으로 일치 후보가 표시됩니다.")
    @app_commands.rename(search_query="항목검색")
    @app_commands.autocomplete(search_query=help_search_autocomplete)
    async def yeonsam_game(self, interaction: discord.Interaction, search_query: str | None = None):
        # JSON 기반 가이드 탐색기를 ephemeral 메시지로 열어 개인별 선택 상태를 유지합니다.
        route = resolve_search_selection(search_query)
        if route is not None:
            game, section, topic, entry = route
            view = GameBrowserView(
                user_id=interaction.user.id,
                game=game,
                section=section,
                topic=topic,
                entry=entry,
            )
            embed, files = view.build_response()
        else:
            view = GameBrowserView(user_id=interaction.user.id)
            embed, files = view.build_response()
            if search_query:
                embed = build_search_results_embed(search_query)
                files = []
                if not find_search_candidates(search_query, limit=1):
                    record_metric(
                        "search_no_result",
                        interaction.guild.id if interaction.guild else None,
                    )
        await interaction.response.send_message(
            embed=embed,
            files=files,
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="연삼환영디버그", description="환영 메시지 화면을 테스트합니다.")
    @app_commands.default_permissions(administrator=True)
    async def yeonsam_debug(self, interaction: discord.Interaction):
        # 실제 입장 이벤트를 기다리지 않고 현재 사용자를 기준으로 환영 메시지를 미리 확인합니다.
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
        # 운영 중인 봇의 길드/명령어/설정 상태를 JSON으로 묶어 관리자에게만 보여줍니다.
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
            "storage_file": str(Path(GUILD_CONFIG_FILE)),
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
