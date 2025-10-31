import discord
import yt_dlp
import os
import asyncio
import logging
from datetime import datetime
from discord.ext import commands
from collections import deque
import re
import urllib.parse
import shutil

from config.settings import (
    DISCORD_TOKEN,
    REBOOT_CHANNEL_ID,
    CHAT_JUKEBOX,
    EQUALIZER_PRESETS
)
from db.database import db

# --- CONFIGURAÇÃO DE LOGGING ---
log_filename = datetime.now().strftime('bot_log_%Y-%m-%d.log')
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

if not DISCORD_TOKEN:
    logging.error("Token do bot não encontrado no arquivo .env")
    raise ValueError("Token do bot não encontrado no arquivo .env")
if not REBOOT_CHANNEL_ID:
    logging.error("ID do canal de reboot não encontrado no arquivo .env")
    raise ValueError("ID do canal de reboot não encontrado no arquivo .env")

# --- CONFIGURAÇÃO DAS INTENTS E BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents, heartbeat_timeout=60.0, help_command=None)

# --- FILA DE REPRODUÇÃO E VARIÁVEIS GLOBAIS ---
play_queue = {}
last_played_info = {}
autoplay_enabled = {}
