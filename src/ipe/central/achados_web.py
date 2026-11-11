"""0.100.16: revisar os achados de IA pelo navegador — o painel "Achados de IA" do Ipê na aba IA do visualizador web.

Pedido dele (11/11/2026): *"as IAs que precisam de confirmação, como o enfisema — hoje eu não consigo confirmar pelo
web, certo?"* → sim, agora consegue. A mesma tabela (`achado_ia`) e as mesmas regras do Ipê (`ai/achados.py`):

- o achado nasce **sugerido**; o médico **confirma**, **corrige** os números (fica "corrigido" e o laudo leva os
  números dele), **descarta** ou **volta a sugerido**;
- **nada vai ao laudo sem revisão**: o texto do laudo é o mesmo do botão "Mandar ao laudo" do Ipê
  (`central/web.texto_dos_achados`), só com os confirmados e corrigidos;
- revisar é ato médico: precisa da permissão de escrever laudos (`report`); ver, só a de abrir exames.

Cada revisão fica no registro de acesso (ação `ia_revisar`).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PERMISSAO = "report"


def _exame(c, s, study: str) -> None:
    if not s.can("view"):
        raise PermissionError("sem permissão")
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame não visível")


def _modulo(ferramenta: str):
    from ipe.ai import ferramentas as FE
    try:
        return FE.modulo(ferramenta)
    except Exception:  # noqa: BLE001
        return None


def _titulo(ferramenta: str) -> str:
    mod = _modulo(ferramenta)
    return str(getattr(mod, "TITULO", "") or ferramenta)


def _web(a: dict) -> dict:
    from ipe.ai import achados as AC
    mod = _modulo(a.get("ferramenta", ""))
    nums = AC.numeros_validos(a)
    chaves = [k for k in (getattr(mod, "CHAVES", None) or list(nums)) if k in nums]
    campos = []
    for k, d in (a.get("numeros") or {}).items():
        v = d.get("v")
        if isinstance(v, (list, tuple)):
            continue                                    # (eixos de um nódulo: não se corrigem um a um)
        atual = nums.get(k, {}).get("v")
        campos.append({"chave": k, "nome": d.get("n", k), "unidade": d.get("u", ""),
                       "valor": atual if isinstance(atual, (int, float, str)) or atual is None else str(atual),
                       "original": v if isinstance(v, (int, float, str)) or v is None else str(v),
                       "numero": isinstance(v, (int, float)) and not isinstance(v, bool),
                       "corrigido": k in (a.get("corrigidos") or {})})
    resultado = None
    fn = getattr(mod, "resultado_do_achado", None)
    if fn is not None:
        try:
            resultado = fn(a)
        except Exception:  # noqa: BLE001
            log.debug("resultado do achado %s", a.get("id"), exc_info=True)
    pos = a.get("posicao")
    return {"id": a["id"], "ferramenta": a.get("ferramenta", ""), "titulo": _titulo(a.get("ferramenta", "")),
            "rotulo": a.get("rotulo", ""), "tipo": a.get("tipo", ""), "local": a.get("local", ""),
            "estado": a.get("estado", "sugerido"), "cor": AC.CORES.get(a.get("estado", "sugerido"), "#ccc"),
            "medidas": " · ".join(AC._fmt(nums[k]) for k in chaves[:3]),
            "numeros": AC.texto_dos_numeros(a), "campos": campos, "nota": a.get("nota", "") or "",
            "revisao": AC.quem_e_quando(a), "resultado": resultado or "",
            "elegibilidade": a.get("elegibilidade", "") or "",
            "modelo": f"{a.get('modelo', '')} {a.get('versao', '')}".strip(),
            "posicao": [float(x) for x in pos] if pos is not None and len(pos) == 3 else None,
            "series_uid": a.get("series_uid", "") or ""}


def achados(c, s, q: dict) -> dict:
    """Os achados de IA do exame (todos os estados), a contagem e o texto que vai ao laudo."""
    from ipe.ai import achados as AC
    from ipe.central import web as WEB
    study = (q.get("study") or [""])[0]
    _exame(c, s, study)
    lista = c.repo.achados(study)
    return {"achados": [_web(a) for a in lista], "contagem": AC.contagem(lista),
            "texto_laudo": WEB.texto_dos_achados(c.repo, study),
            "pode_revisar": PERMISSAO in (getattr(s, "perms", None) or set())}


def _numero(txt):
    if isinstance(txt, (int, float)) and not isinstance(txt, bool):
        return float(txt)
    t = str(txt or "").strip().replace(",", ".")
    return float(t)


def revisar(c, s, corpo: dict) -> dict:
    """{id, estado} — "confirmado", "descartado", "sugerido"; ou {id, corrigidos: {chave: valor}, nota} para
    corrigir (fica "corrigido" se algum número mudou; senão, "confirmado", como no Ipê)."""
    if PERMISSAO not in (getattr(s, "perms", None) or set()):
        raise PermissionError("seu perfil não permite revisar achados de IA (report)")
    aid = int(corpo.get("id") or 0)
    a = c.repo.achado(aid)
    if a is None:
        raise KeyError(f"achado não encontrado: {aid}")
    _exame(c, s, a.get("study_uid", ""))
    quem = getattr(s, "full_name", "") or s.username
    if "corrigidos" in corpo:
        novos = dict(a.get("corrigidos") or {})
        originais = a.get("numeros") or {}
        for k, v in (corpo.get("corrigidos") or {}).items():
            if k not in originais:
                raise ValueError(f"número desconhecido: {k}")
            orig = originais[k].get("v")
            if isinstance(orig, (int, float)) and not isinstance(orig, bool):
                if v in (None, ""):
                    novos.pop(k, None)
                    continue
                try:
                    x = _numero(v)
                except ValueError as e:
                    raise ValueError(f"{originais[k].get('n', k)}: não é número ({v})") from e
                if abs(x - float(orig)) > 1e-9:
                    novos[k] = x
                else:
                    novos.pop(k, None)
            else:
                t = str(v or "").strip()
                if t and t != str(orig or ""):
                    novos[k] = t
                else:
                    novos.pop(k, None)
        estado = "corrigido" if novos else "confirmado"
        novo = c.repo.revisar_achado(aid, estado, quem, corrigidos=novos, nota=str(corpo.get("nota") or ""))
    else:
        estado = str(corpo.get("estado") or "")
        if estado not in ("confirmado", "descartado", "sugerido"):
            raise ValueError(f"estado desconhecido: {estado}")
        novo = c.repo.revisar_achado(aid, estado, quem)
    try:
        c.repo.audit("ia_revisar", f"{_titulo(a.get('ferramenta', ''))} {a.get('rotulo', '')}: {estado} (navegador)",
                     user=s.username, study_uid=a.get("study_uid", ""))
    except Exception:  # noqa: BLE001
        log.exception("registrar a revisão do achado")
    return {"ok": True, "achado": _web(novo) if novo else None}
