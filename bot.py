from __future__ import annotations

import discord
from discord.ext import commands

from discord_setup import configure_bot
from file_index import load_token


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    configure_bot(bot)
    return bot


def main() -> None:
    token = load_token()
    bot = create_bot()
    try:
        bot.run(token)
    except Exception as exc:
        print(f"Error running bot: {exc}")


if __name__ == "__main__":
    main()
