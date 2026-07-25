import unittest

from utils.storage import ensure_guild, update_guild
from utils.welcome_message import build_welcome_embed


class FakeGuild:
    id = 900
    name = "테스트 서버"


class FakeMember:
    mention = "<@901>"


class WelcomeMessageTests(unittest.TestCase):
    def test_welcome_embed_includes_configured_link(self):
        ensure_guild(FakeGuild.id)
        update_guild(FakeGuild.id, "welcome_message", "{server} 환영합니다.")
        update_guild(FakeGuild.id, "link", "https://example.com/guide")

        embed = build_welcome_embed(FakeGuild(), FakeMember())

        self.assertIn("테스트 서버 환영합니다.", embed.description)
        self.assertEqual(embed.fields[0].name, "서버 안내")
        self.assertIn("https://example.com/guide", embed.fields[0].value)


if __name__ == "__main__":
    unittest.main()
