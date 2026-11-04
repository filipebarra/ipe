"""Painel de acompanhamento de lesões (ao lado dos quadros, como o de anteriores).

Tabela lesão × exame do paciente com o valor usado pelo critério (RECIST 1.1, mRECIST, PERCIST ou
livre), a soma/pico, a variação e a resposta. Duplo clique numa célula abre a imagem da medida.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ipe.imaging import lesions as L
from ipe.ui.tabelas import colunas_ajustaveis

ORGANS = ["Fígado", "Pulmão direito", "Pulmão esquerdo", "Linfonodo", "Mama direita", "Mama esquerda",
          "Osso", "Suprarrenal", "Rim", "Pâncreas", "Baço", "Peritônio", "Pleura", "Cérebro", "Partes moles",
          "Outro"]


def patient_key(info: dict) -> str:
    pid = (info or {}).get("patient_id", "")
    if pid:
        return pid
    name = (info or {}).get("patient_name", "")
    return f"nome:{name}|{(info or {}).get('birth_date', '')}" if name else ""


def fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[2:4]}" if len(d) == 8 and d.isdigit() else (d or "?")


class LesionDialog(QDialog):
    def __init__(self, lesion: dict | None = None, parent=None, suggested: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Lesão")
        le = lesion or {}
        self.name = QLineEdit(le.get("name") or suggested)
        self.location = QComboBox()
        self.location.setEditable(True)
        self.location.addItems(ORGANS)
        self.location.setCurrentText(le.get("location", ""))
        self.kind = QComboBox()
        for k, v in L.KINDS.items():
            self.kind.addItem(v, k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(le.get("kind", "target"))))
        self.nodal = QCheckBox("Linfonodo (RECIST: mede o menor eixo; normal < 10 mm)")
        self.nodal.setChecked(bool(le.get("nodal")))
        form = QFormLayout(self)
        form.addRow("Nome:", self.name)
        form.addRow("Local / órgão:", self.location)
        form.addRow("Tipo:", self.kind)
        form.addRow("", self.nodal)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        return {"name": self.name.text().strip() or "Lesão", "location": self.location.currentText().strip(),
                "kind": self.kind.currentData(), "nodal": self.nodal.isChecked()}


class LesionPanel(QWidget):
    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.tab = tab
        self.repo = tab.repo
        self.setMinimumWidth(360)
        self.setMaximumWidth(620)
        self.setStyleSheet("QWidget{background:#1b1c1f;color:#ddd}"
                           "QTableWidget{background:#151515;border:none;gridline-color:#333}"
                           "QHeaderView::section{background:#26272b;color:#bbb;border:none;padding:3px}"
                           "QPushButton{background:#2c2f35;border:1px solid #444;padding:3px 6px}")
        self.pid = patient_key(tab.study_info)
        self.title = QLabel()
        self.criterion = QComboBox()
        for k, v in L.CRITERIA.items():
            self.criterion.addItem(v, k)
        self.criterion.activated.connect(self._criterion_changed)
        self.baseline = QComboBox()
        self.baseline.activated.connect(self._baseline_changed)
        top = QFormLayout()
        top.addRow("Critério:", self.criterion)
        top.addRow("Base:", self.baseline)
        self.table = QTableWidget()
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._open_cell)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        colunas_ajustaveis(self.table)
        self.hint = QLabel("Desenhe a medida (régua, ou ROI no PET), clique com o botão direito sobre ela → "
                           "“Ligar a uma lesão”. Duplo clique numa célula abre a imagem.")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#999;font-size:11px")
        b_new = QPushButton("+ Lesão")
        b_new.clicked.connect(lambda: self.new_lesion())
        b_link = QPushButton("Ligar medida selecionada")
        b_link.setToolTip("Liga a medida selecionada (clique nela) no quadro ativo a uma lesão")
        b_link.clicked.connect(self._link_selected)
        b_layout = QPushButton("Layout das lesões")
        b_layout.setToolTip("Abre um quadro por lesão, na imagem medida (bom para a reunião)")
        b_layout.clicked.connect(self._layout)
        b_copy = QPushButton("Copiar texto")
        b_copy.clicked.connect(self._copy)
        row1 = QHBoxLayout()
        row1.addWidget(b_new)
        row1.addWidget(b_link, 1)
        row2 = QHBoxLayout()
        row2.addWidget(b_layout, 1)
        row2.addWidget(b_copy)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.title)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addWidget(self.status)
        lay.addWidget(self.hint)
        self.lesions: list[dict] = []
        self.studies: list[tuple[str, str]] = []
        self.cells: dict = {}
        self.evals: list = []
        self.refresh()

    # ------------------------------------------------------------ dados
    def load(self) -> None:
        """Lê lesões, exames e medidas do banco e calcula a resposta."""
        self.lesions = self.repo.lesions(self.pid) if self.pid else []
        track = self.repo.lesion_track(self.pid) if self.pid else {"criterion": "recist", "baseline_study": ""}
        self.crit = track.get("criterion") or "recist"
        self.base_uid = track.get("baseline_study") or ""
        rows = self.repo.studies_of_patient(self.tab.study_info.get("patient_id", "")) \
            if self.tab.study_info.get("patient_id") else []
        studies = {r.study_uid: r.study_date for r in rows}
        for uid in self.tab.study_order:
            studies.setdefault(uid, (self.tab.study_infos.get(uid) or {}).get("study_date", ""))
        anns = self.repo.annotations_for_studies(list(studies))
        with_lesion = {a["study_uid"] for a in anns if '"lesion"' in (a.get("data") or "")}
        with_status = {s for le in self.lesions for s in ((le.get("data") or {}).get("status") or {})}
        # mostra só os exames com medida de lesão, o de base e os abertos nesta aba
        keep = with_lesion | with_status | set(self.tab.study_order) | ({self.base_uid} if self.base_uid else set())
        self.studies = sorted(((u, d) for u, d in studies.items() if u in keep), key=lambda s: (s[1] or "", s[0]))
        self.all_studies = sorted(studies.items(), key=lambda s: (s[1] or "", s[0]))
        self.cells = L.collect_cells(self.lesions, anns, self.crit)
        self.evals = L.evaluate(self.crit, self.lesions, self.studies, self.cells, self.base_uid)
        self.duplicacoes = L.duplicacoes(self.lesions, self.studies, self.cells)

    def refresh(self) -> None:
        name = "" if self.tab.anonymize else (self.tab.study_info.get("patient_name", "") or "")
        self.title.setText(f"<b>Acompanhamento de lesões</b><br>{name}")
        if not self.pid:
            self.status.setText("Exame sem identificação do paciente: não dá para acompanhar lesões.")
            return
        self.load()
        self.criterion.setCurrentIndex(max(0, self.criterion.findData(self.crit)))
        self.baseline.blockSignals(True)
        self.baseline.clear()
        self.baseline.addItem("Automática (1º exame medido)", "")
        for uid, d in self.all_studies:
            info = self.tab.study_infos.get(uid) or {}
            self.baseline.addItem(f"{fmt_date(d)} {info.get('modalities', '')} {info.get('description', '')}".strip(), uid)
        self.baseline.setCurrentIndex(max(0, self.baseline.findData(self.base_uid)))
        self.baseline.blockSignals(False)
        self.render()
        names = {le["id"]: le["name"] for le in self.lesions}
        for vp in self.tab.viewports:
            vp.lesion_names = names
            vp.update()

    def render(self) -> None:
        t = self.table
        t.clear()
        n_les = len(self.lesions)
        summary = ["Soma" if self.crit != "percist" else "SUVpeak máx.", "% da base", "% do nadir", "Resposta"]
        if self.crit == "free":
            summary = ["% da base", "% do anterior"]
        t.setRowCount(n_les + len(summary))
        t.setColumnCount(1 + len(self.studies))
        heads = ["Lesão"]
        for uid, d in self.studies:
            mark = " ●" if uid == self.tab.study_uid else ""
            heads.append(fmt_date(d) + mark)
        t.setHorizontalHeaderLabels(heads)
        bold = QFont()
        bold.setBold(True)
        for r, le in enumerate(self.lesions):
            tag = {"target": "", "nontarget": " (NA)", "new": " (nova)"}.get(le.get("kind", "target"), "")
            it = QTableWidgetItem(f"{le['name']}{tag}")
            it.setToolTip(f"{le['name']} — {le.get('location', '')} — {L.KINDS.get(le.get('kind', 'target'))}"
                          + (" — linfonodo" if le.get("nodal") else ""))
            it.setData(Qt.UserRole, le["id"])
            t.setItem(r, 0, it)
            for c, (uid, _d) in enumerate(self.studies, 1):
                cell = self.cells.get((le["id"], uid))
                texto = cell.text(self.crit) if cell else ""
                dup = getattr(self, "duplicacoes", {}).get((le["id"], uid)) if self.crit != "percist" else None
                dicas = []
                if dup is not None and dup[1]:
                    texto += f" · {dup[1]}"
                if dup is not None:
                    dicas.append(dup[2])
                ci = QTableWidgetItem(texto)
                ci.setTextAlignment(Qt.AlignCenter)
                if cell is not None and cell.refs:
                    dicas.append("Duplo clique: abrir a imagem desta medida")
                if dicas:
                    ci.setToolTip("\n".join(dicas))
                t.setItem(r, c, ci)
        for k, lab in enumerate(summary):
            r = n_les + k
            it = QTableWidgetItem(lab)
            it.setFont(bold)
            t.setItem(r, 0, it)
            for c, ev in enumerate(self.evals_for_columns(), 1):
                txt, color = self._summary_cell(lab, ev)
                ci = QTableWidgetItem(txt)
                ci.setTextAlignment(Qt.AlignCenter)
                if color:
                    ci.setForeground(QBrush(QColor(color)))
                    ci.setFont(bold)
                if lab == "Resposta" and ev is not None and ev.notes:
                    ci.setToolTip("\n".join(ev.notes))
                t.setItem(r, c, ci)
        t.resizeColumnsToContents()
        warn = [n for e in self.evals for n in e.notes if e.response == "BASE"]
        self.status.setText("  ".join(warn))

    def evals_for_columns(self) -> list:
        by = {e.study_uid: e for e in self.evals}
        return [by.get(uid) for uid, _d in self.studies]

    def _summary_cell(self, lab: str, ev) -> tuple[str, str]:
        if ev is None:
            return "", ""
        if lab in ("Soma", "SUVpeak máx."):
            if ev.total is None:
                return "", ""
            return (f"{ev.total:.2f}" if self.crit == "percist" else f"{ev.total:.1f} mm"), ""
        if lab == "% da base":
            return ("" if ev.pct_base is None else f"{ev.pct_base:+.0f}%"), ""
        if lab == "% do nadir":
            return ("" if ev.pct_nadir is None else f"{ev.pct_nadir:+.0f}%"), ""
        if lab == "% do anterior":
            return ("" if ev.pct_prev is None else f"{ev.pct_prev:+.0f}%"), ""
        if lab == "Resposta":
            if not ev.response:
                return "", ""
            short = "Base" if ev.response == "BASE" else ev.response
            return short, L.RESPONSE_COLORS.get(ev.response, "")
        return "", ""

    # ------------------------------------------------------------ ações
    def _criterion_changed(self, _i: int) -> None:
        self.repo.save_lesion_track(self.pid, criterion=self.criterion.currentData())
        self.refresh()

    def _baseline_changed(self, _i: int) -> None:
        self.repo.save_lesion_track(self.pid, baseline_study=self.baseline.currentData() or "")
        self.refresh()

    def new_lesion(self, suggested: str = "") -> int | None:
        if not self.pid:
            return None
        n = len(self.lesions) + 1
        dlg = LesionDialog(None, self, suggested or f"Lesão {n}")
        if dlg.exec() != QDialog.Accepted:
            return None
        data = dlg.values()
        data["patient_id"] = self.pid
        lid = self.repo.save_lesion(data)
        self.refresh()
        return lid

    def _lesion_at_row(self, row: int) -> dict | None:
        return self.lesions[row] if 0 <= row < len(self.lesions) else None

    def _menu(self, pos) -> None:
        it = self.table.itemAt(pos)
        if it is None:
            return
        row, col = it.row(), it.column()
        le = self._lesion_at_row(row)
        if le is None:
            return
        m = QMenu(self)
        a = m.addAction("Editar lesão…")
        a.triggered.connect(lambda: self._edit(le))
        if col >= 1:
            uid = self.studies[col - 1][0]
            sm = m.addMenu(f"Neste exame ({fmt_date(self.studies[col - 1][1])})")
            cur = ((le.get("data") or {}).get("status") or {}).get(uid, "")
            for k, lab in L.STATUS.items():
                act = QAction("Automático (pela medida)" if k == "" else lab, sm, checkable=True, checked=(k == cur))
                act.triggered.connect(lambda _=False, kk=k: self.set_status(le, uid, kk))
                sm.addAction(act)
            cell = self.cells.get((le["id"], uid))
            if cell is not None and cell.refs:
                o = m.addAction("Abrir a imagem da medida")
                o.triggered.connect(lambda: self._open_cell(row, col))
        m.addSeparator()
        d = m.addAction("Apagar lesão (as medidas ficam, sem ligação)")
        d.triggered.connect(lambda: self._delete(le))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def set_status(self, le: dict, study_uid: str, status: str) -> None:
        data = dict(le.get("data") or {})
        st = dict(data.get("status") or {})
        if status:
            st[study_uid] = status
        else:
            st.pop(study_uid, None)
        data["status"] = st
        self.repo.save_lesion({"id": le["id"], "data": data})
        self.refresh()

    def _edit(self, le: dict) -> None:
        dlg = LesionDialog(le, self)
        if dlg.exec() == QDialog.Accepted:
            self.repo.save_lesion({"id": le["id"], **dlg.values()})
            self.refresh()

    def _delete(self, le: dict) -> None:
        if QMessageBox.question(self, "Lesões", f"Apagar “{le['name']}” do acompanhamento?") == QMessageBox.Yes:
            self.repo.delete_lesion(le["id"])
            self.refresh()

    def _open_cell(self, row: int, col: int) -> None:
        le = self._lesion_at_row(row)
        if le is None or col < 1:
            return
        uid = self.studies[col - 1][0]
        cell = self.cells.get((le["id"], uid))
        if cell is None or not cell.refs:
            return
        series_uid, sop, frame, _aid = cell.refs[0]
        self.tab.go_to_image(uid, series_uid, sop, frame)

    def _link_selected(self) -> None:
        vp = self.tab.active
        if vp is None or vp.selected is None:
            QMessageBox.information(self, "Lesões", "Clique numa medida (régua ou ROI) no quadro ativo para "
                                    "selecioná-la e tente de novo.")
            return
        self.tab.choose_lesion_for(vp, vp.selected)

    def _layout(self) -> None:
        self.tab.lesion_layout()

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.text_for(self.tab.study_uid))
        self.status.setText("Texto copiado.")

    def text_for(self, study_uid: str | None = None) -> str:
        if not self.lesions:
            return ""
        return L.summary_text(self.crit, self.lesions, self.studies, self.cells, self.evals, study_uid)
