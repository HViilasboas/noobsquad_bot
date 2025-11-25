import logging
import discord
from discord.ext import commands
from datetime import datetime, UTC
from db.database import db


class RankingCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Dicionário para rastrear sessões ativas: {(user_id, activity_name): start_time}
        self.active_sessions = {}

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
        now = datetime.now(UTC)

        # Processar atividades iniciadas
        for activity_name in started_activities:
            self.active_sessions[(user_id, activity_name)] = now
            logging.info(f"Usuário {after.name} começou a jogar {activity_name}")

        # Processar atividades paradas
        for activity_name in stopped_activities:
            start_time = self.active_sessions.pop((user_id, activity_name), None)
            if start_time:
                duration = (now - start_time).total_seconds()
                # Ignorar sessões muito curtas (< 1 minuto)
                if duration > 60:
                    await db.update_user_activity(user_id, activity_name, duration)
                    logging.info(
                        f"Usuário {after.name} jogou {activity_name} por {duration:.2f}s"
                    )

    @commands.command(name="rank")
    async def rank(self, ctx, category: str = None, *, target: str = None):
        """Comandos de ranking de atividades
        Uso:
        !rank atividades [usuario] - Mostra os jogos mais jogados por um usuário
        !rank global <jogo> - Mostra o ranking global de um jogo
        """
        if not category:
            await ctx.send(
                "❌ Uso correto: `!rank atividades [usuario]` ou `!rank global <jogo>`"
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
        else:
            await ctx.send("❌ Categoria inválida! Use `atividades` ou `global`.")

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
            hours = activity.total_seconds / 3600
            description += f"**{i}. {activity.activity_name}**\n⏱️ {hours:.1f} horas\n\n"

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
            user = ctx.guild.get_member(int(activity.user_id))
            user_name = user.display_name if user else f"User {activity.user_id}"

            hours = activity.total_seconds / 3600
            description += f"**{i}. {user_name}**\n⏱️ {hours:.1f} horas\n\n"

        embed.description = description
        await ctx.send(embed=embed)
