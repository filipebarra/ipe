"""Ícones vetoriais desenhados com QPainter (sem arquivos de imagem, sem licença de terceiros)."""

from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

FG = QColor(232, 232, 232)
ACCENT = QColor(79, 179, 255)
GREEN = QColor(80, 220, 120)
GOLD = QColor(255, 200, 40)
S = 64          # desenhado em 64 px; o Qt reduz para o tamanho da barra


def _pen(color=FG, w=4.0, style=Qt.SolidLine) -> QPen:
    p = QPen(color, w, style)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def P(x, y) -> QPointF:
    return QPointF(x, y)


def _draw(name: str, p: QPainter) -> None:  # noqa: C901 - um caso por ícone
    p.setPen(_pen())
    p.setBrush(Qt.NoBrush)
    if name == "wl":
        p.drawEllipse(QRectF(10, 10, 44, 44))
        path = QPainterPath()
        path.moveTo(32, 10)
        path.arcTo(QRectF(10, 10, 44, 44), 90, 180)
        path.closeSubpath()
        p.fillPath(path, FG)
    elif name == "pan":
        p.setPen(_pen(ACCENT))
        p.drawLine(P(32, 8), P(32, 56))
        p.drawLine(P(8, 32), P(56, 32))
        for a, b, c in (((32, 6), (25, 14), (39, 14)), ((32, 58), (25, 50), (39, 50)),
                        ((6, 32), (14, 25), (14, 39)), ((58, 32), (50, 25), (50, 39))):
            p.setBrush(ACCENT)
            p.drawPolygon(QPolygonF([P(*a), P(*b), P(*c)]))
    elif name == "zoom":
        p.setPen(_pen(ACCENT, 5))
        p.drawEllipse(QRectF(8, 8, 34, 34))
        p.drawLine(P(38, 38), P(56, 56))
        p.setPen(_pen(FG, 4))
        p.drawLine(P(25, 17), P(25, 33))
        p.drawLine(P(17, 25), P(33, 25))
    elif name == "scroll":
        for i, y in enumerate((14, 26, 38)):
            poly = QPolygonF([P(10, y + 6), P(32, y - 4), P(54, y + 6), P(32, y + 16)])
            p.setBrush(QColor(232, 232, 232, 255 - i * 60))
            p.drawPolygon(poly)
    elif name == "measure":
        p.drawLine(P(12, 52), P(52, 12))
        for q in (P(12, 52), P(52, 12)):
            p.setBrush(FG)
            p.drawEllipse(q, 4, 4)
    elif name == "polyline":
        pts = [P(8, 50), P(22, 22), P(38, 40), P(56, 12)]
        p.drawPolyline(QPolygonF(pts))
        p.setBrush(FG)
        for q in pts:
            p.drawEllipse(q, 3.5, 3.5)
    elif name == "angle":
        p.drawLine(P(10, 52), P(56, 52))
        p.drawLine(P(10, 52), P(44, 12))
        p.setPen(_pen(ACCENT, 3))
        p.drawArc(QRectF(-8, 34, 36, 36), 0, 50 * 16)
    elif name == "cobb":
        p.drawLine(P(8, 20), P(56, 12))
        p.drawLine(P(8, 44), P(56, 56))
        p.setPen(_pen(ACCENT, 3, Qt.DotLine))
        p.drawLine(P(30, 16), P(34, 40))
        p.drawLine(P(34, 50), P(28, 30))
    elif name == "ellipse":
        p.drawEllipse(QRectF(8, 16, 48, 32))
    elif name == "rect":
        p.drawRect(QRectF(10, 14, 44, 36))
    elif name == "polygon":
        p.drawPolygon(QPolygonF([P(12, 20), P(34, 8), P(56, 26), P(46, 54), P(16, 50)]))
    elif name == "probe":
        p.drawEllipse(QRectF(16, 16, 32, 32))
        for a, b in ((P(32, 4), P(32, 20)), (P(32, 44), P(32, 60)), (P(4, 32), P(20, 32)), (P(44, 32), P(60, 32))):
            p.drawLine(a, b)
        p.setBrush(ACCENT)
        p.setPen(Qt.NoPen)
        p.drawEllipse(P(32, 32), 5, 5)
    elif name == "height":
        p.drawLine(P(6, 14), P(28, 14))
        p.drawLine(P(36, 50), P(58, 50))
        p.setPen(_pen(ACCENT, 3))
        p.drawLine(P(46, 14), P(46, 46))
        p.drawLine(P(40, 40), P(46, 47))
        p.drawLine(P(52, 40), P(46, 47))
        p.setPen(_pen(FG, 2, Qt.DashLine))
        p.drawLine(P(28, 14), P(46, 14))
    elif name == "ctr":
        path = QPainterPath()
        path.moveTo(10, 56)
        path.cubicTo(6, 20, 20, 8, 32, 8)
        path.cubicTo(44, 8, 58, 20, 54, 56)
        p.drawPath(path)
        p.setBrush(QColor(255, 110, 110))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(22, 30, 22, 18))
        p.setPen(_pen(ACCENT, 3))
        p.drawLine(P(20, 52), P(46, 52))
    elif name == "spine":
        for i, y in enumerate((6, 20, 34, 48)):
            p.setBrush(QColor(232, 232, 232, 200))
            p.drawRoundedRect(QRectF(20, y, 24, 10), 3, 3)
            p.setBrush(ACCENT)
            p.setPen(Qt.NoPen)
            p.drawEllipse(P(52, y + 5), 3.5, 3.5)
            p.setPen(_pen())
    elif name == "tic":
        p.drawLine(P(8, 8), P(8, 56))
        p.drawLine(P(8, 56), P(58, 56))
        p.setPen(_pen(QColor(255, 110, 110), 4))
        path = QPainterPath()
        path.moveTo(10, 50)
        path.cubicTo(18, 14, 26, 14, 34, 18)
        path.lineTo(56, 34)
        p.drawPath(path)
    elif name == "calibration":
        p.setBrush(QColor(255, 120, 255, 70))
        p.drawRect(QRectF(6, 24, 52, 16))
        for i, x in enumerate(range(10, 58, 6)):
            p.drawLine(P(x, 24), P(x, 30 if i % 2 else 33))
    elif name == "arrow":
        p.setPen(_pen(GOLD, 4))
        p.drawLine(P(54, 54), P(14, 14))
        p.drawLine(P(14, 14), P(30, 16))
        p.drawLine(P(14, 14), P(16, 30))
    elif name == "text":
        f = QFont()
        f.setPixelSize(48)
        f.setBold(True)
        p.setFont(f)
        p.setPen(FG)
        p.drawText(QRectF(0, 0, 64, 64), Qt.AlignCenter, "A")
    elif name == "pencil":
        p.save()
        p.translate(32, 32)
        p.rotate(45)
        p.setBrush(QColor(255, 170, 60))
        p.drawRect(QRectF(-7, -26, 14, 38))
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(-7, 12), P(7, 12), P(0, 26)]))
        p.restore()
    elif name == "cross":
        p.setPen(_pen(QColor(255, 90, 90), 4))
        p.drawLine(P(32, 6), P(32, 24))
        p.drawLine(P(32, 40), P(32, 58))
        p.drawLine(P(6, 32), P(24, 32))
        p.drawLine(P(40, 32), P(58, 32))
        p.drawEllipse(QRectF(22, 22, 20, 20))
    elif name == "layout":
        p.setBrush(FG)
        p.setPen(Qt.NoPen)
        for x in (8, 26, 44):
            for y in (8, 26, 44):
                p.drawRect(QRectF(x, y, 13, 13))
    elif name == "quad":            # imagem em 4 quadrantes, um destacado
        p.drawRect(QRectF(8, 8, 48, 48))
        p.drawLine(P(32, 8), P(32, 56))
        p.drawLine(P(8, 32), P(56, 32))
        p.fillRect(QRectF(34, 10, 20, 20), ACCENT)
    elif name == "loupe":           # lupa
        p.setPen(_pen(FG, 5))
        p.drawEllipse(QRectF(8, 8, 34, 34))
        p.drawLine(P(38, 38), P(56, 56))
        p.setPen(_pen(GOLD, 3))
        p.drawEllipse(QRectF(16, 16, 18, 18))
    elif name == "import":          # seta para dentro de uma bandeja
        p.drawLine(P(32, 6), P(32, 38))
        p.drawPolyline(QPolygonF([P(20, 27), P(32, 39), P(44, 27)]))
        p.drawPolyline(QPolygonF([P(10, 36), P(10, 54), P(54, 54), P(54, 36)]))
    elif name == "pacs":            # servidor (pilha de discos) + rede
        for y in (8, 24, 40):
            p.drawRoundedRect(QRectF(12, y, 40, 13), 3, 3)
            p.setBrush(GREEN)
            p.drawEllipse(QRectF(43, y + 5, 4, 4))
            p.setBrush(Qt.NoBrush)
    elif name == "open":            # pasta aberta
        p.drawPolyline(QPolygonF([P(8, 50), P(8, 14), P(24, 14), P(29, 20), P(52, 20), P(52, 28)]))
        p.drawPolygon(QPolygonF([P(8, 50), P(16, 28), P(58, 28), P(50, 50)]))
    elif name == "send":            # avião de papel
        p.drawPolygon(QPolygonF([P(6, 30), P(58, 8), P(44, 56), P(32, 38)]))
        p.drawLine(P(32, 38), P(58, 8))
    elif name == "export":          # disco (CD) com seta
        p.drawEllipse(QRectF(6, 14, 40, 40))
        p.drawEllipse(QRectF(22, 30, 8, 8))
        p.setPen(_pen(ACCENT, 4))
        p.drawLine(P(40, 22), P(58, 4))
        p.drawPolyline(QPolygonF([P(46, 4), P(58, 4), P(58, 16)]))
    elif name == "print":
        p.drawRect(QRectF(18, 6, 28, 16))
        p.drawRoundedRect(QRectF(6, 22, 52, 22), 4, 4)
        p.drawRect(QRectF(18, 36, 28, 22))
        p.setPen(_pen(FG, 2))
        p.drawLine(P(23, 44), P(41, 44))
        p.drawLine(P(23, 50), P(41, 50))
    elif name == "prints":          # folhas de filme empilhadas, com o "papel" da frente marcado
        p.drawRect(QRectF(14, 6, 36, 44))
        p.drawRect(QRectF(8, 14, 36, 44))
        p.setPen(_pen(ACCENT, 3))
        p.drawLine(P(14, 26), P(38, 26))
        p.drawLine(P(14, 36), P(38, 36))
        p.drawLine(P(14, 46), P(28, 46))
    elif name == "list":
        for i, y in enumerate((14, 30, 46)):
            p.setBrush(ACCENT if i == 0 else FG)
            p.drawEllipse(QRectF(8, y - 4, 8, 8))
            p.setBrush(Qt.NoBrush)
            p.drawLine(P(24, y), P(56, y))
    elif name == "meeting":         # tela de projeção com "play"
        p.drawRect(QRectF(6, 8, 52, 34))
        p.drawLine(P(32, 42), P(32, 52))
        p.drawLine(P(20, 56), P(44, 56))
        p.setBrush(GREEN)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([P(26, 16), P(42, 25), P(26, 34)]))
    elif name == "gear":
        p.drawEllipse(QRectF(22, 22, 20, 20))
        for k in range(8):
            a = k * math.pi / 4
            p.drawLine(P(32 + 16 * math.cos(a), 32 + 16 * math.sin(a)), P(32 + 25 * math.cos(a), 32 + 25 * math.sin(a)))
        p.drawEllipse(QRectF(12, 12, 40, 40))
    elif name == "users":
        p.drawEllipse(QRectF(10, 12, 16, 16))
        p.drawArc(QRectF(4, 32, 28, 28), 0, 180 * 16)
        p.setPen(_pen(ACCENT))
        p.drawEllipse(QRectF(36, 8, 18, 18))
        p.drawArc(QRectF(28, 30, 34, 30), 0, 180 * 16)
    elif name == "help":
        p.drawEllipse(QRectF(8, 8, 48, 48))
        f = QFont()
        f.setPixelSize(34)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(8, 8, 48, 48), Qt.AlignCenter, "?")
    elif name == "refresh":
        p.drawArc(QRectF(12, 12, 40, 40), 40 * 16, 280 * 16)
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(50, 6), P(52, 22), P(38, 18)]))
    elif name == "rotate":
        p.setPen(_pen(FG, 5))
        p.drawArc(QRectF(12, 12, 40, 40), 100 * 16, 260 * 16)
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(28, 4), P(40, 12), P(28, 21)]))
        p.setBrush(Qt.NoBrush)
        p.setPen(_pen(ACCENT, 3))
        p.drawLine(P(32, 24), P(32, 40))
        p.drawLine(P(24, 32), P(40, 32))
    elif name == "invert":
        p.drawRect(QRectF(10, 10, 44, 44))
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(10, 10), P(54, 10), P(10, 54)]))
    elif name == "fusion":
        p.setBrush(QColor(120, 120, 120, 200))
        p.drawEllipse(QRectF(6, 14, 34, 34))
        p.setBrush(QColor(255, 120, 0, 190))
        p.drawEllipse(QRectF(24, 14, 34, 34))
    elif name == "app":
        # marca do programa (0.99.11): a flor do ipê-amarelo sobre o quadrado escuro. Cinco pétalas
        # largas e um miolo cor de ferrugem com riscos finos, como na flor de verdade; legível a 16 px.
        _flor_de_ipe(p)
    elif name == "cube":
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF([P(12, 22), P(32, 12), P(52, 22), P(52, 46), P(32, 56), P(12, 46)]))
        p.drawLine(P(12, 22), P(32, 32))
        p.drawLine(P(52, 22), P(32, 32))
        p.drawLine(P(32, 32), P(32, 56))
    elif name == "palette":
        cols = [(0, 0, 0), (120, 0, 170), (230, 0, 60), (255, 160, 0), (255, 245, 200)]
        for i, c in enumerate(cols):
            p.fillRect(QRectF(8 + i * 9.6, 14, 9.8, 36), QColor(*c))
        p.drawRect(QRectF(8, 14, 48, 36))
        for (x, y, dx, dy) in ((8, 8, 1, 1), (56, 8, -1, 1), (8, 56, 1, -1), (56, 56, -1, -1)):
            p.drawLine(P(x, y), P(x + dx * 14, y))
            p.drawLine(P(x, y), P(x, y + dy * 14))
        p.drawRect(QRectF(22, 22, 20, 20))
    elif name == "reset":
        p.setPen(_pen(FG, 5))
        p.drawArc(QRectF(12, 12, 40, 40), 60 * 16, 290 * 16)
        p.setBrush(FG)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([P(40, 4), P(48, 20), P(32, 20)]))
    elif name == "cine":
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(18, 10), P(54, 32), P(18, 54)]))
    elif name == "mpr":
        p.setPen(_pen(FG, 4))
        p.drawLine(P(32, 36), P(32, 6))
        p.drawLine(P(32, 36), P(8, 54))
        p.drawLine(P(32, 36), P(56, 54))
        f = QFont()
        f.setPixelSize(14)
        f.setBold(True)
        p.setFont(f)
        p.setPen(ACCENT)
        p.drawText(P(38, 16), "Y")
        p.drawText(P(4, 44), "Z")
        p.drawText(P(50, 44), "X")
    elif name == "sync":
        p.setPen(_pen(ACCENT, 5))
        p.save()
        p.translate(32, 32)
        p.rotate(-45)
        p.drawRoundedRect(QRectF(-26, -9, 30, 18), 9, 9)
        p.drawRoundedRect(QRectF(-4, -9, 30, 18), 9, 9)
        p.restore()
    elif name == "key":
        p.setBrush(GOLD)
        p.setPen(_pen(GOLD, 2))
        pts = []
        for i in range(10):
            r = 26 if i % 2 == 0 else 11
            a = math.radians(-90 + i * 36)
            pts.append(P(32 + r * math.cos(a), 34 + r * math.sin(a)))
        p.drawPolygon(QPolygonF(pts))
    elif name == "priors":
        p.drawEllipse(QRectF(10, 10, 44, 44))
        p.drawLine(P(32, 18), P(32, 32))
        p.drawLine(P(32, 32), P(44, 40))
        p.setPen(_pen(ACCENT, 4))
        p.drawArc(QRectF(2, 2, 60, 60), 120 * 16, 70 * 16)
    elif name == "monitor":
        p.drawRoundedRect(QRectF(6, 10, 52, 34), 3, 3)
        p.drawLine(P(32, 44), P(32, 54))
        p.drawLine(P(20, 56), P(44, 56))
        p.setPen(_pen(ACCENT, 3))
        p.drawLine(P(24, 27), P(40, 27))
        p.drawLine(P(34, 21), P(40, 27))
        p.drawLine(P(34, 33), P(40, 27))
    elif name == "film":
        # folha com grade 2x2 (filme)
        p.drawRoundedRect(QRectF(12, 6, 40, 52), 3, 3)
        p.setBrush(QColor(120, 120, 120))
        p.setPen(_pen(FG, 2))
        for x in (17, 34):
            for y in (13, 34):
                p.drawRect(QRectF(x, y, 13, 17))
        p.setBrush(Qt.NoBrush)
        p.setPen(_pen(ACCENT, 4))
        p.drawLine(P(46, 46), P(58, 46))
        p.drawLine(P(52, 40), P(52, 52))
    elif name == "anon":
        path = QPainterPath()
        path.moveTo(4, 32)
        path.quadTo(32, 4, 60, 32)
        path.quadTo(32, 60, 4, 32)
        p.drawPath(path)
        p.drawEllipse(P(32, 32), 8, 8)
        p.setPen(_pen(QColor(255, 110, 110), 5))
        p.drawLine(P(10, 54), P(54, 10))
    elif name == "apps":
        # aplicações (0.99.12): quatro quadrados, o de baixo à direita aceso
        p.setBrush(Qt.NoBrush)
        for i, (x, y) in enumerate(((10, 10), (36, 10), (10, 36), (36, 36))):
            if i == 3:
                p.setPen(_pen(ACCENT, 4))
            p.drawRoundedRect(QRectF(x, y, 18, 18), 4, 4)
    elif name == "more":
        p.setBrush(FG)
        p.setPen(Qt.NoPen)
        for x in (12, 32, 52):
            p.drawEllipse(P(x, 32), 5.5, 5.5)
    elif name == "trash":
        p.drawLine(P(12, 16), P(52, 16))
        p.drawLine(P(26, 16), P(28, 8))
        p.drawLine(P(28, 8), P(36, 8))
        p.drawLine(P(36, 8), P(38, 16))
        p.drawPolygon(QPolygonF([P(16, 16), P(48, 16), P(44, 56), P(20, 56)]))
    elif name == "next":
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(14, 12), P(40, 32), P(14, 52)]))
        p.drawLine(P(50, 12), P(50, 52))
    elif name == "prev":
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(50, 12), P(24, 32), P(50, 52)]))
        p.drawLine(P(14, 12), P(14, 52))
    elif name == "lesion":          # alvo com régua
        p.drawEllipse(P(32, 32), 20, 20)
        p.drawEllipse(P(32, 32), 9, 9)
        p.drawLine(P(8, 56), P(56, 8))
    elif name == "report":          # folha com linhas
        p.drawPolygon(QPolygonF([P(14, 6), P(42, 6), P(52, 16), P(52, 58), P(14, 58)]))
        for y in (22, 32, 42):
            p.drawLine(P(21, y), P(45, y))
        p.drawLine(P(21, 50), P(36, 50))
    elif name == "ai":              # imagem com contorno destacado (CAD/IA)
        p.drawRect(QRectF(8, 8, 48, 48))
        p.setPen(_pen(QColor(255, 170, 60), 4))
        p.drawPolygon(QPolygonF([P(22, 22), P(40, 18), P(46, 34), P(34, 46), P(20, 40)]))
    elif name == "pick":            # seta do mouse sobre uma alça (selecionar medida)
        p.setBrush(FG)
        p.drawPolygon(QPolygonF([P(18, 10), P(18, 46), P(27, 37), P(34, 52), P(41, 49), P(34, 34), P(46, 32)]))
        p.setBrush(Qt.NoBrush)
        p.setPen(_pen(ACCENT, 4))
        p.drawRect(QRectF(8, 8, 48, 48))
    elif name == "segment":         # mancha preenchida (segmentação)
        p.setBrush(QColor(80, 200, 120, 150))
        p.drawPolygon(QPolygonF([P(14, 30), P(24, 12), P(44, 14), P(52, 32), P(42, 52), P(20, 50)]))
    elif name == "gestao":          # prancheta com ✔ (conferência dos exames no PACS)
        p.drawRoundedRect(QRectF(12, 10, 40, 48), 4, 4)
        p.drawRect(QRectF(24, 6, 16, 8))
        p.setPen(_pen(GREEN, 4))
        p.drawPolyline(QPolygonF([P(20, 34), P(29, 43), P(45, 24)]))
    elif name in _APPS_IA:          # aplicações da barra (0.99.78): um desenho por aplicação
        _draw_app(name, p)
    else:  # desconhecido: quadrado
        p.drawRect(QRectF(12, 12, 40, 40))


