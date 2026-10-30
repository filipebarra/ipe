"""Barra que quebra a linha (0.99.6).

Pedido dele: *"o filme, quando faz parte do layout, em um monitor de resolução pequena, está com os
botões escondidos"*. A QToolBar manda o que não cabe para um botão » quase invisível; aqui os grupos de
botões passam para a linha de baixo. Cada grupo (o que fica entre dois separadores) não se parte.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLayout, QSizePolicy, QWidget


class FluxoLayout(QLayout):
    """Layout em fluxo (o exemplo "Flow Layout" do Qt): esquerda para a direita, quebra quando não cabe."""

    def __init__(self, parent=None, espaco_h: int = 10, espaco_v: int = 4):
        super().__init__(parent)
        self._itens = []
        self._h, self._v = espaco_h, espaco_v
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._itens.append(item)

    def count(self):
        return len(self._itens)

    def itemAt(self, i):  # noqa: N802
        return self._itens[i] if 0 <= i < len(self._itens) else None

    def takeAt(self, i):  # noqa: N802
        return self._itens.pop(i) if 0 <= i < len(self._itens) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, largura):  # noqa: N802
        return self._arrumar(QRect(0, 0, largura, 0), so_medir=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._arrumar(rect, so_medir=False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        s = QSize()
        for it in self._itens:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _arrumar(self, rect: QRect, so_medir: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, altura_linha = area.x(), area.y(), 0
        linha: list = []

        def assentar():
            # alinha os itens da linha pelo meio da altura dela
            for it, px in linha:
                h = it.sizeHint().height()
                it.setGeometry(QRect(QPoint(px, y + (altura_linha - h) // 2), it.sizeHint()))

        for it in self._itens:
            if it.widget() is not None and not it.widget().isVisibleTo(it.widget().parentWidget()):
                continue
            tam = it.sizeHint()
            prox = x + tam.width()
            if prox > area.right() + 1 and linha:
                if not so_medir:
                    assentar()
                linha = []
                x = area.x()
                y += altura_linha + self._v
                altura_linha = 0
                prox = x + tam.width()
            linha.append((it, x))
            x = prox + self._h
            altura_linha = max(altura_linha, tam.height())
        if not so_medir and linha:
            assentar()
        return y + altura_linha - rect.y() + m.bottom()


class BarraQuebra(QWidget):
    """Substitui a QToolBar do filme: `addWidget` vai para o grupo atual; `addSeparator` fecha o grupo.
    Os grupos quebram para a linha de baixo quando o painel é estreito."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fluxo = FluxoLayout(self, espaco_h=14, espaco_v=4)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self._grupo: QHBoxLayout | None = None

    def _novo_grupo(self) -> QHBoxLayout:
        w = QWidget(self)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.fluxo.addWidget(w)
        self._grupo = lay
        return lay

    def addWidget(self, w: QWidget):  # noqa: N802
        (self._grupo or self._novo_grupo()).addWidget(w)
        return w

    def addSeparator(self):  # noqa: N802
        self._grupo = None

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, largura):  # noqa: N802
        return self.fluxo.heightForWidth(largura)

    def sizeHint(self):  # noqa: N802
        largura = max(self.width(), 200)
        return QSize(largura, self.heightForWidth(largura))

    def minimumSizeHint(self):  # noqa: N802
        return self.fluxo.minimumSize()
