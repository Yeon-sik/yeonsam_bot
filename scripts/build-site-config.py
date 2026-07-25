import argparse
import json
import os
from pathlib import Path


DEFAULT_SUPPORT_URL = "https://github.com/Yeon-sik/yeonsam_bot/issues"


def build_config() -> dict[str, str]:
    return {
        "discordApplicationId": os.getenv("DISCORD_APPLICATION_ID", "").strip(),
        "supportUrl": os.getenv("SUPPORT_SERVER_URL", DEFAULT_SUPPORT_URL).strip()
        or DEFAULT_SUPPORT_URL,
        "botHealthUrl": os.getenv("BOT_HEALTH_URL", "").strip(),
    }


def render_config(config: dict[str, str]) -> str:
    payload = json.dumps(config, ensure_ascii=False, indent=4)
    return f"window.YEONSAM_SITE_CONFIG = Object.freeze({payload});\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="docs/assets/site-config.js",
        help="생성할 공개 사이트 설정 파일 경로",
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_config(build_config()), encoding="utf-8")


if __name__ == "__main__":
    main()
