@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Ipe - TotalSegmentator

set "BASE=%LOCALAPPDATA%\DicomViewer\segmentacao"
set "VENV=%BASE%\venv"
set "TOTALSEG_HOME_DIR=%BASE%\pesos"

rem 0.100.13: as mensagens no idioma do Ipe (o programa passa IPE_LANG ao abrir este instalador; tambem
rem aceita "instalar_segmentacao.bat en"). Sem idioma: portugues.
set "L=pt"
if not "%~1"=="" set "IPE_LANG=%~1"
if defined IPE_LANG (
  set "LC=!IPE_LANG:~0,2!"
  if /i "!LC!"=="en" set "L=en"
  if /i "!LC!"=="es" set "L=es"
)
call :textos_%L%

echo === Ipe: !M_TITULO! ===
echo.
echo !M_INTRO1!
echo !M_INTRO2!
echo !M_INTRO3!
echo.
echo !M_PASTA! %BASE%
echo.

rem 0.99.69: variaveis do sistema que apontam para outro Python (um Python 3.5 antigo, um
rem programa que instalou o Python dele) fazem QUALQUER Python quebrar ao abrir
rem ("No module named 'encodings'"). Aqui elas nao valem.
if defined PYTHONHOME echo !M_AVISO_HOME! PYTHONHOME=!PYTHONHOME!
if defined PYTHONPATH echo !M_AVISO_HOME! PYTHONPATH=!PYTHONPATH!
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "PYTHONEXECUTABLE="
set "VIRTUAL_ENV="
set "CONDA_PREFIX="

echo !M_PYTHONS!
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
  echo !M_PY_USADO!
  %PYEXE% --version
) else (
  echo !M_SEM_PY!
)
echo.

rem ambiente que existe mas nao abre (Python antigo, ou o Python de onde ele veio sumiu): apaga e refaz
if exist "%VENV%" (
  call :venv_ok
  if not defined VENV_OK (
    echo !M_VENV_RUIM!
    call :apagar_venv
    if exist "%VENV%" goto :fim
  )
)

if not exist "%VENV%\Scripts\python.exe" (
  if defined PYEXE (
    echo !M_CRIANDO!
    %PYEXE% -m venv "%VENV%"
    call :venv_ok
    if not defined VENV_OK (
      echo !M_VENV_NAO_ABRIU!
      call :apagar_venv
      if exist "%VENV%" goto :fim
    )
  )
)
if not exist "%VENV%\Scripts\python.exe" (
  echo !M_BAIXANDO_PY! %BASE%
  echo !M_PY_INTOCADO!
  call :python_proprio
)
call :venv_ok
if not defined VENV_OK (
  echo [ERRO] !M_ERRO_VENV! %VENV%
  echo        !M_ERRO_VENV2!
  echo        !M_ERRO_VENV3!
  goto :fim
)
set "PY=%VENV%\Scripts\python.exe"
"%PY%" --version
"%PY%" -m pip install --upgrade pip >nul

echo.
echo [1/3] PyTorch (CPU)...
"%PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
  echo [ERRO] !M_ERRO_TORCH!
  echo        !M_ERRO_REDE1!
  echo        !M_ERRO_REDE2!
  goto :fim
)

rem 0.99.71: o PyTorch do Windows precisa do "Microsoft Visual C++ Redistributable" (2015-2022, x64). Sem
rem ele, "import torch" falha com "WinError 126 ... shm.dll or one of its dependencies" (Windows Server e
rem Windows recem-instalados). Confere aqui e, faltando, baixa e instala o da Microsoft.
echo !M_CONF_TORCH!
"%PY%" -c "import torch" >nul 2>&1
if errorlevel 1 (
  echo !M_TORCH_NAO_ABRIU!
  call :vcredist
  "%PY%" -c "import torch" >nul 2>&1
  if errorlevel 1 (
    echo.
    echo [ERRO] !M_TORCH_CONTINUA!
    "%PY%" -c "import torch"
    echo.
    echo        !M_VCR_MANUAL1! https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo        !M_VCR_MANUAL2!
    goto :fim
  )
)
echo PyTorch ok.
echo.
echo [2/3] TotalSegmentator...
"%PY%" -m pip install "TotalSegmentator>=2.18"
if errorlevel 1 ( echo [ERRO] !M_ERRO_TS! & goto :fim )
if not exist "%VENV%\Scripts\totalseg_download_weights.exe" (
  echo [ERRO] !M_ERRO_TS_PESOS!
  goto :fim
)

