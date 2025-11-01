import logging
import discord
from discord.ext import commands
from .commands_utils import validar_canal

class HelpCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='ajuda')
    async def help_command(self, ctx):
        """Mostra a lista de comandos disponíveis"""
        # if not validar_canal(ctx):
        #     await ctx.send("O Animal, Use o canal JUKEBOX para comandos de música.")
        #     return

        embed = discord.Embed(
            title="🎵 Comandos do Bot Noob-Squad Music",
            description="Lista de comandos disponíveis:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Comandos de Música",
            value="""
                `!play <url> [autoplay]` - Toca uma música do YouTube ou adiciona à fila
                `!pause` - Pausa a música atual
                `!resume` - Continua a música pausada
                `!skip` - Pula para a próxima música
                `!stop` - Para a música e limpa a fila
                `!queue` - Mostra a fila de reprodução
                `!autoplay` - Ativa/desativa reprodução automática
                `!profile` - Mostra seu perfil musical
            """,
            inline=False
        )

        embed.add_field(
            name="Comandos de Monitoramento",
            value="""
                `!monitorar_youtube <canal>` - Monitora um canal do YouTube
                `!monitorar_twitch <canal>` - Monitora um canal da Twitch
                `!unmonitor <plataforma> <canal>` - Para de monitorar um canal
                `!list` - Lista todos os canais monitorados
            """,
            inline=False
        )

        await ctx.send(embed=embed)
