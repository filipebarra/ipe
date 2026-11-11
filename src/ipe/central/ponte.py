"""0.100.10: rodar uma chamada na linha da tela (a do laço de eventos) a partir da linha do servidor web.

A fila de IA (`AutomationEngine`) usa QTimer e sinais: chamada da linha de um pedido HTTP, que não tem laço de
eventos, o QTimer nunca dispararia. A ponte é um QObject criado na linha principal; o pedido manda a função por um
sinal (entregue na linha da ponte) e espera a resposta.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot


class Ponte(QObject):
    _pedido = Signal(object)

    def __init__(self):
        super().__init__()
        self._pedido.connect(self._rodar)

    @Slot(object)
    def _rodar(self, item) -> None:
        fn, caixa, pronto = item
        try:
            caixa["r"] = fn()
        except BaseException as e:  # noqa: BLE001 - devolve ao pedido, que relança
            caixa["e"] = e
        pronto.set()

    def chamar(self, fn, espera: float = 30.0):
        """Roda `fn()` na linha da ponte e devolve o resultado (relança o erro dela)."""
        if QThread.currentThread() == self.thread():
            return fn()
        caixa: dict = {}
        pronto = threading.Event()
        self._pedido.emit((fn, caixa, pronto))
        if not pronto.wait(espera):
            raise TimeoutError("a linha principal do servidor não respondeu")
        if "e" in caixa:
            raise caixa["e"]
        return caixa.get("r")
