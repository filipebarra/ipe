"""Deslocar a máscara da DSA (pixel shift) com as setas, vendo o resultado na hora."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout,
)


class DsaShiftDialog(QDialog):
    def __init__(self, vp, parent=None):
        super().__init__(parent)
        self.vp = vp
        self.setWindowTitle("Deslocar a máscara (DSA)")
        self.dy = QSpinBox(minimum=-60, maximum=60, value=int(vp.dsa.get("dy", 0)), suffix=" px")
        self.dx = QSpinBox(minimum=-60, maximum=60, value=int(vp.dsa.get("dx", 0)), suffix=" px")
        self.dy.valueChanged.connect(self._aplicar)
        self.dx.valueChanged.connect(self._aplicar)
        grade = QGridLayout()
        for texto, ddy, ddx, lin, col in (("▲", -1, 0, 0, 1), ("◀", 0, -1, 1, 0),
                                          ("▶", 0, 1, 1, 2), ("▼", 1, 0, 2, 1)):
            b = QPushButton(texto)
            b.setFixedWidth(44)
            b.clicked.connect(lambda _c=False, a=ddy, b2=ddx: self._passo(a, b2))
            grade.addWidget(b, lin, col)
        b_zero = QPushButton("Zerar")
        b_zero.clicked.connect(lambda: (self.dy.setValue(0), self.dx.setValue(0)))
        grade.addWidget(b_zero, 1, 1)
        grade.addWidget(QLabel("cima/baixo:"), 3, 0)
        grade.addWidget(self.dy, 3, 1, 1, 2)
        grade.addWidget(QLabel("esquerda/direita:"), 4, 0)
        grade.addWidget(self.dx, 4, 1, 1, 2)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(self.close)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Quando o paciente se mexeu, sobra o contorno do osso na imagem "
                             "subtraída. Empurre a máscara até o contorno sumir."))
        lay.addLayout(grade)
        lay.addWidget(bb)
        self.setWindowFlag(Qt.Tool, True)

    def _passo(self, ddy: int, ddx: int) -> None:
        self.dy.setValue(self.dy.value() + ddy)
        self.dx.setValue(self.dx.value() + ddx)

    def _aplicar(self) -> None:
        self.vp.set_dsa(on=True, dy=self.dy.value(), dx=self.dx.value())