echo.
echo [3/3] !M_MODELOS!
for %%T in (total_fast total_fast_mr liver_segments liver_segments_mr vertebrae_mr vertebrae_body total_mr head_glands_cavities headneck_bones_vessels craniofacial_structures head_muscles headneck_muscles total lung_nodules trunk_cavities) do (
  echo   - %%T
  "%VENV%\Scripts\totalseg_download_weights.exe" -t %%T
  if errorlevel 1 ( echo [ERRO] !M_ERRO_MODELO! %%T & goto :fim )
)

echo.
echo [extra] !M_SYNTHSEG!
"%PY%" -m pip install "dipy>=1.12"
if errorlevel 1 ( echo [ERRO] !M_ERRO_DIPY! & goto :fim )
set "DIPY_HOME=%BASE%\pesos\dipy"
"%PY%" -c "from dipy.data import get_fnames; print(get_fnames(name='synthseg_torch_weights'))"
if errorlevel 1 ( echo [ERRO] !M_ERRO_SYNTHSEG! & goto :fim )

echo.
echo !M_CONFERINDO!
"%PY%" -c "import torch, totalsegmentator; from importlib.metadata import version; import dipy; print('PyTorch', torch.__version__, '- TotalSegmentator', version('TotalSegmentator'), '- DIPY', dipy.__version__)"
if errorlevel 1 ( echo [ERRO] !M_ERRO_FINAL! & goto :fim )
echo.
echo !M_PRONTO1!
echo !M_PRONTO2!
echo !M_PRONTO3!

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
  if not exist "%VENV%" echo   !M_VELHO! %BASE%\!VELHO!
)
if exist "%VENV%" (
  echo [ERRO] !M_ERRO_APAGAR! %VENV%
  echo        !M_ERRO_APAGAR2!
)
goto :eof

rem --- Visual C++ Redistributable (o que o PyTorch precisa no Windows) -------------------
:vcredist
set "VCR=%BASE%\vc_redist.x64.exe"
if not exist "%VCR%" (
  echo !M_VCR_BAIXANDO!
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%VCR%'"
)
if not exist "%VCR%" (
  echo [ERRO] !M_VCR_ERRO!
  goto :eof
)
echo !M_VCR_INSTALANDO!
"%VCR%" /install /passive /norestart
set "VCRC=!errorlevel!"
if "!VCRC!"=="3010" echo   !M_VCR_3010!
if "!VCRC!"=="1638" echo   !M_VCR_1638!
goto :eof

rem --- sem Python que sirva: um 3.12 proprio, baixado pelo uv (astral.sh) -----------------
rem 0.100.13: o uv cria um atalho de pasta (juncao "cpython-3.12-windows-x86_64-none") apontando para o
rem Python de verdade ("cpython-3.12.16-..."). Alguns Windows bloqueiam esse atalho ("os error 448": ponto de
rem montagem nao confiavel) e o "uv venv --python 3.12" quebrava. Agora: o uv so baixa o Python; o atalho e
rem apagado e o ambiente sai do python.exe da pasta de verdade.
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
  echo [ERRO] !M_ERRO_UV!
  goto :eof
)
set "UV_PYTHON_INSTALL_DIR=%BASE%\python"
call :python_real
if not defined PYREAL (
  rem --no-bin: nao poe python3.12.exe na pasta do usuario (uv antigo nao conhece: tenta sem)
  "%UVEXE%" python install 3.12 --no-bin || "%UVEXE%" python install 3.12
  call :python_real
)
if defined PYREAL (
  echo !M_PY_PROPRIO! !PYREAL!
  "!PYREAL!" -m venv "%VENV%"
  call :venv_ok
  if not defined VENV_OK (
    call :apagar_venv
    "%UVEXE%" venv --clear --python "!PYREAL!" --seed "%VENV%"
  )
  goto :eof
)
"%UVEXE%" venv --clear --python 3.12 --seed "%VENV%"
goto :eof

rem o python.exe de verdade do 3.12 baixado pelo uv (nao o atalho), e so se ele abrir
:python_real
set "PYREAL="
for /d %%D in ("%BASE%\python\cpython-3.12-*") do rmdir "%%~D" 2>nul
for /d %%D in ("%BASE%\python\cpython-3.12.*") do (
  if not defined PYREAL if exist "%%~D\python.exe" (
    set "T_OK="
    for /f "usebackq delims=" %%O in (`call "%%~D\python.exe" "%SONDA%" 2^>nul`) do if "%%O"=="IPE_PY_OK" set "T_OK=1"
    if defined T_OK set "PYREAL=%%~D\python.exe"
  )
)
goto :eof

