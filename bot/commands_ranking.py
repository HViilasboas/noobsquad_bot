import logging
import discord
from discord.ext import commands
from datetime import datetime, UTC
from typing import Literal, Optional
from db.database import db


class RankingCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="rank", description="Exibe rankings de atividades do servidor")
    async def rank(
        self,
        ctx,
        category: Optional[Literal["atividades", "global", "top_atividades", "top_membros"]] = None,
        target: Optional[str] = None,
        dias: Optional[int] = None,
    ):
        """Comandos de ranking de atividades
        Uso:
        !rank atividades [usuario] - Mostra os jogos mais jogados por um usuário
        !rank global <jogo> - Mostra o ranking global de um jogo
        !rank top_atividades - Mostra as atividades mais realizadas globalmente
        !rank top_membros - Mostra os membros com mais horas em atividades
        """
        if not category:
            await ctx.send(
                "❌ Uso correto:\n"
                "`!rank atividades [usuario]` - Top atividades de um usuário\n"
                "`!rank global <jogo>` - Ranking global de um jogo\n"
                "`!rank top_atividades` - Atividades mais realizadas\n"
                "`!rank top_membros` - Membros com mais horas"
            )
            return

        category = category.lower()
        if dias is not None and dias not in (7, 30, 90):
            await ctx.send("O período deve ser 7, 30 ou 90 dias; omita para usar todo o histórico.")
            return

        if category == "atividades":
            await self._show_user_activities(ctx, target, dias)
        elif category == "global":
            if not target:
                await ctx.send(
                    "❌ Você precisa especificar o nome do jogo! Ex: `!rank global League of Legends`"
                )
                return
            await self._show_global_rank(ctx, target, dias)
        elif category == "top_atividades":
            await self._show_top_activities_global(ctx, dias)
        elif category == "top_membros":
            await self._show_top_members(ctx, dias)
        else:
            await ctx.send(
                "❌ Categoria inválida! Use `atividades`, `global`, `top_atividades` ou `top_membros`."
            )

    async def _show_user_activities(self, ctx, target_user: str = None, days: int = None):
        """Mostra as atividades mais frequentes de um usuário"""
        user_id = str(ctx.author.id)
        user_name = ctx.author.display_name

        # Se um usuário foi mencionado ou especificado
        message = getattr(ctx, "message", None)
        mentions = getattr(message, "mentions", [])
        if mentions:
            user = mentions[0]
            user_id = str(user.id)
            user_name = user.display_name
        elif target_user:
            raw_target = target_user.strip().removeprefix("<@").removesuffix(">").lstrip("!")
            user = ctx.guild.get_member(int(raw_target)) if raw_target.isdigit() else None
            if user is None:
                lowered = target_user.casefold()
                user = discord.utils.find(
                    lambda member: member.name.casefold() == lowered
                    or member.display_name.casefold() == lowered,
                    ctx.guild.members,
                )
            if user:
                user_id = str(user.id)
                user_name = user.display_name
            else:
                await ctx.send("Usuário não encontrado neste servidor.")
                return

        activities = await db.get_user_top_activities(user_id, days=days)

        if not activities:
            await ctx.send(
                f"📉 Nenhuma atividade registrada para **{user_name}** ainda."
            )
            return

        embed = discord.Embed(title=f"🎮 Top Atividades de {user_name}", color=0x3498DB)

        description = ""
        for i, activity in enumerate(activities, 1):
            hours = activity["total_seconds"] / 3600
            description += (
                f"**{i}. {activity['activity_name']}**\n⏱️ {hours:.1f} horas\n\n"
            )

        embed.description = description
        await ctx.send(embed=embed)

    async def _show_global_rank(self, ctx, game_name: str, days: int = None):
        """Mostra o ranking global para um jogo específico"""
        activities = await db.get_global_activity_rank(game_name, days=days)

        if not activities:
            await ctx.send(
                f"📉 Ninguém jogou **{game_name}** ainda (ou o nome está incorreto)."
            )
            return

        embed = discord.Embed(title=f"🏆 Ranking Global - {game_name}", color=0xF1C40F)

        description = ""
        for i, activity in enumerate(activities, 1):
            # Tentar pegar o nome do usuário do cache do bot ou do banco
            user = ctx.guild.get_member(int(activity["user_id"]))
            user_name = user.display_name if user else f"User {activity['user_id']}"

            hours = activity["total_seconds"] / 3600
            description += f"**{i}. {user_name}**\n⏱️ {hours:.1f} horas\n\n"

        embed.description = description
        await ctx.send(embed=embed)

    async def _show_top_activities_global(self, ctx, days: int = None):
        """Mostra as atividades mais realizadas globalmente"""
        activities = await db.get_top_activities_global(days=days)

        if not activities:
            await ctx.send("📉 Nenhuma atividade registrada ainda no servidor.")
            return

        embed = discord.Embed(title="🏆 Top Atividades Mais Realizadas", color=0xE74C3C)

        description = ""
        trophy_emojis = ["🥇", "🥈", "🥉"]

        for i, activity in enumerate(activities, 1):
            hours = activity["total_seconds"] / 3600
            emoji = trophy_emojis[i - 1] if i <= 3 else f"**{i}.**"

            description += (
                f"{emoji} **{activity['activity_name']}**\n"
                f"⏱️ {hours:.1f} horas | "
                f"👥 {activity['player_count']} jogador{'es' if activity['player_count'] > 1 else ''} | "
                f"🎮 {activity['session_count']} sessõ{'es' if activity['session_count'] > 1 else ''}\n\n"
            )

        embed.description = description
        embed.set_footer(text="Ranking baseado no tempo total de todas as sessões")
        await ctx.send(embed=embed)

    async def _show_top_members(self, ctx, days: int = None):
        """Mostra os membros com mais horas em atividades"""
        members = await db.get_top_members_by_activity_time(days=days)

        if not members:
            await ctx.send("📉 Nenhum membro com atividades registradas ainda.")
            return

        embed = discord.Embed(title="👑 Top Membros Mais Ativos", color=0x9B59B6)

        description = ""
        medal_emojis = ["🥇", "🥈", "🥉"]

        for i, member in enumerate(members, 1):
            # Tentar pegar o nome do usuário do cache do bot ou do banco
            user = ctx.guild.get_member(int(member["user_id"]))
            user_name = user.display_name if user else f"User {member['user_id']}"

            hours = member["total_seconds"] / 3600
            emoji = medal_emojis[i - 1] if i <= 3 else f"**{i}.**"

            description += f"{emoji} **{user_name}**\n⏱️ {hours:.1f} horas totais\n"

            # Mostra as top 3 atividades do membro
            if member["top_activities"]:
                description += "🎮 Top atividades:\n"
                for j, act in enumerate(member["top_activities"][:3], 1):
                    act_hours = act["seconds"] / 3600
                    description += f"   {j}. {act['name']} ({act_hours:.1f}h)\n"

            description += "\n"

        embed.description = description
        embed.set_footer(text="Ranking baseado no tempo total de atividades")
        await ctx.send(embed=embed)
