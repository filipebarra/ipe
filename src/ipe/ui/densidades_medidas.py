"""Densidades medidas (0.100.46): todas as densidades guardadas nos exames, com a confirmação do médico.

Pedido dele: *"quero visualizar um relatório ou uma tela onde essas mensurações e confirmações apareçam"*. Uma linha
por exame medido (botão Densidade ou fila de revisão): a rede da NYU, o % de área por Otsu e por fuzzy, a categoria
confirmada, quem confirmou e quando. Em cima, quantos foram medidos e confirmados e a concordância de cada método com
as confirmações. Duplo clique abre o exame; o CSV leva a tabela inteira.
"""
from __future__ import annotations

import csv
import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.core.i18n import tr
from ipe.imaging import densidade_revisao as R

log = logging.getLogger(__name__)

COLUNAS = ("Data", "Paciente", "ID", "Descrição", "Aparelho", "Rede (NYU)", "Otsu", "Fuzzy", "Confirmada",
           "Por", "Em", "Situação")
SITUACOES = (("todas", "Todas"), ("confirmadas", "Confirmadas"), ("pendentes", "Não confirmadas"),
             ("discordou", "Confirmadas diferente da rede"))


def _data(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d or "") == 8 else (d or "")


def situacao(r: dict) -> str:
    if not r.get("categoria"):
        return "Não confirmada"
    return "Igual à rede" if r["categoria"] == r.get("nyu") else "Diferente da rede"


def filtrar(linhas: list[dict], qual: str) -> list[dict]:
    if qual == "confirmadas":
        return [r for r in linhas if r.get("categoria")]
    if qual == "pendentes":
        return [r for r in linhas if not r.get("categoria")]
    if qual == "discordou":
        return [r for r in linhas if r.get("categoria") and r["categoria"] != r.get("nyu")]
    return list(linhas)


def resumo(linhas: list[dict]) -> str:
    """Quantos medidos e confirmados, e a concordância de cada método com as confirmações."""
    conf = [r for r in linhas if r.get("categoria")]
    texto = tr("{} exame(s) medido(s), {} confirmado(s).").format(len(linhas), len(conf))
    if conf:
        c = R.concordancia([dict(r, controle=False) for r in conf])
        partes = []
        for m, nome in R.METODOS.items():
            t = c["metodos"][m]["total"]
            if t["n"]:
                k = "—" if t["kappa"] is None else f"{t['kappa']:.2f}"
                partes.append(f"{tr(nome)}: {100 * t['exato']:.0f}% {tr('iguais')} (kappa {k}, n = {t['n']})")
        if partes:
            texto += " " + tr("Concordância com as confirmações") + " — " + " · ".join(partes) + "."
    return texto


class DensidadesMedidasJanela(QDialog):
    def __init__(self, main, repo=None, parent=None) -> None:
        super().__init__(parent or (main if isinstance(main, QWidget) else None))
        self.setWindowTitle(tr("Densidades medidas"))
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
        for k, nome in SITUACOES:
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

        nota = QLabel(tr("Duplo clique abre o exame (no botão Densidade dá para confirmar ou trocar a categoria)."))
        nota.setStyleSheet("color:gray")
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
        self.resize(1200, 600)
        self.carregar()

    def carregar(self) -> None:
        try:
            self.linhas = self.repo.densidades_medidas(self.de.date().toString("yyyyMMdd"),
                                                       self.ate.date().toString("yyyyMMdd"))
        except Exception as e:  # noqa: BLE001
            log.debug("densidades medidas", exc_info=True)
            self.linhas = []
            self.lb_resumo.setText(tr("Não consegui ler as densidades: {} (num servidor central, atualize o "
                                      "servidor para a mesma versão).").format(e))
            self.tabela.setRowCount(0)
            return
        self.preencher()

    def preencher(self) -> None:
        self.vistas = filtrar(self.linhas, self.sit.currentData())
        self.lb_resumo.setText(resumo(self.linhas))
        self.tabela.setSortingEnabled(False)
        self.tabela.setRowCount(len(self.vistas))
        for i, r in enumerate(self.vistas):
            probs = r.get("nyu_probs") or []
            nyu = f"{r['nyu'].upper()} ({100 * max(probs):.0f}%)" if r.get("nyu") and probs else (
                r.get("nyu") or "").upper()
            otsu = "" if r.get("area_pd") is None else f"{r['area_pd']:.0f}% ({(r.get('area') or '').upper()})"
            fuzzy = "" if r.get("fcm_pd") is None else f"{r['fcm_pd']:.0f}% ({(r.get('fcm') or '').upper()})"
            conf = (r.get("categoria") or "").upper()
            valores = (_data(r.get("study_date", "")), r.get("patient_name", ""), r.get("patient_id", ""),
                       r.get("description", ""), r.get("aparelho", ""), nyu, otsu, fuzzy, conf,
                       r.get("revisor", "") if conf else "", r.get("quando", "") if conf else "",
                       tr(situacao(r)))
            for j, v in enumerate(valores):
                it = QTableWidgetItem(str(v))
                it.setData(Qt.UserRole, r["study_uid"])
                if j == 0:
                    it.setData(Qt.UserRole + 1, r.get("study_date", ""))
                self.tabela.setItem(i, j, it)
        self.tabela.setSortingEnabled(True)

    def abrir_exame(self, idx) -> None:
        it = self.tabela.item(idx.row(), 0)
        uid = it.data(Qt.UserRole) if it is not None else ""
        if uid and hasattr(self.main, "open_study"):
            self.main.open_study(uid)

    def exportar(self) -> None:
        if not self.vistas:
            QMessageBox.information(self, tr("Densidades medidas"), tr("Nada para exportar."))
            return
        destino, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV…"), "densidades.csv", "CSV (*.csv)")
        if not destino:
            return
        self.gravar_csv(destino)

    def gravar_csv(self, destino: str) -> None:
        cab = ["study_uid", "data", "paciente", "id", "descricao", "aparelho", "nyu", "nyu_a", "nyu_b", "nyu_c",
               "nyu_d", "otsu_pd", "otsu", "fuzzy_pd", "fuzzy", "confirmada", "por", "em", "medido_em"]
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(cab)
            for r in self.vistas:
                p = [str(x) for x in (r.get("nyu_probs") or [])] + [""] * 4
                w.writerow([r["study_uid"], r.get("study_date", ""), r.get("patient_name", ""),
                            r.get("patient_id", ""), r.get("description", ""), r.get("aparelho", ""),
                            r.get("nyu", ""), *p[:4], "" if r.get("area_pd") is None else r["area_pd"],
                            r.get("area", ""), "" if r.get("fcm_pd") is None else r["fcm_pd"], r.get("fcm", ""),
                            r.get("categoria", ""), r.get("revisor", "") if r.get("categoria") else "",
                            r.get("quando", "") if r.get("categoria") else "", r.get("medido_em", "")])


def abrir(main, repo=None):
    j = getattr(main, "_densidades_medidas", None)
    if j is not None and j.isVisible():
        j.carregar()
        j.raise_()
        j.activateWindow()
        return j
    j = DensidadesMedidasJanela(main, repo)
    main._densidades_medidas = j
    j.show()
    return j
