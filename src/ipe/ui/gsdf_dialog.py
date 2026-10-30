"""Calibração GSDF: ajustar a escala de cinza de cada monitor e conferir com os padrões.

Sem fotômetro não dá para medir o monitor — você informa o preto, o branco e o gama (vêm no
manual ou no menu do monitor) e confere a olho nos padrões: todos os degraus têm de ficar
igualmente distinguíveis, e os quadrados de 5% têm de aparecer tanto no preto quanto no branco.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ipe.imaging import gsdf
from ipe.ui.monitors import screen_key, screen_label

log = logging.getLogger(__name__)


def _qimage(a: np.ndarray) -> QImage:
    a = np.ascontiguousarray(a)
    h, w = a.shape
    return QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()


class PatternWindow(QWidget):
    """O padrão em tela cheia no monitor escolhido (Esc fecha)."""

    def __init__(self, screen, imagem: np.ndarray, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Padrão de teste — Esc fecha")
        self.pix = QPixmap.fromImage(_qimage(imagem))
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setPixmap(self.pix)
        self.label.setStyleSheet("background:#000;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        if screen is not None:
            self.setGeometry(screen.geometry())

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.close()


class GsdfDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Calibração GSDF do monitor")
        self.resize(860, 560)
        self.telas = list(QGuiApplication.screens())
        self.c_tela = QComboBox()
        for i, s in enumerate(self.telas, 1):
            self.c_tela.addItem(screen_label(s, i), screen_key(s))
        self.c_tela.currentIndexChanged.connect(self._carregar)
        self.on = QCheckBox("Aplicar a calibração neste monitor")
        self.lmin = QDoubleSpinBox(minimum=0.05, maximum=20.0, singleStep=0.1, decimals=2,
                                   suffix=" cd/m²")
        self.lmax = QDoubleSpinBox(minimum=50.0, maximum=2000.0, singleStep=10.0, decimals=0,
                                   suffix=" cd/m²")
        self.gamma = QDoubleSpinBox(minimum=1.0, maximum=3.5, singleStep=0.1, decimals=2)
        for w in (self.on, self.lmin, self.lmax, self.gamma):
            (w.toggled if isinstance(w, QCheckBox) else w.valueChanged).connect(self._atualizar)
        self.c_padrao = QComboBox()
        for chave, rotulo in gsdf.PATTERNS.items():
            self.c_padrao.addItem(rotulo, chave)
        self.c_padrao.currentIndexChanged.connect(self._atualizar)
        b_tela = QPushButton("Mostrar em tela cheia")
        b_tela.clicked.connect(self._tela_cheia)
        self.resultado = QLabel()
        self.resultado.setWordWrap(True)
        self.previa = QLabel()
        self.previa.setAlignment(Qt.AlignCenter)
        self.previa.setMinimumSize(420, 260)
        self.previa.setStyleSheet("background:#000;")
        f = QFormLayout()
        f.addRow("Monitor:", self.c_tela)
        f.addRow(self.on)
        f.addRow("Preto (L mín):", self.lmin)
        f.addRow("Branco (L máx):", self.lmax)
        f.addRow("Gama do monitor:", self.gamma)
        f.addRow("Padrão:", self.c_padrao)
        linha = QHBoxLayout()
        linha.addWidget(b_tela)
        linha.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Os valores estão no manual ou no menu do monitor. A prévia já mostra o "
                             "padrão <b>com</b> a calibração aplicada."))
        lay.addLayout(f)
        lay.addLayout(linha)
        lay.addWidget(self.previa, 1)
        lay.addWidget(self.resultado)
        lay.addWidget(bb)
        self._carregar()

    # ------------------------------------------------------------ dados
    def _chave(self) -> str:
        return self.c_tela.currentData() or ""

    def _carregar(self) -> None:
        cfg = gsdf.config(self.settings, self._chave())
        self.on.setChecked(bool(cfg.get("on", False)))
        self.lmin.setValue(float(cfg.get("lmin", 0.5)))
        self.lmax.setValue(float(cfg.get("lmax", 300.0)))
        self.gamma.setValue(float(cfg.get("gamma", 2.2)))
        self._atualizar()

    def table(self) -> np.ndarray | None:
        if not self.on.isChecked():
            return None
        return gsdf.lut(self.lmin.value(), self.lmax.value(), self.gamma.value())

    def _imagem(self, largura: int, altura: int) -> np.ndarray:
        base = gsdf.pattern(self.c_padrao.currentData() or "steps", largura, altura)
        return gsdf.apply(base, self.table())

    def _atualizar(self) -> None:
        img = self._imagem(max(200, self.previa.width()), max(140, self.previa.height()))
        self.previa.setPixmap(QPixmap.fromImage(_qimage(img)))
        tabela = self.table()
        if tabela is None:
            sem = gsdf.deviation(np.arange(256, dtype=np.uint8), self.lmin.value(), self.lmax.value(),
                                 self.gamma.value())
            self.resultado.setText(f"Sem calibração, os passos de cinza variam <b>{sem:.0f}%</b> em "
                                   f"brilho percebido neste monitor.")
            return
        com = gsdf.deviation(tabela, self.lmin.value(), self.lmax.value(), self.gamma.value())
        sem = gsdf.deviation(np.arange(256, dtype=np.uint8), self.lmin.value(), self.lmax.value(),
                             self.gamma.value())
        self.resultado.setText(f"Desvio entre os passos: <b>{com:.0f}%</b> com a calibração, contra "
                               f"{sem:.0f}% sem ela (quanto menor, melhor; até 10% é o aceito em "
                               f"monitor de laudo).")

    def _tela_cheia(self) -> None:
        i = self.c_tela.currentIndex()
        tela = self.telas[i] if 0 <= i < len(self.telas) else None
        g = tela.geometry() if tela is not None else None
        img = self._imagem(g.width() if g else 1024, g.height() if g else 768)
        self._janela = PatternWindow(tela, img, self)
        self._janela.showFullScreen()

    def _salvar(self) -> None:
        gsdf.save_config(self.settings, self._chave(),
                         {"on": self.on.isChecked(), "lmin": round(self.lmin.value(), 2),
                          "lmax": round(self.lmax.value(), 1), "gamma": round(self.gamma.value(), 2)})
        # marca para os quadros recarregarem a tabela
        self.settings.set("monitors.gsdf_stamp", int(self.settings.get("monitors.gsdf_stamp", 0)) + 1)
        self.settings.save()
        self.accept()
