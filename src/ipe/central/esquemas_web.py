"""0.100.72: os esquemas-guia do laudo no Ipê Web — os modelos, os esquemas do exame (ler e gravar), a figura
pronta e a ligação de uma marca a uma imagem do exame. As regras são as do laudo: ver o exame para ler; a
permissão de escrever laudos (`report`) para gravar. O desenho na tela é do navegador (canvas), com os mesmos
dados que o Ipê de mesa usa; a figura do PDF e do DICOM é sempre a do servidor (`reporting/esquemas.py`).
"""
from __future__ import annotations

import logging

from ipe.reporting import esquemas as E

log = logging.getLogger(__name__)


def _um(q: dict, k: str, padrao: str = "") -> str:
    return str((q.get(k) or [padrao])[0])


def _exame(c, s, study: str) -> str:
    if not s.can("view"):
        raise PermissionError("sem permissão")
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame não visível")
    if not c.repo.study_info(study):
        raise LookupError("exame desconhecido")
    return study


def modelos(c, s) -> dict:
    """Os modelos com os traços (a imagem dos modelos próprios vem por `fundo`)."""
    if not s.can("view"):
        raise PermissionError("sem permissão")
    return {"modelos": [{k: v for k, v in m.items() if k != "png"} for m in E.modelos(c.repo)], "cores": E.CORES}


def fundo(c, s, q: dict) -> bytes:
    import base64
    if not s.can("view"):
        raise PermissionError("sem permissão")
    m = E.modelo(_um(q, "id"), c.repo)
    if m is None or not m.get("png"):
        raise LookupError("modelo sem imagem")
    return base64.b64decode(m["png"])


def do_exame(c, s, q: dict) -> dict:
    study = _exame(c, s, _um(q, "study"))
    return {"esquemas": E.ler(c.repo, study), "pode": bool(s.can("report")),
            "legenda": E.texto_para_o_laudo(E.ler(c.repo, study), c.repo)}


def gravar(c, s, d: dict, host: str = "") -> dict:
    study = _exame(c, s, str(d.get("study") or ""))
    if not s.can("report"):
        raise PermissionError("seu perfil não permite escrever laudos")
    if not isinstance(d.get("esquemas"), list):
        raise ValueError("Faltaram os esquemas.")
    ficou = E.gravar(c.repo, study, d["esquemas"], s.username)
    try:
        c.repo.audit("esquema", "esquemas do laudo: " + str(len(ficou)), user=s.username, study_uid=study, host=host)
    except Exception:  # noqa: BLE001
        log.debug("esquemas: registro", exc_info=True)
    return {"ok": True, "esquemas": ficou, "legenda": E.texto_para_o_laudo(ficou, c.repo)}


def figura(c, s, q: dict) -> bytes:
    """A figura como vai para o PDF e para o DICOM (PNG)."""
    study = _exame(c, s, _um(q, "study"))
    e = next((x for x in E.ler(c.repo, study) if x.get("id") == _um(q, "id")), None)
    if e is None:
        raise LookupError("esquema desconhecido")
    try:
        larg = max(200, min(2000, int(_um(q, "w", "1100"))))
    except ValueError:
        larg = 1100
    return E.png(e, larg, c.repo)


def ligar(c, s, d: dict) -> dict:
    """Liga uma marca à imagem que está aberta: ela vira imagem-chave e devolve o rótulo ("série 3, imagem 12")."""
    study = _exame(c, s, str(d.get("study") or ""))
    if not s.can("report"):
        raise PermissionError("seu perfil não permite escrever laudos")
    r = E.ligar_imagem(c.repo, study, str(d.get("series_uid") or ""), str(d.get("sop_uid") or ""),
                       int(d.get("frame") or 0))
    if r is None:
        raise LookupError("a imagem não é deste exame")
    return {"ok": True, "imagem": r}


def rota(c, s, method: str, acao: str, query: dict, corpo: dict, host: str = ""):
    """Devolve um dict (JSON) ou bytes (PNG)."""
    if method == "GET":
        if acao == "modelos":
            return modelos(c, s)
        if acao == "exame":
            return do_exame(c, s, query)
        if acao == "fundo":
            return fundo(c, s, query)
        if acao == "figura":
            return figura(c, s, query)
    elif method == "POST":
        if acao == "exame":
            return gravar(c, s, corpo, host)
        if acao == "ligar":
            return ligar(c, s, corpo)
    raise LookupError("rota")
