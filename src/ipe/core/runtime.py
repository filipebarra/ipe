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
