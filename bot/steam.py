"""Integração pública e cacheada para recomendações de lançamentos da Steam."""

import asyncio
from datetime import datetime, timedelta, UTC
from html.parser import HTMLParser
import logging
import re
from typing import Iterable, Optional

import requests

from config.settings import STEAM_RELEASE_WINDOW_DAYS, STEAM_REQUEST_TIMEOUT
from db.database import db


STORE_URL = "https://store.steampowered.com"
USER_AGENT = "NoobSquadDiscordBot/1.0 (+community game recommendations)"


class _ComingSoonParser(HTMLParser):
    """Lê apenas os campos estáveis da página de resultados da loja Steam."""

    def __init__(self):
        super().__init__()
        self.items: list[dict] = []
        self.current: Optional[dict] = None
        self.field: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        classes = set(data.get("class", "").split())
        if tag == "a" and "search_result_row" in classes:
            raw_appid = data.get("data-ds-appid", "").split(",")[0]
            if raw_appid.isdigit():
                self.current = {"appid": int(raw_appid), "name": "", "release_date_text": ""}
            return
        if not self.current:
            return
        if "title" in classes:
            self.field = "name"
        elif "search_released" in classes:
            self.field = "release_date_text"
        elif "search_tags" in classes:
            self.field = "tags"
        elif tag == "img" and data.get("src"):
            self.current["header_image"] = data["src"]

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            if self.current.get("name"):
                self.items.append(self.current)
            self.current = None
            self.field = None
        elif tag in {"span", "div"}:
            self.field = None

    def handle_data(self, data):
        if not self.current or not self.field:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self.field == "tags":
            self.current.setdefault("tags", []).extend(
                tag.strip() for tag in value.split(",") if tag.strip()
            )
        else:
            self.current[self.field] = f"{self.current.get(self.field, '')} {value}".strip()


