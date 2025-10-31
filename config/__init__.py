"""
Configuration Package

Este pacote contém todas as configurações do bot, incluindo:
- Variáveis de ambiente
- Configurações globais
- Presets de equalização
"""

from .settings import (
    DISCORD_TOKEN,
    REBOOT_CHANNEL_ID,
    CHAT_JUKEBOX,
    MONGODB_URI,
    DATABASE_NAME,
    EQUALIZER_PRESETS
)

__all__ = [
    'DISCORD_TOKEN',
    'REBOOT_CHANNEL_ID',
    'CHAT_JUKEBOX',
    'MONGODB_URI',
    'DATABASE_NAME',
    'EQUALIZER_PRESETS'
]
