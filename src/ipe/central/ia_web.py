"""0.100.10: pedir CAD/IA pelo visualizador web e acompanhar.

A IA roda **no servidor**, pela mesma fila do automático da chegada (`AutomationEngine`): uma por vez, com a janela
"Tarefas de IA" do Ipê mostrando as mesmas tarefas. O navegador lista as ferramentas que servem para o exame (com a
série que cada uma usaria, ou por que não serve), pede uma (com a série sugerida ou outra) e acompanha as tarefas
do exame — as pedidas por ele e as automáticas — com a etapa, e cancela as dele.

Só para quem tem a permissão de pedir CAD/IA (`ai`).
"""
from __future__ import annotations

import time

PERMISSAO = "ai"


def _exigir(s) -> None:
    if PERMISSAO not in (getattr(s, "perms", None) or set()):
        raise PermissionError("seu perfil não permite pedir CAD/IA (ai)")


def _motor(c):
    eng = getattr(c, "auto", None)
    if eng is None:
        raise RuntimeError("este servidor não tem a fila de IA ligada")
    return eng


def _estudo(c, s, study: str) -> str:
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame fora do seu acesso")
    return study


def ferramentas(c, s, q: dict) -> dict:
    from ipe.ai import totalseg as TS
    _exigir(s)
    eng = _motor(c)
    study = _estudo(c, s, (q.get("study") or [""])[0])
    lista = eng.ferramentas_do_exame(study)
    descr = {x.series_uid: f"{x.series_number or '–'} · {x.modality} · {x.description or ''}"
             for x in c.repo.series_for_study(study)}
    for f in lista:
        f["serie_rotulo"] = descr.get(f["serie"] or "", "")
    instalado = bool(getattr(eng, "_seg_simular", False) or TS.instalado(eng.settings))
    return {"ferramentas": lista, "instalado": instalado}


def _tarefa(t, s) -> dict:
    from ipe.ai import tarefas as TA
    agora = time.time()
    dur = ((t.fim or agora) - t.inicio) if t.inicio else 0.0
    minha = t.origem == f"manual · {s.username}"
    return {"id": t.id, "ferramenta": t.ferramenta, "estado": t.estado, "rotulo": TA.ROTULO.get(t.estado, t.estado),
            "etapa": t.etapa, "mensagem": t.mensagem, "origem": t.origem, "segundos": round(dur),
            "ativa": t.ativa, "pode_cancelar": t.ativa and (minha or "configure" in (s.perms or set()))}


def tarefas(c, s, q: dict) -> dict:
    from ipe.ai import tarefas as TA
    _exigir(s)
    study = _estudo(c, s, (q.get("study") or [""])[0])
    TA.REGISTRO.conferir()
    return {"tarefas": [_tarefa(t, s) for t in TA.REGISTRO.tarefas() if t.study_uid == study][:30]}


def pedir(c, s, corpo: dict) -> dict:
    _exigir(s)
    eng = _motor(c)
    study = _estudo(c, s, str(corpo.get("study") or ""))
    tipo = str(corpo.get("tipo") or "")
    serie = str(corpo.get("serie") or "") or None
    if serie and serie not in {x.series_uid for x in c.repo.series_for_study(study)}:
        raise ValueError("série de outro exame")
    tid = c.ponte.chamar(lambda: eng.pedir(study, tipo, serie, s.username))
    c.repo.audit("ia", f"{tipo} pedida pelo navegador", user=s.username, study_uid=study)
    return {"ok": True, "tarefa": tid}


def cancelar(c, s, corpo: dict) -> dict:
    from ipe.ai import tarefas as TA
    _exigir(s)
    tid = int(corpo.get("id") or 0)
    t = next((x for x in TA.REGISTRO.tarefas() if x.id == tid), None)
    if t is None or not c.pode_ver(s, t.study_uid):
        raise KeyError("tarefa não encontrada")
    if not _tarefa(t, s)["pode_cancelar"]:
        raise PermissionError("só quem pediu (ou quem configura) cancela esta tarefa")
    return {"ok": bool(c.ponte.chamar(lambda: TA.REGISTRO.cancelar(tid)))}
