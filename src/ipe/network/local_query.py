"""Responde a C-FIND / C-MOVE / C-GET com o banco local (este programa como PACS)."""

from __future__ import annotations

from typing import Iterator

from pydicom.dataset import Dataset
from sqlalchemy import and_, func, or_, select

from ipe.db.models import Instance, Patient, Series, Study
from ipe.db.session import Database


def _like(v: str) -> str:
    v = v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return v.replace("*", "%").replace("?", "_")


def _values(ds: Dataset, kw: str) -> list[str]:
    """Valor de filtro (vazio = coringa universal). UIDs podem vir em lista."""
    if kw not in ds:
        return []
    v = ds[kw].value
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)) or type(v).__name__ == "MultiValue":
        return [str(x) for x in v if str(x)]
    return [str(v)]


def _str_cond(col, value: str, upper: bool = True):
    if "*" in value or "?" in value:
        return col.ilike(_like(value), escape="\\")
    return func.upper(col) == value.upper() if upper else col == value


def _date_cond(col, value: str):
    value = value.replace(".", "")
    if "-" in value:
        lo, hi = value.split("-", 1)
        conds = []
        if lo:
            conds.append(col >= lo)
        if hi:
            conds.append(col <= hi)
        return and_(*conds) if conds else None
    return col == value


def dicom_pn(display: str) -> str:
    """"Sobrenome, Nome" (como o banco guarda) -> "Sobrenome^Nome"."""
    if ", " in display:
        last, first = display.split(", ", 1)
        return f"{last}^{first}"
    return display


def _pn_query(v: str) -> str:
    return v.replace("^", ", ") if "^" in v and "*" not in v else v.replace("^", "*")


def find(db: Database, ident: Dataset) -> Iterator[Dataset]:
    level = str(ident.get("QueryRetrieveLevel", "STUDY")).upper()
    with db.session() as s:
        q = (select(Patient, Study).join(Study, Study.patient_fk == Patient.id))
        conds = []
        for v in _values(ident, "PatientName"):
            conds.append(_str_cond(Patient.name, _pn_query(v)))
        for v in _values(ident, "PatientID"):
            conds.append(_str_cond(Patient.patient_id, v, upper=False))
        for v in _values(ident, "PatientBirthDate"):
            c = _date_cond(Patient.birth_date, v)
            if c is not None:
                conds.append(c)
        if level != "PATIENT":
            for v in _values(ident, "StudyDate"):
                c = _date_cond(Study.study_date, v)
                if c is not None:
                    conds.append(c)
            for v in _values(ident, "AccessionNumber"):
                conds.append(_str_cond(Study.accession, v, upper=False))
            for v in _values(ident, "StudyDescription"):
                conds.append(_str_cond(Study.description, v))
            uids = _values(ident, "StudyInstanceUID")
            if uids:
                conds.append(Study.study_uid.in_(uids))
            mods = _values(ident, "ModalitiesInStudy")
            if mods:
                conds.append(or_(*[Study.modalities.ilike(f"%{m}%") for m in mods]))
        if conds:
            q = q.where(and_(*conds))
        rows = list(s.execute(q.order_by(Study.study_date.desc())))
        if level == "PATIENT":
            seen = set()
            for p, _st in rows:
                if p.id in seen:
                    continue
                seen.add(p.id)
                yield _fill(ident, p, None, None, s)
            return
        for p, st in rows:
            if level == "STUDY":
                yield _fill(ident, p, st, None, s)
                continue
            sq = select(Series).where(Series.study_fk == st.id)
            for v in _values(ident, "SeriesInstanceUID"):
                sq = sq.where(Series.series_uid.in_(_values(ident, "SeriesInstanceUID")))
                break
            for v in _values(ident, "Modality"):
                sq = sq.where(func.upper(Series.modality) == v.upper())
            for se in s.scalars(sq.order_by(Series.series_number)):
                if level == "SERIES":
                    yield _fill(ident, p, st, se, s)
                    continue
                iq = select(Instance).where(Instance.series_fk == se.id)
                sops = _values(ident, "SOPInstanceUID")
                if sops:
                    iq = iq.where(Instance.sop_uid.in_(sops))
                for inst in s.scalars(iq.order_by(Instance.instance_number)):
                    out = _fill(ident, p, st, se, s)
                    for kw, val in (("SOPInstanceUID", inst.sop_uid), ("SOPClassUID", inst.sop_class_uid),
                                    ("InstanceNumber", str(inst.instance_number))):
                        if kw in ident:
                            setattr(out, kw, val)
                    yield out


