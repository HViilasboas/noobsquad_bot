"""Atualização periódica e distribuição de alertas de lançamentos Steam."""

import logging

import discord
from discord.ext import tasks

from config.settings import STEAM_CHECK_INTERVAL
from db.database import db
from .steam import SteamReleaseService


class SteamScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.service = SteamReleaseService()

    async def start(self):
        if not self.check_releases.is_running():
            self.check_releases.start()

    def stop(self):
        if self.check_releases.is_running():
            self.check_releases.cancel()

    @tasks.loop(seconds=STEAM_CHECK_INTERVAL)
    async def check_releases(self):
        if not self.bot.is_ready():
            return
        updated = await self.service.refresh_releases()
        if not updated:
            return
        for settings in await db.get_active_steam_notification_settings():
            try:
                guild_id = int(settings["guild_id"])
                recommendations = await self.service.recommendations_for_guild(guild_id, limit=5)
                minimum = int(settings.get("minimum_score", 15))
                for item in recommendations:
                    if item["score"] < minimum:
                        continue
                    if await db.was_steam_release_notified(guild_id, item["appid"]):
                        continue
                    channel = self.bot.get_channel(int(settings["channel_id"]))
                    if channel is None:
                        try:
                            channel = await self.bot.fetch_channel(int(settings["channel_id"]))
                        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                            logging.warning("Canal Steam indisponível para servidor %s", guild_id)
                            break
                    embed = discord.Embed(
                        title=f"🎮 Possível interesse: {item['name']}",
                        description=(
                            f"**Afinidade: {item['score']}%** · {item.get('release_date_text', 'Em breve')}\n"
                            f"{self.service.reason_text(item)}"
                        ),
                        url=item["store_url"],
                        color=0x1B2838,
                    )
                    if item.get("header_image"):
                        embed.set_thumbnail(url=item["header_image"])
                    content = "@everyone" if settings.get("mention_everyone") else None
                    await channel.send(
                        content=content,
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(everyone=bool(content)),
                    )
                    await db.mark_steam_release_notified(guild_id, item["appid"])
            except Exception as error:
                logging.exception("Erro ao enviar avisos Steam: %s", error)

    @check_releases.before_loop
    async def before_check_releases(self):
        await self.bot.wait_until_ready()

