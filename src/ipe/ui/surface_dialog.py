"""Exportar modelo 3D: uma ou várias estruturas, em STL, OBJ, PLY, GLB ou 3MF.

A janela junta num modelo só as peças que interessam — osso por limiar, a segmentação
aberta, as segmentações guardadas no exame e o que está na tela do 3D depois de cortar e
esculpir —, cada uma com nome e cor. Antes de gravar ela mostra **o laudo da malha**:
quantos triângulos, tamanho em milímetros, volume fechado, se a malha está fechada e
quantas peças soltas existem. Exporta de qualquer jeito; quem decide é o usuário.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ipe.imaging import mesh_io as MX
from ipe.imaging import surface as S
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

PRESETS = {
    "": ("Escolher a faixa na mão", None, None),
    "osso": ("Osso (TC, a partir de 200 HU)", 200.0, None),
    "osso_denso": ("Osso cortical (TC, 450 HU)", 450.0, None),
    "pele": ("Pele e partes moles (TC, −300 HU)", -300.0, None),
    "metal": ("Metal / implante (TC, 1500 HU)", 1500.0, None),
}
COLUNAS = ["Peça", "Cor", "Triângulos", "Volume (mL)", "Fechada"]


class SurfaceDialog(QDialog):
    """`mask` dado = superfície dessa segmentação; sem máscara = superfície por limiar.

    `grid` = (máscara, espaçamento (dz,dy,dx), origem (z,y,x) em mm) para quem já tem a
    máscara numa grade própria — é por aí que entra o que está na tela do 3D.
    """

    def __init__(self, vol, mask: np.ndarray | None = None, offset=(0, 0, 0),
                 name: str = "Superfície", parent=None, grid=None, tab=None):
        super().__init__(parent)
        self.vol, self.mask_in, self.offset, self.name = vol, mask, offset, name
        self.grid = grid
        self.tab = tab if tab is not None else parent
        self.parts: list = []
        self.setWindowTitle("Exportar modelo 3D")
        self.resize(720, 560)

        self.preset = QComboBox()
        for chave, (rotulo, _lo, _hi) in PRESETS.items():
            self.preset.addItem(rotulo, chave)
        self.preset.currentIndexChanged.connect(self._preset)
        self.lo = QDoubleSpinBox(minimum=-3000, maximum=10000, value=200, decimals=0, singleStep=25)
        self.hi = QDoubleSpinBox(minimum=-3000, maximum=10000, value=10000, decimals=0, singleStep=25)
        self.maior = QCheckBox("Só a maior peça (tira mesa, ruído e ilhas soltas)")
        self.maior.setChecked(mask is None and grid is None)
        self.passo = QSpinBox(minimum=1, maximum=6, value=1, prefix="a cada ", suffix=" voxel(s)")
        self.suave = QSpinBox(minimum=0, maximum=10, value=2, suffix=" passada(s)")
        self.reduzir = QSpinBox(minimum=10, maximum=100, value=100, suffix="% dos triângulos")
        self.reduzir.setToolTip("Junta vértices vizinhos para deixar o arquivo mais leve. "
                                "100% grava a malha inteira.")
        b_calc = QPushButton("Acrescentar esta peça")
        b_calc.clicked.connect(self.calcular)
        self.b_segs = QPushButton("Acrescentar as segmentações do exame")
        self.b_segs.clicked.connect(self.add_segmentations)
        self.b_tirar = QPushButton("Tirar a peça escolhida")
        self.b_tirar.clicked.connect(self._tirar)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.tabela.itemChanged.connect(self._renomeou)
        self.tabela.cellDoubleClicked.connect(self._talvez_cor)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        colunas_ajustaveis(self.tabela)

        self.formato = QComboBox()
        for chave, rotulo in MX.FORMATOS:
            self.formato.addItem(rotulo, chave)
        self.b_gravar = QPushButton("Gravar modelo…")
        self.b_gravar.clicked.connect(self.gravar)
        self.b_gravar.setEnabled(False)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)

        f = QFormLayout()
        if mask is None and grid is None:
            f.addRow("Faixa:", self.preset)
            f.addRow("De (HU):", self.lo)
            f.addRow("Até (HU):", self.hi)
        f.addRow(self.maior)
        f.addRow("Reduzir a máscara:", self.passo)
        f.addRow("Suavizar:", self.suave)
        f.addRow("Enxugar a malha:", self.reduzir)
        linha = QHBoxLayout()
        linha.addWidget(b_calc)
        linha.addWidget(self.b_segs)
        linha.addWidget(self.b_tirar)
        linha.addStretch(1)
        saida = QHBoxLayout()
        saida.addWidget(QLabel("Formato:"))
        saida.addWidget(self.formato, 1)
        saida.addWidget(self.b_gravar)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Cada peça vira uma estrutura do modelo, com nome e cor. "
                             "STL não guarda nome nem cor: com mais de uma peça sai um arquivo "
                             "para cada. Duplo clique no nome renomeia; na cor, troca a cor."))
        lay.addLayout(f)
        lay.addLayout(linha)
        lay.addWidget(self.tabela, 1)
        lay.addWidget(self.info)
        lay.addLayout(saida)
        lay.addWidget(bb)
        self.b_segs.setEnabled(self._tem_segmentacoes())

    # ------------------------------------------------------------------ fonte
    def _preset(self) -> None:
        chave = self.preset.currentData()
        _r, lo, hi = PRESETS.get(chave, ("", None, None))
        if lo is not None:
            self.lo.setValue(lo)
            self.hi.setValue(hi if hi is not None else 10000)

    def _mascara(self) -> tuple:
        """(máscara, espaçamento, origem, deslocamento) da peça que está para ser calculada."""
        if self.grid is not None:
            m, spacing, origin = self.grid
            return np.asarray(m, dtype=bool), spacing, origin, None
        if self.mask_in is not None:
            return self.mask_in, None, None, self.offset
        m = S.mask_from_threshold(self.vol.data, self.lo.value(),
                                  self.hi.value() if self.hi.value() < 9999 else None)
        return m, None, None, (0, 0, 0)

    def _malha(self, mask, spacing, origin, offset):
        if spacing is not None:
            return S.mesh_from_mask(mask, spacing, origin, self.passo.value(), self.suave.value())
        return S.mesh_in_patient(self.vol, mask, offset, self.passo.value(), self.suave.value())

    # ------------------------------------------------------------------ peças
    def calcular(self, nome: str = "", mask=None, spacing=None, origin=None, offset=None,
                 cor=None) -> bool:
        """Calcula a malha e põe na lista. Sem argumentos, usa a fonte da janela."""
        self.info.setText("Calculando…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            if mask is None:
                mask, spacing, origin, offset = self._mascara()
                nome = nome or self.name
            if self.maior.isChecked():
                mask = S.keep_largest(mask)
            if not np.asarray(mask).any():
                self.info.setText("Nada dentro dessa faixa — a máscara ficou vazia.")
                return False
            verts, faces = self._malha(mask, spacing, origin, offset)
            if not len(faces):
                self.info.setText("A superfície ficou vazia.")
                return False
            alvo = self.reduzir.value() / 100.0
            if alvo < 0.999:
                verts, faces = MX.decimate(verts, faces, alvo)
            self.parts.append(MX.Part(nome or f"peça {len(self.parts) + 1}", verts, faces,
                                      cor or MX.cor_da_vez(len(self.parts))))
            self._encher()
            return True
        except Exception as e:  # noqa: BLE001
            log.exception("superfície")
            self.info.setText(f"Não deu para calcular: {e}")
            return False
        finally:
            QApplication.restoreOverrideCursor()

    def _tem_segmentacoes(self) -> bool:
        return bool(self.vol is not None and self._segmentacoes())

    def _segmentacoes(self) -> list:
        """Objetos de segmentação guardados no exame (DICOM SEG)."""
        tab = self.tab
        repo = getattr(tab, "repo", None)
        uid = getattr(tab, "study_uid", "")
        if repo is None or not uid:
            return []
        try:
            from ipe.imaging import overlays as OV
            saida = []
            for s in repo.series_for_study(uid):
                for inst in repo.instances_for_series(s.series_uid):
                    caminho = inst.get("path") if isinstance(inst, dict) else None
                    if not caminho:
                        continue
                    obj = OV.load_object(caminho)
                    if obj is not None and obj.source == "SEG" and obj.masks:
                        saida.append(obj)
            return saida
        except Exception:  # noqa: BLE001
            log.exception("segmentações do exame")
            return []

    def add_segmentations(self) -> int:
        """Cada segmento guardado no exame vira uma peça do modelo."""
        if self.vol is None:
            return 0
        objetos = self._segmentacoes()
        n = 0
        for obj in objetos:
            for rotulo, mask in MX.masks_from_seg(self.vol, obj).items():
                cor = next((tuple(m.color) for m in obj.masks if m.label == rotulo), None)
                if self.calcular(rotulo, mask, None, None, (0, 0, 0), cor):
                    n += 1
        if not n:
            self.info.setText("Não achei segmentação guardada que caiba nesta série.")
        return n

    def _encher(self) -> None:
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self.parts))
        fechadas = 0
        for i, p in enumerate(self.parts):
            r = MX.report(p.verts, p.faces)
            p.__dict__["_rel"] = r
            fechadas += 1 if r.closed else 0
            nome = QTableWidgetItem(p.name)
            self.tabela.setItem(i, 0, nome)
            cor = QTableWidgetItem("")
            from PySide6.QtGui import QColor
            cor.setBackground(QColor(*p.color))
            cor.setFlags(cor.flags() & ~Qt.ItemIsEditable)
            self.tabela.setItem(i, 1, cor)
            for c, txt in ((2, f"{r.faces}"), (3, f"{r.volume_ml:.1f}"),
                           (4, "sim" if r.closed else ("?" if r.closed is None else "não"))):
                it = QTableWidgetItem(txt)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tabela.setItem(i, c, it)
        self.tabela.blockSignals(False)
        self.b_gravar.setEnabled(bool(self.parts))
        self._resumo()

    def _resumo(self) -> None:
        if not self.parts:
            self.info.setText("")
            return
        tri = sum(p.n_faces for p in self.parts)
        r = MX.report(*self._junta())
        linhas = [f"<b>{len(self.parts)} peça(s), {tri} triângulos</b>"] + r.lines()
        if r.printable:
            linhas.append("<b>Pronto para impressão 3D.</b>")
        else:
            linhas.append("<b>Para impressão 3D, confira o que está marcado acima.</b>")
        self.info.setText("<br>".join(linhas))

    def _junta(self):
        vs, fs, base = [], [], 0
        for p in self.parts:
            vs.append(np.asarray(p.verts))
            fs.append(np.asarray(p.faces) + base)
            base += len(p.verts)
        return np.concatenate(vs), np.concatenate(fs)

    def _tirar(self) -> None:
        i = self.tabela.currentRow()
        if 0 <= i < len(self.parts):
            self.parts.pop(i)
            self._encher()

    def _renomeou(self, item) -> None:
        if item.column() == 0 and 0 <= item.row() < len(self.parts):
            self.parts[item.row()].name = item.text().strip() or self.parts[item.row()].name

    def _talvez_cor(self, linha: int, coluna: int) -> None:
        if coluna != 1 or not (0 <= linha < len(self.parts)):
            return
        from PySide6.QtGui import QColor
        atual = QColor(*self.parts[linha].color)
        nova = QColorDialog.getColor(atual, self, "Cor da peça")
        if nova.isValid():
            self.parts[linha].color = (nova.red(), nova.green(), nova.blue())
            self._encher()

    # ------------------------------------------------------------------ gravar
    def gravar(self) -> None:
        if not self.parts:
            return
        fmt = self.formato.currentData() or "stl"
        nome = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.name).strip() or "modelo"
        filtro = {"stl": "STL (*.stl)", "obj": "OBJ (*.obj)", "ply": "PLY (*.ply)",
                  "glb": "glTF binário (*.glb)", "3mf": "3MF (*.3mf)"}[fmt]
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Gravar modelo 3D", str(Path.home() / f"{nome}{MX.EXTENSAO[fmt]}"), filtro)
        if not caminho:
            return
        try:
            arquivos = MX.save(caminho, self.parts, fmt, self.name)
        except Exception as e:  # noqa: BLE001
            log.exception("modelo 3D")
            QMessageBox.warning(self, "Modelo 3D", f"Não foi possível gravar:\n{e}")
            return
        nomes = ", ".join(Path(a).name for a in arquivos)
        recado = f"<b>Gravado:</b> {nomes}"
        if fmt == "stl" and len(self.parts) > 1:
            recado += "<br>" + "STL não guarda nome nem cor: saiu um arquivo por peça."
        self.info.setText(self.info.text() + "<br>" + recado)
