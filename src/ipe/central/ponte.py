"""0.100.10: rodar uma chamada na linha da tela (a do laço de eventos) a partir da linha do servidor web.

A fila de IA (`AutomationEngine`) usa QTimer e sinais: chamada da linha de um pedido HTTP, que não tem laço de
eventos, o QTimer nunca dispararia. A ponte é um QObject criado na linha principal; o pedido manda a função por um
sinal (entregue na linha da ponte) e espera a resposta.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot


class Ponte(QObject):
    _pedido = Signal(object)

    def __init__(self):
        super().__init__()
        self._linha = threading.get_ident()          # a linha (do Python) em que a ponte foi criada: a da tela
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
        # 0.100.68: a comparação é pela linha do Python. Antes era `QThread.currentThread() == self.thread()`, e
        # isso criava um objeto de linha do Qt para cada linha de pedido HTTP — que acaba logo depois. Com muitos
        # pedidos, o processo caía (ou travava) mais adiante, dentro do Qt, ao gravar uma folha em PDF na linha
        # principal (`QPdfEngine::addImage` → `QImageWriter::supportedImageFormats` → `QObject::moveToThread`).
        # Achado nos testes das Impressões no navegador: 3 quedas em 3 rodadas antes, nenhuma em 6 depois.
        if threading.get_ident() == self._linha:
            return fn()
        caixa: dict = {}
        pronto = threading.Event()
        self._pedido.emit((fn, caixa, pronto))
        if not pronto.wait(espera):
            raise TimeoutError("a linha principal do servidor não respondeu")
        if "e" in caixa:
            raise caixa["e"]
        return caixa.get("r")
