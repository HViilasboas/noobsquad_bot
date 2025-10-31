"""
Bot Package

Este pacote contém toda a lógica do bot do Discord, incluindo:
- Comandos (commands.py)
- Configuração principal (main.py)
- Funções utilitárias (utils.py)
"""

from .commands import MusicCommands
from .utils import clean_youtube_url, is_youtube_url, stream_musica

__all__ = [
    'MusicCommands',
    'clean_youtube_url',
    'is_youtube_url',
    'stream_musica'
]
