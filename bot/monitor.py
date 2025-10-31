import logging
import asyncio
from typing import Optional, List
from datetime import datetime
from googleapiclient.discovery import build
from twitchAPI.twitch import Twitch
from config.settings import (
    YOUTUBE_API_KEY,
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    CHECK_YOUTUBE_INTERVAL,
    CHECK_TWITCH_INTERVAL
)
from db.models import MonitoredChannel

class ChannelMonitor:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY) if YOUTUBE_API_KEY else None
        self.twitch = None
        if TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET:
            self.twitch = Twitch(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)
            self.twitch.authenticate_app([])

    async def check_youtube_updates(self, channel: MonitoredChannel) -> Optional[dict]:
        """Verifica atualizações de um canal do YouTube"""
        try:
            # Busca os últimos vídeos do canal
            request = self.youtube.search().list(
                part="snippet",
                channelId=channel.channel_id,
                order="date",
                maxResults=1,
                type="video"
            )
            response = request.execute()

            if not response['items']:
                return None

            video = response['items'][0]
            video_id = video['id']['videoId']

            # Se é um vídeo novo
            if video_id != channel.last_video_id:
                return {
                    'type': 'video',
                    'title': video['snippet']['title'],
                    'url': f'https://www.youtube.com/watch?v={video_id}',
                    'thumbnail': video['snippet']['thumbnails']['default']['url'],
                    'video_id': video_id
                }
            return None
        except Exception as e:
            logging.error(f"Erro ao verificar canal YouTube {channel.channel_name}: {str(e)}")
            return None

    async def check_twitch_updates(self, channel: MonitoredChannel) -> Optional[dict]:
        """Verifica atualizações de um canal da Twitch"""
        try:
            # Verifica se o canal está ao vivo
            streams = self.twitch.get_streams(user_login=[channel.channel_name])['data']

            is_live = bool(streams)
            stream_id = streams[0]['id'] if streams else None

            # Se o status da live mudou
            if is_live != channel.is_live or (is_live and stream_id != channel.last_stream_id):
                if is_live:
                    stream = streams[0]
                    return {
                        'type': 'live',
                        'title': stream['title'],
                        'url': f'https://twitch.tv/{channel.channel_name}',
                        'thumbnail': stream['thumbnail_url'].replace('{width}', '320').replace('{height}', '180'),
                        'stream_id': stream_id
                    }
            return None
        except Exception as e:
            logging.error(f"Erro ao verificar canal Twitch {channel.channel_name}: {str(e)}")
            return None

    def extract_youtube_channel_id(self, input_str: str) -> Optional[str]:
        """Extrai o ID do canal do YouTube de diferentes formatos de URL"""
        try:
            # Se já é um ID válido
            if input_str.startswith('UC') and len(input_str) == 24:
                return input_str

            # Se é uma URL de canal
            if 'youtube.com/' in input_str:
                # Tenta diferentes formatos de URL
                request = self.youtube.channels().list(
                    part="id",
                    forUsername=input_str.split('/')[-1] if '/user/' in input_str else None,
                    id=input_str.split('/')[-1] if '/channel/' in input_str else None
                )
                response = request.execute()
                if response['items']:
                    return response['items'][0]['id']

            # Se é um @handle
            if input_str.startswith('@'):
                request = self.youtube.search().list(
                    part="snippet",
                    q=input_str,
                    type="channel",
                    maxResults=1
                )
                response = request.execute()
                if response['items']:
                    return response['items'][0]['snippet']['channelId']

            return None
        except Exception as e:
            logging.error(f"Erro ao extrair ID do canal YouTube: {str(e)}")
            return None

    async def validate_twitch_channel(self, channel_name: str) -> Optional[dict]:
        """Valida se um canal da Twitch existe e retorna suas informações"""
        try:
            # Remove @ se existir e limpa o nome do canal
            channel_name = channel_name.lstrip('@').lower()

            # Busca informações do canal
            users = self.twitch.get_users(logins=[channel_name])
            if users['data']:
                user = users['data'][0]
                return {
                    'id': user['id'],
                    'name': user['login'],
                    'display_name': user['display_name']
                }
            return None
        except Exception as e:
            logging.error(f"Erro ao validar canal Twitch {channel_name}: {str(e)}")
            return None
