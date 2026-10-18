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

    async def _send_notification(self, monitored, embed):
        """Entrega uma atualização uma vez por destino, agrupando menções."""
        destinations = {}
        targets = monitored.subscription_targets or {}
        for subscriber in monitored.subscribers or []:
            target = targets.get(str(subscriber), {})
            channel_id = target.get("channel_id") or NOTIFICATION_CHANNEL_ID
            if not channel_id:
                continue
            bucket = destinations.setdefault(int(channel_id), [])
            if target.get("mention"):
                bucket.append(str(subscriber))

        if not destinations and NOTIFICATION_CHANNEL_ID:
            destinations[NOTIFICATION_CHANNEL_ID] = []

        for channel_id, mentions in destinations.items():
            destination = self.bot.get_channel(channel_id)
            if not destination:
                try:
                    destination = await self.bot.fetch_channel(channel_id)
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    logging.error("Canal de notificação %s indisponível", channel_id)
                    continue
            content = " ".join(f"<@{user_id}>" for user_id in mentions) or None
            await destination.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )

    @tasks.loop(seconds=CHECK_YOUTUBE_INTERVAL)
    async def check_youtube_updates(self):
        """Verifica atualizações dos canais do YouTube"""
        if not self.bot.is_ready():
            return

        try:
            channels = await db.get_all_monitored_channels()
            for channel in (c for c in channels if c.platform == "youtube"):
                update = await self.monitor.check_youtube_updates(channel)
                if not update:
                    continue
                embed = discord.Embed(
                    title=f"🎥 Novo vídeo em {channel.channel_name}!",
                    description=update['title'], url=update['url'], color=0xff0000
                )
                embed.set_image(url=update['thumbnail'])
                await self._send_notification(channel, embed)
                await db.update_channel_last_video("", channel.channel_id, update['video_id'])
        except Exception as e:
            logging.error(f"Erro ao verificar atualizações do YouTube: {str(e)}")

    @tasks.loop(seconds=CHECK_TWITCH_INTERVAL)
    async def check_twitch_updates(self):
        """Verifica atualizações dos canais da Twitch"""
        if not self.bot.is_ready():
            return

        try:
            channels = await db.get_all_monitored_channels()
            for channel in (c for c in channels if c.platform == "twitch"):
                update = await self.monitor.check_twitch_updates(channel)
                if not update:
                    continue
                if update["type"] == "live":
                    embed = discord.Embed(
                        title=f"🔴 {channel.channel_name} está AO VIVO!",
                        description=update['title'], url=update['url'], color=0x6441a5
                    )
                    embed.set_image(url=update['thumbnail'])
                    await self._send_notification(channel, embed)
                await db.update_channel_stream_status(
                    "", channel.channel_id, update.get('stream_id')
                )
        except Exception as e:
            logging.error(f"Erro ao verificar atualizações da Twitch: {str(e)}")

    @check_youtube_updates.before_loop
    @check_twitch_updates.before_loop
    async def before_check(self):
        """Aguarda o bot estar pronto antes de iniciar as verificações"""
        await self.bot.wait_until_ready()
