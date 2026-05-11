import discord

from utils.storage import get_guild


def build_welcome_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    config = get_guild(guild.id)
    message = config["welcome_message"].replace("{server}", guild.name)

    return discord.Embed(
        title="Welcome",
        description=f"{member.mention}\n{message}",
        color=0x5865F2,
    )
