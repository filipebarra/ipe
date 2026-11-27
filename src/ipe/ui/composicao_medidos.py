"""Composição corporal e densidade óssea: medidas e confirmações (0.100.132) — a tabela, como a do fígado na RM.

Uma linha por exame com o resultado da IA de composição corporal e do osso (HU de L1 e de L1–L4). As colunas de DMO
(T-score da coluna e do fêmur) são digitadas aqui, na própria tabela, e ficam guardadas no exame: com elas, o botão
"Comparar com a DMO…" calcula a AUC e o melhor corte do serviço pela curva ROC. Duplo clique abre o exame; o CSV leva
a tabela inteira (com a DMO).
"""
from __future__ import annotations

import csv
import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.ai import composicao_tabela as CT
from ipe.ai import densidade_osso as DO
from ipe.core.i18n import tr

log = logging.getLogger(__name__)

TITULO = "Composição corporal e densidade óssea: medidas e confirmações"
COLUNAS = ("Data", "Paciente", "ID", "Descrição", "Músculo SMA (cm²)", "SMI (cm²/m²)", "VAT (cm²)", "SAT (cm²)",
           "Fígado (HU)", "Osso L1 (HU)", "Osso L1–L4 (HU)", "Osso: resultado", "DMO coluna (T)", "DMO fêmur (T)",
           "DMO: classe", "Situação", "Por", "Em")
C_COLUNA, C_FEMUR = 12, 13


def _data(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d or "") == 8 else (d or "")


def _num(v, casas=1) -> str:
    return "" if v is None else f"{v:.{casas}f}".replace(".", ",")


def texto_do_resumo(linhas: list[dict]) -> str:
    c = CT.resumo(linhas)
    return (tr("{} exame(s) medido(s), {} revisado(s).").format(c["exames"], c["revisados"]) + " " +
            tr("Osso: {} medido(s); DMO digitada em {}; {} com osso e DMO (dá para comparar).")
            .format(c["osso"], c["com_dmo"], c["validaveis"]))


