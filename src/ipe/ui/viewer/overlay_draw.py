"""Desenho, no viewport, dos objetos de CAD/IA/anotações (imaging.overlays) do quadro atual."""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPolygonF

from ipe.imaging import overlays as O

log = logging.getLogger(__name__)
_MASK_CACHE: dict = {}          # id(MaskFrame) -> (MaskFrame, QImage)


def slice_tolerance(vp) -> float:
    fr = vp.frames
    i = vp.index
    if len(fr) > 1 and fr[0].position is not None and fr[0].normal is not None:
        j = i + 1 if i + 1 < len(fr) else i - 1
        if fr[j].position is not None:
            sp = abs(float((np.asarray(fr[j].position) - np.asarray(fr[i].position)) @ fr[0].normal))
            if sp > 0:
                return max(0.5 * sp, 0.3)
    return 1.0


def _mask_image(mf: O.MaskFrame) -> QImage:
    hit = _MASK_CACHE.get(id(mf))
    if hit is not None and hit[0] is mf:
        return hit[1]
    m = mf.mask
    inner = m.copy()
    inner[1:, :] &= m[:-1, :]
    inner[:-1, :] &= m[1:, :]
    inner[:, 1:] &= m[:, :-1]
    inner[:, :-1] &= m[:, 1:]
    edge = m & ~inner
    rgba = np.zeros(m.shape + (4,), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = mf.color[:3]
    rgba[..., 3] = np.where(edge, 235, np.where(m, 90, 0))
    rgba = np.ascontiguousarray(rgba)
    q = QImage(rgba.data, m.shape[1], m.shape[0], rgba.strides[0], QImage.Format_RGBA8888).copy()
    if len(_MASK_CACHE) > 800:
        _MASK_CACHE.clear()
    _MASK_CACHE[id(mf)] = (mf, q)
    return q


def active_overlays(vp) -> list:
    # A segmentação passou a levar o exame (0.68): ela é desenhada em mm, e em outro exame (um
    # anterior aberto ao lado) as mesmas coordenadas não são a mesma mama.
    # 0.99.65: e os de `so_series` (órgãos abdominais, níveis linfonodais) só na série em que foram calculados —
    # em outra série a mesma posição em mm não cai no mesmo lugar (o paciente mexe entre as séries).
    serie = None
    out = []
    for o in getattr(vp, "overlays", []) or []:
        if not o.enabled or (o.study_uid and o.study_uid != vp.study_uid):
            continue
        if getattr(o, "so_series", ""):
            if serie is None:
                serie = O.serie_do_quadro(vp)
            if serie != o.so_series:
                continue
        out.append(o)
    return out


def draw_masks(vp, p: QPainter) -> None:
    """Máscaras (SEG / segmentação): chamada com o pintor já no giro/espelho da imagem."""
    objs = active_overlays(vp)
    if not objs or vp._img is None:
        return
    f = vp.current_frame()
    if f is None:
        return
    pl = vp.plane()
    pos, row, col, n = pl if pl is not None else (None, None, None, None)
    sp = vp._spacing()
    tol = slice_tolerance(vp)
    r = vp._image_rect()
    h, w = vp._img.pixels.shape[:2]
    sx, sy = r.width() / w, r.height() / h
    p.save()
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    for o in objs:
        outro_plano = False
        for mf in o.masks:
            if pos is not None and not O.paralela(mf, n):
                outro_plano = True              # 0.99.16: este corte vem do volume derivado, abaixo
                continue
            try:
                rect = O.mask_rect(mf, pos, row, col, n, sp, tol, f.sop_uid, f.frame_index)
            except Exception:  # noqa: BLE001
                rect = None
            if rect is None:
                continue
            x0, y0, ww, hh = rect
            p.drawImage(QRectF(r.x() + x0 * sx, r.y() + y0 * sy, ww * sx, hh * sy), _mask_image(mf))
        if pos is None:
            continue
        extras = []
        if outro_plano or (o.planar and _contornos_fora_do_plano(o, n)):
            extras = O.volumes_derivados(o)
        for mv in (getattr(o, "volumes", []) or []) + extras:
            if getattr(mv, "so_rotulo", False):
                continue                # níveis da coluna: só o rótulo (draw_rotulos), sem pintar o disco
            try:
                corte = mv.fatia(pos, row, col, n, sp, (h, w))
            except Exception:  # noqa: BLE001
                log.exception("máscara 3D no quadro")
                corte = None
            if corte is None:
                continue
            x0, y0, mf = corte
            hh, ww = mf.mask.shape
            p.drawImage(QRectF(r.x() + x0 * sx, r.y() + y0 * sy, ww * sx, hh * sy), _mask_image(mf))
    p.restore()


def _contornos_fora_do_plano(o, normal) -> bool:
    """Há contorno fechado (RTSTRUCT) num plano que não é o do quadro? Aí ele entra cortado, pelo volume."""
    for g in o.planar:
        if g.kind == "polygon" and g.points3d is not None and len(g.points3d) >= 3:
            c = np.asarray(g.points3d, float)
            if np.abs((c - c.mean(axis=0)) @ np.asarray(normal, float)).max() > 0.5:
                return True
    return False


def draw_graphics(vp, p: QPainter) -> None:
    """Contornos, pontos e textos (SR, GSPS, RTSTRUCT), em coordenadas da tela."""
    objs = active_overlays(vp)
    if not objs or vp._img is None:
        return
    f = vp.current_frame()
    if f is None:
        return
    h, w = vp._img.pixels.shape[:2]
    pl = vp.plane()
    sp = vp._spacing()
    tol = slice_tolerance(vp)
    font = QFont()
    font.setPointSizeF(max(8.0, min(11.0, vp.width() / 55)))
    fm = QFontMetrics(font)
    p.setFont(font)
    labels_done: set = set()
    for o in objs:
        items = list(o.graphics_for(f.sop_uid, f.frame_index))
        if o.planar and pl is not None:
            pos, row, col, n = pl
            for g in o.planar:
                pts = O.project(g.points3d, pos, row, col, n, sp, tol)
                if pts:
                    items.append(O.Graphic(g.kind, pts, g.text, None, g.color))
        for g in items:
            color = QColor(*(g.color if g.color and g.color[0] >= 0 else o.color))
            pen = QPen(color)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            display = g.text == "__display__" or (g.color is not None and g.color[0] < 0)
            pts = [(x * w, y * h) if display else (x, y) for x, y in g.points]
            wp = [vp.image_to_widget(QPointF(x, y)) for x, y in pts]
            if not wp:
                continue
            if g.kind == "point":
                for q in wp:
                    p.drawEllipse(q, 5, 5)
                    p.drawLine(q - QPointF(9, 0), q - QPointF(6, 0))
                    p.drawLine(q + QPointF(6, 0), q + QPointF(9, 0))
            elif g.kind == "polygon":
                p.drawPolygon(QPolygonF(wp))
            elif g.kind == "polyline":
                p.drawPolyline(QPolygonF(wp))
            text = "" if g.text == "__display__" else g.text
            if not text or (o.key, text, g.kind == "text") in labels_done and g.kind != "text":
                continue
            labels_done.add((o.key, text, g.kind == "text"))
            anchor = wp[0] if g.kind == "text" else QPointF(max(q.x() for q in wp) + 6, min(q.y() for q in wp))
            x = max(4.0, min(anchor.x(), vp.width() - 4 - fm.horizontalAdvance(text)))
            y = max(fm.ascent() + 2.0, min(anchor.y() + fm.ascent() / 2, vp.height() - 4))
            p.setPen(QColor(0, 0, 0))
            p.drawText(QPointF(x + 1, y + 1), text)
            p.setPen(color)
            p.drawText(QPointF(x, y), text)
    draw_rotulos(vp, p)


def draw_rotulos(vp, p: QPainter) -> None:
    """Rótulos dos volumes "só rótulo" (níveis da coluna, 0.99.2): o nome vai no centro do pedaço que o
    plano do quadro corta — em qualquer série e plano do exame. Num sagital aparecem todos os níveis;
    num axial, o nível daquele corte (vértebra ou disco)."""
    objs = [o for o in active_overlays(vp) if any(getattr(mv, "so_rotulo", False) for mv in o.volumes)]
    if not objs or vp._img is None:
        return
    pl = vp.plane()
    if pl is None:
        return
    pos, row, col, n = pl
    h, w = vp._img.pixels.shape[:2]
    sp = vp._spacing()
    font = QFont()
    font.setPointSizeF(max(9.0, min(13.0, vp.width() / 45)))
    font.setBold(True)
    fm = QFontMetrics(font)
    p.save()
    p.setFont(font)
    usados: list[QRectF] = []
    for o in objs:
        for mv in o.volumes:
            if not getattr(mv, "so_rotulo", False) or not mv.label:
                continue
            try:
                corte = mv.fatia(pos, row, col, n, sp, (h, w))
            except Exception:  # noqa: BLE001
                corte = None
            if corte is None:
                continue
            x0, y0, mf = corte
            ys, xs = np.nonzero(mf.mask)
            if len(xs) < 4:
                continue                                   # raspão na borda: não é o nível deste corte
            centro = vp.image_to_widget(QPointF(x0 + float(xs.mean()), y0 + float(ys.mean())))
            texto = mv.label
            caixa = QRectF(centro.x() - fm.horizontalAdvance(texto) / 2 - 3, centro.y() - fm.height() / 2,
                           fm.horizontalAdvance(texto) + 6, fm.height())
            if any(caixa.intersects(u) for u in usados):
                continue                                   # dois rótulos no mesmo lugar: fica o primeiro
            usados.append(caixa)
            p.setPen(QColor(0, 0, 0, 200))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                p.drawText(caixa.translated(dx, dy), int(Qt.AlignCenter), texto)
            p.setPen(QColor(*mv.color[:3]))
            p.drawText(caixa, int(Qt.AlignCenter), texto)
    p.restore()
