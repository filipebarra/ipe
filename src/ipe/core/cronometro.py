"""Cronômetro da abertura de um exame (0.99.86).

Ele achava a abertura lenta, e o registro não dizia onde ia o tempo. Cada abertura agora deixa uma linha
no registro, por exemplo::

    Abertura (CT, 1834 imagens): primeira imagem em 1,92 s — banco 0,05 · barra 0,31 · regras 0,02 ·
    tira 0,40 · protocolo 0,61 · janela 0,08 · estado 0,12 · imagem 0,33

e o que chega depois (sobreposições de IA, o resto do download do servidor) sai numa segunda linha,
com o tempo desde o começo. Custa duas chamadas a `perf_counter` por etapa.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("ipe.abertura")

_atual: "Cronometro | None" = None

# 0.100.61: no modo cliente, cada linha da abertura vai também para o registro do servidor (para comparar versões e
# computadores sem ir à máquina do cliente). Quem liga é o ClientRepository; a chamada sai numa linha à parte.
enviar = None


def _mandar(texto: str) -> None:
    fn = enviar
    if fn is None:
        return
    import threading

    def ir():
        try:
            fn(texto)
        except Exception:  # noqa: BLE001 - servidor de versão anterior, rede: o registro local já tem a linha
            log.debug("abertura para o servidor", exc_info=True)
    threading.Thread(target=ir, name="abertura-servidor", daemon=True).start()


class Cronometro:
    def __init__(self, rotulo: str):
        self.rotulo = rotulo
        self.t0 = self.ultimo = time.perf_counter()
        self.etapas: list[tuple[str, float]] = []
        self.fechado = False

    def marca(self, nome: str) -> None:
        agora = time.perf_counter()
        self.etapas.append((nome, agora - self.ultimo))
        self.ultimo = agora

    def total(self) -> float:
        return time.perf_counter() - self.t0

    def texto(self) -> str:
        partes = " · ".join(f"{n} {d:.2f}".replace(".", ",") for n, d in self.etapas if d >= 0.005)
        return f"Abertura ({self.rotulo}): primeira imagem em {self.total():.2f} s".replace(".", ",") + \
            (f" — {partes}" if partes else "")


def iniciar(rotulo: str = "") -> Cronometro:
    global _atual
    _atual = Cronometro(rotulo)
    return _atual


def atual() -> "Cronometro | None":
    return _atual if _atual is not None and not _atual.fechado else None


def marca(nome: str) -> None:
    c = atual()
    if c is not None:
        c.marca(nome)


def rotular(rotulo: str) -> None:
    c = atual()
    if c is not None and rotulo:
        c.rotulo = rotulo


def primeira_imagem() -> None:
    """Chamado pelo quadro quando pinta uma imagem: fecha a linha da abertura."""
    global _depois
    c = atual()
    if c is None:
        return
    c.marca("imagem")
    c.fechado = True
    texto = c.texto()
    log.info(texto)
    _mandar(texto)
    _depois = c


_depois: "Cronometro | None" = None


def depois(nome: str, segundos: float | None = None) -> None:
    """O que termina depois da primeira imagem (sobreposições, download), com o tempo desde o começo."""
    c = _depois or _atual
    if c is None or nome in c.__dict__.setdefault("_ditos", set()):
        return
    c._ditos.add(nome)
    extra = f" ({segundos:.2f} s)".replace(".", ",") if segundos is not None else ""
    texto = "Abertura ({}): {} pronto em {} s{}".format(c.rotulo, nome, f"{c.total():.2f}".replace(".", ","), extra)
    log.info(texto)
    _mandar(texto)


def cancelar() -> None:
    global _atual
    _atual = None
