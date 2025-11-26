import discord
from discord.ext import commands, tasks
import logging
from datetime import time
from db.database import db
from config.settings import SYNC_MEMBERS_HOUR, SYNC_MEMBERS_MINUTE


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

    @tasks.loop(time=time(hour=SYNC_MEMBERS_HOUR, minute=SYNC_MEMBERS_MINUTE))
    async def sync_members_task(self):
        """Sincroniza periodicamente os membros do servidor com o banco de dados"""
        if not self.bot.is_ready():
            return

        logging.info("=" * 60)
        logging.info("Iniciando sincronização de membros...")
        try:
            for guild in self.bot.guilds:
                logging.info(f"Processando servidor: '{guild.name}' (ID: {guild.id})")
                logging.info(f"Total de membros reportado pelo servidor: {guild.member_count}")

                # Verifica se guild.members está populado
                total_members_cache = len(guild.members)
                logging.info(f"Membros no cache (guild.members): {total_members_cache}")

                members_data = []
                bot_count = 0

                # Para servidores com mais de 75 membros, o cache pode estar incompleto
                # Sempre usamos fetch_members() para garantir que todos sejam carregados
                if guild.member_count > 75 or total_members_cache < guild.member_count:
                    logging.info(f"Servidor grande detectado ou cache incompleto. Buscando todos os membros via API...")
                    try:
                        # Usa async for para iterar pelos membros (SEM LIMITE)
                        member_count = 0
                        async for member in guild.fetch_members(limit=None):
                            member_count += 1
                            if member.bot:
                                bot_count += 1
                                logging.debug(f"  [BOT IGNORADO] {member.display_name} (ID: {member.id})")
                            else:
                                members_data.append({
                                    "id": str(member.id),
                                    "name": member.name,
                                    "display_name": member.display_name
                                })
                                logging.info(f"  [PROCESSANDO] Membro: {member.display_name} (@{member.name}) (ID: {member.id})")

                        logging.info(f"Total de membros buscados via API: {member_count} (esperado: {guild.member_count})")

                        if member_count < guild.member_count:
                            logging.warning(f"⚠️ ATENÇÃO: Foram buscados {member_count} membros, mas o servidor tem {guild.member_count}!")
                            logging.warning(f"⚠️ Verifique se o bot tem permissões corretas e o intent 'members' está habilitado.")
                    except discord.Forbidden:
                        logging.error(f"❌ Sem permissão para buscar membros do servidor '{guild.name}'")
                        logging.error(f"Verifique se o bot tem a permissão 'View Server Members'")
                        continue
                    except Exception as e:
                        logging.error(f"❌ Erro ao buscar membros via API: {str(e)}")
                        import traceback
                        logging.error(traceback.format_exc())
                        continue
                else:
                    # Servidor pequeno (<= 75 membros), usa o cache
                    logging.info(f"Servidor pequeno. Usando cache local...")
                    for member in guild.members:
                        if member.bot:
                            bot_count += 1
                            logging.debug(f"  [BOT IGNORADO] {member.display_name} (ID: {member.id})")
                        else:
                            members_data.append({
                                "id": str(member.id),
                                "name": member.name,
                                "display_name": member.display_name
                            })
                            logging.info(f"  [PROCESSANDO] Membro: {member.display_name} (@{member.name}) (ID: {member.id})")

                logging.info(f"Resumo: {len(members_data)} membros válidos, {bot_count} bots ignorados")

                if members_data:
                    count = await db.sync_member_profiles(members_data)
                    logging.info(f"✅ Sincronizados {len(members_data)} membros do servidor '{guild.name}' ({count} novos)")
                else:
                    logging.warning(f"⚠️ Nenhum membro válido encontrado no servidor '{guild.name}'")
                    logging.warning(f"Verifique se o bot tem o intent 'members' habilitado no Discord Developer Portal")
        except Exception as e:
            logging.error(f"❌ Erro na task de sincronização de membros: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
        finally:
            logging.info("=" * 60)

    @sync_members_task.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ActivityTracker(bot))
