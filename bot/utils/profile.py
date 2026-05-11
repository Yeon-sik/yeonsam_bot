import discord


async def update_member_nickname(
    interaction: discord.Interaction,
    nickname: str,
) -> tuple[bool, str]:
    guild = interaction.guild
    if guild is None:
        return False, "You can only change your server profile inside a server."

    member = interaction.user
    if not isinstance(member, discord.Member):
        member = guild.get_member(interaction.user.id)

    bot_member = guild.me
    if member is None or bot_member is None:
        return False, "Could not load member information. Please try again."

    if not bot_member.guild_permissions.manage_nicknames:
        return False, "The bot needs the Manage Nicknames permission to update server profiles."

    if member == guild.owner:
        return False, "The bot cannot change the server owner's nickname."

    if member.top_role >= bot_member.top_role:
        return False, "The bot role must be higher than your top role to change your server profile."

    try:
        await member.edit(
            nick=nickname,
            reason="User requested nickname update via profile modal",
        )
    except discord.Forbidden:
        return False, "Discord blocked the nickname change. Please check the bot role order and permissions."
    except discord.HTTPException:
        return False, "Discord could not update the nickname right now. Please try again."

    return True, f"Your server profile was updated to '{nickname}'."
