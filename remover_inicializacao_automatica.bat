@echo off
schtasks /Delete /F /TN "NoobSquad Discord Bot"
if errorlevel 1 exit /b 1
echo Tarefa de inicializacao removida.
pause
