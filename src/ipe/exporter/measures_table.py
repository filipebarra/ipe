"""Tabela das medidas do exame para planilha (CSV que o Excel abre direto).

Uma linha por medida: paciente, exame, série, imagem, tipo, valores e a lesão ligada (se houver).
"""

from __future__ import annotations

import csv
import json
import logging

from ipe.imaging import measure as M

log = logging.getLogger(__name__)

COLUMNS = ["Paciente", "ID", "Data do exame", "Exame", "Série", "Descrição da série", "Modalidade",
           "Imagem", "Medida", "Valor 1", "Valor 2", "Valor 3", "Unidade", "Lesão", "Texto", "Quando"]


def rows_for_studies(repo, study_uids: list[str], anonymize: bool = False) -> list[list]:
    from ipe.reporting.fill import _spacings, fmt_date
    out: list[list] = []
    for study_uid in study_uids:
        info = repo.study_info(study_uid) or {}
        series = {s.series_uid: s for s in repo.series_for_study(study_uid)}
        recs = [r for r in repo.annotations_for_studies([study_uid])]
        spac = _spacings(repo, sorted({r["sop_uid"] for r in recs}))
        order = {}
        for s_uid in series:
            for i, inst in enumerate(repo.instances_for_series(s_uid), 1):
                order[inst["sop_uid"]] = i
        for r in recs:
            a = M.Annotation.from_record(r)
            s = series.get(a.series_uid)
            mod = s.modality if s is not None else ""
            unit = "mm"
            try:
                labs = M.labels(a, None, spac.get(a.frame_key[0]), mod)
            except Exception:  # noqa: BLE001
                labs = []
            if a.kind == "seg":
                labs = M.labels(a, None, None, mod)
            vals = (labs + ["", "", ""])[:3]
            if a.kind in ("angle", "cobb"):
                unit = "graus"
            elif a.kind in M.ROI_KINDS:
                unit = "mm² / valor do pixel"
            elif a.kind == "seg":
                unit = "mL"
            elif a.kind in ("text", "arrow", "probe"):
                unit = ""
            try:
                extra = json.loads(r.get("data") or "{}")
            except ValueError:
                extra = {}
            meta = extra.get("meta") or {}
            out.append([
                "" if anonymize else info.get("patient_name", ""),
                "" if anonymize else info.get("patient_id", ""),
                fmt_date(info.get("study_date", "")),
                info.get("description", ""),
                s.series_number if s is not None else "",
                s.description if s is not None else "",
                mod,
                order.get(a.frame_key[0], "") if a.frame_key[1] == 0 else
                f"{order.get(a.frame_key[0], '')} (quadro {a.frame_key[1] + 1})",
                M.KINDS.get(a.kind, a.kind),
                *vals,
                unit,
                meta.get("lesion_name", ""),
                (a.text or "").replace("\n", " "),
                "",
            ])
    return out


def write_csv(path, rows: list[list]) -> int:
    """CSV em UTF-8 com BOM e ponto e vírgula (o Excel em português abre com um duplo clique)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow(r)
    return len(rows)


def export_measures(repo, study_uids: list[str], path, anonymize: bool = False) -> int:
    return write_csv(path, rows_for_studies(repo, study_uids, anonymize))
