#!/usr/bin/env bash
set -e

# Espera pelo MongoDB (host 'mongo' quando utilizado com docker-compose)
HOST=${MONGO_HOST:-mongo}
PORT=${MONGO_PORT:-27017}
MAX_RETRIES=${WAIT_MAX_RETRIES:-30}

count=0
until nc -z "$HOST" "$PORT" >/dev/null 2>&1 || [ $count -ge $MAX_RETRIES ]; do
  echo "Aguardando $HOST:$PORT... ($count)"
  count=$((count+1))
  sleep 1
done

if [ $count -ge $MAX_RETRIES ]; then
  echo "Timeout esperando por $HOST:$PORT" >&2
  # não falha aqui - talvez o usuário queira rodar sem mongo
fi

# Executa o comando padrão (passado no CMD do Dockerfile) ou executa bot/main.py
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec python -u bot/main.py
fi

