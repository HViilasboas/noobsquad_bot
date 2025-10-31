import logging
import discord
from discord.ext import commands
import yt_dlp
import asyncio
from collections import deque
import os
from discord.ext import commands, tasks

from config.settings import CHAT_JUKEBOX, NOTIFICATION_CHANNEL_ID
from db.database import db
from .utils import clean_youtube_url, is_youtube_url, stream_musica
from .monitor import ChannelMonitor
from db.models import MonitoredChannel

# Variáveis globais compartilhadas
play_queue = {}
last_played_info = {}
autoplay_enabled = {}

async def tocar_proxima_musica(vc, guild_id, ctx):
    """Toca a próxima música da fila ou busca uma recomendada se auto-play estiver ativo."""
    if guild_id not in play_queue or not play_queue[guild_id]:
        if autoplay_enabled.get(guild_id, False):
            if guild_id in last_played_info and 'related_videos' in last_played_info[guild_id]:
                related_videos = last_played_info[guild_id]['related_videos']

                next_url = None
                for video in related_videos:
                    if video.get('url') and is_youtube_url(video['url']):
                        next_url = video['url']
                        break

                if next_url:
                    logging.info(f"Fila vazia. Adicionando música recomendada: {next_url}")
                    await ctx.send(f"Fila vazia. Reproduzindo uma música recomendada.")
                    play_queue[guild_id].append((next_url, "padrao"))
                else:
                    await ctx.send("Nenhuma música recomendada encontrada. A reprodução parou.")
                    await vc.disconnect()
                    return
            else:
                await ctx.send("A fila de músicas está vazia e não há recomendações. A reprodução parou.")
                await vc.disconnect()
                return
        else:
            await ctx.send("A fila de músicas está vazia. Desconectando do canal de voz.")
            await vc.disconnect()
            return

    url, preset_name = play_queue[guild_id].popleft()
    source, stream_title, info = await stream_musica(url, preset_name)

    if source:
        last_played_info[guild_id] = info
        try:
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
                tocar_proxima_musica(vc, guild_id, ctx), ctx.bot.loop))
            await ctx.send(f'Transmitindo agora: **{stream_title}** com preset `{preset_name}`')
        except Exception as e:
            logging.error(f"Erro ao transmitir `{stream_title}`: {str(e)}")
            await ctx.send(f"Erro ao transmitir `{stream_title}`: {str(e)}")
            await tocar_proxima_musica(vc, guild_id, ctx)
    else:
        await ctx.send(f"Erro ao processar o stream. Pulando para a próxima música da fila.")
        await tocar_proxima_musica(vc, guild_id, ctx)

def validar_canal(ctx):
    """Valida se o comando foi enviado no canal de texto permitido."""
    ALLOWED_CHANNEL_ID = int(os.getenv('CHAT_JUKEBOX', 0))
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        return False
    return True

