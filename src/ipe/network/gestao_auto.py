"""Gestão DICOM automática (0.99.6).

Pedido dele (27/10): *"queria poder automatizar a gestão também. com regras de horário, podendo
reenviar tudo, reenviar somente incompleto, enviando como e para, repetir se erro em x minutos, com
tela de gestão onde avisa o que foi completado, se deu erro, se algum destino/fonte estiver offline"*.

Uma regra é a rotina da tela de Gestão gravada: as modalidades (cada uma com a identidade que ela
aceita), o destino onde os exames têm de estar (com a identidade, "enviar como"), o período, o que
mandar (só o que falta ou o exame inteiro, sempre dos exames que não estão completos), o modo de
envio e o horário. Fica na tabela de regras da automação (tipo "gestao"); o relógio é o mesmo das
buscas agendadas. Aqui não há Qt: a regra roda inteira numa linha de trabalho e devolve um Relatorio.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from ipe.network import gestao as G

TIPO = "gestao"
PADRAO = {
    "fontes": [],                    # [{"node_id": 3, "identity_id": 7 | None}]
    "destino": {"node_id": None, "identity_id": None},
    "move_destination": "",          # vazio = o AE do destino
    "modalidade": "",
    "periodo": "hoje",               # hoje | ontem | 2dias | 7dias
    "ignorar": "",
    "exato": False,
    "envio": "falta",                # falta | inteiro (sempre só dos exames não completos)
    "modo": "auto",
    "schedule": {"type": "interval", "minutes": 60, "from": "07:00", "to": "20:00",
                 "weekdays": [0, 1, 2, 3, 4, 5]},
    "repetir": {"minutos": 15, "vezes": 3},
}
ENVIOS = {"falta": "Só o que falta", "inteiro": "O exame inteiro"}
A_MANDAR = ("incompleto", "ausente")


def config(regra: dict) -> dict:
    cfg = dict(PADRAO)
    cfg.update(regra.get("config") or {})
    return cfg


@dataclass
class Item:
    """Um exame que a regra mexeu (ou tentou)."""
    paciente: str
    accession: str
    study_uid: str
    fonte: str
    antes: str                       # situação na conferência
    depois: str = ""                 # situação conferida de novo depois do envio
    mensagem: str = ""
    ok: bool = False


@dataclass
class Relatorio:
    regra: str = ""
    inicio: str = ""
    fim: str = ""
    conferidos: int = 0
    completos: int = 0               # já estavam completos
    enviados: list = field(default_factory=list)     # Item com ok=True (completou depois do envio)
    falhas: list = field(default_factory=list)       # Item com erro ou que ainda ficou incompleto
    outro_uid: list = field(default_factory=list)    # mesmo accession, outro Study UID (não manda)
    offline: list = field(default_factory=list)      # "nome: erro" dos nós que não responderam
    destino_offline: bool = False
    erro: str = ""

    @property
    def situacao(self) -> str:
        """ok | erro | offline (o que o painel pinta)."""
        if self.destino_offline or (self.offline and not self.conferidos):
            return "offline"
        if self.erro or self.falhas or self.offline:
            return "erro"
        return "ok"

    def precisa_repetir(self) -> bool:
        return self.situacao != "ok"

    def resumo(self) -> str:
        if self.destino_offline:
            return f"destino fora do ar: {self.erro}"
        partes = [f"{self.conferidos} conferido(s)", f"{self.completos} já completo(s)"]
        if self.enviados:
            partes.append(f"{len(self.enviados)} completado(s) agora")
        if self.falhas:
            partes.append(f"{len(self.falhas)} com erro")
        if self.outro_uid:
            partes.append(f"{len(self.outro_uid)} com outro Study UID (não enviados)")
        if self.offline:
            partes.append("fora do ar: " + ", ".join(o.split(":")[0] for o in self.offline))
        if self.erro:
            partes.append(self.erro)
        return "; ".join(partes)

    def para_dict(self) -> dict:
        d = asdict(self)
        d["situacao"] = self.situacao
        d["resumo"] = self.resumo()
        return d


def _item(c: G.Conferencia) -> Item:
    return Item(c.estudo.get("patient_name", "") or "", c.estudo.get("accession", "") or "", c.study_uid,
                c.fonte, c.situacao)


def fontes_da_regra(repo, cfg: dict) -> list[G.Fonte]:
    out = []
    for f in cfg.get("fontes") or []:
        no = repo.node(f.get("node_id"))
        if no is not None and no.get("active", True) and no.get("kind", "dimse") == "dimse":
            out.append(G.Fonte(no, repo.identity(f.get("identity_id")) if f.get("identity_id") else None))
    return out


def destino_da_regra(repo, cfg: dict) -> G.Fonte | None:
    d = cfg.get("destino") or {}
    no = repo.node(d.get("node_id")) if d.get("node_id") else None
    if no is None:
        return None
    return G.Fonte(no, repo.identity(d.get("identity_id")) if d.get("identity_id") else None)


def executar(regra: dict, repo, cliente, alvo_de, *, sink=None, hoje: date | None = None,
             cancel: threading.Event | None = None, espera: float = 2.0, progresso=None) -> Relatorio:
    """Confere e manda o que precisa. Nunca levanta exceção: o que deu errado vai no relatório."""
    cfg = config(regra)
    rel = Relatorio(regra=regra.get("name", ""), inicio=datetime.now().isoformat(timespec="seconds"))
    try:
        fontes = fontes_da_regra(repo, cfg)
        destino = destino_da_regra(repo, cfg)
        if not fontes or destino is None:
            rel.erro = "regra sem modalidade ou sem destino"
            return rel
        de, ate = G.periodo(cfg.get("periodo", "hoje"), hoje or date.today())
        ignorar = [x.strip() for x in str(cfg.get("ignorar", "")).split(";") if x.strip()]
        conferidor = G.Conferidor(cliente, alvo_de)
        try:
            res, erros = conferidor.conferir(fontes, destino, de, ate, modalidade=cfg.get("modalidade", ""),
                                             ignorar=ignorar, exato=bool(cfg.get("exato")), cancel=cancel,
                                             progresso=progresso)
        except Exception as e:  # noqa: BLE001 - o destino não respondeu: nada a fazer agora
            rel.destino_offline, rel.erro = True, f"{destino.nome}: {e}"
            return rel
        rel.offline = [e for e in erros if not e.startswith(("Conferência interrompida", "O mesmo erro"))]
        rel.erro = next((e for e in erros if e.startswith("O mesmo erro")), "")
        rel.conferidos = len(res)
        rel.completos = sum(1 for c in res if c.situacao == "completo")
        rel.outro_uid = [asdict(_item(c)) for c in res if c.situacao == "outro_uid"]
        for c in res:
            if c.situacao == "erro":
                it = _item(c)
                it.mensagem = c.detalhe or "não deu para conferir"
                rel.falhas.append(asdict(it))
        a_mandar = [c for c in res if c.situacao in A_MANDAR]
        if not a_mandar:
            return rel
        rem = G.Remetente(cliente, alvo_de, sink=sink, repo=repo)
        por_id = {f.no.get("id"): f for f in fontes}
        dest_ae = (cfg.get("move_destination") or "").strip() or destino.no.get("ae_title", "")
        inteiro = cfg.get("envio") == "inteiro"
        for i, c in enumerate(a_mandar, 1):
            if cancel is not None and cancel.is_set():
                break
            it = _item(c)
            f = por_id.get(c.fonte_id)
            if progresso:
                progresso(i - 1, len(a_mandar), f"enviando {it.paciente} ({i} de {len(a_mandar)})")
            try:
                r = rem.enviar(cfg.get("modo", "auto"), f, destino, c, dest_ae, inteiro=inteiro, cancel=cancel)
                it.mensagem = r.get("mensagem", "")
                depois = c
                for tentativa in range(3):          # enviado não é "está lá": o destino indexa depois
                    time.sleep(espera if tentativa else min(espera, 1.0))
                    depois = conferidor.reconferir(f, destino, c.study_uid, ignorar=ignorar,
                                                   exato=bool(cfg.get("exato")))
                    if depois.situacao == "completo":
                        break
                it.depois = depois.situacao
                it.ok = depois.situacao == "completo"
                if not it.ok:
                    it.mensagem = f"{it.mensagem} — conferido de novo: {depois.texto().lower()}"
            except Exception as e:  # noqa: BLE001
                it.mensagem, it.ok = f"falhou: {e}", False
            try:
                repo.audit("gestão automática", f"{rel.regra}: {it.accession} {it.paciente} → {destino.nome} — "
                                                 f"{it.mensagem}", study_uid=c.study_uid)
            except Exception:  # noqa: BLE001
                pass
            (rel.enviados if it.ok else rel.falhas).append(asdict(it))
    except Exception as e:  # noqa: BLE001
        rel.erro = str(e)
    finally:
        rel.fim = datetime.now().isoformat(timespec="seconds")
    return rel


def proxima_tentativa(regra: dict, agora: datetime, tentativas: int) -> datetime | None:
    """Depois de um erro: daqui a X minutos, se ainda houver tentativas; senão None (fica o horário)."""
    rep = config(regra).get("repetir") or {}
    minutos, vezes = int(rep.get("minutos") or 0), int(rep.get("vezes") or 0)
    if minutos <= 0 or tentativas >= vezes:
        return None
    return agora + timedelta(minutes=minutos)