def _parse_release_timestamp(value: str) -> Optional[datetime]:
    cleaned = re.sub(r"\s+", " ", value.replace("–", "-")).strip()
    for fmt in ("%b %d, %Y", "%d %b, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normaliza datas vindas do MongoDB, que por padrão não preserva tzinfo."""
    if value and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _request_json(url: str, params: Optional[dict] = None) -> dict:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=STEAM_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _request_coming_soon() -> list[dict]:
    payload = _request_json(
        f"{STORE_URL}/search/results/",
        {
            "query": "",
            "start": 0,
            "count": 50,
            "dynamic_data": "",
            "sort_by": "Released_DESC",
            "filter": "comingsoon",
            "infinite": 1,
            "cc": "br",
            "l": "english",
        },
    )
    parser = _ComingSoonParser()
    parser.feed(payload.get("results_html", ""))
    return parser.items


def _request_app_details(appid: int) -> Optional[dict]:
    payload = _request_json(
        f"{STORE_URL}/api/appdetails",
        {"appids": appid, "cc": "br", "l": "english"},
    )
    entry = payload.get(str(appid), {})
    if not entry.get("success"):
        return None
    return entry.get("data")


def _request_store_search(term: str) -> Optional[dict]:
    payload = _request_json(
        f"{STORE_URL}/api/storesearch/",
        {"term": term, "cc": "br", "l": "english"},
    )
    items = payload.get("items") or []
    normalized = term.casefold()
    exact = next((item for item in items if item.get("name", "").casefold() == normalized), None)
    return exact or (items[0] if items else None)


def _tags_from_details(details: dict) -> list[str]:
    tags = []
    tags.extend(genre.get("description", "") for genre in details.get("genres") or [])
    tags.extend(category.get("description", "") for category in details.get("categories") or [])
    return sorted({tag.strip() for tag in tags if tag and tag.strip()})


class SteamReleaseService:
    """Obtém lançamentos e calcula afinidade sem exigir dados privados dos membros."""

    async def refresh_releases(self) -> int:
        try:
            items = await asyncio.to_thread(_request_coming_soon)
        except (requests.RequestException, ValueError) as error:
            logging.error("Falha ao consultar lançamentos Steam: %s", error)
            return 0

        semaphore = asyncio.Semaphore(5)

        async def fetch_details(item: dict):
            try:
                async with semaphore:
                    return item, await asyncio.to_thread(_request_app_details, item["appid"])
            except (requests.RequestException, ValueError) as error:
                logging.warning("Falha ao detalhar app Steam %s: %s", item["appid"], error)
                return item, None

        detailed_items = await asyncio.gather(*(fetch_details(item) for item in items))
        saved = 0
        for item, details in detailed_items:
            if not details or details.get("type") != "game":
                continue

            release_date = details.get("release_date") or {}
            release_text = release_date.get("date") or item.get("release_date_text", "Coming soon")
            release_at = _parse_release_timestamp(release_text)
            if release_at and release_at.year > datetime.now(UTC).year + 2:
                release_at = None
            record = {
                "appid": item["appid"],
                "name": details.get("name") or item["name"],
                "store_url": f"{STORE_URL}/app/{item['appid']}/",
                "header_image": details.get("header_image") or item.get("header_image"),
                "release_date_text": release_text,
                "release_timestamp": release_at,
                "release_date_coming_soon": bool(release_date.get("coming_soon", True)),
                "is_upcoming": True,
                "tags": sorted(set((item.get("tags") or []) + _tags_from_details(details))),
                "genres": [genre.get("description") for genre in details.get("genres") or []],
                "categories": [category.get("description") for category in details.get("categories") or []],
                "developers": details.get("developers") or [],
                "publishers": details.get("publishers") or [],
                "short_description": details.get("short_description", ""),
                "is_free": bool(details.get("is_free")),
            }
            if await db.upsert_steam_release(record):
                saved += 1
        logging.info("Steam: %s lançamentos atualizados", saved)
        return saved

    async def _game_for_activity(self, name: str) -> Optional[dict]:
        cached = await db.get_steam_game_cache(name)
        cached_at = _as_utc(cached.get("updated_at")) if cached else None
        if cached and cached_at and cached_at > datetime.now(UTC) - timedelta(days=14):
            return cached
        try:
            hit = await asyncio.to_thread(_request_store_search, name)
            if not hit:
                return None
            details = await asyncio.to_thread(_request_app_details, int(hit["id"]))
        except (requests.RequestException, ValueError, KeyError) as error:
            logging.warning("Steam: não foi possível mapear atividade %r: %s", name, error)
            return None
        if not details or details.get("type") != "game":
            return None
        game = {
            "appid": int(hit["id"]),
            "name": details.get("name") or name,
            "tags": _tags_from_details(details),
            "developers": details.get("developers") or [],
            "publishers": details.get("publishers") or [],
        }
        await db.upsert_steam_game_cache(game)
        return game

    async def recommendations_for_guild(self, guild_id: int, limit: int = 5) -> list[dict]:
        del guild_id  # A atividade já é global ao servidor neste modelo atual.
        activities = await db.get_top_activities_global(limit=12, days=90)
        releases = await db.get_steam_releases(limit=60)
        deadline = datetime.now(UTC) + timedelta(days=STEAM_RELEASE_WINDOW_DAYS)
        releases = [
            release for release in releases
            if not release.get("release_timestamp")
            or _as_utc(release["release_timestamp"]) <= deadline
        ]
        if not activities or not releases:
            return []

        source_games = []
        for activity in activities:
            game = await self._game_for_activity(activity["activity_name"])
            if game and game.get("tags"):
                source_games.append((activity, game))
        if not source_games:
            return []

        total_seconds = sum(activity["total_seconds"] for activity, _ in source_games) or 1
        recommendations = []
        for release in releases:
            release_tags = {tag.casefold() for tag in release.get("tags") or []}
            if not release_tags:
                continue
            weighted_similarity = 0.0
            explanations = []
            for activity, game in source_games:
                game_tags = {tag.casefold() for tag in game.get("tags") or []}
                common = release_tags & game_tags
                if not common:
                    continue
                similarity = len(common) / len(release_tags | game_tags)
                weighted_similarity += activity["total_seconds"] * similarity
                explanations.append((activity["activity_name"], sorted(common)))
            if not weighted_similarity:
                continue
            score = round(100 * weighted_similarity / total_seconds)
            release_at = _as_utc(release.get("release_timestamp"))
            if release_at and release_at <= datetime.now(UTC) + timedelta(days=30):
                score = min(100, score + 5)
            explanations.sort(key=lambda item: len(item[1]), reverse=True)
            recommendations.append({
                **release,
                "score": score,
                "reasons": explanations[:2],
            })
        return sorted(recommendations, key=lambda item: (-item["score"], item["name"]))[:limit]

    @staticmethod
    def reason_text(recommendation: dict) -> str:
        reasons = recommendation.get("reasons") or []
        if not reasons:
            return "Tem afinidade com os jogos mais ativos da comunidade."
        details = []
        for game, tags in reasons:
            details.append(f"{game}: {', '.join(tags[:3])}")
        return "Em comum com " + " • ".join(details)
