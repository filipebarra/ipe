"""A fila dos trabalhos de impressão que ficaram parados.

Um filme parado é um filme que a modalidade mandou e ninguém viu sair. Isso é **de propósito**
quando o aparelho ainda não tem cadastro — sem saber quem mandou não dá para escolher o destino —
mas só é aceitável enquanto estiver visível e for fácil de destravar.

Este módulo não encaminha nada: ele só olha a lista e diz, para cada trabalho, **por que está
parado** e **se já dá para soltar**. Quem solta é a janela, pelo mesmo caminho do encaminhamento
automático, para não existirem dois jeitos de mandar um filme.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ipe.printing import arrival as A
from ipe.printing import origins as O
from ipe.printing import rules as R
from ipe.printing.config import find_server

SEM_CADASTRO = "sem_cadastro"
DESLIGADA = "desligada"
SEM_REGRA = "sem_regra"
SEM_PACIENTE = "sem_paciente"
PRONTO = "pronto"

#: o que cada motivo quer dizer na tela
TEXTO = {
    SEM_CADASTRO: "Origem ainda não cadastrada",
    DESLIGADA: "Origem desligada",
    SEM_REGRA: "Sem regra nem destino fixo",
    SEM_PACIENTE: "Paciente não identificado pelo OCR: confirme em Identificar paciente",
    PRONTO: "Pronto para liberar",
}


@dataclass
class _JobDaLinha:
    """O bastante do trabalho para as regras responderem sem abrir o arquivo no disco.

    A fila precisa saber para onde cada filme iria, e são dezenas — abrir todos só para
    perguntar isso custaria caro e falharia justamente no trabalho cuja pasta sumiu.
    """
    calling_ae: str = ""
    label: str = ""
    film_size: str = ""
    sheets: int = 0
    received_at: str = ""
    modality: str = ""

    def when(self) -> datetime:
        bruto = self.received_at
        if isinstance(bruto, datetime):
            return bruto
        for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(str(bruto)[:19], formato)
            except ValueError:
                continue
        return datetime.now()


def job_of(row: dict, job=None):
    """O trabalho de verdade quando ele existe; senão, o retrato que a linha do banco dá."""
    if job is not None:
        return job
    row = row or {}
    return _JobDaLinha(calling_ae=row.get("calling_ae", ""), label=row.get("label", ""),
                       film_size=row.get("film_size", ""), sheets=int(row.get("sheets") or 0),
                       received_at=row.get("received_at", ""), modality=row.get("modality", "") or "")


def alvos(settings, row: dict, job=None) -> list:
    """Para onde este trabalho iria, se fosse encaminhado agora."""
    origem = O.job_origin(settings, row)
    # modalidade: a guardada no trabalho (exame do paciente) ou, sem ela, a da origem cadastrada
    mod = ((row or {}).get("modality") or getattr(job, "modality", "") or
           (getattr(origem, "modality", "") if origem is not None else "") or "")
    saida = R.choose(settings, job_of(row, job), (row or {}).get("server", ""),
                     origem.id if origem else "", mod)
    if saida:
        return list(saida)
    srv = find_server(settings, (row or {}).get("server", ""))
    if srv is not None and getattr(srv, "auto_destination", ""):
        return [(srv.auto_destination, getattr(srv, "template", ""))]
    return []


def reason(settings, row: dict, job=None) -> str:
    """Por que este trabalho não saiu. `PRONTO` = é só mandar."""
    pode, _ = O.may_forward(settings, row)
    if not pode:
        origem = O.job_origin(settings, row)
        return DESLIGADA if (origem is not None and origem.registered) else SEM_CADASTRO
    if A.falta_paciente(settings, row):
        return SEM_PACIENTE
    return PRONTO if alvos(settings, row, job) else SEM_REGRA


def held(rows) -> list[dict]:
    """Os trabalhos que continuam esperando: recebidos pela impressora e ainda não enviados."""
    return [r for r in (rows or [])
            if (r.get("status") or "new") == "new" and (r.get("source") or "scp") == "scp"]


@dataclass
class Group:
    """Um aparelho e tudo o que dele está parado."""
    origin_id: str = ""
    calling_ae: str = ""
    remote_host: str = ""
    server: str = ""
    name: str = ""
    motivo: str = SEM_CADASTRO
    rows: list = field(default_factory=list)

    @property
    def trabalhos(self) -> int:
        return len(self.rows)

    @property
    def folhas(self) -> int:
        return sum(int(r.get("sheets") or 0) for r in self.rows)

    @property
    def imagens(self) -> int:
        return sum(int(r.get("images") or 0) for r in self.rows)

    @property
    def pode_liberar(self) -> bool:
        return self.motivo == PRONTO

    @property
    def cadastrada(self) -> bool:
        return self.motivo not in (SEM_CADASTRO,)

    def label(self) -> str:
        onde = self.remote_host or "endereço desconhecido"
        if self.name:
            return f"{self.name} — {onde}"
        return f"AE {self.calling_ae or '?'} (sem cadastro) — {onde}"

    def desde(self) -> str:
        datas = [r.get("received_at") for r in self.rows if r.get("received_at")]
        return str(min(datas)) if datas else ""


def groups(settings, rows, carregar=None) -> list[Group]:
    """Agrupa os parados por aparelho.

    `carregar(row)` devolve o `PrintJob` do disco, quando vale a pena abrir. Sem ele o motivo
    sai do retrato que a linha do banco dá (`job_of`) — o suficiente para as regras de AE,
    rótulo, tamanho de filme, folhas e horário, que são as que decidem o destino.
    """
    achados: dict[str, Group] = {}
    for row in held(rows):
        origem = O.job_origin(settings, row)
        ident = origem.id if origem else O.origin_id(row.get("calling_ae", ""),
                                                     row.get("remote_host", ""),
                                                     row.get("server", ""))
        # do mesmo aparelho, os que esperam o paciente ficam num grupo à parte: o motivo é outro
        chave = (ident, A.falta_paciente(settings, row))
        g = achados.get(chave)
        if g is None:
            g = achados[chave] = Group(
                origin_id=ident, calling_ae=row.get("calling_ae", ""),
                remote_host=row.get("remote_host", ""), server=row.get("server", ""),
                name=(origem.name if origem else ""))
        g.rows.append(row)
    for g in achados.values():
        job = None
        if carregar is not None and g.rows:
            try:
                job = carregar(g.rows[0])
            except Exception:  # noqa: BLE001 - motivo é informação, não pode derrubar a tela
                job = None
        g.motivo = reason(settings, g.rows[0], job)
    return sorted(achados.values(), key=lambda g: (not g.pode_liberar, -g.trabalhos))


def releasable(settings, rows, origin_id: str = "", carregar=None) -> list[dict]:
    """Os trabalhos que dá para soltar agora — todos, ou só os de um aparelho."""
    saida = []
    for g in groups(settings, rows, carregar):
        if not g.pode_liberar:
            continue
        if origin_id and g.origin_id != origin_id:
            continue
        saida.extend(g.rows)
    return saida


def resumo(gs: list[Group]) -> str:
    """Uma frase para a faixa da aba de impressões."""
    prontos = sum(g.trabalhos for g in gs if g.pode_liberar)
    sem_paciente = sum(g.trabalhos for g in gs if g.motivo == SEM_PACIENTE)
    parados = sum(g.trabalhos for g in gs) - prontos - sem_paciente
    partes = []
    if prontos and parados:
        partes.append(f"{prontos} trabalho(s) prontos para liberar e {parados} esperando cadastro.")
    elif prontos:
        partes.append(f"{prontos} trabalho(s) prontos para liberar.")
    elif parados:
        partes.append(f"{parados} trabalho(s) parados esperando cadastro da origem.")
    if sem_paciente:
        partes.append(f"{sem_paciente} trabalho(s) esperando você confirmar o paciente.")
    return " ".join(partes)