rem --- textos -------------------------------------------------------------------------
:textos_pt
set "M_TITULO=segmentacao (TotalSegmentator)"
set "M_INTRO1=Isto roda UMA vez. Cria um ambiente Python separado do programa, com o PyTorch"
set "M_INTRO2=(so CPU) e o TotalSegmentator, e baixa os modelos (orgaos abdominais, coluna, cabeca/pescoco e encefalo)."
set "M_INTRO3=Precisa de internet e de uns 5 GB livres. Demora (10 a 30 minutos)."
set "M_PASTA=Pasta:"
set "M_AVISO_HOME=Aviso: ignorado aqui (quebra outros Pythons):"
set "M_PYTHONS=Pythons deste computador:"
set "M_PY_USADO=Python que vai ser usado:"
set "M_SEM_PY=Nenhum Python 3.10 a 3.13 que funcione neste computador."
set "M_VENV_RUIM=O ambiente que existia nao funciona (Python antigo, quebrado ou incompleto): apagando e refazendo."
set "M_CRIANDO=Criando o ambiente..."
set "M_VENV_NAO_ABRIU=O ambiente criado com esse Python nao abriu. Tentando com um Python proprio da segmentacao."
set "M_BAIXANDO_PY=Baixando um Python 3.12 so para a segmentacao, dentro de"
set "M_PY_INTOCADO=(o Python do computador nao e tocado)..."
set "M_PY_PROPRIO=Python da segmentacao:"
set "M_ERRO_VENV=Nao consegui criar um ambiente que funcione em"
set "M_ERRO_VENV2=Instale o Python 3.12 de https://www.python.org/downloads/ (marque Add python.exe to PATH)"
set "M_ERRO_VENV3=e rode este instalador de novo."
set "M_ERRO_TORCH=Falha instalando o PyTorch."
set "M_ERRO_REDE1=Se for a rede (mensagens com connection, timeout, SSL ou proxy): libere"
set "M_ERRO_REDE2=download.pytorch.org, pypi.org e files.pythonhosted.org, ou rode de outra rede."
set "M_CONF_TORCH=Conferindo se o PyTorch abre..."
set "M_TORCH_NAO_ABRIU=O PyTorch nao abriu: quase sempre falta o Microsoft Visual C++ Redistributable."
set "M_TORCH_CONTINUA=O PyTorch continua sem abrir. A mensagem dele:"
set "M_VCR_MANUAL1=Instale o Visual C++ Redistributable x64 de"
set "M_VCR_MANUAL2=reinicie o Windows e rode este instalador de novo."
set "M_ERRO_TS=Falha instalando o TotalSegmentator."
set "M_ERRO_TS_PESOS=O TotalSegmentator nao ficou instalado (falta o totalseg_download_weights). Veja as mensagens acima."
set "M_MODELOS=Modelos: orgaos abdominais (TC e RM), segmentos do figado, coluna (vertebras e discos) e cabeca/pescoco (cefalometria)..."
set "M_ERRO_MODELO=Falha baixando o modelo"
set "M_SYNTHSEG=SynthSeg (encefalo: Evans, 3o ventriculo, angulo calosal, hipocampos), pela DIPY..."
set "M_ERRO_DIPY=Falha instalando a DIPY."
set "M_ERRO_SYNTHSEG=Falha baixando os pesos do SynthSeg."
set "M_CONFERINDO=Conferindo..."
set "M_ERRO_FINAL=O ambiente nao abriu."
set "M_PRONTO1=Pronto. No Ipe: botao direito numa serie de TC ou RM"
set "M_PRONTO2=> Segmentar orgaos abdominais ou Identificar vertebras e discos."
set "M_PRONTO3=(O modo completo da TC, mais lento, baixa o modelo dele na primeira vez que for usado.)"
set "M_VELHO=(nao deu para apagar; ficou em outra pasta - apague depois):"
set "M_ERRO_APAGAR=Nao consegui apagar nem renomear"
set "M_ERRO_APAGAR2=Feche o Ipe (e qualquer segmentacao em andamento), apague essa pasta e rode de novo."
set "M_VCR_BAIXANDO=Baixando o Visual C++ Redistributable da Microsoft..."
set "M_VCR_ERRO=Nao consegui baixar o Visual C++ Redistributable (aka.ms bloqueado?)."
set "M_VCR_INSTALANDO=Instalando o Visual C++ Redistributable (o Windows pode pedir permissao de administrador)..."
set "M_VCR_3010=Instalado; o Windows pede reinicio. Se o PyTorch ainda nao abrir, reinicie e rode de novo."
set "M_VCR_1638=Ja havia uma versao igual ou mais nova instalada."
set "M_ERRO_UV=Nao consegui baixar o uv (github.com bloqueado?)."
goto :eof

