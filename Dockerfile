# Dockerfile for NoobSquad Discord Bot
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Instala dependências do sistema (ffmpeg é necessário para reprodução de áudio)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       build-essential \
       git \
       netcat-openbsd \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia requirements primeiro para usar cache do docker
COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

# Copia o código da aplicação
COPY . /app

# Garante que entrypoint seja executável
RUN chmod +x /app/entrypoint.sh || true

# Usuário opcional não-root
RUN useradd --create-home appuser || true
USER appuser
WORKDIR /app

# Entrypoint espera serviços dependentes (mongo) e executa o comando
ENTRYPOINT ["/app/entrypoint.sh"]
# Executa o bot (usa bot/main.py). Ajuste se seu entrypoint for diferente.
CMD ["python", "-u", "bot/main.py"]

