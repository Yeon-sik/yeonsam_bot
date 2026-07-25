import unittest
from urllib.parse import parse_qs, urlparse

from utils.invite import BOT_INVITE_PERMISSIONS, build_invite_url


class InviteUrlTests(unittest.TestCase):
    def test_invite_uses_minimum_declared_permissions(self):
        url = build_invite_url(123456789012345678)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "discord.com")
        self.assertEqual(query["client_id"], ["123456789012345678"])
        self.assertEqual(query["scope"], ["bot applications.commands"])
        self.assertEqual(query["permissions"], [str(BOT_INVITE_PERMISSIONS)])
        self.assertEqual(BOT_INVITE_PERMISSIONS, 134269952)


if __name__ == "__main__":
    unittest.main()