class ComposicaoMedidosJanela(QDialog):
    def __init__(self, main, repo=None, parent=None) -> None:
        super().__init__(parent or (main if isinstance(main, QWidget) else None))
        self.setWindowTitle(tr(TITULO))
        self.main = main
        self.repo = repo if repo is not None else main.repo
        self.linhas: list[dict] = []
        self.vistas: list[dict] = []
        self._preenchendo = False

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
        for k, nome in CT.SITUACOES:
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
        self.tabela.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.tabela.setSortingEnabled(True)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabela.itemChanged.connect(self._digitou)
        lay.addWidget(self.tabela, 1)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)

        nota = QLabel(tr("Digite o T-score da DMO nas colunas \"DMO coluna (T)\" e \"DMO fêmur (T)\" (duplo clique na "
                         "célula; vale a pior das duas). Para abrir o exame, use o botão \"Abrir o exame\". Os "
                         "números são os que valem: os corrigidos pelo médico por cima dos da IA."))
        nota.setStyleSheet("color:gray")
        nota.setWordWrap(True)
        lay.addWidget(nota)
        self.lb_analise = QLabel("")
        self.lb_analise.setWordWrap(True)
        self.lb_analise.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lb_analise)
        baixo = QHBoxLayout()
        self.bt_abrir = QPushButton(tr("Abrir o exame"))
        self.bt_abrir.clicked.connect(self.abrir_exame)
        self.bt_comp = QPushButton(tr("Comparar com a DMO…"))
        self.bt_comp.setToolTip(tr("AUC e melhor corte do HU de L1 e de L1–L4 contra a DMO digitada (curva ROC)."))
        self.bt_comp.clicked.connect(self.comparar)
        self.bt_csv = QPushButton(tr("Exportar CSV…"))
        self.bt_csv.clicked.connect(self.exportar)
        fechar = QPushButton(tr("Fechar"))
        fechar.clicked.connect(self.close)
        baixo.addWidget(self.bt_abrir)
        baixo.addWidget(self.bt_comp)
        baixo.addStretch(1)
        baixo.addWidget(self.bt_csv)
        baixo.addWidget(fechar)
        lay.addLayout(baixo)
        self.resize(1400, 640)
        self.carregar()

    # ------------------------------------------------------------------ dados
    def carregar(self) -> None:
        try:
            self.linhas = self.repo.composicao_medidos(self.de.date().toString("yyyyMMdd"),
                                                       self.ate.date().toString("yyyyMMdd"))
        except Exception as e:  # noqa: BLE001
            log.debug("composição medidos", exc_info=True)
            self.linhas = []
            self.lb_resumo.setText(tr("Não consegui ler as medidas da composição corporal: {} (num servidor central, "
                                      "atualize o servidor para a mesma versão).").format(e))
            self.tabela.setRowCount(0)
            return
        self.preencher()

    def preencher(self) -> None:
        self._preenchendo = True
        self.vistas = CT.filtrar(self.linhas, self.sit.currentData())
        self.lb_resumo.setText(texto_do_resumo(self.linhas))
        self.tabela.setSortingEnabled(False)
        self.tabela.setRowCount(len(self.vistas))
        for i, r in enumerate(self.vistas):
            valores = (_data(r.get("study_date", "")), r.get("patient_name", ""), r.get("patient_id", ""),
                       r.get("description", ""), _num(r.get("sma")), _num(r.get("smi")), _num(r.get("vat")),
                       _num(r.get("sat")), _num(r.get("figado_hu")), _num(r.get("l1")), _num(r.get("l1l4")),
                       r.get("osso", ""), _num(r.get("dmo_coluna")), _num(r.get("dmo_femur")),
                       tr(CT.classe_dmo(CT.dmo_minima(r))), tr(CT.situacao(r)), r.get("revisor", ""),
                       r.get("revisado_em", ""))
            for j, v in enumerate(valores):
                it = QTableWidgetItem(str(v))
                it.setData(Qt.UserRole, r["study_uid"])
                if j not in (C_COLUNA, C_FEMUR):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                elif j in (C_COLUNA, C_FEMUR):
                    it.setBackground(Qt.transparent)
                if 4 <= j <= 10 or j in (C_COLUNA, C_FEMUR):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabela.setItem(i, j, it)
        self.tabela.setSortingEnabled(True)
        self._preenchendo = False

    def _digitou(self, item: QTableWidgetItem) -> None:
        if self._preenchendo or item.column() not in (C_COLUNA, C_FEMUR):
            return
        uid = item.data(Qt.UserRole)
        r = next((x for x in self.linhas if x["study_uid"] == uid), None)
        if r is None:
            return
        txt = item.text().strip()
        valor = CT._t_score(txt)
        if txt and valor is None:
            QMessageBox.information(self, tr(TITULO), tr("Digite o T-score como número (por exemplo −2,1)."))
            self.preencher()
            return
        r["dmo_coluna" if item.column() == C_COLUNA else "dmo_femur"] = valor
        try:
            self.repo.guardar_dmo(uid, {"coluna": r.get("dmo_coluna"), "femur": r.get("dmo_femur"),
                                        "data": r.get("dmo_data", "")})
        except Exception as e:  # noqa: BLE001
            log.debug("guardar DMO", exc_info=True)
            QMessageBox.warning(self, tr(TITULO), tr("Não consegui guardar a DMO: {}").format(e))
        self.preencher()

    # ------------------------------------------------------------------ ações
    def comparar(self) -> None:
        lim = DO.limites(getattr(self.main, "settings", None))
        cortes = {"osteo": lim["osteo"], "baixa": lim["baixa"], "normal": lim["normal"]}
        linhas = []
        for campo in ("l1", "l1l4"):
            for alvo in ("osteoporose", "baixa"):
                linhas.append(CT.texto_da_analise(CT.analise_osso(self.linhas, campo, alvo, cortes)))
        self.lb_analise.setText("\n".join(linhas))

    def abrir_exame(self) -> None:
        it = self.tabela.item(self.tabela.currentRow(), 0)
        uid = it.data(Qt.UserRole) if it is not None else ""
        if uid and hasattr(self.main, "open_study"):
            self.main.open_study(uid)

    def exportar(self) -> None:
        if not self.vistas:
            QMessageBox.information(self, tr(TITULO), tr("Nada para exportar."))
            return
        destino, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV…"), "composicao_osso.csv", "CSV (*.csv)")
        if destino:
            self.gravar_csv(destino)

    def gravar_csv(self, destino: str) -> None:
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(CT.CSV_CAB)
            for r in self.vistas:
                w.writerow(CT.linha_csv(r))


def abrir(main, repo=None):
    j = getattr(main, "_composicao_medidos", None)
    if j is not None and j.isVisible():
        j.carregar()
        j.raise_()
        j.activateWindow()
        return j
    j = ComposicaoMedidosJanela(main, repo)
    main._composicao_medidos = j
    j.show()
    return j
