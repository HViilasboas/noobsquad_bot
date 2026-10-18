import asyncio
import logging
from pathlib import Path

from discord.ext import commands


class MaintenanceCommands(commands.Cog):
    """Comandos administrativos processados pelo supervisor run.bat."""

    def __init__(self, bot):
        self.bot = bot
        self.project_root = Path(__file__).resolve().parent.parent

    @commands.command(name="rebuild", aliases=["recriar_ambiente"])
    @commands.is_owner()
    async def rebuild(self, ctx):
        """Recria a .venv, atualiza dependencias e reinicia o bot."""
        flag = self.project_root / "rebuild.flag"
        flag.write_text("requested\n", encoding="utf-8")
        logging.warning("Reconstrucao do ambiente solicitada por %s", ctx.author)
        await ctx.send(
            "Reconstrução solicitada. Vou ficar offline enquanto o ambiente é "
            "recriado e voltarei automaticamente."
        )
        await asyncio.sleep(1)
        await self.bot.close()

    @commands.command(name="reiniciar", aliases=["reboot"])
    @commands.is_owner()
    async def restart(self, ctx):
        """Reinicia somente o processo do bot, sem apagar a .venv."""
        await ctx.send("Reiniciando o bot...")
        await asyncio.sleep(1)
        await self.bot.close()

    @rebuild.error
    @restart.error
    async def maintenance_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("Este comando só pode ser usado pelo proprietário do bot.")
            return
        raise error
