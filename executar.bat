@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Rode instalar.bat primeiro.
  pause
  exit /b 1
)
rem o pacote mudou de nome na 0.99.11 (dicomviewer -> ipe): assim abre mesmo antes de reinstalar
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
start "" ".venv\Scripts\pythonw.exe" -m ipe %*
