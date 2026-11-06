@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Ipe - gerar o pacote
cd /d "%~dp0.."
echo === Ipe: gerar o pacote e o instalador ===
echo Pasta: %CD%
echo.

rem --- achar o Python (nao precisa de administrador) --------------------------
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE (where python >nul 2>nul && set "PYEXE=python")
if not defined PYEXE (
  echo [ERRO] Python nao encontrado neste computador.
  echo Instale o Python 3.12 de https://www.python.org/downloads/
  echo e marque "Add python.exe to PATH". Nao precisa de administrador:
  echo na tela do instalador do Python escolha "Install for me only".
  goto :fim
)
%PYEXE% --version
echo.

rem --- ambiente so para empacotar, separado do .venv de desenvolvimento -------
if not exist ".venv-build\Scripts\python.exe" (
  echo Criando o ambiente de empacotamento...
  %PYEXE% -m venv .venv-build
)
if not exist ".venv-build\Scripts\python.exe" (
  echo [ERRO] Falha ao criar o ambiente de empacotamento.
  goto :fim
)
set "PY=.venv-build\Scripts\python.exe"

echo Instalando as bibliotecas (demora na primeira vez)...
"%PY%" -m pip install --upgrade pip >nul
"%PY%" -m pip install -e ".[ia]" "pyinstaller>=6.0"
if errorlevel 1 (
  echo [ERRO] Erro instalando as bibliotecas. Veja as mensagens acima.
  goto :fim
)

rem --- versao, lida do proprio programa --------------------------------------
rem O `for /f` do cmd quebra quando o comando comeca com aspas: gravar e ler e imune.
set "VARQ=%TEMP%\ipe_versao.txt"
"%PY%" -c "import ipe,sys;sys.stdout.write(ipe.__version__)" > "%VARQ%"
set "VERSAO="
if exist "%VARQ%" set /p VERSAO=<"%VARQ%"
del "%VARQ%" 2>nul
if not defined VERSAO (
  echo [ERRO] Nao consegui ler a versao de src\ipe\__init__.py
  goto :fim
)
echo.
echo Versao: %VERSAO%
echo.

rem --- tirar os pacotes antigos da frente -------------------------------------
rem Pacote velho na mesma pasta e armadilha: foi assim que se rodou um instalador 0.35
rem achando que era o novo. Eles nao sao apagados, so saem do caminho.
if not exist "dist\antigos" mkdir "dist\antigos" 2>nul
for %%F in ("dist\Ipe-*-installer.exe" "dist\Ipe-*-portable.zip" "dist\Ipe-*-instalador.exe" "dist\Ipe-*-portatil.zip") do (
  if exist "%%~fF" move /y "%%~fF" "dist\antigos\" >nul && echo Guardado em dist\antigos: %%~nxF
)

rem --- icone -----------------------------------------------------------------
"%PY%" installer\make_icon.py
if errorlevel 1 ( echo [ERRO] Falha ao gerar o icone. & goto :fim )

rem --- empacotar -------------------------------------------------------------
echo.
echo Empacotando (alguns minutos)...
rmdir /s /q build-pyi 2>nul
rmdir /s /q dist\Ipe 2>nul
"%PY%" -m PyInstaller --noconfirm --clean --workpath build-pyi --distpath dist installer\ipe.spec
if errorlevel 1 ( echo [ERRO] Falha no empacotamento. & goto :fim )

rem --- conferir que o pacote abre --------------------------------------------
echo.
echo Conferindo o pacote...
"%PY%" installer\verifica.py
set "CONF=%ERRORLEVEL%"
set "CONFERIDO=sim"
if "%CONF%"=="2" (
  rem Bloqueio do Windows nao e defeito do pacote: gerar assim mesmo, dizendo que nao foi conferido.
  set "CONFERIDO=nao"
  echo.
  echo [AVISO] Nao foi possivel conferir: o Windows bloqueou o executavel recem-gerado.
  echo         O pacote vai ser gerado assim mesmo, SEM conferencia.
  echo         Leia: %CD%\dist\conferencia.txt
) else if not "%CONF%"=="0" (
  echo [ERRO] O pacote nao passou na conferencia. Nada foi gerado.
  echo        O motivo esta em: %CD%\dist\conferencia.txt
  goto :fim
)

rem --- ZIP portatil (sempre) --------------------------------------------------
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Ipe\*' -DestinationPath 'dist\Ipe-%VERSAO%-windows-portable.zip' -Force"
echo Pacote portatil: dist\Ipe-%VERSAO%-windows-portable.zip

rem --- instalador (se o Inno Setup estiver instalado) -------------------------
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo.
  echo Inno Setup 6 nao encontrado: parei no pacote portatil.
  echo Para gerar o instalador, instale de https://jrsoftware.org/isdl.php e rode de novo.
) else (
  "%ISCC%" /DVersao=%VERSAO% installer\ipe.iss
  if errorlevel 1 ( echo [ERRO] Falha ao gerar o instalador. & goto :fim )
  echo Instalador: dist\Ipe-%VERSAO%-installer.exe
)

rem --- dizer, em letras grandes, qual arquivo e o novo -------------------------
echo.
echo ============================================================
echo  PRONTO - versao %VERSAO%
echo ------------------------------------------------------------
if defined ISCC (
  echo  Instale executando ESTE arquivo:
  echo     %CD%\dist\Ipe-%VERSAO%-installer.exe
) else (
  echo  Sem Inno Setup: saiu so o pacote portatil.
  echo     %CD%\dist\Ipe-%VERSAO%-windows-portable.zip
)
if "%CONFERIDO%"=="nao" (
  echo  ATENCAO: o pacote NAO foi conferido - o Windows bloqueou o executavel.
  echo           Teste a mao antes de instalar em outro computador.
)
if exist "modelos\densidade_nyu.onnx" (
  echo  A rede de densidade foi junto no pacote.
) else (
  echo  Sem modelo em modelos\: a rede de densidade nao vai no pacote.
)
echo  Pacotes de versoes anteriores, se havia, estao em dist\antigos.
echo ============================================================

:fim
echo.
pause
