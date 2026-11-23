"""0.100.108: "Criar link do exame (Ipê Web)…" — botão direito no exame, no banco.

O link abre só aquele exame no Ipê Web, sem senha, com as permissões escolhidas (IA, enviar, anexar) e validade. A
janela também lista os links do exame (usos, validade) e revoga.
"""
from __future__ import annotations

import logging
import socket
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ipe.core.i18n import tr

log = logging.getLogger(__name__)


def _ip_da_rede() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class Fonte:
    """Onde os links moram: o servidor central (pelo RPC, no Ipê cliente) ou este computador, se ele é o servidor."""

    def __init__(self, repo, servidor=None) -> None:
        self.repo, self.servidor = repo, servidor
        self.cliente = getattr(repo, "client", None) if hasattr(repo, "upload_study") else None

    def disponivel(self) -> str:
        if self.cliente is not None or self.servidor is not None:
            return ""
        return tr("O link abre o exame no Ipê Web do servidor central. Este computador não é servidor nem está "
                  "ligado a um (Configurações ▸ Servidor central).")

    def base(self) -> str:
        if self.cliente is not None:
            return str(self.cliente.url).rstrip("/")
        srv = self.servidor
        return f"{srv.scheme}://{_ip_da_rede()}:{srv.port}"

    def criar(self, study_uid: str, perms: list[str], horas: float, rotulo: str) -> dict:
        if self.cliente is not None:
            return self.cliente.rpc("links_exame_criar", study_uid, perms=perms, horas=horas, rotulo=rotulo)
        from ipe.auth import session as S
        from ipe.central import links_exame as LE
        tok, link = LE.criar(self.repo, study_uid, perms, horas, rotulo, S.get().username)
        return {"token": tok, "link": link, "caminho": f"/web/#/link/{tok}"}

    def listar(self, study_uid: str) -> list[dict]:
        if self.cliente is not None:
            return list(self.cliente.rpc("links_exame_listar", study_uid) or [])
        from ipe.central import links_exame as LE
        return LE.listar(self.repo, study_uid)

    def revogar(self, lid: str) -> None:
        if self.cliente is not None:
            self.cliente.rpc("links_exame_revogar", lid)
            return
        from ipe.auth import session as S
        from ipe.central import links_exame as LE
        LE.revogar(self.repo, lid, S.get().username)


