"""A fila dos filmes parados, por aparelho.

Um filme parado é de propósito enquanto o aparelho não tem cadastro — mas só é aceitável
enquanto estiver visível e fácil de soltar. Esta janela é as duas coisas.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ipe.core.i18n import tr
from ipe.printing import held as H
from ipe.ui.tabelas import colunas_ajustaveis

#: tons que se leem no claro e no escuro — a janela não sabe em qual tema vai abrir
AMBAR = "#c98b12"
VERDE = "#2e8b45"

#: e, antes da cor, o símbolo: é ele que sobrevive a qualquer tema e a quem não distingue cor
SIMBOLO = {H.PRONTO: "✔", H.SEM_CADASTRO: "⌛", H.DESLIGADA: "⌛", H.SEM_REGRA: "⌛", H.SEM_PACIENTE: "⌛"}


class HeldDialog(QDialog):
    registrar = Signal(str)          # pedir o cadastro de uma origem (origin_id)
    liberar = Signal(list)           # mandar estas linhas pelo caminho normal

    def __init__(self, settings, rows, carregar=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Filmes parados"))
        self.settings, self.rows, self.carregar = settings, list(rows or []), carregar
        self.grupos: list[H.Group] = []
        self.resize(760, 420)

        v = QVBoxLayout(self)
        self.resumo = QLabel()
        self.resumo.setWordWrap(True)
        v.addWidget(self.resumo)

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels([
            tr("Aparelho"), tr("Trabalhos"), tr("Folhas"), tr("Imagens"),
            tr("Parado desde"), tr("Situação")])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setSelectionMode(QTableWidget.SingleSelection)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabela.itemSelectionChanged.connect(self.atualiza_botoes)
        v.addWidget(self.tabela, 1)
        colunas_ajustaveis(self.tabela)

        linha = QHBoxLayout()
        self.b_cadastrar = QPushButton(tr("Cadastrar esta origem…"))
        self.b_cadastrar.clicked.connect(self.pedir_cadastro)
        self.b_liberar = QPushButton(tr("Liberar os deste aparelho"))
        self.b_liberar.clicked.connect(self.liberar_grupo)
        self.b_todos = QPushButton(tr("Liberar todos os prontos"))
        self.b_todos.clicked.connect(self.liberar_todos)
        b_fechar = QPushButton(tr("Fechar"))
        b_fechar.clicked.connect(self.reject)
        for b in (self.b_cadastrar, self.b_liberar, self.b_todos):
            linha.addWidget(b)
        linha.addStretch(1)
        linha.addWidget(b_fechar)
        v.addLayout(linha)

        self.recarregar(self.rows)

    # ------------------------------------------------------------------ conteúdo
    def recarregar(self, rows) -> None:
        self.rows = list(rows or [])
        self.grupos = H.groups(self.settings, self.rows, self.carregar)
        self.tabela.setRowCount(0)
        for g in self.grupos:
            i = self.tabela.rowCount()
            self.tabela.insertRow(i)
            valores = [g.label(), str(g.trabalhos), str(g.folhas), str(g.imagens),
                       (g.desde() or "")[:16],
                       f"{SIMBOLO.get(g.motivo, '')} {tr(H.TEXTO.get(g.motivo, g.motivo))}".strip()]
            for col, txt in enumerate(valores):
                it = QTableWidgetItem(txt)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if col:
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if col == 5:
                    it.setForeground(QColor(VERDE if g.pode_liberar else AMBAR))
                self.tabela.setItem(i, col, it)
        total = sum(g.trabalhos for g in self.grupos)
        if total:
            self.resumo.setText(tr("{} Nenhum deles foi encaminhado: cadastre a origem e libere. Nada sai sozinho.").format(H.resumo(self.grupos)))
        else:
            self.resumo.setText(tr("Nenhum filme parado: tudo o que chegou já foi encaminhado ou já está na lista para você."))
        if self.grupos:
            self.tabela.selectRow(0)     # janela que abre com tudo apagado parece quebrada
        self.atualiza_botoes()

    def grupo(self) -> H.Group | None:
        i = self.tabela.currentRow()
        return self.grupos[i] if 0 <= i < len(self.grupos) else None

    def atualiza_botoes(self) -> None:
        g = self.grupo()
        self.b_cadastrar.setEnabled(g is not None and not g.cadastrada)
        self.b_liberar.setEnabled(g is not None and g.pode_liberar)
        self.b_todos.setEnabled(any(x.pode_liberar for x in self.grupos))

    # ------------------------------------------------------------------ ações
    def pedir_cadastro(self) -> None:
        g = self.grupo()
        if g is not None:
            self.registrar.emit(g.origin_id)

    def liberar_grupo(self) -> None:
        g = self.grupo()
        if g is None or not g.pode_liberar:
            return
        self._confirmar(g.rows, g.label())

    def liberar_todos(self) -> None:
        linhas = [r for g in self.grupos if g.pode_liberar for r in g.rows]
        self._confirmar(linhas, tr("todos os aparelhos prontos"))

    def _confirmar(self, linhas: list[dict], quem: str) -> None:
        if not linhas:
            return
        resp = QMessageBox.question(
            self, tr("Filmes parados"),
            tr("Mandar {} trabalho(s) de {} agora, cada um para o destino da regra dele?").format(len(linhas), quem),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if resp == QMessageBox.Yes:
            self.liberar.emit(linhas)
