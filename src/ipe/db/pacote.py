"""Pacote dos dados de um exame (0.99.28, etapa 4 do plano do modo de uso).

As imagens viajam como DICOM (STOW/WADO ou cópia de arquivo); o que o programa guarda **no banco** sobre
o exame — laudos, medidas e anotações, imagens-chave, comentários, etiquetas, diagnóstico, grupos de
séries, conferência da IA e alinhamentos com outros exames — viaja neste pacote. Assim "laudos, medidas e
anotações acompanham o exame" (decisão dele) também quando o exame muda de computador ou vai para o
servidor.

Juntar é **sem apagar**: o que já existe no destino fica; entra só o que falta (cada tabela tem a sua
chave natural). Laudo assinado nunca é sobrescrito.

Fora do pacote: lesões acompanhadas (são do paciente, não do exame), listas de casos e filmes.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import or_, select

from ipe.db.models import (
    AchadoIA, AnnotationRecord, Comment, Diagnosis, Instance, KeyImage, Report, RevisaoIA, Series, SeriesGroup,
    Study, StudyRegistration, StudyTag, Tag,
)

log = logging.getLogger(__name__)
VERSAO = 1

# tabela -> (modelo, colunas da chave natural)
TABELAS = {
    "comment": (Comment, ("target_uid", "text", "created_at")),
    "key_image": (KeyImage, ("sop_uid", "frame_index")),
    "annotation": (AnnotationRecord, ("sop_uid", "frame_index", "kind", "data")),
    "report": (Report, ("study_uid", "created_at", "title")),
    "revisao_ia": (RevisaoIA, ("study_uid", "modulo")),
    "achado_ia": (AchadoIA, ("study_uid", "ferramenta", "rotulo", "posicao")),
    "series_group": (SeriesGroup, ("study_uid", "name", "series_uids")),
    "study_registration": (StudyRegistration, ("study_a", "study_b")),
}


def _linha(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name != "id"}


def exportar(db, study_uid: str) -> dict:
    """Tudo o que o banco guarda sobre o exame, sem os ids (que são de cada banco)."""
    with db.session() as s:
        st = s.scalar(select(Study).where(Study.study_uid == study_uid))
        if st is None:
            return {}
        series = list(s.scalars(select(Series.series_uid).where(Series.study_fk == st.id)))
        sops = list(s.scalars(select(Instance.sop_uid).join(Series).where(Series.study_fk == st.id)))
        alvos = [study_uid, *series, *sops]
        p: dict = {"versao": VERSAO, "study_uid": study_uid, "dono": st.dono or "",
                   "visivel_para": st.visivel_para or "", "locked": bool(st.locked)}
        p["comment"] = [_linha(c) for c in s.scalars(select(Comment).where(Comment.target_uid.in_(alvos)))]
        for nome in ("key_image", "annotation", "report", "revisao_ia", "achado_ia", "series_group"):
            modelo = TABELAS[nome][0]
            p[nome] = [_linha(x) for x in s.scalars(select(modelo).where(modelo.study_uid == study_uid))]
        for linha in p["achado_ia"]:
            linha["lesao_id"] = None             # as lesões são do paciente e não viajam com o exame
        p["study_registration"] = [_linha(x) for x in s.scalars(
            select(StudyRegistration).where(or_(StudyRegistration.study_a == study_uid,
                                                StudyRegistration.study_b == study_uid)))]
        d = s.get(Diagnosis, study_uid)
        p["diagnosis"] = _linha(d) | {"study_uid": study_uid} if d is not None else None
        p["tags"] = list(s.scalars(select(Tag.name).join(StudyTag, StudyTag.tag_fk == Tag.id)
                                   .where(StudyTag.study_uid == study_uid)))
    return p


def _chave(valores: dict, cols) -> tuple:
    out = []
    for c in cols:
        v = valores.get(c)
        if isinstance(v, datetime):
            v = v.replace(microsecond=0).isoformat()
        out.append(v)
    return tuple(out)


def importar(db, p: dict, escopo: bool = True) -> dict:
    """Junta o pacote no banco. Devolve {tabela: linhas novas}. `escopo`: aplica dono/visível para."""
    if not p or not p.get("study_uid"):
        return {}
    uid = p["study_uid"]
    novas: dict[str, int] = {}
    with db.session() as s:
        st = s.scalar(select(Study).where(Study.study_uid == uid))
        if escopo and st is not None:
            st.dono, st.visivel_para = p.get("dono", "") or "", p.get("visivel_para", "") or ""
            st.locked = bool(st.locked or p.get("locked"))
        for nome, (modelo, cols) in TABELAS.items():
            linhas = p.get(nome) or []
            if not linhas:
                continue
            existentes = set()
            if nome == "comment":
                alvos = {x.get("target_uid") for x in linhas}
                q = select(modelo).where(modelo.target_uid.in_(list(alvos)))
            elif nome == "study_registration":
                q = select(modelo).where(or_(modelo.study_a == uid, modelo.study_b == uid))
            elif nome in ("key_image", "annotation"):
                q = select(modelo).where(modelo.sop_uid.in_([x.get("sop_uid") for x in linhas]))
            else:
                q = select(modelo).where(modelo.study_uid == uid)
            for x in s.scalars(q):
                existentes.add(_chave(_linha(x), cols))
            colunas = {c.name for c in modelo.__table__.columns} - {"id"}
            n = 0
            for x in linhas:
                k = _chave(x, cols)
                if k in existentes:
                    continue
                s.add(modelo(**{c: v for c, v in x.items() if c in colunas}))
                existentes.add(k)
                n += 1
            if n:
                novas[nome] = n
        d = p.get("diagnosis")
        if d:
            atual = s.get(Diagnosis, uid)
            if atual is None:
                s.add(Diagnosis(**{k: v for k, v in d.items() if k in {c.name for c in Diagnosis.__table__.columns}}))
                novas["diagnosis"] = 1
            else:                                 # completa só o que estiver vazio
                for k in ("final_dx", "pathology", "follow_up", "teaching_points"):
                    if not getattr(atual, k) and d.get(k):
                        setattr(atual, k, d[k])
        for nome in p.get("tags") or []:
            tag = s.scalar(select(Tag).where(Tag.name == nome))
            if tag is None:
                tag = Tag(name=nome)
                s.add(tag)
                s.flush()
            if s.get(StudyTag, (uid, tag.id)) is None:
                s.add(StudyTag(study_uid=uid, tag_fk=tag.id))
                novas["tags"] = novas.get("tags", 0) + 1
    if novas:
        log.info("dados do exame %s juntados: %s", uid, novas)
    return novas
