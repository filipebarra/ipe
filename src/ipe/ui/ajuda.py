"""Menu Ajuda: o guia do usuário em PDF e uma janela "Sobre" curta.

Até a 0.74 o F1 abria uma caixa com o texto da 0.13 — 4.400 pixels de altura, maior que qualquer
tela, e o guia em PDF não ia junto com o programa. Agora o guia viaja dentro do pacote
(`ipe/ajuda`) e o F1 o abre no leitor de PDF do sistema.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from ipe import APP_NAME, NOT_FOR_DIAGNOSIS, __version__

GUIA = "Ipe-guia-do-usuario.pdf"


def caminho_do_guia() -> Path | None:
    """Onde está o guia: dentro do pacote; no executável, na pasta de dados do PyInstaller; e,
    rodando do código-fonte, também em `docs/` na raiz do projeto."""
    aqui = Path(__file__).resolve().parent.parent          # .../ipe
    lugares = [aqui / "ajuda" / GUIA]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        lugares.append(Path(base) / "ipe" / "ajuda" / GUIA)
    lugares.append(aqui.parent.parent / "docs" / GUIA)       # raiz do projeto, rodando do fonte
    for p in lugares:
        if p.is_file():
            return p
    return None


def abrir_guia(parent: QWidget | None = None, abrir=None) -> bool:
    """Abre o guia no leitor de PDF do sistema. Se não der, diz por quê e onde procurar."""
    abrir = abrir or QDesktopServices.openUrl
    p = caminho_do_guia()
    if p is None:
        QMessageBox.warning(parent, "Guia do usuário",
                            f"O guia do usuário ({GUIA}) não foi encontrado junto do programa. "
                            "Reinstale o programa ou peça o arquivo a quem o instalou.")
        return False
    if not abrir(QUrl.fromLocalFile(str(p))):
        QMessageBox.warning(parent, "Guia do usuário",
                            "Não foi possível abrir o leitor de PDF deste computador. "
                            f"O guia está em:\n{p}")
        return False
    return True


def texto_sobre() -> str:
    return (f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Visualizador DICOM para pesquisa e ensino.</p>"
            f"<p><b>{NOT_FOR_DIAGNOSIS}.</b></p>"
            "<p>Como usar: <b>Ajuda ▸ Guia do usuário</b> (F1).<br>"
            "Atalhos de teclado: <b>Preferências ▸ Atalhos de teclado</b>.</p>"
            "<p>Bibliotecas: PySide6 (Qt), pydicom, pylibjpeg, NumPy, SQLAlchemy.</p>")


def mostrar_sobre(parent: QWidget | None = None) -> None:
    QMessageBox.about(parent, f"Sobre o {APP_NAME}", texto_sobre())
