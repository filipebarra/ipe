@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Rode instalar.bat primeiro.
  pause
  exit /b 1
)
rem Servidor central sem janela. Na primeira vez: servidor.bat --create-admin admin
rem o pacote mudou de nome na 0.99.11 (dicomviewer -> ipe): assim abre mesmo antes de reinstalar
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
".venv\Scripts\python.exe" -m ipe server %*
pause
