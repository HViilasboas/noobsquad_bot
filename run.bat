@echo off
setlocal

REM Adiciona o diretório atual ao PYTHONPATH
set PYTHONPATH=%CD%

REM Ativa o ambiente virtual
call .venv\Scripts\activate.bat

REM Executa o bot
python bot/main.py

REM Se o bot parar, aguarda 5 segundos e reinicia
timeout /t 5
goto :start
