import discord
from discord.utils import escape_markdown
from discord.ext import commands, tasks
import requests
import os
import json
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

LOG_FILE = os.path.join(os.path.dirname(__file__), "tracker.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("tracker")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
HC_API_URL = os.getenv("HC_API_URL")
SITE_EMAIL = os.getenv("SITE_EMAIL", "").strip()
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "").strip()

if not DISCORD_TOKEN or not HC_API_URL:
    log.error("Missing keys in .env file (need DISCORD_TOKEN and HC_API_URL).")
    exit()

TOP_PER_PAGE = 10


def format_leaderboard_text(teams, max_name_len=40):
    """One line per team in embed description — layout is ours; Discord can't split into columns."""
    header = "**Rank** — **Name** — **Score**"
    lines = []
    for i, t in enumerate(teams, start=1):
        name = str(t["name"]).replace("\n", " ").strip()
        if len(name) > max_name_len:
            name = name[: max_name_len - 1] + "…"
        name = escape_markdown(name)
        score = str(t["score"])
        lines.append(f"{i}. {name} — {score}")
    return header + "\n" + "\n".join(lines)


HTTP = requests.Session()
CURRENT_USER_ID = None
CHALL_JSON = os.path.join(os.path.dirname(__file__), "chall.json")
TRACK_JSON = os.path.join(os.path.dirname(__file__), "track.json")
conversations = {}

