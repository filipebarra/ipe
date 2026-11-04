"""Prioridade, subespecialidade e prazo do laudo (0.99.52, onda B4 do plano ViewerHub/Eden).

A lista de exames vira lista de trabalho: cada exame tem uma **prioridade** (rotina, urgente, emergência),
uma **subespecialidade** (mama, neuro, tórax…) e um **prazo do laudo** = chegada ao banco + as horas da
regra. As três coisas saem de regras do serviço (Configurações ▸ Laudos ▸ Prioridade, subespecialidade e
prazos) e podem ser trocadas à mão em cada exame (botão direito ▸ Prioridade / Subespecialidade).

- Prioridade automática pelas palavras da descrição do exame (de fábrica "URGENTE", "PS", "PRONTO
  SOCORRO", "UTI" → urgente; "EMERGÊNCIA", "CÓDIGO AVC", "TRAUMA" → emergência).
- Subespecialidade pela primeira regra que casa: modalidades + (opcional) palavras da descrição.
- Prazo em horas corridas, por prioridade; a rotina pode ter horas próprias por subespecialidade.
- Situação: "faltam 5 h", "vence em 40 min" (menos de 2 h), "atrasado 3 h"; com o laudo assinado,
  "no prazo" ou "fora do prazo (+5 h)".

As regras moram nas configurações centrais (`AppSetting`, chave `sla`): no servidor central valem para
todas as estações.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

CHAVE = "sla"
PRIORIDADES = {"rotina": "Rotina", "urgente": "Urgente", "emergencia": "Emergência"}
ORDEM = {"emergencia": 0, "urgente": 1, "rotina": 2}
ATENCAO_H = 2.0
PADRAO = {
    "horas": {"rotina": 48, "urgente": 4, "emergencia": 1},
    "por_subesp": {},
    "palavras": {"urgente": "URGENTE|URGENCIA|\\bURG\\b|\\bPS\\b|PRONTO SOCORRO|PRONTO-SOCORRO|\\bUTI\\b",
                 "emergencia": "EMERGENCIA|CODIGO AVC|PROTOCOLO AVC|TRAUMA"},
    "subesp": [
        {"nome": "Mama", "mod": "MG", "desc": ""},
        {"nome": "Mama", "mod": "US|MR", "desc": "MAMA|BREAST|AXILA"},
        {"nome": "Medicina nuclear", "mod": "NM|PT", "desc": ""},
        {"nome": "Neuro", "mod": "CT|MR", "desc": "CRANIO|ENCEFALO|CEREBRO|BRAIN|HEAD|SELA|HIPOFISE"},
        {"nome": "Cabeça e pescoço", "mod": "CT|MR|US",
         "desc": "PESCOCO|TIREOIDE|TIROIDE|SEIOS DA FACE|FACE|ORBITA|OUVIDO|CAVUM|PAROTIDA"},
        {"nome": "Tórax", "mod": "CT|CR|DX", "desc": "TORAX|CHEST|PULM"},
        {"nome": "Musculoesquelético", "mod": "CT|MR|CR|DX|US",
         "desc": "JOELHO|OMBRO|QUADRIL|TORNOZELO|PUNHO|COTOVELO|\\bMAO\\b|\\bPE\\b|COLUNA|LOMBAR|CERVICAL|"
                 "DORSAL|ESQUELETO|MUSCUL|TENDAO"},
        {"nome": "Abdome", "mod": "CT|MR|US", "desc": "ABDOME|ABDOMEN|PELVE|FIGADO|RINS|RENAL|PROSTATA|UTERO|"
                                                   "OVARIO|TRANSVAGINAL|VIAS BILIARES"},
    ],
}


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()


def _dobrar(t: str) -> str:
    return _sem_acento(t).upper()


def config(repo) -> dict:
    cfg = {}
    try:
        cfg = repo.get_app_setting(CHAVE, None) or {}
    except Exception:  # noqa: BLE001
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    horas = {**PADRAO["horas"], **{k: float(v) for k, v in (cfg.get("horas") or {}).items() if k in PRIORIDADES}}
    return {"horas": horas,
            "por_subesp": {str(k): float(v) for k, v in (cfg.get("por_subesp") or {}).items() if str(v).strip()},
            "palavras": {**PADRAO["palavras"], **(cfg.get("palavras") or {})},
            "subesp": list(cfg.get("subesp") or PADRAO["subesp"])}


def _casa(padrao: str, texto: str) -> bool:
    if not padrao:
        return True
    padrao = _sem_acento(padrao)
    try:
        return re.search(padrao, texto, re.I) is not None
    except re.error:
        return any(p.strip() and p.strip().upper() in texto for p in padrao.split("|"))


def subespecialidade(modalidades: str, descricao: str, cfg: dict) -> str:
    mods = {m for m in re.split(r"[\\/,; ]+", str(modalidades or "").upper()) if m}
    desc = _dobrar(descricao)
    for r in cfg.get("subesp", []):
        alvo = {m.strip().upper() for m in str(r.get("mod") or "").split("|") if m.strip()}
        if alvo and not (alvo & mods):
            continue
        if _casa(r.get("desc") or "", desc):
            return str(r.get("nome") or "")
    return "Geral"


def prioridade(descricao: str, cfg: dict, manual: str = "") -> str:
    if manual in PRIORIDADES:
        return manual
    desc = _dobrar(descricao)
    for p in ("emergencia", "urgente"):
        if cfg.get("palavras", {}).get(p) and _casa(cfg["palavras"][p], desc):
            return p
    return "rotina"


def horas_do_prazo(prio: str, subesp: str, cfg: dict) -> float:
    if prio == "rotina" and subesp in cfg.get("por_subesp", {}):
        return float(cfg["por_subesp"][subesp])
    return float(cfg.get("horas", {}).get(prio, PADRAO["horas"].get(prio, 48)))


def prazo(chegada: datetime | None, prio: str, subesp: str, cfg: dict) -> datetime | None:
    if chegada is None:
        return None
    return chegada + timedelta(hours=horas_do_prazo(prio, subesp, cfg))


def _duracao(h: float) -> str:
    m = int(round(abs(h) * 60))
    if m < 60:
        return f"{m} min"
    if m < 48 * 60:
        return f"{m // 60} h" + (f" {m % 60:02d}" if m % 60 and m < 6 * 60 else "")
    return f"{m // (24 * 60)} d"


def situacao(prazo_: datetime | None, laudado_em: datetime | None = None,
             agora: datetime | None = None) -> tuple[str, str]:
    """(texto, estado) — estado: "ok", "atencao", "atrasado", "no_prazo", "fora_do_prazo" ou ""."""
    if prazo_ is None:
        return "", ""
    if laudado_em is not None:
        h = (laudado_em - prazo_).total_seconds() / 3600
        return ("no prazo", "no_prazo") if h <= 0 else (f"fora do prazo (+{_duracao(h)})", "fora_do_prazo")
    h = (prazo_ - (agora or datetime.now())).total_seconds() / 3600
    if h < 0:
        return f"atrasado {_duracao(h)}", "atrasado"
    if h < ATENCAO_H:
        return f"vence em {_duracao(h)}", "atencao"
    return f"faltam {_duracao(h)}", "ok"


def resolver(row_like: dict, cfg: dict, agora: datetime | None = None) -> dict:
    """Para uma linha do banco: prioridade, subespecialidade, prazo (AAAAMMDDHHMM), texto e estado do SLA."""
    prio = prioridade(row_like.get("description", ""), cfg, row_like.get("prioridade_manual", ""))
    sub = row_like.get("subesp_manual") or subespecialidade(row_like.get("modalities", ""),
                                                             row_like.get("description", ""), cfg)
    pz = prazo(row_like.get("chegada"), prio, sub, cfg)
    txt, est = situacao(pz, row_like.get("laudado_em"), agora)
    return {"prioridade": prio, "subesp": sub, "prazo": pz.strftime("%Y%m%d%H%M") if pz else "",
            "sla": txt, "sla_estado": est}
