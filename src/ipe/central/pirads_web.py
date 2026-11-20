"""0.100.79: o PI-RADS no Ipê Web — ler, calcular (sem gravar, para a tela mostrar a categoria enquanto o médico
preenche), gravar, gravar no exame (SR e mapa) e o texto do laudo. As contas são sempre as do servidor
(`reporting/pirads.py`), as mesmas do Ipê de mesa. Ler pede ver o exame; gravar, a permissão de escrever laudos.
"""
from __future__ import annotations

import logging

from ipe.reporting import pirads as P

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


def _pode(s) -> None:
    if not s.can("report"):
        raise PermissionError("seu perfil não permite escrever laudos")


def _resposta(c, study: str, estado: dict, s) -> dict:
    calc = P.calcular(estado)
    return {"estado": calc, "texto": P.texto_laudo(calc), "achados": P.texto_achados(calc),
            "impressao": P.texto_impressao(calc), "pode": bool(s.can("report")), "esquema": P.esquema(calc)}


def ver(c, s, q: dict) -> dict:
    study = _exame(c, s, _um(q, "study"))
    d = P.ler(c.repo, study) or P.normalizar({})
    out = _resposta(c, study, d, s)
    out.update({"setores": P.setores(), "zonas": P.ZONAS, "categorias": P.CATEGORIAS, "cores": P.CORES,
                "dce": P.DCE, "epe": P.EPE, "marca_pesquisa": P.MARCA_PESQUISA})
    return out


def _com_imagens(c, study: str, estado: dict) -> dict:
    """A imagem ligada que chegou só com os UIDs ganha o rótulo (e vira imagem-chave), como no esquema."""
    from ipe.reporting import esquemas as E
    for l in estado.get("lesoes") or []:
        im = l.get("imagem") if isinstance(l, dict) else None
        if isinstance(im, dict) and im.get("sop_uid") and not im.get("rotulo"):
            l["imagem"] = E.ligar_imagem(c.repo, study, str(im.get("series_uid") or ""), str(im["sop_uid"]),
                                         int(im.get("frame") or 0))
    return estado


def calcular(c, s, d: dict) -> dict:
    study = _exame(c, s, str(d.get("study") or ""))
    return _resposta(c, study, P.normalizar(d.get("estado") or {}), s)


def gravar(c, s, d: dict, host: str = "") -> dict:
    study = _exame(c, s, str(d.get("study") or ""))
    _pode(s)
    estado = _com_imagens(c, study, dict(d.get("estado") or {}))
    calc = P.gravar(c.repo, study, estado, s.username)
    try:
        c.repo.audit("laudo", f"PI-RADS gravado (geral {calc['geral'] or '—'})", user=s.username, study_uid=study,
                     host=host)
    except Exception:  # noqa: BLE001
        log.debug("pirads: registro", exc_info=True)
    return _resposta(c, study, calc, s)


def no_exame(c, s, d: dict, host: str = "") -> dict:
    from ipe.reporting import pirads_saida as PS
    study = _exame(c, s, str(d.get("study") or ""))
    _pode(s)
    r = PS.gravar_no_exame(c.repo, c.storage, study, getattr(s, "full_name", "") or s.username)
    try:
        c.repo.audit("laudo", "PI-RADS gravado no exame (SR e mapa)", user=s.username, study_uid=study, host=host)
    except Exception:  # noqa: BLE001
        log.debug("pirads: registro", exc_info=True)
    return {"ok": True, **r}


def rota(c, s, method: str, acao: str, query: dict, corpo: dict, host: str = "") -> dict:
    if method == "GET" and acao == "estado":
        return ver(c, s, query)
    if method == "POST":
        if acao == "calcular":
            return calcular(c, s, corpo)
        if acao == "gravar":
            return gravar(c, s, corpo, host)
        if acao == "no_exame":
            return no_exame(c, s, corpo, host)
    raise LookupError("rota")