:textos_en
set "M_TITULO=segmentation (TotalSegmentator)"
set "M_INTRO1=This runs ONCE. It creates a Python environment separate from the program, with PyTorch"
set "M_INTRO2=(CPU only) and TotalSegmentator, and downloads the models (abdominal organs, spine, head/neck and brain)."
set "M_INTRO3=It needs internet and about 5 GB free. It takes a while (10 to 30 minutes)."
set "M_PASTA=Folder:"
set "M_AVISO_HOME=Warning: ignored here (it breaks other Pythons):"
set "M_PYTHONS=Pythons on this computer:"
set "M_PY_USADO=Python that will be used:"
set "M_SEM_PY=No working Python 3.10 to 3.13 on this computer."
set "M_VENV_RUIM=The existing environment does not work (old, broken or incomplete Python): deleting and rebuilding."
set "M_CRIANDO=Creating the environment..."
set "M_VENV_NAO_ABRIU=The environment created with that Python did not start. Trying a Python of the segmentation's own."
set "M_BAIXANDO_PY=Downloading a Python 3.12 just for the segmentation, inside"
set "M_PY_INTOCADO=(the computer's Python is not touched)..."
set "M_PY_PROPRIO=Segmentation Python:"
set "M_ERRO_VENV=Could not create a working environment in"
set "M_ERRO_VENV2=Install Python 3.12 from https://www.python.org/downloads/ (tick Add python.exe to PATH)"
set "M_ERRO_VENV3=and run this installer again."
set "M_ERRO_TORCH=Failed to install PyTorch."
set "M_ERRO_REDE1=If it is the network (messages with connection, timeout, SSL or proxy): allow"
set "M_ERRO_REDE2=download.pytorch.org, pypi.org and files.pythonhosted.org, or run from another network."
set "M_CONF_TORCH=Checking that PyTorch starts..."
set "M_TORCH_NAO_ABRIU=PyTorch did not start: the Microsoft Visual C++ Redistributable is almost always missing."
set "M_TORCH_CONTINUA=PyTorch still does not start. Its message:"
set "M_VCR_MANUAL1=Install the Visual C++ Redistributable x64 from"
set "M_VCR_MANUAL2=restart Windows and run this installer again."
set "M_ERRO_TS=Failed to install TotalSegmentator."
set "M_ERRO_TS_PESOS=TotalSegmentator was not installed (totalseg_download_weights is missing). See the messages above."
set "M_MODELOS=Models: abdominal organs (CT and MR), liver segments, spine (vertebrae and discs) and head/neck (cephalometry)..."
set "M_ERRO_MODELO=Failed to download the model"
set "M_SYNTHSEG=SynthSeg (brain: Evans, 3rd ventricle, callosal angle, hippocampi), through DIPY..."
set "M_ERRO_DIPY=Failed to install DIPY."
set "M_ERRO_SYNTHSEG=Failed to download the SynthSeg weights."
set "M_CONFERINDO=Checking..."
set "M_ERRO_FINAL=The environment did not start."
set "M_PRONTO1=Done. In Ipe: right-click a CT or MR series"
set "M_PRONTO2=> Segment abdominal organs or Identify vertebrae and discs."
set "M_PRONTO3=(The full CT mode, slower, downloads its model the first time it is used.)"
set "M_VELHO=(could not delete it; it was moved aside - delete it later):"
set "M_ERRO_APAGAR=Could not delete or rename"
set "M_ERRO_APAGAR2=Close Ipe (and any running segmentation), delete that folder and run again."
set "M_VCR_BAIXANDO=Downloading the Microsoft Visual C++ Redistributable..."
set "M_VCR_ERRO=Could not download the Visual C++ Redistributable (aka.ms blocked?)."
set "M_VCR_INSTALANDO=Installing the Visual C++ Redistributable (Windows may ask for administrator permission)..."
set "M_VCR_3010=Installed; Windows asks for a restart. If PyTorch still does not start, restart and run again."
set "M_VCR_1638=The same or a newer version was already installed."
set "M_ERRO_UV=Could not download uv (github.com blocked?)."
goto :eof

