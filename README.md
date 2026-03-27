# Hackcenter Tracker

A Discord bot that tracks challenges, leaderboards, and opponents on Hackcenter.

## Commands

| Command | Description | Where |
|---------|-------------|-------|
| `!top` | Show active competitions | Channel |
| `!top <id>` | Top 10 leaderboard for a competition | Channel |
| `!challs` | Challenges for current competition | Channel |
| `!challs <id>` | Challenges for a specific competition | Channel |
| `!track` | Start tracking opponents via DM | Channel |
| `!tracking` | Show who you're tracking + available teams | Channel |
| `!addtrack <ids>` | Add opponents to your tracking list | DM only |
| `!untrack` | Stop tracking | Channel |
| `!commands` | Show available commands | Channel |

## Features

### Challenge Notifications
Every 10 minutes the bot checks for new challenges across your active competitions. When a new challenge appears, it posts an embed to the configured channel:

```
┌─────────────────┐
│ New Challenge   │
│                 │
│ challenge_name  │
│ (Category)      │
└─────────────────┘
```

### Leaderboard
- `!top` — shows active competitions
- `!top 14` — shows top 10 teams with position, name, and score

### Challenges
- `!challs` — paginated list of challenges with ◀ ▶ buttons
- Shows name, category, and points sorted ascending
- 5 challenges per page

### Opponent Tracking
- `!track` starts a DM conversation:
  1. Bot asks for your platform name
  2. Bot finds your team and confirms it
  3. Bot shows all teams in a paginated embed
  4. You send comma-separated IDs to track (e.g. `1,4,5,6,7`)
- Every 10 minutes the bot checks if any tracked opponent is ranked above you
- If someone passes you, you get a DM: `⚠️ name is now above you! (them: #12, you: #15)`
- `!tracking` shows your current tracking status and remaining available teams
- `!addtrack 8,12` adds more opponents (DM only)
- `!untrack` stops all tracking

## Setup

### Option 1: Using Nix (Recommended)

```bash
nix develop
```

### Option 2: Manual Setup

1. **Install dependencies**
```bash
pip install discord.py requests python-dotenv
```

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

3. **Run the bot**
```bash
python3 bot.py
```

## Project Structure

```
tracker/
├── bot.py          # Main Discord bot
├── chall.json      # Stored challenge IDs (auto-generated)
├── track.json      # Tracking data (auto-generated)
├── tracker.log     # Log file (auto-generated)
├── .env            # Environment variables
├── .env.example    # Environment template
├── flake.nix       # Nix flake
├── flake.lock      # Nix lock file
└── README.md       # This file
```

## Requirements

- Python 3.8+
- discord.py
- requests
- python-dotenv
