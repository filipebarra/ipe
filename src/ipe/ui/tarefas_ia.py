"""Janela "Tarefas de IA" (0.99.32): o andamento das IAs e o botão de cancelar.

Mostra as segmentações (órgãos abdominais, coluna, cefalometria, índices do crânio, linfonodos) e o
implante na mamografia — as que rodam sozinhas quando o exame chega ao programa e as pedidas à mão —
com a situação, a etapa e o tempo. Cancelar vale na fila (não começa) e rodando (o processo do
TotalSegmentator é derrubado; nada é gravado no exame). Abre pelo botão Aplicações do visualizador,
pelo menu Exibir e pelo aviso "IA: …" na barra de status.

Não é modal: dá para continuar trabalhando com ela aberta. Uma só por programa.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ipe.ai import tarefas as TA

_janela: list = []


def _tempo(s: float) -> str:
    s = int(s)
    return f"{s // 60}:{s % 60:02d}" if s else ""


class TarefasIADialog(QDialog):
    COLUNAS = ("Exame", "Ferramenta", "Como", "Situação", "Etapa", "Tempo", "Resultado")

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Tarefas de IA")
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.resize(980, 380)
        lay = QVBoxLayout(self)
        t = QLabel("As IAs que rodam sozinhas quando o exame chega (Configurações ▸ CAD/IA) e as pedidas à mão. "
                   "Uma por vez; as outras esperam na fila. Cancelar não grava nada no exame.")
        t.setWordWrap(True)
        lay.addWidget(t)
        self.tabela = QTableWidget(0, len(self.COLUNAS))
        self.tabela.setHorizontalHeaderLabels(self.COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)
        for c, w in enumerate((240, 160, 90, 130, 220, 60)):
            self.tabela.setColumnWidth(c, w)
        self.tabela.itemSelectionChanged.connect(self._botoes)
        lay.addWidget(self.tabela, 1)
        self.resumo = QLabel()
        bot = QHBoxLayout()
        self.b_cancelar = QPushButton("Cancelar a escolhida")
        self.b_cancelar.clicked.connect(self.cancelar_escolhida)
        self.b_todas = QPushButton("Cancelar todas")
        self.b_todas.setToolTip("A que está rodando e as que esperam na fila")
        self.b_todas.clicked.connect(self.cancelar_todas)
        self.b_limpar = QPushButton("Limpar as concluídas")
        self.b_limpar.clicked.connect(self.limpar)
        b_fechar = QPushButton("Fechar")
        b_fechar.clicked.connect(self.close)
        bot.addWidget(self.resumo, 1)
        for b in (self.b_cancelar, self.b_todas, self.b_limpar, b_fechar):
            bot.addWidget(b)
        lay.addLayout(bot)
        self._ids: list[int] = []
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.atualizar)
        self._timer.start()
        self.atualizar()

    # ------------------------------------------------------------------ tela
    def atualizar(self) -> None:
        tarefas = TA.REGISTRO.tarefas()
        escolhida = self.escolhida()
        agora = time.time()
        self.tabela.setRowCount(len(tarefas))
        self._ids = [t.id for t in tarefas]
        for r, t in enumerate(tarefas):
            valores = (t.exame or t.study_uid[-12:], t.ferramenta, t.origem, TA.ROTULO.get(t.estado, t.estado),
                       t.etapa, _tempo(t.tempo(agora)), t.mensagem)
            for c, v in enumerate(valores):
                it = self.tabela.item(r, c)
                if it is None:
                    it = QTableWidgetItem()
                    self.tabela.setItem(r, c, it)
                if it.text() != str(v):
                    it.setText(str(v))
                it.setToolTip(str(v) if c in (0, 4, 6) else "")
            if escolhida == t.id and self.tabela.currentRow() != r:
                self.tabela.selectRow(r)
        self.resumo.setText(TA.REGISTRO.resumo() or "Nenhuma IA rodando agora.")
        self._botoes()

    def escolhida(self) -> int | None:
        r = self.tabela.currentRow()
        return self._ids[r] if 0 <= r < len(self._ids) and self.tabela.selectedItems() else None

    def _botoes(self) -> None:
        tid = self.escolhida()
        t = next((x for x in TA.REGISTRO.tarefas() if x.id == tid), None)
        self.b_cancelar.setEnabled(bool(t and t.ativa))
        self.b_todas.setEnabled(bool(TA.REGISTRO.ativas()))

    # ------------------------------------------------------------------ ações
    def cancelar_escolhida(self) -> bool:
        tid = self.escolhida()
        ok = tid is not None and TA.REGISTRO.cancelar(tid)
        self.atualizar()
        return ok

    def cancelar_todas(self) -> int:
        n = TA.REGISTRO.cancelar_todas()
        self.atualizar()
        return n

    def limpar(self) -> int:
        n = TA.REGISTRO.limpar_feitas()
        self.atualizar()
        return n


def abrir(parent=None) -> TarefasIADialog:
    """Mostra a janela (a mesma, se já estiver aberta)."""
    vivas = [d for d in _janela if _viva(d)]
    _janela[:] = vivas
    if vivas:
        d = vivas[0]
    else:
        d = TarefasIADialog(parent)
        _janela.append(d)
    d.show()
    d.raise_()
    d.activateWindow()
    return d


def _viva(d) -> bool:
    try:
        import shiboken6
        return shiboken6.isValid(d)
    except Exception:  # noqa: BLE001
        return False
