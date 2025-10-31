from pymongo import MongoClient
from datetime import datetime
import logging
from config.settings import MONGODB_URI, DATABASE_NAME
from .models import UserProfile, Song, MusicPreference, MonitoredChannel
from typing import List, Optional


class Database:
    def __init__(self):
        self.client = None
        self.db = None

    def connect(self):
        """Estabelece conexão com o MongoDB"""
        try:
            self.client = MongoClient(MONGODB_URI)
            self.db = self.client[DATABASE_NAME]
            # Testa a conexão
            self.client.server_info()
            logging.info("Conexão com MongoDB estabelecida com sucesso!")
        except Exception as e:
            logging.error(f"Erro ao conectar ao MongoDB: {str(e)}")
            raise e

    def close(self):
        """Fecha a conexão com o MongoDB"""
        if self.client:
            self.client.close()
            logging.info("Conexão com MongoDB fechada.")

    async def create_user_profile(self, discord_id: str, username: str):
        """Cria um novo perfil de usuário se não existir"""
        try:
            profile = UserProfile(
                discord_id=discord_id,
                username=username,
                music_history=[],
                music_preferences=[],
                created_at=datetime.utcnow()
            )

            result = self.db.user_profiles.update_one(
                {"discord_id": discord_id},
                {"$setOnInsert": profile.to_dict()},
                upsert=True
            )
            if result.upserted_id:
                logging.info(f"Novo perfil criado para usuário {username}")
            return True
        except Exception as e:
            logging.error(f"Erro ao criar perfil do usuário: {str(e)}")
            return False

    async def add_music_preference(self, discord_id: str, name: str, pref_type: str):
        """Adiciona ou atualiza uma preferência musical"""
        try:
            now = datetime.utcnow()
            result = self.db.user_profiles.update_one(
                {
                    "discord_id": discord_id,
                    "music_preferences": {
                        "$not": {
                            "$elemMatch": {
                                "name": name,
                                "type": pref_type
                            }
                        }
                    }
                },
                {
                    "$push": {
                        "music_preferences": {
                            "name": name,
                            "type": pref_type,
                            "count": 1,
                            "last_updated": now
                        }
                    }
                }
            )

            if result.modified_count == 0:
                # Preferência já existe, incrementa o contador
                self.db.user_profiles.update_one(
                    {
                        "discord_id": discord_id,
                        "music_preferences.name": name,
                        "music_preferences.type": pref_type
                    },
                    {
                        "$inc": {"music_preferences.$.count": 1},
                        "$set": {"music_preferences.$.last_updated": now}
                    }
                )

            logging.info(f"Preferência musical {name} ({pref_type}) atualizada para usuário {discord_id}")
            return True
        except Exception as e:
            logging.error(f"Erro ao adicionar preferência musical: {str(e)}")
            return False

    async def add_to_music_history(self, discord_id: str, song_info: dict):
        """Adiciona uma música ao histórico do usuário e atualiza preferências"""
        try:
            song = Song(
                title=song_info['title'],
                url=song_info['url'],
                played_at=datetime.utcnow(),
                artist=song_info.get('artist'),
                genre=song_info.get('genre')
            )

            # Adiciona ao histórico
            result = self.db.user_profiles.update_one(
                {"discord_id": discord_id},
                {
                    "$push": {
                        "music_history": {
                            "$each": [vars(song)],
                            "$slice": -100  # Mantém apenas as últimas 100 músicas
                        }
                    }
                }
            )

            # Atualiza preferências se houver artista ou gênero
            if song.artist:
                await self.add_music_preference(discord_id, song.artist, 'artist')
            if song.genre:
                await self.add_music_preference(discord_id, song.genre, 'genre')

            logging.info(f"Música adicionada ao histórico do usuário {discord_id}")
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao adicionar música ao histórico: {str(e)}")
            return False

    async def get_top_preferences(self, discord_id: str, pref_type: Optional[str] = None, limit: int = 5) -> List[
        MusicPreference]:
        """Retorna as principais preferências musicais do usuário"""
        try:
            user = await self.get_user_profile(discord_id)
            if not user:
                return []

            prefs = user.music_preferences
            if pref_type:
                prefs = [p for p in prefs if p.type == pref_type]

            return sorted(prefs, key=lambda x: x.count, reverse=True)[:limit]
        except Exception as e:
            logging.error(f"Erro ao recuperar preferências musicais: {str(e)}")
            return []

    async def get_user_profile(self, discord_id: str) -> UserProfile:
        """Recupera o perfil do usuário"""
        try:
            data = self.db.user_profiles.find_one({"discord_id": discord_id})
            if data:
                return UserProfile.from_dict(data)
            return None
        except Exception as e:
            logging.error(f"Erro ao recuperar perfil do usuário: {str(e)}")
            return None

    async def add_monitored_channel(self, discord_id: str, channel: MonitoredChannel) -> bool:
        """Adiciona um canal para monitoramento"""
        try:
            # Primeiro verifica se o canal já está sendo monitorado
            result = await self.db.user_profiles.find_one({
                "discord_id": discord_id,
                "monitored_channels": {
                    "$elemMatch": {
                        "platform": channel.platform,
                        "channel_id": channel.channel_id
                    }
                }
            })

            if result:
                return False  # Canal já está sendo monitorado

            # Adiciona o novo canal
            result = await self.db.user_profiles.update_one(
                {"discord_id": discord_id},
                {"$push": {"monitored_channels": channel.__dict__}}
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao adicionar canal monitorado: {str(e)}")
            return False

    async def remove_monitored_channel(self, discord_id: str, platform: str, channel_name: str) -> bool:
        """Remove um canal do monitoramento"""
        try:
            result = await self.db.user_profiles.update_one(
                {"discord_id": discord_id},
                {
                    "$pull": {
                        "monitored_channels": {
                            "platform": platform,
                            "channel_name": channel_name
                        }
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao remover canal monitorado: {str(e)}")
            return False

    async def update_channel_last_video(self, discord_id: str, channel_id: str, video_id: str) -> bool:
        """Atualiza o ID do último vídeo de um canal do YouTube"""
        try:
            result = await self.db.user_profiles.update_one(
                {
                    "discord_id": discord_id,
                    "monitored_channels": {
                        "$elemMatch": {
                            "channel_id": channel_id,
                            "platform": "youtube"
                        }
                    }
                },
                {
                    "$set": {
                        "monitored_channels.$.last_video_id": video_id
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao atualizar último vídeo: {str(e)}")
            return False

    async def update_channel_stream_status(self, discord_id: str, channel_id: str, stream_id: str) -> bool:
        """Atualiza o status de live de um canal da Twitch"""
        try:
            result = await self.db.user_profiles.update_one(
                {
                    "discord_id": discord_id,
                    "monitored_channels": {
                        "$elemMatch": {
                            "channel_id": channel_id,
                            "platform": "twitch"
                        }
                    }
                },
                {
                    "$set": {
                        "monitored_channels.$.last_stream_id": stream_id,
                        "monitored_channels.$.is_live": bool(stream_id)
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao atualizar status de live: {str(e)}")
            return False

    async def get_all_profiles_with_monitored_channels(self) -> List[UserProfile]:
        """Retorna todos os perfis que têm canais monitorados"""
        try:
            profiles = []
            cursor = self.db.user_profiles.find(
                {"monitored_channels": {"$exists": True, "$ne": []}}
            )
            async for doc in cursor:
                profiles.append(UserProfile.from_dict(doc))
            return profiles
        except Exception as e:
            logging.error(f"Erro ao buscar perfis com canais monitorados: {str(e)}")
            return []


# Instância global do banco de dados
db = Database()
