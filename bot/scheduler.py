import logging
import discord
from discord.ext import tasks
from config.settings import (
    NOTIFICATION_CHANNEL_ID,
    CHECK_YOUTUBE_INTERVAL,
    CHECK_TWITCH_INTERVAL
)
from db.database import db
from .monitor import ChannelMonitor


class MonitorScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.monitor = ChannelMonitor()
        self.youtube_task = None
        self.twitch_task = None

    async def start(self):
        """Inicializa o monitor e inicia as tasks de verificação"""
        await self.monitor.initialize()
        self.youtube_task = self.check_youtube_updates.start()
        self.twitch_task = self.check_twitch_updates.start()
        logging.info("Monitor inicializado e tarefas de verificação iniciadas")

    def stop(self):
        """Para todas as tasks de monitoramento"""
        if self.youtube_task:
            self.youtube_task.cancel()
        if self.twitch_task:
            self.twitch_task.cancel()
        logging.info("Tarefas de monitoramento paradas")

    @tasks.loop(seconds=CHECK_YOUTUBE_INTERVAL)
    async def check_youtube_updates(self):
        """Verifica atualizações dos canais do YouTube"""
        if not self.bot.is_ready():
            return

        notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification_channel:
            logging.error(f"Canal de notificação {NOTIFICATION_CHANNEL_ID} não encontrado!")
            return

        try:
            profiles = await db.get_profiles_with_monitored_channels()
            for profile in profiles:
                youtube_channels = [c for c in profile.monitored_channels if c.platform == 'youtube']
                for channel in youtube_channels:
                    update = await self.monitor.check_youtube_updates(channel)
                    if update:
                        embed = discord.Embed(
                            title=f"🎥 Novo vídeo em {channel.channel_name}!",
                            description=update['title'],
                            url=update['url'],
                            color=0xff0000
                        )
                        embed.set_image(url=update['thumbnail'])
                        await notification_channel.send(embed=embed)

                        # Atualiza o último vídeo no banco
                        await db.update_channel_last_video(
                            profile.discord_id,
                            channel.channel_id,
                            update['video_id']
                        )
        except Exception as e:
            logging.error(f"Erro ao verificar atualizações do YouTube: {str(e)}")

    @tasks.loop(seconds=CHECK_TWITCH_INTERVAL)
    async def check_twitch_updates(self):
        """Verifica atualizações dos canais da Twitch"""
        if not self.bot.is_ready():
            return

        notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification_channel:
            logging.error(f"Canal de notificação {NOTIFICATION_CHANNEL_ID} não encontrado!")
            return

        try:
            profiles = await db.get_profiles_with_monitored_channels()
            for profile in profiles:
                twitch_channels = [c for c in profile.monitored_channels if c.platform == 'twitch']
                for channel in twitch_channels:
                    update = await self.monitor.check_twitch_updates(channel)
                    if update:
                        embed = discord.Embed(
                            title=f"🔴 {channel.channel_name} está AO VIVO!",
                            description=update['title'],
                            url=update['url'],
                            color=0x6441a5
                        )
                        embed.set_image(url=update['thumbnail'])
                        await notification_channel.send(embed=embed)

                        # Atualiza o status da live no banco
                        await db.update_channel_stream_status(
                            profile.discord_id,
                            channel.channel_id,
                            update['stream_id']
                        )
        except Exception as e:
            logging.error(f"Erro ao verificar atualizações da Twitch: {str(e)}")

    @check_youtube_updates.before_loop
    @check_twitch_updates.before_loop
    async def before_check(self):
        """Aguarda o bot estar pronto antes de iniciar as verificações"""
        await self.bot.wait_until_ready()