class LinkExameDialog(QDialog):
    def __init__(self, fonte: Fonte, study_uid: str, descricao: str = "", parent=None) -> None:
        super().__init__(parent)
        from ipe.central import links_exame as LE
        self.fonte, self.study_uid = fonte, study_uid
        self.setWindowTitle(tr("Link do exame (Ipê Web)"))
        lay = QVBoxLayout(self)
        topo = QLabel(tr("Abre só este exame no Ipê Web, sem senha: sem a lista, sem o banco, sem laudo. Quem tiver o "
                         "link vê o exame até ele vencer — mande só a quem deve ver.") +
                      (f"<br><b>{descricao}</b>" if descricao else ""))
        topo.setWordWrap(True)
        lay.addWidget(topo)
        caixa = QGroupBox(tr("Novo link"))
        f = QFormLayout(caixa)
        self.e_rotulo = QLineEdit()
        self.e_rotulo.setPlaceholderText(tr("Para quem (ex.: Dr. Fulano, cirurgião)"))
        f.addRow(tr("Para quem:"), self.e_rotulo)
        self.k_perm = {}
        for k, (nome, _p) in LE.PERMISSOES.items():
            c = QCheckBox(tr(nome))
            self.k_perm[k] = c
            f.addRow("" if k != "ia" else tr("O link também pode:"), c)
        self.c_validade = QComboBox()
        for h, nome in zip(LE.VALIDADES_H, ("1 dia", "3 dias", "7 dias", "30 dias")):
            self.c_validade.addItem(tr(nome), h)
        self.c_validade.setCurrentIndex(0)
        f.addRow(tr("Vale por:"), self.c_validade)
        self.b_criar = QPushButton(tr("Criar link"))
        self.b_criar.clicked.connect(self.criar)
        f.addRow("", self.b_criar)
        self.e_link = QLineEdit()
        self.e_link.setReadOnly(True)
        self.b_copiar = QPushButton(tr("Copiar"))
        self.b_copiar.setEnabled(False)
        self.b_copiar.clicked.connect(self.copiar)
        h = QHBoxLayout()
        h.addWidget(self.e_link, 1)
        h.addWidget(self.b_copiar)
        f.addRow(tr("Link:"), h)
        lay.addWidget(caixa)
        lay.addWidget(QLabel(tr("Links deste exame:")))
        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels([tr("Para quem"), tr("Pode"), tr("Criado por"), tr("Criado em"),
                                               tr("Vence"), tr("Usos"), tr("Situação")])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)
        lay.addWidget(self.tabela, 1)
        baixo = QHBoxLayout()
        self.b_revogar = QPushButton(tr("Revogar o link selecionado"))
        self.b_revogar.clicked.connect(self.revogar)
        fechar = QPushButton(tr("Fechar"))
        fechar.clicked.connect(self.accept)
        baixo.addWidget(self.b_revogar)
        baixo.addStretch(1)
        baixo.addWidget(fechar)
        lay.addLayout(baixo)
        self.resize(860, 560)
        self.links: list[dict] = []
        self.carregar()

    def carregar(self) -> None:
        try:
            self.links = self.fonte.listar(self.study_uid)
        except Exception as e:  # noqa: BLE001
            log.exception("links do exame")
            self.links = []
            QMessageBox.warning(self, tr("Link do exame (Ipê Web)"), str(e))
        from ipe.central import links_exame as LE
        quando = lambda t: datetime.fromtimestamp(float(t)).strftime("%d/%m/%Y %H:%M") if t else ""  # noqa: E731
        self.tabela.setRowCount(len(self.links))
        for i, x in enumerate(self.links):
            pode = ", ".join(tr(LE.PERMISSOES[p][0]) for p in x.get("perms") or [] if p in LE.PERMISSOES) \
                or tr("só ver")
            sit = tr("revogado") if x.get("revogado") else (tr("ativo") if x.get("ativo") else tr("vencido"))
            for j, v in enumerate((x.get("rotulo") or "", pode, x.get("criado_por") or "", quando(x.get("criado_em")),
                                   quando(x.get("expira")), str(x.get("usos", 0)), sit)):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, x["id"])
                self.tabela.setItem(i, j, it)

    def criar(self) -> None:
        perms = [k for k, c in self.k_perm.items() if c.isChecked()]
        try:
            r = self.fonte.criar(self.study_uid, perms, float(self.c_validade.currentData()),
                                 self.e_rotulo.text().strip())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("Link do exame (Ipê Web)"), tr("Não consegui criar o link: {}").format(e))
            return
        self.e_link.setText(self.fonte.base() + r["caminho"])
        self.b_copiar.setEnabled(True)
        self.copiar()
        self.carregar()

    def copiar(self) -> None:
        if self.e_link.text():
            QApplication.clipboard().setText(self.e_link.text())
            self.b_copiar.setText(tr("Copiado ✔"))

    def revogar(self) -> None:
        r = self.tabela.currentRow()
        if r < 0 or r >= len(self.links):
            return
        x = self.links[r]
        if QMessageBox.question(self, tr("Link do exame (Ipê Web)"),
                                tr("Revogar o link de “{}”? Quem estiver com ele aberto perde o acesso na hora.")
                                .format(x.get("rotulo") or x["id"])) != QMessageBox.Yes:
            return
        try:
            self.fonte.revogar(x["id"])
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("Link do exame (Ipê Web)"), str(e))
        self.carregar()
