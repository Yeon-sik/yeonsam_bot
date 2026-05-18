import discord
from discord.ext import commands

from utils.profile import update_member_nickname
from utils.welcome_message import build_welcome_embed


class ProfileButton(discord.ui.Button):
    def __init__(self):
        # timeout 없는 WelcomeView에서도 버튼이 재시작 후 유지되도록 custom_id를 고정합니다.
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

        # 사용자가 입력한 닉네임은 제출 시 권한 검사를 거쳐 서버 닉네임으로 반영됩니다.
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
        # 환영 메시지에 붙는 persistent view입니다. 봇 재시작 후에도 버튼 상호작용을 받을 수 있습니다.
        super().__init__(timeout=None)
        self.add_item(ProfileButton())


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # 새 멤버가 들어오면 서버의 system_channel에 환영 임베드와 프로필 수정 버튼을 보냅니다.
        channel = member.guild.system_channel
        if channel is None:
            return

        embed = build_welcome_embed(member.guild, member)
        await channel.send(embed=embed, view=WelcomeView())


async def setup(bot):
    await bot.add_cog(Welcome(bot))
