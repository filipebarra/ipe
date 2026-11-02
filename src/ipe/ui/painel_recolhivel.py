"""Painel lateral que recolhe para uma tira na borda, como os painéis do Weasis (0.99.29).

Pedido dele (com as telas do Weasis): poder esconder o banco (Locais e listas) e as séries da tela de
banco de dados "da mesma forma ou de forma semelhante que o Weasis" — lá, o botão ▁ no título do
painel recolhe o "DICOM Explorer" para uma aba vertical na borda; um clique na aba traz de volta.

Aqui: o título do painel tem o botão ⯇/⯈ (recolher); recolhido, sobra uma tira estreita com o nome
escrito de lado e o botão de abrir. O estado de cada painel fica guardado (preferência do usuário).
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

LARGURA_TIRA = 26


class _TiraVertical(QWidget):
    """A aba na borda: o nome do painel escrito de cima para baixo; clique abre."""

    clicked = Signal()

    def __init__(self, texto: str, parent=None):
        super().__init__(parent)
        self.texto = texto
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Abrir o painel “{texto}”")
        self.setFixedWidth(LARGURA_TIRA)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(LARGURA_TIRA, self.fontMetrics().horizontalAdvance(self.texto) + 24)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        pal = self.palette()
        p.setPen(pal.color(pal.ColorRole.Mid))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 4, 4)
        p.setPen(pal.color(pal.ColorRole.WindowText))
        p.translate(self.width() / 2 + self.fontMetrics().ascent() / 2 - 2, 10)
        p.rotate(90)
        p.drawText(0, 0, self.texto)
        p.end()


class PainelRecolhivel(QWidget):
    """Envolve `conteudo`. `lado` = "esq" ou "dir" (para que lado a seta aponta)."""

    mudou = Signal(bool)                 # True = recolhido

    def __init__(self, titulo: str, conteudo: QWidget, lado: str = "esq", settings=None, chave: str = "",
                 parent=None):
        super().__init__(parent)
        self.titulo, self.conteudo, self.lado = titulo, conteudo, lado
        self.settings, self.chave = settings, chave
        self._max_aberto = conteudo.maximumWidth()
        self.recolhido = False

        self.b_recolher = QToolButton()
        self.b_recolher.setAutoRaise(True)
        self.b_recolher.setText("⯇" if lado == "esq" else "⯈")
        self.b_recolher.setToolTip(f"Recolher o painel “{titulo}” para a borda")
        self.b_recolher.clicked.connect(lambda: self.recolher(True))
        cab = QHBoxLayout()
        cab.setContentsMargins(4, 0, 0, 0)
        rotulo = QLabel(f"<b>{titulo}</b>")
        if lado == "esq":
            cab.addWidget(rotulo)
            cab.addStretch(1)
            cab.addWidget(self.b_recolher)
        else:
            cab.addWidget(self.b_recolher)
            cab.addWidget(rotulo)
            cab.addStretch(1)
        self.cabecalho = QWidget()
        self.cabecalho.setLayout(cab)

        self.aberto = QWidget()
        lay = QVBoxLayout(self.aberto)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.cabecalho)
        lay.addWidget(conteudo, 1)

        self.tira = _TiraVertical(titulo)
        self.tira.clicked.connect(lambda: self.recolher(False))
        self.b_abrir = QToolButton()
        self.b_abrir.setAutoRaise(True)
        self.b_abrir.setText("⯈" if lado == "esq" else "⯇")
        self.b_abrir.setToolTip(f"Abrir o painel “{titulo}”")
        self.b_abrir.clicked.connect(lambda: self.recolher(False))
        self.fechado = QWidget()
        lf = QVBoxLayout(self.fechado)
        lf.setContentsMargins(0, 0, 0, 0)
        lf.setSpacing(2)
        lf.addWidget(self.b_abrir, 0, Qt.AlignHCenter)
        lf.addWidget(self.tira, 0, Qt.AlignHCenter)
        lf.addStretch(1)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(self.aberto)
        raiz.addWidget(self.fechado)
        self.fechado.setVisible(False)
        if settings is not None and chave:
            try:
                self.recolher(bool(settings.get(chave, False)), salvar=False)
            except Exception:  # noqa: BLE001
                pass

    def recolher(self, on: bool, salvar: bool = True) -> None:
        on = bool(on)
        self.recolhido = on
        self.aberto.setVisible(not on)
        self.fechado.setVisible(on)
        if on:
            self.setMaximumWidth(LARGURA_TIRA + 4)
            self.setMinimumWidth(LARGURA_TIRA + 4)
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(self._max_aberto if self._max_aberto < 16777215 else 16777215)
        if salvar and self.settings is not None and self.chave:
            try:
                self.settings.set(self.chave, on)
                self.settings.save()
            except Exception:  # noqa: BLE001
                pass
        self.mudou.emit(on)

    def alternar(self) -> None:
        self.recolher(not self.recolhido)

    def set_max_aberto(self, largura: int) -> None:
        self._max_aberto = largura
        self.conteudo.setMaximumWidth(16777215)
        if not self.recolhido:
            self.setMaximumWidth(largura)
