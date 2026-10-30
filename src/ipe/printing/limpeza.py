"""Limpeza automática da lista de impressões (0.84).

Pedido dele: *"configure a limpeza automática para que eu possa selecionar se quero apenas os que
foram impressos, por data, por modalidade, por origem"*.

Vale para os **trabalhos recebidos** das modalidades (a pasta com as folhas e a linha da lista). O
que **não** é apagado: os filmes montados no compositor (são trabalho de alguém, não fila), o filme
que veio no exame (é do exame) e o exame criado no banco com as folhas (apaga-se pelo banco).

Os critérios se somam (E): mais velho que N dias **e** (se marcado) já impresso **e** (se
preenchida) da modalidade **e** (se escolhida) de uma das origens. Nasce desligada.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
CHAVE = "printing.limpeza"


@dataclass
class Config:
    ligada: bool = False
    dias: int = 30                    # mais velhos que isto (pela chegada)
    so_impressos: bool = True         # só os que já foram enviados
    modalidades: str = ""             # "MG|US" (vazio = qualquer); trabalho sem modalidade não entra
    origens: list = field(default_factory=list)   # ids de origem (vazio = qualquer)

    def to_dict(self) -> dict:
        return {"ligada": self.ligada, "dias": int(self.dias), "so_impressos": self.so_impressos,
                "modalidades": self.modalidades, "origens": list(self.origens)}


def config(settings) -> Config:
    d = (settings.get(CHAVE, {}) if settings is not None else {}) or {}
    known = Config.__dataclass_fields__
    return Config(**{k: v for k, v in d.items() if k in known})


def save(settings, cfg: Config) -> None:
    settings.set(CHAVE, cfg.to_dict())
    settings.save()


def _chegada(r: dict) -> datetime | None:
    v = r.get("received_at")
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19])
    except ValueError:
        return None


def entra(cfg: Config, settings, r: dict, agora: datetime) -> bool:
    """Este trabalho seria apagado pela limpeza?"""
    if (r.get("source") or "scp") != "scp":
        return False
    quando = _chegada(r)
    if quando is None or quando > agora - timedelta(days=max(0, int(cfg.dias))):
        return False
    if cfg.so_impressos and (r.get("status") or "new") != "sent":
        return False
    if cfg.modalidades.strip():
        from ipe.printing.modalidade import combina
        if not combina(cfg.modalidades, r.get("modality", "")):
            return False
    if cfg.origens:
        from ipe.printing import origins as O
        o = O.job_origin(settings, r)
        if o is None or o.id not in cfg.origens:
            return False
    return True


def candidatos(repo, settings, cfg: Config | None = None, agora: datetime | None = None) -> list[dict]:
    cfg = cfg or config(settings)
    agora = agora or datetime.now()
    return [r for r in repo.print_jobs(limit=1_000_000) if entra(cfg, settings, r, agora)]


def limpar(repo, settings, cfg: Config | None = None, agora: datetime | None = None) -> int:
    """Apaga os trabalhos que entram nos critérios. Devolve quantos."""
    n = 0
    for r in candidatos(repo, settings, cfg, agora):
        try:
            if hasattr(repo, "delete_sends"):
                repo.delete_sends("scp", r["id"])
            pasta = repo.delete_print_job(r["id"])
            if pasta:
                shutil.rmtree(pasta, ignore_errors=True)
            n += 1
        except Exception:  # noqa: BLE001 - um trabalho que falha não segura os outros
            log.exception("Limpeza: trabalho %s", r.get("id"))
    return n


def automatica(repo, settings) -> int:
    """Chamada pelo programa (ao abrir e de hora em hora): só age com a limpeza ligada."""
    cfg = config(settings)
    if not cfg.ligada:
        return 0
    n = limpar(repo, settings, cfg)
    if n:
        log.info("Limpeza automática: %d trabalho(s) de impressão apagado(s)", n)
    return n
