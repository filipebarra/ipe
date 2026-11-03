@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Ipê: installation ===
echo Language / Idioma:  1) English (default)   2) Português (Brasil)   3) Español
set "OP="
set /p "OP=[1] "
set "LANG_IPE=en"
if "%OP%"=="2" set "LANG_IPE=pt-BR"
if "%OP%"=="3" set "LANG_IPE=es"
where py >nul 2>nul
if errorlevel 1 (
  echo Python not found / Python nao encontrado / Python no encontrado.
  echo Install Python 3.12 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH". Then run this file again.
  pause
  exit /b 1
)
if not exist .venv (
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo Could not create the virtual environment.
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
if errorlevel 1 (
  echo Error installing the libraries. See the messages above.
  pause
  exit /b 1
)
.venv\Scripts\python -m ipe set-language %LANG_IPE%
.venv\Scripts\python -m ipe register-url
echo.
if "%LANG_IPE%"=="pt-BR" (
  echo Instalacao concluida. Use executar.bat para abrir o programa.
) else if "%LANG_IPE%"=="es" (
  echo Instalacion terminada. Use executar.bat para abrir el programa.
) else (
  echo Installation complete. Run executar.bat to open the program.
)
pause
