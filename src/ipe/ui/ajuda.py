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
            "<p>O nome vem dos ipês que florescem em Brasília na seca — e de uma coincidência: "
            "<i>ipê</i> também está em Fil<b>ipe</b>. Criado por um radiologista de mama que queria "
            "um OsiriX para Windows e Linux. Código aberto (GPL-3.0), escrito com a ajuda do Claude e "
            "feito sobre bibliotecas abertas.</p>"
            "<p>Como usar: <b>Ajuda ▸ Guia do usuário</b> (F1).</p>")


def caminho_da_historia(idioma: str = "") -> Path | None:
    """A história do Ipê no idioma do programa (pt-BR, en, es), com o português de reserva."""
    if not idioma:
        try:
            from ipe.core import i18n
            idioma = i18n.current()
        except Exception:  # noqa: BLE001
            idioma = "pt-BR"
    aqui = Path(__file__).resolve().parent.parent / "ajuda"
    base = getattr(sys, "_MEIPASS", None)
    pastas = [aqui] + ([Path(base) / "ipe" / "ajuda"] if base else [])
    for nome in (f"historia.{idioma}.md", f"historia.{idioma.split('-')[0]}.md", "historia.pt-BR.md"):
        for pasta in pastas:
            if (pasta / nome).is_file():
                return pasta / nome
    return None


def _janela_de_texto(parent, titulo: str, markdown: str = "", html: str = ""):
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout
    d = QDialog(parent)
    d.setWindowTitle(titulo)
    d.resize(720, 620)
    tb = QTextBrowser()
    tb.setOpenExternalLinks(True)
    if markdown:
        tb.setMarkdown(markdown)
    else:
        tb.setHtml(html)
    bb = QDialogButtonBox(QDialogButtonBox.Close)
    bb.button(QDialogButtonBox.Close).setText("Fechar")
    bb.rejected.connect(d.reject)
    lay = QVBoxLayout(d)
    lay.addWidget(tb)
    lay.addWidget(bb)
    d.texto = tb
    return d


def janela_da_historia(parent=None):
    p = caminho_da_historia()
    texto = p.read_text(encoding="utf-8") if p else "A história do Ipê não foi encontrada junto do programa."
    return _janela_de_texto(parent, "A história do Ipê", markdown=texto)


def janela_de_creditos(parent=None):
    from ipe import creditos
    html = ("<p>O Ipê só existe porque muita gente compartilhou seu trabalho em código aberto. "
            "Ele é distribuído sob a licença GPL-3.0-or-later.</p>" + creditos.html())
    return _janela_de_texto(parent, "Créditos e licenças", html=html)


def janela_sobre(parent=None):
    """Sobre o Ipê: o texto curto e dois botões — a história e os créditos."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
    d = QDialog(parent)
    d.setWindowTitle(f"Sobre o {APP_NAME}")
    texto = QLabel(texto_sobre())
    texto.setWordWrap(True)
    texto.setTextFormat(Qt.RichText)
    texto.setMinimumWidth(460)
    botoes = QHBoxLayout()
    d.b_historia = QPushButton("A história do Ipê")
    d.b_historia.clicked.connect(lambda: janela_da_historia(d).exec())
    d.b_creditos = QPushButton("Créditos e licenças")
    d.b_creditos.clicked.connect(lambda: janela_de_creditos(d).exec())
    fechar = QPushButton("Fechar")
    fechar.clicked.connect(d.accept)
    botoes.addWidget(d.b_historia)
    botoes.addWidget(d.b_creditos)
    botoes.addStretch(1)
    botoes.addWidget(fechar)
    lay = QVBoxLayout(d)
    lay.addWidget(texto)
    lay.addLayout(botoes)
    return d


def mostrar_sobre(parent: QWidget | None = None) -> None:
    janela_sobre(parent).exec()
