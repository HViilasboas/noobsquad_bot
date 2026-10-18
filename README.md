# NoobSquad Discord Music Bot

## Descrição
Bot de música para Discord, tocando músicas do YouTube, com fila, presets de equalização, auto-play e comandos de manutenção.

---

## Comandos Disponíveis

Os comandos principais são híbridos: funcionam como slash commands (`/play`) ou
com o prefixo tradicional (`!play`). A sincronização global do Discord pode levar
alguns minutos para exibi-los.

- `!play <url> [preset] [autoplay]`
  - Toca uma música ou playlist do YouTube. Também aceita playlists públicas do Spotify, buscando cada faixa no YouTube.
  - `preset` (opcional): `padrao`, `pop`, `rock`, `graves`.
  - `autoplay` (opcional): ativa reprodução automática de músicas recomendadas.
- `!stop`
  - Para a reprodução atual.
- `!skip`
  - Pula para a próxima música da fila.
- `!leave`
  - Faz o bot sair do canal de voz e limpa a fila.
- `/fila`, `/pause`, `/resume`, `/volume`, `/loop`, `/shuffle`, `/remove`, `/clear`
  - Gerenciam a reprodução e a fila, também acessíveis pelo painel com botões.
- `/monitorar_youtube` e `/monitorar_twitch`
  - Permitem escolher o canal de destino e se o assinante será mencionado.
- `/rank <categoria> [jogo] [dias]`
  - Exibe rankings totais ou dos últimos 7, 30 ou 90 dias.
- `/steam_lancamentos [limite]`
  - Recomenda próximos lançamentos da Steam usando os jogos mais ativos da comunidade.
- `/steam_configurar [canal] [ativo] [mencionar] [afinidade_minima]`
  - Configura notificações automáticas de lançamentos relevantes; exige Gerenciar Servidor.

### Recomendações Steam

O catálogo de próximos lançamentos é consultado periodicamente na loja pública Steam e
armazenado no MongoDB. As recomendações usam gêneros e modos de jogo em comum com as
atividades de Discord registradas nos últimos 90 dias; nenhuma conta Steam precisa ser
vinculada. Datas sem precisão, como "Coming soon", continuam visíveis, mas devem ser
tratadas como estimativas da loja.
- `!reboot`
  - Reinicia o processo (apenas para o owner).
- `!rebuild`
  - Recria o ambiente e reinstala as dependências fixadas (apenas para o owner).

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
   SPOTIFY_CLIENT_ID=client_id_da_aplicacao_spotify
   SPOTIFY_CLIENT_SECRET=client_secret_da_aplicacao_spotify
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

