"""Documentos do exame (0.99.57): os PDF guardados no exame (anexados, laudos em PDF, PDF de outros sistemas)
abertos dentro do programa, com o leitor de PDF do próprio Qt."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget)

from ipe.importer import anexos as AX

log = logging.getLogger(__name__)


def documentos_do_exame(repo, study_uid: str) -> list[dict]:
    """Um item por documento encapsulado do exame: {path, titulo, serie, data}."""
    out = []
    try:
        series = repo.series_for_study(study_uid, ocultas=True)
    except TypeError:
        series = repo.series_for_study(study_uid)
    for se in series:
        if (se.modality or "").upper() != "DOC":
            continue
        for i in repo.instances_for_series(se.series_uid):
            p = i.get("path") or ""
            if not p or not Path(p).exists():
                continue
            try:
                import pydicom
                ds = pydicom.dcmread(p, stop_before_pixels=True, force=True,
                                     specific_tags=["DocumentTitle", "ContentDate", "MIMETypeOfEncapsulatedDocument"])
                titulo = str(ds.get("DocumentTitle", "") or "") or se.description or "Documento"
                data = str(ds.get("ContentDate", "") or "")
            except Exception:  # noqa: BLE001
                titulo, data = se.description or "Documento", ""
            out.append({"path": p, "titulo": titulo, "serie": se.description or "", "data": data})
    return out


class DocumentosDialog(QDialog):
    def __init__(self, repo, study_uid: str, parent=None, anexar=None):
        super().__init__(parent)
        self.repo, self.study_uid, self._anexar = repo, study_uid, anexar
        self.setWindowTitle("Documentos do exame")
        self.resize(1000, 760)
        self._tmp = Path(tempfile.mkdtemp(prefix="ipe_docs_"))
        self.docs: list[dict] = []
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(self.mostrar)
        self.vazio = QLabel()
        self.vazio.setWordWrap(True)
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView
        self.pdf = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.pdf)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        esq = QWidget()
        le = QVBoxLayout(esq)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(self.lista, 1)
        le.addWidget(self.vazio)
        split = QSplitter()
        split.addWidget(esq)
        split.addWidget(self.view)
        split.setStretchFactor(1, 4)
        botoes = QHBoxLayout()
        for texto, fn in (("Anexar documento…", self.anexar), ("Abrir no programa do sistema", self.abrir_fora),
                          ("Salvar o PDF…", self.salvar)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
            if texto.startswith("Anexar") and anexar is None:
                b.setEnabled(False)
        botoes.addStretch(1)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.close)
        botoes.addWidget(fechar)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addLayout(botoes)
        self.recarregar()

    def recarregar(self) -> None:
        self.docs = documentos_do_exame(self.repo, self.study_uid)
        self.lista.clear()
        for d in self.docs:
            data = d["data"]
            rot = d["titulo"] + (f" — {data[6:8]}/{data[4:6]}/{data[:4]}" if len(data) == 8 else "")
            self.lista.addItem(QListWidgetItem(rot))
        self.vazio.setText("" if self.docs else "Nenhum documento neste exame. Arraste um PDF ou uma imagem sobre o "
                                                "exame, ou use Anexar documento….")
        if self.docs:
            self.lista.setCurrentRow(0)

    def _arquivo(self, i: int) -> Path | None:
        if not (0 <= i < len(self.docs)):
            return None
        dados, mime, _t = AX.documento_de(self.docs[i]["path"])
        if mime != "application/pdf":
            raise ValueError(f"documento {mime}: só PDF se abre aqui")
        alvo = self._tmp / f"doc_{i}.pdf"
        alvo.write_bytes(dados)
        return alvo

    def mostrar(self, i: int) -> None:
        try:
            arq = self._arquivo(i)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Documento", f"Não deu para abrir: {e}")
            return
        if arq is not None:
            self.pdf.load(str(arq))

    def abrir_fora(self) -> None:
        try:
            arq = self._arquivo(self.lista.currentRow())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Documento", f"Não deu para abrir: {e}")
            return
        if arq is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(arq)))

    def salvar(self) -> None:
        i = self.lista.currentRow()
        if not (0 <= i < len(self.docs)):
            return
        nome, _f = QFileDialog.getSaveFileName(self, "Salvar o PDF", f"{self.docs[i]['titulo']}.pdf", "PDF (*.pdf)")
        if nome:
            dados, _m, _t = AX.documento_de(self.docs[i]["path"])
            Path(nome).write_bytes(dados)

    def anexar(self) -> None:
        if self._anexar is not None and self._anexar():
            self.recarregar()

    def closeEvent(self, e) -> None:  # noqa: N802
        self.pdf.close()
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().closeEvent(e)
