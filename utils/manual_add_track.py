#!/usr/bin/env python3
"""
Send a single DM to a Discord user by ID. Does not modify track.json — the user
completes setup with the bot (e.g. !track) as usual.

  python -m utils.manual_add_track <discord_user_id>

Requires DISCORD_TOKEN in .env (same as the bot).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

TRACKER_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("manual_add_track")

DEFAULT_MESSAGE = (
    "You can set up leaderboard tracking with this bot. "
    "Send `!track` here to get started."
)


def parse_args():
    if len(sys.argv) != 2:
        log.error("Usage: python -m utils.manual_add_track <discord_user_id>")
        sys.exit(1)
    try:
        return int(sys.argv[1])
    except ValueError:
        log.error("Argument must be a numeric Discord user ID.")
        sys.exit(1)


async def main() -> int:
    discord_id = parse_args()

    from dotenv import load_dotenv

    load_dotenv(TRACKER_ROOT / ".env")
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        log.error("DISCORD_TOKEN not set in .env")
        return 1

    import discord

    intents = discord.Intents.default()
    intents.dm_messages = True
    client = discord.Client(intents=intents)
    exit_code = 0

    @client.event
    async def on_ready():
        nonlocal exit_code
        if not client.user:
            return
        try:
            user = await client.fetch_user(discord_id)
        except discord.NotFound:
            log.error("Discord user not found for that ID.")
            exit_code = 1
            await client.close()
            return

        try:
            await user.send(DEFAULT_MESSAGE)
            log.info("Sent DM.")
        except discord.Forbidden:
            log.error(
                "Could not DM this user (they may have DMs disabled or blocked the bot)."
            )
            exit_code = 1
        except Exception as e:
            log.error(f"Failed to send DM: {e}")
            exit_code = 1

        await client.close()

    try:
        await client.start(token)
    finally:
        if not client.is_closed():
            await client.close()
        # Let aiohttp close the connector before the loop stops (avoids "Unclosed connector").
        await asyncio.sleep(0.25)

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