#: aplicações com pictograma próprio; as marcadas com True levam o selo ✦ de IA
_APPS_IA = {"app_nodulos": True, "app_enfisema": True, "app_composicao": True, "app_figado": True,
            "app_orgaos": True, "app_genant": True, "app_linfonodos": True, "app_cefalometria": True,
            "app_indices": True, "app_difusao": False, "app_figado_lesoes": True,
            "app_autopet": True, "app_brats": True}


def _pulmoes(p: QPainter) -> None:
    """Dois pulmões e a traqueia, no traço comum."""
    p.setPen(_pen(FG, 3.5))
    p.drawLine(P(32, 6), P(32, 22))
    p.drawLine(P(32, 22), P(26, 28))
    p.drawLine(P(32, 22), P(38, 28))
    esq = QPainterPath()
    esq.moveTo(27, 16)
    esq.cubicTo(14, 14, 6, 34, 8, 52)
    esq.cubicTo(14, 56, 22, 54, 28, 50)
    esq.closeSubpath()
    dir_ = QPainterPath()
    dir_.moveTo(37, 16)
    dir_.cubicTo(50, 14, 58, 34, 56, 52)
    dir_.cubicTo(50, 56, 42, 54, 36, 50)
    dir_.closeSubpath()
    p.drawPath(esq)
    p.drawPath(dir_)


