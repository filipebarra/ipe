"""Procurar e instalar versão nova pelo GitHub (0.99.70); o trabalho fica em core/atualizar_github.py."""
from __future__ import annotations

import logging
import os
import threading
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from ipe.core import atualizar_github as GH

log = logging.getLogger(__name__)

CHAVE_LIGADO = "atualizacao.github"
CHAVE_DIA = "atualizacao.github_dia"
CHAVE_PULADA = "atualizacao.github_pulada"


class _Ponte(QObject):
    pronto = Signal(object, object)          # (info, erro)


def procurar(win, silencioso: bool = False, consultar=None) -> None:
    """Consulta o GitHub numa thread (a tela não trava) e responde na janela."""
    s = win.settings
    if silencioso:
        if os.environ.get("IPE_SEM_GITHUB"):          # testes e quem não quer rede nenhuma ao abrir
            return
        if not s.get(CHAVE_LIGADO, True) or getattr(win, "_central", None) is not None:
            return                                   # no modo cliente quem manda nas versões é o servidor
        hoje = time.strftime("%Y-%m-%d")
        if s.get(CHAVE_DIA, "") == hoje:
            return
        s.set(CHAVE_DIA, hoje)
        s.save()
    ponte = _Ponte(win)
    win._ponte_github = ponte                       # não deixar o Python recolher antes da resposta
    ponte.pronto.connect(lambda info, erro: responder(win, info, erro, silencioso))
    consultar = consultar or GH.consultar

    def trabalho():
        try:
            ponte.pronto.emit(consultar(), None)
        except Exception as e:  # noqa: BLE001
            ponte.pronto.emit(None, e)
    threading.Thread(target=trabalho, name="ipe-github", daemon=True).start()


def responder(win, info, erro, silencioso: bool) -> str:
    from ipe import __version__
    titulo = "Versão nova"
    if erro is not None:
        log.info("GitHub: %s", erro)
        if not silencioso:
            QMessageBox.warning(win, titulo, str(erro))
        return "erro"
    if not GH.ha_nova(info, __version__):
        if not silencioso:
            QMessageBox.information(win, titulo, f"Você já está na versão mais nova ({__version__}).")
        return ""
    if silencioso and win.settings.get(CHAVE_PULADA, "") == info["versao"]:
        return "pulada"
    modo = GH.modo_desta_instalacao()
    pacote = GH.pacote_para(info, modo)
    caixa = QMessageBox(win)
    caixa.setWindowTitle(titulo)
    caixa.setText(f"Saiu a versão {info['versao']} do Ipê (você está na {__version__}).")
    notas = (info.get("notas") or "").strip()
    if notas:
        caixa.setDetailedText(notas)
    b_pagina = caixa.addButton("Ver a página", QMessageBox.HelpRole)
    b_agora = None
    if modo == "codigo":
        caixa.setInformativeText("Este programa roda do código-fonte: atualize pelo git (ou pelo pacote de "
                                 "atualização), não pelo GitHub.")
    elif pacote is None:
        caixa.setInformativeText("O release não tem o pacote deste tipo de instalação. Baixe pela página.")
    elif modo == "instalado":
        mb = pacote["tamanho"] / 1024 / 1024
        caixa.setInformativeText(f"Baixar ({mb:.0f} MB) e instalar agora? O programa fecha, instala e abre de novo; "
                                 "pastas, banco, idioma e usuários continuam como estão.")
        b_agora = caixa.addButton("Baixar e instalar", QMessageBox.AcceptRole)
    else:
        mb = pacote["tamanho"] / 1024 / 1024
        caixa.setInformativeText(f"Baixar o pacote ({mb:.0f} MB)? A versão portátil se troca à mão: a pasta abre "
                                 "quando terminar.")
        b_agora = caixa.addButton("Baixar", QMessageBox.AcceptRole)
    b_pular = caixa.addButton("Pular esta versão", QMessageBox.RejectRole)
    caixa.addButton("Depois", QMessageBox.RejectRole)
    caixa.exec()
    clicado = caixa.clickedButton()
    if clicado is b_pagina:
        QDesktopServices.openUrl(QUrl(info.get("pagina") or GH.PAGINA))
        return "pagina"
    if clicado is b_pular:
        win.settings.set(CHAVE_PULADA, info["versao"])
        win.settings.save()
        return "pulada"
    if b_agora is None or clicado is not b_agora:
        return "depois"
    return baixar_e_instalar(win, pacote, modo)


def baixar_e_instalar(win, pacote: dict, modo: str, baixar=None, rodar=None) -> str:
    from ipe.central import atualizacoes as AT
    destino = win.paths.data / "Atualizacoes"
    prog = QProgressDialog("Baixando a versão nova…", "Cancelar", 0, 100, win)
    prog.setMinimumDuration(0)
    prog.setValue(0)

    def andou(feito, total):
        if total:
            prog.setValue(int(100 * feito / total))
        QApplication.processEvents()
        if prog.wasCanceled():
            raise GH.ErroAtualizacao("Download cancelado.")
    try:
        arq = (baixar or GH.baixar)(pacote, destino, andou)
    except GH.ErroAtualizacao as e:
        prog.close()
        if "cancelado" not in str(e):
            QMessageBox.warning(win, "Versão nova", str(e))
        return "erro"
    prog.close()
    GH.limpar_antigos(destino, manter=arq)
    if modo == "instalado":
        try:
            (rodar or AT.rodar_instalador)(arq)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(win, "Versão nova", f"Não deu para abrir o instalador: {e}\n\n{arq}")
            return "baixada"
        win.settings.save()
        QTimer.singleShot(0, win.quit_app)
        return "instalando"
    QMessageBox.information(win, "Versão nova", f"Baixado em:\n{arq}\n\nFeche o programa e troque a pasta pela do "
                            "pacote novo (o banco e as configurações ficam fora dela).")
    AT.abrir_pasta(arq.parent)
    return "baixada"
