import discord

from utils.storage import get_guild


def build_welcome_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    config = get_guild(guild.id)
    message = config["welcome_message"].replace("{server}", guild.name)

    embed = discord.Embed(
        title="Welcome",
        description=f"{member.mention}\n{message}",
        color=0x5865F2,
    )
    if config.get("link"):
        embed.add_field(
            name="서버 안내",
            value=f"[안내 페이지 열기]({config['link']})",
            inline=False,
        )
    return embed
