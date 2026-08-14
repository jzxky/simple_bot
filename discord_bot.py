"""
discord_bot.py — Discord bot that queries the player database.

Run standalone:  python discord_bot.py

Requires DISCORD_BOT_TOKEN in .env.  Optionally set DISCORD_CHANNEL_ID
to restrict responses to a single channel.

Adding a new command: define a function decorated with @bot.command()
and it will be available as !commandname in Discord.
"""

import os
import sys
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
import discord
from discord.ext import commands

import player_db

load_dotenv()

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "")

TOP_JOBS = [
    "Hospital Director", "Fire Chief", "Bank Manager",
    "Funeral Director", "Chief Engineer", "Commissioner-General",
]
_RANK_JOBS = {"Commissioner-General"}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def _format_duration(seconds):
    if seconds is None:
        return "unknown"
    days, rem = divmod(int(seconds), 86400)
    hours, _ = divmod(rem, 3600)
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h"


def _channel_ok(ctx):
    if not CHANNEL_ID:
        return True
    return str(ctx.channel.id) == CHANNEL_ID


@bot.command(name="topjobs")
async def topjobs(ctx):
    """Show who holds top jobs in each city and how long they've held them."""
    if not _channel_ok(ctx):
        return

    now_utc = datetime.now(timezone.utc)
    all_players = player_db.get_all_players()
    holders = [
        p for p in all_players
        if (p.get("occupation") in TOP_JOBS or p.get("rank") in _RANK_JOBS)
        and p.get("active", 1)
    ]

    by_city = {}
    for p in holders:
        matched_job = p.get("rank") if p.get("rank") in _RANK_JOBS else p.get("occupation")
        history = player_db.get_career_history(p["username"])
        duration_secs = None
        for entry in history:
            if entry.get("occupation") == p["occupation"] and entry.get("homecity") == p.get("homecity"):
                ts = entry.get("ts", "")
                if ts:
                    try:
                        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        duration_secs = max(0, int((now_utc - dt).total_seconds()))
                    except Exception:
                        pass
                break

        city = p.get("homecity", "Unknown")
        by_city.setdefault(city, []).append({
            "username": p["username"],
            "job": matched_job,
            "duration": _format_duration(duration_secs),
        })

    if not by_city:
        await ctx.send("No top job holders found.")
        return

    lines = []
    for city in sorted(by_city):
        lines.append(f"**{city}**")
        for h in sorted(by_city[city], key=lambda x: x["job"]):
            lines.append(f"  {h['job']}: {h['username']} ({h['duration']})")
    lines.append("")

    msg = "\n".join(lines)
    if len(msg) > 1900:
        for i in range(0, len(msg), 1900):
            await ctx.send(msg[i:i + 1900])
    else:
        await ctx.send(msg)


@bot.command(name="player")
async def player(ctx, *, name: str = ""):
    """Look up a character by name. Does not include character history."""
    if not _channel_ok(ctx):
        return
    if not name:
        await ctx.send("Usage: `!player <character name>`")
        return

    all_players = player_db.get_all_players()
    match = None
    for p in all_players:
        if p.get("username", "").lower() == name.lower():
            match = p
            break

    if not match:
        await ctx.send(f"No player found matching **{name}**.")
        return

    embed = discord.Embed(
        title=match["username"],
        color=discord.Color.blurple(),
    )

    fields = [
        ("Home City", match.get("homecity")),
        ("Occupation", match.get("occupation")),
        ("Rank", match.get("rank")),
        ("Active", "Yes" if match.get("active", 1) else "No"),
        ("Group", match.get("group_name")),
        ("Alias", match.get("alias")),
        ("Sex", match.get("sex")),
        ("Wealth", match.get("wealth")),
        ("Character Age", match.get("character_age")),
        ("Crew", match.get("crew_name")),
        ("Godfather", match.get("godfather")),
    ]

    for label, value in fields:
        if value:
            embed.add_field(name=label, value=str(value), inline=True)

    await ctx.send(embed=embed)


@bot.event
async def on_ready():
    print(f"Discord bot connected as {bot.user}")


if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_BOT_TOKEN not set in .env")
        sys.exit(1)
    bot.run(TOKEN)
