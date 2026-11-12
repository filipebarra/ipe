"""0.100.20: a lista de exames do navegador — a situação de cada exame (laudo, IA) e a prévia do exame selecionado.

Desenhos aprovados por ele (11/11/2026): *lista em duas partes* (exames à esquerda; à direita, o exame selecionado com
as séries, a IA, o laudo e os anteriores, antes de abrir) e *filtros rápidos* (período, modalidade, situação).

- `situacoes`: para os exames da lista, o estado do laudo ("", "draft", "final"), se há achados de IA e quantos
  esperam revisão — os filtros "Sem laudo", "Rascunho", "Assinado" e "Com IA para revisar" e o selo IA saem daqui;
- `previa`: o exame selecionado — paciente, séries (com miniatura e selo IA), IA (ferramentas e achados por estado),
  laudo (estado, data e o começo do texto) e os exames anteriores do paciente.

Só para quem pode abrir o exame; o texto do laudo só para quem pode ver exames (a mesma regra do laudo web).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MAX_ESTUDOS = 600
NAO_MOSTRA = {"SR", "KO", "PR", "DOC", "RTSTRUCT", "RTPLAN", "SEG", "REG", "OT_PDF"}


def situacoes(c, s, corpo: dict) -> dict:
    from sqlalchemy import func, select

    from ipe.db.models import AchadoIA
    if not s.can("view"):
        raise PermissionError("sem permissão")
    uids = [str(u) for u in (corpo.get("studies") or [])][:MAX_ESTUDOS]
    uids = [u for u in uids if c.pode_ver(s, u)]
    laudos = c.repo.report_counts(uids)
    ia: dict[str, dict] = {}
    if uids:
        with c.repo.db.session() as ss:
            for uid, estado, n in ss.execute(select(AchadoIA.study_uid, AchadoIA.estado, func.count(AchadoIA.id))
                                             .where(AchadoIA.study_uid.in_(uids))
                                             .group_by(AchadoIA.study_uid, AchadoIA.estado)):
                d = ia.setdefault(uid, {"achados": 0, "revisar": 0})
                d["achados"] += int(n)
                if estado == "sugerido":
                    d["revisar"] += int(n)
    return {"estudos": {u: {"laudo": laudos.get(u, ""), "achados": ia.get(u, {}).get("achados", 0),
                            "revisar": ia.get(u, {}).get("revisar", 0)} for u in uids}}


def previa(c, s, q: dict) -> dict:
    from ipe.ai import achados as AC
    from ipe.ai import series_ia as SIA
    if not s.can("view"):
        raise PermissionError("sem permissão")
    study = (q.get("study") or [""])[0]
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame não visível")
    info = c.repo.study_info(study)
    if info is None:
        raise KeyError("exame não encontrado")
    todas = list(c.repo.series_for_study(study, ocultas=True))
    com_ia = SIA.series_com_ia(c.repo, study, todas)
    series = [{"uid": r.series_uid, "numero": r.series_number, "modalidade": r.modality or "",
               "descricao": r.description or "", "imagens": int(r.num_images or 0), "ia": r.series_uid in com_ia}
              for r in c.repo.series_for_study(study) if (r.modality or "").upper() not in NAO_MOSTRA]
    ferramentas = sorted({f for d in com_ia.values() for f in d["ferramentas"]})
    ach = c.repo.achados(study)
    laudo = None
    reps = c.repo.reports(study)
    if reps:
        r = next((x for x in reversed(reps) if x["status"] != "draft"), reps[-1])
        texto = " ".join((r.get("text") or "").split())
        laudo = {"estado": r["status"], "quando": r.get("signed_at") or r.get("updated_at") or "",
                 "quem": r.get("signed_by") or r.get("author") or "", "trecho": texto[:220] + ("…" if len(texto) > 220 else "")}
    anteriores = []
    try:
        for o in c.repo.other_studies_same_patient(study):
            if c.pode_ver(s, o.study_uid):
                anteriores.append({"uid": o.study_uid, "data": o.study_date or "", "descricao": o.description or "",
                                   "modalidades": o.modalities or ""})
    except Exception:  # noqa: BLE001
        log.exception("anteriores do exame %s", study)
    anteriores.sort(key=lambda x: x["data"], reverse=True)
    return {"study": study, "paciente": info["patient_name"], "id": info["patient_id"], "idade": info.get("patient_age") or "",
            "sexo": info.get("sex") or "", "data": info.get("study_date") or "", "descricao": info.get("description") or "",
            "acesso": info.get("accession") or "", "series": series,
            "ia": {"ferramentas": ferramentas, "contagem": AC.contagem(ach) if ach else {}},
            "laudo": laudo, "anteriores": anteriores[:12]}
