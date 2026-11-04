"""Janela da busca ativa (0.99.51, onda B8) e a configuração dos prazos por categoria BI-RADS."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ipe.reporting import busca_ativa as BA
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

VISOES = {"abertas": "Abertas (pendente, contatada, agendada)", "atrasadas": "Atrasadas",
          "retornou": "Retornaram", "encerrado": "Encerradas", "todas": "Todas"}
COLS = ["Paciente", "ID", "Exame", "BI-RADS", "Motivo", "Prazo", "Situação", "Estado"]


def _usuario() -> str:
    try:
        from ipe.auth import session as S
        u = S.get()
        return u.full_name or u.username
    except Exception:  # noqa: BLE001
        return ""


class BuscaAtivaDialog(QDialog):
    def __init__(self, repo, win=None, parent=None):
        super().__init__(parent)
        self.repo, self.win = repo, win
        self.setWindowTitle("Busca ativa — BI-RADS que pedem retorno")
        self.resize(1050, 560)
        self.itens: list[dict] = []
        self.visao = QComboBox()
        for k, v in VISOES.items():
            self.visao.addItem(v, k)
        self.visao.currentIndexChanged.connect(self.recarregar)
        self.resumo = QLabel()
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Mostrar:"))
        topo.addWidget(self.visao)
        topo.addStretch(1)
        topo.addWidget(self.resumo)
        self.tabela = QTableWidget(0, len(COLS))
        self.tabela.setHorizontalHeaderLabels(COLS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        colunas_ajustaveis(self.tabela)
        self.tabela.itemSelectionChanged.connect(self._mostrar_historico)
        self.tabela.cellDoubleClicked.connect(lambda *_a: self.abrir_exame())
        self.historico = QLabel()
        self.historico.setWordWrap(True)
        self.historico.setTextInteractionFlags(Qt.TextSelectableByMouse)
        botoes = QHBoxLayout()
        for texto, fn in (("Contatada", lambda: self.mudar("contatado")), ("Agendada", lambda: self.mudar("agendado")),
                          ("Retornou", lambda: self.mudar("retornou")), ("Encerrar…", self.encerrar),
                          ("Nota…", self.nota), ("Abrir o exame", self.abrir_exame)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        botoes.addStretch(1)
        for texto, fn in (("Conferir retornos", self.conferir), ("Exportar CSV…", self.exportar),
                          ("Prazos…", self.configurar)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        lay = QVBoxLayout(self)
        lay.addLayout(topo)
        lay.addWidget(self.tabela, 1)
        lay.addWidget(self.historico)
        lay.addLayout(botoes)
        self.conferir(silencioso=True)

    # ------------------------------------------------------------------ dados
    def recarregar(self) -> None:
        visao = self.visao.currentData()
        estados = {"abertas": BA.ABERTOS, "atrasadas": BA.ABERTOS, "retornou": ("retornou",),
                   "encerrado": ("encerrado",)}.get(visao)
        try:
            itens = self.repo.buscas_ativas(list(estados) if estados else None)
        except Exception as e:  # noqa: BLE001
            log.exception("buscas ativas")
            QMessageBox.warning(self, "Busca ativa", f"Não deu para ler a busca ativa: {e}")
            itens = []
        if visao == "atrasadas":
            itens = [i for i in itens if BA.situacao(i)[1]]
        self.itens = itens
        self.tabela.setRowCount(len(itens))
        atrasadas = 0
        for r, it in enumerate(itens):
            sit, atraso = BA.situacao(it)
            atrasadas += int(atraso)
            vals = [it["patient_name"], it["patient_id"], f"{BA.fmt(it['study_date'])} {it['modalidade']}",
                    it["categoria"], it["motivo"], BA.fmt(it["prazo"]), sit, BA.ESTADOS.get(it["estado"], it["estado"])]
            for c, v in enumerate(vals):
                cel = QTableWidgetItem(str(v))
                if atraso:
                    cel.setForeground(QColor(200, 40, 40))
                self.tabela.setItem(r, c, cel)
        self.tabela.resizeColumnsToContents()
        self.resumo.setText(f"{len(itens)} pedido(s)" + (f" · {atrasadas} atrasado(s)" if atrasadas else ""))
        self._mostrar_historico()

    def selecionado(self) -> dict | None:
        r = self.tabela.currentRow()
        return self.itens[r] if 0 <= r < len(self.itens) and self.tabela.selectedItems() else None

    def _mostrar_historico(self) -> None:
        it = self.selecionado()
        self.historico.setText(("<b>Histórico</b><br>" + (it["historico"] or "").replace("\n", "<br>")) if it else "")

    # ------------------------------------------------------------------ ações
    def mudar(self, estado: str, nota: str = "") -> None:
        it = self.selecionado()
        if it is None:
            return
        self.repo.atualizar_busca_ativa(it["id"], estado=estado, nota=nota, usuario=_usuario())
        self.recarregar()

    def encerrar(self) -> None:
        it = self.selecionado()
        if it is None:
            return
        motivo, ok = QInputDialog.getItem(
            self, "Encerrar", "Motivo:", ["Fez o exame em outro serviço", "Não quis voltar", "Sem contato",
                                          "Óbito", "Outro"], 0, True)
        if ok:
            self.mudar("encerrado", motivo)

    def nota(self) -> None:
        it = self.selecionado()
        if it is None:
            return
        texto, ok = QInputDialog.getText(self, "Nota", "Nota (vai ao histórico):")
        if ok and texto.strip():
            self.mudar("", texto)

    def abrir_exame(self) -> None:
        it = self.selecionado()
        if it is None or self.win is None:
            return
        uid = it.get("retorno_uid") if it.get("estado") == "retornou" and it.get("retorno_uid") else it["study_uid"]
        try:
            self.win.open_study(uid)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Busca ativa", f"Não deu para abrir o exame: {e}")

    def conferir(self, silencioso: bool = False) -> int:
        try:
            n = self.repo.conferir_retornos_busca_ativa()
        except Exception:  # noqa: BLE001
            log.exception("conferir retornos")
            n = 0
        self.recarregar()
        if not silencioso:
            QMessageBox.information(self, "Busca ativa", f"{n} paciente(s) com exame de retorno no banco.")
        return n

    def exportar(self) -> None:
        nome, _f = QFileDialog.getSaveFileName(self, "Exportar a busca ativa", "busca_ativa.csv", "CSV (*.csv)")
        if not nome:
            return
        with open(nome, "w", encoding="utf-8-sig") as f:
            f.write(BA.csv_das_buscas(self.itens))

    def configurar(self) -> None:
        if BuscaAtivaConfigDialog(self.repo, self).exec():
            self.recarregar()


class BuscaAtivaConfigDialog(QDialog):
    """Configurações ▸ Laudos ▸ Busca ativa: quais categorias geram o pedido e em quantos dias."""

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Busca ativa — prazos")
        cfg = BA.config(repo)
        self.ligada = QCheckBox("O laudo assinado gera o pedido de busca ativa")
        self.ligada.setChecked(cfg["ligada"])
        form = QFormLayout()
        form.addRow(self.ligada)
        self.linhas = {}
        for cat, dias in BA.OPCOES:
            c = QCheckBox(BA.MOTIVOS[cat])
            c.setChecked(cat in cfg["dias"])
            sp = QSpinBox()
            sp.setRange(1, 730)
            sp.setSuffix(" dias")
            sp.setValue(int(cfg["dias"].get(cat, dias)))
            h = QHBoxLayout()
            h.addWidget(c, 1)
            h.addWidget(sp)
            form.addRow(h)
            self.linhas[cat] = (c, sp)
        nota = QLabel("O prazo conta da data da assinatura. A paciente sai da lista sozinha quando chega ao banco "
                      "um exame de mama dela (mamografia, ou US/RM com “mama” na descrição).")
        nota.setWordWrap(True)
        form.addRow(nota)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(bb)

    def valor(self) -> dict:
        return {"ligada": self.ligada.isChecked(),
                "dias": {cat: sp.value() for cat, (c, sp) in self.linhas.items() if c.isChecked()}}

    def _salvar(self) -> None:
        try:
            self.repo.set_app_setting(BA.CHAVE, self.valor())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Busca ativa", f"Não deu para gravar: {e}")
            return
        self.accept()
