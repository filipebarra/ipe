"""Monitores: papel de cada tela e janelas de estudo por monitor.

Cada monitor pode ter um papel, salvo em settings.json -> "monitors":
- "browser":  janela principal (banco de dados);
- "viewer":   estudos abertos vão para esta tela;
- "compare":  exames anteriores abrem aqui, ligados ao exame atual;
- "off":      não usar.
O monitor é reconhecido pelo nome, modelo e número de série; se um monitor
configurado não estiver conectado, os estudos ficam na janela principal.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QGuiApplication, QScreen
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget

from ipe import APP_NAME

log = logging.getLogger(__name__)

ROLES = {"": "Automático", "browser": "Banco de dados (janela principal)", "viewer": "Viewer (estudos)",
         "compare": "Comparação (exames anteriores)", "off": "Não usar"}


def screen_key(screen: QScreen) -> str:
    parts = [screen.name(), screen.model(), screen.serialNumber()]
    return "|".join(p for p in parts if p) or screen.name()


def screen_label(screen: QScreen, i: int) -> str:
    g = screen.geometry()
    extra = f" {screen.model()}" if screen.model() else ""
    orient = "retrato" if g.height() > g.width() else "paisagem"
    return f"Monitor {i}: {screen.name()}{extra} — {g.width()}×{g.height()} ({orient})"


def monitor_config(settings, screen: QScreen) -> dict:
    return (settings.get("monitors", {}) or {}).get(screen_key(screen), {}) or {}


def telas_ordenadas(settings) -> list:
    """As telas na **ordem do usuário** (Preferências ▸ Monitores), não na do sistema.

    O sistema numera as telas como quer, e na mamografia o número importa: a etapa diz "com 2
    telas, mostrar no Monitor 2". Se o Monitor 2 do programa não for o monitor 2 da mesa, o
    arranjo sai espelhado. Quem não mexeu na ordem fica com a do sistema, como antes.
    """
    telas = list(QGuiApplication.screens())
    pos = {s: i for i, s in enumerate(telas)}

    def chave(s):
        try:
            n = int(monitor_config(settings, s).get("ordem"))
        except (TypeError, ValueError):
            n = pos[s] + 1
        return (n, pos[s])
    return sorted(telas, key=chave)


def numero_da_tela(settings, screen: QScreen) -> int:
    """1, 2, 3… como o usuário vê o monitor (e como a etapa de mamografia o chama)."""
    ordenadas = telas_ordenadas(settings)
    return ordenadas.index(screen) + 1 if screen in ordenadas else 1


def screens_with_role(settings, role: str, exclude: QScreen | None = None) -> list:
    """**Todas** as telas com esse papel, na ordem do sistema.

    Existe porque "o primeiro monitor viewer" não é a mesma coisa que "os monitores viewer": com
    dois configurados, pegar só o primeiro deixava o segundo sem nada — foi o que aconteceu.
    """
    return [s for s in telas_ordenadas(settings)
            if s is not exclude and monitor_config(settings, s).get("role") == role]


def screen_with_role(settings, role: str, exclude: QScreen | None = None) -> QScreen | None:
    telas = screens_with_role(settings, role, exclude)
    return telas[0] if telas else None


def tela_da_janela_principal(settings) -> QScreen | None:
    """Onde a janela do banco de dados deve ficar.

    Na ordem: a tela marcada como "banco de dados"; se não houver, a primeira **sem papel**; e só
    então qualquer uma que não esteja marcada como "Não usar". Sem isto a janela principal podia
    acabar justamente numa tela de viewer — ou numa que o usuário tinha desligado —, e aí o exame
    parecia abrir no monitor do banco.
    """
    telas = QGuiApplication.screens()
    por_papel = {s: monitor_config(settings, s).get("role", "") for s in telas}
    for alvo in ("browser",):
        for s in telas:
            if por_papel.get(s) == alvo:
                return s
    livres = [s for s in telas if not por_papel.get(s)]
    if livres:
        return livres[0]
    fora = [s for s in telas if por_papel.get(s) != "off"]
    return fora[0] if fora else (telas[0] if telas else None)


def layout_for_screen(settings, screen: QScreen | None) -> tuple[int, int] | None:
    if screen is None:
        return None
    lay = monitor_config(settings, screen).get("layout")
    return tuple(lay) if lay else None


def identify_screens(ms: int = 2500, settings=None) -> None:
    """Mostra um número grande em cada monitor, por alguns segundos.

    O número é o **do programa** (a ordem escolhida), que é o que a etapa de mamografia usa.
    """
    labels = []
    telas = telas_ordenadas(settings) if settings is not None else list(QGuiApplication.screens())
    for i, s in enumerate(telas, 1):
        lab = QLabel(str(i))
        lab.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        lab.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(120)
        f.setBold(True)
        lab.setFont(f)
        lab.setStyleSheet("background:#35506e;color:white;border-radius:20px")
        g = s.geometry()
        lab.setGeometry(g.x() + g.width() // 2 - 150, g.y() + g.height() // 2 - 150, 300, 300)
        lab.show()
        labels.append(lab)
    QTimer.singleShot(ms, lambda: [lab.close() for lab in labels])
    identify_screens._keep = labels          # mantém referência até fechar


class ScreenWindow(QMainWindow):
    """Janela de estudos num monitor. Tem abas próprias; fechar devolve os estudos
    à janela principal."""

    def __init__(self, main, screen: QScreen, restrito: bool = False):
        super().__init__()
        self.main = main
        # `restrito`: janela aberta por chamada externa no modo "só visualizador". Não há caminho
        # daqui para o banco de dados, para a busca no PACS nem para exportar — quem recebe a
        # chamada do RIS vê o exame que o RIS pediu, e só.
        self.restrito = restrito
        self.screen_key = screen_key(screen)
        self.setWindowTitle(f"{APP_NAME} — {screen.name()}")
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.setAcceptDrops(True)            # arrastar arquivos DICOM (ver file_drop.py)
        # A barra de menu inteira, a mesma da janela principal: no monitor do laudo o médico não
        # deveria ter que voltar para a outra tela só para mudar o layout ou exportar.
        try:
            main._build_menus(self, restrito=restrito)
        except Exception:  # noqa: BLE001 - menu é conveniência; a janela tem que abrir de todo jeito
            log.debug("não consegui montar o menu desta janela", exc_info=True)
        self._devolvendo = False
        if not restrito:
            back = QAction("Voltar estudos para a janela principal", self)
            back.triggered.connect(self.devolver_estudos)
            self.menuBar().addAction(back)
        self.statusBar().showMessage(f"{APP_NAME} — {screen.name()}", 4000)
        self.setGeometry(screen.availableGeometry())
        self.show()
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(screen)
        self.setGeometry(screen.availableGeometry())
        self.showMaximized()

    # compatibilidade: a janela de um único estudo
    @property
    def tab(self):
        return self.tabs.currentWidget()

    def viewer_tabs(self) -> list:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def add_tab(self, tab) -> None:
        if self.restrito and hasattr(tab, "restringir_saidas"):
            tab.restringir_saidas()
        idx = self.tabs.addTab(tab, tab.title()[:40])
        self.tabs.setTabToolTip(idx, tab.title())
        self.tabs.setCurrentIndex(idx)
        tab.show()
        self.raise_()

    def take_tab(self, tab):
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            self.tabs.removeTab(idx)
            tab.setParent(None)
        return tab

    def _close_tab(self, index: int) -> None:
        tab = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.main.discard_tab(tab)
        if self.tabs.count() == 0:
            self.close()

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        self.main.dragEnterEvent(e)

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        self.main.dragMoveEvent(e)

    def dropEvent(self, e) -> None:  # noqa: N802
        self.main.dropEvent(e)

    def devolver_estudos(self) -> None:
        """Traz as abas desta janela de volta para a janela principal e fecha a janela.

        É o gesto deliberado — pelo menu —, que o X deixou de ser: o X fecha o exame inteiro.
        """
        self._devolvendo = True
        self.main.reattach(self)
        self.close()

    def closeEvent(self, e) -> None:  # noqa: N802
        """O X desta janela fecha o exame em **todas** as telas e devolve o banco de dados.

        Antes ele devolvia as abas para a janela principal: o médico fechava um monitor e o exame
        reaparecia noutro lugar, com os outros monitores ainda abertos.
        """
        if getattr(self, "_devolvendo", False):
            super().closeEvent(e)
            return
        if self.restrito:
            # Fechou o exame: o programa continua na bandeja, recebendo. A próxima chamada do RIS
            # abre na hora, sem esperar o programa subir de novo — e o banco não aparece.
            for t in self.viewer_tabs():
                self.main.discard_tab(t)
            self.tabs.clear()
            if self in self.main.detached:
                self.main.detached.remove(self)
            self.main.avisar_bandeja_so_viewer()
            super().closeEvent(e)
            return
        if self.main.fechar_exames_e_voltar_ao_banco():
            e.accept()
            return
        self.main.reattach(self)
        super().closeEvent(e)
