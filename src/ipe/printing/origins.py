"""Origens dos trabalhos de impressão: quem mandou, com nome que você reconhece.

O padrão DICOM não manda nome de paciente num trabalho de impressão, mas manda **quem está
falando**: o AE title de quem abriu a associação, o endereço de onde veio e em qual dos seus
servidores de impressão a conexão entrou. Isso é o suficiente para separar aparelhos.

O problema é que "CT1_CONSOLE em 10.0.3.47" não diz nada na hora de criar uma regra. Este
módulo guarda um cadastro: cada origem vista ganha um **nome amigável** ("TC Sala 2"), e as
regras passam a apontar para a origem em vez de um padrão de AE digitado à mão.

Uma origem é identificada por **AE + endereço + servidor que recebeu**. É o critério mais
estrito, e por isso existe `also_hosts`: quando o mesmo aparelho volta de outro IP (troca de
rede, DHCP), você diz uma vez que é o mesmo e o endereço novo passa a valer para aquela
origem, em vez de virar um cadastro repetido.

Sem Qt: serve tanto à interface quanto ao recebimento em segundo plano.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)

CHAVE = "printing.origins"


@dataclass
class Origin:
    """Um aparelho (ou console) que manda trabalhos de impressão."""
    calling_ae: str = ""
    remote_host: str = ""
    server: str = ""                                  # servidor de impressão que recebeu
    name: str = ""                                    # "" = vista, mas ainda não cadastrada
    enabled: bool = True
    note: str = ""
    modality: str = ""                                # 0.84: modalidade do aparelho (MG, CT…), opcional
    also_hosts: list = field(default_factory=list)    # outros endereços do mesmo aparelho
    first_seen: str = ""
    last_seen: str = ""
    jobs: int = 0

    @property
    def id(self) -> str:
        return origin_id(self.calling_ae, self.remote_host, self.server)

    @property
    def registered(self) -> bool:
        return bool((self.name or "").strip())

    def hosts(self) -> list:
        return [h for h in [self.remote_host, *self.also_hosts] if h]

    def matches(self, calling_ae: str, remote_host: str, server: str) -> bool:
        if (self.calling_ae or "").upper() != (calling_ae or "").upper():
            return False
        if (self.server or "") != (server or ""):
            return False
        enderecos = [h.lower() for h in self.hosts()]
        return not enderecos or (remote_host or "").lower() in enderecos

    def label(self) -> str:
        quem = self.name or self.calling_ae or "(sem AE)"
        onde = self.remote_host or "?"
        return f"{quem} — AE {self.calling_ae or '?'} em {onde}"

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in Origin.__dataclass_fields__}

    @staticmethod
    def from_dict(d: dict) -> Origin:
        known = Origin.__dataclass_fields__
        dados = {k: v for k, v in (d or {}).items() if k in known}
        dados["also_hosts"] = list(dados.get("also_hosts") or [])
        return Origin(**dados)


def origin_id(calling_ae: str, remote_host: str, server: str) -> str:
    return f"{(calling_ae or '').upper()}|{(remote_host or '').lower()}|{server or ''}"


# ------------------------------------------------------------------ cadastro
def all_origins(settings) -> list[Origin]:
    return [Origin.from_dict(d) for d in (settings.get(CHAVE, []) or [])]


def save_origins(settings, origens: list[Origin]) -> None:
    settings.set(CHAVE, [o.to_dict() for o in origens])
    settings.save()


def find(settings, calling_ae: str, remote_host: str, server: str) -> Origin | None:
    """A origem cadastrada que combina com estes dados (endereço alternativo conta)."""
    for o in all_origins(settings):
        if o.matches(calling_ae, remote_host, server):
            return o
    return None


def find_by_id(settings, ident: str) -> Origin | None:
    return next((o for o in all_origins(settings) if o.id == ident), None)


def see(settings, calling_ae: str, remote_host: str, server: str,
        when: str = "") -> tuple[Origin, bool]:
    """Anota que esta origem mandou um trabalho. Devolve (origem, é a primeira vez).

    Origem nunca vista entra **sem nome** — é o que a deixa na lista de pendentes.
    """
    agora = when or datetime.now().isoformat(timespec="seconds")
    origens = all_origins(settings)
    for o in origens:
        if o.matches(calling_ae, remote_host, server):
            o.last_seen = agora
            o.jobs = int(o.jobs or 0) + 1
            if remote_host and remote_host not in o.hosts():
                o.also_hosts.append(remote_host)
            save_origins(settings, origens)
            return o, False
    nova = Origin(calling_ae=calling_ae or "", remote_host=remote_host or "", server=server or "",
                  first_seen=agora, last_seen=agora, jobs=1)
    origens.append(nova)
    save_origins(settings, origens)
    log.info("Origem de impressão nova: %s em %s (servidor %s)", calling_ae, remote_host, server)
    return nova, True


def pending(settings) -> list[Origin]:
    """Origens já vistas que ainda não têm nome — as que estão segurando trabalhos."""
    return [o for o in all_origins(settings) if not o.registered]


def same_ae_elsewhere(settings, calling_ae: str, remote_host: str, server: str) -> list[Origin]:
    """Origens **cadastradas** com o mesmo AE, mas de outro endereço ou servidor.

    Serve para a pergunta "é o mesmo aparelho que mudou de IP?" — que é o caso comum quando
    uma origem nova aparece do nada num serviço que já estava funcionando.
    """
    saida = []
    for o in all_origins(settings):
        if not o.registered:
            continue
        if (o.calling_ae or "").upper() != (calling_ae or "").upper():
            continue
        if o.matches(calling_ae, remote_host, server):
            continue
        saida.append(o)
    return saida


def merge_host(settings, destino_id: str, remote_host: str) -> bool:
    """Diz que um endereço também é daquela origem (mesmo aparelho, IP novo)."""
    origens = all_origins(settings)
    alvo = next((o for o in origens if o.id == destino_id), None)
    if alvo is None or not remote_host:
        return False
    if remote_host not in alvo.hosts():
        alvo.also_hosts.append(remote_host)
    # a origem pendente que tinha esse endereço deixa de existir
    origens = [o for o in origens
               if o is alvo or not (o.calling_ae.upper() == alvo.calling_ae.upper()
                                    and not o.registered and remote_host in o.hosts())]
    save_origins(settings, origens)
    return True


def remove(settings, ident: str) -> bool:
    origens = all_origins(settings)
    restantes = [o for o in origens if o.id != ident]
    if len(restantes) == len(origens):
        return False
    save_origins(settings, restantes)
    return True


# ------------------------------------------------------------------ nome sugerido
_SEPARADORES = re.compile(r"[_\-.]+")


def suggest_name(calling_ae: str) -> str:
    """Nome de partida a partir do AE: "CT_SALA2" -> "CT Sala 2". Você ajusta depois."""
    bruto = _SEPARADORES.sub(" ", (calling_ae or "").strip())
    bruto = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", bruto)      # SALA2 -> SALA 2
    partes = []
    for p in bruto.split():
        partes.append(p if (p.isupper() and len(p) <= 3) or p.isdigit() else p.capitalize())
    return " ".join(partes)


# ------------------------------------------------------------------ uso pelo encaminhamento
def job_origin(settings, row: dict) -> Origin | None:
    """A origem de uma linha da lista de impressões."""
    return find(settings, (row or {}).get("calling_ae", ""), (row or {}).get("remote_host", ""),
                (row or {}).get("server", ""))


def may_forward(settings, row: dict) -> tuple[bool, str]:
    """Pode encaminhar sozinho? (pode, motivo de não poder).

    Trabalho de origem não cadastrada **fica parado**: foi a escolha do serviço, e é coerente
    com a regra de que nada sai sozinho sem alguém ter dito que pode.
    """
    if not bool(settings.get("printing.hold_unknown_origin", True)):
        return True, ""
    o = job_origin(settings, row)
    if o is None or not o.registered:
        quem = (row or {}).get("calling_ae") or "?"
        return False, f"Origem {quem} ainda não cadastrada: o trabalho ficou esperando."
    if not o.enabled:
        return False, f"Origem {o.name} está desligada: o trabalho ficou esperando."
    return True, ""


def register_from_job(settings, row: dict) -> tuple[Origin, bool]:
    """Anota a origem de um trabalho recebido."""
    return see(settings, (row or {}).get("calling_ae", ""), (row or {}).get("remote_host", ""),
               (row or {}).get("server", ""))


def backfill(settings, rows: list) -> int:
    """Monta o cadastro a partir dos trabalhos que já estão na lista. Devolve quantas entraram.

    Existe porque o cadastro nasceu depois dos trabalhos: sem isto, um serviço que já recebia
    impressões abriria a aba de origens vazia.
    """
    origens = all_origins(settings)
    novas = 0
    for row in rows or []:
        ae = (row or {}).get("calling_ae", "")
        host = (row or {}).get("remote_host", "")
        srv = (row or {}).get("server", "")
        if not ae and not host:
            continue
        achou = next((o for o in origens if o.matches(ae, host, srv)), None)
        quando = str((row or {}).get("received_at", "") or "")
        if achou is not None:
            achou.jobs = int(achou.jobs or 0) + 1
            if quando and (not achou.last_seen or quando > achou.last_seen):
                achou.last_seen = quando
            if quando and (not achou.first_seen or quando < achou.first_seen):
                achou.first_seen = quando
            continue
        origens.append(Origin(calling_ae=ae, remote_host=host, server=srv,
                              first_seen=quando, last_seen=quando, jobs=1))
        novas += 1
    if novas or origens:
        save_origins(settings, origens)
    return novas
