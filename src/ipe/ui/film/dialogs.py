"""Diálogos do filme: série/intervalo, filmes salvos e impressora DICOM."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QRadioButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QHeaderView, QAbstractItemView,
)

from ipe.printing.dicom_print import (
    DESTINATIONS, FILM_SIZES, MAGNIFICATIONS, MEDIUMS, PrinterConfig, printer_status,
)
from ipe.printing.film import LAYOUTS, pick_frames
from ipe.ui.tabelas import colunas_ajustaveis


class SeriesRangeDialog(QDialog):
    """Série inteira, intervalo (a cada N) ou N imagens espalhadas."""

    def __init__(self, label: str, n_frames: int, current: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Série no filme")
        self.n = n_frames
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{label}</b> — {n_frames} imagem(ns)"))
        self.r_all = QRadioButton("Todas as imagens")
        self.r_range = QRadioButton("Intervalo")
        self.r_count = QRadioButton("Quantidade fixa, espalhadas por igual no intervalo")
        grp = QButtonGroup(self)
        for r in (self.r_all, self.r_range, self.r_count):
            grp.addButton(r)
        self.first = QSpinBox(minimum=1, maximum=max(1, n_frames), value=1)
        self.last = QSpinBox(minimum=1, maximum=max(1, n_frames), value=max(1, n_frames))
        self.every = QSpinBox(minimum=1, maximum=max(1, n_frames), value=max(1, n_frames // 12 or 1))
        self.count = QSpinBox(minimum=1, maximum=max(1, n_frames), value=min(12, max(1, n_frames)))
        grid = QGridLayout()
        grid.addWidget(QLabel("da imagem"), 0, 0)
        grid.addWidget(self.first, 0, 1)
        grid.addWidget(QLabel("até"), 0, 2)
        grid.addWidget(self.last, 0, 3)
        grid.addWidget(QLabel("a cada"), 1, 0)
        grid.addWidget(self.every, 1, 1)
        grid.addWidget(QLabel("imagem(ns)"), 1, 2)
        grid.addWidget(QLabel("quantidade"), 2, 0)
        grid.addWidget(self.count, 2, 1)
        lay.addWidget(self.r_all)
        lay.addWidget(self.r_range)
        lay.addWidget(self.r_count)
        lay.addLayout(grid)
        self.layout_box = QComboBox()
        self.layout_box.addItem("manter o layout da folha", None)
        for t in LAYOUTS:
            self.layout_box.addItem(t, t)
        row = QHBoxLayout()
        row.addWidget(QLabel("Layout das folhas novas:"))
        row.addWidget(self.layout_box, 1)
        lay.addLayout(row)
        self.keep_window = QCheckBox("Usar a janela (W/L) e o zoom do quadro atual")
        self.keep_window.setChecked(True)
        lay.addWidget(self.keep_window)
        self.summary = QLabel()
        lay.addWidget(self.summary)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.r_count.setChecked(n_frames > 24)
        self.r_all.setChecked(n_frames <= 24)
        for w in (self.first, self.last, self.every, self.count):
            w.valueChanged.connect(self._update)
        for r in (self.r_all, self.r_range, self.r_count):
            r.toggled.connect(self._update)
        self._update()

    def indices(self) -> list[int]:
        if self.r_all.isChecked():
            return list(range(self.n))
        a, b = self.first.value() - 1, self.last.value() - 1
        if self.r_count.isChecked():
            return pick_frames(self.n, a, b, count=self.count.value())
        return pick_frames(self.n, a, b, every=self.every.value())

    def chosen_layout(self) -> str | None:
        return self.layout_box.currentData()

    def _update(self) -> None:
        rng = not self.r_all.isChecked()
        for w in (self.first, self.last):
            w.setEnabled(rng)
        self.every.setEnabled(self.r_range.isChecked())
        self.count.setEnabled(self.r_count.isChecked())
        idx = self.indices()
        self.summary.setText(f"{len(idx)} imagem(ns) vão para o filme.")


class FilmsDialog(QDialog):
    """Filmes salvos: abrir, renomear, excluir."""

    def __init__(self, repo, study_uid: str | None = None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Filmes salvos")
        self.resize(760, 420)
        self.chosen: int | None = None
        lay = QVBoxLayout(self)
        self.only_study = QCheckBox("Só os filmes deste exame")
        self.only_study.setVisible(bool(study_uid))
        self.only_study.setChecked(bool(study_uid))
        self.study_uid = study_uid
        self.only_study.toggled.connect(self.refresh)
        lay.addWidget(self.only_study)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Nome", "Paciente", "Folhas", "Imagens", "Alterado", "Impresso"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda *_: self._open())
        lay.addWidget(self.table, 1)
        colunas_ajustaveis(self.table)
        row = QHBoxLayout()
        for text, fn in (("Abrir", self._open), ("Renomear…", self._rename), ("Excluir", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        films = self.repo.films(self.study_uid if self.only_study.isChecked() else None)
        self.table.setRowCount(len(films))
        for r, f in enumerate(films):
            vals = [f["name"], f["patient_name"], str(f["sheets"]), str(f["images"]),
                    f["updated_at"].strftime("%d/%m/%Y %H:%M") if f["updated_at"] else "",
                    f["printed_at"].strftime("%d/%m/%Y %H:%M") if f["printed_at"] else ""]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, f["id"])
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def _current(self) -> int | None:
        it = self.table.item(self.table.currentRow(), 0) if self.table.currentRow() >= 0 else None
        return it.data(Qt.UserRole) if it else None

    def _open(self) -> None:
        fid = self._current()
        if fid is not None:
            self.chosen = fid
            self.accept()

    def _rename(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        fid = self._current()
        if fid is None:
            return
        data = self.repo.film_data(fid) or {}
        name, ok = QInputDialog.getText(self, "Renomear filme", "Nome:", text=data.get("name", ""))
        if ok and name.strip():
            data["name"] = name.strip()
            f = next((x for x in self.repo.films() if x["id"] == fid), None)
            self.repo.save_film(name.strip(), data, f["study_uids"] if f else [], f["patient_name"] if f else "", fid)
            self.refresh()

    def _delete(self) -> None:
        fid = self._current()
        if fid is None:
            return
        if QMessageBox.question(self, "Excluir filme", "Excluir o filme salvo? (as imagens do exame não são "
                                "apagadas)") == QMessageBox.Yes:
            self.repo.delete_film(fid)
            self.refresh()


class _Bridge(QObject):
    done = Signal(object, object)       # resultado, erro


class DicomPrintDialog(QDialog):
    """Escolher/configurar a impressora DICOM e o que imprimir."""

    def __init__(self, settings, local_ae: str, n_sheets: int, current_sheet: int, parent=None,
                 so_configurar: bool = False):
        super().__init__(parent)
        self.settings, self.local_ae = settings, local_ae
        self.so_configurar = so_configurar
        self.setWindowTitle("Impressoras DICOM" if so_configurar else "Imprimir em impressora DICOM")
        self.resize(640, 480)
        self.printers: list[dict] = list(settings.get("printing.dicom_printers", []) or [])
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Impressoras DICOM</b>"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in (("+ Nova", self._add), ("Duplicar", self._duplicate), ("Excluir", self._remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        form = QFormLayout()
        self.f_name = QLineEdit()
        self.f_ae = QLineEdit()
        self.f_host = QLineEdit()
        self.f_port = QSpinBox(minimum=1, maximum=65535, value=104)
        self.f_calling = QLineEdit(placeholderText=f"(padrão: {local_ae})")
        self.f_size = QComboBox()
        for s in FILM_SIZES:
            self.f_size.addItem(s or "o tamanho de cada folha", s)
        self.f_medium = QComboBox()
        self.f_medium.addItems(MEDIUMS)
        self.f_dest = QComboBox()
        self.f_dest.addItems(DESTINATIONS)
        self.f_mag = QComboBox()
        self.f_mag.addItems(MAGNIFICATIONS)
        self.f_dpi = QSpinBox(minimum=72, maximum=600, value=150, suffix=" dpi")
        self.f_color = QCheckBox("Colorida (Basic Color Print)")
        for label, w in (("Nome", self.f_name), ("AE da impressora", self.f_ae), ("IP / host", self.f_host),
                         ("Porta", self.f_port), ("AE de origem", self.f_calling), ("Tamanho do filme", self.f_size),
                         ("Mídia", self.f_medium), ("Destino", self.f_dest), ("Ampliação", self.f_mag),
                         ("Resolução enviada", self.f_dpi), ("", self.f_color)):
            form.addRow(label, w)
        right.addLayout(form)
        test = QPushButton("Testar conexão")
        test.clicked.connect(self._test)
        self.status = QLabel()
        self.status.setWordWrap(True)
        right.addWidget(test)
        right.addWidget(self.status)
        what = QFormLayout()
        self.which = QComboBox()
        self.which.addItem(f"Todas as folhas ({n_sheets})", "all")
        self.which.addItem(f"Só a folha atual ({current_sheet + 1})", "current")
        self.copies = QSpinBox(minimum=1, maximum=20, value=1)
        what.addRow("Imprimir", self.which)
        what.addRow("Cópias", self.copies)
        right.addLayout(what)
        if so_configurar:            # 0.99.6: aberta pela janela Imprimir, só cadastra as impressoras
            what.setRowVisible(self.which, False)
            what.setRowVisible(self.copies, False)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Salvar" if so_configurar else "Imprimir", QDialogButtonBox.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right, 2)
        self._bridge = _Bridge()
        self._bridge.done.connect(self._tested)
        self._cur = -1
        self._fill()

    def _fill(self) -> None:
        self.list.clear()
        for p in self.printers:
            self.list.addItem(p.get("name", "?"))
        last = self.settings.get("printing.last_dicom_printer", 0) or 0
        if self.printers:
            self.list.setCurrentRow(min(int(last), len(self.printers) - 1))
        else:
            self._add()

    def _collect(self) -> None:
        if 0 <= self._cur < len(self.printers):
            self.printers[self._cur] = self.config().__dict__.copy()
            it = self.list.item(self._cur)
            if it is not None:
                it.setText(self.f_name.text() or "?")

    def _show(self, row: int) -> None:
        self._collect()
        self._cur = row
        if not 0 <= row < len(self.printers):
            return
        c = PrinterConfig.from_dict(self.printers[row])
        self.f_name.setText(c.name)
        self.f_ae.setText(c.ae_title)
        self.f_host.setText(c.host)
        self.f_port.setValue(int(c.port))
        self.f_calling.setText(c.calling_ae)
        self.f_size.setCurrentIndex(max(0, self.f_size.findData(c.film_size)))
        self.f_medium.setCurrentText(c.medium)
        self.f_dest.setCurrentText(c.destination)
        self.f_mag.setCurrentText(c.magnification)
        self.f_dpi.setValue(int(c.dpi))
        self.f_color.setChecked(bool(c.color))
        self.copies.setValue(int(c.copies))

    def _add(self) -> None:
        self._collect()
        self.printers.append(PrinterConfig(name=f"Impressora {len(self.printers) + 1}").__dict__.copy())
        self.list.addItem(self.printers[-1]["name"])
        self._cur = -1
        self.list.setCurrentRow(len(self.printers) - 1)

    def _duplicate(self) -> None:
        """Cópia da impressora escolhida, com o nome "(cópia)", logo abaixo dela."""
        self._collect()
        row = self.list.currentRow()
        if not 0 <= row < len(self.printers):
            return
        from ipe.ui.print_settings import nome_de_copia
        copia = dict(self.printers[row])
        copia["name"] = nome_de_copia(copia.get("name", ""), [p.get("name", "") for p in self.printers])
        self.printers.insert(row + 1, copia)
        self.list.insertItem(row + 1, copia["name"])
        self._cur = -1
        self.list.setCurrentRow(row + 1)
        self.f_name.setFocus()
        self.f_name.selectAll()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.printers):
            self.printers.pop(row)
            self._cur = -1
            self.list.takeItem(row)

    def config(self) -> PrinterConfig:
        return PrinterConfig(
            name=self.f_name.text().strip() or "Impressora DICOM", ae_title=self.f_ae.text().strip(),
            host=self.f_host.text().strip(), port=self.f_port.value(), calling_ae=self.f_calling.text().strip(),
            film_size=self.f_size.currentData() or "", medium=self.f_medium.currentText(),
            destination=self.f_dest.currentText(), magnification=self.f_mag.currentText(),
            copies=self.copies.value(), dpi=self.f_dpi.value(), color=self.f_color.isChecked())

    def save(self) -> None:
        self._collect()
        self.settings.set("printing.dicom_printers", self.printers)
        self.settings.set("printing.last_dicom_printer", max(0, self.list.currentRow()))
        self.settings.save()

    def _test(self) -> None:
        cfg = self.config()
        self.status.setText("Testando…")

        def run():
            try:
                self._bridge.done.emit(printer_status(cfg, self.local_ae), None)
            except Exception as e:  # noqa: BLE001
                self._bridge.done.emit(None, e)
        threading.Thread(target=run, daemon=True).start()

    def _tested(self, res, err) -> None:
        self.status.setText(f"<span style='color:#f77'>{err}</span>" if err else f"<span style='color:#7f7'>{res}</span>")

    def _accept(self) -> None:
        cfg = self.config()
        if self.so_configurar and not self.printers:
            self.save()
            self.accept()
            return
        if not cfg.host or not cfg.ae_title:
            QMessageBox.warning(self, "Impressora DICOM", "Preencha o AE e o IP da impressora.")
            return
        self.save()
        self.accept()

    def only_current(self) -> bool:
        return self.which.currentData() == "current"


# ------------------------------------------------------------------ 0.99.6: Salvar e Imprimir
def paginas_do_texto(texto: str, n: int) -> list[int]:
    """"1-3, 5" → [0, 1, 2, 4] (índices). Fora de 1..n é ignorado; repetida conta uma vez."""
    out: list[int] = []
    for parte in (texto or "").replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            a, _, b = parte.partition("-")
            try:
                ia, ib = int(a), int(b)
            except ValueError:
                continue
            faixa = range(min(ia, ib), max(ia, ib) + 1)
        else:
            try:
                faixa = [int(parte)]
            except ValueError:
                continue
        for k in faixa:
            if 1 <= k <= n and k - 1 not in out:
                out.append(k - 1)
    return out


class SalvarFilmeDialog(QDialog):
    """Salvar: o nome, "Salvar" (este filme) ou "Salvar como novo" (outra cópia), e também no exame.

    Pedido dele (27/10): *"ao clicar em salvar aparece uma janela com opções de nome, salvar, salvar
    como, também salvar no exame"*."""

    def __init__(self, nome: str, ja_salvo: bool, no_exame: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Salvar filme")
        self.acao = ""
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.e_nome = QLineEdit(nome)
        self.e_nome.selectAll()
        f.addRow("Nome do filme:", self.e_nome)
        lay.addLayout(f)
        self.c_exame = QCheckBox("Também salvar no exame (como a estação AW: SR, folhas prontas e imagens)")
        self.c_exame.setChecked(no_exame)
        self.c_exame.setToolTip("Se o filme não mudou desde a última gravação no exame, não grava de novo; "
                                "se mudou, pergunta se substitui a anterior.")
        lay.addWidget(self.c_exame)
        info = QLabel("Salvar: atualiza este filme." if ja_salvo else "Este filme ainda não foi salvo.")
        info.setStyleSheet("color:#9a9a9a")
        lay.addWidget(info)
        bb = QDialogButtonBox()
        self.b_salvar = bb.addButton("Salvar", QDialogButtonBox.AcceptRole)
        self.b_novo = bb.addButton("Salvar como novo", QDialogButtonBox.ActionRole)
        self.b_novo.setToolTip("Guarda uma cópia com este nome; o filme salvo antes continua como estava")
        self.b_novo.setVisible(ja_salvo)
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        self.b_salvar.clicked.connect(lambda: self._fim("salvar"))
        self.b_novo.clicked.connect(lambda: self._fim("novo"))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.b_salvar.setDefault(True)

    def _fim(self, acao: str) -> None:
        if not self.e_nome.text().strip():
            QMessageBox.information(self, "Salvar filme", "Dê um nome ao filme.")
            return
        self.acao = acao
        self.accept()

    def nome(self) -> str:
        return self.e_nome.text().strip()

    def no_exame(self) -> bool:
        return self.c_exame.isChecked()


class ImprimirFilmeDialog(QDialog):
    """Imprimir: para onde (impressora do computador, PDF, JPG/PNG, impressora DICOM) e quais folhas.

    Pedido dele (27/10): *"ao clicar no botão imprimir abre uma janela com impressora local, pdf,
    jpg/png, dicom print, escolher as páginas"*."""

    DESTINOS = (("local", "Impressora do computador"), ("pdf", "PDF"), ("imagem", "Imagens (JPG/PNG)"),
                ("dicom", "Impressora DICOM"))

    def __init__(self, settings, local_ae: str, n_folhas: int, atual: int, parent=None):
        super().__init__(parent)
        self.settings, self.local_ae, self.n, self.atual = settings, local_ae, n_folhas, atual
        self.setWindowTitle("Imprimir filme")
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("<b>Para onde</b>"))
        self.g_dest = QButtonGroup(self)
        self.r_dest: dict[str, QRadioButton] = {}
        ultimo = str(settings.get("printing.ultimo_destino_filme", "local") or "local")
        grade = QGridLayout()
        for row, (k, txt) in enumerate(self.DESTINOS):
            r = QRadioButton(txt)
            self.g_dest.addButton(r)
            self.r_dest[k] = r
            grade.addWidget(r, row, 0)
        # imagens: formato e resolução
        self.c_fmt = QComboBox()
        self.c_fmt.addItems(["PNG", "JPG"])
        self.c_fmt.setCurrentText(str(settings.get("printing.image_fmt", "PNG") or "PNG"))
        self.c_dpi = QComboBox()
        for d in (96, 150, 200, 300):
            self.c_dpi.addItem(f"{d} dpi", d)
        self.c_dpi.setCurrentIndex(max(0, self.c_dpi.findData(int(settings.get("printing.image_dpi", 150) or 150))))
        img = QHBoxLayout()
        img.addWidget(self.c_fmt)
        img.addWidget(self.c_dpi)
        img.addStretch(1)
        grade.addLayout(img, 2, 1)
        # DICOM: impressora, cópias e o cadastro
        self.c_imp = QComboBox()
        self.s_copias = QSpinBox(minimum=1, maximum=20, value=1)
        self.s_copias.setSuffix(" cópia(s)")
        b_conf = QPushButton("Configurar impressoras…")
        b_conf.clicked.connect(self._configurar)
        dic = QHBoxLayout()
        dic.addWidget(self.c_imp, 1)
        dic.addWidget(self.s_copias)
        dic.addWidget(b_conf)
        grade.addLayout(dic, 3, 1)
        grade.setColumnStretch(1, 1)
        lay.addLayout(grade)
        self._preencher_impressoras()

        lay.addSpacing(8)
        lay.addWidget(QLabel("<b>Folhas</b>"))
        self.g_pag = QButtonGroup(self)
        self.r_todas = QRadioButton(f"Todas ({n_folhas})")
        self.r_atual = QRadioButton(f"Só a atual ({atual + 1})")
        self.r_escolher = QRadioButton("Escolher:")
        self.e_paginas = QLineEdit()
        self.e_paginas.setPlaceholderText("ex.: 1-3, 5")
        self.e_paginas.textEdited.connect(lambda _t: self.r_escolher.setChecked(True))
        for r in (self.r_todas, self.r_atual, self.r_escolher):
            self.g_pag.addButton(r)
        pg = QHBoxLayout()
        pg.addWidget(self.r_todas)
        pg.addWidget(self.r_atual)
        pg.addWidget(self.r_escolher)
        pg.addWidget(self.e_paginas, 1)
        lay.addLayout(pg)
        self.r_todas.setChecked(True)

        bb = QDialogButtonBox()
        self.b_ok = bb.addButton("Imprimir", QDialogButtonBox.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.g_dest.buttonToggled.connect(lambda *_a: self._ativar())
        self.r_dest.get(ultimo, self.r_dest["local"]).setChecked(True)
        self._ativar()
        self.resize(560, 300)

    def _preencher_impressoras(self) -> None:
        self.c_imp.clear()
        self.impressoras = list(self.settings.get("printing.dicom_printers", []) or [])
        for p in self.impressoras:
            self.c_imp.addItem(p.get("name", "?"))
        if not self.impressoras:
            self.c_imp.addItem("(nenhuma cadastrada)")
        ult = int(self.settings.get("printing.last_dicom_printer", 0) or 0)
        if self.impressoras:
            self.c_imp.setCurrentIndex(min(ult, len(self.impressoras) - 1))
            self.s_copias.setValue(int(self.impressoras[self.c_imp.currentIndex()].get("copies", 1) or 1))

    def _configurar(self) -> None:
        dlg = DicomPrintDialog(self.settings, self.local_ae, self.n, self.atual, self, so_configurar=True)
        dlg.exec()
        self._preencher_impressoras()
        self.r_dest["dicom"].setChecked(True)

    def destino(self) -> str:
        return next((k for k, r in self.r_dest.items() if r.isChecked()), "local")

    def _ativar(self) -> None:
        d = self.destino()
        for w in (self.c_fmt, self.c_dpi):
            w.setEnabled(d == "imagem")
        for w in (self.c_imp, self.s_copias):
            w.setEnabled(d == "dicom" and bool(self.impressoras))
        self.b_ok.setText({"pdf": "Salvar PDF…", "imagem": "Salvar imagens…"}.get(d, "Imprimir"))

    def folhas(self) -> list[int]:
        if self.r_atual.isChecked():
            return [self.atual]
        if self.r_escolher.isChecked():
            return paginas_do_texto(self.e_paginas.text(), self.n)
        return list(range(self.n))

    def impressora_dicom(self) -> PrinterConfig | None:
        i = self.c_imp.currentIndex()
        if not self.impressoras or not 0 <= i < len(self.impressoras):
            return None
        cfg = PrinterConfig.from_dict(self.impressoras[i])
        cfg.copies = self.s_copias.value()
        return cfg

    def _ok(self) -> None:
        if not self.folhas():
            QMessageBox.information(self, "Imprimir filme",
                                    f"Nenhuma folha válida em “{self.e_paginas.text()}”. O filme tem {self.n}.")
            return
        d = self.destino()
        if d == "dicom":
            cfg = self.impressora_dicom()
            if cfg is None or not cfg.host or not cfg.ae_title:
                QMessageBox.information(self, "Imprimir filme",
                                        "Cadastre a impressora DICOM (AE e IP) em “Configurar impressoras…”.")
                return
            self.settings.set("printing.last_dicom_printer", self.c_imp.currentIndex())
        self.settings.set("printing.ultimo_destino_filme", d)
        if d == "imagem":
            self.settings.set("printing.image_fmt", self.c_fmt.currentText())
            self.settings.set("printing.image_dpi", int(self.c_dpi.currentData()))
        self.accept()
