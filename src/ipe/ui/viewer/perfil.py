"""Perfil de intensidade ao longo de uma régua ou polilinha (0.99.31, onda A4 — ideia da Eden).

Botão direito numa régua (ou polilinha) ▸ "Perfil de intensidade…": o gráfico do valor (HU na TC) ao
longo da linha, em mm. Mostra a transição densitométrica, a parede de uma lesão, o realce de um vaso —
o que a intensidade num ponto só não mostra. O gráfico acompanha a linha quando ela é mexida.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ipe.imaging import measure as M

LINHA = QColor(120, 220, 140)
EIXO = QColor(150, 150, 150)


class PerfilView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.d = np.zeros(0)
        self.v = np.zeros(0)
        self.unidade_x, self.unidade_y = "mm", ""
        self.setMinimumSize(460, 240)

    def set_data(self, d, v, unidade_x: str, unidade_y: str) -> None:
        self.d, self.v, self.unidade_x, self.unidade_y = d, v, unidade_x, unidade_y
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(24, 25, 28))
        font = QFont()
        font.setPointSizeF(8.5)
        p.setFont(font)
        fm = QFontMetrics(font)
        left, bottom, top, right = 56, 26, 10, 12
        r = QRectF(left, top, max(10, self.width() - left - right), max(10, self.height() - top - bottom))
        if self.v.size < 2:
            p.setPen(EIXO)
            p.drawText(self.rect(), Qt.AlignCenter, "Sem dados")
            p.end()
            return
        x0, x1 = float(self.d[0]), float(self.d[-1]) or 1.0
        y0, y1 = float(self.v.min()), float(self.v.max())
        if y1 - y0 < 1e-9:
            y0, y1 = y0 - 1, y1 + 1
        pad = (y1 - y0) * 0.05
        y0, y1 = y0 - pad, y1 + pad
        sx = lambda x: r.left() + (x - x0) / ((x1 - x0) or 1) * r.width()  # noqa: E731
        sy = lambda y: r.bottom() - (y - y0) / (y1 - y0) * r.height()      # noqa: E731
        p.setPen(QPen(EIXO))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        p.drawLine(r.topLeft(), r.bottomLeft())
        for k in range(5):
            xv = x0 + (x1 - x0) * k / 4
            yv = y0 + (y1 - y0) * k / 4
            tx = f"{xv:.0f}" if abs(x1 - x0) >= 8 else f"{xv:.1f}"
            ty = f"{yv:.0f}" if abs(y1 - y0) >= 8 else f"{yv:.2f}"
            p.drawText(QPointF(sx(xv) - fm.horizontalAdvance(tx) / 2, r.bottom() + fm.ascent() + 4), tx)
            p.drawText(QPointF(r.left() - fm.horizontalAdvance(ty) - 5, sy(yv) + fm.ascent() / 2 - 1), ty)
        p.drawText(QPointF(r.right() - fm.horizontalAdvance(self.unidade_x), r.bottom() - 4), self.unidade_x)
        if self.unidade_y:
            p.drawText(QPointF(r.left() + 4, r.top() + fm.ascent()), self.unidade_y)
        if y0 < 0 < y1:                                     # o zero (água na TC)
            p.setPen(QPen(QColor(90, 90, 90), 1, Qt.DashLine))
            p.drawLine(QPointF(r.left(), sy(0)), QPointF(r.right(), sy(0)))
        path = QPainterPath(QPointF(sx(self.d[0]), sy(self.v[0])))
        for x, y in zip(self.d[1:], self.v[1:]):
            path.lineTo(QPointF(sx(x), sy(y)))
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(LINHA, 1.6))
        p.drawPath(path)
        p.end()


class PerfilDialog(QDialog):
    def __init__(self, vp, ann, parent=None):
        super().__init__(parent)
        self.vp, self.ann = vp, ann
        self.setWindowTitle("Perfil de intensidade")
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        self.view = PerfilView()
        self.info = QLabel()
        lay.addWidget(self.view, 1)
        lay.addWidget(self.info)
        bot = QHBoxLayout()
        b_copiar = QPushButton("Copiar valores (planilha)")
        b_copiar.clicked.connect(self.copiar)
        bot.addWidget(b_copiar)
        bot.addStretch(1)
        lay.addLayout(bot)
        self._pontos = None
        self.refresh()
        self._t = QTimer(self)                    # acompanha a linha quando ela é mexida
        self._t.setInterval(300)
        self._t.timeout.connect(self._talvez_refresh)
        self._t.start()
        self.resize(620, 360)

    def dados(self):
        img = self.vp._img
        if img is None or img.is_color or len(self.ann.points) < 2:
            return np.zeros(0), np.zeros(0), "px"
        sp = self.vp.measure_spacing(self.ann)
        d, v = M.perfil(img.pixels, [tuple(p) for p in self.ann.points], sp)
        return d, v, ("mm" if sp else "px")

    def _talvez_refresh(self) -> None:
        if [tuple(p) for p in self.ann.points] != self._pontos:
            self.refresh()

    def refresh(self) -> None:
        self._pontos = [tuple(p) for p in self.ann.points]
        d, v, ux = self.dados()
        uy = M.unit_for(getattr(self.vp, "modality", "") or "")
        self.view.set_data(d, v, ux, uy)
        self._d, self._v = d, v
        if v.size:
            self.info.setText(f"Comprimento {d[-1]:.1f} {ux} · mínimo {v.min():.1f} · máximo {v.max():.1f} · "
                              f"média {v.mean():.1f} {uy}".strip())
        else:
            self.info.setText("Sem valores (imagem colorida ou linha sem pontos).")

    def copiar(self) -> str:
        linhas = ["distancia\tvalor"] + [f"{a:.2f}\t{b:.2f}".replace(".", ",") for a, b in zip(self._d, self._v)]
        texto = "\n".join(linhas)
        QApplication.clipboard().setText(texto)
        return texto
