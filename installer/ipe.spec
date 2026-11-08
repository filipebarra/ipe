# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller: junta o programa e tudo de que ele precisa numa pasta só.

Roda pelo `build_windows.bat`. O resultado é `dist/Ipe/`, que já funciona como
programa portátil — o instalador do Inno Setup só copia essa pasta para o perfil do
usuário e cria os atalhos.
"""
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RAIZ = Path(SPECPATH).resolve().parent          # noqa: F821 - SPECPATH vem do PyInstaller
SRC = RAIZ / "src"
ICONE = RAIZ / "installer" / "ipe.ico"


def versao() -> str:
    texto = (SRC / "ipe" / "__init__.py").read_text(encoding="utf-8")
    achou = re.search(r'__version__\s*=\s*"([^"]+)"', texto)
    return achou.group(1) if achou else "0.0.0"


# --- arquivos que vão junto ------------------------------------------------
# Os idiomas são lidos de `ipe/locale`; o caminho tem que ser o mesmo de dentro
# do pacote, senão `core/i18n.py` não acha (veja `core/runtime.resource_dir`).
datas = [(str(SRC / "ipe" / "locale"), "ipe/locale")]
# o guia do usuário (Ajuda ▸ Guia do usuário, F1)
datas += [(str(SRC / "ipe" / "ajuda"), "ipe/ajuda")]
if (SRC / "ipe" / "web_dist").is_dir():          # 0.99.91: o visualizador web do servidor central
    datas += [(str(SRC / "ipe" / "web_dist"), "ipe/web_dist")]
# o trabalhador do TotalSegmentator (0.98) roda num Python separado: vai como arquivo .py, não
# compilado dentro do pacote — é o ambiente da segmentação que o executa
datas += [(str(SRC / "ipe" / "ai" / "totalseg_worker.py"), "ipe/ai")]
# 0.99.83: o instalador dos modelos extras (MedSAM2, autoPET, BraTS) também roda no Python da segmentação
datas += [(str(SRC / "ipe" / "ai" / "instalar_modelos_extras.py"), "ipe/ai")]
# e o instalador dela, para quem instalou o programa pelo instalador também poder baixá-la uma vez
# (Arquivo ▸ Instalar a segmentação de órgãos). O programa acha em resource_dir().
for _inst in ("instalar_segmentacao.bat", "instalar_segmentacao.sh"):
    if (RAIZ / _inst).exists():
        datas += [(str(RAIZ / _inst), "ipe")]
datas += collect_data_files("pydicom")          # tabelas de UID e de conjuntos de caracteres

# Modelos de IA (hoje só a rede de densidade, 23 MB). Vão **se estiverem na pasta**: quem não
# quiser o peso no instalador é só não pôr o arquivo lá. `ai/densidade_nyu.py` procura em
# `resource_dir()/modelos`, que é para onde isto copia.
MODELOS = RAIZ / "modelos"
if MODELOS.is_dir() and any(MODELOS.glob("*.onnx")):
    datas += [(str(MODELOS), "modelos")]

# --- módulos que só são importados na hora ---------------------------------
# pydicom e pynetdicom escolhem o decodificador em tempo de execução; sem isto o pacote
# abre e só falha quando aparece um arquivo comprimido — que é o pior momento.
hidden = collect_submodules("pydicom") + collect_submodules("pynetdicom")
hidden += ["pylibjpeg", "libjpeg", "openjpeg", "gdcm",
           "pylibjpeg_libjpeg", "pylibjpeg_openjpeg", "jpeg_ls", "pyjpegls", "sqlalchemy.dialects.sqlite"]
try:                                             # 0.99.96: HTJ2K para o visualizador web (sem ele, JPEG-LS)
    import imagecodecs  # noqa: F401
    hidden += ["imagecodecs", "imagecodecs._htj2k", "imagecodecs._shared", "imagecodecs._shared_cython", "imagecodecs._imcd"]
except ImportError:
    pass
try:                                             # opcional: sem ele, a rede de densidade não roda
    import onnxruntime  # noqa: F401
    hidden += collect_submodules("onnxruntime")
    datas += collect_data_files("onnxruntime")
except Exception:                                # noqa: BLE001 - não está instalado: segue sem
    pass
# OCR das folhas de impressão (0.80): os modelos ONNX e o config.yaml moram dentro do pacote
try:
    import rapidocr_onnxruntime  # noqa: F401
    hidden += collect_submodules("rapidocr_onnxruntime")
    datas += collect_data_files("rapidocr_onnxruntime")
except Exception:                                # noqa: BLE001
    pass

# --- o que não precisa ir ---------------------------------------------------
excluir = [
    "tkinter", "unittest", "pytest", "matplotlib", "IPython", "notebook", "pandas",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSpatialAudio",
]

a = Analysis(                                    # noqa: F821
    [str(SRC / "ipe" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    excludes=excluir,
    noarchive=False,
)
pyz = PYZ(a.pure)                                # noqa: F821

exe = EXE(                                       # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Ipe",
    debug=False,
    strip=False,
    upx=False,
    console=False,                               # sem janela preta atrás do programa
    icon=str(ICONE) if ICONE.exists() else None,
    version_info=None,
)
# Segundo executável, de console: no Windows um programa de janela não tem saída padrão,
# e `print` numa saída inexistente derruba o processo. Os comandos de linha
# (info, import, server, register-url) vão por aqui.
exe_cli = EXE(                                   # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ipe-cli",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ICONE) if ICONE.exists() else None,
)
coll = COLLECT(                                  # noqa: F821
    exe, exe_cli, a.binaries, a.datas,
    strip=False, upx=False, name="Ipe",
)