def _fill(ident: Dataset, p, st, se, s) -> Dataset:
    out = Dataset()
    out.QueryRetrieveLevel = ident.get("QueryRetrieveLevel", "STUDY")
    vals = {
        "PatientName": dicom_pn(p.name), "PatientID": p.patient_id, "PatientBirthDate": p.birth_date,
        "PatientSex": p.sex,
    }
    if st is not None:
        n_series = s.scalar(select(func.count(Series.id)).where(Series.study_fk == st.id)) or 0
        n_inst = s.scalar(select(func.count(Instance.id)).join(Series, Instance.series_fk == Series.id)
                          .where(Series.study_fk == st.id)) or 0
        vals.update({
            "StudyInstanceUID": st.study_uid, "StudyDate": st.study_date, "StudyTime": st.study_time,
            "AccessionNumber": st.accession, "StudyDescription": st.description,
            "ModalitiesInStudy": st.modalities.split("\\") if st.modalities else "",
            "ReferringPhysicianName": dicom_pn(st.referring), "InstitutionName": st.institution,
            "NumberOfStudyRelatedSeries": str(n_series), "NumberOfStudyRelatedInstances": str(n_inst),
        })
    if se is not None:
        n = s.scalar(select(func.count(Instance.id)).where(Instance.series_fk == se.id)) or 0
        vals.update({
            "SeriesInstanceUID": se.series_uid, "Modality": se.modality,
            "SeriesNumber": str(se.series_number), "SeriesDescription": se.description,
            "BodyPartExamined": se.body_part, "NumberOfSeriesRelatedInstances": str(n),
        })
    for elem in ident:
        kw = elem.keyword
        if not kw or kw == "QueryRetrieveLevel":
            continue
        if kw in vals:
            setattr(out, kw, vals[kw])
        else:
            setattr(out, kw, elem.value if elem.value not in (None, "") else "")
    for kw in ("StudyInstanceUID", "SeriesInstanceUID"):
        if kw in vals and kw not in out:
            setattr(out, kw, vals[kw])
    return out


def files_for(db: Database, ident: Dataset) -> list[tuple[str, str, str]]:
    """(caminho, SOPClassUID, TransferSyntaxUID) dos arquivos pedidos num C-MOVE/C-GET."""
    level = str(ident.get("QueryRetrieveLevel", "STUDY")).upper()
    with db.session() as s:
        q = (select(Instance.file_path, Instance.sop_class_uid, Instance.transfer_syntax)
             .join(Series, Instance.series_fk == Series.id).join(Study, Series.study_fk == Study.id)
             .join(Patient, Study.patient_fk == Patient.id))
        if level == "PATIENT":
            ids = _values(ident, "PatientID")
            if not ids:
                return []
            q = q.where(Patient.patient_id.in_(ids))
        else:
            st = _values(ident, "StudyInstanceUID")
            if st:
                q = q.where(Study.study_uid.in_(st))
            if level in ("SERIES", "IMAGE"):
                se = _values(ident, "SeriesInstanceUID")
                if se:
                    q = q.where(Series.series_uid.in_(se))
            if level == "IMAGE":
                sops = _values(ident, "SOPInstanceUID")
                if sops:
                    q = q.where(Instance.sop_uid.in_(sops))
            if not st and level != "IMAGE":
                return []
        return [(p, c or "", t or "") for p, c, t in s.execute(q)]
