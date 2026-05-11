import discord
from discord.ext import commands

from utils.profile import update_member_nickname
from utils.welcome_message import build_welcome_embed


class ProfileButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="서버 프로필 수정",
            style=discord.ButtonStyle.secondary,
            custom_id="welcome:edit_server_profile",
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


class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProfileButton())


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = member.guild.system_channel
        if channel is None:
            return

        embed = build_welcome_embed(member.guild, member)
        await channel.send(embed=embed, view=WelcomeView())


async def setup(bot):
    await bot.add_cog(Welcome(bot))
