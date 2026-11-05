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

rem 0.99.69: variaveis do sistema que apontam para outro Python (um Python 3.5 antigo, um
rem programa que instalou o Python dele) fazem QUALQUER Python quebrar ao abrir
rem ("No module named 'encodings'"). Aqui elas nao valem.
if defined PYTHONHOME echo Aviso: o Windows tem PYTHONHOME=!PYTHONHOME! ^(ignorado aqui; ele quebra outros Pythons^)
if defined PYTHONPATH echo Aviso: o Windows tem PYTHONPATH=!PYTHONPATH! ^(ignorado aqui^)
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "PYTHONEXECUTABLE="
set "VIRTUAL_ENV="
set "CONDA_PREFIX="

echo Pythons deste computador:
where python 2>nul
py -0p 2>nul
echo.

rem --- achar um Python que sirva (3.10 a 3.13) ------------------------------------
rem 0.99.7: um PC com o Python 3.5 no PATH fazia o instalador usar o 3.5, que o PyTorch
rem e o TotalSegmentator nao aceitam. So serve 3.10-3.13; se nao houver, o instalador
rem baixa um Python 3.12 so para a segmentacao (pelo "uv"), sem mexer no Python do PC.
rem 0.99.69: o teste agora exige que o Python ABRA de verdade e responda (um Python quebrado
rem ou o atalho da Microsoft Store nao contam).
if not exist "%BASE%" mkdir "%BASE%"
set "SONDA=%BASE%\sonda_python.py"
> "%SONDA%" echo import sys, encodings
>> "%SONDA%" echo print("IPE_PY_OK" if (3, 10) ^<= sys.version_info[:2] ^<= (3, 13) else "IPE_PY_VELHO")
set "PYEXE="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PYEXE call :testa py -%%V
)
if not defined PYEXE call :testa python
if not defined PYEXE call :testa python3
if not defined PYEXE (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%ProgramFiles(x86)%\Python3*" "C:\Python3*" "%USERPROFILE%\AppData\Local\Programs\Python\Python3*") do (
    if not defined PYEXE if exist "%%~D\python.exe" call :testa "%%~D\python.exe"
  )
)
if defined PYEXE (
  echo Python que vai ser usado:
  %PYEXE% --version
) else (
  echo Nenhum Python 3.10 a 3.13 que funcione neste computador.
)
echo.

rem ambiente que existe mas nao abre (Python antigo, ou o Python de onde ele veio sumiu): apaga e refaz
if exist "%VENV%" (
  call :venv_ok
  if not defined VENV_OK (
    echo O ambiente que existia nao funciona ^(Python antigo, quebrado ou incompleto^): apagando e refazendo.
    call :apagar_venv
    if exist "%VENV%" goto :fim
  )
)

if not exist "%VENV%\Scripts\python.exe" (
  if defined PYEXE (
    echo Criando o ambiente...
    %PYEXE% -m venv "%VENV%"
    call :venv_ok
    if not defined VENV_OK (
      echo O ambiente criado com esse Python nao abriu. Tentando com um Python proprio da segmentacao.
      call :apagar_venv
      if exist "%VENV%" goto :fim
    )
  )
)
if not exist "%VENV%\Scripts\python.exe" (
  echo Baixando um Python 3.12 so para a segmentacao, dentro de %BASE%
  echo ^(o Python do computador nao e tocado^)...
  call :python_proprio
)
call :venv_ok
if not defined VENV_OK (
  echo [ERRO] Nao consegui criar um ambiente que funcione em %VENV%
  echo        Instale o Python 3.12 de https://www.python.org/downloads/ ^(marque "Add python.exe to PATH"^)
  echo        e rode este instalador de novo.
  goto :fim
)
set "PY=%VENV%\Scripts\python.exe"
"%PY%" --version
"%PY%" -m pip install --upgrade pip >nul

echo.
echo [1/3] PyTorch (versao para CPU)...
"%PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
  echo [ERRO] Falha instalando o PyTorch.
  echo        Se for a rede ^(mensagens com "connection", "timeout", "SSL" ou "proxy"^): libere
  echo        download.pytorch.org, pypi.org e files.pythonhosted.org, ou rode de outra rede.
  goto :fim
)

echo.
echo [2/3] TotalSegmentator...
"%PY%" -m pip install "TotalSegmentator>=2.18"
if errorlevel 1 ( echo [ERRO] Falha instalando o TotalSegmentator. & goto :fim )
if not exist "%VENV%\Scripts\totalseg_download_weights.exe" (
  echo [ERRO] O TotalSegmentator nao ficou instalado ^(falta o totalseg_download_weights^). Veja as mensagens acima.
  goto :fim
)

echo.
echo [3/3] Modelos: orgaos abdominais (TC e RM), segmentos do figado, coluna (vertebras e discos) e cabeca/pescoco (cefalometria)...
for %%T in (total_fast total_fast_mr liver_segments liver_segments_mr vertebrae_mr vertebrae_body total_mr head_glands_cavities headneck_bones_vessels craniofacial_structures head_muscles headneck_muscles total lung_nodules trunk_cavities) do (
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

rem --- serve? (Python 3.10 a 3.13, e abre de verdade). Uso: call :testa comando do python ----------
rem o Python tem que RESPONDER a sonda; um Python quebrado, o atalho da Microsoft Store ou um
rem comando que nao existe nao respondem
:testa
set "T_OK="
for /f "usebackq delims=" %%O in (`call %* "%SONDA%" 2^>nul`) do if "%%O"=="IPE_PY_OK" set "T_OK=1"
if defined T_OK set "PYEXE=%*"
goto :eof

rem --- o ambiente da segmentacao abre? -------------------------------------------------
:venv_ok
set "VENV_OK="
if not exist "%VENV%\Scripts\python.exe" goto :eof
for /f "usebackq delims=" %%O in (`call "%VENV%\Scripts\python.exe" "%SONDA%" 2^>nul`) do if "%%O"=="IPE_PY_OK" set "VENV_OK=1"
goto :eof

rem --- apagar o ambiente (e, se nao der, tirar do caminho) ------------------------------
:apagar_venv
rmdir /s /q "%VENV%" 2>nul
if exist "%VENV%" (
  set "VELHO=venv_velho_%RANDOM%"
  ren "%VENV%" "!VELHO!" 2>nul
  if not exist "%VENV%" echo   ^(nao deu para apagar; ficou em %BASE%\!VELHO! - apague depois^)
)
if exist "%VENV%" (
  echo [ERRO] Nao consegui apagar nem renomear %VENV%
  echo        Feche o Ipe ^(e qualquer segmentacao em andamento^), apague essa pasta e rode de novo.
)
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
