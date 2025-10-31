import discord
import yt_dlp
import os
import asyncio
import logging
from datetime import datetime
from discord.ext import commands
from collections import deque
from dotenv import load_dotenv
import re
import urllib.parse
import shutil

# --- CONFIGURAÇÃO DE LOGGING ---
log_filename = datetime.now().strftime('bot_log_%Y-%m-%d.log')
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- CARREGAR TOKEN DE FORMA SEGURA ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
REBOOT_CHANNEL_ID = os.getenv('REBOOT_CHANNEL_ID')

if not TOKEN:
    logging.error("Token do bot não encontrado no arquivo .env")
    raise ValueError("Token do bot não encontrado no arquivo .env")
if not REBOOT_CHANNEL_ID:
    logging.error("ID do canal de reboot não encontrado no arquivo .env")
    raise ValueError("ID do canal de reboot não encontrado no arquivo .env")

# --- CONFIGURAÇÃO DAS INTENTS E BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents, heartbeat_timeout=60.0, help_command=None)

# --- PRESETS DE EQUALIZAÇÃO ---
EQUALIZER_PRESETS = {
    "padrao": '-filter_complex "equalizer=f=5000:g=2:w=1,equalizer=f=8000:g=2:w=1"',
    "pop": '-filter_complex "equalizer=f=80:g=4:w=1:t=h,equalizer=f=8000:g=4:w=1:t=h"',
    "rock": '-filter_complex "equalizer=f=120:g=-2:w=1:t=h,equalizer=f=2000:g=3:w=1:t=h,equalizer=f=5000:g=4:w=1:t=h"',
    "graves": '-filter_complex "equalizer=f=80:g=4:w=1:t=h,equalizer=f=200:g=2:w=1:t=h"',
}

# --- FILA DE REPRODUÇÃO E FUNÇÕES AUXILIARES ---
play_queue = {}
last_played_info = {}
autoplay_enabled = {}

def clean_youtube_url(url):
    """
    Remove parâmetros desnecessários da URL do YouTube.
    NOVO: Se 'v' (vídeo) está presente, remove o 'list' para evitar falha de rádio/autoplay.
    """
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    
    essential_params = {}
    
    # Se há um ID de vídeo E um ID de playlist, prioriza o vídeo para evitar falhas de "rádio"
    if 'v' in query_params and 'list' in query_params:
        essential_params['v'] = query_params['v']
    elif 'list' in query_params:
        essential_params['list'] = query_params['list']
    elif 'v' in query_params:
        essential_params['v'] = query_params['v']

    cleaned_query = urllib.parse.urlencode(essential_params, doseq=True)
    cleaned_url = urllib.parse.urlunparse(
        parsed_url._replace(query=cleaned_query, fragment='')
    )
    return cleaned_url


def is_youtube_url(url):
    """Valida se a URL fornecida é do YouTube ou YouTube Music."""
    youtube_regex = r'^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+$'
    if not re.match(youtube_regex, url):
        logging.warning(f'URL inválida: {url}. Deve ser uma URL do YouTube.')
        return False
    return True


async def stream_musica(url, preset_name="padrao"):
    """Extrai o stream de áudio direto de uma URL do YouTube."""
    loop = asyncio.get_event_loop()
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'extract_flat': 'auto' 
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            
            if not info or 'url' not in info:
                logging.error(f'Falha ao obter URL de stream para {url}. O vídeo pode não estar disponível.')
                return None, None, None

            url_audio = info['url']
            title = info.get('title', 'Desconhecido')
            equalizer_args = EQUALIZER_PRESETS.get(preset_name, '')
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': f'{equalizer_args} -loglevel warning'
            }
            
            source = discord.FFmpegPCMAudio(url_audio, **ffmpeg_options)
            logging.info("Fonte FFmpeg criada com sucesso.")
            return source, title, info
    except Exception as e:
        logging.error(f'Erro ao extrair stream da URL {url}: {e}')
        return None, None, None


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
                    logging.info("Nenhuma música recomendada encontrada. A reprodução parou.")
                    await ctx.send("Nenhuma música recomendada encontrada. A reprodução parou.")
                    await vc.disconnect()
                    return
            else:
                logging.info("Nenhuma música recomendada encontrada. A reprodução parou.")
                await ctx.send("A fila de músicas está vazia e não há recomendações. A reprodução parou.")
                await vc.disconnect()
                return
        else:
            logging.info("Fila vazia. Auto-play desativado. Desconectando do canal de voz.")
            await ctx.send("A fila de músicas está vazia. Desconectando do canal de voz.")
            await vc.disconnect()
            return

    url, preset_name = play_queue[guild_id].popleft()
    source, stream_title, info = await stream_musica(url, preset_name)
    
    if source:
        last_played_info[guild_id] = info
        try:
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
                tocar_proxima_musica(vc, guild_id, ctx), bot.loop))
            await ctx.send(f'Transmitindo agora: **{stream_title}** com preset `{preset_name}`')
        except Exception as e:
            logging.error(f"Erro ao transmitir `{stream_title}`: {str(e)}")
            await ctx.send(f"Erro ao transmitir `{stream_title}`: {str(e)}")
            await tocar_proxima_musica(vc, guild_id, ctx)
    else:
        logging.error(f"Erro ao processar o stream de `{url}`. Pulando para a próxima música.")
        await ctx.send(f"Erro ao processar o stream de `{url}`. Pulando para a próxima música da fila.")
        await tocar_proxima_musica(vc, guild_id, ctx)


