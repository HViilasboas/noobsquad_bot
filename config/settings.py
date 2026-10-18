import os
from dotenv import load_dotenv

load_dotenv()

# Discord configs
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
REBOOT_CHANNEL_ID = int(os.getenv('REBOOT_CHANNEL_ID', 0))
CHAT_JUKEBOX = os.getenv('CHAT_JUKEBOX')

# Notification channel
NOTIFICATION_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))

# MongoDB configs
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'noobsquad_bot')

# YouTube API
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# Spotify API - usada somente para importar playlists públicas para a fila do YouTube
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Twitch API
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')

# Monitor intervals (em segundos)
CHECK_YOUTUBE_INTERVAL = int(os.getenv('CHECK_YOUTUBE_INTERVAL', 300))  # 5 minutos
CHECK_TWITCH_INTERVAL = int(os.getenv('CHECK_TWITCH_INTERVAL', 180))   # 3 minutos

# Steam - catálogo público de lançamentos e recomendações comunitárias
STEAM_CHECK_INTERVAL = int(os.getenv('STEAM_CHECK_INTERVAL', 21600))  # 6 horas
STEAM_RELEASE_WINDOW_DAYS = int(os.getenv('STEAM_RELEASE_WINDOW_DAYS', 90))
STEAM_REQUEST_TIMEOUT = int(os.getenv('STEAM_REQUEST_TIMEOUT', 20))

# Sync de membros - Horário de execução (formato HH:MM em UTC)
SYNC_MEMBERS_TIME = os.getenv('SYNC_MEMBERS_TIME', '03:00')  # Padrão: 03:00 UTC

def parse_sync_time(time_str: str) -> tuple[int, int]:
    """Converte string HH:MM para tupla (hora, minuto)"""
    try:
        hour, minute = time_str.split(':')
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        # Fallback para 03:00 se formato inválido
        return 3, 0

SYNC_MEMBERS_HOUR, SYNC_MEMBERS_MINUTE = parse_sync_time(SYNC_MEMBERS_TIME)

# Screen-share web app and MediaMTX endpoints. Public URLs must be reachable by
# the presenter and viewers; use HTTPS outside localhost for browser capture.
STREAM_WEB_HOST = os.getenv('STREAM_WEB_HOST', '0.0.0.0')
STREAM_WEB_PORT = int(os.getenv('STREAM_WEB_PORT', 8080))
STREAM_PUBLIC_URL = os.getenv('STREAM_PUBLIC_URL', 'http://localhost:8080')
STREAM_MEDIA_URL = os.getenv('STREAM_MEDIA_URL', 'http://localhost:8889')
STREAM_MEDIA_API_URL = os.getenv('STREAM_MEDIA_API_URL', 'http://127.0.0.1:9997')
STREAM_SESSION_MAX_MINUTES = int(os.getenv('STREAM_SESSION_MAX_MINUTES', 240))

# ICE servers improve WebRTC connectivity across NATs and restricted networks.
# The second server defaults to a backup STUN server and can be changed to TURN.
STREAM_ICE_SERVER_0_URL = os.getenv(
    'STREAM_ICE_SERVER_0_URL', 'stun:stun.l.google.com:19302'
).strip()
STREAM_ICE_SERVER_1_URL = os.getenv(
    'STREAM_ICE_SERVER_1_URL', 'stun:stun1.l.google.com:19302'
).strip()
STREAM_ICE_SERVER_1_USERNAME = os.getenv('STREAM_ICE_SERVER_1_USERNAME', '').strip()
STREAM_ICE_SERVER_1_PASSWORD = os.getenv('STREAM_ICE_SERVER_1_PASSWORD', '')

if STREAM_ICE_SERVER_1_URL.lower().startswith(('turn:', 'turns:')):
    if STREAM_ICE_SERVER_1_USERNAME == 'AUTH_SECRET':
        if not STREAM_ICE_SERVER_1_PASSWORD:
            raise ValueError(
                'STREAM_ICE_SERVER_1_PASSWORD deve conter o segredo REST do TURN.'
            )
    elif not STREAM_ICE_SERVER_1_USERNAME or not STREAM_ICE_SERVER_1_PASSWORD:
        raise ValueError(
            'Configure STREAM_ICE_SERVER_1_USERNAME e STREAM_ICE_SERVER_1_PASSWORD '
            'para o servidor TURN.'
        )

# Equalizer presets
EQUALIZER_PRESETS = {
    "padrao": '-filter_complex "equalizer=f=5000:g=2:w=1,equalizer=f=8000:g=2:w=1"',
    "pop": '-filter_complex "equalizer=f=80:g=4:w=1:t=h,equalizer=f=8000:g=4:w=1:t=h"',
    "rock": '-filter_complex "equalizer=f=120:g=-2:w=1:t=h,equalizer=f=2000:g=3:w=1:t=h,equalizer=f=5000:g=4:w=1:t=h"',
    "graves": '-filter_complex "equalizer=f=80:g=4:w=1:t=h,equalizer=f=200:g=2:w=1:t=h"',
}
