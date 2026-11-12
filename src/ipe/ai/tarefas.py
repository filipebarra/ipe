"""Registro das tarefas de IA (0.99.32): o que está na fila, rodando, pronto, com erro ou cancelado.

Pedido dele: *"quero acompanhar as IAs. hoje não tenho onde poder cancelar e ver o andamento, em
especial das que rodam automaticamente quando o exame é adicionado"*. As segmentações (TotalSegmentator,
SynthSeg) rodam pela tela (Segmentacao, com barra de progresso) ou sozinhas na chegada do exame
(automation/engine, em segundo plano, sem janela nenhuma). Todas passam a se registrar aqui, e a janela
"Tarefas de IA" mostra e cancela.

Sem Qt: a janela consulta `REGISTRO.tarefas()` a cada segundo. Thread-safe (o trabalho automático roda
fora da linha da tela).
"""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field

FILA, PREPARANDO, RODANDO, GRAVANDO = "fila", "preparando", "rodando", "gravando"
PRONTO, ERRO, CANCELADO, VAZIO = "pronto", "erro", "cancelado", "nada a fazer"
ATIVOS = (FILA, PREPARANDO, RODANDO, GRAVANDO)
ROTULO = {FILA: "Na fila", PREPARANDO: "Montando o volume", RODANDO: "Rodando", GRAVANDO: "Gravando no exame",
          PRONTO: "Pronto", ERRO: "Erro", CANCELADO: "Cancelado", VAZIO: "Nada a fazer"}


@dataclass
class Tarefa:
    id: int
    ferramenta: str                  # "Órgãos abdominais", "Níveis da coluna"…
    study_uid: str
    exame: str = ""                  # paciente e descrição (para a tela)
    origem: str = "automática"       # automática | manual
    estado: str = FILA
    etapa: str = ""
    criada: float = field(default_factory=time.time)
    inicio: float = 0.0
    fim: float = 0.0
    mensagem: str = ""
    cancelar_fn: object = field(default=None, repr=False)   # callable() que pede o cancelamento
    cancelar_pedido: bool = False
    cancelar_em: float = 0.0          # quando o Cancelar foi apertado (0.99.34)
    liberar_fn: object = field(default=None, repr=False)    # callable() que solta o exame à força

    @property
    def ativa(self) -> bool:
        return self.estado in ATIVOS

    def tempo(self, agora: float | None = None) -> float:
        if not self.inicio:
            return 0.0
        return (self.fim or (agora if agora is not None else time.time())) - self.inicio


