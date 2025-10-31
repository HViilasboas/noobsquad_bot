import os
from dotenv import load_dotenv

load_dotenv()

# Discord configs
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
REBOOT_CHANNEL_ID = os.getenv('REBOOT_CHANNEL_ID')
CHAT_JUKEBOX = os.getenv('CHAT_JUKEBOX')

# Notification channel
NOTIFICATION_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))

# MongoDB configs
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'noobsquad_bot')

# YouTube API
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# Twitch API
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')

# Monitor intervals (em segundos)
CHECK_YOUTUBE_INTERVAL = int(os.getenv('CHECK_YOUTUBE_INTERVAL', 300))  # 5 minutos
CHECK_TWITCH_INTERVAL = int(os.getenv('CHECK_TWITCH_INTERVAL', 180))   # 3 minutos

# Equalizer presets
EQUALIZER_PRESETS = {
    "padrao": '-filter_complex "equalizer=f=5000:g=2:w=1,equalizer=f=8000:g=2:w=1"',
    "pop": '-filter_complex "equalizer=f=80:g=4:w=1:t=h,equalizer=f=8000:g=4:w=1:t=h"',
    "rock": '-filter_complex "equalizer=f=120:g=-2:w=1:t=h,equalizer=f=2000:g=3:w=1:t=h,equalizer=f=5000:g=4:w=1:t=h"',
    "graves": '-filter_complex "equalizer=f=80:g=4:w=1:t=h,equalizer=f=200:g=2:w=1:t=h"',
}
