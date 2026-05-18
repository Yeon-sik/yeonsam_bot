import discord

from utils.storage import get_guild


def build_welcome_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    # 길드별 환영 문구에 서버명을 치환해 새 멤버에게 보낼 임베드를 조립합니다.
    config = get_guild(guild.id)
    message = config["welcome_message"].replace("{server}", guild.name)

    return discord.Embed(
        title="Welcome",
        description=f"{member.mention}\n{message}",
        color=0x5865F2,
    )
