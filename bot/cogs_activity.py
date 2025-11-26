import discord
from discord.ext import commands, tasks
import logging
from db.database import db


class ActivityTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sync_members_task.start()

    def cog_unload(self):
        self.sync_members_task.cancel()

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Monitora mudanças de presença para rastrear atividades"""
        if after.bot:
            return

        # Identifica atividades que iniciaram
        # Atividades no 'after' que não estavam no 'before' ou que mudaram

        # Simplificação: Vamos olhar para after.activities e before.activities
        # Se uma atividade está em after e não em before -> Iniciou
        # Se uma atividade está em before e não em after -> Terminou

        # Mapeia atividades por nome para facilitar comparação
        # Nota: Discord pode ter múltiplas atividades com mesmo nome? Raro, mas possível.
        # Vamos usar o nome como chave.

        before_activities = {
            act.name: act
            for act in before.activities
            if act.type == discord.ActivityType.playing
        }
        after_activities = {
            act.name: act
            for act in after.activities
            if act.type == discord.ActivityType.playing
        }

        # Detecta inícios
        for name, activity in after_activities.items():
            if name not in before_activities:
                logging.info(f"Atividade iniciada: {name} por {after.name}")
                await db.start_activity_session(str(after.id), after.name, name)

        # Detecta términos
        for name, activity in before_activities.items():
            if name not in after_activities:
                logging.info(f"Atividade finalizada: {name} por {after.name}")
                await db.end_activity_session(str(after.id), name)

    @tasks.loop(hours=24)
    async def sync_members_task(self):
        """Sincroniza periodicamente os membros do servidor com o banco de dados"""
        if not self.bot.is_ready():
            return

        logging.info("Iniciando sincronização de membros...")
        try:
            for guild in self.bot.guilds:
                members_data = []
                for member in guild.members:
                    if not member.bot:
                        members_data.append({"id": str(member.id), "name": member.name})

                if members_data:
                    await db.sync_member_profiles(members_data)
        except Exception as e:
            logging.error(f"Erro na task de sincronização de membros: {str(e)}")

    @sync_members_task.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ActivityTracker(bot))
