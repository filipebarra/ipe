"""Curva tempo-intensidade (cinética) de uma ROI, para RM dinâmica (ex.: mama).

As fases são procuradas assim:
1. na mesma série, imagens na mesma posição (fases guardadas numa série só);
2. se não houver, em outras séries do mesmo estudo com a mesma orientação,
   o mesmo tamanho de imagem e um corte na mesma posição (uma série por fase).
O tempo vem do AcquisitionTime (ou da ordem das séries, se faltar).
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.imaging import measure as M
from ipe.imaging.series import build_frames
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)


def _seconds(t: str) -> float | None:
    t = (t or "").replace(":", "").strip()
    if len(t) < 4:
        return None
    try:
        hh, mm = int(t[0:2]), int(t[2:4])
        ss = float(t[4:]) if len(t) > 4 else 0.0
        return hh * 3600 + mm * 60 + ss
    except ValueError:
        return None


def collect(tab, vp, ann) -> list[tuple[float | None, float, str]]:
    """[(tempo em s ou None, média na ROI, rótulo)] ordenado pelo tempo."""
    f0 = vp.current_frame()
    if f0 is None or f0.position is None or f0.orientation is None:
        return []
    normal = f0.normal
    shape = vp._img.pixels.shape if vp._img is not None else None
    spacing = vp.measure_spacing()

    def same_pos(f, tol=0.6) -> bool:
        return (f.position is not None and f.orientation is not None
                and np.allclose(f.orientation, f0.orientation, atol=1e-3)
                and abs(float((np.asarray(f.position) - np.asarray(f0.position)) @ normal)) <= tol
                and float(np.linalg.norm(np.asarray(f.position) - np.asarray(f0.position))) <= 2.0)

    if vp.phases:                      # série dinâmica agrupada: uma fase por série
        from ipe.imaging.phases import map_index
        phases = [(ph[map_index(vp.frames, vp.index, ph)], lab)
                  for ph, lab in zip(vp.phases, vp.phase_labels)]
    else:
        phases = [(f, vp.series_label) for f in vp.frames if same_pos(f)]
    if len(phases) < 2:
        phases = [(f0, vp.series_label)]
        cur = vp.series_uid
        for s in tab.series:
            if s.series_uid == cur or s.study_uid != vp.study_uid or s.modality != vp.modality:
                continue
            frames = build_frames(tab.repo.instances_for_series(s.series_uid), s.series_uid)
            cand = [f for f in frames if same_pos(f)]
            if cand:
                phases.append((cand[0], f"Se {s.series_number} {s.description}"))
    out = []
    for f, label in phases:
        try:
            img = tab.cache.get(f)
        except Exception as e:  # noqa: BLE001
            log.warning("Fase ilegível %s: %s", f.path, e)
            continue
        if img.is_color or (shape is not None and img.pixels.shape != shape):
            continue
        st = M.roi_stats(img.pixels, "ellipse", ann.points, spacing)
        if st.mean is None:
            continue
        out.append((_seconds(f.acquisition_time), st.mean, label))
    if all(t is not None for t, _m, _l in out):
        out.sort(key=lambda r: r[0])
        t0 = out[0][0] if out else 0.0
        out = [(t - t0, m, l) for t, m, l in out]
    return out


class _Chart(QWidget):
    def __init__(self, times: list[float], enh: list[float], parent=None):
        super().__init__(parent)
        self.times, self.enh = times, enh
        self.setMinimumSize(520, 280)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(24, 24, 26))
        m = QRectF(56, 16, self.width() - 76, self.height() - 52)
        ymax = max(20.0, max(self.enh) * 1.15) if self.enh else 100.0
        ymin = min(0.0, min(self.enh) * 1.15) if self.enh else 0.0
        tmax = max(self.times) or 1.0

        def pt(t, e) -> QPointF:
            return QPointF(m.left() + t / tmax * m.width(), m.bottom() - (e - ymin) / (ymax - ymin) * m.height())
        grid = QPen(QColor(70, 70, 70))
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        for k in range(6):
            e = ymin + (ymax - ymin) * k / 5
            y = pt(0, e).y()
            p.setPen(grid)
            p.drawLine(QPointF(m.left(), y), QPointF(m.right(), y))
            p.setPen(QColor(170, 170, 170))
            p.drawText(QRectF(0, y - 8, 50, 16), Qt.AlignRight | Qt.AlignVCenter, f"{e:.0f}%")
        for k in range(6):
            t = tmax * k / 5
            x = pt(t, 0).x()
            p.setPen(QColor(170, 170, 170))
            p.drawText(QRectF(x - 30, m.bottom() + 4, 60, 16), Qt.AlignCenter, f"{t / 60:.1f} min")
        p.setPen(QPen(QColor(120, 120, 120)))
        p.drawRect(m)
        pts = [pt(t, e) for t, e in zip(self.times, self.enh)]
        p.setPen(QPen(QColor(255, 110, 110), 2.5))
        p.drawPolyline(QPolygonF(pts))
        p.setBrush(QColor(255, 110, 110))
        for q in pts:
            p.drawEllipse(q, 4, 4)
        p.setPen(QColor(200, 200, 200))
        p.drawText(QRectF(m.left(), m.bottom() + 20, m.width(), 16), Qt.AlignCenter,
                   "tempo desde a fase pré-contraste · eixo vertical: realce relativo (%)")


class TicDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Curva tempo-intensidade")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        timed = all(t is not None for t, _m, _l in rows)
        times = [t if timed else i * 60.0 for i, (t, _m, _l) in enumerate(rows)]
        values = [m for _t, m, _l in rows]
        self.result = M.tic_analysis(times, values)
        head = QLabel(f"<b>{self.result['summary']}</b>" + ("" if timed else
                      "<br><i>Sem horário de aquisição: fases colocadas a cada 1 min, só na ordem.</i>"))
        head.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(_Chart(times, self.result["enhancement"] or [0.0] * len(times)), 1)
        t = QTableWidget(len(rows), 4)
        t.setHorizontalHeaderLabels(["Fase", "Tempo", "Média na ROI", "Realce"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i, (tm, m, lab) in enumerate(rows):
            enh = self.result["enhancement"][i] if self.result["enhancement"] else 0.0
            for c, v in enumerate((lab, f"{times[i] / 60:.2f} min", f"{m:.1f}", f"{enh:+.0f}%")):
                t.setItem(i, c, QTableWidgetItem(v))
        lay.addWidget(t)
        colunas_ajustaveis(t)
        note = QLabel("Critérios: realce inicial nos primeiros 2 min (lento < 50%, médio 50–100%, "
                      "rápido > 100%); fase tardia comparada ao pico inicial (> +10% persistente, "
                      "±10% platô, < −10% washout). Ferramenta de pesquisa e ensino, "
                      "não destinada a uso diagnóstico.")
        note.setWordWrap(True)
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