# --- FUNÇÃO DE VALIDAÇÃO DE CANAL DE TEXTO ---
def validar_canal(ctx):
    """Valida se o comando foi enviado no canal de texto permitido."""
    ALLOWED_CHANNEL_ID = int(os.getenv('CHAT_JUKEBOX', 0))
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        return False
    return True


# --- EVENTOS DO BOT ---
@bot.event
async def on_ready():
    logging.info(f'Logado como {bot.user.name} ({bot.user.id})')
    
    if os.path.exists('reboot.flag'):
        logging.info("Arquivo de sinal de reboot encontrado. Enviando mensagem de confirmação.")
        try:
            channel_id = int(REBOOT_CHANNEL_ID)
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send("Reinicialização concluída com sucesso. Estou de volta online!")
                os.remove('reboot.flag')
            else:
                logging.error(f'ID de canal {REBOOT_CHANNEL_ID} não encontrado para enviar mensagem de reboot.')
        except ValueError:
            logging.error(f'ID do canal de reboot no .env não é um número válido: "{REBOOT_CHANNEL_ID}"')


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel and not after.channel:
        guild_id = before.channel.guild.id
        if guild_id in play_queue:
            play_queue.pop(guild_id)
            logging.info(f'Bot desconectado do canal de voz, a fila do servidor {guild_id} foi limpa.')
        if guild_id in last_played_info:
            last_played_info.pop(guild_id)
        if guild_id in autoplay_enabled:
            autoplay_enabled.pop(guild_id)

# --- COMANDOS DO BOT ---
@bot.command(name='reboot')
@commands.is_owner()
async def reboot_command(ctx):
    """Reinicia o bot e reinstala as dependências."""
    logging.info(f'Comando "!reboot" recebido. Criando arquivo de sinal...')
    try:
        with open('reboot.flag', 'w') as f:
            f.write('reboot')
        await ctx.send("Bot recebendo sinal de reinicialização. Por favor, aguarde...")
        await bot.close()
    except Exception as e:
        logging.error(f'Erro ao criar o arquivo de sinal ou encerrar o bot: {e}')


