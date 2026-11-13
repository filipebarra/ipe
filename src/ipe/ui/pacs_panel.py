"""Aba "PACS": buscar em nós remotos, baixar estudos/séries e acompanhar as transferências."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ipe.network import nodes as NODES
from ipe.network.service import STATUS_TEXT, Job, NetworkService
from ipe.ui.tabelas import colunas_ajustaveis

ALL_NODES = -1
STUDY_COLS = ["Paciente", "ID", "Nascimento", "Data", "Mod.", "Descrição", "Accession", "Séries",
              "Imagens", "Nó", "No computador"]
PERIODS = [("Hoje", 0), ("Ontem e hoje", 1), ("Últimos 7 dias", 7), ("Últimos 30 dias", 30),
           ("Último ano", 365), ("Qualquer data", None), ("Data exata…", "one"), ("Intervalo…", "range")]


def fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 and d.isdigit() else d


class PacsPanel(QWidget):
    open_study = Signal(str)
    configure_requested = Signal()

    def __init__(self, net: NetworkService, repo, parent=None):
        super().__init__(parent)
        self.net, self.repo = net, repo
        self.settings = net.settings
        self._busy = False

        # --- filtros
        self.node = QComboBox()
        self.node.setMinimumWidth(180)
        self.node.currentIndexChanged.connect(self._fill_identities)
        self.identity = QComboBox()
        self.identity.setToolTip("AE Title de origem da busca e do download")
        self.name = QLineEdit(placeholderText="Nome (ex.: SILVA, SILVA^MARIA ou *SILVA*)")
        self.pid = QLineEdit(placeholderText="ID do paciente")
        self.acc = QLineEdit(placeholderText="Accession")
        self.desc = QLineEdit(placeholderText="Descrição do estudo")
        self.mod = QComboBox()
        self.mod.setEditable(True)                 # dá para digitar mais de uma: "CT, MR"
        self.mod.setToolTip("Modalidade do exame; aceita mais de uma separada por vírgula (ex.: CT, MR)")
        self.mod.addItems(["Todas", "CT", "MR", "MG", "US", "CR", "DX", "PT", "NM", "XA", "RF", "SR", "OT"])
        self.mod.lineEdit().returnPressed.connect(self.search)
        self.period = QComboBox()
        for label, _d in PERIODS:
            self.period.addItem(label)
        self.period.setCurrentIndex(2)
        self.period.currentIndexChanged.connect(self._period_changed)
        hoje = QDate.currentDate()
        self.date_a = QDateEdit(hoje)
        self.date_b = QDateEdit(hoje)
        for d in (self.date_a, self.date_b):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.setVisible(False)
        self.lbl_ate = QLabel("até")
        self.lbl_ate.setVisible(False)
        for w in (self.name, self.pid, self.acc, self.desc):
            w.returnPressed.connect(self.search)
        self.btn_search = QPushButton("Buscar")
        self.btn_search.setDefault(True)
        self.btn_search.clicked.connect(self._search_or_stop)
        self._cancel = None
        btn_cfg = QPushButton("Configurar nós…")
        btn_cfg.clicked.connect(self.configure_requested.emit)

        row1 = QHBoxLayout()
        for lab, w in (("Nó:", self.node), ("Como:", self.identity)):
            row1.addWidget(QLabel(lab))
            row1.addWidget(w)
        row1.addStretch(1)
        row1.addWidget(btn_cfg)
        row2 = QHBoxLayout()
        for w, st in ((self.name, 3), (self.pid, 1), (self.acc, 1), (self.desc, 2)):
            row2.addWidget(w, st)
        row2.addWidget(self.mod)
        row2.addWidget(self.period)
        row2.addWidget(self.date_a)
        row2.addWidget(self.lbl_ate)
        row2.addWidget(self.date_b)
        row2.addWidget(self.btn_search)

        # --- resultados
        self.results = QTreeWidget()
        self.results.setColumnCount(len(STUDY_COLS))
        self.results.setHeaderLabels(STUDY_COLS)
        self.results.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results.setSortingEnabled(True)
        self.results.itemExpanded.connect(self._expand)
        self.results.itemDoubleClicked.connect(self._double_click)
        self.results.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self._menu)
        colunas_ajustaveis(self.results)
        self.info = QLabel("Escolha o nó e busque. Clique na seta de um estudo para ver as séries.")
        b_get = QPushButton("Baixar")
        b_get.clicked.connect(lambda: self.retrieve_selected(False))
        b_open = QPushButton("Baixar e abrir")
        b_open.clicked.connect(lambda: self.retrieve_selected(True))
        acts = QHBoxLayout()
        acts.addWidget(self.info, 1)
        acts.addWidget(b_get)
        acts.addWidget(b_open)

        # --- transferências
        self.jobs = QTreeWidget()
        self.jobs.setColumnCount(4)
        self.jobs.setHeaderLabels(["Transferência", "Nó", "Situação", "Progresso"])
        self.jobs.setRootIsDecorated(False)
        self.jobs.header().setSectionResizeMode(0, QHeaderView.Stretch)
        colunas_ajustaveis(self.jobs)
        self._job_items: dict[int, QTreeWidgetItem] = {}
        self._enviar_depois: dict = {}          # download → envios que esperam por ele
        b_cancel = QPushButton("Cancelar")
        b_cancel.clicked.connect(self._cancel_selected)
        b_clear = QPushButton("Limpar concluídas")
        b_clear.clicked.connect(self._clear_finished)
        jb = QHBoxLayout()
        jb.addWidget(QLabel("<b>Transferências</b>"))
        jb.addStretch(1)
        jb.addWidget(b_cancel)
        jb.addWidget(b_clear)

        top_w, bot_w = QWidget(), QWidget()
        tl = QVBoxLayout(top_w)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.results, 1)
        tl.addLayout(acts)
        bl = QVBoxLayout(bot_w)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addLayout(jb)
        bl.addWidget(self.jobs, 1)
        split = QSplitter(Qt.Vertical)
        split.addWidget(top_w)
        split.addWidget(bot_w)
        split.setSizes([500, 180])

        root = QVBoxLayout(self)
        root.addLayout(row1)
        root.addLayout(row2)
        root.addWidget(split, 1)

        net.job_changed.connect(self._job_changed)
        self.refresh_nodes()

    # ------------------------------------------------------------ nós
    def _search_or_stop(self) -> None:
        """O mesmo botão busca e, durante a busca, interrompe."""
        if self._cancel is not None:
            self.stop_search()
        else:
            self.search()

    def refresh_nodes(self) -> None:
        cur = self.node.currentData()
        self.node.blockSignals(True)
        self.node.clear()
        nodes = [n for n in self.repo.nodes(only_active=True) if n["kind"] in NODES.CONSULTA]
        if len([n for n in nodes if n["use_in_search"]]) > 1:
            self.node.addItem("Todos os nós de busca", ALL_NODES)
        for n in nodes:
            if n.get("kind") == "servidor":
                self.node.addItem(n["name"], n["id"])
            else:
                self.node.addItem(f"{n['name']}  ({n['ae_title']}@{n['host']})", n["id"])
        if not nodes:
            self.node.addItem("(nenhum nó cadastrado — clique em Configurar nós…)", None)
        i = self.node.findData(cur)
        self.node.setCurrentIndex(max(0, i))
        self.node.blockSignals(False)
        self._fill_identities()

    def _fill_identities(self) -> None:
        self.identity.clear()
        self.identity.addItem(f"Este programa ({self.net.local_ae})", None)
        node = self._single_node()
        idents = self.net.identities_for(node) if node else self.repo.identities()
        for i in idents:
            self.identity.addItem(f"{i['name']} ({i['ae_title']})", i["id"])

    def _single_node(self) -> dict | None:
        nid = self.node.currentData()
        return self.repo.node(nid) if nid not in (None, ALL_NODES) else None

    def _nodes(self) -> list[dict]:
        nid = self.node.currentData()
        if nid is None:
            return []
        if nid == ALL_NODES:
            return [n for n in self.repo.nodes(only_active=True)
                    if n["use_in_search"] and n["kind"] in NODES.CONSULTA]
        n = self.repo.node(nid)
        return [n] if n else []

    def _identity(self) -> dict | None:
        return self.repo.identity(self.identity.currentData())

    # ------------------------------------------------------------ busca
    def _period_changed(self) -> None:
        modo = PERIODS[self.period.currentIndex()][1]
        self.date_a.setVisible(modo in ("one", "range"))
        self.lbl_ate.setVisible(modo == "range")
        self.date_b.setVisible(modo == "range")

    def filters(self) -> dict:
        modo = PERIODS[self.period.currentIndex()][1]
        today = date.today()
        d_from = d_to = ""
        if modo == "one":
            d_from = d_to = self.date_a.date().toString("yyyyMMdd")
        elif modo == "range":
            a, b = self.date_a.date(), self.date_b.date()
            if a > b:
                a, b = b, a
            d_from, d_to = a.toString("yyyyMMdd"), b.toString("yyyyMMdd")
        elif modo is not None:
            d_from = (today - timedelta(days=int(modo))).strftime("%Y%m%d")
            d_to = today.strftime("%Y%m%d")
        mod = self.mod.currentText().strip()
        if mod.lower() in ("todas", "todos"):
            mod = ""
        else:                                    # "ct, mr" -> "CT\\MR" (como o padrão espera)
            mod = "\\".join(m.strip().upper() for m in mod.replace(";", ",").split(",") if m.strip())
        return {"name": self.name.text(), "patient_id": self.pid.text(), "accession": self.acc.text(),
                "description": self.desc.text(), "modality": mod,
                "date_from": d_from, "date_to": d_to}

    def search(self) -> None:
        from ipe.auth import session as S
        if not S.require("query", self):
            return
        nodes = self._nodes()
        if not nodes:
            QMessageBox.information(self, "PACS", "Cadastre um nó em Configurar nós… primeiro.")
            return
        f = self.filters()
        if not any(f[k] for k in ("name", "patient_id", "accession", "description")) and not f["date_from"]:
            if QMessageBox.question(self, "PACS", "Buscar sem filtro nem período pode trazer muitos "
                                    "estudos e pesar no PACS. Continuar?") != QMessageBox.Yes:
                return
        import threading
        self._cancel = threading.Event()
        self.btn_search.setText("Parar")
        self.btn_search.setToolTip("Interromper a busca e mostrar o que já chegou")
        self.info.setText("Buscando… (clique em Parar para interromper)")
        self.results.clear()
        S.audit(self.repo, "busca", f"{', '.join(n['name'] for n in nodes)}: "
                + ", ".join(f"{k}={v}" for k, v in f.items() if v))
        self.net.search(nodes, self._identity(), f, self._search_done, cancel=self._cancel)

    def stop_search(self) -> None:
        """Interrompe a busca em andamento; o que já chegou continua na tela."""
        if self._cancel is not None:
            self._cancel.set()
            self.info.setText("Interrompendo a busca…")

    def _search_done(self, res, err) -> None:
        interrompida = self._cancel is not None and self._cancel.is_set()
        self._cancel = None
        self.btn_search.setText("Buscar")
        self.btn_search.setToolTip("")
        self.btn_search.setEnabled(True)
        if err is not None:
            self.info.setText(f"Erro: {err}")
            return
        rows, errors = res
        self.show_results(rows)
        msg = (f"{len(rows)} estudo(s) até parar a busca." if interrompida
               else f"{len(rows)} estudo(s) encontrado(s).")
        if errors:
            msg += "  ⚠ " + "  ".join(errors)
        self.info.setText(msg)

    def show_results(self, rows: list[dict]) -> None:
        self.results.setSortingEnabled(False)
        self.results.clear()
        local = self.repo.instance_counts([r["study_uid"] for r in rows])
        for r in rows:
            n_local = local.get(r["study_uid"], 0)
            if n_local and r["num_images"] and n_local >= r["num_images"]:
                here = "✓ sim"
            elif n_local:
                here = f"parcial ({n_local})"
            else:
                here = "—"
            vals = [r["patient_name"], r["patient_id"], fmt_date(r["birth_date"]), fmt_date(r["study_date"]),
                    r["modalities"], r["description"], r["accession"], str(r["num_series"] or ""),
                    str(r["num_images"] or ""), r.get("node_name", ""), here]
            it = QTreeWidgetItem(vals)
            it.setData(0, Qt.UserRole, r)
            if n_local:
                it.setForeground(10, QBrush(QColor(120, 220, 120)))
            it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            self.results.addTopLevelItem(it)
        self.results.setSortingEnabled(True)
        self.results.sortByColumn(3, Qt.DescendingOrder)
        for c in range(len(STUDY_COLS)):
            self.results.resizeColumnToContents(c)
        self.results.setColumnWidth(5, min(self.results.columnWidth(5), 300))

    def _expand(self, item: QTreeWidgetItem) -> None:
        r = item.data(0, Qt.UserRole)
        if r is None or item.childCount() or item.data(1, Qt.UserRole) == "loading":
            return
        node = self.repo.node(r["node_id"])
        item.setData(1, Qt.UserRole, "loading")

        def done(series, err) -> None:
            item.setData(1, Qt.UserRole, None)
            if err is not None:
                child = QTreeWidgetItem([f"Erro: {err}"])
                item.addChild(child)
                return
            locais = self.repo.series_instance_counts([x["series_uid"] for x in series])
            for s in series:
                n_local = locais.get(s["series_uid"], 0)
                if n_local and s["num_images"] and n_local >= s["num_images"]:
                    aqui = "✓ sim"
                elif n_local:
                    aqui = f"parcial ({n_local})"
                else:
                    aqui = "—"
                c = QTreeWidgetItem([f"Série {s['series_number']}", "", "", "", s["modality"], s["description"],
                                     "", "", str(s["num_images"] or ""), "", aqui])
                if n_local:
                    c.setForeground(10, QBrush(QColor(120, 220, 120)))
                c.setData(0, Qt.UserRole + 1, s)
                c.setFlags(c.flags() | Qt.ItemIsUserCheckable)
                c.setCheckState(0, Qt.Unchecked)
                item.addChild(c)
            if not series:
                item.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)
        self.net.series(node, self._identity(), r["study_uid"], done)

    # ------------------------------------------------------------ download
    def _study_items(self) -> list[QTreeWidgetItem]:
        out = []
        for it in self.results.selectedItems():
            top = it if it.parent() is None else it.parent()
            if top not in out:
                out.append(top)
        return out

    def retrieve_selected(self, open_after: bool) -> None:
        items = self._study_items()
        if not items:
            QMessageBox.information(self, "PACS", "Selecione um ou mais estudos.")
            return
        for it in items:
            r = it.data(0, Qt.UserRole)
            checked = [it.child(i).data(0, Qt.UserRole + 1)["series_uid"] for i in range(it.childCount())
                       if it.child(i).checkState(0) == Qt.Checked and it.child(i).data(0, Qt.UserRole + 1)]
            self.retrieve(r, checked or None, open_after and it is items[0])

    def retrieve(self, r: dict, series_uids: list[str] | None, open_after: bool) -> Job | None:
        from ipe.auth import session as S
        if not S.require("retrieve", self):
            return None
        node = self.repo.node(r["node_id"])
        S.audit(self.repo, "baixar", f"{node['name'] if node else ''}: {r.get('patient_name', '')} "
                f"{r.get('study_date', '')} {r.get('modalities', '')}", study_uid=r["study_uid"])
        label = f"{r['patient_name']} — {fmt_date(r['study_date'])} {r['modalities']} {r['description']}"
        if series_uids:
            label += f" ({len(series_uids)} série(s))"
        stream = self._want_stream(node, r, open_after)
        return self.net.retrieve(node, self._identity(), r["study_uid"], label, series_uids, open_after, stream)

    def _want_stream(self, node: dict | None, r: dict, open_after: bool) -> bool:
        """Abrir enquanto baixa? Usa a opção do nó ou, se o download parecer demorado, pergunta."""
        from ipe.network import probe
        if not open_after or (node or {}).get("kind") == "servidor":
            return False
        if node is not None and node.get("stream_open") is not None:
            return bool(node["stream_open"])
        if probe.stream_enabled(node, self.settings):
            return True
        est = probe.estimate(self.settings, (node or {}).get("id"), int(r.get("num_images") or 0),
                             r.get("modalities", ""))
        if not probe.should_ask(self.settings, est["seconds"]):
            return False
        box = QMessageBox(QMessageBox.Question, "Abrir enquanto baixa",
                          f"<b>{r.get('description', '')} — {r.get('num_images') or '?'} imagens "
                          f"(~{probe.fmt_size(est['mb'])})</b><br><br>"
                          f"Nesta rede ({est['mbps']:.1f} MB/s"
                          + (f", resposta {est['ms']:.0f} ms" if est.get("ms") else "")
                          + (")" if est["known"] else ", estimado)")
                          + f", o download deve levar cerca de <b>{probe.fmt_time(est['seconds'])}</b>.<br><br>"
                          "Abrir o exame assim que as primeiras imagens chegarem? O resto entra sozinho, "
                          "conforme baixa.", parent=self)
        b_stream = box.addButton("Abrir enquanto baixa", QMessageBox.AcceptRole)
        box.addButton("Esperar terminar", QMessageBox.RejectRole)
        always = QCheckBox("Fazer sempre assim neste nó")
        box.setCheckBox(always)
        box.exec()
        want = box.clickedButton() is b_stream
        if always.isChecked() and node is not None:
            self.repo.save_node({**node, "stream_open": want})
        return want

    def _double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        top = item if item.parent() is None else item.parent()
        r = top.data(0, Qt.UserRole)
        if r is None:
            return
        if self.repo.study_info(r["study_uid"]) and top.text(10).startswith("✓"):
            self.open_study.emit(r["study_uid"])
        else:
            self.retrieve(r, None, True)

    def _menu(self, pos) -> None:
        if not self._study_items():
            return
        self.menu_dos_resultados().exec(self.results.viewport().mapToGlobal(pos))

    def menu_dos_resultados(self) -> QMenu:
        """Monta o menu do botão direito (separado de quem exibe, para poder testar)."""
        m = QMenu(self)
        m.addAction("Baixar", lambda: self.retrieve_selected(False))
        m.addAction("Baixar e abrir", lambda: self.retrieve_selected(True))
        # Pedido dele (11/10/2026): o mesmo “Enviar para” da lista do banco, com a escolha de
        # mandar como outra modalidade (identidade). O exame é baixado antes, se ainda não está aqui.
        from ipe.auth import session as S
        from ipe.ui.send_menu import preencher_envio
        envio = m.addMenu("Enviar para")
        preencher_envio(envio, self.repo, self.enviar_para)
        envio.setEnabled(S.can("send"))
        # Pedido dele (10/10/2026): "Baixar para" — o exame vai do nó direto para o destino
        # escolhido (C-MOVE com outro destino), e não para este programa.
        sub = m.addMenu("Baixar para")
        origens = {it.data(0, Qt.UserRole)["node_id"] for it in self._study_items()
                   if it.data(0, Qt.UserRole)}
        nos_origem = [self.repo.node(i) for i in origens]
        if any(n and n.get("kind") == "dicomweb" for n in nos_origem):
            sub.setEnabled(False)
            sub.setToolTip("Nó DICOMweb não faz C-MOVE: não manda para outro destino.")
            return m
        destinos = [n for n in self.repo.nodes(only_active=True)
                    if n.get("kind", "dimse") == "dimse" and n["ae_title"] and n["id"] not in origens]
        for n in destinos:
            sub.addAction(f"{n['name']}  ({n['ae_title']})",
                          lambda ae=n["ae_title"], nome=n["name"]: self.baixar_para(ae, nome))
        if destinos:
            sub.addSeparator()
        sub.addAction("Outro AE…", self._baixar_para_outro)
        return m

    def _baixar_para_outro(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        ae, ok = QInputDialog.getText(self, "Baixar para", "AE de destino (o nó de origem precisa "
                                      "conhecer esse AE — IP e porta cadastrados nele):")
        if ok and ae.strip():
            self.baixar_para(ae.strip().upper()[:16], ae.strip())

    def baixar_para(self, destino_ae: str, nome: str = "") -> list:
        """Manda os estudos (ou as séries marcadas) do nó direto para outro destino."""
        from ipe.auth import session as S
        items = self._study_items()
        if not items or not S.require("send", self, "mandar exames para outro destino"):
            return []
        jobs = []
        for it in items:
            r = it.data(0, Qt.UserRole)
            node = self.repo.node(r["node_id"])
            if node is None:
                continue
            checked = [it.child(i).data(0, Qt.UserRole + 1)["series_uid"] for i in range(it.childCount())
                       if it.child(i).checkState(0) == Qt.Checked and it.child(i).data(0, Qt.UserRole + 1)]
            # o mesmo rótulo do "Baixar", e o destino junto (sem criar padrão de tradução genérico)
            label = f"{r['patient_name']} — {fmt_date(r['study_date'])} {r['modalities']} {r['description']}"
            label = label + "  ➜ " + (nome or destino_ae)
            if checked:
                label += f" ({len(checked)} série(s))"
            S.audit(self.repo, "baixar para", f"de {node['name']} para {destino_ae}: "
                    f"{r.get('patient_name', '')} {r.get('study_date', '')} {r.get('modalities', '')}",
                    study_uid=r["study_uid"])
            jobs.append(self.net.move_to(node, self._identity(), r["study_uid"], label, destino_ae,
                                         checked or None))
        return jobs

    def enviar_para(self, node_id: int, identity_id: int | None) -> list:
        """Envia os estudos (ou as séries marcadas) para `node_id`, como a identidade escolhida.

        O envio sai deste programa (C-STORE), por isso o exame precisa estar aqui: o que já está
        completo vai na hora; o resto entra na fila de download e é enviado quando terminar.
        """
        from ipe.auth import session as S
        items = self._study_items()
        if not items or not S.require("send", self):
            return []
        node = self.repo.node(node_id)
        if node is None:
            return []
        ident = self.repo.identity(identity_id) if identity_id is not None else None
        jobs = []
        for it in items:
            r = it.data(0, Qt.UserRole)
            if not r:
                continue
            marcadas = [it.child(i).data(0, Qt.UserRole + 1) for i in range(it.childCount())
                        if it.child(i).checkState(0) == Qt.Checked and it.child(i).data(0, Qt.UserRole + 1)]
            series = [x["series_uid"] for x in marcadas] or None
            label = f"{r['patient_name']} — {fmt_date(r['study_date'])} {r['modalities']} {r['description']}"
            label = label + "  ➜ " + node["name"] + (f" ({ident['ae_title']})" if ident else "")
            if series:
                label += f" ({len(series)} série(s))"
            pedido = (node, ident, r["study_uid"], series, label)
            if self._ja_esta_aqui(r, marcadas):
                jobs.append(self._enviar(*pedido))
                continue
            baixa = self.retrieve(r, series, False)
            if baixa is None:
                continue
            self._enviar_depois.setdefault(baixa.id, []).append(pedido)
            jobs.append(baixa)
        return jobs

    def _ja_esta_aqui(self, r: dict, series: list[dict]) -> bool:
        if series:
            n = self.repo.series_instance_counts([x["series_uid"] for x in series])
            return all(x.get("num_images") and n.get(x["series_uid"], 0) >= x["num_images"] for x in series)
        n = self.repo.instance_counts([r["study_uid"]]).get(r["study_uid"], 0)
        return bool(n and r.get("num_images") and n >= int(r["num_images"]))

    def _enviar(self, node: dict, ident: dict | None, study_uid: str, series, label: str) -> Job:
        from ipe.auth import session as S
        S.audit(self.repo, "enviar", f"{node['name']}" + (f" como {ident['ae_title']}" if ident else "")
                + f": {label}", study_uid=study_uid)
        return self.net.send(node, ident, [study_uid], label, series)

    # ------------------------------------------------------------ fila
    def _job_changed(self, job: Job) -> None:
        it = self._job_items.get(job.id)
        if it is None:
            seta = {"retrieve": "⬇ ", "moveto": "➜ "}.get(job.kind, "⬆ ")
            it = QTreeWidgetItem([seta + job.label,
                                  job.node.get("name", ""), "", ""])
            it.setData(0, Qt.UserRole, job.id)
            self.jobs.insertTopLevelItem(0, it)
            bar = QProgressBar()
            bar.setTextVisible(True)
            self.jobs.setItemWidget(it, 3, bar)
            self._job_items[job.id] = it
        it.setText(2, STATUS_TEXT.get(job.status, job.status) + (f" — {job.message}" if job.message
                                                                    and job.status != "running" else ""))
        it.setToolTip(2, job.message)
        bar = self.jobs.itemWidget(it, 3)
        if bar is not None:
            if job.status == "running" and not job.total:
                bar.setRange(0, 0)                       # animação "trabalhando"
            elif job.total:
                bar.setRange(0, job.total)
                bar.setValue(job.done)
            else:
                bar.setRange(0, 1)
                bar.setValue(1 if job.status == "done" else 0)
            bar.setFormat(job.message if job.status == "running" and job.message else
                          ("%p%" if job.total else ""))
        color = {"error": QColor(255, 120, 120), "done": QColor(120, 220, 120)}.get(job.status)
        if color:
            it.setForeground(2, QBrush(color))
        # atualiza a coluna "No computador" quando o download termina
        if job.kind == "retrieve" and job.status == "done":
            self._mark_local(job.study_uids[0])
        # envio esperando este download: vai quando termina; se falhou, fica registrado na fila
        if job.kind == "retrieve" and job.status in ("done", "error", "cancelled"):
            for pedido in self._enviar_depois.pop(job.id, []):
                if job.status == "done":
                    self._enviar(*pedido)
                else:
                    it.setToolTip(2, f"{job.message}\n" + "Envio não feito: " + pedido[4])

    def _mark_local(self, study_uid: str) -> None:
        n = self.repo.instance_counts([study_uid]).get(study_uid, 0)
        for i in range(self.results.topLevelItemCount()):
            it = self.results.topLevelItem(i)
            r = it.data(0, Qt.UserRole)
            if r and r["study_uid"] == study_uid:
                it.setText(10, "✓ sim" if not r["num_images"] or n >= r["num_images"] else f"parcial ({n})")
                it.setForeground(10, QBrush(QColor(120, 220, 120)))

    def _cancel_selected(self) -> None:
        ids = {it.data(0, Qt.UserRole) for it in self.jobs.selectedItems()}
        for j in self.net.jobs:
            if j.id in ids:
                self.net.cancel(j)

    def _clear_finished(self) -> None:
        self.net.clear_finished()
        keep = {j.id for j in self.net.jobs}
        for jid, it in list(self._job_items.items()):
            if jid not in keep:
                self.jobs.takeTopLevelItem(self.jobs.indexOfTopLevelItem(it))
                del self._job_items[jid]