:textos_es
set "M_TITULO=segmentacion (TotalSegmentator)"
set "M_INTRO1=Esto se ejecuta UNA vez. Crea un entorno de Python separado del programa, con PyTorch"
set "M_INTRO2=(solo CPU) y TotalSegmentator, y descarga los modelos (organos abdominales, columna, cabeza/cuello y encefalo)."
set "M_INTRO3=Necesita internet y unos 5 GB libres. Tarda (10 a 30 minutos)."
set "M_PASTA=Carpeta:"
set "M_AVISO_HOME=Aviso: ignorado aqui (rompe otros Pythons):"
set "M_PYTHONS=Pythons de este equipo:"
set "M_PY_USADO=Python que se va a usar:"
set "M_SEM_PY=Ningun Python 3.10 a 3.13 que funcione en este equipo."
set "M_VENV_RUIM=El entorno que existia no funciona (Python viejo, roto o incompleto): borrando y rehaciendo."
set "M_CRIANDO=Creando el entorno..."
set "M_VENV_NAO_ABRIU=El entorno creado con ese Python no abrio. Probando con un Python propio de la segmentacion."
set "M_BAIXANDO_PY=Descargando un Python 3.12 solo para la segmentacion, dentro de"
set "M_PY_INTOCADO=(el Python del equipo no se toca)..."
set "M_PY_PROPRIO=Python de la segmentacion:"
set "M_ERRO_VENV=No pude crear un entorno que funcione en"
set "M_ERRO_VENV2=Instale Python 3.12 desde https://www.python.org/downloads/ (marque Add python.exe to PATH)"
set "M_ERRO_VENV3=y ejecute este instalador de nuevo."
set "M_ERRO_TORCH=Fallo al instalar PyTorch."
set "M_ERRO_REDE1=Si es la red (mensajes con connection, timeout, SSL o proxy): permita"
set "M_ERRO_REDE2=download.pytorch.org, pypi.org y files.pythonhosted.org, o ejecute desde otra red."
set "M_CONF_TORCH=Comprobando que PyTorch abre..."
set "M_TORCH_NAO_ABRIU=PyTorch no abrio: casi siempre falta el Microsoft Visual C++ Redistributable."
set "M_TORCH_CONTINUA=PyTorch sigue sin abrir. Su mensaje:"
set "M_VCR_MANUAL1=Instale el Visual C++ Redistributable x64 desde"
set "M_VCR_MANUAL2=reinicie Windows y ejecute este instalador de nuevo."
set "M_ERRO_TS=Fallo al instalar TotalSegmentator."
set "M_ERRO_TS_PESOS=TotalSegmentator no quedo instalado (falta totalseg_download_weights). Vea los mensajes de arriba."
set "M_MODELOS=Modelos: organos abdominales (TC y RM), segmentos del higado, columna (vertebras y discos) y cabeza/cuello (cefalometria)..."
set "M_ERRO_MODELO=Fallo al descargar el modelo"
set "M_SYNTHSEG=SynthSeg (encefalo: Evans, 3er ventriculo, angulo calloso, hipocampos), por DIPY..."
set "M_ERRO_DIPY=Fallo al instalar DIPY."
set "M_ERRO_SYNTHSEG=Fallo al descargar los pesos de SynthSeg."
set "M_CONFERINDO=Comprobando..."
set "M_ERRO_FINAL=El entorno no abrio."
set "M_PRONTO1=Listo. En Ipe: clic derecho en una serie de TC o RM"
set "M_PRONTO2=> Segmentar organos abdominales o Identificar vertebras y discos."
set "M_PRONTO3=(El modo completo de TC, mas lento, descarga su modelo la primera vez que se usa.)"
set "M_VELHO=(no se pudo borrar; quedo en otra carpeta - borrela despues):"
set "M_ERRO_APAGAR=No pude borrar ni renombrar"
set "M_ERRO_APAGAR2=Cierre Ipe (y cualquier segmentacion en curso), borre esa carpeta y ejecute de nuevo."
set "M_VCR_BAIXANDO=Descargando el Microsoft Visual C++ Redistributable..."
set "M_VCR_ERRO=No pude descargar el Visual C++ Redistributable (aka.ms bloqueado?)."
set "M_VCR_INSTALANDO=Instalando el Visual C++ Redistributable (Windows puede pedir permiso de administrador)..."
set "M_VCR_3010=Instalado; Windows pide reiniciar. Si PyTorch aun no abre, reinicie y ejecute de nuevo."
set "M_VCR_1638=Ya habia una version igual o mas nueva instalada."
set "M_ERRO_UV=No pude descargar uv (github.com bloqueado?)."
goto :eof