class Registro:
    def __init__(self, guardar: int = 100):
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._t: dict[int, Tarefa] = {}
        self.guardar = guardar

    # ------------------------------------------------------------------ escrever
    def nova(self, ferramenta: str, study_uid: str, exame: str = "", origem: str = "automática",
             estado: str = FILA, cancelar=None) -> Tarefa:
        with self._lock:
            t = Tarefa(next(self._ids), ferramenta, study_uid, exame, origem, estado, cancelar_fn=cancelar)
            if estado != FILA:
                t.inicio = time.time()
            self._t[t.id] = t
            self._podar()
            return t

    def mudar(self, tid: int | None, estado: str | None = None, etapa: str | None = None,
              mensagem: str | None = None) -> None:
        if tid is None:
            return
        with self._lock:
            t = self._t.get(tid)
            if t is None:
                return
            if estado is not None:
                if estado != FILA and not t.inicio:
                    t.inicio = time.time()
                if estado not in ATIVOS and not t.fim:
                    t.fim = time.time()
                t.estado = estado
            if etapa is not None:
                t.etapa = etapa
            if mensagem is not None:
                t.mensagem = mensagem

    def ao_liberar(self, tid: int | None, fn) -> None:
        """O que fazer se a tarefa não responder ao Cancelar (soltar o exame, matar o processo)."""
        with self._lock:
            t = self._t.get(tid) if tid is not None else None
            if t is not None:
                t.liberar_fn = fn

    def ao_cancelar(self, tid: int | None, fn) -> None:
        with self._lock:
            t = self._t.get(tid) if tid is not None else None
            if t is not None:
                t.cancelar_fn = fn

    def _podar(self) -> None:
        feitas = sorted((t for t in self._t.values() if not t.ativa), key=lambda t: t.fim or t.criada)
        for t in feitas[: max(0, len(feitas) - self.guardar)]:
            self._t.pop(t.id, None)

    # ------------------------------------------------------------------ ler
    def tarefas(self) -> list[Tarefa]:
        with self._lock:
            return sorted(self._t.values(), key=lambda t: (not t.ativa, -t.criada if not t.ativa else t.criada))

    def ativas(self, study_uid: str | None = None) -> list[Tarefa]:
        return [t for t in self.tarefas() if t.ativa and (study_uid is None or t.study_uid == study_uid)]

    def resumo(self) -> str:
        """"IA: 1 rodando, 2 na fila" — vazio quando não há nada ativo."""
        at = self.ativas()
        if not at:
            return ""
        rod = sum(1 for t in at if t.estado != FILA)
        fila = len(at) - rod
        partes = ([f"{rod} rodando"] if rod else []) + ([f"{fila} na fila"] if fila else [])
        return "IA: " + ", ".join(partes)

    # ------------------------------------------------------------------ cancelar
    #: segundos que a tarefa tem para parar depois do Cancelar; passou disso, ela é fechada à força
    ESPERA_CANCELAR = 15.0

    def cancelar(self, tid: int) -> bool:
        """0.99.34, relato dele: *"não consigo cancelar. os botões de cancelar a escolhida ou todos não
        estão funcionando"*. Antes, quando o trabalho já não existia (a aba do exame tinha fechado), o
        pedido de cancelar dava erro calado e a tarefa ficava "rodando" para sempre. Agora: sem quem
        cancele, ou se cancelar der erro, fecha na hora; se o trabalho não parar em 15 s, `conferir()`
        fecha e solta o exame."""
        with self._lock:
            t = self._t.get(tid)
            if t is None or not t.ativa:
                return False
            t.cancelar_pedido = True
            t.cancelar_em = time.time()
            fn = t.cancelar_fn
            if t.estado == FILA:
                t.estado, t.fim, t.mensagem = CANCELADO, time.time(), "cancelada antes de começar"
        ok = fn is not None
        if fn is not None:
            try:
                fn()
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            self._forcar(tid, "cancelada")
        return True

    def _forcar(self, tid: int, mensagem: str) -> None:
        with self._lock:
            t = self._t.get(tid)
            if t is None or not t.ativa:
                return
            t.estado, t.fim, t.mensagem, t.etapa = CANCELADO, time.time(), mensagem, ""
            liberar = t.liberar_fn
        if liberar is not None:
            try:
                liberar()
            except Exception:  # noqa: BLE001
                pass

    def conferir(self, agora: float | None = None) -> int:
        """Fecha as tarefas que pediram para cancelar e não pararam (chamado a cada segundo pela janela
        Tarefas de IA e pela barra de status). Devolve quantas fechou."""
        agora = time.time() if agora is None else agora
        presas = [t.id for t in self.ativas() if t.cancelar_pedido and t.cancelar_em
                  and agora - t.cancelar_em >= self.ESPERA_CANCELAR]
        for tid in presas:
            self._forcar(tid, "cancelada (o trabalho não respondeu e foi encerrado)")
        return len(presas)

    def cancelar_todas(self) -> int:
        return sum(1 for t in self.ativas() if self.cancelar(t.id))

    def limpar_feitas(self) -> int:
        with self._lock:
            ids = [i for i, t in self._t.items() if not t.ativa]
            for i in ids:
                self._t.pop(i, None)
            return len(ids)


REGISTRO = Registro()


# ---------------------------------------------------------------------- o que o exame já tem de IA
#: (trecho da descrição da série, nome curto) — as séries que as ferramentas de IA gravam no exame
MARCAS = (
    ("Órgãos abdominais · TotalSegmentator", "órgãos abdominais"),
    ("Volumetria abdominal · TotalSegmentator", "órgãos abdominais"),
    ("Níveis da coluna", "coluna"),
    ("medidas · TotalSegmentator", "coluna"),
    ("Cefalometria", "cefalometria"),
    ("· SynthSeg", "índices do crânio"),
    ("· SynthSR", "T1 sintético"),
    ("Níveis linfonodais", "níveis linfonodais"),
    ("· sem implante", "implante"),
    ("· TotalSegmentator", "segmentação"),
)


def ferramentas_da_serie(descricao: str) -> str:
    d = descricao or ""
    for trecho, nome in MARCAS:
        if trecho in d:
            return nome
    return ""
