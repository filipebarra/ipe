@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Ipê: instalacao ===
where py >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado.
  echo Instale o Python 3.12 em https://www.python.org/downloads/
  echo e marque a opcao "Add python.exe to PATH". Depois rode este arquivo de novo.
  pause
  exit /b 1
)
if not exist .venv (
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo Falha ao criar o ambiente virtual.
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
if errorlevel 1 (
  echo Erro na instalacao das bibliotecas. Veja as mensagens acima.
  pause
  exit /b 1
)
.venv\Scripts\python -m ipe register-url
echo.
echo Instalacao concluida. Use executar.bat para abrir o programa.
pause
