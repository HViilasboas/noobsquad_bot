import logging
import discord
from discord.ext import commands
from datetime import datetime, UTC
from db.database import db


class RankingCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Monitora mudanças de presença para rastrear tempo de jogo"""
        if before.bot or after.bot:
            return

        # Identificar atividades que começaram e terminaram
        before_activities = {
            a.name for a in before.activities if a.type == discord.ActivityType.playing
        }
        after_activities = {
            a.name for a in after.activities if a.type == discord.ActivityType.playing
        }

        started_activities = after_activities - before_activities
        stopped_activities = before_activities - after_activities

        user_id = str(after.id)
        username = after.display_name

        # Processar atividades iniciadas
        for activity_name in started_activities:
            await db.start_activity_session(user_id, username, activity_name)
            logging.info(f"Usuário {username} começou a jogar {activity_name}")

        # Processar atividades paradas
        for activity_name in stopped_activities:
            await db.end_activity_session(user_id, activity_name)
            logging.info(f"Usuário {username} parou de jogar {activity_name}")

    @commands.command(name="rank")
    async def rank(self, ctx, category: str = None, *, target: str = None):
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

        if category == "atividades":
            await self._show_user_activities(ctx, target)
        elif category == "global":
            if not target:
                await ctx.send(
                    "❌ Você precisa especificar o nome do jogo! Ex: `!rank global League of Legends`"
                )
                return
            await self._show_global_rank(ctx, target)
        elif category == "top_atividades":
            await self._show_top_activities_global(ctx)
        elif category == "top_membros":
            await self._show_top_members(ctx)
        else:
            await ctx.send(
                "❌ Categoria inválida! Use `atividades`, `global`, `top_atividades` ou `top_membros`."
            )

    async def _show_user_activities(self, ctx, target_user: str = None):
        """Mostra as atividades mais frequentes de um usuário"""
        user_id = str(ctx.author.id)
        user_name = ctx.author.display_name

        # Se um usuário foi mencionado ou especificado
        if ctx.message.mentions:
            user = ctx.message.mentions[0]
            user_id = str(user.id)
            user_name = user.display_name
        elif target_user:
            # Tentar achar pelo nome (simplificado)
            # Idealmente usaria converter, mas mentions é mais seguro
            pass

        activities = await db.get_user_top_activities(user_id)

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
                f"**{i}. {activity['activity_name']}**\\n⏱️ {hours:.1f} horas\\n\\n"
            )

        embed.description = description
        await ctx.send(embed=embed)

    async def _show_global_rank(self, ctx, game_name: str):
        """Mostra o ranking global para um jogo específico"""
        activities = await db.get_global_activity_rank(game_name)

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
            description += f"**{i}. {user_name}**\\n⏱️ {hours:.1f} horas\\n\\n"

        embed.description = description
        await ctx.send(embed=embed)

    async def _show_top_activities_global(self, ctx):
        """Mostra as atividades mais realizadas globalmente"""
        activities = await db.get_top_activities_global()

        if not activities:
            await ctx.send("📉 Nenhuma atividade registrada ainda no servidor.")
            return

        embed = discord.Embed(
            title="🏆 Top Atividades Mais Realizadas",
            description="Ranking global das atividades por tempo total",
            color=0xE74C3C,
        )

        description = ""
        trophy_emojis = ["🥇", "🥈", "🥉"]

        for i, activity in enumerate(activities, 1):
            hours = activity["total_seconds"] / 3600
            emoji = trophy_emojis[i - 1] if i <= 3 else f"**{i}.**"

            description += (
                f"{emoji} **{activity['activity_name']}**\\n"
                f"⏱️ {hours:.1f} horas | "
                f"👥 {activity['player_count']} jogador{'es' if activity['player_count'] > 1 else ''} | "
                f"🎮 {activity['session_count']} sessõ{'es' if activity['session_count'] > 1 else ''}\\n\\n"
            )

        embed.description = description
        embed.set_footer(text="Ranking baseado no tempo total de todas as sessões")
        await ctx.send(embed=embed)

    async def _show_top_members(self, ctx):
        """Mostra os membros com mais horas em atividades"""
        members = await db.get_top_members_by_activity_time()

        if not members:
            await ctx.send("📉 Nenhum membro com atividades registradas ainda.")
            return

        embed = discord.Embed(
            title="👑 Top Membros Mais Ativos",
            description="Ranking de membros por tempo total em atividades",
            color=0x9B59B6,
        )

        description = ""
        medal_emojis = ["🥇", "🥈", "🥉"]

        for i, member in enumerate(members, 1):
            # Tentar pegar o nome do usuário do cache do bot ou do banco
            user = ctx.guild.get_member(int(member["user_id"]))
            user_name = user.display_name if user else f"User {member['user_id']}"

            hours = member["total_seconds"] / 3600
            emoji = medal_emojis[i - 1] if i <= 3 else f"**{i}.**"

            description += f"{emoji} **{user_name}**\\n⏱️ {hours:.1f} horas totais\\n"

            # Mostra as top 3 atividades do membro
            if member["top_activities"]:
                description += "🎮 Top atividades:\\n"
                for j, act in enumerate(member["top_activities"][:3], 1):
                    act_hours = act["seconds"] / 3600
                    description += f"   {j}. {act['name']} ({act_hours:.1f}h)\\n"

            description += "\\n"

        embed.description = description
        embed.set_footer(text="Ranking baseado no tempo total de atividades")
        await ctx.send(embed=embed)
