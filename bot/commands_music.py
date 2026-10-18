import logging
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import random
from collections import deque
from typing import Literal, Optional

from db.database import db
from .utils import (
    clean_youtube_url,
    get_youtube_playlist_url,
    is_youtube_url,
    stream_musica,
)
from .commands_utils import (
    autoplay_enabled,
    last_played_info,
    loop_mode,
    now_playing,
    play_queue,
    stop_requested,
    validar_canal,
    volume_level,
)
from .spotify import SpotifyPlaylistError, get_public_spotify_playlist, is_spotify_playlist


def _same_voice_channel(ctx) -> bool:
    """Impede que membros fora do canal controlem a sessão de voz."""
    voice_client = ctx.guild.voice_client if ctx.guild else None
    author_voice = getattr(ctx.author, "voice", None)
    return bool(voice_client and author_voice and author_voice.channel == voice_client.channel)


class MusicControls(discord.ui.View):
    """Controles simples anexados à mensagem de reprodução atual."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def _guild_id(self, interaction: discord.Interaction) -> int:
        return interaction.guild_id or self.guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        voice_client = interaction.guild.voice_client if interaction.guild else None
        member_voice = getattr(interaction.user, "voice", None)
        if voice_client and member_voice and member_voice.channel == voice_client.channel:
            return True
        await interaction.response.send_message(
            "Entre no mesmo canal de voz para usar os controles.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Pausar", emoji="⏯️", style=discord.ButtonStyle.secondary,
                       custom_id="noobsquad:music:pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client.is_paused():
            voice_client.resume()
            button.label = "Pausar"
            message = "Reprodução retomada."
        elif voice_client.is_playing():
            voice_client.pause()
            button.label = "Continuar"
            message = "Reprodução pausada."
        else:
            message = "Nenhuma música está tocando."
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Pular", emoji="⏭️", style=discord.ButtonStyle.primary,
                       custom_id="noobsquad:music:skip")
    async def skip(self, interaction: discord.Interaction, _button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        guild_id = self._guild_id(interaction)
        stop_requested[guild_id] = False
        now_playing.pop(guild_id, None)
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message("Música pulada.", ephemeral=True)
        else:
            await interaction.response.send_message("Nenhuma música está tocando.", ephemeral=True)

    @discord.ui.button(label="Parar", emoji="⏹️", style=discord.ButtonStyle.danger,
                       custom_id="noobsquad:music:stop")
    async def stop(self, interaction: discord.Interaction, _button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        guild_id = self._guild_id(interaction)
        stop_requested[guild_id] = True
        play_queue.setdefault(guild_id, deque()).clear()
        autoplay_enabled[guild_id] = False
        now_playing.pop(guild_id, None)
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
        await interaction.response.send_message("Reprodução e fila encerradas.", ephemeral=True)


async def tocar_proxima_musica(vc, guild_id, ctx):
    """Toca a próxima música da fila ou busca uma recomendada se auto-play estiver ativo."""
    if stop_requested.pop(guild_id, False):
        return

    current = now_playing.get(guild_id)
    if loop_mode.get(guild_id) == "musica" and current:
        play_queue.setdefault(guild_id, deque()).appendleft(current)
    elif loop_mode.get(guild_id) == "fila" and current:
        play_queue.setdefault(guild_id, deque()).append(current)
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
    now_playing[guild_id] = (url, preset_name)
    source, stream_title, info = await stream_musica(url, preset_name)

    if source:
        last_played_info[guild_id] = info
        try:
            channel_bitrate = max(
                16, min(getattr(vc.channel, "bitrate", 128_000) // 1000, 512)
            )
            wrapped_source = discord.PCMVolumeTransformer(
                source, volume=volume_level.get(guild_id, 100) / 100
            )
            vc.play(
                wrapped_source,
                bitrate=channel_bitrate,
                application="audio",
                bandwidth="full",
                signal_type="music",
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    tocar_proxima_musica(vc, guild_id, ctx), ctx.bot.loop
                ),
            )
            logging.info(
                "Transmitindo em PCM 48 kHz stereo / Opus %s kbps", channel_bitrate
            )
            embed = discord.Embed(
                title="🎶 Tocando agora",
                description=f"**{stream_title}**",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Preset", value=preset_name)
            embed.add_field(name="Volume", value=f"{volume_level.get(guild_id, 100)}%")
            embed.add_field(name="Fila", value=str(len(play_queue.get(guild_id, []))))
            await ctx.send(embed=embed, view=MusicControls(guild_id))
        except Exception as e:
            logging.error(f"Erro ao transmitir `{stream_title}`: {str(e)}")
            await ctx.send(f"Erro ao transmitir `{stream_title}`: {str(e)}")
            await tocar_proxima_musica(vc, guild_id, ctx)
    else:
        now_playing.pop(guild_id, None)
        await ctx.send(f"Erro ao processar o stream. Pulando para a próxima música da fila.")
        await tocar_proxima_musica(vc, guild_id, ctx)


class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='play', description='Toca YouTube, busca ou playlist pública do Spotify')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def play(
        self,
        ctx,
        url: Optional[str] = None,
        preset: Literal["padrao", "pop", "rock", "graves"] = "padrao",
        autoplay: bool = False,
    ):
        """Toca uma música ou adiciona à fila
        Uso: !play <url> [autoplay]"""
        # 1. Validar canal correto
        if not validar_canal(ctx):
            await ctx.send("O Animal, Use o canal JUKEBOX para comandos de música.")
            return

        # 2. Validar se a URL foi fornecida
        if not url:
            await ctx.send("Ei! Envie uma URL do YouTube, uma playlist pública do Spotify ou uma busca. Uso: `!play <url> [autoplay]`")
            return

        # 3. Validar se está em um canal de voz
        if not ctx.author.voice:
            await ctx.send("Quer que eu adivinhe o canal para tocar musica ?, conecte-se a um canal de voz primeiro.")
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
            if vc.channel != ctx.author.voice.channel:
                await ctx.send("Já estou tocando em outro canal de voz.")
                return

        preset_name = preset
        if autoplay:
            autoplay_enabled[guild_id] = True

        if is_spotify_playlist(url):
            try:
                async with ctx.typing():
                    spotify_playlist = await get_public_spotify_playlist(url)
            except SpotifyPlaylistError as exc:
                await ctx.send(str(exc))
                return

            if not spotify_playlist.tracks:
                await ctx.send("A playlist do Spotify nao contem musicas disponiveis.")
                return

            await db.create_user_profile(str(ctx.author.id), ctx.author.name)
            for track in spotify_playlist.tracks:
                # O audio continua vindo do YouTube. A busca e resolvida somente
                # ao tocar cada faixa, mantendo a importacao rapida em listas grandes.
                play_queue[guild_id].append((f"ytsearch1:{track.youtube_query}", preset_name))

            await ctx.send(
                f"Importando **{len(spotify_playlist.tracks)}** musicas de **{spotify_playlist.name}** "
                "do Spotify para a fila do YouTube."
            )
            if not vc.is_playing() and not vc.is_paused():
                await tocar_proxima_musica(vc, guild_id, ctx)
            return

        is_search = not is_youtube_url(url)
        if not is_search:
            cleaned_url = clean_youtube_url(url)
        else:
            cleaned_url = f"ytsearch1:{url}"

        try:
            async with ctx.typing():
                extraction_url = (
                    get_youtube_playlist_url(cleaned_url)
                    if is_youtube_url(cleaned_url)
                    else None
                ) or cleaned_url
                with yt_dlp.YoutubeDL({
                    'extract_flat': True,
                    'ignoreerrors': True,
                    'quiet': True,
                }) as ydl:
                    info = await asyncio.to_thread(
                        ydl.extract_info, extraction_url, download=False
                    )

            if not info:
                await ctx.send("Não foi possível obter informações desse link.")
                return

            if 'entries' in info and not is_search:
                title = info.get('title', 'Playlist')
                playlist_urls = []
                for entry in info.get('entries') or []:
                    if not entry:
                        continue
                    entry_url = entry.get('url') or entry.get('webpage_url')
                    if not entry_url and entry.get('id'):
                        entry_url = f"https://www.youtube.com/watch?v={entry['id']}"
                    if entry_url and is_youtube_url(entry_url):
                        playlist_urls.append(entry_url)

                if not playlist_urls:
                    await ctx.send("A playlist não contém músicas disponíveis.")
                    return
                await db.create_user_profile(str(ctx.author.id), ctx.author.name)

                for playlist_url in playlist_urls:
                    play_queue[guild_id].append((playlist_url, preset_name))

                await ctx.send(f'Adicionando **{len(playlist_urls)}** músicas da playlist **{title}** à fila.')
            else:
                if is_search:
                    entries = [entry for entry in info.get("entries", []) if entry]
                    if not entries:
                        await ctx.send("Nenhum resultado encontrado no YouTube.")
                        return
                    info = entries[0]
                title = info.get('title', 'Desconhecido')
                item_url = info.get("webpage_url") or info.get("original_url") or cleaned_url
                if item_url.startswith("ytsearch") and info.get("id"):
                    item_url = f"https://www.youtube.com/watch?v={info['id']}"
                play_queue[guild_id].append((item_url, preset_name))

                await db.create_user_profile(str(ctx.author.id), ctx.author.name)
                await db.add_to_music_history(str(ctx.author.id), {
                    "title": title,
                    "url": item_url,
                    "artist": info.get("artist") or info.get("uploader") or info.get("channel"),
                    "genre": info.get("genre"),
                })

                await ctx.send(f'Adicionado à fila: **{title}** com preset `{preset_name}`')

            if not vc.is_playing() and not vc.is_paused():
                await tocar_proxima_musica(vc, guild_id, ctx)

        except Exception as e:
            logging.error(f'Erro ao processar música: {e}')
            await ctx.send("Ocorreu um erro ao processar a música.")

    @commands.hybrid_command(name='stop', description='Para a reprodução e limpa a fila')
    async def stop(self, ctx):
        """Para a reprodução atual"""
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para controlar a reprodução.")
            return
        guild_id = ctx.guild.id
        stop_requested[guild_id] = True
        play_queue.setdefault(guild_id, deque()).clear()
        autoplay_enabled[guild_id] = False
        loop_mode[guild_id] = "desligado"
        now_playing.pop(guild_id, None)
        if ctx.guild.voice_client and (ctx.guild.voice_client.is_playing() or ctx.guild.voice_client.is_paused()):
            ctx.guild.voice_client.stop()
            await ctx.send("Reprodução parada e fila limpa.")
        else:
            await ctx.send("Nenhuma música está tocando.")

    @commands.hybrid_command(name='skip', description='Pula a música atual')
    async def skip(self, ctx):
        """Pula a música atual"""
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para controlar a reprodução.")
            return
        if ctx.guild.voice_client and (ctx.guild.voice_client.is_playing() or ctx.guild.voice_client.is_paused()):
            stop_requested[ctx.guild.id] = False
            now_playing.pop(ctx.guild.id, None)
            ctx.guild.voice_client.stop()
            await ctx.send("Música pulada!")
        else:
            await ctx.send("Nenhuma música está tocando.")

    @commands.hybrid_command(name='leave', description='Desconecta o bot e limpa a sessão musical')
    async def leave(self, ctx):
        """Faz o bot sair do canal de voz"""
        if ctx.guild.voice_client and not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para controlar a reprodução.")
            return
        if ctx.guild.voice_client:
            guild_id = ctx.guild.id
            if guild_id in play_queue:
                play_queue[guild_id].clear()
            stop_requested[guild_id] = True
            autoplay_enabled[guild_id] = False
            now_playing.pop(guild_id, None)
            await ctx.guild.voice_client.disconnect()
            await ctx.send("Desconectado do canal de voz.")
        else:
            await ctx.send("Não estou em nenhum canal de voz.")

    @commands.hybrid_command(name="pause", description="Pausa a música atual")
    async def pause(self, ctx):
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para controlar a reprodução.")
            return
        voice_client = ctx.guild.voice_client
        if voice_client.is_playing():
            voice_client.pause()
            await ctx.send("Reprodução pausada.")
        else:
            await ctx.send("Nenhuma música está tocando.")

    @commands.hybrid_command(name="resume", description="Continua uma música pausada")
    async def resume(self, ctx):
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para controlar a reprodução.")
            return
        voice_client = ctx.guild.voice_client
        if voice_client.is_paused():
            voice_client.resume()
            await ctx.send("Reprodução retomada.")
        else:
            await ctx.send("A reprodução não está pausada.")

    @commands.hybrid_command(name="volume", description="Ajusta o volume entre 0 e 200%")
    async def volume(self, ctx, percentual: int):
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para controlar a reprodução.")
            return
        if not 0 <= percentual <= 200:
            await ctx.send("Informe um volume entre 0 e 200.")
            return
        volume_level[ctx.guild.id] = percentual
        source = getattr(ctx.guild.voice_client, "source", None)
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = percentual / 100
        await ctx.send(f"Volume ajustado para **{percentual}%**.")

    @commands.hybrid_command(name="loop", description="Repete a música ou a fila")
    async def loop(
        self,
        ctx,
        modo: Literal["desligado", "musica", "fila"] = "musica",
    ):
        loop_mode[ctx.guild.id] = modo
        await ctx.send(f"Modo de repetição: **{modo}**.")

    @commands.hybrid_command(name="fila", description="Mostra a fila de reprodução")
    async def fila(self, ctx):
        guild_id = ctx.guild.id
        queue = play_queue.get(guild_id, deque())
        current = now_playing.get(guild_id)
        embed = discord.Embed(title="🎵 Fila de reprodução", color=discord.Color.blurple())
        if current:
            embed.add_field(name="Tocando", value=current[0], inline=False)
        if queue:
            lines = [f"**{index}.** {item[0]} (`{item[1]}`)" for index, item in enumerate(list(queue)[:15], 1)]
            if len(queue) > 15:
                lines.append(f"… e mais {len(queue) - 15} música(s).")
            embed.add_field(name=f"Próximas ({len(queue)})", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Próximas", value="A fila está vazia.", inline=False)
        embed.set_footer(text=f"Loop: {loop_mode.get(guild_id, 'desligado')} | Volume: {volume_level.get(guild_id, 100)}%")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="shuffle", description="Embaralha a fila")
    async def shuffle(self, ctx):
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para editar a fila.")
            return
        queue = play_queue.get(ctx.guild.id)
        if not queue or len(queue) < 2:
            await ctx.send("Não há músicas suficientes para embaralhar.")
            return
        items = list(queue)
        random.shuffle(items)
        queue.clear()
        queue.extend(items)
        await ctx.send(f"Fila com **{len(queue)}** músicas embaralhada.")

    @commands.hybrid_command(name="remove", description="Remove uma posição da fila")
    async def remove(self, ctx, posicao: int):
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para editar a fila.")
            return
        queue = play_queue.get(ctx.guild.id)
        if not queue or posicao < 1 or posicao > len(queue):
            await ctx.send("Posição inválida. Consulte `/fila`.")
            return
        items = list(queue)
        removed = items.pop(posicao - 1)
        queue.clear()
        queue.extend(items)
        await ctx.send(f"Removido da fila: {removed[0]}")

    @commands.hybrid_command(name="clear", description="Limpa as próximas músicas da fila")
    async def clear(self, ctx):
        if not _same_voice_channel(ctx):
            await ctx.send("Entre no mesmo canal de voz para editar a fila.")
            return
        queue = play_queue.setdefault(ctx.guild.id, deque())
        count = len(queue)
        queue.clear()
        await ctx.send(f"Fila limpa: **{count}** música(s) removida(s).")

    @commands.hybrid_command(name='profile', description='Mostra seu perfil musical')
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

    @commands.hybrid_command(name='recommend', description='Recomenda músicas pelo seu histórico')
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

    @commands.command(name='reproduzir_historico')
    async def reproduzir_historico(self, ctx, count: int = 5, *flags):
        """Adiciona o histórico de reprodução do perfil do usuário à fila.

        Uso: !reproduzir_historico [count=5] [append] [search]
        - count: quantas músicas do histórico serão adicionadas (padrão 5)
        - append: se presente, adiciona as músicas ao final da fila; caso contrário, são inseridas para tocar em seguida
        - search: se presente, tenta buscar músicas pelo título quando uma entrada do histórico não tiver URL
        Ex.: `!reproduzir_historico 10 append search`
        """
        # Validar canal de comandos
        if not validar_canal(ctx):
            await ctx.send("O Animal, Use o canal JUKEBOX para comandos de música.")
            return

        # Certificar que o usuário está em um canal de voz
        if not ctx.author.voice:
            await ctx.send("Conecte-se a um canal de voz primeiro para reproduzir seu histórico.")
            return

        user_profile = await db.get_user_profile(str(ctx.author.id))
        if not user_profile or not user_profile.music_history:
            await ctx.send("Nenhum histórico de reprodução encontrado no seu perfil.")
            return

        guild_id = ctx.guild.id
        if guild_id not in play_queue:
            play_queue[guild_id] = deque()

        # Conectar ao canal de voz se necessário
        if not ctx.guild.voice_client:
            try:
                vc = await ctx.author.voice.channel.connect(reconnect=True, self_deaf=True)
            except Exception as e:
                logging.error(f'Erro ao conectar ao canal de voz: {e}')
                await ctx.send("Não foi possível conectar ao canal de voz.")
                return
        else:
            vc = ctx.guild.voice_client

        # Flags de modo (aceita várias flags, ex: 'append' 'search')
        flag_set = {f.lower() for f in flags}
        append_mode = 'append' in flag_set
        fallback_search = 'search' in flag_set or 'fallback' in flag_set

        # Pega as últimas `count` músicas (ordem cronológica: do mais antigo ao mais recente)
        songs = user_profile.music_history[-count:]

        # Construir lista de URLs candidatas (respeitando ordem)
        existing_urls = set()
        for entry in play_queue[guild_id]:
            try:
                existing_urls.add(clean_youtube_url(entry[0]))
            except Exception:
                pass

        candidates = []  # list of (url, title)
        added_urls = set()

        for s in songs:
            title = getattr(s, 'title', None) or ''
            url = getattr(s, 'url', None)
            chosen_url = None

            # Use URL from history when valid
            if url:
                try:
                    cleaned = clean_youtube_url(url)
                except Exception:
                    cleaned = None
                if cleaned and is_youtube_url(cleaned):
                    chosen_url = cleaned

            # Fallback: buscar por título usando yt_dlp (opcional)
            if not chosen_url and fallback_search and title:
                try:
                    with yt_dlp.YoutubeDL(
                            {'quiet': True, 'extract_flat': 'True', 'default_search': 'ytsearch1'}) as ydl:
                        info = await asyncio.to_thread(ydl.extract_info, f"ytsearch1:{title}", download=False)
                    if info and 'entries' in info and info['entries']:
                        entry = info['entries'][0]
                        # Try common fields that may contain a usable url/id
                        maybe = entry.get('url') or entry.get('webpage_url') or entry.get('id')
                        if maybe:
                            try:
                                cleaned = clean_youtube_url(maybe)
                            except Exception:
                                cleaned = None
                            if cleaned and is_youtube_url(cleaned):
                                chosen_url = cleaned
                except Exception as e:
                    logging.warning(f"Busca por título falhou para '{title}': {e}")

            # Se ainda não encontramos uma url válida, pula
            if not chosen_url:
                continue

            # Dedupe: pula se já existe na fila ou foi selecionada previamente
            if chosen_url in existing_urls or chosen_url in added_urls:
                continue

            candidates.append((chosen_url, title))
            added_urls.add(chosen_url)

        if not candidates:
            await ctx.send("Nenhuma música válida encontrada no seu histórico para adicionar (ou já estão na fila).")
            return

        # Montar mensagem de confirmação com a lista de títulos
        lines = []
        for i, (u, t) in enumerate(candidates, start=1):
            display_title = t or u
            lines.append(f"{i}. {display_title}")
        preview = "\n".join(lines[:20])  # limitar

        await ctx.send(
            f"Vou adicionar {len(candidates)} músicas do seu histórico:\n{preview}\n\nResponda 'sim' para confirmar (30s) ou qualquer outra coisa para cancelar.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await self.bot.wait_for('message', check=check, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("Tempo esgotado. Operação cancelada.")
            return

        if reply.content.lower() not in ('sim', 's', 'yes', 'y'):
            await ctx.send("Operação cancelada pelo usuário.")
            return

        # Inserir na fila conforme modo
        added_count = 0
        if append_mode:
            for (u, t) in candidates:
                play_queue[guild_id].append((u, 'padrao'))
                added_count += 1
        else:
            # inserir para tocar em seguida: percorre em ordem cronológica e appendleft
            # candidates are in chronological order because songs were iterated that way
            for (u, t) in candidates:
                play_queue[guild_id].appendleft((u, 'padrao'))
                added_count += 1

        await ctx.send(f'✅ Adicionados {added_count} músicas do seu histórico à fila.' + (
            " (no final)" if append_mode else " (serão reproduzidas em seguida)"))

        # Se não está tocando nada, inicia a reprodução
        if not vc.is_playing() and not vc.is_paused():
            await tocar_proxima_musica(vc, guild_id, ctx)
