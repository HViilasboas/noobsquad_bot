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

- `!play <url> [preset] [autoplay]`
  - Toca uma música ou playlist do YouTube.
  - `preset` (opcional): `padrao`, `pop`, `rock`, `graves`.
  - `autoplay` (opcional): ativa reprodução automática de músicas recomendadas.
- `!stop`
  - Para a reprodução atual.
- `!skip`
  - Pula para a próxima música da fila.
- `!leave`
  - Faz o bot sair do canal de voz e limpa a fila.
- `!check_bitrate`
  - Mostra o bitrate do canal de voz atual.

### Comandos de Monitoramento

- `!addchannel <plataforma> <url_do_canal>`
  - Adiciona um canal para ser monitorado.
  - `plataforma`: `youtube` ou `twitch`.
- `!removechannel <url_do_canal>`
  - Remove um canal da sua lista de monitoramento.
- `!listchannels`
  - Lista todos os canais que você está monitorando.

### Comandos de Manutenção

- `!reboot`
  - Reinicia o bot e reinstala dependências (apenas para o owner).

---

## Como Configurar

1.  Acesse o [Discord Developer Portal](https://discord.com/developers/applications).
2.  Crie uma "New Application" e dê um nome ao seu bot.
3.  No menu lateral, vá em "Bot" e clique em "Add Bot".
4.  Em "TOKEN", clique em "Reset Token" e copie o token gerado.
5.  Crie um arquivo `.env` na raiz do projeto com o seguinte conteúdo:
    ```
    DISCORD_TOKEN=seu_token_aqui
    REBOOT_CHANNEL_ID=ID_do_canal_para_mensagens_de_reboot
    MONGO_URI=sua_string_de_conexao_mongodb
    MONGO_DB_NAME=nome_do_banco_de_dados
    ```
    - O `REBOOT_CHANNEL_ID` pode ser obtido clicando com o botão direito no canal desejado no Discord e selecionando "Copiar ID" (ative o modo desenvolvedor nas configurações do Discord).
    - `MONGO_URI` e `MONGO_DB_NAME` são as credenciais para seu banco de dados MongoDB.

---

## Instalação e Execução

1.  Instale o Python 3.8+.
2.  Execute o script `run.bat` para criar o ambiente virtual, instalar dependências e iniciar o bot.
3.  O bot será reiniciado automaticamente se o arquivo `reboot.flag` for criado (usado pelo comando `!reboot`).

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
