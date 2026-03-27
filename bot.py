import discord
from discord.ext import tasks, commands
import requests
import json
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, time
from zoneinfo import ZoneInfo

# ================= CONFIGURATION =================
# Load the .env file
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_STR = os.getenv("CHANNEL_ID")
HC_API_URL = os.getenv("HC_API_URL")

# Check if the required keys exist
if not DISCORD_TOKEN or not HC_API_URL or not CHANNEL_ID_STR:
    print(
        "❌ ERROR: Missing keys in .env file! Ensure DISCORD_TOKEN, HC_API_URL, and CHANNEL_ID are set."
    )
    exit()

try:
    CHANNEL_ID = int(CHANNEL_ID_STR)
except ValueError:
    print("❌ ERROR: CHANNEL_ID in .env must be a number.")
    exit()

