"""Preferências ▸ Anotações (0.99.9): o que cada nível de anotação mostra.

Uma tabela com os itens do overlay (linhas) e os níveis Completa, Parcial 1 e Parcial 2 (colunas
de caixas). Ausente não tem coluna: é a imagem sem nada por cima. Em cima, o nível em uso — o mesmo
que o botão "Anotações" do visualizador troca.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.ui.tabelas import colunas_ajustaveis
from ipe.ui.viewer import anotacoes as AN


class AnotacoesEditor(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        dica = QLabel("Escolha o que aparece sobre a imagem em cada nível. No visualizador, o botão "
                      "<b>Anotações</b> (e o botão direito do quadro) troca entre <b>Completa</b>, "
                      "<b>Parcial 1</b>, <b>Parcial 2</b> e <b>Ausente</b> — ausente é a imagem limpa. "
                      "O <b>Ctrl+C</b> copia o quadro como está na tela — ou com o nível escolhido "
                      "em <i>Na cópia</i>. <b>Ocultar dados do paciente</b> continua valendo por cima de qualquer nível.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color:#9a9a9a")

        self.c_nivel = QComboBox()
        for chave, nome in AN.NIVEIS:
            self.c_nivel.addItem(nome, chave)
        self.c_nivel.setCurrentIndex(max(0, self.c_nivel.findData(AN.nivel_atual(settings))))
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Nível em uso no visualizador:"))
        topo.addWidget(self.c_nivel)
        topo.addStretch(1)
        # 0.99.22 (plano AW 12): a cópia pode sair com outro nível (aula sem o nome do paciente, sem
        # anonimizar o arquivo) e leva sempre um carimbo mínimo
        self.c_saida = QComboBox()
        self.c_saida.addItem("O mesmo da tela", "")
        for chave, nome in AN.NIVEIS:
            self.c_saida.addItem(nome, chave)
        self.c_saida.setCurrentIndex(max(0, self.c_saida.findData(
            str(settings.get("viewer.anotacoes_saida", "") or ""))))
        self.cb_carimbo = QCheckBox("Carimbo mínimo na cópia: série, janela, escala e processamento aplicado")
        self.cb_carimbo.setChecked(bool(settings.get("viewer.carimbo_saida", True)))
        self.cb_carimbo.setToolTip("Uma faixa no pé da imagem copiada, mesmo com as anotações escondidas: quem "
                                   "recebe a cópia sabe que é um MIP de 10 mm, uma subtração, com que janela "
                                   "e escala. Os selos graves (compressão com perdas na mamografia) vão junto.")
        saida = QHBoxLayout()
        saida.addWidget(QLabel("Na cópia (Ctrl+C):"))
        saida.addWidget(self.c_saida)
        saida.addWidget(self.cb_carimbo)
        saida.addStretch(1)

        self.tabela = QTableWidget(len(AN.ITENS), 2 + len(AN.EDITAVEIS))
        self.tabela.setHorizontalHeaderLabels(["Onde", "Item"] + [AN.NOME_DO_NIVEL[n] for n in AN.EDITAVEIS])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setSelectionMode(QTableWidget.NoSelection)
        self._encher(AN.todos_os_niveis(settings))
        self.tabela.resizeColumnsToContents()
        colunas_ajustaveis(self.tabela)

        botoes = QHBoxLayout()
        for texto, fn in (("Marcar / desmarcar tudo em:", self._marcar_tudo),
                          ("Voltar ao de fábrica", self._fabrica)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        self.c_nivel_tudo = QComboBox()
        for n in AN.EDITAVEIS:
            self.c_nivel_tudo.addItem(AN.NOME_DO_NIVEL[n], n)
        botoes.insertWidget(1, self.c_nivel_tudo)
        botoes.addStretch(1)

        lay = QVBoxLayout(self)
        lay.addWidget(dica)
        lay.addLayout(topo)
        lay.addLayout(saida)
        lay.addWidget(self.tabela, 1)
        lay.addLayout(botoes)

    def _encher(self, niveis: dict[str, list[str]]) -> None:
        for r, (chave, nome, onde) in enumerate(AN.ITENS):
            self.tabela.setItem(r, 0, QTableWidgetItem(onde))
            it = QTableWidgetItem(nome)
            it.setData(Qt.UserRole, chave)
            self.tabela.setItem(r, 1, it)
            for c, nivel in enumerate(AN.EDITAVEIS):
                cb = QTableWidgetItem()
                cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                cb.setCheckState(Qt.Checked if chave in niveis.get(nivel, []) else Qt.Unchecked)
                cb.setTextAlignment(Qt.AlignCenter)
                self.tabela.setItem(r, 2 + c, cb)

    def _marcar_tudo(self) -> None:
        c = 2 + AN.EDITAVEIS.index(self.c_nivel_tudo.currentData())
        alvo = Qt.Unchecked if all(self.tabela.item(r, c).checkState() == Qt.Checked
                                   for r in range(self.tabela.rowCount())) else Qt.Checked
        for r in range(self.tabela.rowCount()):
            self.tabela.item(r, c).setCheckState(alvo)

    def _fabrica(self) -> None:
        self._encher({n: list(v) for n, v in AN.FABRICA.items()})

    def itens(self) -> dict[str, list[str]]:
        out = {}
        for c, nivel in enumerate(AN.EDITAVEIS):
            out[nivel] = [self.tabela.item(r, 1).data(Qt.UserRole) for r in range(self.tabela.rowCount())
                          if self.tabela.item(r, 2 + c).checkState() == Qt.Checked]
        return out

    def save(self) -> None:
        self.settings.set("viewer.anotacoes_itens", self.itens())
        self.settings.set("viewer.anotacoes_nivel", self.c_nivel.currentData() or "completa")
        self.settings.set("viewer.anotacoes_saida", self.c_saida.currentData() or "")
        self.settings.set("viewer.carimbo_saida", self.cb_carimbo.isChecked())
