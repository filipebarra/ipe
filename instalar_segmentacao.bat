@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Ipe - instalar a segmentacao (TotalSegmentator)
echo === Ipe: segmentacao (TotalSegmentator) ===
echo.
echo Isto roda UMA vez. Cria um ambiente Python separado do programa, com o PyTorch
echo (so CPU) e o TotalSegmentator, e baixa os modelos (orgaos abdominais, coluna, cabeca/pescoco e encefalo).
echo Precisa de internet e de uns 5 GB livres. Demora (10 a 30 minutos).
echo.

set "BASE=%LOCALAPPDATA%\DicomViewer\segmentacao"
set "VENV=%BASE%\venv"
set "TOTALSEG_HOME_DIR=%BASE%\pesos"
echo Pasta: %BASE%
echo.

rem --- achar um Python que sirva (3.10 a 3.13) ------------------------------------
rem 0.99.7: um PC com o Python 3.5 no PATH fazia o instalador usar o 3.5, que o PyTorch
rem e o TotalSegmentator nao aceitam. Agora so serve 3.10-3.13; se nao houver, o instalador
rem baixa um Python 3.12 so para a segmentacao (pelo "uv"), sem mexer no Python do PC.
set "PYEXE="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PYEXE (
    py -%%V -c "import sys" >nul 2>nul && set "PYEXE=py -%%V"
  )
)
if not defined PYEXE call :testa python
if not defined PYEXE call :testa python3
if not defined PYEXE (
  for %%D in ("%LOCALAPPDATA%\Programs\Python\Python312" "%LOCALAPPDATA%\Programs\Python\Python311" "%LOCALAPPDATA%\Programs\Python\Python313" "%LOCALAPPDATA%\Programs\Python\Python310" "%ProgramFiles%\Python312" "%ProgramFiles%\Python311" "%ProgramFiles%\Python313" "%ProgramFiles%\Python310") do (
    if not defined PYEXE if exist "%%~D\python.exe" call :testa "%%~D\python.exe"
  )
)

rem ambiente antigo criado com um Python que nao serve: apaga e refaz
if exist "%VENV%\Scripts\python.exe" (
  "%VENV%\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo O ambiente que existia foi criado com um Python antigo: refazendo.
    rmdir /s /q "%VENV%"
  )
)

rem ambiente incompleto (instalacao interrompida, ou apagado pela metade): apaga antes de refazer
if exist "%VENV%" if not exist "%VENV%\Scripts\python.exe" (
  echo O ambiente que existia estava incompleto: apagando e refazendo.
  rmdir /s /q "%VENV%" 2>nul
  if exist "%VENV%" (
    echo [ERRO] Nao consegui apagar %VENV%
    echo        Feche o Ipe ^(e qualquer segmentacao em andamento^), apague essa pasta e rode de novo.
    goto :fim
  )
)

if not exist "%VENV%\Scripts\python.exe" (
  if defined PYEXE (
    echo Python encontrado:
    %PYEXE% --version
    echo Criando o ambiente...
    %PYEXE% -m venv "%VENV%"
  ) else (
    echo Nenhum Python 3.10 a 3.13 neste computador. Baixando um Python 3.12 so para a
    echo segmentacao, dentro de %BASE% ^(o Python do computador nao e tocado^)...
    call :python_proprio
  )
)
if not exist "%VENV%\Scripts\python.exe" (
  echo [ERRO] Nao consegui criar o ambiente em %VENV%
  echo        Instale o Python 3.12 de https://www.python.org/downloads/ e rode de novo.
  goto :fim
)
set "PY=%VENV%\Scripts\python.exe"
"%PY%" --version
"%PY%" -m pip install --upgrade pip >nul

echo.
echo [1/3] PyTorch (versao para CPU)...
"%PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 ( echo [ERRO] Falha instalando o PyTorch. & goto :fim )

echo.
echo [2/3] TotalSegmentator...
"%PY%" -m pip install "TotalSegmentator>=2.18"
if errorlevel 1 ( echo [ERRO] Falha instalando o TotalSegmentator. & goto :fim )

echo.
echo [3/3] Modelos: orgaos abdominais (TC e RM), segmentos do figado, coluna (vertebras e discos) e cabeca/pescoco (cefalometria)...
for %%T in (total_fast total_fast_mr liver_segments liver_segments_mr vertebrae_mr vertebrae_body total_mr head_glands_cavities headneck_bones_vessels craniofacial_structures head_muscles headneck_muscles) do (
  echo   - %%T
  "%VENV%\Scripts\totalseg_download_weights.exe" -t %%T
  if errorlevel 1 ( echo [ERRO] Falha baixando o modelo %%T. & goto :fim )
)

echo.
echo [extra] SynthSeg (encefalo: Evans, 3o ventriculo, angulo calosal, hipocampos), pela DIPY...
"%PY%" -m pip install "dipy>=1.12"
if errorlevel 1 ( echo [ERRO] Falha instalando a DIPY. & goto :fim )
set "DIPY_HOME=%BASE%\pesos\dipy"
"%PY%" -c "from dipy.data import get_fnames; print(get_fnames(name='synthseg_torch_weights'))"
if errorlevel 1 ( echo [ERRO] Falha baixando os pesos do SynthSeg. & goto :fim )

echo.
echo Conferindo...
"%PY%" -c "import torch, totalsegmentator; from importlib.metadata import version; import dipy; print('PyTorch', torch.__version__, '- TotalSegmentator', version('TotalSegmentator'), '- DIPY', dipy.__version__)"
if errorlevel 1 ( echo [ERRO] O ambiente nao abriu. & goto :fim )
echo.
echo Pronto. No Ipe: botao direito numa serie de TC ou RM
echo ^> "Segmentar orgaos abdominais" ou "Identificar vertebras e discos".
echo (O modo completo da TC, mais lento, baixa o modelo dele na primeira vez que for usado.)

:fim
echo.
pause
exit /b

rem --- serve? (Python 3.10 a 3.13) ---------------------------------------------------
:testa
"%~1" -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul
if not errorlevel 1 set "PYEXE="%~1""
goto :eof

rem --- sem Python que sirva: um 3.12 proprio, baixado pelo uv (astral.sh) -----------------
:python_proprio
set "UVDIR=%BASE%\uv"
set "UVEXE="
if exist "%UVDIR%\uv.exe" set "UVEXE=%UVDIR%\uv.exe"
if not defined UVEXE (
  if not exist "%UVDIR%" mkdir "%UVDIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile '%UVDIR%\uv.zip'; Expand-Archive -Force '%UVDIR%\uv.zip' '%UVDIR%'"
  for /r "%UVDIR%" %%F in (uv.exe) do if exist "%%F" set "UVEXE=%%F"
)
if not defined UVEXE (
  echo [ERRO] Nao consegui baixar o uv ^(github.com bloqueado?^).
  goto :eof
)
set "UV_PYTHON_INSTALL_DIR=%BASE%\python"
"%UVEXE%" venv --clear --python 3.12 --seed "%VENV%"
goto :eof
