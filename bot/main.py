import discord
import logging
from datetime import datetime
from discord.ext import commands

from config.settings import DISCORD_TOKEN, REBOOT_CHANNEL_ID
from db.database import db
from bot.commands import MusicCommands, HelpCommands, StreamCommands
from bot.commands_music import MusicControls
from bot.commands_monitor import MonitorCommands
from bot.commands_ranking import RankingCommands
from bot.scheduler import MonitorScheduler
from bot.cogs_activity import ActivityTracker
from bot.commands_maintenance import MaintenanceCommands
from bot.commands_steam import SteamCommands
from bot.steam_scheduler import SteamScheduler
from bot.streaming import ScreenShareService

# --- CONFIGURAÇÃO DE LOGGING ---
log_filename = datetime.now().strftime("bot_log_%Y-%m-%d.log")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

if not DISCORD_TOKEN:
    logging.error("Token do bot não encontrado no arquivo .env")
    raise ValueError("Token do bot não encontrado no arquivo .env")
if not REBOOT_CHANNEL_ID:
    logging.error("ID do canal de reboot não encontrado no arquivo .env")
    raise ValueError("ID do canal de reboot não encontrado no arquivo .env")

# --- CONFIGURAÇÃO DAS INTENTS E BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.presences = True
intents.members = True  # Necessário para acessar guild.members
screen_share_service = ScreenShareService()


class NoobSquadBot(commands.Bot):
    async def close(self):
        try:
            await screen_share_service.close()
        except Exception:
            logging.error("Erro ao encerrar o serviço de compartilhamento", exc_info=True)
        await super().close()


bot = NoobSquadBot(
    command_prefix="!", intents=intents, heartbeat_timeout=60.0, help_command=None
)

# Criar instância do scheduler
scheduler = MonitorScheduler(bot)
steam_scheduler = SteamScheduler(bot)
cogs_initialized = False
commands_synced = False


# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
def setup_database():
    """Inicializa a conexão com o banco de dados"""
    try:
        db.connect()
        db.initialize_collections()  # Inicializa as coleções e índices
        logging.info("Banco de dados inicializado com sucesso!")
    except Exception as e:
        logging.error(f"Erro ao inicializar banco de dados: {e}")
        raise e


# --- REGISTRAR OS COGS ---
async def setup_cogs():
    """Configura os Cogs do bot"""
    # Garante que o banco de dados está conectado antes de registrar os Cogs
    setup_database()
    bot.add_view(MusicControls(0))
    await screen_share_service.start()

    await bot.add_cog(MusicCommands(bot))
    await bot.add_cog(StreamCommands(bot, screen_share_service))
    await bot.add_cog(MonitorCommands(bot))
    await bot.add_cog(RankingCommands(bot))
    await bot.add_cog(HelpCommands(bot))
    activity_tracker = ActivityTracker(bot)
    await bot.add_cog(activity_tracker)
    await bot.add_cog(MaintenanceCommands(bot))
    await bot.add_cog(SteamCommands(bot))
    await activity_tracker.reconcile_current_activities()

    # Iniciar o scheduler de monitoramento
    await scheduler.start()
    await steam_scheduler.start()

    logging.info("Cogs registrados com sucesso!")


@bot.event
async def on_ready():
    """Evento disparado quando o bot está pronto e conectado"""
    global cogs_initialized, commands_synced
    just_initialized = False
    if not cogs_initialized:
        await setup_cogs()
        cogs_initialized = True
        just_initialized = True
    if not commands_synced:
        synced = await bot.tree.sync()
        commands_synced = True
        logging.info("%s comandos de aplicação sincronizados", len(synced))
    logging.info(f"Bot conectado como {bot.user.name}")

    try:
        # Reconectar ao canal de voz se o bot reiniciar
        reboot_channel = bot.get_channel(REBOOT_CHANNEL_ID)
        if reboot_channel and just_initialized:
            await reboot_channel.send("🔄 Bot reiniciado e pronto para uso!")
    except Exception as e:
        logging.error(f"Erro ao enviar mensagem de reboot: {e}")


@bot.event
async def on_command_error(ctx, error):
    """Trata erros de comando."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(
            f"🤔 Comando não encontrado. Digite `!ajuda` para ver a lista de comandos disponíveis."
        )
    else:
        # Para outros erros, loga e informa o usuário
        logging.error(f"Ocorreu um erro no comando '{ctx.command}': {error}")
        await ctx.send(
            "❌ Ocorreu um erro ao processar o comando. Por favor, tente novamente."
        )


@bot.tree.error
async def on_app_command_error(interaction, error):
    """Retorna erros de slash commands sem expor detalhes internos."""
    logging.error("Erro em comando de aplicação: %s", error)
    message = "❌ Não foi possível executar este comando. Tente novamente."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.event
async def on_error(event, *args, **kwargs):
    """Tratamento global de erros"""
    logging.error(f"Erro no evento {event}: ", exc_info=True)


# Cleanup quando o bot for desligado
def cleanup():
    """Limpa recursos ao desligar o bot"""
    try:
        scheduler.stop()  # Para as tasks de monitoramento
        steam_scheduler.stop()
        db.close()
        logging.info("Recursos do bot liberados com sucesso.")
    except Exception as e:
        logging.error(f"Erro ao liberar recursos: {e}")


# Iniciar o bot
try:
    bot.run(DISCORD_TOKEN)
except Exception as e:
    logging.error(f"Erro ao iniciar o bot: {e}")
finally:
    cleanup()
