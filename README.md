# NoobSquad Discord Music Bot

## Descrição
Bot de música para Discord, tocando músicas do YouTube, com fila, presets de equalização, auto-play e comandos de manutenção.

---

## Comandos Disponíveis

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
- `!reboot`
  - Reinicia o bot e reinstala dependências (apenas para o owner).

---

## Como Gerar o Token do Discord

1. Acesse o [Discord Developer Portal](https://discord.com/developers/applications).
2. Clique em "New Application" e dê um nome ao seu bot.
3. No menu lateral, vá em "Bot" e clique em "Add Bot".
4. Em "TOKEN", clique em "Reset Token" e copie o token gerado.
5. Crie um arquivo `.env` na raiz do projeto com o conteúdo:
   ```
   DISCORD_TOKEN=seu_token_aqui
   REBOOT_CHANNEL_ID=ID_do_canal_para_mensagens_de_reboot
   ```
   - O `REBOOT_CHANNEL_ID` pode ser obtido clicando com o botão direito no canal desejado no Discord e selecionando "Copiar ID" (ative o modo desenvolvedor nas configurações do Discord se necessário).

---

## Instalação e Execução

1. Instale o Python 3.8+.
2. Execute o script `run.bat` para criar o ambiente virtual, instalar dependências e iniciar o bot.
3. O bot será reiniciado automaticamente se o arquivo `reboot.flag` for criado (usado pelo comando `!reboot`).

---

## Problemas Comuns com a Biblioteca yt-dlp

A biblioteca `yt-dlp` é usada para extrair áudio do YouTube. Devido a mudanças frequentes no YouTube, pode ser necessário reinstalar ou atualizar a biblioteca para garantir o funcionamento do bot.

**Sintomas de problema:**
- O bot não consegue tocar músicas ou retorna erro de download.
- Mensagens de erro como "DownloadError" ou "Falha ao obter URL de stream".

**Solução:**
- Execute o comando abaixo para reinstalar/atualizar o yt-dlp:
  ```powershell
  pip install --upgrade yt-dlp
  ```
- Caso o erro persista, remova a pasta do ambiente virtual `.venv` e execute novamente o `run.bat` para reinstalar todas as dependências.

---

## Observações

- O bot só funciona com URLs do YouTube ou YouTube Music.
- Para melhor qualidade de áudio, utilize canais de voz com bitrate acima de 128 kbps.
- O comando `!reboot` é restrito ao owner do bot.

---

Dúvidas ou problemas? Consulte os comentários no código ou abra uma issue.
