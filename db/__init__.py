"""
Database Package

Este pacote gerencia todas as operações de banco de dados, incluindo:
- Conexão com MongoDB (database.py)
- Modelos de dados (models.py)
"""

from .database import db
from .models import UserProfile, Song, MusicPreference

__all__ = [
    'db',
    'UserProfile',
    'Song',
    'MusicPreference'
]
