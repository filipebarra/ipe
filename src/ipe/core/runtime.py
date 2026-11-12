"""Onde o programa está rodando: do código-fonte ou do pacote do instalador.

Empacotado (PyInstaller), `sys.executable` **é** o programa — não existe `-m ipe`,
e a pasta dos arquivos de apoio muda. Tudo o que precisa relançar o programa ou achar um
arquivo que veio junto passa por aqui, para não haver dois jeitos de descobrir a mesma coisa.
"""

from __future__ import annotations

import sys
from pathlib import Path


def frozen() -> bool:
    """O programa está rodando a partir do pacote gerado pelo instalador?"""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Pasta onde estão os arquivos que vieram junto (idiomas, por exemplo)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "ipe"
    return Path(__file__).resolve().parent.parent


def app_exe() -> Path:
    """O executável que abre a interface, sem console no Windows.

    O pacote tem dois: `Ipe.exe` (janela) e `ipe-cli.exe` (linha de
    comando). Quem registra atalho ou link tem que apontar para o de janela, mesmo quando
    quem está rodando é o de console.
    """
    exe = Path(sys.executable)
    if frozen():
        if exe.stem.endswith("-cli"):
            janela = exe.with_name(exe.name.replace("-cli", "").replace("ipe", "Ipe"))
            return janela if janela.exists() else exe
        return exe
    if sys.platform == "win32":
        janela = exe.with_name("pythonw.exe")
        return janela if janela.exists() else exe
    return exe


def app_command(*args: str) -> str:
    """Linha de comando pronta para abrir o programa com esses argumentos.

    Do código-fonte sai `"python.exe" -m ipe <args>`; empacotado, o executável já é
    o programa e o `-m` não existe.
    """
    partes = [f'"{app_exe()}"']
    if not frozen():
        partes += ["-m", "ipe"]
    partes += list(args)
    return " ".join(partes)


def ambiente_do_sistema(env: dict | None = None) -> dict:
    """0.100.22: ambiente para rodar programas de fora (terminal, xdg-open, o Python da segmentação).
    No pacote do Linux, o PyInstaller põe as bibliotecas do Ipê no LD_LIBRARY_PATH; um programa do
    sistema herdava isso e carregava a glib do pacote ("undefined symbol: g_once_init_leave_pointer"
    ao abrir o gnome-terminal). Devolve uma cópia com o valor original (LD_LIBRARY_PATH_ORIG) de volta."""
    import os
    e = dict(os.environ if env is None else env)
    if not frozen() or sys.platform == "win32":
        return e
    for k in ("DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "DYLD_FALLBACK_LIBRARY_PATH"):   # macOS (0.100.24)
        e.pop(k, None)
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        orig = e.pop(k + "_ORIG", None)
        if orig:
            e[k] = orig
        else:
            e.pop(k, None)
    for k in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "GI_TYPELIB_PATH",
              "GIO_MODULE_DIR", "GSETTINGS_SCHEMA_DIR", "GTK_PATH", "GDK_PIXBUF_MODULE_FILE", "PYTHONPATH", "PYTHONHOME"):
        e.pop(k, None)
    return e
