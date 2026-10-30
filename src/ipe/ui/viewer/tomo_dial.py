"""Indicador de profundidade da tomossíntese, no canto externo do quadro.

É o desenho que a estação de trabalho mostra: o relógio da mama, a mama comprimida vista
de perfil no ângulo real do braço e um marcador no corte que está na tela. Aqui ele também
navega — arrastar o marcador leva ao corte daquela profundidade.

Convenções, todas escolhidas com o usuário:
- **Relógio de frente para a paciente**: 12 em cima, 3 à direita da caixinha nas duas mamas;
  o que muda de lado é o significado, então medial e lateral aparecem escritos (M e L).
- **Canto externo**: do lado oposto à parede torácica, que o quadro já sabe dizer.
- A faixa é a **reconstrução inteira** (é o que dá para rolar) e a pá de compressão ganha
  uma marca tracejada, porque a reconstrução costuma passar da mama.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF

from ipe.imaging import tomo_pos as TP

HOTSPOT = "tomodial"
MAMA_MM = 140.0          # diâmetro que o círculo representa, para a faixa sair em escala


def geometry(vp):
    """Geometria da tomo do quadro (None quando não é tomossíntese)."""
    if not vp.frames or not vp.in_tomo():
        return None
    inicio, fim = vp.tomo_range if vp.tomo_range is not None else (0, len(vp.frames))
    quadros = vp.frames[inicio:fim]
    if len(quadros) < 2:
        return None
    return TP.from_frames(quadros)


def _radius(vp) -> float:
    return float(min(32.0, max(18.0, vp.width() / 20.0)))


LADO_PX = 13.0           # folga para as letras de medial e lateral, fora do círculo


def box(vp, lh: float = 0.0, linhas: int = 0, margem: float = 6.0) -> QRectF:
    """Retângulo do indicador: canto de baixo do lado oposto à parede torácica."""
    r = _radius(vp)
    larg = 2 * r + 12 + 2 * LADO_PX
    alt = 2 * r + 12 + lh
    parede = vp.chest_screen_side()
    fora_esquerda = parede != "left"          # parede à direita (ou desconhecida) -> canto esquerdo
    x = margem if fora_esquerda else vp.width() - margem - larg
    y = vp.height() - margem - alt - linhas * lh
    return QRectF(x, max(y, margem), larg, alt)


def _axis(geo) -> tuple[float, float]:
    """Direção do detector para a pá, em coordenadas da tela (x para a direita, y para baixo)."""
    a = math.radians(geo.angle_deg or 0.0)
    sinal = -1.0 if (geo.side or "R").upper().startswith("L") else 1.0
    return sinal * math.sin(a), -math.cos(a)


def _band(vp, geo, rect: QRectF, lh: float):
    """Centro do círculo, raio, direção do eixo e altura da faixa."""
    r = _radius(vp)
    c = QPointF(rect.x() + rect.width() / 2, rect.y() + 6 + r)
    ax, ay = _axis(geo)
    escala = min(max(geo.scale_mm / MAMA_MM, 0.25), 0.85)
    return c, r, (ax, ay), 2 * r * escala


def draw(vp, p, font: QFont, lh: float = 0.0, linhas: int = 0) -> None:
    """Desenha o indicador e registra a área clicável."""
    geo = geometry(vp)
    if geo is None:
        return
    rect = box(vp, lh, linhas)
    vp._hotspots.setdefault(HOTSPOT, rect)
    c, r, (ax, ay), faixa = _band(vp, geo, rect, lh)
    quente = vp._hover == HOTSPOT
    i = max(0, vp.index - (vp.tomo_range[0] if vp.tomo_range is not None else 0))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(0, 0, 0, 150))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(rect, 5, 5)

    # ---- relógio
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 220, 120) if quente else QColor(150, 160, 175), 1.2))
    p.drawEllipse(c, r, r)
    hf = QFont(font)
    hf.setPointSizeF(max(6.0, r * 0.26))
    p.setFont(hf)
    hfm = QFontMetrics(hf)
    p.setPen(QColor(200, 205, 215))
    for hora, (dx, dy) in (("12", (0, -1)), ("3", (1, 0)), ("6", (0, 1)), ("9", (-1, 0))):
        tw = hfm.horizontalAdvance(hora)
        pt = QPointF(c.x() + dx * (r - 9) - tw / 2, c.y() + dy * (r - 9) + hfm.ascent() / 2)
        p.drawText(pt, hora)
    # medial e lateral: nas duas mamas o relógio é o mesmo; o que muda é o significado
    if geo.side:
        med_dir = 1 if geo.side.upper().startswith("R") else -1
        lf = QFont(font)
        lf.setPointSizeF(max(5.5, r * 0.22))
        lfm = QFontMetrics(lf)
        p.setFont(lf)
        p.setPen(QColor(120, 160, 200))
        for letra, lado in (("M", med_dir), ("L", -med_dir)):
            tw = lfm.horizontalAdvance(letra)
            p.drawText(QPointF(c.x() + lado * (r + LADO_PX * 0.55) - tw / 2,
                               c.y() + lfm.ascent() / 2), letra)
        p.setFont(hf)

    # ---- mama comprimida de perfil, no ângulo do braço
    bx, by = -ay, ax                    # direção das placas (perpendicular ao eixo)
    meia = faixa / 2

    def ponto(t_eixo: float, t_placa: float) -> QPointF:
        return QPointF(c.x() + ax * t_eixo + bx * t_placa, c.y() + ay * t_eixo + by * t_placa)

    p.setPen(QPen(QColor(170, 180, 195), 1.4))
    for k in (-1, 1):                   # as duas placas
        p.drawLine(ponto(k * meia, -r), ponto(k * meia, r))
    p.setPen(QPen(QColor(88, 98, 110), 1.0))
    for k in (-0.5, 0.0, 0.5):          # tecido entre as placas
        p.drawLine(ponto(k * meia, -r * 0.9), ponto(k * meia, r * 0.9))

    # ---- marca da pá (a reconstrução passa da mama)
    fp = geo.paddle_fraction()
    if fp is not None and fp < 0.98:
        caneta = QPen(QColor(110, 190, 150), 1.0, Qt.DashLine)
        p.setPen(caneta)
        t = (fp - 0.5) * faixa
        p.drawLine(ponto(t, -r * 0.8), ponto(t, r * 0.8))

    # ---- marcador do corte
    f = geo.fraction(i)
    t = (f - 0.5) * faixa
    p.setPen(QPen(QColor(255, 190, 60), 1.5))
    p.drawLine(ponto(t, -r * 0.9), ponto(t, r * 0.9))
    p.setBrush(QColor(255, 190, 60))
    p.setPen(Qt.NoPen)
    for k in (-1, 1):                   # uma seta em cada ponta, como na estação
        base = ponto(t, k * r * 0.9)
        asa = QPointF(bx * k * 4.5, by * k * 4.5)
        p.drawPolygon(QPolygonF([base,
                                 QPointF(base.x() + asa.x() + ax * 3.5, base.y() + asa.y() + ay * 3.5),
                                 QPointF(base.x() + asa.x() - ax * 3.5, base.y() + asa.y() - ay * 3.5)]))

    # ---- profundidade em milímetros
    if lh:
        sf = QFont(font)
        sf.setPointSizeF(max(6.5, min(font.pointSizeF(), r * 0.3)))
        p.setFont(sf)
        sfm = QFontMetrics(sf)
        txt = geo.depth_text(i)
        if geo.source == "estimado":
            txt += " (estimado)"
        tw = sfm.horizontalAdvance(txt)
        p.setPen(QColor(230, 230, 230))
        p.drawText(QPointF(c.x() - tw / 2, rect.bottom() - 4), txt)
    p.restore()


def index_at(vp, pos: QPointF, lh: float = 0.0, linhas: int = 0) -> int | None:
    """Índice do quadro sob o ponto clicado dentro do indicador."""
    geo = geometry(vp)
    if geo is None:
        return None
    rect = box(vp, lh, linhas)
    c, _r, (ax, ay), faixa = _band(vp, geo, rect, lh)
    t = (pos.x() - c.x()) * ax + (pos.y() - c.y()) * ay
    f = t / faixa + 0.5
    inicio = vp.tomo_range[0] if vp.tomo_range is not None else 0
    return inicio + geo.index_at(f)


def tip(vp) -> str:
    geo = geometry(vp)
    if geo is None:
        return ""
    inicio = vp.tomo_range[0] if vp.tomo_range is not None else 0
    return geo.tip_text(max(0, vp.index - inicio))