def _vertebra(p: QPainter, y: float, cunha: bool = False) -> None:
    if cunha:              # anterior (esquerda) mais baixa que a posterior: fratura em cunha
        p.drawPolygon(QPolygonF([P(14, y + 5), P(40, y), P(40, y + 13), P(14, y + 10)]))
    else:
        p.drawRoundedRect(QRectF(14, y, 26, 12), 3, 3)


def _brilho(p: QPainter) -> None:
    """Selo ✦ dourado no canto superior direito: a aplicação usa IA."""
    cx, cy, r = 54.0, 10.0, 9.0
    path = QPainterPath()
    path.moveTo(cx, cy - r)
    for ang in range(4):
        a = math.radians(90 * ang)
        b = math.radians(90 * ang + 90)
        path.quadTo(cx, cy, cx + r * math.sin(b), cy - r * math.cos(b))
        _ = a
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(GOLD)
    p.drawPath(path)


def _draw_app(name: str, p: QPainter) -> None:  # noqa: C901 - um caso por aplicação
    if name == "app_nodulos":           # pulmões com um ponto azul
        _pulmoes(p)
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT)
        p.drawEllipse(QRectF(42, 34, 9, 9))
    elif name == "app_enfisema":        # pulmões com bolhas vazias no lobo superior
        _pulmoes(p)
        p.setPen(_pen(ACCENT, 2.5))
        for x, y, r in ((14, 26, 5), (20, 33, 4), (44, 26, 5), (49, 34, 4)):
            p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
    elif name == "app_composicao":      # corte axial do abdome: gordura, músculo e a vértebra L3
        p.setPen(_pen(FG, 3.5))
        p.drawEllipse(QRectF(6, 12, 52, 40))
        p.setPen(_pen(ACCENT, 5))
        p.drawArc(QRectF(13, 18, 38, 28), 200 * 16, 140 * 16)
        p.setPen(_pen(FG, 3))
        p.setBrush(QColor(232, 232, 232, 90))
        p.drawEllipse(QRectF(26, 36, 12, 10))
    elif name == "app_figado":          # contorno do fígado com uma gota (gordura / ferro)
        p.setPen(_pen(FG, 3.5))
        path = QPainterPath()
        path.moveTo(6, 26)
        path.cubicTo(10, 12, 40, 8, 56, 18)
        path.cubicTo(52, 30, 36, 50, 18, 52)
        path.cubicTo(8, 46, 4, 36, 6, 26)
        p.drawPath(path)
        gota = QPainterPath()
        gota.moveTo(30, 22)
        gota.cubicTo(24, 32, 24, 40, 30, 40)
        gota.cubicTo(36, 40, 36, 32, 30, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT)
        p.drawPath(gota)
    elif name == "app_figado_lesoes":   # fígado com as linhas dos segmentos e duas lesões
        p.setPen(_pen(FG, 3.5))
        path = QPainterPath()
        path.moveTo(6, 26)
        path.cubicTo(10, 12, 40, 8, 56, 18)
        path.cubicTo(52, 30, 36, 50, 18, 52)
        path.cubicTo(8, 46, 4, 36, 6, 26)
        p.drawPath(path)
        p.setPen(_pen(FG, 1.8))
        p.drawLine(P(30, 13), P(26, 50))
        p.drawLine(P(8, 32), P(50, 26))
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT)
        p.drawEllipse(QRectF(14, 20, 9, 9))
        p.drawEllipse(QRectF(36, 31, 6, 6))
    elif name == "app_autopet":         # silhueta do corpo com focos quentes (PET)
        p.setPen(_pen(FG, 3.5))
        p.drawEllipse(QRectF(24, 4, 16, 14))
        corpo = QPainterPath()
        corpo.moveTo(18, 20)
        corpo.lineTo(46, 20)
        corpo.lineTo(44, 44)
        corpo.lineTo(40, 60)
        corpo.lineTo(24, 60)
        corpo.lineTo(20, 44)
        corpo.closeSubpath()
        p.drawPath(corpo)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 120, 40))
        p.drawEllipse(QRectF(26, 26, 8, 8))
        p.drawEllipse(QRectF(35, 38, 6, 6))
        p.setBrush(ACCENT)
        p.drawEllipse(QRectF(29, 48, 5, 5))
    elif name == "app_brats":           # encéfalo com o tumor em camadas (edema, captante, necrose)
        p.setPen(_pen(FG, 3.5))
        p.drawEllipse(QRectF(6, 8, 52, 46))
        p.drawLine(P(32, 10), P(32, 52))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(80, 200, 120))
        p.drawEllipse(QRectF(34, 18, 20, 20))
        p.setBrush(QColor(255, 70, 70))
        p.drawEllipse(QRectF(38, 22, 12, 12))
        p.setBrush(QColor(250, 220, 60))
        p.drawEllipse(QRectF(42, 26, 5, 5))
    elif name == "app_orgaos":          # fígado, rim e baço
        p.setPen(_pen(FG, 3.5))
        fig = QPainterPath()
        fig.moveTo(4, 20)
        fig.cubicTo(8, 8, 28, 8, 34, 14)
        fig.cubicTo(30, 26, 18, 34, 8, 34)
        fig.closeSubpath()
        p.drawPath(fig)
        p.drawEllipse(QRectF(40, 10, 16, 22))
        p.setPen(_pen(ACCENT, 3.5))
        rim = QPainterPath()
        rim.moveTo(24, 38)
        rim.cubicTo(14, 38, 14, 58, 24, 58)
        rim.cubicTo(30, 58, 28, 50, 26, 48)
        rim.cubicTo(28, 46, 30, 38, 24, 38)
        p.drawPath(rim)
    elif name == "app_genant":          # três vértebras, a do meio em cunha, com a seta da altura
        p.setPen(_pen(FG, 3.5))
        _vertebra(p, 6)
        p.setPen(_pen(ACCENT, 3.5))
        _vertebra(p, 25, cunha=True)
        p.setPen(_pen(FG, 3.5))
        _vertebra(p, 44)
        p.setPen(_pen(ACCENT, 2.5))
        p.drawLine(P(50, 25), P(50, 38))
        p.drawLine(P(47, 28), P(50, 25))
        p.drawLine(P(53, 28), P(50, 25))
        p.drawLine(P(47, 35), P(50, 38))
        p.drawLine(P(53, 35), P(50, 38))
    elif name == "app_linfonodos":      # perfil do pescoço com as faixas dos níveis
        p.setPen(_pen(FG, 3.5))
        path = QPainterPath()
        path.moveTo(20, 4)
        path.cubicTo(8, 8, 8, 24, 16, 30)
        path.lineTo(18, 60)
        p.drawPath(path)
        p.drawLine(P(44, 22), P(44, 60))
        p.setPen(_pen(ACCENT, 3))
        for y in (32, 42, 52):
            p.drawLine(P(20, y), P(42, y - 2))
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT)
        p.drawEllipse(QRectF(27, 34, 7, 6))
    elif name == "app_cefalometria":    # perfil do crânio com a linha de medida
        p.setPen(_pen(FG, 3.5))
        path = QPainterPath()
        path.moveTo(50, 50)
        path.cubicTo(58, 30, 50, 6, 30, 6)
        path.cubicTo(14, 6, 8, 18, 10, 28)
        path.lineTo(6, 34)
        path.lineTo(11, 37)
        path.cubicTo(10, 46, 14, 52, 22, 54)
        p.drawPath(path)
        p.setPen(_pen(ACCENT, 3))
        p.drawLine(P(14, 30), P(46, 18))
        p.setBrush(ACCENT)
        p.drawEllipse(QRectF(12, 28, 5, 5))
        p.drawEllipse(QRectF(44, 16, 5, 5))
    elif name == "app_indices":         # corte do encéfalo com uma régua
        p.setPen(_pen(FG, 3.5))
        p.drawEllipse(QRectF(8, 8, 48, 44))
        p.drawLine(P(32, 10), P(32, 50))
        p.setPen(_pen(FG, 2.5))
        p.drawArc(QRectF(20, 22, 10, 12), 30 * 16, 300 * 16)
        p.drawArc(QRectF(34, 22, 10, 12), 210 * 16, 300 * 16)
        p.setPen(_pen(ACCENT, 3.5))
        p.drawLine(P(8, 58), P(56, 58))
        for x in (8, 20, 32, 44, 56):
            p.drawLine(P(x, 58), P(x, 53))
    elif name == "app_difusao":         # três setas saindo de um ponto
        p.setPen(_pen(ACCENT, 4))
        cx, cy = 22.0, 40.0
        for ang in (-60, -20, 20):
            a = math.radians(ang)
            x2, y2 = cx + 32 * math.cos(a), cy + 32 * math.sin(a)
            p.drawLine(P(cx, cy), P(x2, y2))
            for d in (150, -150):
                b = a + math.radians(d)
                p.drawLine(P(x2, y2), P(x2 + 8 * math.cos(b), y2 + 8 * math.sin(b)))
        p.setPen(Qt.NoPen)
        p.setBrush(FG)
        p.drawEllipse(QRectF(cx - 5, cy - 5, 10, 10))
    if _APPS_IA.get(name):
        _brilho(p)


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    _draw(name, p)
    p.end()
    ic = QIcon(pm)
    # versão apagada (desabilitado) automática do Qt é suficiente
    return ic


