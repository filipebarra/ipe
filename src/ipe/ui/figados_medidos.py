"""Fígado na RM: medidas e confirmações (0.100.101) — a tabela da esteatose, do ferro e da rigidez, como a da
densidade mamária (`densidades_medidas`).

Uma linha por exame com o resultado da IA de fígado: PDFF e grau, fração de sinal da dupla eco, R2* e ferro estimado,
rigidez e faixa, a situação da revisão e quem revisou. Em cima, quantos foram medidos e quantos com esteatose,
sobrecarga de ferro ou rigidez acima do normal. Duplo clique abre o exame; o CSV leva a tabela inteira.
"""
from __future__ import annotations

import csv
import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.ai import figado_tabela as FT
from ipe.core.i18n import tr

log = logging.getLogger(__name__)

TITULO = "Fígado na RM: medidas e confirmações"
COLUNAS = ("Data", "Paciente", "ID", "Descrição", "PDFF (%)", "Gordura", "Dupla eco (%)", "R2* (s⁻¹)",
           "LIC (mg Fe/g)", "Ferro", "Rigidez (kPa)", "Rigidez: faixa", "Situação", "Por", "Em")


def _data(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d or "") == 8 else (d or "")


def _num(v, casas=1) -> str:
    return "" if v is None else f"{v:.{casas}f}".replace(".", ",")


def texto_do_resumo(linhas: list[dict]) -> str:
    c = FT.resumo(linhas)
    return (tr("{} exame(s) medido(s), {} revisado(s).").format(c["exames"], c["revisados"]) + " " +
            tr("Gordura: {} medido(s), {} com esteatose (PDFF ≥ 5%).").format(c["pdff"], c["esteatose"]) + " " +
            tr("Ferro: {} medido(s), {} com sobrecarga (LIC ≥ 3,2 mg Fe/g).").format(c["lic"], c["ferro"]) + " " +
            tr("Rigidez: {} medida(s), {} acima do normal.").format(c["kpa"], c["rigidez"]))


class FigadosMedidosJanela(QDialog):
    def __init__(self, main, repo=None, parent=None) -> None:
        super().__init__(parent or (main if isinstance(main, QWidget) else None))
        self.setWindowTitle(tr(TITULO))
        self.main = main
        self.repo = repo if repo is not None else main.repo
        self.linhas: list[dict] = []
        self.vistas: list[dict] = []

        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(QLabel(tr("Exames de")))
        self.de = QDateEdit(QDate.currentDate().addMonths(-3))
        self.de.setCalendarPopup(True)
        self.ate = QDateEdit(QDate.currentDate())
        self.ate.setCalendarPopup(True)
        topo.addWidget(self.de)
        topo.addWidget(QLabel(tr("até")))
        topo.addWidget(self.ate)
        self.sit = QComboBox()
        for k, nome in FT.SITUACOES:
            self.sit.addItem(tr(nome), k)
        self.sit.currentIndexChanged.connect(lambda _i: self.preencher())
        topo.addWidget(self.sit)
        bt = QPushButton(tr("Atualizar"))
        bt.clicked.connect(self.carregar)
        topo.addWidget(bt)
        topo.addStretch(1)
        lay.addLayout(topo)

        self.lb_resumo = QLabel("")
        self.lb_resumo.setWordWrap(True)
        lay.addWidget(self.lb_resumo)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels([tr(c) for c in COLUNAS])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setSortingEnabled(True)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabela.doubleClicked.connect(self.abrir_exame)
        lay.addWidget(self.tabela, 1)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)

        nota = QLabel(tr("Duplo clique abre o exame (em IA ▸ Achados de IA dá para confirmar, corrigir ou descartar). "
                         "Os números são os que valem: os corrigidos pelo médico por cima dos da IA."))
        nota.setStyleSheet("color:gray")
        nota.setWordWrap(True)
        lay.addWidget(nota)
        baixo = QHBoxLayout()
        self.bt_csv = QPushButton(tr("Exportar CSV…"))
        self.bt_csv.clicked.connect(self.exportar)
        fechar = QPushButton(tr("Fechar"))
        fechar.clicked.connect(self.close)
        baixo.addStretch(1)
        baixo.addWidget(self.bt_csv)
        baixo.addWidget(fechar)
        lay.addLayout(baixo)
        self.resize(1300, 600)
        self.carregar()

    def carregar(self) -> None:
        try:
            self.linhas = self.repo.figados_medidos(self.de.date().toString("yyyyMMdd"),
                                                    self.ate.date().toString("yyyyMMdd"))
        except Exception as e:  # noqa: BLE001
            log.debug("fígados medidos", exc_info=True)
            self.linhas = []
            self.lb_resumo.setText(tr("Não consegui ler as medidas do fígado: {} (num servidor central, atualize o "
                                      "servidor para a mesma versão).").format(e))
            self.tabela.setRowCount(0)
            return
        self.preencher()

    def preencher(self) -> None:
        self.vistas = FT.filtrar(self.linhas, self.sit.currentData())
        self.lb_resumo.setText(texto_do_resumo(self.linhas))
        self.tabela.setSortingEnabled(False)
        self.tabela.setRowCount(len(self.vistas))
        for i, r in enumerate(self.vistas):
            grau = "" if r.get("grau") is None else tr(" (grau {})").format(r["grau"])
            valores = (_data(r.get("study_date", "")), r.get("patient_name", ""), r.get("patient_id", ""),
                       r.get("description", ""), _num(r.get("pdff")) + (grau if r.get("pdff") is not None else ""),
                       tr(r.get("gordura") or ""), _num(r.get("ff_sinal")), _num(r.get("r2"), 0),
                       _num(r.get("lic"), 2), tr(r.get("ferro") or ""), _num(r.get("kpa"), 2),
                       tr(r.get("faixa") or ""), tr(FT.situacao(r)), r.get("revisor", ""), r.get("revisado_em", ""))
            numericos = {4: r.get("pdff"), 6: r.get("ff_sinal"), 7: r.get("r2"), 8: r.get("lic"), 10: r.get("kpa")}
            for j, v in enumerate(valores):
                it = QTableWidgetItem(str(v))
                it.setData(Qt.UserRole, r["study_uid"])
                if j == 0:
                    it.setData(Qt.UserRole + 1, r.get("study_date", ""))
                if j in numericos and numericos[j] is not None:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabela.setItem(i, j, it)
        self.tabela.setSortingEnabled(True)

    def abrir_exame(self, idx) -> None:
        it = self.tabela.item(idx.row(), 0)
        uid = it.data(Qt.UserRole) if it is not None else ""
        if uid and hasattr(self.main, "open_study"):
            self.main.open_study(uid)

    def exportar(self) -> None:
        if not self.vistas:
            QMessageBox.information(self, tr(TITULO), tr("Nada para exportar."))
            return
        destino, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV…"), "figado_rm.csv", "CSV (*.csv)")
        if not destino:
            return
        self.gravar_csv(destino)

    def gravar_csv(self, destino: str) -> None:
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(FT.CSV_CAB)
            for r in self.vistas:
                w.writerow(FT.linha_csv(r))


def abrir(main, repo=None):
    j = getattr(main, "_figados_medidos", None)
    if j is not None and j.isVisible():
        j.carregar()
        j.raise_()
        j.activateWindow()
        return j
    j = FigadosMedidosJanela(main, repo)
    main._figados_medidos = j
    j.show()
    return j
