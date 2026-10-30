"""Toda janela abre no centro da tela, com 80% dela (0.99.7; na 0.99.6 era maximizada).

0.99.7: *"as janelas maximizadas não funcionaram. é possível abri-las no centro da tela, +- 80% da
resolução? calcula a resolução da tela e faz esse ajuste, pc a pc"*. O tamanho sai da área útil do
monitor em que a janela abre (sem a barra de tarefas), em cada computador, na hora de abrir. A janela
do banco de dados continua com a opção própria (Preferências ▸ Geral ▸ "Abrir maximizado").

(0.99.6)

Pedido dele: *"Faça com que toda janela que abrir abra maximizada"*. Um filtro de eventos na aplicação
olha cada janela de primeiro nível na primeira vez que aparece e a maximiza na tela em que ela abriu.

Ficam como estão (maximizar seria pior que não maximizar):
- caixas de pergunta, aviso, progresso, escolha de arquivo/cor/fonte e de texto (QMessageBox…);
- menus, dicas, janelas de ferramenta e splash;
- janelas de tamanho fixo e as que abriram em tela cheia;
- diálogos pequenos (formulários de poucos campos, menores que 640 × 420 no tamanho pedido).
Preferências ▸ Geral ▸ "Abrir todas as janelas maximizadas" desliga.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QFileDialog, QFontDialog, QInputDialog, QMenu, QMessageBox, QProgressDialog, QWidget,
)

log = logging.getLogger(__name__)

CHAVE = "ui.janelas_maximizadas"
DIALOGO_MIN = (640, 420)            # diálogo menor que isso é formulário: fica do tamanho dele
_NUNCA = (QMessageBox, QProgressDialog, QInputDialog, QFileDialog, QColorDialog, QFontDialog, QMenu)
_MARCA = "_dv_maximizada"


def deve_maximizar(w: QWidget) -> bool:
    if not isinstance(w, QWidget) or not w.isWindow() or isinstance(w, _NUNCA):
        return False
    tipo = w.windowType()
    if tipo in (Qt.Popup, Qt.ToolTip, Qt.SplashScreen, Qt.Tool, Qt.Desktop, Qt.SubWindow):
        return False
    if w.isFullScreen() or w.isMaximized() or w.isMinimized():
        return False
    if w.minimumSize() == w.maximumSize() and w.minimumWidth() > 0:
        return False                                   # tamanho fixo
    if callable(getattr(w, "abre_maximizada", None)):
        return False                                   # a janela do banco tem opção própria
    if isinstance(w, QDialog):
        tam = w.size().expandedTo(w.sizeHint())
        if tam.width() < DIALOGO_MIN[0] or tam.height() < DIALOGO_MIN[1]:
            return False
    return True


FRACAO = 0.80


def tela_de(w: QWidget):
    """O monitor onde a janela vai aparecer: o da janela-mãe; senão o do mouse; senão o principal."""
    from PySide6.QtGui import QCursor, QGuiApplication
    mae = w.parentWidget().window() if w.parentWidget() is not None else None
    if mae is not None and mae.isVisible() and mae.screen() is not None:
        return mae.screen()
    return QGuiApplication.screenAt(QCursor.pos()) or w.screen() or QGuiApplication.primaryScreen()


def centralizar(w: QWidget, fracao: float = FRACAO) -> None:
    """80% da área útil do monitor, no centro dele (respeita o tamanho mínimo e máximo da janela)."""
    tela = tela_de(w)
    if tela is None:
        return
    area = tela.availableGeometry()
    w.resize(int(area.width() * fracao), int(area.height() * fracao))
    moldura = w.frameGeometry()
    moldura.moveCenter(area.center())
    w.move(moldura.topLeft())


class MaximizarJanelas(QObject):
    """O filtro: na primeira vez que cada janela aparece, centraliza com 80% da tela."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    def eventFilter(self, obj, ev):  # noqa: N802
        if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow() \
                and not obj.property(_MARCA):
            obj.setProperty(_MARCA, True)              # só na primeira vez: depois vale o que ele fez
            try:
                if bool(self.settings.get(CHAVE, True)) and deve_maximizar(obj):
                    centralizar(obj)
                    # quem restaura a posição salva logo depois de mostrar não desfaz o ajuste
                    QTimer.singleShot(0, lambda w=obj: _centralizar_de_novo(w))
            except Exception:  # noqa: BLE001
                log.debug("ajustar a janela", exc_info=True)
        return False


def _centralizar_de_novo(w: QWidget) -> None:
    try:
        if w.isVisible() and not w.isFullScreen() and not w.isMaximized():
            centralizar(w)
    except RuntimeError:
        pass                                           # a janela já foi fechada


def instalar(app, settings) -> MaximizarJanelas:
    f = MaximizarJanelas(settings, app)
    app.installEventFilter(f)
    return f
