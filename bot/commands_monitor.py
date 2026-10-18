import logging
from typing import Literal, Optional
import discord
from discord.ext import commands
from config.settings import NOTIFICATION_CHANNEL_ID
from db.database import db
from .monitor import ChannelMonitor
from db.models import MonitoredChannel


class MonitorCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monitor = ChannelMonitor()
        # Inicializar o monitor de forma assíncrona quando o Cog é carregado
        bot.loop.create_task(self._initialize_monitor())

    async def _ensure_user_profile(self, author: discord.User):
        """Garante que um perfil de usuário exista no banco de dados."""
        user_id = str(author.id)
        profile = await db.get_user_profile(user_id)
        if not profile:
            await db.create_user_profile(user_id, author.name)
            logging.info(f"Perfil de usuário criado para {user_id} ({author.name})")

    async def _initialize_monitor(self):
        """Inicializa o monitor"""
        await self.monitor.initialize()
        logging.info("Monitor inicializado com sucesso!")

    def cog_unload(self):
        """Chamado quando o Cog é descarregado"""
        logging.info("Monitor descarregado")

    @commands.hybrid_command(name='monitorar_youtube', description='Monitora um canal do YouTube')
    async def monitor_youtube(self, ctx, channel_input: str,
                              destino: Optional[discord.TextChannel] = None,
                              mencionar: bool = False):
        """Adiciona um canal do YouTube para monitoramento
        Uso: !monitorar_youtube <url_do_canal ou @nome>"""
        try:
            # Garante que o perfil do usuário existe
            await self._ensure_user_profile(ctx.author)

            channel_id = self.monitor.extract_youtube_channel_id(channel_input)
            if not channel_id:
                await ctx.send("❌ Canal não encontrado! Verifique o link ou ID fornecido.")
                return

            # Busca informações do canal
            channel_info = self.monitor.youtube.channels().list(
                part="snippet",
                id=channel_id
            ).execute()['items'][0]

            channel = MonitoredChannel(
                platform='youtube',
                channel_id=channel_id,
                channel_name=channel_info['snippet']['title'],
                added_by=str(ctx.author.id)
            )

            # Adiciona ao banco de dados (coleção separada)
            target = destino or ctx.channel
            success = await db.add_monitored_channel(
                str(ctx.author.id), channel, target.id, mencionar
            )
            if success:
                embed = discord.Embed(
                    title="✅ Canal Adicionado!",
                    description=f"Agora monitorando: **{channel.channel_name}**\nDestino: {target.mention}",
                    color=0x00ff00
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Erro ao adicionar canal. Talvez ele já esteja sendo monitorado por você?")

        except Exception as e:
            logging.error(f"Erro ao adicionar canal YouTube: {str(e)}")
            await ctx.send("❌ Ocorreu um erro ao adicionar o canal.")

    @commands.hybrid_command(name='monitorar_twitch', description='Monitora um canal da Twitch')
    async def monitor_twitch(self, ctx, channel_name: str,
                             destino: Optional[discord.TextChannel] = None,
                             mencionar: bool = False):
        """Adiciona um canal da Twitch para monitoramento
        Uso: !monitorar_twitch <nome_do_canal>"""
        try:
            # Garante que o perfil do usuário existe
            await self._ensure_user_profile(ctx.author)

            channel_info = await self.monitor.validate_twitch_channel(channel_name)
            if not channel_info:
                await ctx.send("❌ Canal não encontrado! Verifique o nome fornecido.")
                return

            channel = MonitoredChannel(
                platform='twitch',
                channel_id=channel_info['id'],
                channel_name=channel_info['name'],
                added_by=str(ctx.author.id)
            )

            # Adiciona ao banco de dados
            target = destino or ctx.channel
            success = await db.add_monitored_channel(
                str(ctx.author.id), channel, target.id, mencionar
            )
            if success:
                embed = discord.Embed(
                    title="✅ Canal Adicionado!",
                    description=f"Agora monitorando: **{channel_info['display_name']}**\nDestino: {target.mention}",
                    color=0x6441a5
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Erro ao adicionar canal. Talvez ele já esteja sendo monitorado por você?")

        except Exception as e:
            logging.error(f"Erro ao adicionar canal Twitch: {str(e)}")
            await ctx.send("❌ Ocorreu um erro ao adicionar o canal Twitch.")

    @commands.hybrid_command(name='listar_monitoramento', description='Lista suas assinaturas de monitoramento')
    async def list_monitored(self, ctx):
        """Lista todos os canais monitorados pelo usuário"""
        try:
            user_id = str(ctx.author.id)
            # Busca na coleção monitored_channels todos os documentos onde o usuário é subscriber
            cursor = db.monitored_channels.find({'subscribers': user_id})
            channels = [MonitoredChannel.from_dict(doc) for doc in cursor]

            if not channels:
                await ctx.send("Você não está monitorando nenhum canal!")
                return

            embed = discord.Embed(
                title="📺 Seus Canais Monitorados",
                color=0x00ff00
            )

            youtube_channels = [c for c in channels if c.platform == 'youtube']
            twitch_channels = [c for c in channels if c.platform == 'twitch']

            if youtube_channels:
                youtube_text = "\n".join(f"• {c.channel_name}" for c in youtube_channels)
                embed.add_field(name="YouTube 🎥", value=youtube_text, inline=False)

            if twitch_channels:
                twitch_text = "\n".join(f"• {c.channel_name}" for c in twitch_channels)
                embed.add_field(name="Twitch 🔴", value=twitch_text, inline=False)

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Erro ao listar canais: {str(e)}")
            await ctx.send("❌ Ocorreu um erro ao listar os canais.")

    @commands.hybrid_command(name='remover_monitoramento', description='Remove uma assinatura de monitoramento')
    async def remove_monitored(
        self, ctx, platform: Literal['youtube', 'twitch'], channel_name: str
    ):
        """Remove um canal do monitoramento
        Uso: !remover_monitoramento <youtube|twitch> <nome_do_canal>"""
        if platform.lower() not in ['youtube', 'twitch']:
            await ctx.send("❌ Plataforma inválida! Use 'youtube' ou 'twitch'.")
            return

        try:
            success = await db.remove_monitored_channel(
                str(ctx.author.id),
                platform.lower(),
                channel_name
            )

            if success:
                await ctx.send(f"✅ Canal **{channel_name}** removido do monitoramento!")
            else:
                await ctx.send("❌ Canal não encontrado ou você não está monitorando este canal.")
        except Exception as e:
            logging.error(f"Erro ao remover canal do monitoramento: {str(e)}")
            await ctx.send("❌ Ocorreu um erro ao remover o canal do monitoramento.")
