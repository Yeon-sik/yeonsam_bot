from urllib.parse import urlencode


# View Channel, Send Messages, Embed Links, Attach Files, Manage Nicknames
BOT_INVITE_PERMISSIONS = 134269952


def build_invite_url(application_id: int | str) -> str:
    query = urlencode(
        {
            "client_id": str(application_id),
            "scope": "bot applications.commands",
            "permissions": str(BOT_INVITE_PERMISSIONS),
        }
    )
    return f"https://discord.com/oauth2/authorize?{query}"
