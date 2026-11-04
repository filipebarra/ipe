"""Laudos ▸ Produtividade… (0.99.53, onda B6): laudos assinados por médico, modalidade, subespecialidade,
prioridade ou dia, com o tempo até a assinatura e a parte no prazo; e o que está pendente agora."""
from __future__ import annotations

import logging

from PySide6.QtCore import QDate, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ipe.core import produtividade as PR
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)


class Barras(QWidget):
    """Barras horizontais simples: laudos por grupo (no prazo em verde, fora em laranja)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.linhas: list[dict] = []
        self.setMinimumHeight(120)

    def mostrar(self, linhas: list[dict]) -> None:
        self.linhas = linhas[:15]
        self.setMinimumHeight(24 + 20 * len(self.linhas))
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        if not self.linhas:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        larg_rot = 170
        maior = max(li["laudos"] for li in self.linhas) or 1
        w = max(10, self.width() - larg_rot - 60)
        for i, li in enumerate(self.linhas):
            y = 10 + 20 * i
            p.setPen(self.palette().text().color())
            p.drawText(QRectF(4, y, larg_rot - 8, 18), Qt.AlignRight | Qt.AlignVCenter, li["grupo"][:28])
            a = w * li["no_prazo"] / maior
            b = w * li["fora"] / maior
            p.fillRect(QRectF(larg_rot, y + 2, a, 14), QColor(60, 160, 90))
            p.fillRect(QRectF(larg_rot + a, y + 2, b, 14), QColor(225, 140, 40))
            p.drawText(QRectF(larg_rot + a + b + 6, y, 60, 18), Qt.AlignLeft | Qt.AlignVCenter, str(li["laudos"]))
        p.end()


class ProdutividadeDialog(QDialog):
    def __init__(self, repo, parent=None, so_eu: str | None = None):
        super().__init__(parent)
        self.repo = repo
        self.so_eu = so_eu                   # sem a permissão de usuários: só os laudos de quem está logado
        self.setWindowTitle("Produtividade dos laudos")
        self.resize(900, 640)
        self.itens: list[dict] = []
        self.linhas: list[dict] = []
        self.c_periodo = QComboBox()
        for k, v in PR.PERIODOS.items():
            self.c_periodo.addItem(v, k)
        self.c_periodo.addItem("Datas escolhidas", "datas")
        self.c_periodo.setCurrentIndex(2)
        self.d_de, self.d_ate = QDateEdit(QDate.currentDate().addDays(-29)), QDateEdit(QDate.currentDate())
        for d in (self.d_de, self.d_ate):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(lambda *_a: self._datas_mudaram())
        self.c_por = QComboBox()
        for k, v in PR.AGRUPAR.items():
            self.c_por.addItem(v, k)
        self.c_periodo.currentIndexChanged.connect(self._periodo_mudou)
        self.c_por.currentIndexChanged.connect(self.mostrar)
        topo = QHBoxLayout()
        for w in (QLabel("Período:"), self.c_periodo, self.d_de, QLabel("a"), self.d_ate, QLabel("Agrupar por:"),
                  self.c_por):
            topo.addWidget(w)
        topo.addStretch(1)
        self.resumo = QLabel()
        self.resumo.setWordWrap(True)
        self.pendentes = QLabel()
        self.pendentes.setWordWrap(True)
        self.tabela = QTableWidget(0, len(PR.COLS))
        self.tabela.setHorizontalHeaderLabels(PR.COLS)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSortingEnabled(False)
        colunas_ajustaveis(self.tabela)
        self.barras = Barras()
        rodape = QHBoxLayout()
        b_csv = QPushButton("Exportar CSV…")
        b_csv.clicked.connect(self.exportar)
        b_atual = QPushButton("Atualizar")
        b_atual.clicked.connect(self.recarregar)
        rodape.addWidget(b_atual)
        rodape.addStretch(1)
        rodape.addWidget(b_csv)
        lay = QVBoxLayout(self)
        lay.addLayout(topo)
        lay.addWidget(self.resumo)
        lay.addWidget(self.pendentes)
        lay.addWidget(self.tabela, 2)
        lay.addWidget(self.barras, 1)
        lay.addLayout(rodape)
        self._periodo_mudou()

    def _periodo_mudou(self, *_a) -> None:
        k = self.c_periodo.currentData()
        livre = k == "datas"
        self.d_de.setEnabled(livre)
        self.d_ate.setEnabled(livre)
        if not livre:
            a, b = PR.periodo(k)
            for d, v in ((self.d_de, a), (self.d_ate, b)):
                d.blockSignals(True)
                d.setDate(QDate.fromString(v, "yyyy-MM-dd"))
                d.blockSignals(False)
        self.recarregar()

    def _datas_mudaram(self) -> None:
        if self.c_periodo.currentData() == "datas":
            self.recarregar()

    def datas(self) -> tuple[str, str]:
        a, b = self.d_de.date().toString("yyyy-MM-dd"), self.d_ate.date().toString("yyyy-MM-dd")
        return (a, b) if a <= b else (b, a)

    def recarregar(self) -> None:
        de, ate = self.datas()
        try:
            itens = self.repo.produtividade_dados(de, ate)
        except Exception as e:  # noqa: BLE001
            log.exception("produtividade")
            QMessageBox.warning(self, "Produtividade", f"Não deu para ler os laudos: {e}")
            itens = []
        if self.so_eu is not None:
            itens = [i for i in itens if i.get("medico") == self.so_eu]
        self.itens = itens
        self._pendentes()
        self.mostrar()

    def _pendentes(self) -> None:
        try:
            rows = self.repo.search_studies(limit=20000)
        except TypeError:
            rows = self.repo.search_studies()
        except Exception:  # noqa: BLE001
            log.exception("pendentes")
            rows = []
        abertos = [r for r in rows if getattr(r, "report", "") in ("", "rascunho")]
        atras = sum(1 for r in abertos if getattr(r, "sla_estado", "") == "atrasado")
        venc = sum(1 for r in abertos if getattr(r, "sla_estado", "") == "atencao")
        self.pendentes.setText(f"Agora: {len(abertos)} exame(s) sem laudo assinado — {atras} atrasado(s), "
                               f"{venc} vencendo em menos de 2 h.")

    def mostrar(self, *_a) -> None:
        por = self.c_por.currentData()
        self.linhas = PR.agrupar(self.itens, por)
        t = PR.total(self.itens)
        self.tabela.setHorizontalHeaderItem(0, QTableWidgetItem(PR.AGRUPAR[por]))
        self.tabela.setRowCount(len(self.linhas))
        for r, li in enumerate(self.linhas):
            for c, v in enumerate(PR.celulas(li)):
                cel = QTableWidgetItem(v)
                if c:
                    cel.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabela.setItem(r, c, cel)
        de, ate = self.datas()
        pct = t.get("pct_prazo")
        self.resumo.setText(
            f"<b>{t['laudos']}</b> laudo(s) assinado(s) de {de[8:]}/{de[5:7]}/{de[:4]} a {ate[8:]}/{ate[5:7]}/{ate[:4]}"
            + (f" · mediana da chegada à assinatura {PR._h(t['mediana_h'])} h" if t["mediana_h"] is not None else "")
            + (f" · {pct:.0f}% no prazo" if pct is not None else "")
            + (f" · {t['retificacoes']} retificação(ões)" if t["retificacoes"] else "")
            + (" · só os seus laudos" if self.so_eu is not None else ""))
        self.barras.mostrar(self.linhas if por != "dia" else self.linhas[-15:])

    def exportar(self) -> None:
        nome, _f = QFileDialog.getSaveFileName(self, "Exportar a produtividade", "produtividade.csv", "CSV (*.csv)")
        if nome:
            with open(nome, "w", encoding="utf-8-sig") as f:
                f.write(PR.csv(self.linhas, PR.AGRUPAR[self.c_por.currentData()]))
