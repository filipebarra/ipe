"""Regras de automação, sem Qt e sem rede (fáceis de testar).

Tipos de regra (tabela automation_rule, campo config em JSON):
- "query":    busca agendada num nó, com ação (baixar ou só avisar);
- "prior":    pré-busca de exames anteriores por modalidade;
- "route":    encaminhar para outro nó os exames que chegam e batem com o filtro.
A limpeza (autodelete) é uma política única, guardada nas preferências ("retention").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

KINDS = {"query": "Busca agendada", "prior": "Pré-busca de anteriores", "route": "Roteamento"}

# ------------------------------------------------------------------ padrões
DEFAULT_QUERY = {
    "node_id": None, "identity_id": None,
    "filters": {"name": "", "patient_id": "", "accession": "", "description": "", "modality": "MG"},
    "date": "today",                      # today | last_hours:N | last_days:N | any
    "schedule": {"type": "interval", "minutes": 10, "from": "07:00", "to": "19:00",
                 "weekdays": [0, 1, 2, 3, 4, 5]},
    "action": "download",                 # download | notify
    "add_to_list": None,
    "max_studies": 50,
}
DEFAULT_PRIORS = [
    ("MG / DBT", {"current": ["MG"], "fetch": ["MG"], "count": 2, "years": 5, "keywords": []}),
    ("RM de mama", {"current": ["MR"], "fetch": ["MR", "MG"], "count": 1, "years": 3, "keywords": ["mama"]}),
    ("US de mama", {"current": ["US"], "fetch": ["US", "MG"], "count": 1, "years": 2, "keywords": ["mama"]}),
    ("TC", {"current": ["CT"], "fetch": ["CT"], "count": 1, "years": 2, "keywords": []}),
    ("PET/CT", {"current": ["PT"], "fetch": ["PT"], "count": 1, "years": 3, "keywords": []}),
]
DEFAULT_ROUTE = {"modalities": [], "description_contains": "", "origins": ["received"],
                 "node_id": None, "identity_id": None}
# Pré-cálculo da dinâmica na chegada: nada é gravado nem enviado, só os quadros ficam prontos.
DEFAULT_DINAMICA = {"modalities": ["MR"], "description_contains": "mama"}
DEFAULT_RETENTION = {
    "enabled": False,
    "only_network": True,          # só exames que vieram da rede (não os importados à mão)
    "max_age_days": 30,            # recebidos há mais de N dias (0 = não usar)
    "not_opened_days": 15,         # não abertos há mais de N dias (0 = não usar)
    "per_modality_days": {},       # ex.: {"CT": 7, "MG": 90}
    "prefetch_days": 7,            # anteriores trazidos pela pré-busca
    "disk_high_pct": 85,           # ao passar disso, apaga os menos usados…
    "disk_low_pct": 70,            # …até voltar a isto
    "max_storage_gb": 0,           # teto do armazenamento (0 = não usar)
    "trash_days": 7,               # dias na lixeira antes de apagar de vez
}


# ------------------------------------------------------------------ datas
def date_range(spec: str, now: datetime) -> tuple[str, str]:
    """"today" / "last_days:7" / "last_hours:24" / "any" -> (de, até) em AAAAMMDD."""
    today = now.date()
    fmt = "%Y%m%d"
    if spec == "today":
        return today.strftime(fmt), today.strftime(fmt)
    if spec.startswith("last_days:"):
        n = int(spec.split(":", 1)[1] or 0)
        return (today - timedelta(days=n)).strftime(fmt), today.strftime(fmt)
    if spec.startswith("last_hours:"):
        n = int(spec.split(":", 1)[1] or 0)
        return (now - timedelta(hours=n)).date().strftime(fmt), today.strftime(fmt)
    return "", ""


def _hm(s: str, default: time) -> time:
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return default


def next_run(schedule: dict, after: datetime) -> datetime | None:
    """Próxima execução estritamente depois de `after`."""
    kind = schedule.get("type", "interval")
    if kind == "once":
        try:
            at = datetime.strptime(schedule.get("at", ""), "%Y-%m-%d %H:%M")
        except ValueError:
            return None
        return at if at > after else None
    days = set(schedule.get("weekdays") or range(7))
    if kind == "daily":
        at = _hm(schedule.get("at", "06:00"), time(6, 0))
        for d in range(0, 8):
            cand = datetime.combine(after.date() + timedelta(days=d), at)
            if cand > after and cand.weekday() in days:
                return cand
        return None
    minutes = max(1, int(schedule.get("minutes", 10)))
    t_from = _hm(schedule.get("from", "00:00"), time(0, 0))
    t_to = _hm(schedule.get("to", "23:59"), time(23, 59))
    cand = (after + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    for _ in range(9):
        if cand.weekday() in days:
            start, end = datetime.combine(cand.date(), t_from), datetime.combine(cand.date(), t_to)
            if cand < start:
                return start
            if cand <= end:
                return cand
        cand = datetime.combine(cand.date() + timedelta(days=1), t_from)
    return None


def describe_schedule(s: dict) -> str:
    wd = s.get("weekdays")
    days = "" if not wd or len(wd) == 7 else " (" + ",".join("SMTQQSS"[(d + 1) % 7] for d in sorted(wd)) + ")"
    if s.get("type") == "once":
        return f"uma vez em {s.get('at', '?')}"
    if s.get("type") == "daily":
        return f"diariamente às {s.get('at', '06:00')}{days}"
    return f"a cada {s.get('minutes', 10)} min, {s.get('from', '00:00')}–{s.get('to', '23:59')}{days}"


# ------------------------------------------------------------------ anteriores
def prior_rule_for(rules: list[dict], modalities: str, description: str) -> dict | None:
    """Primeira regra ativa que se aplica ao exame atual."""
    mods = {m.strip().upper() for m in (modalities or "").replace("\\", ",").split(",") if m.strip()}
    for r in rules:
        c = r["config"]
        if not r.get("active", True):
            continue
        if c.get("current") and not mods & {m.upper() for m in c["current"]}:
            continue
        return r
    return None


def select_priors(rule_cfg: dict, current: dict, candidates: list[dict], today: date) -> list[dict]:
    """Escolhe os anteriores a baixar: mais recentes primeiro, dentro da janela e das modalidades."""
    limit = (today - timedelta(days=int(365.25 * float(rule_cfg.get("years", 5))))).strftime("%Y%m%d")
    fetch = {m.upper() for m in rule_cfg.get("fetch", [])}
    kws = [k.lower() for k in rule_cfg.get("keywords", []) if k.strip()]
    per_mod = int(rule_cfg.get("count", 1))
    out, taken = [], {}
    for c in sorted(candidates, key=lambda x: (x.get("study_date", ""), x.get("study_time", "")), reverse=True):
        if c["study_uid"] == current["study_uid"]:
            continue
        if c.get("study_date", "") and (c["study_date"] < limit or c["study_date"] > current.get("study_date", "99999999")):
            continue
        mods = {m.upper() for m in (c.get("modalities") or "").replace("\\", ",").split(",") if m}
        hit = mods & fetch if fetch else mods
        if fetch and not hit:
            continue
        # palavras-chave (ex.: "mama") valem para a modalidade atual; MG e US de mama não precisam
        same_mod = bool(mods & {m.upper() for m in (current.get("modalities") or "").replace("\\", ",").split(",")})
        if kws and same_mod and not any(k in (c.get("description") or "").lower() for k in kws):
            continue
        key = sorted(hit)[0] if hit else ""
        if taken.get(key, 0) >= per_mod:
            continue
        taken[key] = taken.get(key, 0) + 1
        out.append(c)
    return out


# ------------------------------------------------------------------ roteamento
def route_matches(cfg: dict, study: dict, origin: str) -> bool:
    if cfg.get("origins") and origin not in cfg["origins"]:
        return False
    mods = {m.upper() for m in (study.get("modalities") or "").replace("\\", ",").split(",") if m}
    want = {m.upper() for m in cfg.get("modalities", []) if m}
    if want and not mods & want:
        return False
    text = (cfg.get("description_contains") or "").strip().lower()
    return not text or text in (study.get("description") or "").lower()


# ------------------------------------------------------------------ limpeza
@dataclass
class StudyStat:
    study_uid: str
    patient: str
    description: str
    modalities: str
    origin: str
    date_added: datetime
    last_accessed: datetime | None
    size_bytes: int
    protected: list[str] = field(default_factory=list)     # motivos para nunca apagar


def select_for_deletion(stats: list[StudyStat], policy: dict, now: datetime,
                        disk_used_pct: float | None = None, disk_total_bytes: int | None = None,
                        storage_bytes: int | None = None, open_uids: set[str] = frozenset()
                        ) -> list[tuple[StudyStat, str]]:
    """Estudos a apagar e o motivo. Nunca inclui protegidos nem abertos."""
    pool = [s for s in stats if not s.protected and s.study_uid not in open_uids
            and not (policy.get("only_network", True) and s.origin in ("import", "anonymized"))]
    chosen: dict[str, tuple[StudyStat, str]] = {}

    def older(dt: datetime | None, days: int) -> bool:
        return bool(days) and dt is not None and dt < now - timedelta(days=days)

    for s in pool:
        mod = (s.modalities or "").split("\\")[0].upper()
        per_mod = (policy.get("per_modality_days") or {}).get(mod)
        if s.origin == "prefetch" and older(s.date_added, int(policy.get("prefetch_days") or 0)):
            chosen[s.study_uid] = (s, f"anterior da pré-busca há mais de {policy['prefetch_days']} dias")
        elif per_mod and older(s.date_added, int(per_mod)):
            chosen[s.study_uid] = (s, f"{mod}: guardado há mais de {per_mod} dias")
        elif older(s.date_added, int(policy.get("max_age_days") or 0)):
            chosen[s.study_uid] = (s, f"recebido há mais de {policy['max_age_days']} dias")
        elif older(s.last_accessed or s.date_added, int(policy.get("not_opened_days") or 0)):
            chosen[s.study_uid] = (s, f"não aberto há mais de {policy['not_opened_days']} dias")

    # espaço: apaga os menos usados até voltar ao limite baixo
    freed = sum(s.size_bytes for s, _r in chosen.values())
    rest = sorted((s for s in pool if s.study_uid not in chosen),
                  key=lambda s: s.last_accessed or s.date_added)
    max_gb = float(policy.get("max_storage_gb") or 0)
    if max_gb and storage_bytes is not None:
        target = max_gb * 1024 ** 3 * 0.9
        for s in rest:
            if storage_bytes - freed <= target:
                break
            chosen[s.study_uid] = (s, f"armazenamento acima de {max_gb:g} GB")
            freed += s.size_bytes
    high, low = float(policy.get("disk_high_pct") or 0), float(policy.get("disk_low_pct") or 0)
    if high and disk_used_pct is not None and disk_total_bytes and disk_used_pct > high:
        target_bytes = disk_total_bytes * (disk_used_pct - low) / 100.0
        for s in rest:
            if freed >= target_bytes:
                break
            if s.study_uid in chosen:
                continue
            chosen[s.study_uid] = (s, f"disco acima de {high:g}% (menos usados primeiro)")
            freed += s.size_bytes
    return list(chosen.values())