def with_badge(pm: QPixmap, text: str, color: QColor = GREEN) -> QPixmap:
    """Miniatura com um selo no canto (ex.: número de imagens com medida)."""
    out = QPixmap(pm)
    if out.isNull():
        out = QPixmap(80, 80)
        out.fill(QColor(30, 30, 30))
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    f = QFont()
    f.setPixelSize(max(11, out.height() // 6))
    f.setBold(True)
    p.setFont(f)
    w = p.fontMetrics().horizontalAdvance(text) + 10
    h = p.fontMetrics().height() + 2
    r = QRectF(out.width() - w - 2, out.height() - h - 2, w, h)
    p.setBrush(QBrush(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setPen(QColor(0, 0, 0))
    p.drawText(r, Qt.AlignCenter, text)
    p.end()
    return out


def with_corner_letter(pm: QPixmap, text: str, color: QColor = QColor(255, 150, 40)) -> QPixmap:
    """Ícone da barra com uma letra grande no canto inferior direito (D = botão direito, M = meio)."""
    out = QPixmap(pm)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    f = QFont()
    f.setPixelSize(int(out.height() * 0.42))
    f.setBold(True)
    p.setFont(f)
    w = p.fontMetrics().horizontalAdvance(text) + out.width() * 0.12
    h = out.height() * 0.46
    r = QRectF(out.width() - w, out.height() - h, w, h)
    p.setBrush(QBrush(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(r, h * 0.25, h * 0.25)
    p.setPen(QColor(0, 0, 0))
    p.drawText(r, Qt.AlignCenter, text)
    p.end()
    return out


def _flor_de_ipe(p: QPainter) -> None:
    """O ícone do Ipê, desenhado em 64 × 64."""
    from PySide6.QtGui import QTransform
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(22, 30, 40))
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 13, 13)
    cx, cy, comp, larg = 32.0, 33.0, 24.0, 10.2
    amarelo, borda = QColor(246, 196, 0), QColor(214, 150, 0)
    p.setPen(QPen(borda, 1.4))
    p.setBrush(amarelo)
    for i in range(5):
        path = QPainterPath(P(0, 0))
        path.cubicTo(P(-larg, -comp * 0.35), P(-larg * 1.05, -comp * 0.95), P(-larg * 0.35, -comp * 1.02))
        path.quadTo(P(0, -comp * 0.9), P(larg * 0.35, -comp * 1.02))       # a borda ondulada da pétala
        path.cubicTo(P(larg * 1.05, -comp * 0.95), P(larg, -comp * 0.35), P(0, 0))
        tr = QTransform()
        tr.translate(cx, cy)
        tr.rotate(i * 72)
        p.drawPath(tr.map(path))
    # riscos avermelhados que saem do miolo (a "garganta" da flor)
    p.setPen(_pen(QColor(190, 90, 20), 1.3))
    for i in range(5):
        a = math.radians(i * 72 - 90)
        p.drawLine(P(cx + 4 * math.cos(a), cy + 4 * math.sin(a)), P(cx + 9 * math.cos(a), cy + 9 * math.sin(a)))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(150, 70, 10))
    p.drawEllipse(P(cx, cy), 4.8, 4.8)
