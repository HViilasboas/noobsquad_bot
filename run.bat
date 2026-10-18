@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%CD%"
set "VENV_DIR=%CD%\.venv"

call :ensure_mongodb
if errorlevel 1 exit /b 1
call :ensure_mediamtx
if errorlevel 1 exit /b 1

:start
if exist "rebuild.flag" (
    call :rebuild_environment
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel preparar o ambiente Python.
        timeout /t 15 /nobreak >nul
        goto :start
    )
)
if not exist "%VENV_DIR%\Scripts\python.exe" (
    call :create_environment
    if errorlevel 1 (
        timeout /t 15 /nobreak >nul
        goto :start
    )
)

echo [BOT] Iniciando...
"%VENV_DIR%\Scripts\python.exe" bot\main.py
echo [BOT] Processo encerrado. Reiniciando em 5 segundos...
timeout /t 5 /nobreak >nul
goto :start

:create_environment
echo [PYTHON] Criando ambiente virtual...
py -3 -m venv "%VENV_DIR%" || exit /b 1
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade -r requirements.txt || exit /b 1
where ffmpeg >nul 2>&1 || echo [AVISO] FFmpeg nao esta no PATH. Instale-o antes de usar musica.
exit /b 0

:rebuild_environment
echo [PYTHON] Reconstruindo ambiente solicitado pelo Discord...
del /q "rebuild.flag" >nul 2>&1
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
call :create_environment
exit /b %errorlevel%

:ensure_mongodb
where docker >nul 2>&1 || (
    echo [ERRO] Docker nao foi encontrado no PATH.
    exit /b 1
)
docker info >nul 2>&1 || call :start_docker_desktop
docker info >nul 2>&1 || (
    echo [ERRO] Docker Desktop nao ficou disponivel.
    exit /b 1
)
for /f %%M in ('docker ps --filter "publish=27017" --format "{{.Names}}"') do (
    docker exec %%M mongosh --quiet --eval "quit(db.adminCommand('ping').ok ? 0 : 1)" >nul 2>&1 && (
        docker update --restart unless-stopped %%M >nul 2>&1
        echo [MONGODB] Reutilizando o container existente %%M.
        exit /b 0
    )
)
docker inspect mongodb >nul 2>&1 && (
    echo [MONGODB] Iniciando o container existente mongodb...
    docker start mongodb >nul || exit /b 1
    docker update --restart unless-stopped mongodb >nul 2>&1
    for /l %%I in (1,1,60) do (
        docker exec mongodb mongosh --quiet --eval "quit(db.adminCommand('ping').ok ? 0 : 1)" >nul 2>&1 && exit /b 0
        timeout /t 2 /nobreak >nul
    )
    echo [ERRO] O container mongodb iniciou, mas nao respondeu ao ping.
    exit /b 1
)
echo [MONGODB] Criando ou iniciando o container...
docker compose up -d mongodb || exit /b 1
echo [MONGODB] Aguardando ficar saudavel...
for /l %%I in (1,1,60) do (
    for /f %%S in ('docker inspect --format "{{.State.Health.Status}}" noobsquad-mongodb 2^>nul') do (
        if /i "%%S"=="healthy" exit /b 0
    )
    timeout /t 2 /nobreak >nul
)
echo [ERRO] MongoDB nao ficou saudavel em 120 segundos.
docker compose logs --tail 30 mongodb
exit /b 1

:ensure_mediamtx
echo [STREAM] Iniciando o servidor MediaMTX...
docker compose up -d mediamtx || (
    echo [ERRO] Nao foi possivel iniciar o MediaMTX.
    exit /b 1
)
findstr /r /c:"^STREAM_DOMAIN=." .env >nul 2>&1
if not errorlevel 1 (
    echo [STREAM] Iniciando o proxy HTTPS do Caddy...
    docker compose up -d caddy || (
        echo [ERRO] Nao foi possivel iniciar o Caddy.
        exit /b 1
    )
)
exit /b 0

:start_docker_desktop
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    echo [DOCKER] Iniciando Docker Desktop...
    start "" /min "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    for /l %%I in (1,1,60) do (
        docker info >nul 2>&1 && exit /b 0
        timeout /t 2 /nobreak >nul
    )
)
exit /b 1
