"""Célula do filme: um Viewport enxuto que mostra uma imagem com os ajustes da célula
(janela, zoom, pan, giro, espelho, inversão) e desenha igual na tela e na impressão."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QMimeData, QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPen, QTransform
from PySide6.QtWidgets import QWidget

from ipe.imaging.series import Frame
from ipe.imaging.windowing import orientation_labels
from ipe.printing.film import Cell
from ipe.ui.viewer.viewport import Viewport

SERIES_MIME = "application/x-dicomviewer-series"
CELL_MIME = "application/x-dicomviewer-filmcell"


class ReadOnlyStore:
    """Mostra as medidas do banco sem deixar a célula alterá-las."""

    def __init__(self, store):
        self.store = store

    def load(self, frames):
        return self.store.load(frames) if self.store is not None else []

    def save(self, _ann) -> None:
        pass

    def delete(self, _ann) -> None:
        pass


def _dist_segmento(p: QPointF, a: QPointF, b: QPointF) -> float:
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    vx, vy = bx - ax, by - ay
    n2 = vx * vx + vy * vy
    t = 0.0 if n2 == 0 else max(0.0, min(1.0, ((p.x() - ax) * vx + (p.y() - ay) * vy) / n2))
    return math.hypot(p.x() - (ax + t * vx), p.y() - (ay + t * vy))


class CellSignals(QObject):
    clicked = Signal(object, object, object)  # célula, modificadores, botão
    expand_requested = Signal()              # duplo clique: expandir/restaurar o filme
    changed = Signal(object)                 # janela/zoom/pan/corte/giro mudou
    menu_requested = Signal(object, object)  # célula, posição global
    dropped = Signal(object, str, str)       # célula, tipo ("series" | "cell"), conteúdo
    delete_requested = Signal(object)
    note_added = Signal(object)              # anotação nova pronta: o mouse volta à função dele


def _fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d or "") == 8 else (d or "")


class FilmCell(Viewport):
    GRIP = 16

    def __init__(self, cache, settings, parent: QWidget | None = None):
        super().__init__(cache, settings, parent)
        self.csig = CellSignals()
        self.cell: Cell | None = None
        self.slot = (0, 0)                  # (folha, posição) no filme
        self.rotation = 0
        self.flip_h = False
        self.pan_frac = QPointF(0, 0)
        self.overlay = "min"
        self.ruler = True
        self.show_measures = True
        self.interactive = True
        self.is_selected = False
        self._drop_hover = False
        self._cpress: dict | None = None
        self._bottom_lines = 1
        self.note_tool = ""                 # "" (função do mouse) | arrow | text | pencil
        self.left_tool = "wl"               # botão esquerdo fora da anotação: wl | pan | zoom
        self.show_notes = True              # anotações do filme à vista (e na impressão)
        self._note_draft: dict | None = None
        self.setAcceptDrops(True)
        self.setMinimumSize(40, 40)

    # ------------------------------------------------------------ dados
    def _start_prefetch(self) -> None:      # células não pré-carregam a série inteira
        pass

    def load(self, cell: Cell | None, frames: list[Frame] | None, study_info: dict | None,
             store=None) -> None:
        self.cell = cell
        if cell is None or not frames:
            self.frames, self.series_uid, self._img, self.annotations = [], "", None, []
            self._qimage_key = None
            self.update()
            return
        idx = next((i for i, f in enumerate(frames)
                    if f.sop_uid == cell.sop_uid and f.frame_index == cell.frame_index), 0)
        self.annotation_store = ReadOnlyStore(store) if store is not None else None
        self.set_series(cell.series_uid, frames, cell.label, study_info or {}, start_index=idx)
        if cell.width is not None and cell.level is not None:
            self.state.width, self.state.level = float(cell.width), float(cell.level)
            self.state.window_set = True
        self.state.zoom = float(cell.zoom or 1.0)
        self.state.invert = bool(cell.invert)
        self.state.cmap = str(getattr(cell, "cmap", "") or "")
        self.state.filter = str(getattr(cell, "filter", "") or "")
        self.rotation = int(cell.rotation or 0) % 360
        self.flip_h = bool(cell.flip_h)
        self.pan_frac = QPointF(float(cell.pan_x or 0), float(cell.pan_y or 0))
        self.show_measures = bool(cell.measures)
        self._qimage_key = None
        self.update()

    def sync_to_cell(self) -> None:
        """Grava na célula (modelo) o que foi ajustado com o mouse."""
        c = self.cell
        if c is None or not self.frames:
            return
        f = self.frames[self.index]
        c.sop_uid, c.frame_index = f.sop_uid, f.frame_index
        if self._img is not None and not self._img.is_color and self.state.window_set:
            c.width, c.level = round(self.state.width, 2), round(self.state.level, 2)
        c.zoom = round(self.state.zoom, 4)
        c.pan_x, c.pan_y = round(self.pan_frac.x(), 4), round(self.pan_frac.y(), 4)
        c.invert, c.rotation, c.flip_h, c.measures = self.state.invert, self.rotation, self.flip_h, \
            self.show_measures
        c.cmap = self.state.cmap
        c.filter = self.state.filter

    def _changed(self) -> None:
        self.sync_to_cell()
        self.update()
        self.csig.changed.emit(self)

    # ------------------------------------------------------------ ações
    def rotate(self, degrees: int) -> None:
        self.rotation = (self.rotation + degrees) % 360
        self._changed()

    def toggle_flip(self) -> None:
        self.flip_h = not self.flip_h
        self._changed()

    def toggle_invert(self) -> None:
        self.state.invert = not self.state.invert
        self._changed()

    def reset_cell(self) -> None:
        self.state.zoom, self.pan_frac, self.rotation, self.flip_h = 1.0, QPointF(0, 0), 0, False
        self.state.window_set = False
        self._load_current()
        if self.cell is not None:
            self.cell.width = self.cell.level = None
        self._changed()

    def set_window(self, width: float, level: float, emit: bool = True) -> None:
        self.state.width, self.state.level = max(1.0, width), level
        self.state.window_set = True
        self._changed()

    def apply_preset(self, key: str, geral: bool = False) -> None:
        super().apply_preset(key, geral)
        self._changed()

    # ------------------------------------------------------------ geometria (com giro/espelho)
    def _swapped(self) -> bool:
        return self.rotation in (90, 270)

    def _frame_box(self) -> tuple[float, float]:
        return (self.height(), self.width()) if self._swapped() else (self.width(), self.height())

    def _linear(self) -> QTransform:
        t = QTransform()
        t.rotate(self.rotation)
        t.scale(-1 if self.flip_h else 1, 1)
        return t

    def view_transform(self) -> QTransform:
        c = QPointF(self.width() / 2, self.height() / 2)
        return QTransform.fromTranslate(-c.x(), -c.y()) * self._linear() * QTransform.fromTranslate(c.x(), c.y())

    def _image_rect(self) -> QRectF:
        if self._img is None:
            return QRectF()
        h, w = self._img.pixels.shape[:2]
        rs, cs = self._spacing()
        aspect = rs / cs if cs else 1.0
        disp_w, disp_h = w, h * aspect
        bw, bh = self._frame_box()
        fit = min(bw / disp_w, bh / disp_h) if disp_w and disp_h else 1
        s = fit * self.state.zoom
        rw, rh = disp_w * s, disp_h * s
        cx = self.width() / 2 + self.pan_frac.x() * bw
        cy = self.height() / 2 + self.pan_frac.y() * bh
        return QRectF(cx - rw / 2, cy - rh / 2, rw, rh)

    def display_orientation(self) -> np.ndarray | None:
        """Vetores de orientação como a imagem aparece (depois do giro/espelho)."""
        f = self.current_frame()
        if f is None or f.orientation is None:
            return None
        r, c = np.asarray(f.orientation[:3], float), np.asarray(f.orientation[3:], float)
        inv, _ok = self._linear().inverted()
        a = inv.map(QPointF(1, 0))
        b = inv.map(QPointF(0, 1))
        return np.concatenate([r * a.x() + c * a.y(), r * b.x() + c * b.y()])

    # ------------------------------------------------------------ desenho
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        self.paint_cell(p, printing=False)
        p.end()

    def paint_to(self, p: QPainter, rect: QRectF) -> None:
        """Desenha a célula (para impressão) no retângulo dado do pintor."""
        self.resize(max(1, int(round(rect.width()))), max(1, int(round(rect.height()))))
        p.save()
        p.translate(rect.topLeft())
        p.setClipRect(QRectF(0, 0, self.width(), self.height()))
        self.paint_cell(p, printing=True)
        p.restore()

    def _font(self, scale: float = 1.0, bold: bool = False) -> QFont:
        f = QFont()
        f.setPixelSize(max(7, int(min(15.0, min(self.width(), self.height()) / 22) * scale)))
        f.setBold(bold)
        return f

    def paint_cell(self, p: QPainter, printing: bool) -> None:
        W, H = self.width(), self.height()
        p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0))
        q = self._qimage_for_current() if self.cell is not None else None
        if q is not None:
            p.save()
            p.setTransform(self.view_transform(), True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.drawImage(self._image_rect(), q)
            if self.show_measures and self.annotations:
                self._draw_measurements(p)
            p.restore()
            self._draw_notes(p)
            if self.overlay != "none":
                self._draw_cell_text(p)
            if self.ruler:
                self._draw_ruler(p)
        elif self.cell is not None:
            p.setPen(QColor(220, 90, 90))
            p.setFont(self._font())
            p.drawText(QRectF(0, 0, W, H), Qt.AlignCenter | Qt.TextWordWrap, "Imagem indisponível")
        elif not printing:
            p.setPen(QColor(95, 95, 95))
            p.setFont(self._font(0.9))
            p.drawText(QRectF(4, 4, W - 8, H - 8), Qt.AlignCenter | Qt.TextWordWrap,
                       "vazio\narraste uma série\nou use “Enviar ao filme”")
        if printing:
            return
        if self._drop_hover:
            p.fillRect(QRectF(0, 0, W, H), QColor(40, 110, 200, 90))
        if self.cell is not None and self.interactive:
            p.setPen(QColor(150, 150, 150))
            p.setFont(self._font(1.0))
            p.drawText(QRectF(2, 1, self.GRIP + 4, self.GRIP + 2), Qt.AlignCenter, "⠿")
        pen = QPen(QColor(255, 200, 0) if self.is_selected else QColor(55, 55, 55))
        pen.setWidth(2 if self.is_selected else 1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(0.5, 0.5, W - 1, H - 1))

    # ------------------------------------------------------------ anotações do filme
    NOTE_COLOR = QColor(255, 225, 0)

    def _note_pt(self, pt) -> QPointF:
        """Ponto da imagem -> ponto da célula (já com zoom, pan, giro e espelho)."""
        return self.view_transform().map(self.image_to_widget(QPointF(float(pt[0]), float(pt[1]))))

    def _img_from_widget(self, pos: QPointF) -> list[float]:
        inv, _ok = self.view_transform().inverted()
        ip = self.widget_to_image(inv.map(pos))
        return [round(ip.x(), 2), round(ip.y(), 2)]

    def _note_scale(self) -> float:
        return max(40.0, min(self.width(), self.height()))

    def _draw_notes(self, p: QPainter) -> None:
        notes = list(self.cell.notes) if self.cell is not None and self.show_notes else []
        if self._note_draft is not None:
            notes.append(self._note_draft)
        if not notes or self._img is None:
            return
        k = self._note_scale()
        width = max(1.5, k / 180)
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        for n in notes:
            pts = [self._note_pt(q) for q in n.get("points", [])]
            if not pts:
                continue
            kind = n.get("kind")
            for color, w in ((QColor(0, 0, 0, 200), width + 2), (self.NOTE_COLOR, width)):
                pen = QPen(color, w)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                if kind == "arrow" and len(pts) >= 2:
                    tip, tail = pts[0], pts[1]
                    p.drawLine(tail, tip)
                    ang = math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
                    head = k * 0.045
                    for da in (0.45, -0.45):
                        p.drawLine(tip, QPointF(tip.x() - head * math.cos(ang + da),
                                                tip.y() - head * math.sin(ang + da)))
                elif kind == "pencil" and len(pts) >= 2:
                    for a, b in zip(pts, pts[1:]):
                        p.drawLine(a, b)
            if kind == "text" and n.get("text"):
                f = self._text_font()
                p.setFont(f)
                fm = QFontMetrics(f)
                x, y = pts[0].x(), pts[0].y() + fm.ascent() / 2
                for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    p.setPen(QColor(0, 0, 0))
                    p.drawText(QPointF(x + dx, y + dy), n["text"])
                p.setPen(self.NOTE_COLOR)
                p.drawText(QPointF(x, y), n["text"])
        p.restore()

    def _text_font(self) -> QFont:
        f = QFont()
        f.setPixelSize(max(8, int(self._note_scale() * 0.055)))
        f.setBold(True)
        return f

    def _text_rect(self, n: dict) -> QRectF | None:
        pts = n.get("points") or []
        if not pts or not n.get("text"):
            return None
        a = self._note_pt(pts[0])
        fm = QFontMetrics(self._text_font())
        return QRectF(a.x() - 3, a.y() - fm.ascent() / 2 - 3,
                      fm.horizontalAdvance(n["text"]) + 6, fm.height() + 6)

    def note_at(self, pos: QPointF):
        """A anotação debaixo do mouse: (índice, parte). Parte: "tip"/"tail" (pontas da seta,
        que mudam o tamanho) ou "all" (o corpo, que move a anotação inteira)."""
        if self.cell is None or not self.cell.notes or not self.show_notes or self._img is None:
            return None
        for i in range(len(self.cell.notes) - 1, -1, -1):
            n = self.cell.notes[i]
            kind = n.get("kind")
            pts = [self._note_pt(q) for q in n.get("points", [])]
            if kind == "text":
                r = self._text_rect(n)
                if r is not None and r.contains(pos):
                    return i, "all"
                continue
            if kind == "arrow" and len(pts) >= 2:
                for parte, q in (("tip", pts[0]), ("tail", pts[1])):
                    if (q - pos).manhattanLength() <= 10:
                        return i, parte
            for a, b in zip(pts, pts[1:]):
                if _dist_segmento(pos, a, b) <= 6:
                    return i, "all"
        return None

    def edit_note_text(self, i: int) -> bool:
        """Duplo clique num texto: muda o texto."""
        from PySide6.QtWidgets import QInputDialog
        n = self.cell.notes[i]
        text, ok = QInputDialog.getText(self, "Texto no filme", "Texto:", text=n.get("text", ""))
        if not ok:
            return False
        if text.strip():
            n["text"] = text.strip()
        else:
            self.cell.notes.pop(i)              # texto apagado: a anotação sai
        self._changed()
        return True

    def _note_press(self, pos: QPointF) -> None:
        ip = self._img_from_widget(pos)
        if self.note_tool == "text":
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(self, "Texto no filme", "Texto:")
            if ok and text.strip():
                self.cell.notes.append({"kind": "text", "points": [ip], "text": text.strip()})
                self._changed()
                self.csig.note_added.emit(self)
            return
        self._note_draft = {"kind": self.note_tool, "points": [ip, ip] if self.note_tool == "arrow" else [ip]}

    def _note_move(self, pos: QPointF) -> None:
        d = self._note_draft
        ip = self._img_from_widget(pos)
        if d["kind"] == "arrow":
            d["points"][1] = ip
        else:
            d["points"].append(ip)
        self.update()

    def _note_release(self) -> None:
        d, self._note_draft = self._note_draft, None
        if d is None:
            return
        a = self._note_pt(d["points"][0])
        b = self._note_pt(d["points"][-1])
        if len(d["points"]) >= 2 and (abs(a.x() - b.x()) + abs(a.y() - b.y()) > 4 or len(d["points"]) > 3):
            self.cell.notes.append(d)
            self._changed()
            self.csig.note_added.emit(self)
        else:
            self.update()

    def undo_note(self) -> None:
        if self.cell is not None and self.cell.notes:
            self.cell.notes.pop()
            self._changed()

    def clear_notes(self) -> None:
        if self.cell is not None and self.cell.notes:
            self.cell.notes.clear()
            self._changed()

    def _draw_cell_text(self, p: QPainter) -> None:
        font = self._font()
        p.setFont(font)
        fm = QFontMetrics(font)
        lh, m = fm.height(), max(3, fm.height() // 4)
        W, H = self.width(), self.height()
        si = self.study_info or {}
        n = len(self.frames)
        tl, tr, bl, br = [], [], [], []
        if self.overlay == "full":
            if not self.anonymize:
                tl += [si.get("patient_name", ""), f"ID {si.get('patient_id', '')}" if si.get("patient_id") else ""]
                tr.append(_fmt_date(si.get("study_date", "")))
            tr.append(self.series_label)
            pos = self._position_text()
            if pos:
                bl.append(pos)
            hdr = self._img.header if self._img is not None else {}
            if hdr.get("SliceThickness"):
                try:
                    bl.append(f"Esp {float(hdr['SliceThickness']):.1f} mm")
                except (TypeError, ValueError):
                    pass
        else:
            tr.append(self.series_label)
        bl.insert(0, f"Im {self.index + 1}/{n}")
        if self._img is not None and not self._img.is_color:
            br.append(f"W {self.state.width:.0f} L {self.state.level:.0f}")
        if self.overlay == "full" and self.state.zoom != 1.0:
            br.append(f"Zoom {self.state.zoom * 100:.0f}%")

        def block(lines, right: bool, bottom: bool, top_pad: float = 0) -> None:
            lines = [t for t in lines if t]
            for i, t in enumerate(lines):
                t = fm.elidedText(t, Qt.ElideRight, int(W * 0.62))
                tw = fm.horizontalAdvance(t)
                x = W - m - tw if right else m + (0 if bottom or right else top_pad)
                y = (H - m - (len(lines) - i) * lh) if bottom else m + i * lh
                p.setPen(QColor(0, 0, 0))
                p.drawText(QPointF(x + 1, y + fm.ascent() + 1), t)
                p.setPen(QColor(235, 235, 235))
                p.drawText(QPointF(x, y + fm.ascent()), t)

        self._bottom_lines = max(len([t for t in bl if t]), len([t for t in br if t]))
        block(tl, False, False, top_pad=self.GRIP if self.interactive else 0)
        block(tr, True, False)
        block(bl, False, True)
        block(br, True, True)
        # letras de orientação
        labels = orientation_labels(self.display_orientation())
        if labels:
            big = self._font(1.1, bold=True)
            p.setFont(big)
            bfm = QFontMetrics(big)
            for side, txt in labels.items():
                tw = bfm.horizontalAdvance(txt)
                x, y = {"left": (m, H / 2 + bfm.ascent() / 2), "right": (W - m - tw, H / 2 + bfm.ascent() / 2),
                        "top": (W / 2 - tw / 2, m + bfm.ascent() + (lh if tr and W < 260 else 0)),
                        "bottom": (W / 2 - tw / 2, H - m - self._text_band() - self._ruler_band())}[side]
                p.setPen(QColor(0, 0, 0))
                p.drawText(QPointF(x + 1, y + 1), txt)
                p.setPen(QColor(255, 220, 120))
                p.drawText(QPointF(x, y), txt)

    def _text_band(self) -> float:
        """Altura das linhas de texto no pé da célula."""
        if self.overlay == "none":
            return 0.0
        return QFontMetrics(self._font()).height() * self._bottom_lines

    def _ruler_band(self) -> float:
        """Altura reservada no pé da célula para a régua (a letra de orientação fica acima)."""
        if not self.ruler or self._img is None or not self._img.pixel_spacing:
            return 0.0
        return QFontMetrics(self._font(0.85)).height() * 2.3

    def mm_por_pixel(self) -> float | None:
        """mm por pixel da célula, na horizontal da tela (zoom incluído). None sem escala."""
        if self._img is None or not self._img.pixel_spacing:
            return None
        rs, cs = self.measure_spacing() or self._img.pixel_spacing
        r = self._image_rect()
        h, w = self._img.pixels.shape[:2]
        if r.width() <= 0 or r.height() <= 0:
            return None
        v = (rs * h / r.height()) if self._swapped() else (cs * w / r.width())
        return v if v > 0 else None

    def _draw_ruler(self, p: QPainter) -> None:
        """Régua de escala (mm) na horizontal, no pé da célula."""
        if self._img is None or not self._img.pixel_spacing:
            return
        mm_per_px = self.mm_por_pixel()
        if not mm_per_px:
            return
        W, H = self.width(), self.height()
        target = W * 0.22 * mm_per_px
        length = next((v for v in (1, 2, 5, 10, 20, 50, 100, 200, 500) if v >= target * 0.6), 500)
        px = length / mm_per_px
        if px > W * 0.45:
            return
        font = self._font(0.85)
        fm = QFontMetrics(font)
        y = H - max(3, fm.height() // 4) - self._text_band() - fm.height() * 1.5
        x0 = W / 2 - px / 2
        for color, off in ((QColor(0, 0, 0), 1), (QColor(235, 235, 235), 0)):
            pen = QPen(color)
            pen.setWidthF(max(1.0, H / 300))
            p.setPen(pen)
            p.drawLine(QPointF(x0 + off, y + off), QPointF(x0 + px + off, y + off))
            for k in range(0, 2 if length < 10 else 3):
                xx = x0 + px * k / (1 if length < 10 else 2)
                tick = fm.height() * (0.45 if k in (0, 2) or length < 10 else 0.3)
                p.drawLine(QPointF(xx + off, y - tick + off), QPointF(xx + off, y + off))
        label = f"{length / 10:g} cm" if length >= 10 else f"{length} mm"
        p.setFont(font)
        tw = fm.horizontalAdvance(label)
        p.setPen(QColor(0, 0, 0))
        p.drawText(QPointF(W / 2 - tw / 2 + 1, y + fm.ascent() + 2), label)
        p.setPen(QColor(235, 235, 235))
        p.drawText(QPointF(W / 2 - tw / 2, y + fm.ascent() + 1), label)

    # ------------------------------------------------------------ mouse
    def _grip_rect(self) -> QRectF:
        return QRectF(0, 0, self.GRIP + 6, self.GRIP + 4)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self.csig.clicked.emit(self, e.modifiers(), e.button())
        self.setFocus()
        pos = e.position()
        if not self.interactive:
            return
        esquerdo = e.button() == Qt.LeftButton
        # a alça ⠿ troca a imagem de lugar, seja qual for a função do mouse
        if esquerdo and self.cell is not None and self._grip_rect().contains(pos):
            self._start_drag()
            return
        if esquerdo and self.note_tool and self.cell is not None and self._img is not None:
            self._cpress = {"button": e.button(), "pos": pos, "last": pos, "moved": False, "note": True}
            self._note_press(pos)
            return
        alvo = self.note_at(pos) if esquerdo else None
        if alvo is not None:
            # em cima de uma anotação: arrastar move (ou estica a seta, pela ponta)
            i, parte = alvo
            self._cpress = {"button": e.button(), "pos": pos, "last": pos, "moved": False,
                            "edit": (i, parte),
                            "orig": [list(q) for q in self.cell.notes[i].get("points", [])],
                            "img0": self._img_from_widget(pos)}
            return
        self._cpress = {"button": e.button(), "pos": pos, "last": pos, "moved": False}

    def _start_drag(self) -> None:
        md = QMimeData()
        md.setData(CELL_MIME, f"{self.slot[0]},{self.slot[1]}".encode())
        drag = QDrag(self)
        drag.setMimeData(md)
        pm = self.grab().scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        drag.setPixmap(pm)
        drag.exec(Qt.MoveAction)

    def _cursor_parado(self, pos: QPointF) -> None:
        if self.cell is None:
            self.setCursor(Qt.ArrowCursor)
        elif self._grip_rect().contains(pos):
            self.setCursor(Qt.OpenHandCursor)
        elif self.note_tool:
            self.setCursor(Qt.CrossCursor)
        else:
            alvo = self.note_at(pos)
            if alvo is None:
                self.setCursor(Qt.ArrowCursor)
            elif alvo[1] == "all":
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.SizeFDiagCursor)

    def _editar_nota(self, pr: dict, pos: QPointF) -> None:
        i, parte = pr["edit"]
        n = self.cell.notes[i]
        agora = self._img_from_widget(pos)
        if parte == "all":
            dx, dy = agora[0] - pr["img0"][0], agora[1] - pr["img0"][1]
            n["points"] = [[round(q[0] + dx, 2), round(q[1] + dy, 2)] for q in pr["orig"]]
        else:
            n["points"][0 if parte == "tip" else 1] = agora
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        pr = self._cpress
        pos = e.position()
        if pr is None:
            self._cursor_parado(pos)
            return
        if pr.get("note"):
            if self._note_draft is not None:
                self._note_move(pos)
            return
        if not pr["moved"] and (pos - pr["pos"]).manhattanLength() <= 3:
            return
        pr["moved"] = True
        if pr.get("edit"):
            self._editar_nota(pr, pos)
            return
        dx, dy = pos.x() - pr["last"].x(), pos.y() - pr["last"].y()
        pr["last"] = pos
        if self._img is None:
            return
        b = pr["button"]
        if b == Qt.LeftButton:
            acao = {"wl": "janela", "pan": "mover", "zoom": "zoom"}.get(self.left_tool, "janela")
        elif b == Qt.RightButton:
            acao = "zoom"
        elif b == Qt.MiddleButton:
            acao = "mover"
        else:
            return
        if acao == "janela":
            if self._img.is_color:
                return
            k = max(self.state.width, 1.0) / 300.0
            self.state.width = max(1.0, self.state.width + dx * k)
            self.state.level += dy * k
            self.state.window_set = True
        elif acao == "zoom":
            f = float(np.clip(self.state.zoom * math.exp(-dy * 0.01), 0.1, 40)) / self.state.zoom
            self.state.zoom *= f
            self.pan_frac = self.pan_frac * f
        else:
            inv, _ok = self._linear().inverted()
            d = inv.map(QPointF(dx, dy))
            bw, bh = self._frame_box()
            self.pan_frac += QPointF(d.x() / max(bw, 1), d.y() / max(bh, 1))
        self._changed()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        pr, self._cpress = self._cpress, None
        if pr is not None and pr.get("note"):
            self._note_release()
            return
        if pr is not None and pr.get("edit"):
            if pr["moved"]:
                self._changed()
            return
        if pr is None or pr["moved"]:
            return
        if pr["button"] == Qt.RightButton:
            self.csig.menu_requested.emit(self, e.globalPosition().toPoint())
        elif pr["button"] == Qt.MiddleButton:
            self.state.zoom, self.pan_frac = 1.0, QPointF(0, 0)
            self._changed()

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton or not self.interactive:
            return
        alvo = self.note_at(e.position())
        if alvo is not None and self.cell.notes[alvo[0]].get("kind") == "text":
            self._cpress = None
            self.edit_note_text(alvo[0])
            return
        self.csig.expand_requested.emit()

    def wheelEvent(self, e) -> None:  # noqa: N802
        if not self.interactive or not self.frames:
            return
        d = e.angleDelta()
        steps = (d.y() or d.x()) / 120
        if steps:
            self.step(-1 if steps > 0 else 1)
            self._changed()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        k = e.key()
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.csig.delete_requested.emit(self)
        elif k in (Qt.Key_Up, Qt.Key_Left, Qt.Key_PageUp) and self.frames:
            self.step(-1)
            self._changed()
        elif k in (Qt.Key_Down, Qt.Key_Right, Qt.Key_PageDown) and self.frames:
            self.step(1)
            self._changed()
        else:
            e.ignore()

    def leaveEvent(self, _e) -> None:  # noqa: N802
        pass

    # ------------------------------------------------------------ arrastar e soltar
    def _kind(self, md) -> str | None:
        if md.hasFormat(CELL_MIME):
            return "cell"
        if md.hasFormat(SERIES_MIME):
            return "series"
        return None

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if self.interactive and self._kind(e.mimeData()):
            self._drop_hover = True
            self.update()
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if self._kind(e.mimeData()):
            e.acceptProposedAction()

    def dragLeaveEvent(self, _e) -> None:  # noqa: N802
        self._drop_hover = False
        self.update()

    def dropEvent(self, e) -> None:  # noqa: N802
        self._drop_hover = False
        md = e.mimeData()
        kind = self._kind(md)
        if kind is None:
            return
        fmt = CELL_MIME if kind == "cell" else SERIES_MIME
        e.acceptProposedAction()
        self.csig.dropped.emit(self, kind, bytes(md.data(fmt)).decode())
        self.update()