HTTP.headers.update(
    {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
)
_origin = urlparse(HC_API_URL)
if _origin.scheme and _origin.netloc:
    HTTP.headers["Referer"] = f"{_origin.scheme}://{_origin.netloc}/"


def load_chall():
    try:
        with open(CHALL_JSON, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"competitions": {}}


def save_chall(data):
    with open(CHALL_JSON, "w") as f:
        json.dump(data, f, indent=2)


def load_track():
    try:
        with open(TRACK_JSON, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"tracking": {}}
    data.setdefault("tracking", {})
    data.setdefault("challenge_notif_subscribers", [])
    return data


def save_track(data):
    with open(TRACK_JSON, "w") as f:
        json.dump(data, f, indent=2)


def get_team_id(competition_id):
    global CURRENT_USER_ID
    try:
        resp = HTTP.get(
            f"{HC_API_URL}/competitions/{competition_id}/teams/me", timeout=15
        )
        if resp.status_code != 200:
            log.warning(
                f"teams/me returned {resp.status_code} for competition {competition_id}"
            )
            return None
        data = resp.json()
        if CURRENT_USER_ID is None:
            CURRENT_USER_ID = data["admin_id"]
            log.info(f"Fetched user ID: {CURRENT_USER_ID}")
        return data["team_id"]
    except Exception as e:
        log.error(f"Failed to get team_id for competition {competition_id}: {e}")
        return None


def is_active(comp):
    if not comp.get("public"):
        return False
    now = datetime.now(timezone.utc)
    start = comp["start_time"]
    end = comp["end_time"]
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    return start_dt <= now <= end_dt


def fetch_all_teams(competition_id):
    teams = []
    page = 0
    while True:
        try:
            resp = HTTP.get(
                f"{HC_API_URL}/competitions/{competition_id}/teams?page={page}&per_page=10&training=",
                timeout=15,
            )
            if resp.status_code != 200:
                log.warning(
                    f"Failed to fetch teams page {page}: HTTP {resp.status_code}"
                )
                break
            batch = resp.json()["teams"]
            if not batch:
                break
            teams.extend(batch)
            page += 1
        except Exception as e:
            log.error(f"Error fetching teams page {page}: {e}")
            break
    log.info(f"Fetched {len(teams)} teams for competition {competition_id}")
    return teams


def safe_cookie_get(name):
    for cookie in HTTP.cookies:
        if cookie.name == name:
            return cookie.value
    return ""


def login():
    if not SITE_EMAIL or not SITE_PASSWORD:
        log.error("Missing SITE_EMAIL/SITE_PASSWORD")
        return False, "missing SITE_EMAIL/SITE_PASSWORD"

    log.info(f"Logging in as {SITE_EMAIL}")
    HTTP.cookies.clear()
    HTTP.get(f"{HC_API_URL}/", timeout=15)
    csrf = safe_cookie_get("token")

    payload = {"email": SITE_EMAIL, "password": SITE_PASSWORD}
    if csrf:
        payload["token"] = csrf

    try:
        resp = HTTP.post(f"{HC_API_URL}/users/login", data=payload, timeout=15)

        if resp.status_code == 302:
            log.info("Login successful (redirect)")
            return True, "redirect ok"

        if resp.status_code != 200:
            log.error(f"Login failed: HTTP {resp.status_code}")
            return False, f"status {resp.status_code}"

        try:
            data = resp.json()
            if data.get("success") is False:
                log.error(f"Login rejected: {data.get('message', 'unknown')}")
                return False, data.get("message", "login failed")
        except ValueError:
            pass

        log.info("Login successful")
        return True, "logged in"
    except Exception as e:
        log.error(f"Login request failed: {e}")
        return False, str(e)


def resolve_competition(override_id=None):
    if override_id is not None:
        return override_id, None

    try:
        resp = HTTP.get(
            f"{HC_API_URL}/users/{CURRENT_USER_ID}/competitions", timeout=15
        )
        resp.raise_for_status()
        competitions = resp.json()["competitions"]
    except Exception as e:
        log.error(f"Failed to fetch competitions: {e}")
        raise

    active = [c for c in competitions if is_active(c)]
    if active:
        c = active[0]
        log.info(f"Resolved active competition: {c['name']} ({c['competition_id']})")
        return c["competition_id"], c["name"]

    c = competitions[0]
    log.info(f"Resolved competition (fallback): {c['name']} ({c['competition_id']})")
    return c["competition_id"], c["name"]


intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def dm_only_check(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        return True
    await ctx.send(
        "⚠️ Use this bot in **DMs only** (open a direct message with the bot)."
    )
    return False


bot.add_check(dm_only_check)


async def deny_if_not_dm(interaction: discord.Interaction) -> bool:
    """Return False and respond if interaction is not in a DM."""
    if interaction.guild is not None:
        await interaction.response.send_message(
            "⚠️ Use this bot in **DMs only**.",
            ephemeral=True,
        )
        return False
    return True


@bot.event
async def on_ready():
    log.info(f"Bot connected as {bot.user} (ID: {bot.user.id})")

    success, reason = login()
    if success:
        log.info(f"Site login succeeded ({reason})")
    else:
        log.error(f"Site login failed: {reason}")

    get_team_id(14)

    if not check_new_challenges.is_running():
        check_new_challenges.start()
        log.info("Started check_new_challenges loop")

    if not check_tracking.is_running():
        check_tracking.start()
        log.info("Started check_tracking loop")


@tasks.loop(minutes=10)
async def check_new_challenges():
    if CURRENT_USER_ID is None:
        return

    track_data = load_track()
    subscribers = track_data.get("challenge_notif_subscribers", [])

    try:
        resp = HTTP.get(
            f"{HC_API_URL}/users/{CURRENT_USER_ID}/competitions", timeout=15
        )
        if resp.status_code != 200:
            log.warning(f"Failed to fetch competitions: HTTP {resp.status_code}")
            return
        competitions = resp.json()["competitions"]
    except Exception as e:
        log.error(f"Error fetching competitions: {e}")
        return

    active = [c for c in competitions if is_active(c)]
    stored = load_chall()

    for comp in active:
        cid = comp["competition_id"]
        team_id = get_team_id(cid)
        if team_id is None:
            continue

        try:
            resp = HTTP.get(
                f"{HC_API_URL}/competitions/{cid}/teams/{team_id}/challenges",
                timeout=15,
            )
            if resp.status_code != 200:
                log.warning(
                    f"Failed to fetch challenges for comp {cid}: HTTP {resp.status_code}"
                )
                continue
            challenges = resp.json()["challenges"]
        except Exception as e:
            log.error(f"Error fetching challenges for comp {cid}: {e}")
            continue

        comp_key = str(cid)
        old_ids = set(stored.get("competitions", {}).get(comp_key, []))

        new_count = 0
        for chall in challenges:
            if chall["challenge_id"] not in old_ids:
                new_count += 1
                embed = discord.Embed(
                    title="New Challenge", color=discord.Color.green()
                )
                name = chall["name"]
                category = chall.get("category", "")
                if category:
                    embed.description = f"**{name}** ({category})"
                else:
                    embed.description = f"**{name}**"
                if subscribers:
                    for uid_str in subscribers:
                        try:
                            user = await bot.fetch_user(int(uid_str))
                            await user.send(embed=embed)
                        except Exception as e:
                            log.error(
                                f"Failed to DM new challenge to user {uid_str}: {e}"
                            )

        if new_count > 0:
            log.info(f"Found {new_count} new challenge(s) in competition {cid}")

        stored.setdefault("competitions", {})[comp_key] = [
            c["challenge_id"] for c in challenges
        ]

    save_chall(stored)


@tasks.loop(minutes=10)
async def check_tracking():
    if CURRENT_USER_ID is None:
        return

    data = load_track()
    tracking = data.get("tracking", {})
    if not tracking:
        return

    log.info(f"Checking tracking for {len(tracking)} user(s)")

    try:
        resp = HTTP.get(
            f"{HC_API_URL}/users/{CURRENT_USER_ID}/competitions", timeout=15
        )
        if resp.status_code != 200:
            log.warning(
                f"Failed to fetch competitions for tracking: HTTP {resp.status_code}"
            )
            return
        competitions = resp.json()["competitions"]
    except Exception as e:
        log.error(f"Error fetching competitions for tracking: {e}")
        return

    active = [c for c in competitions if is_active(c)]
    if not active:
        return
    cid = active[0]["competition_id"]

    teams = fetch_all_teams(cid)
    if not teams:
        log.warning("No teams found for tracking check")
        return

    rank_map = {t["team_id"]: i + 1 for i, t in enumerate(teams)}
    name_map = {t["team_id"]: t["name"] for t in teams}

    for discord_id_str, entry in list(tracking.items()):
        my_team_id = entry.get("team_id")
        opponents = entry.get("opponents", [])

        if my_team_id not in rank_map:
            continue

        my_rank = rank_map[my_team_id]

        notified = set(entry.get("above_notified", []))
        notified &= set(opponents)

        for opp_id in opponents:
            if opp_id not in rank_map:
                notified.discard(opp_id)
                continue
            opp_rank = rank_map[opp_id]
            opp_name = name_map.get(opp_id, str(opp_id))

            if opp_rank >= my_rank:
                notified.discard(opp_id)
                continue

            if opp_id in notified:
                continue

            log.info(
                f"Opponent {opp_name} ({opp_id}) above user {entry.get('team_name')}: #{opp_rank} vs #{my_rank}"
            )
            try:
                user = await bot.fetch_user(int(discord_id_str))
                await user.send(
                    f"⚠️ **{opp_name}** is now above you! "
                    f"(them: #{opp_rank}, you: #{my_rank})"
                )
                notified.add(opp_id)
            except Exception as e:
                log.error(f"Failed to DM user {discord_id_str}: {e}")

        entry["above_notified"] = sorted(notified)

    save_track(data)


@bot.command(name="comps")
async def comps(ctx):
    log.info(f"!comps called by {ctx.author}")
    try:
        resp = HTTP.get(
            f"{HC_API_URL}/users/{CURRENT_USER_ID}/competitions", timeout=15
        )
        resp.raise_for_status()
        competitions = resp.json()["competitions"]

        active = [c for c in competitions if is_active(c)]
        if not active:
            await ctx.send("⚠️ No active competitions. Use `!top <id>`.")
            return

        embed = discord.Embed(title="Active Competitions", color=discord.Color.blue())
        embed.description = "Use `!top <id>` to show leaderboard."
        ids = [f"`{c['competition_id']}`" for c in active]
        names = [c["name"] for c in active]
        embed.add_field(name="ID", value="\n".join(ids), inline=True)
        embed.add_field(name="Name", value="\n".join(names), inline=True)
        await ctx.send(embed=embed)
    except Exception as e:
        log.error(f"!comps failed: {e}")
        await ctx.send(f"❌ Failed to fetch competitions: {e}")


@bot.command(name="top")
async def top(ctx, competition_id: int):
    log.info(f"!top called by {ctx.author} (id={competition_id})")
    try:
        comp_resp = HTTP.get(f"{HC_API_URL}/competitions/{competition_id}", timeout=15)
        comp_resp.raise_for_status()
        comp_name = comp_resp.json()["name"]

        teams_resp = HTTP.get(
            f"{HC_API_URL}/competitions/{competition_id}/teams?page=0&per_page={TOP_PER_PAGE}&training=",
            timeout=15,
        )
        teams_resp.raise_for_status()
        teams = teams_resp.json()["teams"]

        if not teams:
            await ctx.send("⚠️ No leaderboard entries found.")
            return

        embed = discord.Embed(
            title=f"Top {TOP_PER_PAGE} — {comp_name}",
            description=format_leaderboard_text(teams),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)
    except Exception as e:
        log.error(f"!top failed: {e}")
        await ctx.send(f"❌ Failed to fetch leaderboard: {e}")


@bot.command(name="commands")
async def commands_list(ctx):
    embed = discord.Embed(title="Commands", color=discord.Color.blue())
    embed.add_field(name="`!comps`", value="Show active competitions", inline=False)
    embed.add_field(
        name="`!top <id>`",
        value="Top 10 leaderboard for a specific competition",
        inline=False,
    )
    embed.add_field(
        name="`!challs`", value="Challenges for current competition", inline=False
    )
    embed.add_field(
        name="`!challs <id>`",
        value="Challenges for a specific competition",
        inline=False,
    )
    embed.add_field(
        name="`!track`", value="Track opponents on the leaderboard", inline=False
    )
    embed.add_field(name="`!tracking`", value="Show who you're tracking", inline=False)
    embed.add_field(
        name="`!addtrack <ids>`", value="Add opponent team IDs", inline=False
    )
    embed.add_field(name="`!untrack`", value="Stop tracking", inline=False)
    embed.add_field(
        name="`!notif`",
        value="Toggle DM when a new challenge is released (opt-in)",
        inline=False,
    )
    embed.add_field(name="`!commands`", value="Show this message", inline=False)
    embed.add_field(
        name="Feedback",
        value="For feature requests or bug reports, please [open an issue](https://github.com/hackintro/tracker/issues).",
        inline=False,
    )
    await ctx.send(embed=embed)


CHALLS_PER_PAGE = 5


class ChallView(discord.ui.View):
    def __init__(self, challenges, comp_name):
        super().__init__(timeout=120)
        self.challenges = challenges
        self.comp_name = comp_name
        self.page = 0
        self.max_page = max(0, (len(challenges) - 1) // CHALLS_PER_PAGE)

    def build_embed(self):
        start = self.page * CHALLS_PER_PAGE
        page_challs = self.challenges[start : start + CHALLS_PER_PAGE]

        embed = discord.Embed(
            title=f"Challenges — {self.comp_name}", color=discord.Color.blue()
        )

        lines = []
        for c in page_challs:
            name = c["name"]
            category = c.get("category", "")
            score = c["score"]
            line = f"**{name}**"
            if category:
                line += f" — {category}"
            line += f" ({score} pts)"
            lines.append(line)

        embed.add_field(name="", value="\n".join(lines), inline=False)

        embed.set_footer(
            text=f"Page {self.page + 1}/{self.max_page + 1} • {len(self.challenges)} challenges"
        )
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await deny_if_not_dm(interaction):
            return
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await deny_if_not_dm(interaction):
            return
        if self.page < self.max_page:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


TEAMS_PER_PAGE = 10


class TeamView(discord.ui.View):
    def __init__(self, teams):
        super().__init__(timeout=300)
        self.teams = teams
        self.page = 0
        self.max_page = max(0, (len(teams) - 1) // TEAMS_PER_PAGE)

    def build_embed(self):
        start = self.page * TEAMS_PER_PAGE
        page_teams = self.teams[start : start + TEAMS_PER_PAGE]

        embed = discord.Embed(title="Teams on Leaderboard", color=discord.Color.blue())
        embed.description = "Send the IDs you want to track (e.g. `1,4,5,6,7`):"

        names = [t["name"] for t in page_teams]
        ids = [str(t["team_id"]) for t in page_teams]

        embed.add_field(name="Name", value="\n".join(names), inline=True)
        embed.add_field(name="ID", value="\n".join(ids), inline=True)

        embed.set_footer(
            text=f"Page {self.page + 1}/{self.max_page + 1} • {len(self.teams)} teams"
        )
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await deny_if_not_dm(interaction):
            return
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await deny_if_not_dm(interaction):
            return
        if self.page < self.max_page:
            self.page += 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


@bot.command(name="challs")
async def challs(ctx, competition_id: int = None):
    log.info(f"!challs called by {ctx.author} (id={competition_id})")
    try:
        if competition_id is None:
            cid, comp_name = resolve_competition()
        else:
            cid = competition_id
            comp_resp = HTTP.get(f"{HC_API_URL}/competitions/{cid}", timeout=15)
            comp_resp.raise_for_status()
            comp_name = comp_resp.json()["name"]

        team_id = get_team_id(cid)
        if team_id is None:
            await ctx.send("⚠️ Could not find your team for this competition.")
            return

        resp = HTTP.get(
            f"{HC_API_URL}/competitions/{cid}/teams/{team_id}/challenges",
            timeout=15,
        )
        resp.raise_for_status()
        challenges = resp.json()["challenges"]

        if not challenges:
            await ctx.send("⚠️ No challenges found.")
            return

        challenges.sort(key=lambda c: c["score"])

        view = ChallView(challenges, comp_name)
        await ctx.send(embed=view.build_embed(), view=view)
    except Exception as e:
        log.error(f"!challs failed: {e}")
        await ctx.send(f"❌ Failed to fetch challenges: {e}")


@bot.command(name="track")
async def track(ctx):
    discord_id = str(ctx.author.id)
    log.info(f"!track called by {ctx.author} ({discord_id})")
    if discord_id in conversations:
        await ctx.send(
            "⚠️ You already have a setup in progress. Finish the steps in this chat."
        )
        return

    dm = await ctx.author.create_dm()
    await dm.send("What is your name on the platform?")

    conversations[discord_id] = {"step": "name", "channel_id": ctx.channel.id}
    await ctx.send(
        "📬 Reply here with your **platform team name** (exactly as on the site)."
    )


@bot.command(name="notif")
async def notif(ctx):
    """Opt in/out of DMs when a new challenge appears."""
    discord_id = str(ctx.author.id)
    log.info(f"!notif called by {ctx.author} ({discord_id})")
    data = load_track()
    subs = data.setdefault("challenge_notif_subscribers", [])
    if discord_id in subs:
        subs.remove(discord_id)
        save_track(data)
        await ctx.send("✅ You will no longer receive DMs for new challenges.")
    else:
        subs.append(discord_id)
        save_track(data)
        await ctx.send(
            "✅ You will get a **DM** when a new challenge is released. "
            "Use `!notif` again to turn this off."
        )


@bot.command(name="untrack")
async def untrack(ctx):
    discord_id = str(ctx.author.id)
    log.info(f"!untrack called by {ctx.author} ({discord_id})")
    data = load_track()

    if discord_id not in data.get("tracking", {}):
        await ctx.send("⚠️ You are not tracking anyone.")
        return

    del data["tracking"][discord_id]
    save_track(data)
    log.info(f"User {discord_id} stopped tracking")
    await ctx.send("✅ Tracking stopped.")


@bot.command(name="addtrack")
async def addtrack(ctx, *, ids: str = None):
    discord_id = str(ctx.author.id)
    log.info(f"!addtrack called by {ctx.author} ({discord_id}): {ids}")
    data = load_track()

    if discord_id not in data.get("tracking", {}):
        await ctx.send("⚠️ You are not tracking anyone. Use `!track` first.")
        return

    if not ids:
        await ctx.send("⚠️ Provide IDs to add (e.g. `!addtrack 1,4,5`).")
        return

    try:
        new_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        await ctx.send(
            "⚠️ Invalid format. Use comma-separated IDs (e.g. `!addtrack 1,4,5`)."
        )
        return

    teams = fetch_all_teams(14)
    name_map = {t["team_id"]: t["name"] for t in teams}

    entry = data["tracking"][discord_id]
    existing = set(entry["opponents"])

    added = []
    for oid in new_ids:
        if oid in name_map and oid not in existing:
            entry["opponents"].append(oid)
            added.append(f"**{name_map[oid]}** (`{oid}`)")
        elif oid in existing:
            await ctx.send(f"⚠️ Already tracking `{oid}`.")
        else:
            await ctx.send(f"⚠️ ID `{oid}` not found.")

    if added:
        save_track(data)
        log.info(f"User {discord_id} added {len(added)} opponent(s)")
        await ctx.send(f"✅ Added:\n" + "\n".join(f"- {n}" for n in added))


@bot.command(name="tracking")
async def tracking(ctx):
    discord_id = str(ctx.author.id)
    data = load_track()

    if discord_id not in data.get("tracking", {}):
        await ctx.send("⚠️ You are not tracking anyone. Use `!track` first.")
        return

    entry = data["tracking"][discord_id]
    teams = fetch_all_teams(14)
    name_map = {t["team_id"]: t["name"] for t in teams}

    embed = discord.Embed(title="Tracking", color=discord.Color.blue())
    embed.description = f"You: **{entry['team_name']}** (`{entry['team_id']}`)"

    names = []
    ids = []
    for oid in entry["opponents"]:
        names.append(name_map.get(oid, "Unknown"))
        ids.append(str(oid))

    if names:
        embed.add_field(name="Opponents", value="\n".join(names), inline=True)
        embed.add_field(name="ID", value="\n".join(ids), inline=True)

    await ctx.send(embed=embed)

    remaining = [
        t
        for t in teams
        if t["team_id"] not in entry["opponents"] and t["team_id"] != entry["team_id"]
    ]
    if remaining:
        view = TeamView(remaining)
        await ctx.send(embed=view.build_embed(), view=view)


@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    discord_id = str(message.author.id)

    if message.guild is None and discord_id in conversations:
        conv = conversations[discord_id]
        text = message.content.strip()

        if conv["step"] == "name":
            log.info(f"Track setup: user {discord_id} provided name '{text}'")
            teams = fetch_all_teams(14)
            if not teams:
                log.error(f"Failed to fetch teams for track setup (user {discord_id})")
                await message.channel.send("❌ Failed to fetch teams. Try again later.")
                del conversations[discord_id]
                return
            match = None
            for t in teams:
                if t["name"].lower() == text.lower():
                    match = t
                    break

            if match is None:
                log.info(f"Track setup: team '{text}' not found for user {discord_id}")
                await message.channel.send(
                    f"❌ Could not find a team named '{text}'. Try again."
                )
                return

            log.info(
                f"Track setup: matched '{match['name']}' (ID: {match['team_id']}) for user {discord_id}"
            )
            await message.channel.send(
                f"✅ Found: **{match['name']}** (ID: `{match['team_id']}`)"
            )

            view = TeamView(teams)
            await message.channel.send(embed=view.build_embed(), view=view)

            conv["step"] = "opponents"
            conv["team_id"] = match["team_id"]
            conv["team_name"] = match["name"]
            conv["all_teams"] = {t["team_id"]: t["name"] for t in teams}

        elif conv["step"] == "opponents":
            try:
                ids = [int(x.strip()) for x in text.split(",") if x.strip()]
            except ValueError:
                await message.channel.send(
                    "❌ Invalid format. Use comma-separated IDs (e.g. `1,4,5,6,7`)."
                )
                return

            all_teams = conv["all_teams"]
            valid = []
            for oid in ids:
                if oid in all_teams:
                    valid.append(oid)
                else:
                    await message.channel.send(f"⚠️ ID `{oid}` not found, skipping.")

            if not valid:
                await message.channel.send("❌ No valid IDs. Try again.")
                return

            data = load_track()
            data.setdefault("tracking", {})[discord_id] = {
                "team_id": conv["team_id"],
                "team_name": conv["team_name"],
                "opponents": valid,
            }
            save_track(data)

            log.info(
                f"User {discord_id} started tracking {len(valid)} opponent(s): {valid}"
            )
            names = [all_teams[oid] for oid in valid]
            await message.channel.send(
                f"✅ Now tracking **{len(valid)}** opponents:\n"
                + "\n".join(f"- **{n}** (`{i}`)" for n, i in zip(names, valid))
            )

            del conversations[discord_id]

    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        if ctx.command and ctx.command.name == "top":
            await ctx.send(
                "⚠️ Specify a competition ID (e.g. `!top 14`). "
                "Use `!comps` to list active competitions."
            )
            return
    if isinstance(error, commands.BadArgument):
        await ctx.send("⚠️ Invalid argument. Use a number (e.g. `!top 14`).")
    else:
        log.error(f"Command error in {ctx.command}: {error}")
        raise error


if __name__ == "__main__":
    log.info("Starting bot...")
    bot.run(DISCORD_TOKEN)
