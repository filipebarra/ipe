"""Listas de casos na interface: árvore de pastas/listas, editor da lista e modo reunião."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

log = logging.getLogger(__name__)

STUDIES_MIME = "application/x-dicomviewer-studies"
LISTNODE_MIME = "application/x-dicomviewer-listnode"
KIND_LABEL = {"meeting": " · reunião"}


def _kind_icon(kind: str):
    from PySide6.QtWidgets import QApplication, QStyle
    st = QApplication.style()
    return st.standardIcon({"folder": QStyle.SP_DirIcon, "meeting": QStyle.SP_MediaPlay,
                            "smart": QStyle.SP_FileDialogContentsView}.get(kind, QStyle.SP_FileDialogDetailedView))


class SmartListDialog(QDialog):
    """Lista inteligente: um filtro salvo; os exames entram e saem sozinhos."""

    def __init__(self, name: str = "", query: dict | None = None, parent=None):
        super().__init__(parent)
        q = query or {}
        self.setWindowTitle("Lista inteligente")
        self.name = QLineEdit(name)
        self.text = QLineEdit(q.get("text", ""))
        self.text.setPlaceholderText("nome, ID, accession ou descrição (| para vários)")
        self.modality = QComboBox()
        self.modality.addItems(["Todas", "CT", "MR", "MG", "US", "CR", "DX", "PT", "NM", "XA", "OT"])
        self.modality.setCurrentText(q.get("modality") or "Todas")
        from PySide6.QtWidgets import QCheckBox, QSpinBox
        self.days = QSpinBox(minimum=0, maximum=36500, value=int(q.get("days") or 0), suffix=" dias")
        self.days.setSpecialValueText("qualquer data")
        self.desc = QLineEdit(q.get("description", ""))
        self.body = QLineEdit(q.get("body_part", ""))
        self.inst = QLineEdit(q.get("institution", ""))
        self.inst.setPlaceholderText("parte do nome basta (ex.: crispim)")
        self.origin = QComboBox()
        for label, v in (("Qualquer", ""), ("Importado", "import"), ("Recebido pela rede", "received"),
                         ("Baixado do PACS", "retrieved"), ("Pré-busca", "prefetch"),
                         ("Cópia anonimizada", "anonymized")):
            self.origin.addItem(label, v)
        self.origin.setCurrentIndex(max(0, self.origin.findData(q.get("origin", ""))))
        self.checks = {}
        form = QFormLayout()
        form.addRow("Nome da lista:", self.name)
        form.addRow("Busca:", self.text)
        form.addRow("Modalidade:", self.modality)
        form.addRow("Exame dos últimos:", self.days)
        form.addRow("Descrição contém:", self.desc)
        form.addRow("Região contém:", self.body)
        form.addRow("Instituição / unidade contém:", self.inst)
        form.addRow("Origem:", self.origin)
        for key, label in (("key_images", "com imagens-chave"), ("measured", "com medidas"),
                           ("comment", "com comentário"), ("locked", "protegidos"),
                           ("unread", "ainda não abertos"), ("no_list", "que não estão em nenhuma lista")):
            c = QCheckBox(label)
            c.setChecked(bool(q.get(key)))
            self.checks[key] = c
            form.addRow("" if self.checks and len(self.checks) > 1 else "Só exames:", c)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        note = QLabel("Os exames que combinam com o filtro aparecem sozinhos na lista, inclusive os que chegarem depois.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9a9a9a")
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(bb)

    def _ok(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Lista inteligente", "Dê um nome à lista.")
            return
        self.accept()

    def query(self) -> dict:
        q = {"text": self.text.text().strip(), "modality": "" if self.modality.currentText() == "Todas"
             else self.modality.currentText(), "days": self.days.value(), "description": self.desc.text().strip(),
             "body_part": self.body.text().strip(), "institution": self.inst.text().strip(),
             "origin": self.origin.currentData()}
        q.update({k: c.isChecked() for k, c in self.checks.items()})
        return {k: v for k, v in q.items() if v}


def _fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d or "") == 8 else (d or "")


# ============================================================ árvore
class ListTree(QTreeWidget):
    """Pastas e listas. Arrastar lista/pasta para uma pasta move; arrastar exames da tabela para uma
    lista adiciona."""
    list_selected = Signal(object)              # id da lista/pasta ou None (todos os estudos)
    studies_dropped = Signal(int, list)         # lista, estudos
    changed = Signal()

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setIndentation(14)
        self.itemClicked.connect(lambda it, _c: self.list_selected.emit(it.data(0, Qt.UserRole)))
        self.currentItemChanged.connect(
            lambda it, _p: self.list_selected.emit(it.data(0, Qt.UserRole)) if it is not None else None)
        self._nodes: dict[int, dict] = {}

    def node(self, lid: int | None) -> dict | None:
        return self._nodes.get(lid) if lid is not None else None

    def rebuild(self, select: int | None = -1) -> None:
        cur = self.current_id() if select == -1 else select
        expanded = {self.itemFromIndex(i).data(0, Qt.UserRole) for i in self._all_indexes()
                    if self.itemFromIndex(i).isExpanded()}
        self.blockSignals(True)
        self.clear()
        allit = QTreeWidgetItem(["Todos os estudos"])
        allit.setData(0, Qt.UserRole, None)
        f = QFont()
        f.setBold(True)
        allit.setFont(0, f)
        self.addTopLevelItem(allit)
        tree = self.repo.case_list_tree()
        self._nodes = {d["id"]: d for d in tree}
        items: dict[int, QTreeWidgetItem] = {}
        for d in tree:
            label = d["name"]
            if d["kind"] != "folder":
                label += f"  ({d['count']})"
            it = QTreeWidgetItem([label])
            it.setIcon(0, _kind_icon(d["kind"]))
            if d["kind"] == "meeting":
                it.setForeground(0, QColor(140, 200, 255))
            elif d["kind"] == "smart":
                it.setForeground(0, QColor(170, 230, 150))
                it.setToolTip(0, "Lista inteligente (filtro salvo): " + (d["description"] or d["name"]))
            it.setData(0, Qt.UserRole, d["id"])
            it.setToolTip(0, d["description"] or d["name"])
            if d.get("dono"):                       # 0.99.30: lista pessoal (ou compartilhada com escolhidos)
                from ipe.auth import visibilidade as V
                fi = it.font(0)
                fi.setItalic(True)
                it.setFont(0, fi)
                it.setToolTip(0, f"{d['description'] or d['name']}\nVisível para: {V.rotulo(d)}")
            items[d["id"]] = it
        for d in tree:
            it = items[d["id"]]
            parent = items.get(d["parent"])
            (parent.addChild(it) if parent is not None else self.addTopLevelItem(it))
        for lid, it in items.items():
            if lid in expanded or self._nodes[lid]["kind"] == "folder" and not expanded:
                it.setExpanded(True)
        target = items.get(cur) if cur is not None else allit
        self.setCurrentItem(target or allit)
        self.blockSignals(False)

    def _all_indexes(self):
        out = []

        def walk(it):
            for i in range(it.childCount()):
                c = it.child(i)
                out.append(self.indexFromItem(c))
                walk(c)
        walk(self.invisibleRootItem())
        return out

    def current_id(self) -> int | None:
        it = self.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def select_id(self, lid: int | None) -> None:
        for idx in self._all_indexes():
            it = self.itemFromIndex(idx)
            if it.data(0, Qt.UserRole) == lid:
                self.setCurrentItem(it)
                return

    # ---------------------------------------------------------- arrastar e soltar
    def mimeTypes(self):  # noqa: N802
        return [LISTNODE_MIME, STUDIES_MIME]

    def mimeData(self, items):  # noqa: N802
        from PySide6.QtCore import QMimeData
        md = QMimeData()
        ids = [str(it.data(0, Qt.UserRole)) for it in items if it.data(0, Qt.UserRole) is not None]
        md.setData(LISTNODE_MIME, ",".join(ids).encode())
        return md

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasFormat(STUDIES_MIME) or e.mimeData().hasFormat(LISTNODE_MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):  # noqa: N802
        it = self.itemAt(e.position().toPoint())
        lid = it.data(0, Qt.UserRole) if it is not None else None
        node = self.node(lid)
        if e.mimeData().hasFormat(STUDIES_MIME):
            ok = node is not None and node["kind"] not in ("folder", "smart")
        else:
            ok = True
        if ok:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):  # noqa: N802
        md = e.mimeData()
        it = self.itemAt(e.position().toPoint())
        lid = it.data(0, Qt.UserRole) if it is not None else None
        node = self.node(lid)
        if md.hasFormat(STUDIES_MIME):
            uids = [u for u in bytes(md.data(STUDIES_MIME)).decode().split(",") if u]
            if node is not None and node["kind"] not in ("folder", "smart") and uids:
                e.acceptProposedAction()
                self.studies_dropped.emit(lid, uids)
            return
        if md.hasFormat(LISTNODE_MIME):
            ids = [int(x) for x in bytes(md.data(LISTNODE_MIME)).decode().split(",") if x]
            e.setDropAction(Qt.IgnoreAction)
            e.accept()
            for src in ids:
                self.move_node(src, lid)
            self.rebuild(select=ids[0] if ids else -1)
            self.changed.emit()

    def move_node(self, src: int, target: int | None) -> None:
        """Solta `src` sobre `target`: pasta = entra nela; lista = fica logo antes dela; vazio = raiz."""
        node = self.node(target)
        if target == src:
            return
        if node is None:
            parent, before = None, None
        elif node["kind"] == "folder":
            parent, before = target, None
        else:
            parent, before = node["parent"], target
        try:
            self.repo.update_case_list(src, parent_fk=parent)
        except ValueError as err:
            QMessageBox.warning(self, "Mover", str(err))
            return
        sibs = [d["id"] for d in self.repo.case_list_tree() if d["parent"] == parent and d["id"] != src]
        pos = sibs.index(before) if before in sibs else len(sibs)
        sibs.insert(pos, src)
        for i, lid in enumerate(sibs):
            self.repo.update_case_list(lid, position=i)


# ============================================================ editor da lista
class ListEditorDialog(QDialog):
    """Organizar a lista: ordem dos casos (arrastando), nome amigável, história, resposta, notas,
    tags e séries a mostrar."""
    open_case = Signal(str, list)

    def __init__(self, repo, list_id: int, parent=None, select_uid: str | None = None):
        super().__init__(parent)
        self.repo, self.list_id = repo, list_id
        info = repo.case_list_info(list_id) or {}
        self.setWindowTitle(f"Organizar lista — {info.get('name', '')}")
        self.resize(1050, 680)
        self._cur: str | None = None
        self._loading = False

        # --- lista
        self.name = QLineEdit(info.get("name", ""))
        self.kind = QComboBox()
        self.kind.addItem("Normal", "normal")
        self.kind.addItem("Reunião", "meeting")
        self.kind.setCurrentIndex(max(0, self.kind.findData(info.get("kind", "normal"))))
        self.desc = QLineEdit(info.get("description", ""))
        self.desc.setPlaceholderText("Descrição (ex.: reunião de mama — março)")
        top = QHBoxLayout()
        top.addWidget(QLabel("Lista:"))
        top.addWidget(self.name, 2)
        top.addWidget(self.kind)
        top.addWidget(self.desc, 3)

        # --- casos (esquerda)
        self.cases = QListWidget()
        self.cases.setDragDropMode(QAbstractItemView.InternalMove)
        self.cases.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cases.model().rowsMoved.connect(lambda *_: self._save_order())
        self.cases.currentItemChanged.connect(self._case_changed)
        self.cases.itemDoubleClicked.connect(lambda it: self._open(it))
        btns = QHBoxLayout()
        for text, fn, tip in (("↑", lambda: self._move(-1), "Subir"), ("↓", lambda: self._move(1), "Descer"),
                              ("Numerar nomes…", self._number, "Dar nome “Caso 1”, “Caso 2”… aos casos sem nome"),
                              ("Remover da lista", self._remove, "Tira o caso da lista (o exame continua no banco)")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            btns.addWidget(b)
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Casos</b> — arraste para mudar a ordem; duplo clique abre"))
        left.addWidget(self.cases, 1)
        left.addLayout(btns)
        lw = QWidget()
        lw.setLayout(left)

        # --- caso (direita)
        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText("Nome que aparece na reunião (sem dados do paciente)")
        self.f_tags = QLineEdit()
        self.f_tags.setPlaceholderText("ex.: mama, RM, BI-RADS 5")
        self.f_hist = QPlainTextEdit()
        self.f_hist.setPlaceholderText("História clínica / pergunta do caso (pode ser mostrada na reunião)")
        self.f_dx = QPlainTextEdit()
        self.f_dx.setPlaceholderText("Resposta: diagnóstico, anatomopatológico (fica oculto até “Revelar”)")
        self.f_note = QPlainTextEdit()
        self.f_note.setPlaceholderText("Notas de ensino / pontos-chave")
        self.f_series = QListWidget()
        self.f_series.setToolTip("Marque as séries que abrem na reunião. Nenhuma marcada = todas.")
        self.f_exam = QLabel()
        self.f_exam.setWordWrap(True)
        self.f_exam.setStyleSheet("color:#9a9a9a")
        form = QFormLayout()
        form.addRow("Exame:", self.f_exam)
        form.addRow("Nome do caso:", self.f_name)
        form.addRow("Tags:", self.f_tags)
        form.addRow("História:", self.f_hist)
        form.addRow("Resposta:", self.f_dx)
        form.addRow("Notas de ensino:", self.f_note)
        form.addRow("Séries a abrir:", self.f_series)
        rw = QWidget()
        rw.setLayout(form)

        split = QSplitter()
        split.addWidget(lw)
        split.addWidget(rw)
        split.setSizes([420, 630])
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addWidget(bb)
        self.reload(select_uid)

    def reload(self, select_uid: str | None = None) -> None:
        self._loading = True
        self.cases.clear()
        for it in self.repo.list_items(self.list_id):
            text = f"{it['n']}. {it['friendly_name'] or '(sem nome)'}\n    {it['modalities']} · {it['description']} · " \
                   f"{_fmt_date(it['study_date'])} · {it['patient_name']}"
            if not it["present"]:
                text += "  — exame não está no banco"
            li = QListWidgetItem(text)
            li.setData(Qt.UserRole, it["study_uid"])
            if not it["present"]:
                li.setForeground(QColor(200, 110, 110))
            self.cases.addItem(li)
        self._loading = False
        target = 0
        if select_uid:
            for i in range(self.cases.count()):
                if self.cases.item(i).data(Qt.UserRole) == select_uid:
                    target = i
        if self.cases.count():
            self.cases.setCurrentRow(target)
        else:
            self._show(None)

    def _item(self, uid: str) -> dict | None:
        return next((x for x in self.repo.list_items(self.list_id) if x["study_uid"] == uid), None)

    def _case_changed(self, cur, prev) -> None:
        if self._loading:
            return
        if prev is not None:
            self._save_case(prev.data(Qt.UserRole))
        self._show(cur.data(Qt.UserRole) if cur is not None else None)

    def _show(self, uid: str | None) -> None:
        self._cur = uid
        it = self._item(uid) if uid else None
        for w in (self.f_name, self.f_tags, self.f_hist, self.f_dx, self.f_note, self.f_series):
            w.setEnabled(it is not None)
        self.f_series.clear()
        if it is None:
            for w in (self.f_name, self.f_tags):
                w.clear()
            for w in (self.f_hist, self.f_dx, self.f_note):
                w.clear()
            self.f_exam.clear()
            return
        self.f_exam.setText(f"{it['patient_name']} · {it['modalities']} · {it['description']} · "
                            f"{_fmt_date(it['study_date'])}")
        self.f_name.setText(it["friendly_name"])
        self.f_tags.setText(", ".join(it["tags"]))
        self.f_hist.setPlainText(it["clinical_summary"])
        self.f_dx.setPlainText(it["hidden_diagnosis"])
        self.f_note.setPlainText(it["note"])
        chosen = set(it["show_series"])
        for s in (self.repo.series_for_study(uid) if it["present"] else []):
            li = QListWidgetItem(f"{s.series_number} {s.modality} — {s.description} ({s.num_images} im)")
            li.setData(Qt.UserRole, s.series_uid)
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Checked if s.series_uid in chosen else Qt.Unchecked)
            self.f_series.addItem(li)

    def _save_case(self, uid: str | None) -> None:
        if not uid:
            return
        series = [self.f_series.item(i).data(Qt.UserRole) for i in range(self.f_series.count())
                  if self.f_series.item(i).checkState() == Qt.Checked]
        self.repo.update_list_item(
            self.list_id, uid, friendly_name=self.f_name.text().strip(),
            tags=[t.strip() for t in self.f_tags.text().split(",") if t.strip()],
            clinical_summary=self.f_hist.toPlainText().strip(), hidden_diagnosis=self.f_dx.toPlainText().strip(),
            note=self.f_note.toPlainText().strip(), show_series=series)

    def save_all(self) -> None:
        self._save_case(self._cur)
        self.repo.update_case_list(self.list_id, name=self.name.text().strip() or "Lista",
                                   kind=self.kind.currentData(), description=self.desc.text().strip())

    def _order(self) -> list[str]:
        return [self.cases.item(i).data(Qt.UserRole) for i in range(self.cases.count())]

    def _save_order(self) -> None:
        if self._loading:
            return
        self._save_case(self._cur)
        self.repo.reorder_case_list(self.list_id, self._order())
        self.reload(self._cur)

    def _move(self, delta: int) -> None:
        row = self.cases.currentRow()
        j = row + delta
        if row < 0 or not 0 <= j < self.cases.count():
            return
        order = self._order()
        order[row], order[j] = order[j], order[row]
        self._save_case(self._cur)
        self.repo.reorder_case_list(self.list_id, order)
        self.reload(order[j])

    def _number(self) -> None:
        self._save_case(self._cur)
        prefix, ok = QInputDialog.getText(self, "Numerar casos", "Prefixo:", text="Caso")
        if not ok:
            return
        for it in self.repo.list_items(self.list_id):
            if not it["friendly_name"]:
                self.repo.update_list_item(self.list_id, it["study_uid"], friendly_name=f"{prefix} {it['n']}")
        self.reload(self._cur)

    def _remove(self) -> None:
        uids = [it.data(Qt.UserRole) for it in self.cases.selectedItems()]
        if not uids:
            return
        if QMessageBox.question(self, "Remover", f"Tirar {len(uids)} caso(s) desta lista? "
                                "(os exames continuam no banco)") != QMessageBox.Yes:
            return
        self._cur = None
        self.repo.remove_from_case_list(self.list_id, uids)
        self.reload()

    def _open(self, li) -> None:
        self._save_case(self._cur)
        it = self._item(li.data(Qt.UserRole))
        if it and it["present"]:
            self.open_case.emit(it["study_uid"], it["show_series"])

    def done(self, r) -> None:  # noqa: D401
        try:
            self.save_all()
        except Exception as e:  # noqa: BLE001
            log.warning("não salvou a lista: %s", e)
        super().done(r)


# ============================================================ modo reunião
class MeetingBar(QWidget):
    """Barra do modo reunião, no topo do caso aberto."""
    prev_requested = Signal()
    next_requested = Signal()
    jump_requested = Signal(int)
    end_requested = Signal()
    fullscreen_requested = Signal()

    STYLE = ("QWidget#meetingBar{background:#1f3350;border-bottom:1px solid #35506e}"
             "QLabel{color:#e8eef6} QPushButton,QToolButton{padding:3px 10px}")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("meetingBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(self.STYLE)
        self.title = QLabel()
        f = self.title.font()
        f.setPointSizeF(f.pointSizeF() + 2)
        f.setBold(True)
        self.title.setFont(f)
        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_next = QPushButton("Próximo ▶")
        self.btn_cases = QToolButton()
        self.btn_cases.setText("Casos ▾")
        self.btn_cases.setPopupMode(QToolButton.InstantPopup)
        self.cases_menu = QMenu(self)
        self.btn_cases.setMenu(self.cases_menu)
        self.btn_hist = QPushButton("História")
        self.btn_hist.setCheckable(True)
        self.btn_answer = QPushButton("Revelar resposta")
        self.btn_answer.setCheckable(True)
        self.btn_full = QPushButton("Tela cheia")
        self.btn_end = QPushButton("Encerrar reunião")
        for b, tip in ((self.btn_prev, "Caso anterior (Alt+←)"), (self.btn_next, "Próximo caso (Alt+→)"),
                       (self.btn_hist, "Mostrar/ocultar a história clínica (Alt+H)"),
                       (self.btn_answer, "Mostrar/ocultar resposta, notas e tags (Alt+R)"),
                       (self.btn_full, "Tela cheia liga/desliga (F11)"), (self.btn_end, "Sair do modo reunião")):
            b.setToolTip(tip)
        self.btn_prev.clicked.connect(self.prev_requested.emit)
        self.btn_next.clicked.connect(self.next_requested.emit)
        self.btn_full.clicked.connect(self.fullscreen_requested.emit)
        self.btn_end.clicked.connect(self.end_requested.emit)
        self.btn_hist.toggled.connect(lambda _on: self._refresh_info())
        self.btn_answer.toggled.connect(lambda _on: self._refresh_info())
        row = QHBoxLayout()
        row.setContentsMargins(8, 4, 8, 4)
        row.addWidget(self.title, 1)
        for w in (self.btn_prev, self.btn_next, self.btn_cases, self.btn_hist, self.btn_answer, self.btn_full,
                  self.btn_end):
            row.addWidget(w)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)
        self.info.setStyleSheet("background:#172538;color:#f0f4fa;padding:6px 10px;font-size:13px")
        self.info.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(row)
        lay.addWidget(self.info)
        self.case: dict = {}

    def set_case(self, list_name: str, idx: int, total: int, case: dict, cases: list[dict]) -> None:
        self.case = case
        self.title.setText(f"{list_name} — {idx + 1}/{total}: {case.get('friendly_name') or f'Caso {idx + 1}'}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < total - 1)
        self.btn_hist.blockSignals(True)
        self.btn_answer.blockSignals(True)
        self.btn_hist.setChecked(bool(case.get("clinical_summary")))
        self.btn_answer.setChecked(False)
        self.btn_hist.blockSignals(False)
        self.btn_answer.blockSignals(False)
        self.btn_hist.setEnabled(bool(case.get("clinical_summary")))
        self.btn_answer.setEnabled(bool(case.get("hidden_diagnosis") or case.get("note") or case.get("tags")))
        self.cases_menu.clear()
        for i, c in enumerate(cases):
            a = QAction(f"{i + 1}. {c.get('friendly_name') or f'Caso {i + 1}'}", self.cases_menu, checkable=True,
                        checked=i == idx)
            a.triggered.connect(lambda _=False, k=i: self.jump_requested.emit(k))
            self.cases_menu.addAction(a)
        self._refresh_info()

    def _refresh_info(self) -> None:
        c = self.case
        parts = []
        esc = (lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>"))
        if self.btn_hist.isChecked() and c.get("clinical_summary"):
            parts.append(f"<b>História:</b> {esc(c['clinical_summary'])}")
        if self.btn_answer.isChecked():
            if c.get("hidden_diagnosis"):
                parts.append(f"<b style='color:#ffd24a'>Resposta:</b> {esc(c['hidden_diagnosis'])}")
            if c.get("note"):
                parts.append(f"<b>Notas:</b> {esc(c['note'])}")
            if c.get("tags"):
                parts.append(f"<b>Tags:</b> {esc(', '.join(c['tags']))}")
        self.info.setText("<br>".join(parts))
        self.info.setVisible(bool(parts))


class MeetingController(QObject):
    """Percorre os casos de uma lista com os dados do paciente ocultos em todo o programa."""
    finished = Signal()

    def __init__(self, main, list_id: int, start: int = 0):
        super().__init__(main)
        self.main = main
        self.list_id = list_id
        info = main.repo.case_list_info(list_id) or {}
        self.list_name = info.get("name", "Reunião")
        self.cases = [c for c in main.repo.list_items(list_id) if c["present"]]
        self.index = -1
        self.tab = None
        self.bar: MeetingBar | None = None
        self._was_full = main.isFullScreen()
        self._shortcuts: list[QShortcut] = []

    def start(self, start: int = 0) -> bool:
        if not self.cases:
            QMessageBox.information(self.main, "Modo reunião", "A lista não tem casos com exame no banco.")
            return False
        m = self.main
        m.set_privacy(True, {c["study_uid"]: c.get("friendly_name") or f"Caso {c['n']}" for c in self.cases})
        for seq, fn in (("Alt+Right", self.next), ("Alt+Left", self.prev), ("Alt+H", self._toggle_hist),
                        ("Alt+R", self._toggle_answer), ("F11", self.toggle_fullscreen)):
            sc = QShortcut(QKeySequence(seq), m)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)
        self.go(start)
        if not self._was_full and m.settings.get("meeting.fullscreen", True):
            m.showFullScreen()
        return True

    def _toggle_hist(self) -> None:
        if self.bar is not None and self.bar.btn_hist.isEnabled():
            self.bar.btn_hist.toggle()

    def _toggle_answer(self) -> None:
        if self.bar is not None and self.bar.btn_answer.isEnabled():
            self.bar.btn_answer.toggle()

    def toggle_fullscreen(self) -> None:
        m = self.main
        (m.showNormal() if m.isFullScreen() else m.showFullScreen())

    def next(self) -> None:
        self.go(self.index + 1)

    def prev(self) -> None:
        self.go(self.index - 1)

    def go(self, i: int) -> None:
        if not 0 <= i < len(self.cases) or i == self.index:
            return
        m = self.main
        self._close_tab()
        self.index = i
        c = self.cases[i]
        label = c.get("friendly_name") or f"Caso {i + 1}"
        tab = m._make_tab(c["study_uid"], None, c["show_series"] or None)
        if tab is None:
            return
        self.bar = MeetingBar()
        self.bar.prev_requested.connect(self.prev)
        self.bar.next_requested.connect(self.next)
        self.bar.jump_requested.connect(self.go)
        self.bar.end_requested.connect(self.end)
        self.bar.fullscreen_requested.connect(self.toggle_fullscreen)
        tab.set_meeting(label, self.bar)
        self.bar.set_case(self.list_name, i, len(self.cases), c, self.cases)
        idx = m.tabs.addTab(tab, f"Reunião: {label}"[:40])
        m.tabs.setCurrentIndex(idx)
        self.tab = tab

    def _close_tab(self) -> None:
        if self.tab is None:
            return
        m = self.main
        idx = m.tabs.indexOf(self.tab)
        if idx >= 0:
            m.tabs.removeTab(idx)
        m.discard_tab(self.tab)
        self.tab, self.bar = None, None

    def end(self) -> None:
        m = self.main
        for sc in self._shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts = []
        self._close_tab()
        m.set_privacy(False)
        if not self._was_full and m.isFullScreen():
            m.showNormal()
        m.tabs.setCurrentWidget(m.browser)
        m.browser.tree.select_id(self.list_id)
        self.finished.emit()


# ============================================================ exportar / importar (diálogos)
def export_dialog(parent, repo, list_id: int) -> None:
    from ipe.caselists.package import PackageError, export_case_list
    from PySide6.QtWidgets import QApplication, QProgressDialog
    info = repo.case_list_info(list_id) or {}
    box = QMessageBox(parent)
    box.setWindowTitle("Exportar lista")
    box.setText(f"Exportar “{info.get('name', '')}” ({info.get('count', 0)} caso(s)).")
    box.setInformativeText(
        "Com imagens: pacote para levar a outro computador. As imagens vão como CÓPIAS anonimizadas "
        "(nome vira CASO 001, sem nascimento, instituição, médicos, operador e accession; UIDs novos). "
        "Os arquivos do seu banco não mudam. Texto gravado dentro da imagem (burned-in) não é removido.\n\n"
        "Só a lista: nomes, respostas, notas e a referência aos exames (para quem já tem os mesmos "
        "exames, ex.: do mesmo PACS).")
    b_img = box.addButton("Com imagens (anonimizadas)", QMessageBox.AcceptRole)
    b_list = box.addButton("Só a lista", QMessageBox.AcceptRole)
    box.addButton("Cancelar", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() not in (b_img, b_list):
        return
    with_images = box.clickedButton() is b_img
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in info.get("name", "lista")).strip() or "lista"
    path, _ = QFileDialog.getSaveFileName(parent, "Salvar pacote da lista", f"{safe}.zip", "Pacote de lista (*.zip)")
    if not path:
        return
    dlg = QProgressDialog("Exportando…", "Cancelar", 0, 100, parent)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(300)

    def prog(done, total):
        dlg.setMaximum(max(1, total))
        dlg.setValue(done)
        QApplication.processEvents()
    try:
        r = export_case_list(repo, list_id, path, with_images, progress=prog, cancel=dlg.wasCanceled)
    except PackageError as e:
        dlg.close()
        QMessageBox.warning(parent, "Exportar lista", str(e))
        return
    dlg.close()
    extra = ""
    if r.missing:
        extra = f"\n\n{len(r.missing)} caso(s) sem exame no banco ficaram de fora: " + ", ".join(r.missing[:8])
    QMessageBox.information(parent, "Exportar lista",
                            f"{r.cases} caso(s) exportado(s)" + (f", {r.files} imagem(ns)" if with_images else "")
                            + f".\n{path}{extra}")


def import_dialog(parent, repo, db, storage_root, parent_folder: int | None = None) -> int | None:
    from ipe.caselists.package import PackageError, import_case_list, read_manifest
    from PySide6.QtWidgets import QApplication, QProgressDialog
    path, _ = QFileDialog.getOpenFileName(parent, "Importar pacote de lista", "", "Pacote de lista (*.zip)")
    if not path:
        return None
    try:
        man = read_manifest(path)
    except PackageError as e:
        QMessageBox.warning(parent, "Importar lista", str(e))
        return None
    name, ok = QInputDialog.getText(parent, "Importar lista",
                                    f"{len(man.get('cases', []))} caso(s)"
                                    f"{' com imagens' if man.get('with_images') else ''}. Nome da lista:",
                                    text=man.get("name", "Lista importada"))
    if not ok:
        return None
    dlg = QProgressDialog("Importando…", None, 0, 0, parent)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(300)
    QApplication.processEvents()
    try:
        r = import_case_list(repo, db, storage_root, path, name.strip() or None, parent_folder)
    except Exception as e:  # noqa: BLE001
        dlg.close()
        log.exception("importar lista")
        QMessageBox.warning(parent, "Importar lista", f"Falha ao importar:\n{e}")
        return None
    dlg.close()
    msg = f"{r.cases} caso(s) na lista."
    if r.missing:
        msg += (f"\n\n{len(r.missing)} caso(s) não entraram porque o exame não está no banco "
                f"(importe ou baixe do PACS e adicione depois): " + ", ".join(r.missing[:8]))
    QMessageBox.information(parent, "Importar lista", msg)
    return r.list_id


