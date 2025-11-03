from datetime import datetime, UTC
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Song:
    """Representa uma música no histórico"""
    title: str
    url: str
    played_at: datetime
    artist: Optional[str] = None
    genre: Optional[str] = None


@dataclass
class MusicPreference:
    """Representa uma preferência musical"""
    name: str  # Nome do gênero, artista ou banda
    type: str  # 'genre', 'artist', 'band'
    count: int  # Número de vezes que músicas deste tipo foram tocadas
    last_updated: datetime


@dataclass
class MonitoredChannel:
    """Representa um canal monitorado (YouTube ou Twitch) como documento próprio

    Agora existe uma coleção separada `monitored_channels` no banco. Cada documento
    armazena a lista de `subscribers` (IDs de Discord) que reclamam este canal.
    """
    platform: str  # 'youtube' ou 'twitch'
    channel_id: str
    channel_name: str
    added_by: Optional[str] = None  # Discord user ID who first added the channel
    last_video_id: Optional[str] = None
    last_stream_id: Optional[str] = None
    is_live: bool = False
    added_at: datetime = datetime.now(UTC)  # Usando UTC de forma explícita
    subscribers: Optional[List[str]] = None

    def __post_init__(self):
        if self.subscribers is None:
            self.subscribers = []

    @classmethod
    def from_dict(cls, data: Dict) -> 'MonitoredChannel':
        return cls(
            platform=data.get('platform'),
            channel_id=data.get('channel_id'),
            channel_name=data.get('channel_name'),
            added_by=data.get('added_by'),
            last_video_id=data.get('last_video_id'),
            last_stream_id=data.get('last_stream_id'),
            is_live=data.get('is_live', False),
            added_at=data.get('added_at', datetime.now(UTC)),
            subscribers=data.get('subscribers', [])
        )

    def to_dict(self) -> Dict:
        return {
            'platform': self.platform,
            'channel_id': self.channel_id,
            'channel_name': self.channel_name,
            'added_by': self.added_by,
            'last_video_id': self.last_video_id,
            'last_stream_id': self.last_stream_id,
            'is_live': self.is_live,
            'added_at': self.added_at,
            'subscribers': self.subscribers or []
        }


@dataclass
class UserProfile:
    """Representa o perfil de um usuário no MongoDB"""
    discord_id: str
    username: str
    music_history: List[Song] = None  # Será inicializado como lista vazia
    music_preferences: List[MusicPreference] = None  # Será inicializado como lista vazia
    created_at: datetime = None  # Será inicializado com datetime.now(UTC)

    def __post_init__(self):
        """Inicializa campos com valores padrão se necessário"""
        if self.music_history is None:
            self.music_history = []
        if self.music_preferences is None:
            self.music_preferences = []
        if self.created_at is None:
            self.created_at = datetime.now(UTC)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserProfile':
        """Cria um UserProfile a partir de um dicionário do MongoDB"""
        return cls(
            discord_id=data['discord_id'],
            username=data['username'],
            music_history=[
                Song(
                    title=song['title'],
                    url=song['url'],
                    played_at=song['played_at'],
                    artist=song.get('artist'),
                    genre=song.get('genre')
                ) for song in data.get('music_history', [])
            ],
            music_preferences=[
                MusicPreference(
                    name=pref['name'],
                    type=pref['type'],
                    count=pref['count'],
                    last_updated=pref['last_updated']
                ) for pref in data.get('music_preferences', [])
            ],
            created_at=data.get('created_at')
        )

    def to_dict(self) -> Dict:
        """Converte o UserProfile para um dicionário para salvar no MongoDB"""
        return {
            'discord_id': self.discord_id,
            'username': self.username,
            'music_history': [
                {
                    'title': song.title,
                    'url': song.url,
                    'played_at': song.played_at,
                    'artist': song.artist,
                    'genre': song.genre
                } for song in self.music_history
            ],
            'music_preferences': [
                {
                    'name': pref.name,
                    'type': pref.type,
                    'count': pref.count,
                    'last_updated': pref.last_updated
                } for pref in self.music_preferences
            ],
            'created_at': self.created_at
        }


__all__ = ['Song', 'MusicPreference', 'MonitoredChannel', 'UserProfile']
