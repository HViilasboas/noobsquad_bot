import logging

import discord
from discord import app_commands
from discord.ext import commands

from .streaming import ScreenShareError, ScreenShareService


class StreamCommands(commands.Cog):
    """Discord controls for browser-based screen-sharing sessions."""

    stream = app_commands.Group(
        name="stream",
        description="Compartilhamento de tela por link",
    )

    def __init__(self, bot: commands.Bot, service: ScreenShareService):
        self.bot = bot
        self.service = service

    @stream.command(name="iniciar", description="Cria links para transmitir e assistir à tela")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def iniciar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            session = await self.service.create_session(
                guild_id=interaction.guild_id,
                owner_id=interaction.user.id,
            )
        except ScreenShareError as exc:
            await interaction.followup.send(f"Não foi possível iniciar: {exc}", ephemeral=True)
            return

        watch_embed = discord.Embed(
            title="📺 Compartilhamento preparado",
            description=(
                "A transmissão começará quando o apresentador abrir o link privado e "
                "escolher uma tela, janela ou aba no navegador.\n\n"
                f"**Assistir:** {self.service.viewer_url(session)}"
            ),
            color=discord.Color.blurple(),
        )
        watch_embed.set_footer(text="A sessão expira automaticamente após o limite configurado.")
        if self.service.local_only:
            watch_embed.add_field(
                name="Acesso local",
                value=(
                    "As URLs atuais usam localhost e só abrem neste computador. Para outros "
                    "espectadores, configure os domínios HTTPS descritos no README."
                ),
                inline=False,
            )
        if interaction.channel is None:
            await interaction.followup.send(
                "Não consegui publicar o link de visualização neste canal.", ephemeral=True
            )
            await interaction.followup.send(
                f"🔐 Link privado para transmitir: <{self.service.presenter_url(session)}>",
                ephemeral=True,
            )
            return
        await interaction.edit_original_response(
            content=(
                "🔐 **Link privado para transmitir** (enviei somente para você):\n"
                f"<{self.service.presenter_url(session)}>\n\n"
                "Abra esse link no computador cuja tela será compartilhada."
            )
        )
        await interaction.channel.send(embed=watch_embed)
        logging.info(
            "Sessão de tela criada: guild=%s owner=%s path=%s",
            interaction.guild_id,
            interaction.user.id,
            session.path,
        )

    @stream.command(name="parar", description="Encerra a transmissão do servidor")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def parar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            session = await self.service.stop_guild(interaction.guild_id)
        except ScreenShareError as exc:
            await interaction.followup.send(
                f"Não consegui encerrar a conexão de mídia: {exc}", ephemeral=True
            )
            return

        if session is None:
            await interaction.followup.send(
                "Não há uma transmissão ativa neste servidor.", ephemeral=True
            )
            return
        await interaction.followup.send("A transmissão foi encerrada.", ephemeral=True)
        logging.info(
            "Sessão de tela encerrada: guild=%s owner=%s path=%s",
            interaction.guild_id,
            interaction.user.id,
            session.path,
        )

    @stream.command(name="status", description="Mostra o estado da transmissão do servidor")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction):
        session = self.service.active_session(interaction.guild_id)
        if session is None:
            await interaction.response.send_message(
                "Não há uma transmissão ativa neste servidor.", ephemeral=True
            )
            return

        labels = {
            "ready": "Aguardando o apresentador",
            "live": "Ao vivo",
            "stopping": "Encerrando",
            "ended": "Encerrada",
        }
        await interaction.response.send_message(
            f"**Estado:** {labels.get(session.state, session.state)}\n"
            f"**Apresentador:** <@{session.owner_id}>\n"
            f"**Assistir:** {self.service.viewer_url(session)}",
            ephemeral=True,
        )

    @iniciar.error
    @parar.error
    @status.error
    async def stream_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = "Você precisa da permissão **Gerenciar Servidor** para controlar transmissões."
        else:
            logging.error("Erro em comando de transmissão: %s", error, exc_info=error)
            message = "Não foi possível processar o comando de transmissão."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
