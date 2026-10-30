"""Painel de anteriores (linha do tempo do paciente) ao lado do viewer.

Junta os estudos do banco local com os que existem nos nós de busca (C-FIND pelo
PatientID). Mostra se cada um já está no computador, baixando ou só no PACS, e
deixa baixar e comparar sem sair do exame.
"""

from __future__ import annotations

import re
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

_CACHE: dict[str, tuple[float, list[dict]]] = {}      # PatientID -> (quando, resultados remotos)
CACHE_SECONDS = 300


def fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 and d.isdigit() else d
from ipe.ui.tabelas import colunas_ajustaveis


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-zà-ú0-9]+", (text or "").lower()) if len(w) > 3}


class PriorsPanel(QWidget):
    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.tab = tab
        self.setFixedWidth(300)
        self.setStyleSheet("QWidget{background:#1b1c1f;color:#ddd}"
                           "QTreeWidget{background:#151515;border:none}"
                           "QHeaderView::section{background:#26272b;color:#bbb;border:none;padding:3px}")
        info = tab.study_info
        self.pid = info.get("patient_id", "")
        self.title = QLabel(f"<b>Exames do paciente</b><br>{'' if tab.anonymize else info.get('patient_name', '')}")
        self.filter = QComboBox()
        self.filter.addItems(["Todos", "Mesma modalidade", "Mesma região"])
        self.filter.currentIndexChanged.connect(self.render)
        btn = QPushButton("Atualizar")
        btn.clicked.connect(lambda: self.refresh(force=True))
        from PySide6.QtWidgets import QMenu, QToolButton
        self.nodes_btn = QToolButton()
        self.nodes_btn.setText("Nós ▾")
        self.nodes_btn.setToolTip("Em quais nós procurar os anteriores")
        self.nodes_btn.setPopupMode(QToolButton.InstantPopup)
        self.nodes_menu = QMenu(self)
        self.nodes_menu.aboutToShow.connect(self._fill_nodes_menu)
        self.nodes_btn.setMenu(self.nodes_menu)
        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(self.nodes_btn)
        top.addWidget(btn)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Data", "Mod.", "Descrição", "Situação"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self.compare(it.data(0, Qt.UserRole)))
        self.status = QLabel("")
        self.status.setWordWrap(True)
        b_cmp = QPushButton("Baixar / comparar")
        b_cmp.clicked.connect(lambda: [self.compare(it.data(0, Qt.UserRole)) for it in self.tree.selectedItems()])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.title)
        lay.addLayout(top)
        lay.addWidget(self.tree, 1)
        colunas_ajustaveis(self.tree)
        lay.addWidget(b_cmp)
        lay.addWidget(self.status)
        self.remote: list[dict] = []
        self._compare_after: set[str] = set()
        self._update_nodes_label()
        net = getattr(tab, "net", None)
        if net is not None:
            net.job_changed.connect(self._job_changed)
            net.job_finished.connect(self._job_finished)
        self.refresh()

    # ------------------------------------------------------------ nós
    def _fill_nodes_menu(self) -> None:
        from PySide6.QtGui import QAction
        from ipe.network.nodes import prior_candidates, prior_selection
        m = self.nodes_menu
        m.clear()
        cands = prior_candidates(self.tab.repo)
        sel = prior_selection(self.tab.settings)
        a = QAction("Todos os nós de anteriores", m, checkable=True, checked=sel is None)
        a.triggered.connect(lambda: self.set_nodes(None))
        m.addAction(a)
        m.addSeparator()
        if not cands:
            x = QAction("(nenhum nó marcado para anteriores)", m)
            x.setEnabled(False)
            m.addAction(x)
        for n in cands:
            on = sel is not None and n["id"] in sel
            b = QAction(f"{n['name']}  ({n['ae_title']})", m, checkable=True, checked=on)
            b.triggered.connect(lambda checked, nid=n["id"]: self.toggle_node(nid, checked))
            m.addAction(b)

    def set_nodes(self, ids: list[int] | None) -> None:
        from ipe.network.nodes import set_prior_selection
        set_prior_selection(self.tab.settings, ids)
        self._update_nodes_label()
        self.refresh(force=True)

    def toggle_node(self, nid: int, on: bool) -> None:
        from ipe.network.nodes import prior_selection
        sel = set(prior_selection(self.tab.settings) or [])
        (sel.add if on else sel.discard)(nid)
        self.set_nodes(sorted(sel) if sel else None)

    def _update_nodes_label(self) -> None:
        from ipe.network.nodes import prior_nodes, prior_selection
        sel = prior_selection(self.tab.settings)
        n = len(prior_nodes(self.tab.repo, self.tab.settings))
        self.nodes_btn.setText("Nós: todos ▾" if sel is None else f"Nós: {n} ▾")

    # ------------------------------------------------------------ dados
    def refresh(self, force: bool = False) -> None:
        self.render()
        net = getattr(self.tab, "net", None)
        if net is None or not self.pid:
            self.status.setText("Sem ID do paciente ou sem rede: mostrando só o banco local."
                                if not self.pid else "")
            return
        from ipe.network.nodes import prior_nodes
        nodes = prior_nodes(self.tab.repo, self.tab.settings)
        if not nodes:
            self.status.setText("Nenhum nó para anteriores: marque “Busca de anteriores” no cadastro do nó "
                                "(Rede → Configurar nós) ou escolha os nós no botão Nós.")
            return
        key = (self.pid, tuple(sorted(n["id"] for n in nodes)))
        cached = _CACHE.get(key)
        if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
            self.remote = cached[1]
            self.render()
            return
        self.status.setText("Consultando o PACS…")

        def done(res, err) -> None:
            if err is not None:
                self.status.setText(f"Erro: {err}")
                return
            rows, errors = res
            self.remote = rows
            _CACHE[key] = (time.time(), rows)
            self.status.setText("  ".join(errors) if errors else f"{len(rows)} exame(s) no PACS.")
            self.render()
        net.search(nodes, None, {"patient_id": self.pid}, done)

    def entries(self) -> list[dict]:
        repo = self.tab.repo
        local = {r.study_uid: r for r in repo.studies_of_patient(self.pid)} if self.pid else {}
        counts = repo.instance_counts(list(local))
        out: dict[str, dict] = {}
        for uid, r in local.items():
            out[uid] = {"study_uid": uid, "study_date": r.study_date, "modalities": r.modalities,
                        "description": r.description, "num_images": r.num_images, "local": counts.get(uid, 0),
                        "node_id": None, "node_name": "banco local"}
        for r in self.remote:
            e = out.get(r["study_uid"])
            if e is None:
                out[r["study_uid"]] = {**r, "local": 0}
            else:
                e["node_id"], e["node_name"] = r["node_id"], r["node_name"]
                e["num_images"] = max(e["num_images"] or 0, r["num_images"] or 0)
        cur = self.tab.study_info
        items = sorted(out.values(), key=lambda e: e.get("study_date", ""), reverse=True)
        f = self.filter.currentIndex()
        if f == 1:
            mods = set((cur.get("modalities") or "").split("\\"))
            items = [e for e in items if mods & set((e.get("modalities") or "").split("\\"))]
        elif f == 2:
            words = _words(cur.get("description", ""))
            items = [e for e in items if e["study_uid"] == self.tab.study_uid or words & _words(e.get("description", ""))]
        return items

    def _state(self, e: dict) -> tuple[str, QColor]:
        net = getattr(self.tab, "net", None)
        if e["study_uid"] in self.tab.study_order:
            return "aberto", QColor(255, 210, 120)
        if net is not None:
            for j in net.active_jobs():
                if j.kind == "retrieve" and j.study_uids == [e["study_uid"]]:
                    pct = f" {int(100 * j.done / j.total)}%" if j.total else ""
                    return f"⬇ baixando{pct}", QColor(120, 190, 255)
        if e["local"] and (not e["num_images"] or e["local"] >= e["num_images"]):
            return "✓ no computador", QColor(120, 220, 120)
        if e["local"]:
            return f"parcial ({e['local']})", QColor(220, 200, 120)
        return "só no PACS", QColor(170, 170, 170)

    def render(self) -> None:
        self.tree.clear()
        for e in self.entries():
            state, color = self._state(e)
            it = QTreeWidgetItem([fmt_date(e.get("study_date", "")), e.get("modalities", ""),
                                  e.get("description", ""), state])
            it.setData(0, Qt.UserRole, e)
            it.setForeground(3, QBrush(color))
            it.setToolTip(2, f"{e.get('description', '')} — {e.get('num_images') or '?'} imagens — {e['node_name']}")
            self.tree.addTopLevelItem(it)
        for c in (0, 1, 3):
            self.tree.resizeColumnToContents(c)

    # ------------------------------------------------------------ ações
    def compare(self, e: dict | None) -> None:
        if not e or e["study_uid"] == self.tab.study_uid:
            return
        uid = e["study_uid"]
        complete = e["local"] and (not e["num_images"] or e["local"] >= e["num_images"])
        if complete or e.get("node_id") is None:
            self.tab.open_prior(uid)
            self.render()
            return
        net = self.tab.net
        node = self.tab.repo.node(e["node_id"])
        net.retrieve(node, None, uid, f"Anterior: {e.get('study_date', '')} {e.get('modalities', '')} "
                                      f"{e.get('description', '')}")
        self._compare_after.add(uid)
        self.status.setText("Baixando; o exame entra na comparação quando terminar.")
        self.render()

    def _job_changed(self, job) -> None:
        if job.kind == "retrieve" and self.isVisible():
            self.render()

    def _job_finished(self, job) -> None:
        if job.kind != "retrieve":
            return
        uid = job.study_uids[0]
        if uid in self._compare_after and job.status == "done":
            self._compare_after.discard(uid)
            self.tab.open_prior(uid)
        if self.isVisible():
            self.render()
