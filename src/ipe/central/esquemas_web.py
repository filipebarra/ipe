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


MAX_IMAGEM = 12 * 1024 * 1024                          # a imagem de um modelo, como chega do navegador


def _sem_png(m: dict) -> dict:
    return {**{k: v for k, v in m.items() if k != "png"}, "imagem": bool(m.get("png"))}


def modelos(c, s, q: dict | None = None) -> dict:
    """Os modelos com os traços (a imagem dos modelos próprios vem por `fundo`). Os ocultos vêm sempre (um esquema
    antigo pode usar um): a tela de escolher não os mostra; `pode_modelos` = pode cadastrar e mudar modelos."""
    if not s.can("view"):
        raise PermissionError("sem permissão")
    return {"modelos": [_sem_png(m) for m in E.modelos(c.repo, ocultos=True)], "cores": E.CORES,
            "pode_modelos": bool(s.can("configure"))}


def modelo_gravar(c, s, d: dict, host: str = "") -> dict:
    """0.100.73: cadastra ou muda um modelo pelo navegador (`imagem` = o arquivo em base64, se houver)."""
    import base64
    import binascii
    if not s.can("configure"):
        raise PermissionError("cadastrar e mudar modelos de esquema pede a permissão de configurar")
    dados = None
    if d.get("imagem"):
        txt = str(d["imagem"])
        if len(txt) > MAX_IMAGEM * 4 // 3 + 64:
            raise ValueError("A imagem é grande demais (mais de 12 MB).")
        try:
            dados = base64.b64decode(txt.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Não consegui ler a imagem (use PNG ou JPG).") from None
    m = E.salvar_modelo(c.repo, d, dados)
    try:
        c.repo.audit("config", "modelo de esquema: " + m["nome"], user=s.username, host=host)
    except Exception:  # noqa: BLE001
        log.debug("esquemas: registro", exc_info=True)
    return {"ok": True, "modelo": _sem_png(m)}


def modelo_excluir(c, s, d: dict, host: str = "") -> dict:
    if not s.can("configure"):
        raise PermissionError("cadastrar e mudar modelos de esquema pede a permissão de configurar")
    r = E.excluir_modelo(c.repo, str(d.get("id") or ""))
    if not r:
        raise LookupError("modelo desconhecido")
    try:
        c.repo.audit("config", "modelo de esquema " + r + ": " + str(d.get("id")), user=s.username, host=host)
    except Exception:  # noqa: BLE001
        log.debug("esquemas: registro", exc_info=True)
    return {"ok": True, "o_que": r}


def no_exame(c, s, d: dict, host: str = "") -> dict:
    """0.100.73: grava os esquemas no exame agora (figuras e SR), sem laudo assinado."""
    from ipe.reporting import esquemas_saida as ES
    study = _exame(c, s, str(d.get("study") or ""))
    if not s.can("report"):
        raise PermissionError("seu perfil não permite escrever laudos")
    r = ES.gravar_no_exame(c.repo, c.storage, study, getattr(s, "full_name", "") or s.username)
    try:
        c.repo.audit("esquema", "gravou no exame: " + str(r["imagens"]) + " figura(s) e o SR", user=s.username,
                     study_uid=study, host=host)
    except Exception:  # noqa: BLE001
        log.debug("esquemas: registro", exc_info=True)
    return {"ok": True, "imagens": r["imagens"]}


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
    lista = E.ler(c.repo, study)
    return {"esquemas": lista, "pode": bool(s.can("report")), "legenda": E.texto_para_o_laudo(lista, c.repo),
            "no_laudo": E.no_laudo(c.repo, study),          # 0.100.74: o médico pôs os esquemas no laudo?
            "com_desenho": sum(1 for e in lista if not E.vazio(e) and E.modelo(e.get("modelo", ""), c.repo))}


def no_laudo(c, s, d: dict, host: str = "") -> dict:
    """0.100.74: liga ou desliga "os esquemas entram no laudo" (figuras no PDF, esquemas no SR ao assinar)."""
    study = _exame(c, s, str(d.get("study") or ""))
    if not s.can("report"):
        raise PermissionError("seu perfil não permite escrever laudos")
    sim = E.por_no_laudo(c.repo, study, bool(d.get("sim")), s.username)
    return {"ok": True, "no_laudo": sim, "legenda": E.texto_para_o_laudo(E.ler(c.repo, study), c.repo) if sim else ""}


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
        if acao == "no_exame":
            return no_exame(c, s, corpo, host)
        if acao == "no_laudo":
            return no_laudo(c, s, corpo, host)
        if acao == "modelo":
            return modelo_gravar(c, s, corpo, host)
        if acao == "modelo_excluir":
            return modelo_excluir(c, s, corpo, host)
    raise LookupError("rota")
