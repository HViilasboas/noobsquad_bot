import discord
from discord.ext import commands

class HelpCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='ajuda')
    async def help_command(self, ctx):
        """Mostra a lista de comandos disponíveis"""

        embed = discord.Embed(
            title="🎵 Comandos do Bot Noob-Squad Music",
            description="Lista de comandos disponíveis:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Comandos de Música",
            value="""
                `!play <url> [autoplay]` - Toca uma música do YouTube ou adiciona à fila
                `!skip` - Pula para a próxima música
                `!stop` - Para a música e limpa a fila
                `!leave` - Faz o bot sair do canal de voz
                `!profile` - Mostra seu perfil musical
                `!recommend` - Mostra recomendações com base nas suas preferências
                `!reproduzir_historico [count] [append] [search]` - Adiciona músicas do seu histórico à fila
                  - `count` (opcional): quantas músicas adicionar (padrão 5)
                  - `append` (flag): adiciona ao final da fila em vez de tocar em seguida
                  - `search` (flag): tenta buscar por título quando não houver URL no histórico
            """,
            inline=False
        )

        embed.add_field(
            name="Comandos de Monitoramento",
            value="""
                `!monitorar_youtube <canal>` - Monitora um canal do YouTube
                `!monitorar_twitch <canal>` - Monitora um canal da Twitch
                `!remover_monitoramento <plataforma> <nome_do_canal>` - Para de monitorar um canal (ou remove sua inscrição)
                `!listar_monitoramento` - Lista os canais que você está monitorando
            """,
            inline=False
        )

        await ctx.send(embed=embed)