- `/play` aceita URLs do YouTube, YouTube Music, playlists ou uma busca por texto.
- Para importar playlists públicas do Spotify, crie uma aplicação em [Spotify for Developers](https://developer.spotify.com/dashboard) e preencha `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET` no `.env`. O bot usa os metadados da playlist para buscar cada faixa no YouTube; não transmite áudio do Spotify.
- Para melhor qualidade de áudio, utilize canais de voz com bitrate acima de 128 kbps.
- O comando `!reboot` é restrito ao owner do bot.

## Compartilhamento de tela por link

O bot cria uma sessão WebRTC e entrega dois links: um privado para o apresentador e
outro para os espectadores. Abra o link do apresentador no computador cuja tela
será compartilhada e clique em **Escolher o que compartilhar**. O seletor do
navegador permite escolher uma tela inteira, uma janela de aplicativo ou uma aba.
O navegador pede essa escolha e autorização a cada transmissão; o bot não captura
a tela em segundo plano. Não é necessário instalar um agente local: a página aberta
no navegador captura a fonte escolhida e envia o vídeo ao servidor MediaMTX. O áudio
do sistema é opcional e depende do navegador e do sistema operacional.

A captura solicita até **1920×1080 a 30 fps**, marca o conteúdo como apresentação/texto
e limita a codificação a 8 Mbps. Esses números são metas e limites: o navegador, a
resolução da tela escolhida, a CPU/GPU e a rede determinam a qualidade efetiva. A
página do apresentador mostra a resolução e a taxa de quadros capturadas. Para 1080p30
estável, use Chrome ou Edge atual, uma tela de pelo menos 1920×1080 e conexão cabeada
quando possível. O navegador não permite impor 30 fps mínimos para captura de tela;
se o equipamento ou a rede não sustentarem esse ritmo, a taxa real pode cair.

O MediaMTX encaminha o mesmo fluxo a cada espectador e não o recodifica. Com o limite
de 8 Mbps, reserve aproximadamente **10 Mbps de upload estável por espectador** no
servidor, além do tráfego normal da rede. Por exemplo, três espectadores podem exigir
cerca de 30 Mbps de upload sustentado. O download de cada espectador também precisa
acompanhar a taxa do fluxo. Dois servidores STUN são usados por padrão para atravessar
NAT; se uma rede bloquear WebRTC direto/UDP, configure um servidor TURN.

Comandos disponíveis para quem tem **Gerenciar Servidor**:

- `/stream iniciar`: cria os links e publica o link para assistir no canal;
- `/stream parar`: encerra a sessão e desconecta apresentador e espectadores;
- `/stream status`: mostra se está aguardando o apresentador ou ao vivo.

O `run.bat` inicia o MediaMTX pelo Docker Compose. Para links por DDNS,
configure `STREAM_DOMAIN`, `STREAM_PUBLIC_URL`, `STREAM_PUBLIC_ORIGIN`,
`STREAM_MEDIA_URL` e `STREAM_MEDIA_PUBLIC_HOST` com o hostname público. O registro
DDNS deve apontar para o IP WAN público, nunca para um endereço privado da LAN.
O Caddy serve HTTPS na porta alternativa **28443**, usando um certificado PEM e
uma chave privada já emitidos para o hostname. Coloque a cadeia em
`caddy_certs/noobsquad_tls_fullchain.pem` e a chave correspondente em
`caddy_certs/noobsquad_tls.key`; essa pasta é ignorada pelo Git. Renove o
certificado antes do vencimento e substitua a cadeia pelo arquivo atualizado.
TCP 28080 oferece redirecionamento HTTP opcional para HTTPS em 28443.

```dotenv
STREAM_DOMAIN=noobsquad.ddns.net
STREAM_HTTP_PORT=28080
STREAM_PUBLIC_PORT=28443
STREAM_MEDIA_UDP_PORT=28189
STREAM_PUBLIC_URL=https://${STREAM_DOMAIN}:${STREAM_PUBLIC_PORT}
STREAM_PUBLIC_ORIGIN=https://${STREAM_DOMAIN}:${STREAM_PUBLIC_PORT}
STREAM_MEDIA_URL=https://${STREAM_DOMAIN}:${STREAM_PUBLIC_PORT}/media
STREAM_MEDIA_PUBLIC_HOST=${STREAM_DOMAIN}
```

`STREAM_MEDIA_PUBLIC_HOST` aceita vários endereços separados por vírgula. O exemplo
usa somente o hostname DDNS. O Compose configura dois servidores STUN e as páginas os
usam para coletar candidatos ICE. Para redes restritivas, um TURN pode substituir o segundo STUN:
configure `STREAM_ICE_SERVER_1_URL`, por exemplo,
`turn:turn.seudominio.com:28478?transport=tcp`, defina
`STREAM_ICE_SERVER_1_USERNAME=AUTH_SECRET` e coloque em
`STREAM_ICE_SERVER_1_PASSWORD` o segredo `use-auth-secret` do Coturn. O aplicativo
gera credenciais temporárias por sessão. O Coturn é um serviço separado e precisa de
porta TCP de escuta e de uma faixa de portas de relay encaminhadas no roteador e no
firewall; esses encaminhamentos dependem da faixa configurada no Coturn.

O HTTPS do app em `STREAM_PUBLIC_PORT` (28443) deve ser encaminhado para a porta
28443 do host. O certificado precisa ser confiável, válido para `STREAM_DOMAIN` e
corresponder à chave privada instalada; os navegadores recusam a captura de tela
em uma origem sem HTTPS válido. As portas externas 80 e 443 não são necessárias
para o certificado instalado manualmente. O WebRTC usa
UDP na porta `STREAM_MEDIA_UDP_PORT` e também escuta TCP na mesma porta como
alternativa se UDP estiver bloqueado.

Inicie o bot e os serviços de mídia/proxy (`docker compose up -d mediamtx caddy`).
Libere no firewall **TCP 28443** e **UDP e TCP 28189**. No roteador, encaminhe
TCP 28443 para a porta 28443 do host e UDP/TCP 28189 para a porta 28189. TCP
28080 é opcional e redireciona HTTP para HTTPS. O
MediaMTX anuncia o hostname DDNS e recebe o tráfego de mídia em UDP 28189, com TCP
28189 como alternativa. **Não exponha TCP 8080, 8889 ou 9997**: o proxy encaminha
internamente a aplicação e o sinal WebRTC, e a
API administrativa permanece local. O `Caddyfile` encaminha `/media/...` ao
MediaMTX e as demais rotas ao bot. Em redes com NAT restritivo ou UDP bloqueado,
pode ser necessário configurar um servidor TURN.

Cada servidor pode ter uma transmissão ativa por vez. As sessões expiram após
240 minutos por padrão; altere `STREAM_SESSION_MAX_MINUTES` se necessário. Os
links são temporários e dão acesso à transmissão enquanto a sessão existir.

### Verificação da transmissão

Rode a suíte localmente com:

```powershell
.\.venv\Scripts\python.exe -m unittest discover --start-directory tests --pattern "test_*.py" --verbose
node --test tests/streaming_viewer.test.js tests/stream_diagnostics.test.js
```

O GitHub Actions executa as suítes Python e JavaScript em cada push e pull
request. O teste JavaScript verifica que o espectador mantém a conexão WebRTC
ativa depois de conectar e só a encerra quando a conexão cai ou o usuário
desconecta. Depois de alterar o NAT, teste de fora da rede local (por exemplo,
usando os dados móveis):

```powershell
Test-NetConnection noobsquad.ddns.net -Port 28443
curl.exe https://noobsquad.ddns.net:28443/health
```

O primeiro comando deve mostrar `TcpTestSucceeded: True`; o segundo deve retornar
`{"status": "ok"}` sem ignorar a validação TLS.

### Acesso na rede local

Os links usam o hostname DDNS também dentro da rede local. Isso depende de o roteador
suportar NAT loopback; sem esse recurso, clientes locais não conseguem retornar ao
servidor pelo IP externo. A rota de mídia também anuncia somente esse IP, conforme
`STREAM_MEDIA_PUBLIC_HOST`.

## Inicialização automática no Windows

Execute `run.bat` na raiz do projeto. Ele agora:

1. inicia o Docker Desktop caso necessário;
2. cria/inicia o MongoDB definido em `docker-compose.yml` e aguarda o healthcheck;
3. inicia o MediaMTX e, se `STREAM_DOMAIN` estiver configurado, o Caddy para HTTPS;
4. cria a `.venv` e instala as dependências quando ela não existir;
5. mantém o bot em execução, reiniciando-o após falhas.

Comandos de manutenção, disponíveis somente para o proprietário do bot:

- `!reiniciar` (ou `!reboot`): reinicia apenas o processo;
- `!rebuild` (ou `!recriar_ambiente`): encerra o bot, apaga a `.venv`, reinstala as
  dependências — incluindo a versão atual do `yt-dlp` — e inicia novamente.

O volume `mongodb_data` preserva os dados mesmo quando o container é recriado.
Para iniciar junto com o Windows, crie uma tarefa no Agendador de Tarefas apontando
para o caminho completo de `run.bat`, configurada para executar no logon.

---

Dúvidas ou problemas? Consulte os comentários no código ou abra uma issue.
