# Hackcenter Tracker

A Discord bot that tracks challenges, leaderboards, and opponents on Hackcenter.

**All bot commands work in DMs only** — open a direct message with the bot (server channels are not supported).

## Commands

| Command | Description |
|---------|-------------|
| `!comps` | List active competitions (IDs and names) |
| `!top <id>` | Top 10 leaderboard for a competition (e.g. `!top 14`) |
| `!challs` | Challenges for the current (resolved) competition |
| `!challs <id>` | Challenges for a specific competition |
| `!track` | Start opponent-tracking setup (DM flow) |
| `!tracking` | Show who you are tracking and browse more teams |
| `!addtrack <ids>` | Add opponent team IDs (comma-separated) |
| `!untrack` | Stop tracking |
| `!notif` | Toggle DM alerts when a **new challenge** is released (opt-in) |
| `!commands` | Show available commands |

If you run `!top` without an ID, the bot asks you to use `!comps` and pass a competition ID.

## Features

### Challenge notifications (DM)

Every **10 minutes** the bot checks **active** competitions for new challenges (for the configured site account’s teams). When a new challenge appears, it sends a **DM embed** to every user who opted in with `!notif`.

- First-time opt-in: run `!notif` in a DM with the bot; run `!notif` again to opt out.
- Subscribers are stored in `track.json` under `challenge_notif_subscribers`.

### Leaderboard

- `!comps` — active competitions (use the IDs with `!top`).
- `!top 14` — top 10 teams with rank, name, and score for that competition.

### Challenges

- `!challs` / `!challs <id>` — paginated list with ◀ ▶ buttons (5 challenges per page).
- Shows name, category, and points (sorted ascending).

### Opponent tracking

- `!track` starts setup in DMs: you enter your **platform team name**, confirm the match, then pick opponent team IDs from the paginated list (comma-separated, e.g. `1,4,5,6,7`).
- Every **10 minutes** the bot checks the **active** competition’s leaderboard; if a tracked opponent moves above you, you get a DM:  
  `⚠️ name is now above you! (them: #12, you: #15)`.
- `!tracking` shows current tracking and remaining teams (with pagination).
- `!addtrack 8,12` adds more opponents after setup.
- `!untrack` clears your tracking entry.

## Setup

### Option 1: Using Nix (recommended)

```bash
nix develop
```

### Option 2: Manual setup

1. **Install dependencies**

```bash
pip install -r requirements.txt
```

(`discord.py`, `python-dotenv`, `requests`, `tzdata`; `black` is optional for formatting.)

2. **Configure `.env`**

```bash
cp .env.example .env
```

Edit `.env`:
```
DISCORD_TOKEN=your_discord_bot_token
CHANNEL_ID=your_discord_channel_id
HC_API_URL=https://hackintro.di.uoa.gr/api
SITE_EMAIL=your_email
SITE_PASSWORD=your_password
```

The bot logs into the site API with `SITE_EMAIL` / `SITE_PASSWORD` (session cookies) to resolve teams and challenges. `HC_API_URL` should be the API base (same style as in `.env.example`).

3. **Run the bot**

```bash
python3 bot.py
```

Logs go to `tracker.log` and stdout.

## Optional: manual outreach scripts

These utilities send a **single DM** by Discord user ID using the same `DISCORD_TOKEN` as the bot. They **do not** edit `track.json`; users still opt in with `!notif` or complete setup with `!track` as usual.

Discord may refuse the DM (`403`) if the user does not share a server with the bot, has DMs from server members disabled, or has blocked the bot.

```bash
python3 -m utils.manual_add_notif <discord_user_id>
python3 -m utils.manual_add_track <discord_user_id>
```

## Project structure

```
tracker/
├── bot.py                 # Main Discord bot
├── requirements.txt       # Python dependencies
├── chall.json             # Seen challenge IDs (auto-generated)
├── track.json             # Tracking + notification subscribers (auto-generated)
├── tracker.log            # Log file (auto-generated)
├── .env                   # Environment variables (not committed)
├── .env.example           # Environment template
├── utils/
│   ├── manual_add_notif.py   # One-off DM: point users at !notif
│   └── manual_add_track.py   # One-off DM: point users at !track
├── flake.nix
├── flake.lock
└── README.md
```

## Requirements

- Python 3.8+
- See `requirements.txt`
