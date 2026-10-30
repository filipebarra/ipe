"""Histograma da imagem (ou da ROI selecionada), com a janela atual marcada.

Serve para escolher a janela olhando a distribuição dos valores: os botões ajustam a janela do
quadro pelos percentis ou pela ROI.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ipe.imaging import measure as M

BARS = QColor(120, 190, 255)
WINDOW_FILL = QColor(255, 200, 60, 45)
AXIS = QColor(150, 150, 150)


class HistogramView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.counts = np.zeros(1)
        self.edges = np.array([0.0, 1.0])
        self.window: tuple[float, float] | None = None
        self.log = False
        self.setMinimumHeight(220)

    def set_data(self, counts, edges, window) -> None:
        self.counts, self.edges, self.window = counts, edges, window
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(24, 25, 28))
        font = QFont()
        font.setPointSizeF(8.5)
        p.setFont(font)
        fm = QFontMetrics(font)
        left, bottom, top, right = 52, 22, 8, 10
        plot = QRectF(left, top, max(10, self.width() - left - right), max(10, self.height() - top - bottom))
        c = self.counts.astype(float)
        if c.size == 0 or c.max() <= 0:
            p.setPen(AXIS)
            p.drawText(self.rect(), Qt.AlignCenter, "Sem dados")
            p.end()
            return
        vals = np.log10(c + 1) if self.log else c
        vmax = float(vals.max()) or 1.0
        x0, x1 = float(self.edges[0]), float(self.edges[-1])
        span = (x1 - x0) or 1.0
        if self.window:
            w, l = self.window
            a = (l - w / 2 - x0) / span * plot.width() + plot.left()
            b = (l + w / 2 - x0) / span * plot.width() + plot.left()
            p.fillRect(QRectF(max(plot.left(), a), plot.top(), min(plot.right(), b) - max(plot.left(), a),
                              plot.height()), WINDOW_FILL)
        bw = plot.width() / len(vals)
        p.setPen(Qt.NoPen)
        p.setBrush(BARS)
        for i, v in enumerate(vals):
            h = v / vmax * plot.height()
            p.drawRect(QRectF(plot.left() + i * bw, plot.bottom() - h, max(1.0, bw), h))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(AXIS))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        p.drawLine(plot.topLeft(), plot.bottomLeft())
        for k in range(5):                                   # marcas do eixo dos valores
            x = plot.left() + plot.width() * k / 4
            val = x0 + span * k / 4
            p.drawLine(QPointF(x, plot.bottom()), QPointF(x, plot.bottom() + 3))
            txt = f"{val:.0f}" if abs(val) >= 10 else f"{val:.2f}"
            p.drawText(QPointF(min(x - fm.horizontalAdvance(txt) / 2, self.width() - fm.horizontalAdvance(txt) - 2),
                               plot.bottom() + fm.ascent() + 4), txt)
        top_txt = f"{int(c.max()):,}".replace(",", ".") + (" (log)" if self.log else "")
        p.drawText(QPointF(4, plot.top() + fm.ascent()), top_txt)
        p.drawText(QPointF(4, plot.bottom()), "0")
        p.end()


class HistogramDialog(QDialog):
    def __init__(self, vp, parent=None):
        super().__init__(parent)
        self.vp = vp
        self.setWindowTitle("Histograma")
        self.resize(640, 420)
        self.view = HistogramView()
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.source = QComboBox()
        self.source.addItem("Imagem inteira", "image")
        self.source.addItem("Dentro da ROI selecionada", "roi")
        self.source.activated.connect(lambda _i: self.refresh())
        self.bins = QComboBox()
        for n in (64, 128, 256, 512):
            self.bins.addItem(f"{n} barras", n)
        self.bins.setCurrentIndex(2)
        self.bins.activated.connect(lambda _i: self.refresh())
        self.log = QCheckBox("Escala log")
        self.log.toggled.connect(lambda on: (setattr(self.view, "log", on), self.view.update()))
        top = QHBoxLayout()
        top.addWidget(QLabel("Dados:"))
        top.addWidget(self.source)
        top.addWidget(self.bins)
        top.addWidget(self.log)
        top.addStretch(1)
        b_p = QPushButton("Janela pelos percentis 1–99")
        b_p.clicked.connect(lambda: self.apply_window(1, 99))
        b_p2 = QPushButton("Janela 5–95")
        b_p2.clicked.connect(lambda: self.apply_window(5, 95))
        b_copy = QPushButton("Copiar dados")
        b_copy.clicked.connect(self.copy)
        b_close = QPushButton("Fechar")
        b_close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(b_p)
        row.addWidget(b_p2)
        row.addStretch(1)
        row.addWidget(b_copy)
        row.addWidget(b_close)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.info)
        lay.addLayout(row)
        self.refresh()

    # ------------------------------------------------------------ dados
    def values(self) -> np.ndarray | None:
        img = self.vp._img
        if img is None or img.is_color:
            return None
        px = img.pixels
        ann = self.vp.selected
        if self.source.currentData() == "roi" and ann is not None and ann.kind in M.ROI_KINDS:
            res = M.roi_mask(ann.kind, ann.points, px.shape)
            if res is not None:
                sl, mask = res
                return px[sl][mask].astype(np.float64)
        return px.astype(np.float64).ravel()

    def refresh(self) -> None:
        has_roi = self.vp.selected is not None and self.vp.selected.kind in M.ROI_KINDS
        self.source.model().item(1).setEnabled(has_roi)
        if not has_roi and self.source.currentData() == "roi":
            self.source.setCurrentIndex(0)
        v = self.values()
        if v is None or v.size == 0:
            self.info.setText("Esta imagem não tem valores numéricos (colorida) ou a ROI está vazia.")
            self.view.set_data(np.zeros(1), np.array([0.0, 1.0]), None)
            return
        n = int(self.bins.currentData())
        counts, edges = np.histogram(v, bins=n)
        self.view.set_data(counts, edges, (self.vp.state.width, self.vp.state.level))
        unit = M.unit_for(self.vp.modality)
        suv = getattr(self.vp, "suv_factor", None)
        p1, p50, p99 = np.percentile(v, [1, 50, 99])
        txt = (f"{v.size:,} pixels".replace(",", ".") +
               f" · média {v.mean():.1f} ± {v.std():.1f}{' ' + unit if unit else ''}"
               f" · mín {v.min():.1f} · mediana {p50:.1f} · máx {v.max():.1f}"
               f" · p1 {p1:.1f} · p99 {p99:.1f}")
        if suv:
            txt += f"  ·  SUVmáx {v.max() * suv:.2f}, SUVméd {v.mean() * suv:.2f}"
        txt += f"  ·  janela atual: L {self.vp.state.level:.0f} / W {self.vp.state.width:.0f}"
        self.info.setText(txt)
        self._values = v

    def apply_window(self, lo_pct: float, hi_pct: float) -> None:
        v = getattr(self, "_values", None)
        if v is None or v.size == 0:
            return
        lo, hi = np.percentile(v, [lo_pct, hi_pct])
        if hi <= lo:
            return
        self.vp.state.window_set = True
        self.vp.set_window(float(hi - lo), float((hi + lo) / 2))
        self.vp._qimage_key = None
        self.vp.update()
        self.refresh()

    def copy(self) -> None:
        counts, edges = np.histogram(getattr(self, "_values", np.zeros(1)), bins=int(self.bins.currentData()))
        lines = ["valor;contagem"] + [f"{(edges[i] + edges[i + 1]) / 2:.4f};{int(c)}" for i, c in enumerate(counts)]
        QApplication.clipboard().setText("\n".join(lines))
        self.info.setText(self.info.text() + "   (dados copiados)")
