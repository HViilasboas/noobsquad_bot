import logging
from typing import Optional
import asyncio
from googleapiclient.discovery import build
from twitchAPI.twitch import Twitch
from config.settings import (
    YOUTUBE_API_KEY,
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
)
from db.models import MonitoredChannel

class ChannelMonitor:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY) if YOUTUBE_API_KEY else None
        self.twitch = None
        # Inicialização do Twitch será feita de forma assíncrona
        if TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET:
            self.twitch = Twitch(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)

    async def initialize(self):
        """Inicializa as APIs de forma assíncrona"""
        if self.twitch:
            try:
                # Agora aguardamos corretamente a autenticação
                await self.twitch.authenticate_app([])
                logging.info("Twitch API autenticada com sucesso!")
            except Exception as e:
                logging.error(f"Falha ao autenticar Twitch na inicialização: {e}")
                self.twitch = None

    async def ensure_twitch_authenticated(self) -> bool:
        """Garante que self.twitch está autenticado (tenta reautenticar se necessário).
        Retorna True se a instância autenticada estiver pronta para uso, False caso contrário.
        """
        if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
            logging.error("TWITCH_CLIENT_ID ou TWITCH_CLIENT_SECRET não configurados.")
            return False

        if self.twitch is None:
            try:
                self.twitch = Twitch(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)
                await self.twitch.authenticate_app([])
                return True
            except Exception as e:
                logging.error(f"Falha ao (re)autenticar Twitch: {e}")
                self.twitch = None
                return False

        # Se já temos uma instância, assumimos que está autenticada; operações terão tratamento de erro
        return True

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
            thumbnails = video['snippet']['thumbnails']

            # Se é um vídeo novo
            if video_id != channel.last_video_id:
                # Pega a melhor qualidade de thumbnail disponível
                if 'maxres' in thumbnails:
                    thumbnail_url = thumbnails['maxres']['url']
                elif 'high' in thumbnails:
                    thumbnail_url = thumbnails['high']['url']
                elif 'medium' in thumbnails:
                    thumbnail_url = thumbnails['medium']['url']
                else:
                    thumbnail_url = thumbnails['default']['url']

                return {
                    'type': 'video',
                    'title': video['snippet']['title'],
                    'url': f'https://www.youtube.com/watch?v={video_id}',
                    'thumbnail': thumbnail_url,
                    'video_id': video_id
                }
            return None
        except Exception as e:
            logging.error(f"Erro ao verificar canal YouTube {channel.channel_name}: {str(e)}")
            return None

    async def check_twitch_updates(self, channel: MonitoredChannel) -> Optional[dict]:
        """Verifica atualizações de um canal da Twitch"""
        try:
            # Garante autenticação antes de chamar a API
            if not await self.ensure_twitch_authenticated():
                logging.error("Twitch não autenticada ao verificar atualizações.")
                return None
            # Verifica se o canal está ao vivo
            try:
                streams = self.twitch.get_streams(user_login=[channel.channel_name])['data']
            except Exception as e:
                logging.warning(f"Erro na chamada Twitch get_streams: {e}. Tentando reautenticar e repetir.")
                # Tenta reautenticar uma vez e repetir
                if await self.ensure_twitch_authenticated():
                    try:
                        streams = self.twitch.get_streams(user_login=[channel.channel_name])['data']
                    except Exception as e2:
                        logging.error(f"Falha após reautenticar ao chamar get_streams: {e2}")
                        return None
                else:
                    return None

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
        """Extrai o ID do canal do YouTube de diferentes formatos de URL, incluindo handle (@)"""
        try:
            # Se já é um ID válido
            if input_str.startswith('UC') and len(input_str) == 24:
                return input_str

            # Se é uma URL do YouTube
            if 'youtube.com/' in input_str:
                # Se é URL de canal direto
                if '/channel/' in input_str:
                    return input_str.split('/channel/')[-1].split('/')[0]
                # Se é URL de usuário
                elif '/user/' in input_str:
                    username = input_str.split('/user/')[-1].split('/')[0]
                    request = self.youtube.channels().list(
                        part="id",
                        forUsername=username
                    )
                    response = request.execute()
                    if response.get('items'):
                        return response['items'][0]['id']
                    return None
                # Se é URL de handle (@)
                elif '/@' in input_str:
                    handle = input_str.split('/@')[-1].split('/')[0]
                    request = self.youtube.channels().list(
                        part="id",
                        forHandle=handle
                    )
                    response = request.execute()
                    if response.get('items'):
                        return response['items'][0]['id']
                    return None

            # Se é um @handle puro
            if input_str.startswith('@'):
                handle = input_str.lstrip('@').split('/')[0]
                request = self.youtube.channels().list(
                    part="id",
                    forHandle=handle
                )
                response = request.execute()
                if response.get('items'):
                    return response['items'][0]['id']
                return None

            # Se é nome de usuário
            username = input_str.lstrip('@')
            request = self.youtube.channels().list(
                part="id",
                forUsername=username
            )
            response = request.execute()
            if response.get('items'):
                return response['items'][0]['id']

            return None
        except Exception as e:
            logging.error(f"Erro ao extrair ID do canal YouTube: {str(e)}")
            return None

    async def validate_twitch_channel(self, channel_name: str) -> Optional[dict]:
        """Valida se um canal da Twitch existe e retorna suas informações"""
        try:
            # Remove @ se existir e limpa o nome do canal
            channel_name = channel_name.lstrip('@').lower()

            # Garante autenticação antes de chamar a API
            if not await self.ensure_twitch_authenticated():
                logging.error("Twitch não autenticada ao validar canal.")
                return None
            # Busca informações do canal
            try:
                users_generator = self.twitch.get_users(logins=[channel_name])
                users = []
                async for user_data in users_generator:
                    users.append(user_data)
            except Exception as e:
                logging.warning(f"Erro na chamada Twitch get_users: {e}. Tentando reautenticar e repetir.")
                if await self.ensure_twitch_authenticated():
                    try:
                        users_generator = self.twitch.get_users(logins=[channel_name])
                        users = []
                        async for user_data in users_generator:
                            users.append(user_data)
                    except Exception as e2:
                        logging.error(f"Falha após reautenticar ao chamar get_users: {e2}")
                        return None
                else:
                    return None
            if users:
                user = users[0]
                return {
                    'id': user['id'],
                    'name': user['login'],
                    'display_name': user['display_name']
                }
            return None
        except Exception as e:
            logging.error(f"Erro ao validar canal Twitch {channel_name}: {str(e)}")
            return None
