@echo off
setlocal

:start
echo Iniciando rotina de manutencao...
if exist ".venv" (
    echo Removendo ambiente virtual...
    rmdir /s /q ".venv"
)

echo Criando novo ambiente virtual...
python -m venv .venv

echo Ativando e instalando dependencias...
call .venv\Scripts\activate
pip install -r requirements.txt

echo Iniciando o bot...
start /b python main.py
set BOT_PID=%!
echo Bot iniciado com PID: %BOT_PID%!

:monitor
if exist "reboot.flag" (
    echo Sinal de reinicializacao detectado.
    del reboot.flag
    taskkill /pid %BOT_PID%
    timeout /t 5 > nul
    goto start
)
timeout /t 5 > nul
goto monitor

endlocal
pause