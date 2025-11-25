from pymongo import MongoClient
from datetime import datetime
import logging
from config.settings import MONGODB_URI, DATABASE_NAME
from .models import UserProfile, Song, MusicPreference, MonitoredChannel, UserActivity
from typing import List, Optional


class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.user_profiles = None  # Referência para a coleção user_profiles
        self.monitored_channels = None  # Nova coleção para canais monitorados

    def connect(self):
        """Estabelece conexão com o MongoDB"""
        try:
            self.client = MongoClient(MONGODB_URI)
            self.db = self.client[DATABASE_NAME]
            # Inicializa as coleções
            self.user_profiles = self.db.user_profiles
            self.monitored_channels = self.db.monitored_channels
            self.user_activities = (
                self.db.user_activities
            )  # Nova coleção para atividades
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
            # Criamos um novo perfil - os valores padrão serão inicializados pelo __post_init__
            profile = UserProfile(discord_id=discord_id, username=username)

            result = self.db.user_profiles.update_one(
                {"discord_id": discord_id},
                {"$setOnInsert": profile.to_dict()},
                upsert=True,
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
                        "$not": {"$elemMatch": {"name": name, "type": pref_type}}
                    },
                },
                {
                    "$push": {
                        "music_preferences": {
                            "name": name,
                            "type": pref_type,
                            "count": 1,
                            "last_updated": now,
                        }
                    }
                },
            )

            if result.modified_count == 0:
                # Preferência já existe, incrementa o contador
                self.db.user_profiles.update_one(
                    {
                        "discord_id": discord_id,
                        "music_preferences.name": name,
                        "music_preferences.type": pref_type,
                    },
                    {
                        "$inc": {"music_preferences.$.count": 1},
                        "$set": {"music_preferences.$.last_updated": now},
                    },
                )

            logging.info(
                f"Preferência musical {name} ({pref_type}) atualizada para usuário {discord_id}"
            )
            return True
        except Exception as e:
            logging.error(f"Erro ao adicionar preferência musical: {str(e)}")
            return False

    async def add_to_music_history(self, discord_id: str, song_info: dict):
        """Adiciona uma música ao histórico do usuário e atualiza preferências"""
        try:
            song = Song(
                title=song_info["title"],
                url=song_info["url"],
                played_at=datetime.utcnow(),
                artist=song_info.get("artist"),
                genre=song_info.get("genre"),
            )

            # Adiciona ao histórico
            result = self.db.user_profiles.update_one(
                {"discord_id": discord_id},
                {
                    "$push": {
                        "music_history": {
                            "$each": [vars(song)],
                            "$slice": -100,  # Mantém apenas as últimas 100 músicas
                        }
                    }
                },
            )

            # Atualiza preferências se houver artista ou gênero
            if song.artist:
                await self.add_music_preference(discord_id, song.artist, "artist")
            if song.genre:
                await self.add_music_preference(discord_id, song.genre, "genre")

            logging.info(f"Música adicionada ao histórico do usuário {discord_id}")
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao adicionar música ao histórico: {str(e)}")
            return False

    async def get_top_preferences(
        self, discord_id: str, pref_type: Optional[str] = None, limit: int = 5
    ) -> List[MusicPreference]:
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

    async def add_monitored_channel(
        self, discord_id: str, channel: MonitoredChannel
    ) -> bool:
        """Adiciona um canal para monitoramento na coleção `monitored_channels`.

        Se o documento do canal já existir, apenas adiciona o usuário à lista de subscribers
        (se ainda não for assinante). Caso contrário cria o documento com o primeiro assinante.
        """
        try:
            # Tenta encontrar um documento existente pelo platform+channel_id
            existing = self.monitored_channels.find_one(
                {"platform": channel.platform, "channel_id": channel.channel_id}
            )

            if existing:
                # Se o usuário já é subscriber, não faz nada
                if str(discord_id) in existing.get("subscribers", []):
                    return False
                # Adiciona o subscriber ao documento do canal
                result = self.monitored_channels.update_one(
                    {"_id": existing["_id"]},
                    {"$addToSet": {"subscribers": str(discord_id)}},
                )
                return result.modified_count > 0

            # Cria novo documento de canal
            channel.subscribers = [str(discord_id)]
            result = self.monitored_channels.insert_one(channel.to_dict())
            return result.acknowledged
        except Exception as e:
            logging.error(f"Erro ao adicionar canal monitorado: {str(e)}")
            return False

    async def remove_monitored_channel(
        self, discord_id: str, platform: str, channel_name: str
    ) -> bool:
        """Remove um canal do monitoramento para um usuário específico.

        Se o usuário for o único subscriber, o documento do canal será removido.
        Caso contrário, apenas será removido da lista de subscribers.
        """
        try:
            # Tenta encontrar o canal pelo platform e channel_name
            doc = self.monitored_channels.find_one(
                {"platform": platform, "channel_name": channel_name}
            )
            if not doc:
                return False

            # Se o usuário não está na lista de subscribers
            if str(discord_id) not in doc.get("subscribers", []):
                return False

            # Se há mais de um subscriber, apenas remove o usuário
            if len(doc.get("subscribers", [])) > 1:
                result = self.monitored_channels.update_one(
                    {"_id": doc["_id"]}, {"$pull": {"subscribers": str(discord_id)}}
                )
                return result.modified_count > 0

            # Caso contrário, remove o documento do canal por completo
            result = self.monitored_channels.delete_one({"_id": doc["_id"]})
            return result.deleted_count > 0
        except Exception as e:
            logging.error(f"Erro ao remover canal monitorado: {str(e)}")
            return False

    async def update_channel_last_video(
        self, discord_id: str, channel_id: str, video_id: str
    ) -> bool:
        """Atualiza o ID do último vídeo de um canal do YouTube (baseado na coleção de canais monitorados)"""
        try:
            result = self.monitored_channels.update_one(
                {"channel_id": channel_id, "platform": "youtube"},
                {"$set": {"last_video_id": video_id}},
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao atualizar último vídeo: {str(e)}")
            return False

    async def update_channel_stream_status(
        self, discord_id: str, channel_id: str, stream_id: str
    ) -> bool:
        """Atualiza o status de live de um canal da Twitch (na coleção de canais monitorados)"""
        try:
            result = self.monitored_channels.update_one(
                {"channel_id": channel_id, "platform": "twitch"},
                {"$set": {"last_stream_id": stream_id, "is_live": bool(stream_id)}},
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Erro ao atualizar status de live: {str(e)}")
            return False

    async def get_all_monitored_channels(self) -> List[MonitoredChannel]:
        """Retorna todos os canais monitorados (cada documento contém subscribers)."""
        try:
            channels = []
            cursor = self.monitored_channels.find({})
            for doc in cursor:
                channels.append(MonitoredChannel.from_dict(doc))
            return channels
        except Exception as e:
            logging.error(f"Erro ao buscar canais monitorados: {str(e)}")
            return []

    async def get_profiles_with_monitored_channels(self) -> List[UserProfile]:
        """Compat layer: Retorna perfis dos usuários que têm ao menos um canal monitorado.

        Este método preserva a interface esperada pelo scheduler e outros módulos:
        - Antes: retornava UserProfile com `monitored_channels` embutidos.
        - Agora: retornará UserProfile com monitored_channels preenchidos a partir da coleção separada.
        """
        try:
            profiles = []
            # Obter todos os canais monitorados e agrupar por subscriber
            cursor = self.monitored_channels.find({})

            # mapa de discord_id -> list[MonitoredChannel]
            grouped = {}
            for doc in cursor:
                channel = MonitoredChannel.from_dict(doc)
                for sub in doc.get("subscribers", []):
                    grouped.setdefault(str(sub), []).append(channel)

            # Para cada subscriber, buscar o perfil e anexar a lista de canais
            for discord_id, channels in grouped.items():
                user_doc = self.user_profiles.find_one({"discord_id": discord_id})
                if user_doc:
                    profile = UserProfile.from_dict(user_doc)
                else:
                    # Cria um perfil mínimo caso não exista
                    profile = UserProfile(
                        discord_id=discord_id, username=str(discord_id)
                    )
                # Atribui a lista de canais para compatibilidade com o restante do código
                # Observação: UserProfile não tem mais o campo monitored_channels, mas o resto do
                # código espera que o objeto retornado tenha esse atributo; adicionamos dinamicamente.
                setattr(profile, "monitored_channels", channels)
                profiles.append(profile)

# Instância global do banco de dados
db = Database()
