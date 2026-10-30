"""Descobrir de quem é um trabalho de impressão.

O padrão não manda paciente nenhum, então sobra o que dá para deduzir: exames que estão no
banco, do mesmo aparelho e do mesmo horário. O programa sugere; quem decide é você.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


def _quando(study) -> datetime | None:
    d = (getattr(study, "study_date", "") or "").strip()
    t = (getattr(study, "study_time", "") or "").strip()
    if len(d) != 8 or not d.isdigit():
        return None
    hora = 0
    minuto = 0
    if len(t) >= 4 and t[:4].isdigit():
        hora, minuto = int(t[:2]), int(t[2:4])
    try:
        return datetime(int(d[:4]), int(d[4:6]), int(d[6:8]), hora, minuto)
    except ValueError:
        return None


def _pedacos(texto: str) -> set[str]:
    return {p for p in re.split(r"[^A-Za-z0-9]+", (texto or "").upper()) if len(p) > 2}


def candidates(repo, job, horas: float = 6.0, limite: int = 6) -> list[dict]:
    """Exames que podem ser deste trabalho, do mais provável para o menos.

    Combina a proximidade do horário com o nome do aparelho (AE de origem × estação/instituição).
    """
    chegada = job.when()
    dia = chegada.strftime("%Y%m%d")
    ontem = (chegada - timedelta(days=1)).strftime("%Y%m%d")
    try:
        estudos = repo.search_studies(date_from=ontem, date_to=dia, limit=400)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao procurar exames para o trabalho de impressão")
        return []
    ae = _pedacos(getattr(job, "calling_ae", ""))
    saida = []
    for e in estudos:
        quando = _quando(e)
        if quando is None:
            continue
        distancia = abs((chegada - quando).total_seconds()) / 3600.0
        if distancia > horas:
            continue
        nota = max(0.0, 1.0 - distancia / horas)          # 1 = mesmo horário
        texto = _pedacos(f"{getattr(e, 'institution', '')} {getattr(e, 'description', '')}")
        try:
            for s in repo.series_for_study(e.study_uid)[:4]:
                meta = repo.series_meta(s.series_uid) or {}
                texto |= _pedacos(str(meta.get("station", "")))
        except Exception:  # noqa: BLE001
            pass
        if ae & texto:
            nota += 0.5                                    # o aparelho bate com o AE de origem
        saida.append({"study_uid": e.study_uid, "patient_name": e.patient_name,
                      "patient_id": e.patient_id, "modalities": e.modalities,
                      "description": e.description, "when": quando, "score": round(nota, 3),
                      "hours": round(distancia, 2)})
    saida.sort(key=lambda c: (-c["score"], c["hours"]))
    return saida[:limite]


def describe(c: dict) -> str:
    quando = c["when"].strftime("%d/%m/%Y %H:%M") if c.get("when") else "sem data"
    return (f"{c.get('patient_name') or '(sem nome)'} · {c.get('modalities', '')} · {quando} · "
            f"{c.get('description', '')}")
