"""Leitura de playlists públicas do Spotify para importação na fila do YouTube."""

import asyncio
import logging
import re
import time
from dataclasses import dataclass

import requests

from config.settings import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET


_SPOTIFY_PLAYLIST_RE = re.compile(
    r"^(?:https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?playlist/|spotify:playlist:)([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_URL = "https://api.spotify.com/v1"
_REQUEST_TIMEOUT = 15
_access_token: str | None = None
_token_expires_at = 0.0


class SpotifyPlaylistError(Exception):
    """Erro seguro para exibir a quem solicitou a playlist."""


@dataclass(frozen=True)
class SpotifyTrack:
    name: str
    artists: str

    @property
    def youtube_query(self) -> str:
        return f"{self.artists} - {self.name}"


@dataclass(frozen=True)
class SpotifyPlaylist:
    name: str
    tracks: list[SpotifyTrack]


def spotify_playlist_id(url: str) -> str | None:
    """Obtém o ID de um link ou URI de playlist do Spotify."""
    match = _SPOTIFY_PLAYLIST_RE.match(url.strip())
    return match.group(1) if match else None


def is_spotify_playlist(url: str) -> bool:
    return spotify_playlist_id(url) is not None


def _request_access_token() -> str:
    global _access_token, _token_expires_at

    if _access_token and time.monotonic() < _token_expires_at:
        return _access_token

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise SpotifyPlaylistError(
            "A importação do Spotify ainda não foi configurada. "
            "Peça ao administrador para definir SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET."
        )

    try:
        response = requests.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        _access_token = payload["access_token"]
        # Margem para não reutilizar um token prestes a expirar.
        _token_expires_at = time.monotonic() + max(int(payload.get("expires_in", 3600)) - 60, 1)
        return _access_token
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        logging.warning("Não foi possível autenticar na API do Spotify: %s", exc)
        raise SpotifyPlaylistError("Não foi possível autenticar na API do Spotify.") from exc


def _spotify_get(path_or_url: str) -> dict:
    url = path_or_url if path_or_url.startswith("http") else f"{_API_URL}{path_or_url}"
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {_request_access_token()}"},
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code == 404:
            raise SpotifyPlaylistError("Playlist do Spotify não encontrada ou não é pública.")
        if response.status_code in (401, 403):
            raise SpotifyPlaylistError("Não foi possível acessar esta playlist do Spotify.")
        response.raise_for_status()
        return response.json()
    except SpotifyPlaylistError:
        raise
    except (requests.RequestException, ValueError) as exc:
        logging.warning("Falha ao consultar playlist do Spotify: %s", exc)
        raise SpotifyPlaylistError("Não foi possível consultar a playlist do Spotify agora.") from exc


def _read_public_playlist(playlist_id: str) -> SpotifyPlaylist:
    playlist_data = _spotify_get(f"/playlists/{playlist_id}?fields=name")
    playlist_name = playlist_data.get("name") or "Playlist do Spotify"
    next_page: str | None = f"/playlists/{playlist_id}/items?limit=100&additional_types=track"
    tracks: list[SpotifyTrack] = []

    while next_page:
        page = _spotify_get(next_page)
        for playlist_item in page.get("items", []):
            # A API atual usa "item"; "track" mantém compatibilidade com respostas antigas.
            track = playlist_item.get("item") or playlist_item.get("track") or {}
            if track.get("type") != "track" or not track.get("name"):
                continue
            artists = ", ".join(
                artist.get("name", "") for artist in track.get("artists", []) if artist.get("name")
            )
            if artists:
                tracks.append(SpotifyTrack(name=track["name"], artists=artists))
        next_page = page.get("next")

    return SpotifyPlaylist(name=playlist_name, tracks=tracks)


async def get_public_spotify_playlist(url: str) -> SpotifyPlaylist:
    """Lê metadados de uma playlist pública sem bloquear o loop do Discord."""
    playlist_id = spotify_playlist_id(url)
    if not playlist_id:
        raise SpotifyPlaylistError("Link de playlist do Spotify inválido.")
    return await asyncio.to_thread(_read_public_playlist, playlist_id)
