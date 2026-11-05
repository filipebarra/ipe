"""Telas de exportar e importar as configurações (0.99.68; o trabalho fica em core/config_pacote.py)."""
from __future__ import annotations

import logging
import socket
import time
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QLabel, QMessageBox,
                               QVBoxLayout)

from ipe.core import config_pacote as CP

log = logging.getLogger(__name__)

PEDEM_CONFIGURAR = ("servico", "nos", "identidades", "regras")


def _pode(perm: str) -> bool:
    from ipe.auth import session as S
    return bool(S.can(perm))


class EscolherPartes(QDialog):
    """Caixas com as partes; `senhas` acrescenta a caixa de levar as senhas (na exportação)."""

    def __init__(self, parent, titulo: str, texto: str, partes: dict[str, str], marcar_pessoal: bool = True,
                 senhas: bool = False):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        lay = QVBoxLayout(self)
        t = QLabel(texto)
        t.setWordWrap(True)
        lay.addWidget(t)
        self.caixas: dict[str, QCheckBox] = {}
        pode = _pode("configure")
        for s, detalhe in partes.items():
            cb = QCheckBox(CP.TITULOS[s] + (f" — {detalhe}" if detalhe else ""))
            cb.setChecked(True)
            if s in PEDEM_CONFIGURAR and not pode:
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.setToolTip("Pede a permissão de configurar o computador.")
            self.caixas[s] = cb
            lay.addWidget(cb)
        self.senhas = None
        if senhas:
            self.senhas = QCheckBox("Levar as senhas (dos nós DICOM e da IA do laudo) — o arquivo fica com elas em "
                                    "texto claro: guarde-o com cuidado")
            lay.addWidget(self.senhas)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def escolhidas(self) -> tuple[str, ...]:
        return tuple(s for s, cb in self.caixas.items() if cb.isChecked())


def exportar(win) -> str | None:
    partes = {s: "" for s in CP.SECOES}
    if not getattr(win.settings, "user", None):
        partes.pop("pessoal")
    d = EscolherPartes(win, "Exportar as configurações",
                       "O arquivo abre em qualquer computador com o Ipê, no Windows ou no Linux. Não leva os exames, "
                       "a pasta do banco, os monitores, o login nem o título AE deste computador.", partes, senhas=True)
    if d.exec() != QDialog.Accepted or not d.escolhidas():
        return None
    nome = f"Ipe-configuracoes-{socket.gethostname() or 'pc'}-{time.strftime('%Y%m%d')}{CP.EXTENSAO}"
    caminho, _ = QFileDialog.getSaveFileName(win, "Salvar as configurações", str(Path.home() / nome),
                                             f"Configurações do Ipê (*{CP.EXTENSAO})")
    if not caminho:
        return None
    try:
        pac = CP.exportar(caminho, win.settings, getattr(win, "repo", None), win.paths, d.escolhidas(),
                          senhas=bool(d.senhas and d.senhas.isChecked()))
    except Exception as e:  # noqa: BLE001
        log.exception("exportar as configurações")
        QMessageBox.warning(win, "Exportar as configurações", f"Não deu para gravar o arquivo:\n{e}")
        return None
    win.statusBar().showMessage(f"Configurações exportadas: {pac['_arquivo']}", 12000)
    return pac["_arquivo"]


def importar(win, caminho: str | None = None) -> dict | None:
    if not caminho:
        caminho, _ = QFileDialog.getOpenFileName(win, "Importar configurações", str(Path.home()),
                                                 f"Configurações do Ipê (*{CP.EXTENSAO});;Todos (*)")
    if not caminho:
        return None
    try:
        pac = CP.ler(caminho)
    except CP.PacoteInvalido as e:
        QMessageBox.warning(win, "Importar configurações", str(e))
        return None
    partes = CP.resumo(pac)
    if not partes:
        QMessageBox.information(win, "Importar configurações", "O arquivo não tem configurações.")
        return None
    origem = f"Feito na versão {pac.get('programa', '?')} ({pac.get('sistema', '?')}), em {pac.get('data', '?')}."
    d = EscolherPartes(win, "Importar configurações",
                       origem + " O que já existe aqui com o mesmo nome (nó, regra, protocolo) é atualizado; o resto "
                       "fica. Antes, as configurações de agora são guardadas numa cópia.", partes)
    if d.exec() != QDialog.Accepted or not d.escolhidas():
        return None
    copia = CP.guardar_antes(win.settings, getattr(win, "repo", None), win.paths)
    feito = CP.aplicar(pac, win.settings, getattr(win, "repo", None), win.paths, d.escolhidas())
    linhas = [f"{CP.TITULOS[s]}: {feito[s]}" for s in CP.SECOES if s in feito]
    if feito["_caminhos"]:
        linhas.append(f"Pastas do outro sistema que não foram gravadas: {len(feito['_caminhos'])}.")
    if feito["_erros"]:
        linhas.append("Não entraram: " + "; ".join(feito["_erros"][:6]))
    if copia is not None:
        linhas.append(f"Cópia de antes: {copia}")
    linhas.append("Feche e abra o programa para tudo valer.")
    QMessageBox.information(win, "Importar configurações", "\n".join(linhas))
    return feito
