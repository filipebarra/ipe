"""0.100.51: calcificações vasculares da mama no Ipê Web — o mesmo botão do Ipê de mesa.

Medir é medir no servidor (a SCU-Net nas quatro incidências 2D do exame, `ai/calc_vascular.py`), guardado em
`revisao_ia` (módulo "calc_vascular"); confirmar o grau (ausente, leve, moderada, acentuada) pede a permissão de
escrever laudos. As prévias (as incidências com o que a rede marcou em vermelho) são PNG desenhados no servidor.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

_TRAVAS: dict[str, threading.Lock] = {}
_TRAVA = threading.Lock()
CAMPOS = ("sugestao", "area_mm2", "por_mama", "aviso", "avisos", "aparelho", "quando", "grau", "estado", "revisor",
          "confirmado_em", "cortes")


def _exame(c, s, study: str) -> None:
    if not s.can("view"):
        raise PermissionError("sem permissão")
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame não visível")


def _saida(m: dict | None, s) -> dict:
    from ipe.ai import calc_vascular as C
    if not m:
        return {"medida": None, "pode_confirmar": s.can("report")}
    out = {k: m.get(k) for k in CAMPOS}
    out["avisos"] = list(out.get("avisos") or [])
    out["escalas"] = m["escalas"] if "escalas" in m else C.escalas(m)  # 0.100.55
    imgs = C.imagens_guardadas(m)
    # 0.100.52: todas as imagens 2D (o navegador rola entre as da mesma incidência); a máscara fica no servidor
    out["imagens"] = [{"i": i, "chave": v["chave"], "area_mm2": v.get("area_mm2"), "extra": bool(v.get("extra")),
                       "modificadores": v.get("modificadores") or [], "serie": v.get("serie", ""),
                       "protese": bool(v.get("protese"))} for i, v in enumerate(imgs)]
    sops = {k: (v or {}).get("sop") for k, v in (m.get("vistas") or {}).items()}
    out["vistas"] = {}
    for i, v in enumerate(imgs):
        if v["chave"] not in out["vistas"] or (sops.get(v["chave"]) and v.get("sop") == sops[v["chave"]]):
            out["vistas"][v["chave"]] = i
    return {"medida": out, "pode_confirmar": s.can("report"), "frases": {g: C.frase_do_laudo(g) for g in C.GRAUS}}


def ver(c, s, study: str) -> dict:
    from ipe.ai import calc_vascular as C
    _exame(c, s, study)
    return _saida(C.guardada(c.repo, study), s)


def medir(c, s, study: str, de_novo: bool = False) -> dict:
    from ipe.ai import calc_vascular as C
    _exame(c, s, study)
    with _TRAVA:
        trava = _TRAVAS.setdefault(study, threading.Lock())
    with trava:
        if not de_novo:
            g = C.guardada(c.repo, study)
            if g:
                return _saida(g, s)
        m = C.medir_exame(c.repo, study)
        if m.get("imagens"):
            C.guardar_medida(c.repo, study, m)
        c.repo.audit("calc_vascular", f"medida pelo navegador: {m.get('sugestao') or '—'}", user=s.username,
                     study_uid=study)
        return _saida(C.guardada(c.repo, study) or m, s)


def confirmar(c, s, study: str, grau: str) -> dict:
    from ipe.ai import calc_vascular as C
    _exame(c, s, study)
    if not s.can("report"):
        raise PermissionError("confirmar pede a permissão de escrever laudos")
    m = C.guardada(c.repo, study)
    if not m:
        raise ValueError("o exame ainda não foi medido")
    C.confirmar(c.repo, study, m, str(grau or "").lower(), s.username)
    c.repo.audit("calc_vascular", f"confirmada pelo navegador: {grau}", user=s.username, study_uid=study)
    from ipe.central.densidade_web import gravar_sr
    gravar_sr(c, s, study)                        # 0.100.57: tudo confirmado → o SR no exame
    return _saida(C.guardada(c.repo, study), s)


def previa(c, s, study: str, indice: int) -> bytes:
    """A imagem `indice` da medida (a ordem de `imagens`), com o que a rede marcou."""
    import pydicom

    from ipe.ai import calc_vascular as C
    _exame(c, s, study)
    m = C.guardada(c.repo, study)
    imgs = C.imagens_guardadas(m or {})
    if not 0 <= indice < len(imgs):
        raise KeyError(f"sem a imagem {indice}")
    cam = C.arquivo_da_imagem(c.repo, study, imgs[indice])
    if not cam:
        raise KeyError(f"sem a imagem {indice}")
    return C.previa_png(pydicom.dcmread(cam, force=True), imgs[indice], 420)