class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='play')
    async def play(self, ctx, arg: str, *args):
        """Toca uma música ou adiciona à fila"""
        if not validar_canal(ctx):
            await ctx.send("Use o canal correto para o comando `!play`.")
            return

        if not ctx.author.voice:
            await ctx.send("Você precisa estar em um canal de voz para tocar música.")
            return

        guild_id = ctx.guild.id
        if guild_id not in play_queue:
            play_queue[guild_id] = deque()

        if not ctx.guild.voice_client:
            try:
                vc = await ctx.author.voice.channel.connect(reconnect=True, self_deaf=True)
            except Exception as e:
                logging.error(f'Erro ao conectar ao canal de voz: {e}')
                await ctx.send("Não foi possível conectar ao canal de voz.")
                return
        else:
            vc = ctx.guild.voice_client

        preset_name = "padrao"
        if 'autoplay' in args:
            autoplay_enabled[guild_id] = True
            args = [a for a in args if a != 'autoplay']

        cleaned_url = clean_youtube_url(arg)
        if not is_youtube_url(cleaned_url):
            await ctx.send("URL inválida. Use uma URL do YouTube.")
            return

        try:
            async with ctx.typing():
                with yt_dlp.YoutubeDL({'extract_flat': 'True', 'quiet': True}) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, cleaned_url, download=False)

            if 'entries' in info:
                title = info.get('title', 'Playlist')
                playlist_urls = [entry['url'] for entry in info['entries']]
                await db.create_user_profile(str(ctx.author.id), ctx.author.name)

                for playlist_url in playlist_urls:
                    play_queue[guild_id].append((playlist_url, preset_name))

                await ctx.send(f'Adicionando **{len(playlist_urls)}** músicas da playlist **{title}** à fila.')
            else:
                title = info.get('title', 'Desconhecido')
                play_queue[guild_id].append((cleaned_url, preset_name))

                await db.create_user_profile(str(ctx.author.id), ctx.author.name)
                await db.add_to_music_history(str(ctx.author.id), {
                    "title": title,
                    "url": cleaned_url
                })

                await ctx.send(f'Adicionado à fila: **{title}** com preset `{preset_name}`')

            if not vc.is_playing() and not vc.is_paused():
                await tocar_proxima_musica(vc, guild_id, ctx)

        except Exception as e:
            logging.error(f'Erro ao processar música: {e}')
            await ctx.send("Ocorreu um erro ao processar a música.")

    @commands.command(name='stop')
    async def stop(self, ctx):
        """Para a reprodução atual"""
        if ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
            ctx.guild.voice_client.stop()
            await ctx.send("Reprodução parada.")
        else:
            await ctx.send("Nenhuma música está tocando.")

    @commands.command(name='skip')
    async def skip(self, ctx):
        """Pula a música atual"""
        if ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
            ctx.guild.voice_client.stop()
            await ctx.send("Música pulada!")
        else:
            await ctx.send("Nenhuma música está tocando.")

    @commands.command(name='leave')
    async def leave(self, ctx):
        """Faz o bot sair do canal de voz"""
        if ctx.guild.voice_client:
            guild_id = ctx.guild.id
            if guild_id in play_queue:
                play_queue[guild_id].clear()
            await ctx.guild.voice_client.disconnect()
            await ctx.send("Desconectado do canal de voz.")
        else:
            await ctx.send("Não estou em nenhum canal de voz.")

    @commands.command(name='profile')
    async def profile(self, ctx):
        """Mostra o perfil musical do usuário"""
        user_profile = await db.get_user_profile(str(ctx.author.id))
        if not user_profile:
            await ctx.send("Você ainda não tem um perfil! Use o comando `!play` para começar.")
            return

        history_text = "\n".join([
            f"• {song.title}" + (f" - {song.artist}" if song.artist else "") +
            f" ({song.played_at.strftime('%d/%m/%Y %H:%M')})"
            for song in user_profile.music_history[-5:]
        ]) or "Nenhuma música tocada ainda"

        top_artists = await db.get_top_preferences(str(ctx.author.id), 'artist', 5)
        top_genres = await db.get_top_preferences(str(ctx.author.id), 'genre', 5)

        artists_text = "\n".join([
            f"• {pref.name} ({pref.count} músicas)"
            for pref in top_artists
        ]) or "Nenhum artista definido"

        genres_text = "\n".join([
            f"• {pref.name} ({pref.count} músicas)"
            for pref in top_genres
        ]) or "Nenhum gênero definido"

        embed = discord.Embed(
            title=f"Perfil Musical de {user_profile.username}",
            color=0x00ff00,
            timestamp=user_profile.created_at
        )
        embed.add_field(name="📜 Histórico Recente", value=history_text, inline=False)
        embed.add_field(name="🎤 Artistas Favoritos", value=artists_text, inline=True)
        embed.add_field(name="🎵 Gêneros Favoritos", value=genres_text, inline=True)
        embed.set_footer(text="Perfil criado em")

        await ctx.send(embed=embed)

    @commands.command(name='recommend')
    async def recommend(self, ctx):
        """Recomenda músicas baseadas nas preferências"""
        user_profile = await db.get_user_profile(str(ctx.author.id))
        if not user_profile or not user_profile.music_preferences:
            await ctx.send("Você precisa ter preferências musicais registradas!")
            return

        top_prefs = sorted(user_profile.music_preferences, key=lambda x: x.count, reverse=True)[:3]
        search_terms = " OR ".join([f"\"{pref.name}\"" for pref in top_prefs])

        try:
            with yt_dlp.YoutubeDL({
                'quiet': True,
                'extract_flat': True,
                'default_search': 'ytsearch5'
            }) as ydl:
                result = await asyncio.to_thread(
                    ydl.extract_info,
                    f"ytsearch5:{search_terms.replace('&', 'and')}",
                    download=False
                )

                if result and 'entries' in result:
                    embed = discord.Embed(
                        title="🎵 Recomendações Musicais",
                        description=f"Com base em: {', '.join([p.name for p in top_prefs])}",
                        color=0x00ff00
                    )

                    for entry in result['entries'][:5]:
                        if entry:
                            embed.add_field(
                                name=entry.get('title', 'Sem título'),
                                value=f"[Tocar no YouTube]({entry.get('url', '')})",
                                inline=False
                            )

                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Não foi possível encontrar recomendações.")
        except Exception as e:
            logging.error(f"Erro ao buscar recomendações: {str(e)}")
            await ctx.send("Erro ao buscar recomendações. Tente novamente.")

class MonitorCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monitor = ChannelMonitor()
        self.check_updates.start()

    def cog_unload(self):
        self.check_updates.cancel()

    @tasks.loop(seconds=60)  # Checa a cada minuto
    async def check_updates(self):
        """Task que verifica atualizações nos canais monitorados"""
        if not self.bot.is_ready():
            return

        notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification_channel:
            logging.error(f"Canal de notificação {NOTIFICATION_CHANNEL_ID} não encontrado!")
            return

        try:
            # Busca todos os perfis que têm canais monitorados
            all_profiles = await db.get_all_profiles_with_monitored_channels()

            for profile in all_profiles:
                for channel in profile.monitored_channels:
                    if channel.platform == 'youtube':
                        update = await self.monitor.check_youtube_updates(channel)
                        if update:
                            embed = discord.Embed(
                                title=f"🎥 Novo vídeo em {channel.channel_name}!",
                                description=update['title'],
                                url=update['url'],
                                color=0xff0000
                            )
                            embed.set_thumbnail(url=update['thumbnail'])
                            await notification_channel.send(embed=embed)

                            # Atualiza o último vídeo no banco
                            await db.update_channel_last_video(
                                profile.discord_id,
                                channel.channel_id,
                                update['video_id']
                            )

                    elif channel.platform == 'twitch':
                        update = await self.monitor.check_twitch_updates(channel)
                        if update:
                            embed = discord.Embed(
                                title=f"🔴 {channel.channel_name} está AO VIVO!",
                                description=update['title'],
                                url=update['url'],
                                color=0x6441a5
                            )
                            embed.set_thumbnail(url=update['thumbnail'])
                            await notification_channel.send(embed=embed)

                            # Atualiza o status da live no banco
                            await db.update_channel_stream_status(
                                profile.discord_id,
                                channel.channel_id,
                                update['stream_id']
                            )

        except Exception as e:
            logging.error(f"Erro ao verificar atualizações: {str(e)}")

    @commands.command(name='monitorar_youtube')
    async def monitor_youtube(self, ctx, *, channel_input: str):
        """Adiciona um canal do YouTube para monitoramento
        Uso: !monitorar_youtube <url_do_canal ou @nome>"""
        try:
            channel_id = await self.monitor.extract_youtube_channel_id(channel_input)
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

            # Adiciona ao banco de dados
            success = await db.add_monitored_channel(str(ctx.author.id), channel)
            if success:
                embed = discord.Embed(
                    title="✅ Canal Adicionado!",
                    description=f"Agora monitorando: **{channel.channel_name}**\nVocê receberá notificações de novos vídeos.",
                    color=0x00ff00
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Erro ao adicionar canal. Talvez ele já esteja sendo monitorado?")

        except Exception as e:
            logging.error(f"Erro ao adicionar canal YouTube: {str(e)}")
            await ctx.send("❌ Ocorreu um erro ao adicionar o canal.")

    @commands.command(name='monitorar_twitch')
    async def monitor_twitch(self, ctx, channel_name: str):
        """Adiciona um canal da Twitch para monitoramento
        Uso: !monitorar_twitch <nome_do_canal>"""
        try:
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
            success = await db.add_monitored_channel(str(ctx.author.id), channel)
            if success:
                embed = discord.Embed(
                    title="✅ Canal Adicionado!",
                    description=f"Agora monitorando: **{channel_info['display_name']}**\nVocê receberá notificações quando o canal estiver ao vivo.",
                    color=0x6441a5
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Erro ao adicionar canal. Talvez ele já esteja sendo monitorado?")

        except Exception as e:
            logging.error(f"Erro ao adicionar canal Twitch: {str(e)}")
            await ctx.send("❌ Ocorreu um erro ao adicionar o canal.")

    @commands.command(name='listar_monitoramento')
    async def list_monitored(self, ctx):
        """Lista todos os canais monitorados pelo usuário"""
        try:
            profile = await db.get_user_profile(str(ctx.author.id))
            if not profile or not profile.monitored_channels:
                await ctx.send("Você não está monitorando nenhum canal!")
                return

            embed = discord.Embed(
                title="📺 Seus Canais Monitorados",
                color=0x00ff00
            )

            youtube_channels = [c for c in profile.monitored_channels if c.platform == 'youtube']
            twitch_channels = [c for c in profile.monitored_channels if c.platform == 'twitch']

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

    @commands.command(name='remover_monitoramento')
    async def remove_monitored(self, ctx, platform: str, *, channel_name: str):
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
