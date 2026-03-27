# Hackcenter Tracker

A Discord bot that tracks 

## Features

- **User Tracking**: Track Hackcenter users by their User ID via DM
- **Challenges**: Notifies users when new challenges are available
- **Leaderboard**: Shows the top 10 users by points

## Commands

| Command | Description |
|---------|-------------|
| `!track` | Start tracking your Hackcenter via DM |
| `!untrack` | Stop tracking your Hackcenter account |
| `!stats` | View your personal progress |
| `!top` | View the leaderboard |

## Setup

### Option 1: Using Nix (Recommended)

If you have [Nix](https://nixos.org/) installed with [flakes](https://nixos.org/manual/nix/stable/command-ref/new-cli/nix3-flake.html) enabled:

```bash
nix develop
```

This will enter a shell with all dependencies installed automatically.

### Option 2: Manual Setup

1. **Clone the repository**
```bash
git clone https://github.com/hackintro/tracker.git
cd tracker
```

2. **Install dependencies**
```bash
pip install discord.py requests python-dotenv
```

3. **Configure environment variables**
```bash
cp .env.example .env
```
   
Edit `.env`:
```
DISCORD_TOKEN=your_discord_bot_token
CHANNEL_ID=your_discord_channel_id
HC_API_URL=""
```

4. **Run the bot**
```bash
python3 bot.py
```

## Project Structure

```
tracker/
├── bot.py                     # Main Discord bot
├── .env                       # Environment variables
├── .env.example               # Environment template
├── README.md                  # This file
└── bot.py                     # Main Discord bot
```

## How It Works

1. Users run `!track` and provide their Hackcenter User ID

## Requirements

- Python 3.8+
- Discord.py
- requests
- python-dotenv

Or use [Nix](https://nixos.org/) with flakes for automatic dependency management:
```bash
nix develop
```

<!-- ## License -->

<!-- This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. -->
