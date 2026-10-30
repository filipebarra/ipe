@echo off
chcp 65001 >nul
title Ipe - conferir o pacote ja gerado
cd /d "%~dp0.."
if not exist ".venv-build\Scripts\python.exe" (
  echo [ERRO] Nao existe o ambiente de empacotamento. Rode installer\build_windows.bat antes.
  goto :fim
)
".venv-build\Scripts\python.exe" installer\verifica.py
echo.
echo O relato completo esta em: %CD%\dist\conferencia.txt
:fim
echo.
pause
