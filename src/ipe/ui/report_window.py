"""Janela do laudo: modelo, texto, formulário BI-RADS, campos automáticos e assinatura.

Saídas: PDF (arquivo), PDF dentro do exame (DICOM Encapsulated PDF) e DICOM SR de texto.
Um laudo assinado não muda: a retificação cria um laudo novo que substitui o anterior.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from ipe.auth import session as auth
from ipe.reporting import birads as B
from ipe.reporting import fill as F
from ipe.reporting.templates import PLACEHOLDERS, best_template, default_templates

log = logging.getLogger(__name__)
KIND_NAMES = {"": "(sem BI-RADS)", "mg": "Mamografia", "us": "Ultrassonografia", "mri": "Ressonância"}
LOCATIONS = ["quadrante superolateral", "quadrante superomedial", "quadrante inferolateral",
             "quadrante inferomedial", "união dos quadrantes superiores", "união dos quadrantes laterais",
             "união dos quadrantes inferiores", "união dos quadrantes mediais", "região retroareolar",
             "região central", "prolongamento axilar", "às 12 horas", "às 3 horas", "às 6 horas", "às 9 horas"]
CHANGES = ["", "novo", "estável", "aumentou", "diminuiu"]


# ======================================================================== BI-RADS
class FindingDialog(QDialog):
    def __init__(self, kind: str, finding: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Achado")
        f = finding or {}
        self.side = QComboBox()
        for k, v in B.SIDES.items():
            self.side.addItem(v, k)
        self.side.setCurrentIndex(max(0, self.side.findData(f.get("side", "D"))))
        self.type = QComboBox()
        self.type.setEditable(True)
        self.type.addItems(B.FINDING_TYPES.get(kind, B.FINDING_TYPES["mg"]))
        self.type.setCurrentText(f.get("type", self.type.itemText(0)))
        self.desc = QLineEdit(f.get("desc", ""))
        self.desc_btn = QToolButton()
        self.desc_btn.setText("Descritores ▾")
        self.desc_btn.setPopupMode(QToolButton.InstantPopup)
        self.desc_menu = QMenu(self)
        self.desc_menu.aboutToShow.connect(self._fill_desc)
        self.desc_btn.setMenu(self.desc_menu)
        drow = QHBoxLayout()
        drow.addWidget(self.desc, 1)
        drow.addWidget(self.desc_btn)
        self.size = QLineEdit(f.get("size", ""))
        self.size.setPlaceholderText("ex.: 12 x 8 mm")
        self.location = QComboBox()
        self.location.setEditable(True)
        self.location.addItems([""] + LOCATIONS)
        self.location.setCurrentText(f.get("location", ""))
        self.distance = QLineEdit(f.get("distance", ""))
        self.distance.setPlaceholderText("ex.: 4 cm")
        self.change = QComboBox()
        self.change.addItems(CHANGES)
        self.change.setCurrentText(f.get("change", ""))
        self.cat = QComboBox()
        self.cat.addItem("", "")
        for c, n in B.CATEGORIES.items():
            self.cat.addItem(f"{c} — {n}", c)
        self.cat.setCurrentIndex(max(0, self.cat.findData(f.get("category", ""))))
        form = QFormLayout(self)
        form.addRow("Mama:", self.side)
        form.addRow("Achado:", self.type)
        form.addRow("Descrição:", drow)
        form.addRow("Tamanho:", self.size)
        form.addRow("Localização:", self.location)
        form.addRow("Distância do mamilo:", self.distance)
        form.addRow("Evolução:", self.change)
        form.addRow("Categoria do achado:", self.cat)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _fill_desc(self) -> None:
        self.desc_menu.clear()
        for d in B.DESCRIPTORS.get(self.type.currentText(), []) or sum(B.DESCRIPTORS.values(), []):
            a = self.desc_menu.addAction(d)
            a.triggered.connect(lambda _=False, t=d: self.desc.setText(
                (self.desc.text().rstrip(", ") + ", " if self.desc.text().strip() else "") + t))

    def value(self) -> dict:
        return {"side": self.side.currentData(), "type": self.type.currentText().strip(),
                "desc": self.desc.text().strip(), "size": self.size.text().strip(),
                "location": self.location.currentText().strip(), "distance": self.distance.text().strip(),
                "change": self.change.currentText(), "category": self.cat.currentData() or ""}


class BiradsPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.findings: list[dict] = []
        self.kind = QComboBox()
        for k, v in KIND_NAMES.items():
            self.kind.addItem(v, k)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.comp = QComboBox()
        self.bpe = QComboBox()
        self.bpe.addItem("", "")
        for k, v in B.BPE.items():
            self.bpe.addItem(v, k)
        self.bpe_sym = QComboBox()
        self.bpe_sym.addItem("", "")
        self.bpe_sym.addItem("simétrico", "simetrico")
        self.bpe_sym.addItem("assimétrico", "assimetrico")
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: self._edit(self.list.row(it)))
        b_add = QPushButton("+ Achado")
        b_add.clicked.connect(lambda: self._edit(-1))
        b_rm = QPushButton("Remover")
        b_rm.clicked.connect(self._remove)
        self.cat_r = self._cat_combo()
        self.cat_l = self._cat_combo()
        self.rec = QLineEdit()
        self.rec.setPlaceholderText("conduta automática pela categoria")
        self.final = QLabel()
        self.final.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Exame:", self.kind)
        self.comp_label = QLabel("Composição:")
        form.addRow(self.comp_label, self.comp)
        self.bpe_label = QLabel("Realce de fundo:")
        bl = QHBoxLayout()
        bl.addWidget(self.bpe, 1)
        bl.addWidget(self.bpe_sym, 1)
        form.addRow(self.bpe_label, bl)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        t = QLabel("<b>BI-RADS®</b>")
        lay.addWidget(t)
        lay.addLayout(form)
        lay.addWidget(QLabel("Achados (duplo clique edita):"))
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(b_add)
        row.addWidget(b_rm)
        lay.addLayout(row)
        f2 = QFormLayout()
        f2.addRow("Mama direita:", self.cat_r)
        f2.addRow("Mama esquerda:", self.cat_l)
        f2.addRow("Conduta:", self.rec)
        lay.addLayout(f2)
        lay.addWidget(self.final)
        self.b_apply = QPushButton("Levar ao texto do laudo")
        self.b_apply.setToolTip("O texto do laudo já muda sozinho a cada alteração do formulário; use este botão "
                                "se você editou à mão e o BI-RADS não estiver no texto")
        lay.addWidget(self.b_apply)
        for w in (self.comp, self.bpe, self.bpe_sym, self.cat_r, self.cat_l):
            w.currentIndexChanged.connect(self._emit)
        self.rec.textChanged.connect(self._emit)
        self._kind_changed()

    def _cat_combo(self) -> QComboBox:
        c = QComboBox()
        c.addItem("", "")
        for k, v in B.CATEGORIES.items():
            c.addItem(f"{k} — {v}", k)
        return c

    def _kind_changed(self) -> None:
        kind = self.kind.currentData() or ""
        self.comp.blockSignals(True)
        self.comp.clear()
        self.comp.addItem("", "")
        for k, v in B.COMPOSITION.get(kind, {}).items():
            self.comp.addItem(f"{k}) {v}", k)
        self.comp.blockSignals(False)
        self.comp_label.setText("Tecido fibroglandular:" if kind == "mri" else "Composição:")
        for w in (self.bpe, self.bpe_sym, self.bpe_label):
            w.setVisible(kind == "mri")
        for w in (self.comp, self.comp_label):
            w.setVisible(bool(kind))
        self._emit()

    def _emit(self, *_a) -> None:
        f = self.fields()
        cat = B.final_category(f)
        self.final.setText(f"Categoria final: <b>BI-RADS® {cat}</b> — {B.CATEGORIES.get(cat, '')}<br>"
                           f"<i>{B.recommendation(f)}</i>" if cat else "Categoria final: —")
        self.changed.emit()

    def _render_list(self) -> None:
        self.list.clear()
        for f in self.findings:
            self.list.addItem(B.finding_text(f))

    def _edit(self, row: int) -> None:
        cur = self.findings[row] if 0 <= row < len(self.findings) else None
        dlg = FindingDialog(self.kind.currentData() or "mg", cur, self)
        if dlg.exec() != QDialog.Accepted:
            return
        if cur is None:
            self.findings.append(dlg.value())
        else:
            self.findings[row] = dlg.value()
        self._render_list()
        self._emit()

    def _remove(self) -> None:
        r = self.list.currentRow()
        if 0 <= r < len(self.findings):
            del self.findings[r]
            self._render_list()
            self._emit()

    def fields(self) -> dict:
        kind = self.kind.currentData() or ""
        if not kind:
            return {}
        d = {"kind": kind, "findings": list(self.findings), "cat_right": self.cat_r.currentData() or "",
             "cat_left": self.cat_l.currentData() or "", "recommendation": self.rec.text().strip()}
        if kind == "mri":
            d.update(fgt=self.comp.currentData() or "", bpe=self.bpe.currentData() or "",
                     bpe_sym=self.bpe_sym.currentData() or "")
        else:
            d["composition"] = self.comp.currentData() or ""
        return d

    def set_fields(self, d: dict) -> None:
        d = d or {}
        self.kind.setCurrentIndex(max(0, self.kind.findData(d.get("kind", ""))))
        self._kind_changed()
        key = "fgt" if d.get("kind") == "mri" else "composition"
        self.comp.setCurrentIndex(max(0, self.comp.findData(d.get(key, ""))))
        self.bpe.setCurrentIndex(max(0, self.bpe.findData(d.get("bpe", ""))))
        self.bpe_sym.setCurrentIndex(max(0, self.bpe_sym.findData(d.get("bpe_sym", ""))))
        self.findings = list(d.get("findings") or [])
        self._render_list()
        self.cat_r.setCurrentIndex(max(0, self.cat_r.findData(d.get("cat_right", ""))))
        self.cat_l.setCurrentIndex(max(0, self.cat_l.findData(d.get("cat_left", ""))))
        self.rec.setText(d.get("recommendation", ""))
        self._emit()


# ======================================================================== modelos
class TemplatesDialog(QDialog):
    """Editar os modelos de laudo (ficam no banco: no modo cliente, valem para todos)."""

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Modelos de laudo")
        self.resize(900, 620)
        self.templates = [dict(t) for t in repo.report_templates()]
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        self.name = QLineEdit()
        self.mods = QLineEdit()
        self.mods.setPlaceholderText("ex.: CT  ou  MG  ou  PT, CT")
        self.keys = QLineEdit()
        self.keys.setPlaceholderText("palavras da descrição do exame, separadas por vírgula")
        self.kind = QComboBox()
        for k, v in KIND_NAMES.items():
            self.kind.addItem(v, k)
        self.text = QPlainTextEdit()
        ph = QToolButton()
        ph.setText("Inserir campo ▾")
        ph.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self)
        for k, v in PLACEHOLDERS.items():
            a = m.addAction(f"{{{k}}} — {v}")
            a.triggered.connect(lambda _=False, kk=k: self.text.insertPlainText(f"{{{kk}}}"))
        ph.setMenu(m)
        form = QFormLayout()
        form.addRow("Nome:", self.name)
        form.addRow("Modalidades:", self.mods)
        form.addRow("Palavras-chave:", self.keys)
        form.addRow("BI-RADS:", self.kind)
        right = QVBoxLayout()
        right.addLayout(form)
        right.addWidget(ph, 0, Qt.AlignLeft)
        right.addWidget(self.text, 1)
        b_new = QPushButton("+ Novo")
        b_new.clicked.connect(self._new)
        b_dup = QPushButton("Duplicar")
        b_dup.clicked.connect(self._dup)
        b_del = QPushButton("Apagar")
        b_del.clicked.connect(self._delete)
        b_def = QPushButton("Restaurar os de fábrica")
        b_def.clicked.connect(self._defaults)
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        for b in (b_new, b_dup, b_del, b_def):
            left.addWidget(b)
        body = QHBoxLayout()
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(260)
        body.addWidget(lw)
        body.addLayout(right, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(bb)
        self._cur = -1
        self._fill()

    def _fill(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for t in self.templates:
            self.list.addItem(t.get("name", "?"))
        self.list.blockSignals(False)
        self._cur = -1
        if self.templates:
            self.list.setCurrentRow(0)
            self._show(0)

    def _commit(self) -> None:
        i = self._cur
        if 0 <= i < len(self.templates):
            t = self.templates[i]
            t["name"] = self.name.text().strip() or "Modelo"
            t["modalities"] = [m.strip().upper() for m in self.mods.text().replace(";", ",").split(",") if m.strip()]
            t["keywords"] = [k.strip() for k in self.keys.text().split(",") if k.strip()]
            t["birads"] = self.kind.currentData() or ""
            t["text"] = self.text.toPlainText()
            it = self.list.item(i)
            if it is not None:
                it.setText(t["name"])

    def _show(self, i: int) -> None:
        self._commit()
        self._cur = i
        if not (0 <= i < len(self.templates)):
            return
        t = self.templates[i]
        self.name.setText(t.get("name", ""))
        self.mods.setText(", ".join(t.get("modalities", [])))
        self.keys.setText(", ".join(t.get("keywords", [])))
        self.kind.setCurrentIndex(max(0, self.kind.findData(t.get("birads", "") or "")))
        self.text.setPlainText(t.get("text", ""))

    def _new(self) -> None:
        self._commit()
        import uuid
        self.templates.append({"id": uuid.uuid4().hex[:8], "name": "Novo modelo", "modalities": [],
                               "keywords": [], "text": "{exame}\n\nRelatório:\n\nIMPRESSÃO:\n"})
        self.list.addItem("Novo modelo")
        self.list.setCurrentRow(len(self.templates) - 1)

    def _dup(self) -> None:
        self._commit()
        i = self.list.currentRow()
        if 0 <= i < len(self.templates):
            import uuid
            t = dict(self.templates[i], id=uuid.uuid4().hex[:8], name=self.templates[i]["name"] + " (cópia)")
            self.templates.append(t)
            self.list.addItem(t["name"])
            self.list.setCurrentRow(len(self.templates) - 1)

    def _delete(self) -> None:
        i = self.list.currentRow()
        if 0 <= i < len(self.templates):
            del self.templates[i]
            self._cur = -1
            self._fill()

    def _defaults(self) -> None:
        if QMessageBox.question(self, "Modelos", "Voltar aos modelos de fábrica? Os seus modelos serão perdidos.") \
                == QMessageBox.Yes:
            self.templates = default_templates()
            self._cur = -1
            self._fill()

    def _save(self) -> None:
        self._commit()
        try:
            self.repo.save_report_templates(self.templates)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Modelos", f"Não foi possível salvar:\n{e}")
            return
        self.accept()


# ======================================================================== janela do laudo
def _soltar(repo, study_uid: str) -> None:
    try:
        repo.leitura_terminar(study_uid)
    except Exception:  # noqa: BLE001
        pass


class ReportWindow(QWidget):
    saved = Signal(str)            # study_uid
    assinado = Signal(str)         # study_uid (0.99.31)

    def __init__(self, repo, study_uid: str, settings=None, tab=None, parent=None):
        super().__init__(parent, Qt.Window)
        self.repo, self.study_uid, self.settings, self.tab = repo, study_uid, settings, tab
        self.info = repo.study_info(study_uid) or {}
        self.anonymize = bool(getattr(tab, "anonymize", False))
        who = "" if self.anonymize else (self.info.get("patient_name") or "").replace("^", " ")
        self.setWindowTitle(f"Laudo — {who} — {self.info.get('description', '')}".strip(" —"))
        self.resize(1100, 760)
        self.templates = repo.report_templates()
        self.report: dict = {}
        self._dirty = False
        self._loading = True

        self.template = QComboBox()
        for t in self.templates:
            self.template.addItem(t.get("name", "?"), t.get("id"))
        b_apply = QPushButton("Aplicar modelo")
        b_apply.setToolTip("Monta o texto a partir do modelo, com os campos automáticos preenchidos")
        b_apply.clicked.connect(self.apply_template)
        b_models = QPushButton("Modelos…")
        b_models.clicked.connect(self.edit_templates)
        ins = QToolButton()
        ins.setText("Inserir ▾")
        ins.setPopupMode(QToolButton.InstantPopup)
        im = QMenu(self)
        for key, lab in (("medidas", "Medidas do exame"), ("lesoes", "Acompanhamento de lesões (resposta)"),
                         ("volumes", "Segmentações (volume, SUV, TMTV/TLG)"), ("curva", "Curvas tempo-intensidade"),
                         ("comparacao", "Comparação com anteriores"), ("birads", "Categoria BI-RADS e conduta"),
                         ("achados_birads", "Achados BI-RADS"), ("composicao", "Composição mamária"),
                         ("cad", "Achados de CAD/IA")):
            a = im.addAction(lab)
            a.triggered.connect(lambda _=False, k=key: self.insert_field(k))
        ins.setMenu(im)
        self.versions = QComboBox()
        self.versions.activated.connect(self._pick_version)
        self.status = QLabel()
        top = QHBoxLayout()
        top.addWidget(QLabel("Modelo:"))
        top.addWidget(self.template, 1)
        top.addWidget(b_apply)
        top.addWidget(b_models)
        top.addWidget(ins)
        top.addSpacing(16)
        top.addWidget(QLabel("Laudos deste exame:"))
        top.addWidget(self.versions)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Título do laudo")
        self.editor = QPlainTextEdit()
        f = QFont()
        f.setPointSize(11)
        self.editor.setFont(f)
        self.editor.textChanged.connect(self._changed)
        self.title.textChanged.connect(self._changed)
        self.birads = BiradsPanel()
        self.birads.changed.connect(self._birads_changed)
        self.birads.b_apply.clicked.connect(lambda: self.sync_birads(force=True))
        self._auto: dict[str, str] = {}          # blocos do BI-RADS que estão no texto (para trocar)
        split = QSplitter(Qt.Horizontal)
        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.title)
        ll.addWidget(self.editor, 1)
        split.addWidget(lw)
        split.addWidget(self.birads)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        user = auth.get()
        self.crm = QLineEdit(str(self._setting(f"report.signature.{user.username}", "") or ""))
        self.crm.setPlaceholderText("Linha abaixo da assinatura (ex.: CRM-DF 00000 — Radiologia)")
        self.header = QPlainTextEdit(str(self._setting("report.header", "") or self.info.get("institution", "")))
        self.header.setMaximumHeight(46)
        self.header.setPlaceholderText("Cabeçalho do PDF (nome da clínica, endereço…)")
        self.with_keys = QCheckBox("Imagens-chave no PDF")
        self.with_keys.setChecked(bool(self._setting("report.key_images", True)))
        self.save_pdf_dicom = QCheckBox("Guardar o PDF no exame (DICOM)")
        self.save_pdf_dicom.setChecked(bool(self._setting("report.dicom_pdf", True)))
        self.save_sr = QCheckBox("Guardar DICOM SR no exame")
        self.save_sr.setChecked(bool(self._setting("report.dicom_sr", True)))
        opts = QFormLayout()
        opts.addRow("Cabeçalho:", self.header)
        opts.addRow("Assinatura:", self.crm)
        chk = QHBoxLayout()
        for c in (self.with_keys, self.save_pdf_dicom, self.save_sr):
            chk.addWidget(c)
        chk.addStretch(1)
        self.b_save = QPushButton("Salvar rascunho")
        self.b_save.clicked.connect(lambda: self.save_draft(notify=True))
        b_pdf = QPushButton("Salvar PDF…")
        b_pdf.clicked.connect(self.save_pdf_file)
        b_copy = QPushButton("Copiar texto")
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.editor.toPlainText()))
        self.b_sign = QPushButton("Assinar e liberar")
        self.b_sign.setStyleSheet("font-weight:bold")
        self.b_sign.clicked.connect(self.sign)
        self.b_amend = QPushButton("Retificar")
        self.b_amend.clicked.connect(self.amend)
        btns = QHBoxLayout()
        btns.addWidget(self.status, 1)
        for b in (b_copy, b_pdf, self.b_save, self.b_amend, self.b_sign):
            btns.addWidget(b)
        help_ = QLabel("Como usar: 1) confira o modelo (ele já vem preenchido); 2) na mamografia/US/RM, preencha o "
                       "BI-RADS® à direita — composição, “+ Achado” e a categoria de cada mama: o texto muda sozinho; "
                       "3) ajuste o texto; 4) “Salvar rascunho” ou “Assinar e liberar”. Para reabrir: botão Laudo "
                       "(visualizador ou tela inicial) ou botão direito no exame → Laudo.")
        help_.setWordWrap(True)
        help_.setStyleSheet("color:#777;font-size:11px")
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(help_)
        lay.addWidget(split, 1)
        lay.addLayout(opts)
        lay.addLayout(chk)
        lay.addLayout(btns)
        self.so_leitura = ""                 # 0.99.31: quem está laudando (quando não sou eu)
        self.load()
        self._comecar_leitura()
        # janela destruída sem fechar (a aba do exame fechou): solta a trava do mesmo jeito
        self.destroyed.connect(lambda *_a, r=repo, u=study_uid, me=self.__dict__: (
            None if me.get("so_leitura") else _soltar(r, u)))

    # ------------------------------------------------------------ utilidades
    def _setting(self, key: str, default=None):
        try:
            return self.settings.get(key, default) if self.settings is not None else default
        except Exception:  # noqa: BLE001
            return default

    def _set_setting(self, key: str, value) -> None:
        try:
            if self.settings is not None:
                self.settings.set(key, value)
        except Exception:  # noqa: BLE001
            pass

    def _changed(self, *_a) -> None:
        if not self._loading:
            self._dirty = True

    def _template(self) -> dict | None:
        tid = self.template.currentData()
        return next((t for t in self.templates if t.get("id") == tid), None)

    # ------------------------------------------------------------ carregar
    def load(self, report_id: int | None = None) -> None:
        self._loading = True
        reps = self.repo.reports(self.study_uid)
        self.versions.clear()
        for r in reps:
            st = {"draft": "rascunho", "final": "assinado", "amended": "retificado"}.get(r["status"], r["status"])
            self.versions.addItem(f"#{r['id']} {st} {r['updated_at']}", r["id"])
        cur = None
        if report_id is not None:
            cur = next((r for r in reps if r["id"] == report_id), None)
        if cur is None and reps:
            drafts = [r for r in reps if r["status"] == "draft"]
            cur = drafts[-1] if drafts else reps[-1]
        if cur is None:
            t = best_template(self.templates, self.info.get("modalities", ""), self.info.get("description", ""))
            cur = {"id": None, "study_uid": self.study_uid, "status": "draft", "text": "", "fields": {},
                   "template": t.get("id") if t else "", "title": t.get("name", "Laudo") if t else "Laudo"}
            self.report = cur
            if t is not None:
                self.template.setCurrentIndex(max(0, self.template.findData(t.get("id"))))
                bk = t.get("birads") or ""
                self.birads.set_fields({"kind": bk} if bk else {})
            self._loading = False
            self.apply_template(confirm=False)
            self._dirty = False
            self._update_state()
            return
        self.report = dict(cur)
        if cur.get("id") is not None:
            self.versions.setCurrentIndex(max(0, self.versions.findData(cur["id"])))
        self.template.setCurrentIndex(max(0, self.template.findData(cur.get("template"))))
        self.title.setText(cur.get("title", ""))
        self.editor.setPlainText(cur.get("text", ""))
        self.birads.set_fields(cur.get("fields") or {})
        self._auto = {k: v for k, v in self._birads_values(cur.get("fields") or {}).items() if v}
        self._loading = False
        self._dirty = False
        self._update_state()

    def _pick_version(self, _i: int) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self.load(self.versions.currentData())

    # ------------------------------------------------------------ trava de leitura (0.99.31, onda A1)
    def _comecar_leitura(self) -> None:
        """No servidor central, quem abre o laudo vira "quem está laudando" até fechar."""
        from PySide6.QtCore import QTimer
        try:
            r = self.repo.leitura_comecar(self.study_uid) or {"ok": True}
        except Exception:  # noqa: BLE001
            r = {"ok": True}
        if not r.get("ok"):
            if self.perguntar_leitura(r) == "assumir":
                try:
                    self.repo.leitura_comecar(self.study_uid, True)
                except Exception:  # noqa: BLE001
                    pass
            else:
                self.so_leitura = f"{r.get('de', '?')} está laudando este exame desde {r.get('desde', '?')}"
        self._update_state()
        if not self.so_leitura and getattr(self.repo, "remote", False):
            self._t_leitura = QTimer(self)
            self._t_leitura.setInterval(120_000)
            self._t_leitura.timeout.connect(self._manter_leitura)
            self._t_leitura.start()

    def perguntar_leitura(self, r: dict) -> str:
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Laudo em andamento")
        caixa.setText(f"{r.get('de', 'Outro médico')} está laudando este exame desde {r.get('desde', '?')}.")
        caixa.setInformativeText("Abrir só para ler, ou assumir o laudo? Assumir fica no registro de acesso, e "
                                 "o outro não consegue mais gravar.")
        b_ler = caixa.addButton("Só ler", QMessageBox.RejectRole)
        caixa.addButton("Assumir o laudo", QMessageBox.AcceptRole)
        caixa.setDefaultButton(b_ler)
        caixa.exec()
        return "ler" if caixa.clickedButton() is b_ler else "assumir"

    def _manter_leitura(self) -> None:
        try:
            self.repo.leitura_manter([self.study_uid])
        except Exception:  # noqa: BLE001
            pass

    def _terminar_leitura(self) -> None:
        t = getattr(self, "_t_leitura", None)
        if t is not None:
            t.stop()
        if self.so_leitura:
            return
        try:
            self.repo.leitura_terminar(self.study_uid)
        except Exception:  # noqa: BLE001
            pass

    def _update_state(self) -> None:
        if getattr(self, "so_leitura", ""):
            for w in (self.editor, self.title):
                w.setReadOnly(True)
            for w in (self.birads, self.b_save, self.b_sign):
                w.setEnabled(False)
            self.b_amend.setVisible(False)
            self.status.setText(f"Só leitura: {self.so_leitura}.")
            return
        final = self.report.get("status") in ("final", "amended")
        self.editor.setReadOnly(final)
        self.title.setReadOnly(final)
        self.birads.setEnabled(not final)
        self.b_save.setEnabled(not final)
        self.b_sign.setEnabled(not final)
        self.b_amend.setVisible(final)
        if final:
            self.status.setText(f"Assinado por {self.report.get('signed_by', '')} em {self.report.get('signed_at', '')}"
                                " — para mudar, use Retificar.")
        else:
            self.status.setText("Rascunho" + (f" #{self.report['id']}" if self.report.get("id") else " (novo)"))

    # ------------------------------------------------------------ texto
    def context(self) -> dict:
        ctx = F.build_context(self.repo, self.study_uid, self.birads.fields(), self.anonymize)
        ctx["cad"] = self.cad_text()
        return ctx

    def cad_text(self) -> str:
        tab = self.tab
        objs = [o for o in (getattr(tab, "overlay_objects", []) or []) if o.source in ("CAD", "SR", "SEG", "RTSTRUCT")
                and o.study_uid == self.study_uid and o.enabled]
        if not objs:
            return ""
        lines = [f"- {o.source}: {o.label}" + (f" — {', '.join(o.findings[:8])}" if o.findings else "") for o in objs]
        return "Resultados de CAD/IA:\n" + "\n".join(lines)

    BIRADS_KEYS = ("achados_birads", "composicao", "birads", "bpe_texto", "conduta")

    def _birads_values(self, fields: dict | None = None) -> dict:
        f = self.birads.fields() if fields is None else fields
        if not f.get("kind"):
            return {}
        return {"composicao": B.composition_text(f), "achados_birads": B.findings_text(f),
                "birads": B.category_text(f), "conduta": B.recommendation(f), "bpe_texto": B.bpe_text(f)}

    def _birads_changed(self) -> None:
        if self._loading:
            return
        self._changed()
        self.sync_birads()

    def sync_birads(self, force: bool = False) -> None:
        """Troca no texto os blocos do BI-RADS (achados, composição, categoria/conduta) pelos novos."""
        if self.editor.isReadOnly():
            return
        new = self._birads_values()
        if not new:
            return
        text = self.editor.toPlainText()
        t = self._template()
        used = [k for k in self.BIRADS_KEYS if t is None or f"{{{k}}}" in t.get("text", "")] or \
            ["achados_birads", "composicao", "birads"]
        missing = []
        for k in used:
            old, val = self._auto.get(k), new.get(k, "")
            if old and old in text:
                if old != val:
                    text = text.replace(old, val, 1)
                self._auto[k] = val
            elif val:
                missing.append(k)
        if text != self.editor.toPlainText():
            cur = self.editor.textCursor().position()
            self._loading = True
            self.editor.setPlainText(text)
            self._loading = False
            c = self.editor.textCursor()
            c.setPosition(min(cur, len(text)))
            self.editor.setTextCursor(c)
            self._dirty = True
        if missing and force:
            blocks = [new[k] for k in ("composicao", "achados_birads", "birads") if k in missing]
            self.editor.insertPlainText("\n".join(blocks).rstrip() + "\n")
            for k in missing:
                self._auto[k] = new[k]
            self.status.setText("BI-RADS inserido onde está o cursor.")
        elif missing:
            self.status.setText("Parte do texto do BI-RADS foi editada à mão: clique em “Levar ao texto do laudo” "
                                "para inserir o BI-RADS onde está o cursor.")
        else:
            self.status.setText("Texto atualizado com o BI-RADS.")

    def apply_template(self, confirm: bool = True) -> None:
        t = self._template()
        if t is None:
            return
        if confirm and self.editor.toPlainText().strip() and QMessageBox.question(
                self, "Laudo", "Substituir o texto atual pelo modelo (com os campos atualizados)?") != QMessageBox.Yes:
            return
        if t.get("birads") and not self.birads.fields():
            self.birads.set_fields({"kind": t["birads"]})
        ctx = self.context()
        text = F.fill(t.get("text", ""), ctx)
        self._loading = True
        self.editor.setPlainText(text)
        self._loading = False
        self._dirty = True
        self._auto = {k: ctx.get(k, "") for k in self.BIRADS_KEYS if ctx.get(k)}
        if not self.title.text().strip() or confirm:
            self.title.setText(t.get("name", "Laudo"))
        self.report["template"] = t.get("id", "")

    def insert_field(self, key: str) -> None:
        if self.editor.isReadOnly():
            return
        val = self.context().get(key, "")
        if not val:
            self.status.setText("Nada para inserir.")
            return
        self.editor.insertPlainText(val.rstrip() + "\n")

    def edit_templates(self) -> None:
        if not auth.require("report", self, "editar modelos de laudo"):
            return
        if TemplatesDialog(self.repo, self).exec() == QDialog.Accepted:
            cur = self.template.currentData()
            self.templates = self.repo.report_templates()
            self.template.clear()
            for t in self.templates:
                self.template.addItem(t.get("name", "?"), t.get("id"))
            self.template.setCurrentIndex(max(0, self.template.findData(cur)))

    # ------------------------------------------------------------ gravar
    def _data(self) -> dict:
        return {"id": self.report.get("id"), "study_uid": self.study_uid, "template": self.report.get("template", ""),
                "title": self.title.text().strip() or "Laudo", "text": self.editor.toPlainText(),
                "fields": self.birads.fields(), "author": auth.get().full_name or auth.get().username}

    def save_draft(self, notify: bool = False) -> bool:
        if self.report.get("status") in ("final", "amended") or getattr(self, "so_leitura", ""):
            return True
        if not auth.require("report", self, "escrever laudos"):
            return False
        try:
            rid = self.repo.save_report(self._data())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Laudo", f"Não foi possível salvar:\n{e}")
            return False
        self.report["id"] = rid
        self._dirty = False
        self._set_setting(f"report.signature.{auth.get().username}", self.crm.text().strip())
        self._set_setting("report.header", self.header.toPlainText().strip())
        if notify:
            self.load(rid)
            self.status.setText("Rascunho salvo. Para voltar a ele: botão Laudo (no visualizador ou na tela inicial) "
                                "ou botão direito no exame → Laudo.")
        self.saved.emit(self.study_uid)
        return True

    def key_images(self, limit: int = 6) -> list:
        """Imagens-chave do exame como QImage, com as medidas, setas, textos e desenhos feitos nelas.
        A janela/cor é a do quadro que mostra a série no visualizador (se houver); senão a do arquivo."""
        out = []
        cache = getattr(self.tab, "cache", None)
        if cache is None:
            return out
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QImage, QPainter
        from ipe.imaging.series import build_frames
        from ipe.printing.film import Cell
        from ipe.ui.film.cell import FilmCell
        from ipe.ui.viewer.viewer_tab import RepoAnnotationStore
        store = RepoAnnotationStore(self.repo)
        cw = FilmCell(cache, self.settings)
        cw.interactive = False
        cw.overlay, cw.ruler = "none", True
        views = {}
        for v in getattr(self.tab, "viewports", []) or []:
            if v.frames and v._img is not None and not v._img.is_color:
                for f in v.frames[:1]:
                    views.setdefault(f.series_uid or v.series_uid, v)
        frames_of: dict[str, list] = {}
        try:
            for k in self.repo.key_images(self.study_uid)[:limit]:
                try:
                    su = k.get("series_uid", "")
                    if su not in frames_of:
                        frames_of[su] = build_frames(self.repo.instances_for_series(su), su)
                    cell = Cell(self.study_uid, su, k["sop_uid"], int(k.get("frame_index", 0)))
                    v = views.get(su)
                    if v is not None and v.state.window_set:
                        cell.width, cell.level = v.state.width, v.state.level
                        cell.invert, cell.cmap = v.state.invert, v.state.cmap
                    cw.resize(600, 600)
                    cw.load(cell, frames_of[su], self.info, store)
                    if cw._img is None:
                        continue
                    h, w = cw._img.pixels.shape[:2]
                    rs, cs = cw._img.pixel_spacing or (1.0, 1.0)
                    aspect = (h * rs) / (w * cs) if w and cs else 1.0
                    W = 600
                    H = int(max(300, min(900, W * aspect)))
                    img = QImage(W, H, QImage.Format_RGB32)
                    img.fill(QColor(0, 0, 0))
                    p = QPainter(img)
                    p.setRenderHint(QPainter.Antialiasing, True)
                    p.setRenderHint(QPainter.TextAntialiasing, True)
                    cw.paint_to(p, QRectF(0, 0, W, H))
                    p.end()
                    out.append(img)
                except Exception as e:  # noqa: BLE001
                    log.warning("imagem-chave no laudo: %s", e)
        finally:
            cw.deleteLater()
        return out

    def pdf_bytes(self, report: dict | None = None) -> bytes:
        from ipe.reporting.pdf import write_pdf
        rep = report or {**self.report, **self._data()}
        imgs = self.key_images() if self.with_keys.isChecked() else []
        return write_pdf(None, self.info, rep, self.header.toPlainText().strip(), self.crm.text().strip(), imgs,
                         self.anonymize)

    def save_pdf_file(self) -> None:
        name = f"laudo_{self.info.get('study_date', '')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Salvar PDF", name, "PDF (*.pdf)")
        if not path:
            return
        Path(path).write_bytes(self.pdf_bytes())
        auth.audit(self.repo, "laudo_pdf", path, self.study_uid)
        self.status.setText(f"PDF salvo em {path}")

    def sign(self) -> None:
        if not auth.require("sign_report", self, "assinar laudos"):
            return
        if not self.editor.toPlainText().strip():
            return
        if QMessageBox.question(self, "Assinar", "Assinar e liberar o laudo? Depois de assinado, ele só pode ser "
                                "mudado por retificação.") != QMessageBox.Yes:
            return
        amended = bool(self.report.get("amends"))
        if not self.save_draft():
            return
        user = auth.get()
        rep = self.repo.sign_report(self.report["id"], user.full_name or user.username,
                                    "amended" if amended else "final")
        if rep is None:
            return
        self.report = rep
        self._set_setting("report.key_images", self.with_keys.isChecked())
        self._set_setting("report.dicom_pdf", self.save_pdf_dicom.isChecked())
        self._set_setting("report.dicom_sr", self.save_sr.isChecked())
        auth.audit(self.repo, "laudo_assinado", rep.get("title", ""), self.study_uid)
        msgs = []
        try:
            n = self.store_dicom(rep)
            if n:
                msgs.append(f"{n} objeto(s) DICOM guardado(s) no exame")
        except Exception as e:  # noqa: BLE001
            log.exception("laudo DICOM")
            QMessageBox.warning(self, "Laudo", f"Laudo assinado, mas não foi possível gravar no exame:\n{e}")
        self.load(rep["id"])
        self.status.setText("Laudo assinado. " + "; ".join(msgs))
        self.saved.emit(self.study_uid)
        self.assinado.emit(self.study_uid)
        if self._setting("viewer.fechar_ao_assinar", False):     # 0.99.31 (onda A8)
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                if hasattr(w, "fechar_exame") and hasattr(w, "detached"):
                    QTimer.singleShot(0, lambda w=w, u=self.study_uid: w.fechar_exame(u, "laudo assinado"))
                    break
            QTimer.singleShot(0, self.close)

    def store_dicom(self, rep: dict) -> int:
        from ipe.reporting import dicom_out as D
        if not (self.save_pdf_dicom.isChecked() or self.save_sr.isChecked()):
            return 0
        files = self.repo.files_for_study(self.study_uid)
        storage = getattr(self.tab, "storage_root", None)
        if not files or storage is None:
            return 0
        tmp = Path(tempfile.mkdtemp(prefix="dv_laudo_"))
        n = 0
        if self.save_pdf_dicom.isChecked():
            ds = D.encapsulated_pdf(self.pdf_bytes(rep), files[0], rep.get("title") or "Laudo")
            ds.save_as(tmp / "laudo_pdf.dcm", enforce_file_format=True)
            n += 1
        if self.save_sr.isChecked():
            cat = B.final_category(rep.get("fields") or {})
            ds = D.text_sr(rep.get("text", ""), files[0], rep.get("title") or "Laudo", rep.get("author", ""),
                           True, rep.get("signed_by", ""), cat)
            ds.save_as(tmp / "laudo_sr.dcm", enforce_file_format=True)
            n += 1
        from ipe.importer.scanner import Importer
        Importer(self.repo.db, storage).import_paths([tmp])
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        from ipe.central.client_repo import upload_if_client
        upload_if_client(self.repo, self.study_uid)
        return n

    def amend(self) -> None:
        if not auth.require("report", self, "retificar laudos"):
            return
        old = dict(self.report)
        self.report = {"id": None, "study_uid": self.study_uid, "status": "draft", "template": old.get("template", ""),
                       "amends": old.get("id")}
        self._loading = True
        self.title.setText((old.get("title") or "Laudo") + " (retificação)")
        self.editor.setPlainText(old.get("text", ""))
        self.birads.set_fields(old.get("fields") or {})
        self._auto = {k: v for k, v in self._birads_values(old.get("fields") or {}).items() if v}
        self._loading = False
        self._dirty = True
        self._update_state()
        self.status.setText("Retificação: edite e assine; o laudo anterior continua guardado.")

    # ------------------------------------------------------------ fechar
    def _confirm_discard(self) -> bool:
        return QMessageBox.question(self, "Laudo", "Há mudanças não salvas. Descartar?") == QMessageBox.Yes

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._dirty and self.report.get("status") == "draft" and self.editor.toPlainText().strip():
            if auth.can("report") and not self.so_leitura:
                self.save_draft()
        self._terminar_leitura()
        super().closeEvent(e)
