import re
import urllib.parse
import logging
import discord
import asyncio
import yt_dlp
from config.settings import EQUALIZER_PRESETS

def clean_youtube_url(url: str) -> str:
    """Remove parâmetros desnecessários da URL do YouTube."""
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    essential_params = {}
    if 'v' in query_params and 'list' in query_params:
        essential_params['v'] = query_params['v']
    elif 'list' in query_params:
        essential_params['list'] = query_params['list']
    elif 'v' in query_params:
        essential_params['v'] = query_params['v']

    cleaned_query = urllib.parse.urlencode(essential_params, doseq=True)
    return urllib.parse.urlunparse(
        parsed_url._replace(query=cleaned_query, fragment='')
    )

def is_youtube_url(url: str) -> bool:
    """Valida se a URL fornecida é do YouTube ou YouTube Music."""
    youtube_regex = r'^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+$'
    if not re.match(youtube_regex, url):
        logging.warning(f'URL inválida: {url}. Deve ser uma URL do YouTube.')
        return False
    return True

async def stream_musica(url: str, preset_name: str = "padrao"):
    """Extrai o stream de áudio direto de uma URL do YouTube."""
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
                logging.error(f'Falha ao obter URL de stream para {url}.')
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
