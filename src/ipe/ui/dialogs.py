"""Diálogos auxiliares: tags DICOM, comentários, sobre."""

from __future__ import annotations

import pydicom
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)



class TagDialog(QDialog):
    """Ver as tags da imagem e, se precisar, corrigir as principais gravando uma cópia."""

    def __init__(self, path: str, parent=None, files_for=None, on_fixed=None):
        super().__init__(parent)
        self.path = str(path)
        self.files_for = files_for          # escopo -> lista de arquivos ("" = só esta imagem)
        self.on_fixed = on_fixed            # chamado com os arquivos corrigidos, para importar
        self.setWindowTitle("Informações DICOM")
        self.resize(780, 660)
        try:
            ds = pydicom.dcmread(self.path, stop_before_pixels=True, force=True)
            self._lines = str(ds).splitlines()
        except Exception as e:  # noqa: BLE001
            self._lines = [f"Erro ao ler {self.path}: {e}"]
        self.filter = QLineEdit(placeholderText="Filtrar (ex.: Window, 0028, Patient)")
        self.text = QPlainTextEdit(readOnly=True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.text.setFont(mono)
        self.filter.textChanged.connect(self._apply)
        tudo = QWidget()
        tl = QVBoxLayout(tudo)
        tl.addWidget(self.filter)
        tl.addWidget(self.text)
        self.tabs = QTabWidget()
        self.tabs.addTab(tudo, "Todas as tags")
        if files_for is not None:
            self.tabs.addTab(self._aba_corrigir(), "Corrigir")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(self.path))
        lay.addWidget(self.tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._apply("")

    def _apply(self, text: str) -> None:
        t = text.lower()
        self.text.setPlainText("\n".join(l for l in self._lines if t in l.lower()))

    # ------------------------------------------------------------ corrigir
    def _aba_corrigir(self) -> QWidget:
        from ipe.core.tag_edit import FIELDS, LEVELS, read_values
        try:
            self.antes = read_values(self.path)
        except Exception:  # noqa: BLE001
            self.antes = {}
        self.campos: dict[str, QLineEdit] = {}
        dentro = QWidget()
        form = QFormLayout(dentro)
        nivel_atual = ""
        for f in FIELDS:
            if f.level != nivel_atual:
                nivel_atual = f.level
                form.addRow(QLabel(f"<b>{LEVELS.get(f.level, f.level)}</b>"))
            e = QLineEdit(self.antes.get(f.keyword, ""))
            if f.hint:
                e.setPlaceholderText(f.hint)
            self.campos[f.keyword] = e
            form.addRow(f.label + ":", e)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(dentro)
        self.escopo = QComboBox()
        self.escopo.addItem("Só esta imagem", "image")
        self.escopo.addItem("Toda a série", "series")
        self.escopo.addItem("Todo o exame", "study")
        self.escopo.setCurrentIndex(1)
        b_gravar = QPushButton("Gravar cópia corrigida")
        b_gravar.clicked.connect(self._gravar)
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Aplicar em:"))
        linha.addWidget(self.escopo, 1)
        linha.addWidget(b_gravar)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Mude o que estiver errado. O exame original <b>não é alterado</b>: o "
                             "programa grava uma cópia corrigida e a coloca no banco ao lado dele."))
        lay.addWidget(rolagem, 1)
        lay.addLayout(linha)
        return w

    def _mudancas(self) -> dict:
        return {k: e.text() for k, e in self.campos.items() if e.text() != self.antes.get(k, "")}

    def _gravar(self) -> None:
        import tempfile
        from pathlib import Path as _Path

        from ipe.core.tag_edit import apply_to_files, describe, needs_new_study
        edits = self._mudancas()
        if not edits:
            QMessageBox.information(self, "Corrigir tags", "Nada mudou.")
            return
        arquivos = list(self.files_for(self.escopo.currentData()) or [])
        if not arquivos:
            QMessageBox.warning(self, "Corrigir tags", "Não encontrei os arquivos deste exame.")
            return
        aviso = ("Um exame novo será criado (a correção é de paciente ou de exame)."
                 if needs_new_study(edits) else
                 "A série corrigida entra no mesmo exame, ao lado da original.")
        texto = "\n".join(describe(edits, self.antes))
        if QMessageBox.question(self, "Corrigir tags",
                                f"Gravar uma cópia de {len(arquivos)} imagem(ns) com:\n\n{texto}\n\n"
                                f"{aviso}") != QMessageBox.Yes:
            return
        destino = _Path(tempfile.mkdtemp(prefix="dicomviewer-corrigido-"))
        feitos = apply_to_files(arquivos, edits, destino)
        if not feitos:
            QMessageBox.warning(self, "Corrigir tags", "Não consegui gravar as cópias.")
            return
        if self.on_fixed is not None:
            self.on_fixed(feitos)
        self.accept()


class TextInputDialog(QDialog):
    def __init__(self, title: str, label: str, text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(480, 260)
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(text)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(label))
        lay.addWidget(self.edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self) -> str:
        return self.edit.toPlainText().strip()

