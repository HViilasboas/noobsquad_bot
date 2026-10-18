import discord
from discord.ext import commands

class HelpCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='ajuda', description='Mostra todos os comandos do bot')
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
                `/play <url ou busca> [preset] [autoplay]` - Toca ou adiciona à fila; aceita playlists públicas do Spotify
                `/fila` - Exibe a música atual e a fila
                `/pause`, `/resume`, `/skip`, `/stop`, `/leave` - Controles
                `/volume <0-200>` - Ajusta o volume
                `/loop <desligado|musica|fila>` - Configura repetição
                `/shuffle`, `/remove`, `/clear` - Editam a fila
                `/profile` - Mostra seu perfil musical
                `/recommend` - Recomenda músicas pelo histórico
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
                `/monitorar_youtube <canal> [destino] [mencionar]`
                `/monitorar_twitch <canal> [destino] [mencionar]`
                `/remover_monitoramento <plataforma> <canal>`
                `/listar_monitoramento` - Lista suas assinaturas
            """,
            inline=False
        )

        embed.add_field(
            name="Rankings",
            value="`/rank <categoria> [jogo] [dias]` - Períodos: 7, 30 ou 90 dias",
            inline=False,
        )
        embed.add_field(
            name="Steam",
            value=(
                "`/steam_lancamentos [limite]` - Recomenda próximos jogos\n"
                "`/steam_configurar` - Configura avisos automáticos (admin)\n"
                "`/steam_atualizar` - Atualiza o catálogo (admin)"
            ),
            inline=False,
        )
        embed.add_field(
            name="Compartilhamento de tela",
            value=(
                "`/stream iniciar` - Cria os links privados para transmitir e assistir\n"
                "`/stream parar` - Encerra a transmissão\n"
                "`/stream status` - Mostra o estado da sessão\n"
                "Requer a permissão Gerenciar Servidor."
            ),
            inline=False,
        )
        embed.set_footer(text="Comandos slash híbridos também funcionam com o prefixo !")
        await ctx.send(embed=embed)
