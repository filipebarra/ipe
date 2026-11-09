"""0.100.1: o sinal da rede até o servidor central, na barra de status do cliente — barras como as do celular e
o ping dos jogos. Mede ao abrir o programa (ida e volta + vazão) e a cada exame aberto (só a ida e volta, para
não disputar a rede com o download; a vazão passa a ser a do próprio download). Clique para medir de novo."""
from __future__ import annotations

import threading

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ipe.core.i18n import tr


def barras(ping_ms: float | None, mbps: float | None, ok: bool = True) -> int:
    """0 (sem conexão) a 4. Vale o pior dos dois: uma rede rápida com ida e volta lenta trava a tela, e uma
    resposta rápida com pouca vazão demora a trazer o exame. Sem a vazão medida, vale só a ida e volta."""
    if not ok or ping_ms is None:
        return 0
    p = 4 if ping_ms < 10 else 3 if ping_ms < 30 else 2 if ping_ms < 80 else 1
    if mbps is None:
        return p
    v = 4 if mbps >= 300 else 3 if mbps >= 80 else 2 if mbps >= 20 else 1
    return min(p, v)


def texto(ping_ms: float | None, mbps: float | None, ok: bool = True) -> str:
    if not ok or ping_ms is None:
        return tr("sem conexão")
    t = f"{ping_ms:.0f} ms"
    if mbps is not None:
        t += f" · {mbps:.0f} Mbit/s"
    return t


CORES = {0: QColor(200, 70, 70), 1: QColor(220, 90, 70), 2: QColor(225, 170, 60), 3: QColor(150, 200, 90),
         4: QColor(80, 190, 110)}


class SinalRede(QWidget):
    """As barras e o texto; `medir()` roda numa linha à parte."""

    chegou = Signal(dict)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.r: dict = {"ok": True, "ping_ms": None, "mbps": None}
        self.medindo = False
        self._tem = False
        self.chegou.connect(self._mostrar)
        self.setCursor(Qt.PointingHandCursor)
        self._dica()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(34 + self.fontMetrics().horizontalAdvance(self._texto()) + 8, 18)

    def _texto(self) -> str:
        return texto(self.r.get("ping_ms"), self.r.get("mbps"), self.r.get("ok", True)) if self._tem else tr("rede…")

    def nivel(self) -> int:
        return barras(self.r.get("ping_ms"), self.r.get("mbps"), self.r.get("ok", True)) if self._tem else 0

    def medir(self, completo: bool = True) -> None:
        if self.medindo:
            return
        self.medindo = True

        def trabalho():
            try:
                r = self.client.medir_rede(completo)
            except Exception:  # noqa: BLE001
                r = {"ok": False, "ping_ms": None, "mbps": None}
            self.chegou.emit(r)
        threading.Thread(target=trabalho, name="ipe-rede", daemon=True).start()

    def vazao_do_download(self, mbps: float) -> None:
        """A vazão medida no próprio download do exame (sem tráfego a mais)."""
        self.chegou.emit({**self.r, "mbps": float(mbps), "_so_vazao": True})

    def _mostrar(self, r: dict) -> None:
        if not r.pop("_so_vazao", False):
            self.medindo = False
            if r.get("mbps") is None and r.get("ok"):
                r["mbps"] = self.r.get("mbps")           # o teste rápido não apaga a vazão que já se conhece
        self.r = r
        self._tem = True
        self._dica()
        self.updateGeometry()
        self.update()

    def _dica(self) -> None:
        nomes = {0: tr("sem conexão"), 1: tr("ruim"), 2: tr("regular"), 3: tr("boa"), 4: tr("ótima")}
        self.setToolTip(
            f"Rede até o servidor central: {nomes[self.nivel()] if self._tem else tr('medindo…')}\n"
            f"{self._texto()}\n"
            "Ida e volta (ms): quanto o servidor leva para responder. Vazão (Mbit/s): quanto chega por segundo.\n"
            "Clique para medir de novo.")

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.medir(True)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = self.nivel()
        h = self.height()
        for i in range(4):
            bh = 4 + i * 3
            r = QRectF(2 + i * 7, h - 3 - bh, 5, bh)
            p.setPen(Qt.NoPen)
            p.setBrush(CORES[n] if i < n else QColor(120, 120, 120, 110))
            p.drawRoundedRect(r, 1.2, 1.2)
        p.setPen(self.palette().windowText().color() if n else CORES[0])
        p.drawText(self.rect().adjusted(34, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self._texto())
        p.end()
