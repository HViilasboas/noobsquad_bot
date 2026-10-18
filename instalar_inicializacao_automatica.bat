@echo off
setlocal
cd /d "%~dp0"

echo Criando tarefa de inicializacao automatica do NoobSquad Bot...
schtasks /Create /F /SC ONLOGON /RL HIGHEST /TN "NoobSquad Discord Bot" /TR "\"%~dp0run.bat\""
if errorlevel 1 (
    echo.
    echo [ERRO] Execute este arquivo como Administrador e tente novamente.
    pause
    exit /b 1
)

echo.
echo Tarefa instalada. Docker, MongoDB e bot iniciarao no proximo logon.
echo Para iniciar agora, execute run.bat.
pause