@bot.command(name='play')
async def play(ctx, arg: str, *args):
    if not validar_canal(ctx):
        await ctx.send("O Animal, use o canal correto para o comando `!play`.")
        return

    if not ctx.author.voice:
        logging.warning(f'Comando "!play" de {ctx.author.name} ignorado, usuário não está em um canal de voz.')
        await ctx.send("Você precisa estar em um canal de voz para tocar música.")
        return

    guild_id = ctx.guild.id
    if guild_id not in play_queue:
        play_queue[guild_id] = deque()

    if not ctx.guild.voice_client:
        try:
            vc = await ctx.author.voice.channel.connect(reconnect=True, self_deaf=True)
            logging.info(f'Conectado ao canal de voz: {ctx.author.voice.channel.name} com áudio de entrada desativado.')
        except discord.errors.ClientException as e:
            logging.error(f'Erro de conexão ao canal de voz: {e}')
            await ctx.send("Já estou conectado a um canal de voz neste servidor.")
            return
        except asyncio.TimeoutError:
            logging.error('Tempo limite de conexão esgotado.')
            await ctx.send("Não foi possível conectar ao canal de voz. Por favor, tente novamente mais tarde.")
            return
        except Exception as e:
            logging.error(f'Erro inesperado ao conectar: {e}')
            await ctx.send("Ocorreu um erro ao conectar. Tente novamente.")
            return
    else:
        vc = ctx.guild.voice_client

    preset_name = "padrao"
    if 'autoplay' in args:
        autoplay_enabled[guild_id] = True
        args = [a for a in args if a != 'autoplay']
    else:
        autoplay_enabled[guild_id] = False

    for arg_item in args:
        if arg_item in EQUALIZER_PRESETS:
            preset_name = arg_item
            break

    cleaned_url = clean_youtube_url(arg)

    if not is_youtube_url(cleaned_url):
        await ctx.send(
            "A URL fornecida não é do YouTube. Use uma URL válida do YouTube (ex.: youtube.com ou youtu.be).")
        return

    logging.info(f'Comando "!play {arg}" recebido. Adicionando URL limpa à fila para stream: {cleaned_url}')
    try:
        ydl_opts_info = {'extract_flat': 'True', 'quiet': True}

        async with ctx.typing():
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, cleaned_url, download=False)
        
        if 'entries' in info:
            title = info.get('title', 'Playlist')
            
            playlist_urls = [entry['url'] for entry in info['entries']]
            for playlist_url in playlist_urls:
                play_queue[guild_id].append((playlist_url, preset_name))

            await ctx.send(f'Adicionando **{len(playlist_urls)}** músicas da playlist **{title}** à fila.')
        
        else:
            title = info.get('title', 'Desconhecido')
            play_queue[guild_id].append((cleaned_url, preset_name))
            await ctx.send(f'Adicionado à fila para stream: **{title}** com preset `{preset_name}`')
        
        if not vc.is_playing() and not vc.is_paused():
            await tocar_proxima_musica(vc, guild_id, ctx)

    except yt_dlp.utils.DownloadError as e:
        logging.error(f'Erro de download/URL: {e}')
        await ctx.send(f"Opa, não consegui processar a URL. Verifique se o link está correto e se o vídeo está disponível.")
        return
    except Exception as e:
        logging.error(f'Erro inesperado ao extrair informações da URL {cleaned_url}: {e}')
        await ctx.send(f"Ocorreu um erro inesperado: {str(e)}")
        return


@bot.command(name='stop')
async def stop_playback(ctx):
    logging.info(f'Comando "!stop" recebido de {ctx.author.name}.')
    if ctx.guild.voice_client:
        if ctx.guild.voice_client.is_playing() or ctx.guild.voice_client.is_paused():
            ctx.guild.voice_client.stop()
            await ctx.send("Reprodução parada.")
            logging.info('Reprodução interrompida.')
        else:
            await ctx.send("Nenhuma música está tocando no momento.")
    else:
        await ctx.send("Não estou em nenhum canal de voz.")


@bot.command(name='leave')
async def leave(ctx):
    logging.info(f'Comando "!leave" recebido de {ctx.author.name}.')
    if ctx.guild.voice_client:
        guild_id = ctx.guild.id
        if guild_id in play_queue:
            play_queue[guild_id].clear()
            logging.info(f'Fila do servidor {guild_id} limpa.')
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Desconectado do canal de voz.")
    else:
        logging.warning('Comando "!leave" executado, mas o bot não está em um canal de voz.')
        await ctx.send("Não estou em nenhum canal de voz.")


@bot.command(name='skip')
async def skip(ctx):
    logging.info(f'Comando "!skip" recebido de {ctx.author.name}.')
    if ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
        ctx.guild.voice_client.stop()
        await ctx.send("Música pulada!")
        logging.info('Música atual pulada.')
    else:
        logging.warning('Comando "!skip" executado, mas nenhuma música está tocando.')
        await ctx.send("Nenhuma música está tocando no momento.")


@bot.command(name='check_bitrate')
async def check_bitrate(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        bitrate = ctx.author.voice.channel.bitrate / 1000
        await ctx.send(f"O bitrate do canal de voz `{ctx.author.voice.channel.name}` é {bitrate} kbps.")
        if bitrate < 128:
            await ctx.send(
                "Para melhor qualidade de áudio, considere usar um servidor com boost nível 2 ou 3 (bitrate de 256 kbps ou 384 kbps).")
    else:
        await ctx.send("Você precisa estar em um canal de voz para verificar o bitrate.")


@bot.command(name='help')
async def help_command(ctx):
    """Lista todos os comandos disponíveis e suas funções."""
    help_text = "**Lista de Comandos:**\n"
    help_text += "`!reboot` - Reinicia o bot e reinstala as dependências.\n"
    help_text += "`!play <url>` - Toca uma música ou adiciona à fila.\n"
    help_text += "`!stop` - Para a reprodução atual.\n"
    help_text += "`!leave` - Faz o bot sair do canal de voz.\n"
    help_text += "`!skip` - Pula a música atual.\n"
    help_text += "`!check_bitrate` - Mostra o bitrate do canal de voz atual.\n"

    await ctx.send(help_text)

bot.run(TOKEN)