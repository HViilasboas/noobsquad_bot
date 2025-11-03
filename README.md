# NoobSquad Discord Bot

## Descrição
Bot multifuncional para Discord, com funcionalidades de música (YouTube) e monitoramento de canais (YouTube e Twitch).

**Funcionalidades de Música:**
- Toca músicas e playlists do YouTube.
- Fila de reprodução.
- Presets de equalização.
- Auto-play de músicas recomendadas.

**Funcionalidades de Monitoramento:**
- Monitora canais do YouTube e Twitch.
- Notifica no servidor quando um novo vídeo é postado ou uma transmissão ao vivo começa.

---

## Comandos Disponíveis

### Comandos de Música

- `!play <url> [autoplay]`
  - Toca uma música ou playlist do YouTube.
  - `autoplay` (opcional): ativa reprodução automática de músicas recomendadas.
- `!stop`
  - Para a reprodução atual.
- `!skip`
  - Pula para a próxima música da fila.
- `!leave`
  - Faz o bot sair do canal de voz e limpa a fila.
- `!profile`
  - Mostra seu perfil musical e histórico recente.
- `!recommend`
  - Mostra recomendações com base nas suas preferências musicais.
- `!reproduzir_historico [count] [append] [search]`
  - Adiciona músicas do seu histórico de reprodução à fila.
  - `count` (opcional): quantas músicas adicionar (padrão 5).
  - `append` (flag): adiciona ao final da fila em vez de tocar em seguida.
  - `search` (flag): tenta buscar a faixa no YouTube pelo título, caso não exista URL no histórico.
  - Exemplos:
    - `!reproduzir_historico` — insere as últimas 5 músicas para tocar em seguida.
    - `!reproduzir_historico 10 append` — adiciona 10 músicas ao final da fila.
    - `!reproduzir_historico 8 search` — tenta buscar por título quando necessário.

### Comandos de Monitoramento

- `!monitorar_youtube <canal>`
  - Monitora um canal do YouTube (aceita URL, ID ou handle)
- `!monitorar_twitch <canal>`
  - Monitora um canal da Twitch
- `!remover_monitoramento <plataforma> <nome_do_canal>`
  - Para de monitorar um canal (ou remove sua inscrição)
- `!listar_monitoramento`
  - Lista os canais que você está monitorando

---

## Como Configurar

1.  Acesse o [Discord Developer Portal](https://discord.com/developers/applications).
2.  Crie uma "New Application" e dê um nome ao seu bot.
3.  No menu lateral, vá em "Bot" e clique em "Add Bot".
4.  Em "TOKEN", clique em "Reset Token" e copie o token gerado.
5.  Crie um arquivo `.env` na raiz do projeto com o seguinte conteúdo:
    ```env
    DISCORD_TOKEN=seu_token_aqui
    REBOOT_CHANNEL_ID=ID_do_canal_para_mensagens_de_reboot
    CHAT_JUKEBOX=ID_do_canal_de_comandos_de_musica
    MONGODB_URI=sua_string_de_conexao_mongodb
    DATABASE_NAME=nome_do_banco_de_dados
    ```
    - O `REBOOT_CHANNEL_ID` pode ser obtido clicando com o botão direito no canal desejado no Discord e selecionando "Copiar ID" (ative o modo desenvolvedor nas configurações do Discord).
    - `MONGODB_URI` e `DATABASE_NAME` são as credenciais para seu banco de dados MongoDB.

---

## Instalação e Execução

1.  Instale o Python 3.8+.
2.  Crie um ambiente virtual e instale dependências do `requirements.txt` (se houver):

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install yt-dlp
```

3.  Configure o `.env` e execute o bot (por exemplo via `run.bat`).

---

## Problemas Comuns com a Biblioteca yt-dlp

A biblioteca `yt-dlp` é usada para extrair áudio do YouTube. Devido a mudanças frequentes na plataforma, pode ser necessário reinstalar ou atualizar a biblioteca.

**Sintomas de problema:**
- O bot não consegue tocar músicas ou retorna erro de download.
- Mensagens de erro como "DownloadError" ou "Falha ao obter URL de stream".

**Solução:**
- Execute o comando abaixo para reinstalar/atualizar o yt-dlp:

```powershell
pip install --upgrade yt-dlp
```

---

Se quiser, posso adicionar exemplos de uso mais detalhados no README e instruções de troubleshooting específicas para MongoDB e credenciais do YouTube/Twitch.
