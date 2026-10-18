"""Comandos Discord para lançamentos e alertas Steam."""

from typing import Optional

import discord
from discord.ext import commands

from db.database import db
from .steam import SteamReleaseService


class SteamCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = SteamReleaseService()

    async def _ensure_catalog(self) -> bool:
        if await db.get_steam_releases(limit=1):
            return True
        return bool(await self.service.refresh_releases())

    @commands.hybrid_command(
        name="steam_lancamentos",
        description="Recomenda próximos lançamentos Steam para a comunidade",
    )
    async def releases(self, ctx, limite: int = 5):
        limite = max(1, min(limite, 10))
        async with ctx.typing():
            if not await self._ensure_catalog():
                await ctx.send("Não consegui consultar os lançamentos da Steam agora. Tente novamente em alguns minutos.")
                return
            recommendations = await self.service.recommendations_for_guild(ctx.guild.id, limite)

        if not recommendations:
            await ctx.send(
                "Ainda não há dados suficientes para recomendações. O bot precisa de "
                "atividades de jogo registradas e de lançamentos com gêneros compatíveis."
            )
            return

        embed = discord.Embed(
            title="🎮 Lançamentos Steam para a comunidade",
            description="Baseado nos jogos registrados nos últimos 90 dias.",
            color=0x1B2838,
        )
        for item in recommendations:
            tags = ", ".join((item.get("tags") or [])[:4]) or "sem tags"
            value = (
                f"**Afinidade: {item['score']}%** · {item.get('release_date_text', 'Em breve')}\n"
                f"{self.service.reason_text(item)}\n"
                f"[{tags}]({item['store_url']})"
            )
            embed.add_field(name=item["name"][:256], value=value[:1024], inline=False)
        image = recommendations[0].get("header_image")
        if image:
            embed.set_thumbnail(url=image)
        embed.set_footer(text="Datas da Steam podem ser alteradas pelos publicadores.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="steam_configurar",
        description="Configura os avisos automáticos de lançamentos Steam",
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def configure(
        self,
        ctx,
        canal: Optional[discord.TextChannel] = None,
        ativo: bool = True,
        mencionar: bool = False,
        afinidade_minima: int = 10,
    ):
        if not 0 <= afinidade_minima <= 100:
            await ctx.send("A afinidade mínima deve ficar entre 0 e 100.")
            return
        target = canal or ctx.channel
        success = await db.set_steam_notification_settings(
            str(ctx.guild.id),
            {
                "enabled": ativo,
                "channel_id": target.id,
                "mention_role_id": None,
                "mention_everyone": mencionar,
                "minimum_score": afinidade_minima,
            },
        )
        if success:
            status = "ativados" if ativo else "desativados"
            await ctx.send(
                f"Avisos Steam {status} em {target.mention}; afinidade mínima: **{afinidade_minima}%**."
            )
        else:
            await ctx.send("Não foi possível salvar a configuração Steam.")

    @commands.hybrid_command(
        name="steam_atualizar",
        description="Atualiza agora o cache de lançamentos Steam",
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def refresh(self, ctx):
        async with ctx.typing():
            count = await self.service.refresh_releases()
        if count:
            await ctx.send(f"Cache Steam atualizado: **{count}** lançamentos disponíveis.")
        else:
            await ctx.send("A Steam não retornou lançamentos utilizáveis agora. Tente novamente mais tarde.")

    @configure.error
    @refresh.error
    async def steam_permission_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Você precisa da permissão **Gerenciar Servidor** para configurar avisos Steam.")
            return
        raise error
