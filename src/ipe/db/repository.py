"""Consultas usadas pela interface (browser, viewer, banco de casos)."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import String, case, func, or_, select
from sqlalchemy.orm import selectinload

from ipe.db.models import (
    AeIdentity, AnnotationRecord, AuditLog, AutomationRule, CaseList, DeletionLog, Diagnosis, JobRun, CaseListItem, Comment, Instance, KeyImage, Patient, Series, Study,
    DicomNode, PrintJobRecord, PrintSendRecord, SavedFilm, SeriesGroup, StudyRegistration, User, AppSetting, Lesion, LesionTrack, Report,
    RevisaoIA, AchadoIA, BuscaAtiva,
)
from ipe.db.session import Database

_ITEM_FIELDS = {"friendly_name", "clinical_summary", "hidden_diagnosis", "note", "tags", "show_series", "position"}


def _item_value(key: str, value):
    if key in ("tags", "show_series") and isinstance(value, (list, tuple, set)):
        return ",".join(str(v).strip().replace(",", " ") for v in value if str(v).strip())
    return value

log = logging.getLogger(__name__)


def comment_summary(texts: list[str]) -> str:
    """Coluna "Comentário": o mais recente e, se houver mais, quantos."""
    if not texts:
        return ""
    last = (texts[-1] or "").replace("\n", " ").strip()[:120]
    return last + (f"  (+{len(texts) - 1})" if len(texts) > 1 else "")


@dataclass
class StudyRow:
    """Linha plana para a tabela do browser (evita objetos ORM na interface)."""
    study_uid: str
    patient_name: str
    patient_id: str
    birth_date: str
    sex: str
    study_date: str
    modalities: str
    description: str
    accession: str
    num_series: int
    num_images: int
    unread: bool
    has_comment: bool
    # colunas opcionais do banco de dados
    study_time: str = ""
    patient_age: str = ""
    institution: str = ""
    referring: str = ""
    origin: str = ""
    date_added: str = ""          # AAAAMMDDHHMM
    last_accessed: str = ""
    locked: bool = False
    size_mb: float = 0.0
    key_images: int = 0
    measured: int = 0             # imagens com medida
    lists: str = ""               # nomes das listas de casos
    comment: str = ""             # 1º comentário
    body_part: str = ""
    num_groups: int = 0           # dinâmicas agrupadas
    operators: str = ""           # (0008,1070) de todas as séries
    station: str = ""
    device: str = ""
    report: str = ""              # laudo: "", "rascunho", "assinado", "retificado"
    has_film: bool = False        # tem filme salvo no compositor
    dono: str = ""                # 0.99.27: "" = compartilhado; usuário = banco pessoal dele
    visivel_para: str = ""
    ia: str = ""                  # 0.99.32: aplicações de IA já feitas no exame ("órgãos abdominais, coluna")
    birads: str = ""              # 0.99.51: categoria final do laudo BI-RADS assinado
    densidade: str = ""           # composição (ACR a–d) do mesmo laudo
    busca: str = ""               # estado da busca ativa do exame
    prioridade: str = ""          # 0.99.52 (onda B4): rotina, urgente, emergencia
    subesp: str = ""              # subespecialidade
    prazo: str = ""               # prazo do laudo, AAAAMMDDHHMM
    sla: str = ""                 # "faltam 5 h", "atrasado 2 h", "no prazo"
    sla_estado: str = ""          # ok, atencao, atrasado, no_prazo, fora_do_prazo


@dataclass
class SeriesRow:
    series_uid: str
    study_uid: str
    modality: str
    series_number: int
    description: str
    num_images: int
    thumbnail: bytes | None
    hidden: bool = False
    body_part: str = ""          # (0018,0015) BodyPartExamined — a região, para a barra do visualizador (0.99.12)


#: modelos de fábrica que chegaram depois da marca "report_templates_vistos" (0.99.31): quem já tinha a
#: lista gravada recebe só estes; os de antes, que ele tenha apagado, não voltam
MODELOS_NOVOS = frozenset({"rx_oit"})


def _filtro_de_banco(q, banco: str, visao):
    """A parte do filtro de banco que o SQL resolve (o resto, exato, em `_no_banco`)."""
    if visao is None or banco == "todos":
        return q
    eu = visao.usuario.lower()
    if banco == "meu":
        return q.where(func.lower(Study.dono) == eu)
    if banco == "compartilhado":
        return q.where(Study.dono == "")
    if banco == "comigo":
        return q.where(Study.dono != "", Study.visivel_para.ilike(f"%{visao.usuario}%"))
    if banco.startswith("usuario:"):
        return q.where(func.lower(Study.dono) == banco.split(":", 1)[1].strip().lower()) if visao.admin \
            else q.where(Study.id < 0)
    return q.where(or_(Study.dono == "", func.lower(Study.dono) == eu,
                       Study.visivel_para.ilike(f"%{visao.usuario}%")))


def _no_banco(st, banco: str, visao) -> bool:
    if visao is None or banco in ("todos", "meu", "compartilhado") or banco.startswith("usuario:"):
        return True
    from ipe.auth import visibilidade as V
    eu = visao.usuario.lower()
    outros = [x.lower() for x in V.lista(st.visivel_para)]
    if banco == "comigo":
        return eu in outros
    return not st.dono or st.dono.lower() == eu or eu in outros


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------ busca
    def search_studies(self, text: str = "", modality: str = "",
                       date_from: str = "", date_to: str = "",
                       limit: int = 2000, banco: str = "visivel") -> list[StudyRow]:
        """0.99.27: `banco` = "visivel" (o compartilhado, o meu e o compartilhado comigo), "meu",
        "compartilhado", "comigo", "usuario:<nome>" (o banco pessoal de alguém — administrador) ou
        "todos". Sem usuário na sessão (modo "só eu") não há filtro."""
        from ipe.auth import visibilidade as V
        visao = V.visao_atual()
        with self.db.session() as s:
            n_series = (select(func.count(Series.id)).where(Series.study_fk == Study.id)
                        .correlate(Study).scalar_subquery())
            n_images = (select(func.count(Instance.id)).join(Series)
                        .where(Series.study_fk == Study.id).correlate(Study).scalar_subquery())
            has_comment = (select(func.count(Comment.id))
                           .where(Comment.target_uid == Study.study_uid)
                           .correlate(Study).scalar_subquery())
            size = (select(func.coalesce(func.sum(Instance.file_size), 0)).join(Series)
                    .where(Series.study_fk == Study.id).correlate(Study).scalar_subquery())
            n_keys = (select(func.count(KeyImage.id)).where(KeyImage.study_uid == Study.study_uid)
                      .correlate(Study).scalar_subquery())
            n_meas = (select(func.count(func.distinct(AnnotationRecord.sop_uid)))
                      .where(AnnotationRecord.study_uid == Study.study_uid).correlate(Study).scalar_subquery())
            n_groups = (select(func.count(SeriesGroup.id)).where(SeriesGroup.study_uid == Study.study_uid)
                        .correlate(Study).scalar_subquery())
            q = (select(Study, Patient, n_series, n_images, has_comment, size, n_keys, n_meas, n_groups)
                 .join(Patient, Study.patient_fk == Patient.id))
            if text:
                # vários termos separados por | (qualquer um casa)
                terms = [t.strip() for t in text.split("|") if t.strip()]
                conds = []
                for t in terms:
                    like = f"%{t}%"
                    conds += [Patient.name.ilike(like), Patient.patient_id.ilike(like),
                              Study.accession.ilike(like), Study.description.ilike(like)]
                q = q.where(or_(*conds))
            if modality:
                q = q.where(Study.modalities.ilike(f"%{modality}%"))
            if date_from:
                q = q.where(Study.study_date >= date_from)
            if date_to:
                q = q.where(Study.study_date <= date_to)
            q = _filtro_de_banco(q, banco, visao)
            q = q.order_by(Study.study_date.desc(), Study.study_time.desc()).limit(limit)
            result = [r for r in s.execute(q) if _no_banco(r[0], banco, visao)]
            uids = [st.study_uid for st, *_r in result]
            lists: dict[str, list[str]] = {}
            details: dict[str, dict[str, list[str]]] = {}
            comments: dict[str, str] = {}
            reports: dict[str, str] = {}
            filmados: set[str] = set()
            parts: dict[str, set[str]] = {}
            ias: dict[str, list[str]] = {}
            mama: dict[str, tuple[str, str]] = {}
            buscas: dict[str, str] = {}
            laudado: dict = {}
            from ipe.core import sla as _SLA
            cfg_sla = _SLA.config(self)
            agora = datetime.now()
            if uids:
                for uid, name in s.execute(select(CaseListItem.study_uid, CaseList.name)
                                           .join(CaseList, CaseListItem.list_fk == CaseList.id)
                                           .where(CaseListItem.study_uid.in_(uids))):
                    lists.setdefault(uid, []).append(name)
                import json as _json
                from ipe.reporting import birads as _BR
                for uid, st_, flds, sig in s.execute(select(Report.study_uid, Report.status, Report.fields,
                                                            Report.signed_at)
                                                     .where(Report.study_uid.in_(uids)).order_by(Report.id)):
                    if st_ != "draft" and sig is not None and uid not in laudado:
                        laudado[uid] = sig                 # 0.99.52: a primeira assinatura conta para o prazo
                    name = {"draft": "rascunho", "final": "assinado", "amended": "retificado"}.get(st_, st_)
                    rank = {"rascunho": 1, "assinado": 2, "retificado": 3}
                    if rank.get(name, 0) > rank.get(reports.get(uid, ""), 0):
                        reports[uid] = name
                    if st_ != "draft" and flds and flds not in ("{}", "null"):
                        # 0.99.51 (onda B7): categoria e densidade do laudo assinado mais recente
                        try:
                            f = _json.loads(flds)
                        except ValueError:
                            f = {}
                        if isinstance(f, dict) and f.get("kind"):
                            cat = _BR.final_category(f)
                            comp = f.get("composition" if f.get("kind") != "mri" else "fgt", "")
                            mama[uid] = (cat, str(comp or "").lower())
                for uid, est in s.execute(select(BuscaAtiva.study_uid, BuscaAtiva.estado)
                                          .where(BuscaAtiva.study_uid.in_(uids)).order_by(BuscaAtiva.id)):
                    buscas[uid] = est
                for guardados in s.scalars(select(SavedFilm.study_uids)):
                    for uid in (guardados or "").split(","):
                        if uid in set(uids):
                            filmados.add(uid)
                texts: dict[str, list[str]] = {}
                for uid, text in s.execute(select(Comment.target_uid, Comment.text)
                                           .where(Comment.target_uid.in_(uids)).order_by(Comment.created_at)):
                    texts.setdefault(uid, []).append(text or "")
                comments = {uid: comment_summary(t) for uid, t in texts.items()}
                details: dict[str, dict[str, list[str]]] = {}
                from ipe.ai.tarefas import ferramentas_da_serie
                for uid, bp, ops, sta, dev, desc in s.execute(
                        select(Study.study_uid, Series.body_part, Series.operators, Series.station, Series.device,
                               Series.description)
                        .join(Series, Series.study_fk == Study.id).where(Study.study_uid.in_(uids))):
                    nome_ia = ferramentas_da_serie(desc or "")
                    if nome_ia and nome_ia not in ias.setdefault(uid, []):
                        ias[uid].append(nome_ia)
                    if bp:
                        parts.setdefault(uid, set()).add(bp)
                    d = details.setdefault(uid, {"operators": [], "station": [], "device": []})
                    for key, val in (("operators", ops), ("station", sta), ("device", dev)):
                        for item in (val or "").split("; "):
                            if item and item not in d[key]:
                                d[key].append(item)
            rows = []
            fmt = "%Y%m%d%H%M"
            for st, pt, ns, ni, hc, sz, nk, nm, ng in result:
                sla = _SLA.resolver({"description": st.description or "", "modalities": st.modalities or "",
                                     "prioridade_manual": st.prioridade or "", "subesp_manual": st.subespecialidade or "",
                                     "chegada": st.date_added, "laudado_em": laudado.get(st.study_uid)}, cfg_sla, agora)
                rows.append(StudyRow(
                    st.study_uid, pt.name, pt.patient_id, pt.birth_date, pt.sex, st.study_date,
                    st.modalities, st.description, st.accession, ns or 0, ni or 0, st.unread, bool(hc),
                    study_time=st.study_time or "", patient_age=st.patient_age or "",
                    institution=st.institution or "", referring=st.referring or "", origin=st.origin or "",
                    date_added=st.date_added.strftime(fmt) if st.date_added else "",
                    last_accessed=st.last_accessed.strftime(fmt) if st.last_accessed else "",
                    locked=bool(st.locked), size_mb=round((sz or 0) / 1024 / 1024, 1), key_images=nk or 0,
                    measured=nm or 0, lists=", ".join(lists.get(st.study_uid, [])),
                    comment=comments.get(st.study_uid, ""),
                    body_part=", ".join(sorted(parts.get(st.study_uid, set()))), num_groups=ng or 0,
                    report=reports.get(st.study_uid, ""), has_film=st.study_uid in filmados,
                    dono=st.dono or "", visivel_para=st.visivel_para or "",
                    ia=", ".join(ias.get(st.study_uid, [])),
                    birads=mama.get(st.study_uid, ("", ""))[0], densidade=mama.get(st.study_uid, ("", ""))[1],
                    busca=buscas.get(st.study_uid, ""), **sla,
                    **{k: "; ".join(v) for k, v in details.get(st.study_uid, {}).items()}))
            return rows

    def series_missing_details(self, limit: int = 500) -> list[tuple[str, str]]:
        """Séries de bancos antigos sem operador/estação/aparelho lidos: (série, um arquivo)."""
        with self.db.session() as s:
            out = []
            for se in s.scalars(select(Series).where(Series.operators.is_(None)).limit(limit)):
                path = s.scalar(select(Instance.file_path).where(Instance.series_fk == se.id).limit(1))
                out.append((se.series_uid, path or ""))
            return out

    def set_series_details(self, series_uid: str, operators: str, station: str, device: str) -> None:
        with self.db.session() as s:
            se = s.scalar(select(Series).where(Series.series_uid == series_uid))
            if se is not None:
                se.operators, se.station, se.device = operators, station, device

    def series_for_study(self, study_uid: str, ocultas: bool = False) -> list[SeriesRow]:
        """Séries do exame. As **ocultas** ficam de fora a menos que `ocultas=True`:
        esconder não é apagar — a série continua no banco e os arquivos no disco."""
        with self.db.session() as s:
            n_images = (select(func.count(Instance.id)).where(Instance.series_fk == Series.id)
                        .correlate(Series).scalar_subquery())
            q = (select(Series, n_images).join(Study)
                 .where(Study.study_uid == study_uid).order_by(Series.series_number))
            if not ocultas:
                q = q.where(Series.hidden.is_(False))
            return [SeriesRow(se.series_uid, study_uid, se.modality, se.series_number,
                              se.description, ni or 0, se.thumbnail, bool(se.hidden), se.body_part or "")
                    for se, ni in s.execute(q)]

    def set_series_hidden(self, series_uids: list[str], hidden: bool) -> int:
        """Esconde (ou mostra) séries. Nada é apagado."""
        n = 0
        with self.db.session() as s:
            for se in s.scalars(select(Series).where(Series.series_uid.in_(list(series_uids)))):
                se.hidden = bool(hidden)
                n += 1
        return n

    def count_hidden_series(self, study_uid: str) -> int:
        with self.db.session() as s:
            return int(s.scalar(select(func.count(Series.id)).join(Study)
                                .where(Study.study_uid == study_uid, Series.hidden.is_(True))) or 0)

    def delete_series(self, series_uid: str, storage_root: Path) -> int:
        """Apaga uma série do banco e os arquivos dela **que estão no Storage**.

        Arquivos apenas referenciados (fora do Storage) nunca são tocados — a mesma regra do
        apagar exame. Exame com cadeado e última série do exame são recusados: exame sem série
        nenhuma é fantasma, e para isso existe o apagar exame.
        """
        with self.db.session() as s:
            se = s.scalar(select(Series).where(Series.series_uid == series_uid))
            if se is None:
                return 0
            st = se.study
            if st.locked:
                raise PermissionError("Exame protegido (cadeado). Desbloqueie antes de apagar.")
            if len(st.series) <= 1:
                raise PermissionError("Esta é a única série do exame. Apague o exame inteiro.")
            study_uid = st.study_uid
            files = [Path(i.file_path) for i in se.instances if i.in_storage]
            for model in (KeyImage, AnnotationRecord):
                for row in s.scalars(select(model).where(model.series_uid == series_uid)):
                    s.delete(row)
            for g in s.scalars(select(SeriesGroup).where(SeriesGroup.study_uid == study_uid)):
                restantes = [u for u in (g.series_uids or "").split(",") if u and u != series_uid]
                if len(restantes) < 2:
                    s.delete(g)
                else:
                    g.series_uids = ",".join(restantes)
            s.delete(se)
        removed = 0
        root = Path(storage_root).resolve()
        for f in files:
            try:
                if root in f.resolve().parents and f.exists():
                    f.unlink()
                    removed += 1
            except OSError as e:
                log.warning("Não foi possível apagar %s: %s", f, e)
        return removed

    def delete_instance(self, sop_uid: str, storage_root: Path) -> int:
        """0.99.31 (onda A7): apaga uma imagem só (um arquivo). Mesmas regras do apagar série: exame com
        cadeado é recusado, e a última imagem da série pede apagar a série. Medidas e imagem-chave dela
        vão junto; o arquivo só sai do disco se estiver no Storage. Devolve 1 se apagou o arquivo."""
        with self.db.session() as s:
            ins = s.scalar(select(Instance).where(Instance.sop_uid == sop_uid))
            if ins is None:
                return 0
            se = ins.series
            st = se.study
            if st.locked:
                raise PermissionError("Exame protegido (cadeado). Desbloqueie antes de apagar.")
            if len(se.instances) <= 1:
                raise PermissionError("Esta é a única imagem da série. Apague a série.")
            arquivo = Path(ins.file_path) if ins.in_storage else None
            for model in (KeyImage, AnnotationRecord):
                for row in s.scalars(select(model).where(model.sop_uid == sop_uid)):
                    s.delete(row)
            s.delete(ins)
        if arquivo is None:
            return 0
        try:
            if Path(storage_root).resolve() in arquivo.resolve().parents and arquivo.exists():
                arquivo.unlink()
                return 1
        except OSError as e:
            log.warning("Não foi possível apagar %s: %s", arquivo, e)
        return 0

    def study_of_sop(self, sop_uid: str) -> str:
        with self.db.session() as s:
            return s.scalar(select(Study.study_uid).join(Series, Series.study_fk == Study.id)
                            .join(Instance, Instance.series_fk == Series.id).where(Instance.sop_uid == sop_uid)) or ""

    def historico_do_exame(self, study_uid: str, limit: int = 500) -> list[dict]:
        """0.99.31 (onda A6): o que aconteceu com o exame — o registro de acesso dele e os laudos
        (criado, assinado), do mais recente para o mais antigo."""
        out = [{"at": a["at"], "user": a["user"], "action": a["action"], "detail": a["detail"], "host": a["host"]}
               for a in self.access_log(limit=limit, study_uid=study_uid)]
        with self.db.session() as s:
            for r in s.scalars(select(Report).where(Report.study_uid == study_uid)):
                if r.created_at:
                    out.append({"at": r.created_at, "user": r.author or "", "action": "laudo_criado",
                                "detail": r.title or "", "host": ""})
                if r.signed_at:
                    out.append({"at": r.signed_at, "user": r.signed_by or "", "action": "laudo_assinado",
                                "detail": f"{r.title or ''} ({r.status})", "host": ""})
        out.sort(key=lambda x: x["at"] or datetime.min, reverse=True)
        return out[:limit]

    def series_by_description(self, names: list, limit: int = 500) -> list[dict]:
        """Séries cuja descrição é uma das dadas (comparação sem caixa). Usado pelo filme da AW."""
        alvos = {str(n or "").strip().lower() for n in names if str(n or "").strip()}
        if not alvos:
            return []
        with self.db.session() as s:
            n_images = (select(func.count(Instance.id)).where(Instance.series_fk == Series.id)
                        .correlate(Series).scalar_subquery())
            q = (select(Series, n_images, Study, Patient).join(Study, Series.study_fk == Study.id)
                 .join(Patient, Study.patient_fk == Patient.id)
                 .where(func.lower(func.trim(Series.description)).in_(alvos))
                 .order_by(Study.study_date.desc()).limit(limit))
            return [{"series_uid": se.series_uid, "study_uid": st.study_uid,
                     "description": se.description, "modality": se.modality,
                     "series_number": se.series_number, "num_images": ni or 0,
                     "patient_name": pa.name, "patient_id": pa.patient_id,
                     "study_date": st.study_date, "study_time": st.study_time}
                    for se, ni, st, pa in s.execute(q)]

    def study_info(self, study_uid: str) -> dict | None:
        with self.db.session() as s:
            st = s.scalar(select(Study).options(selectinload(Study.patient))
                          .where(Study.study_uid == study_uid))
            if st is None:
                return None
            p = st.patient
            return {
                "study_uid": st.study_uid, "patient_name": p.name, "patient_id": p.patient_id,
                "birth_date": p.birth_date, "sex": p.sex, "study_date": st.study_date,
                "study_time": st.study_time, "accession": st.accession,
                "description": st.description, "institution": st.institution,
                "referring": st.referring, "patient_age": st.patient_age,
                "modalities": st.modalities, "dono": st.dono or "", "visivel_para": st.visivel_para or "",
            }

    # ------------------------------------------------------------------ banco pessoal × compartilhado (0.99.27)
    def set_study_scope(self, study_uids, dono: str = "", visivel_para: str = "") -> int:
        """Move exames entre os bancos: "" = compartilhado; um usuário = banco pessoal dele. Só a marca
        muda — os arquivos continuam no mesmo lugar."""
        n = 0
        with self.db.session() as s:
            for st in s.scalars(select(Study).where(Study.study_uid.in_(list(study_uids)))):
                st.dono, st.visivel_para = (dono or "").strip(), (visivel_para or "").strip()
                n += 1
        return n

    def set_study_priority(self, study_uids, prioridade: str | None = None, subespecialidade: str | None = None) -> int:
        """0.99.52 (onda B4): troca à mão a prioridade ("" = a da regra) e/ou a subespecialidade."""
        n = 0
        with self.db.session() as s:
            for st in s.scalars(select(Study).where(Study.study_uid.in_(list(study_uids or [])))):
                if prioridade is not None:
                    st.prioridade = str(prioridade or "")
                if subespecialidade is not None:
                    st.subespecialidade = str(subespecialidade or "")
                n += 1
        return n

    def donos_de_exames(self) -> dict[str, int]:
        """{usuário: exames no banco pessoal dele}."""
        with self.db.session() as s:
            return {d: int(n) for d, n in s.execute(select(Study.dono, func.count(Study.id))
                                                     .where(Study.dono != "").group_by(Study.dono))}

    def transferir_banco(self, de: str, para: str = "") -> int:
        """O banco pessoal inteiro de `de` passa para `para` ("" = compartilhado)."""
        with self.db.session() as s:
            n = 0
            for st in s.scalars(select(Study).where(func.lower(Study.dono) == de.strip().lower())):
                st.dono, st.visivel_para = (para or "").strip(), ""
                n += 1
        return n

    # ------------------------------------------------------------------ dados do exame (0.99.28)
    def dados_do_exame(self, study_uid: str) -> dict:
        """Laudos, medidas, imagens-chave… do exame, para levar junto com as imagens (db/pacote.py)."""
        from ipe.db import pacote
        return pacote.exportar(self.db, study_uid)

    def receber_dados_do_exame(self, pacote_: dict, escopo: bool = True) -> dict:
        from ipe.db import pacote
        return pacote.importar(self.db, pacote_, escopo=escopo)

    def nomes_de_usuarios(self) -> list[str]:
        """Usuários ativos (só o nome), para "Compartilhar com…" — não precisa da permissão de usuários."""
        with self.db.session() as s:
            return sorted(s.scalars(select(User.username).where(User.active.is_(True))), key=str.lower)

    def find_study_uids(self, *, accession: str = "", study_uid: str = "",
                        patient_id: str = "") -> list[str]:
        """Usado pela chamada externa (--accession etc.)."""
        with self.db.session() as s:
            q = select(Study.study_uid).join(Patient)
            if accession:
                q = q.where(Study.accession == accession)
            if study_uid:
                q = q.where(Study.study_uid == study_uid)
            if patient_id:
                q = q.where(Patient.patient_id == patient_id)
            q = q.order_by(Study.study_date.desc())
            return list(s.scalars(q))

    def instances_for_series(self, series_uid: str) -> list[dict]:
        with self.db.session() as s:
            q = (select(Instance).join(Series).where(Series.series_uid == series_uid))
            return [{
                "sop_uid": i.sop_uid, "path": i.file_path, "instance_number": i.instance_number,
                "position": i.image_position, "orientation": i.image_orientation,
                "slice_location": i.slice_location, "frames": i.number_of_frames,
                "acquisition_time": i.acquisition_time,
            } for i in s.scalars(q)]

    def series_meta(self, series_uid: str) -> dict | None:
        with self.db.session() as s:
            se = s.scalar(select(Series).where(Series.series_uid == series_uid))
            if se is None:
                return None
            return {"series_uid": se.series_uid, "modality": se.modality,
                    "series_number": se.series_number, "description": se.description,
                    "study_uid": se.study.study_uid, "station": se.station or "",
                    "operators": se.operators or "",
                    "frame_of_reference": se.frame_of_reference}

    def has_thumbnail(self, series_uid: str) -> bool:
        with self.db.session() as s:
            return s.scalar(select(Series.thumbnail.isnot(None))
                            .where(Series.series_uid == series_uid)) or False

    def set_thumbnail(self, series_uid: str, png: bytes) -> None:
        with self.db.session() as s:
            se = s.scalar(select(Series).where(Series.series_uid == series_uid))
            if se is not None:
                se.thumbnail = png

    def mark_opened(self, study_uid: str) -> None:
        with self.db.session() as s:
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is not None:
                st.last_accessed = datetime.now()
                st.unread = False

    # ------------------------------------------------------------- remoção
    def delete_study(self, study_uid: str, storage_root: Path) -> int:
        """Remove o estudo do banco e apaga os arquivos que estão no Storage.
        Arquivos apenas referenciados (fora do Storage) nunca são apagados."""
        removed = 0
        with self.db.session() as s:
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is None:
                return 0
            if st.locked:
                raise PermissionError("Estudo protegido (cadeado). Desbloqueie antes de apagar.")
            files = [Path(i.file_path) for se in st.series for i in se.instances if i.in_storage]
            patient = st.patient
            for model in (KeyImage, AnnotationRecord, SeriesGroup):
                for row in s.scalars(select(model).where(model.study_uid == study_uid)):
                    s.delete(row)
            for reg in s.scalars(select(StudyRegistration).where(
                    or_(StudyRegistration.study_a == study_uid, StudyRegistration.study_b == study_uid))):
                s.delete(reg)
            s.delete(st)
            s.flush()
            remaining = s.scalar(select(func.count(Study.id))
                                 .where(Study.patient_fk == patient.id))
            if not remaining:
                s.delete(patient)
        root = storage_root.resolve()
        for f in files:
            try:
                if root in f.resolve().parents and f.exists():
                    f.unlink()
                    removed += 1
            except OSError as e:
                log.warning("Não foi possível apagar %s: %s", f, e)
        study_dir = root / _safe(study_uid)
        if study_dir.exists():
            shutil.rmtree(study_dir, ignore_errors=True)
        return removed

    def set_locked(self, study_uid: str, locked: bool) -> None:
        with self.db.session() as s:
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is not None:
                st.locked = locked

    # ---------------------------------------------------------- comentários
    def comments(self, target_uid: str) -> list[Comment]:
        with self.db.session() as s:
            return list(s.scalars(select(Comment).where(Comment.target_uid == target_uid)
                                  .order_by(Comment.created_at)))

    def add_comment(self, target_type: str, target_uid: str, text: str) -> None:
        with self.db.session() as s:
            s.add(Comment(target_type=target_type, target_uid=target_uid, text=text))

    # ------------------------------------------------------- listas de casos
    def case_lists(self) -> list[tuple[int, str, str, int]]:
        """Listas (sem as pastas): (id, nome, tipo, nº de casos)."""
        return [(d["id"], d["name"], d["kind"], d["count"]) for d in self.case_list_tree()
                if d["kind"] not in ("folder", "smart")]

    def case_list_tree(self, gerenciar: bool = False) -> list[dict]:
        """Pastas e listas, com pai e ordem (a interface monta a árvore). `gerenciar`: o administrador
        vê as de todos (Configurações ▸ Usuários ▸ Pessoais e compartilhadas)."""
        with self.db.session() as s:
            n = (select(func.count(CaseListItem.id)).where(CaseListItem.list_fk == CaseList.id)
                 .correlate(CaseList).scalar_subquery())
            rows = s.execute(select(CaseList, n)).all()
            out = [{"id": cl.id, "name": cl.name, "kind": cl.kind, "count": cnt or 0,
                    "parent": cl.parent_fk, "description": cl.description or "",
                    "smart_query": cl.smart_query or "",
                    "position": cl.position if cl.position is not None else 10_000 + cl.id,
                    "dono": cl.dono or "", "visivel_para": cl.visivel_para or ""}
                   for cl, cnt in rows]
        # 0.99.30: cada um vê as do serviço, as suas e as compartilhadas com ele; a lista cuja pasta
        # ele não vê sobe para a raiz
        from ipe.auth import visibilidade as V
        v = V.visao_atual()
        if v is not None and not (gerenciar and v.admin):
            out = [d for d in out if V.visivel(d, v)]
            ids = {d["id"] for d in out}
            for d in out:
                if d["parent"] is not None and d["parent"] not in ids:
                    d["parent"] = None
        for d in out:
            if d["kind"] == "smart":
                d["count"] = len(self.smart_study_uids(d["smart_query"]))
        out.sort(key=lambda d: (d["kind"] != "folder", d["position"], d["name"].lower()))
        return out

    def case_list_info(self, list_id: int) -> dict | None:
        with self.db.session() as s:
            cl = s.get(CaseList, list_id)
            if cl is None:
                return None
            d = {"id": cl.id, "name": cl.name, "kind": cl.kind, "parent": cl.parent_fk,
                 "dono": cl.dono or "", "visivel_para": cl.visivel_para or "",
                 "description": cl.description or "", "smart_query": cl.smart_query or "",
                 "position": cl.position if cl.position is not None else 10_000 + cl.id,
                 "count": s.scalar(select(func.count(CaseListItem.id)).where(CaseListItem.list_fk == cl.id)) or 0}
        if d["kind"] == "smart":
            d["count"] = len(self.smart_study_uids(d["smart_query"]))
        return d

    # listas inteligentes: o conteúdo vem de um filtro salvo (JSON), recalculado sempre
    def smart_study_uids(self, query) -> list[str]:
        import json
        from datetime import date, timedelta
        q = json.loads(query) if isinstance(query, str) and query else (query or {})
        d_from = ""
        if int(q.get("days") or 0) > 0:
            d_from = (date.today() - timedelta(days=int(q["days"]))).strftime("%Y%m%d")
        rows = self.search_studies(q.get("text", ""), q.get("modality", ""), d_from, "", limit=20000)

        def has(txt, needle):
            return not needle or needle.lower() in (txt or "").lower()
        out = []
        for r in rows:
            if not has(r.description, q.get("description", "")) or not has(r.body_part, q.get("body_part", "")):
                continue
            if not has(getattr(r, "institution", ""), q.get("institution", "")):
                continue
            if q.get("origin") and r.origin != q["origin"]:
                continue
            if q.get("key_images") and not r.key_images:
                continue
            if q.get("measured") and not r.measured:
                continue
            if q.get("comment") and not r.has_comment:
                continue
            if q.get("locked") and not r.locked:
                continue
            if q.get("no_list") and r.lists:
                continue
            if q.get("unread") and not r.unread:
                continue
            out.append(r.study_uid)
        return out

    def create_case_list(self, name: str, kind: str = "normal", parent: int | None = None,
                         description: str = "", smart_query: str = "") -> int:
        with self.db.session() as s:
            pos = s.scalar(select(func.coalesce(func.max(CaseList.position), -1))
                           .where(CaseList.parent_fk.is_(None) if parent is None
                                  else CaseList.parent_fk == parent)) + 1
            from ipe.auth import visibilidade as V
            cl = CaseList(name=name, kind=kind, parent_fk=parent, position=pos, description=description,
                          smart_query=smart_query, **V.padrao_novo())    # 0.99.30: do administrador, de todos
            s.add(cl)
            s.flush()
            return cl.id

    def escopo_da_lista(self, list_id: int, dono: str = "", visivel_para: str = "") -> int:
        """0.99.30: quem vê a lista (e, numa pasta, tudo o que está dentro). Regras: o dono ou o
        administrador mudam; tirar do serviço (esconder dos outros) pede configurar; passar para outro
        usuário, só o administrador. Devolve quantas listas/pastas mudaram."""
        from ipe.auth import visibilidade as V
        v = V.visao_atual()
        dono = (dono or "").strip()
        with self.db.session() as s:
            cl = s.get(CaseList, list_id)
            if cl is None:
                return 0
            if v is not None and not v.admin:
                atual = (cl.dono or "").lower()
                if atual not in ("", v.usuario.lower()):
                    raise PermissionError("a lista é de outro usuário")
                if dono and dono.lower() != v.usuario.lower():
                    raise PermissionError("só o administrador passa uma lista para outro usuário")
                if not atual and dono and not V.pode("configure"):
                    raise PermissionError("tirar uma lista de todos (esconder dos outros) pede a permissão de configurar")
            alvo = [cl]
            i = 0
            while i < len(alvo):
                alvo += list(s.scalars(select(CaseList).where(CaseList.parent_fk == alvo[i].id)))
                i += 1
            for x in alvo:
                x.dono, x.visivel_para = dono, (visivel_para or "").strip() if dono else ""
            return len(alvo)

    def update_case_list(self, list_id: int, **fields) -> None:
        allowed = {"name", "kind", "description", "parent_fk", "position", "smart_query"}
        with self.db.session() as s:
            cl = s.get(CaseList, list_id)
            if cl is None:
                return
            if "parent_fk" in fields:
                p = fields["parent_fk"]
                # não deixa uma pasta ir para dentro dela mesma
                while p is not None:
                    if p == list_id:
                        raise ValueError("Uma pasta não pode ficar dentro dela mesma.")
                    parent = s.get(CaseList, p)
                    p = parent.parent_fk if parent is not None else None
            for k, v in fields.items():
                if k in allowed:
                    setattr(cl, k, v)

    def delete_case_list(self, list_id: int) -> None:
        """Apaga a lista (os exames continuam no banco). Numa pasta, o conteúdo sobe um nível."""
        with self.db.session() as s:
            cl = s.get(CaseList, list_id)
            if cl is None:
                return
            for child in s.scalars(select(CaseList).where(CaseList.parent_fk == list_id)):
                child.parent_fk = cl.parent_fk
            s.delete(cl)

    def duplicate_case_list(self, list_id: int, name: str | None = None) -> int:
        with self.db.session() as s:
            src = s.get(CaseList, list_id)
            if src is None or src.kind == "folder":
                raise ValueError("Só listas podem ser duplicadas.")
            from ipe.auth import visibilidade as V
            cl = CaseList(name=name or f"{src.name} (cópia)", kind=src.kind, description=src.description,
                          parent_fk=src.parent_fk, position=(src.position or 0), **V.padrao_novo())
            s.add(cl)
            s.flush()
            for it in src.items:
                s.add(CaseListItem(list_fk=cl.id, study_uid=it.study_uid, position=it.position, note=it.note,
                                   friendly_name=it.friendly_name, clinical_summary=it.clinical_summary,
                                   hidden_diagnosis=it.hidden_diagnosis, saved_view=it.saved_view,
                                   tags=it.tags, show_series=it.show_series))
            return cl.id

    def add_to_case_list(self, list_id: int, study_uid: str, friendly_name: str = "", **fields) -> bool:
        with self.db.session() as s:
            cl = s.get(CaseList, list_id)
            if cl is not None and cl.kind in ("smart", "folder"):
                return False
            exists = s.scalar(select(CaseListItem).where(CaseListItem.list_fk == list_id,
                                                         CaseListItem.study_uid == study_uid))
            if exists:
                return False
            pos = s.scalar(select(func.coalesce(func.max(CaseListItem.position), -1))
                           .where(CaseListItem.list_fk == list_id)) + 1
            item = CaseListItem(list_fk=list_id, study_uid=study_uid, position=pos, friendly_name=friendly_name)
            for k, v in fields.items():
                if k in _ITEM_FIELDS:
                    setattr(item, k, _item_value(k, v))
            s.add(item)
            # estudos em listas ficam protegidos do futuro autodelete
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is not None:
                st.locked = True
            return True

    def study_uids_in_list(self, list_id: int) -> list[str]:
        info = self.case_list_info(list_id)
        if info is not None and info["kind"] == "smart":
            return self.smart_study_uids(info["smart_query"])
        with self.db.session() as s:
            return list(s.scalars(select(CaseListItem.study_uid)
                                  .where(CaseListItem.list_fk == list_id)
                                  .order_by(CaseListItem.position)))

    def list_items(self, list_id: int) -> list[dict]:
        """Casos da lista, na ordem, com os campos do caso e um resumo do exame."""
        with self.db.session() as s:
            cl = s.get(CaseList, list_id)
            smart = cl.smart_query if cl is not None and cl.kind == "smart" else None
        if smart is not None:
            uids = self.smart_study_uids(smart)
            infos = []
            for n, u in enumerate(uids, 1):
                i = self.study_info(u) or {}
                infos.append({"n": n, "study_uid": u, "friendly_name": "", "clinical_summary": "",
                              "hidden_diagnosis": "", "note": "", "tags": [], "show_series": [], "present": True,
                              "description": i.get("description", ""), "modalities": i.get("modalities", ""),
                              "study_date": i.get("study_date", ""), "patient_name": i.get("patient_name", ""),
                              "patient_id": i.get("patient_id", "")})
            return infos
        with self.db.session() as s:
            q = (select(CaseListItem, Study, Patient)
                 .join(Study, Study.study_uid == CaseListItem.study_uid, isouter=True)
                 .join(Patient, Study.patient_fk == Patient.id, isouter=True)
                 .where(CaseListItem.list_fk == list_id).order_by(CaseListItem.position, CaseListItem.id))
            out = []
            for n, (it, st, p) in enumerate(s.execute(q), 1):
                out.append({
                    "n": n, "study_uid": it.study_uid, "friendly_name": it.friendly_name or "",
                    "clinical_summary": it.clinical_summary or "", "hidden_diagnosis": it.hidden_diagnosis or "",
                    "note": it.note or "", "tags": [t for t in (it.tags or "").split(",") if t.strip()],
                    "show_series": [u for u in (it.show_series or "").split(",") if u],
                    "present": st is not None,
                    "description": st.description if st else "", "modalities": st.modalities if st else "",
                    "study_date": st.study_date if st else "",
                    "patient_name": p.name if p else "", "patient_id": p.patient_id if p else "",
                })
            return out

    def update_list_item(self, list_id: int, study_uid: str, **fields) -> None:
        with self.db.session() as s:
            it = s.scalar(select(CaseListItem).where(CaseListItem.list_fk == list_id,
                                                     CaseListItem.study_uid == study_uid))
            if it is None:
                return
            for k, v in fields.items():
                if k in _ITEM_FIELDS:
                    setattr(it, k, _item_value(k, v))

    def remove_from_case_list(self, list_id: int, study_uids: list[str]) -> None:
        with self.db.session() as s:
            for it in s.scalars(select(CaseListItem).where(CaseListItem.list_fk == list_id,
                                                           CaseListItem.study_uid.in_(list(study_uids)))):
                s.delete(it)

    def reorder_case_list(self, list_id: int, study_uids: list[str]) -> None:
        """Nova ordem dos casos (os que não vierem na lista vão para o fim, na ordem antiga)."""
        with self.db.session() as s:
            items = list(s.scalars(select(CaseListItem).where(CaseListItem.list_fk == list_id)
                                   .order_by(CaseListItem.position)))
            order = {u: i for i, u in enumerate(study_uids)}
            items.sort(key=lambda it: (order.get(it.study_uid, len(order)), it.position))
            for i, it in enumerate(items):
                it.position = i

    def lists_of_study(self, study_uid: str) -> list[tuple[int, str]]:
        with self.db.session() as s:
            return [(cl.id, cl.name) for cl in s.scalars(
                select(CaseList).join(CaseListItem, CaseListItem.list_fk == CaseList.id)
                .where(CaseListItem.study_uid == study_uid).order_by(CaseList.name))]

    # ------------------------------------------------------- imagens-chave
    def toggle_key_image(self, study_uid: str, series_uid: str, sop_uid: str,
                         frame_index: int) -> bool:
        """Marca/desmarca. Devolve True se ficou marcada."""
        with self.db.session() as s:
            ki = s.scalar(select(KeyImage).where(KeyImage.sop_uid == sop_uid,
                                                 KeyImage.frame_index == frame_index))
            if ki is not None:
                s.delete(ki)
                return False
            s.add(KeyImage(study_uid=study_uid, series_uid=series_uid, sop_uid=sop_uid,
                           frame_index=frame_index))
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is not None:
                st.locked = True          # estudo com imagem-chave não é apagado automaticamente
            return True

    def key_images(self, study_uid: str) -> list[dict]:
        """Imagens-chave do estudo, com os dados para montar os quadros."""
        with self.db.session() as s:
            q = (select(KeyImage, Instance).join(Instance, Instance.sop_uid == KeyImage.sop_uid)
                 .where(KeyImage.study_uid == study_uid).order_by(KeyImage.created_at))
            out = []
            for ki, inst in s.execute(q):
                out.append({"sop_uid": inst.sop_uid, "path": inst.file_path,
                            "instance_number": inst.instance_number,
                            "position": inst.image_position, "orientation": inst.image_orientation,
                            "frames": 1, "frame_index": ki.frame_index,
                            "series_uid": ki.series_uid, "acquisition_time": ""})
            return out

    def captures_missing_key(self, sop_class: str, modalities: list[str],
                             limit: int = 500) -> list[tuple[str, str, str, str]]:
        """Capturas de tela de MN/PET que ainda não são imagem-chave: (exame, série, SOP, arquivo).

        Serve para bancos montados antes da versão que marca isso na importação.
        """
        with self.db.session() as s:
            ja = select(KeyImage.sop_uid)
            q = (select(Study.study_uid, Series.series_uid, Instance.sop_uid, Instance.file_path)
                 .join(Series, Instance.series_fk == Series.id).join(Study, Series.study_fk == Study.id)
                 .where(Instance.sop_class_uid == sop_class, Series.modality.in_(list(modalities)),
                        Instance.sop_uid.not_in(ja)).limit(limit))
            return [tuple(r) for r in s.execute(q)]

    def add_key_images(self, rows: list[tuple[str, str, str]]) -> int:
        """Marca várias imagens-chave de uma vez, **sem travar o exame** (não é escolha do usuário)."""
        feitas = 0
        with self.db.session() as s:
            for study_uid, series_uid, sop_uid in rows:
                if s.scalar(select(KeyImage.id).where(KeyImage.sop_uid == sop_uid,
                                                      KeyImage.frame_index == 0)):
                    continue
                s.add(KeyImage(study_uid=study_uid, series_uid=series_uid, sop_uid=sop_uid,
                               frame_index=0))
                feitas += 1
        return feitas

    def key_image_set(self, study_uid: str) -> set[tuple[str, int]]:
        with self.db.session() as s:
            return {(k.sop_uid, k.frame_index) for k in
                    s.scalars(select(KeyImage).where(KeyImage.study_uid == study_uid))}

    # ------------------------------------------------------- medidas
    def annotations_for_series(self, series_uids: list[str]) -> list[dict]:
        if not series_uids:
            return []
        with self.db.session() as s:
            q = (select(AnnotationRecord).where(AnnotationRecord.series_uid.in_(list(series_uids)))
                 .order_by(AnnotationRecord.id))
            return [{"id": a.id, "study_uid": a.study_uid, "series_uid": a.series_uid,
                     "sop_uid": a.sop_uid, "frame_index": a.frame_index, "kind": a.kind,
                     "data": a.data} for a in s.scalars(q)]

    def save_annotation(self, *, db_id: int | None, study_uid: str, series_uid: str, sop_uid: str,
                        frame_index: int, kind: str, data: str) -> int:
        with self.db.session() as s:
            row = s.get(AnnotationRecord, db_id) if db_id else None
            if row is None:
                row = AnnotationRecord(study_uid=study_uid, series_uid=series_uid, sop_uid=sop_uid,
                                       frame_index=frame_index, kind=kind)
                s.add(row)
            row.data = data
            s.flush()
            return row.id

    def delete_annotation(self, db_id: int) -> None:
        with self.db.session() as s:
            row = s.get(AnnotationRecord, db_id)
            if row is not None:
                s.delete(row)

    def annotation_counts(self, series_uids: list[str]) -> dict[str, int]:
        """Número de imagens com medida por série."""
        if not series_uids:
            return {}
        with self.db.session() as s:
            q = (select(AnnotationRecord.series_uid,
                        func.count(func.distinct(AnnotationRecord.sop_uid + ":" + func.cast(
                            AnnotationRecord.frame_index, String))))
                 .where(AnnotationRecord.series_uid.in_(list(series_uids)))
                 .group_by(AnnotationRecord.series_uid))
            return {u: n for u, n in s.execute(q)}

    def count_annotations(self, study_uid: str) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count(AnnotationRecord.id))
                            .where(AnnotationRecord.study_uid == study_uid)) or 0

    # ------------------------------------------------------- alinhamentos
    def get_registration(self, study_a: str, study_b: str) -> tuple[list[float], float] | None:
        """Deslocamento (mm, e relativo) que leva pontos de A para B, se salvo."""
        with self.db.session() as s:
            for a, b, sign in ((study_a, study_b, 1.0), (study_b, study_a, -1.0)):
                r = s.scalar(select(StudyRegistration).where(StudyRegistration.study_a == a,
                                                              StudyRegistration.study_b == b))
                if r is not None:
                    return [sign * r.dx, sign * r.dy, sign * r.dz], sign * r.rel
        return None

    def get_registration_matriz(self, study_a: str, study_b: str):
        """A matriz 4 × 4 do registro rígido que leva um ponto de A ao de B (0.99.38), ou None."""
        import json
        import numpy as np
        with self.db.session() as s:
            for a, b, inverter in ((study_a, study_b, False), (study_b, study_a, True)):
                r = s.scalar(select(StudyRegistration).where(StudyRegistration.study_a == a,
                                                              StudyRegistration.study_b == b))
                if r is not None:
                    if not r.matriz:
                        return None
                    M = np.asarray(json.loads(r.matriz), dtype=float)
                    return (np.linalg.inv(M) if inverter else M).tolist()
        return None

    # ------------------------------------------------------------ conferência de IA (0.99.22)
    def revisao_ia(self, study_uid: str, modulo: str) -> dict | None:
        with self.db.session() as s:
            r = s.scalar(select(RevisaoIA).where(RevisaoIA.study_uid == study_uid, RevisaoIA.modulo == modulo))
            if r is None:
                return None
            return {"estado": r.estado, "editado": bool(r.editado), "usuario": r.usuario,
                    "quando": r.quando, "dados": r.dados}

    def salvar_revisao_ia(self, study_uid: str, modulo: str, estado: str, editado: bool, usuario: str,
                          dados: str) -> None:
        with self.db.session() as s:
            r = s.scalar(select(RevisaoIA).where(RevisaoIA.study_uid == study_uid, RevisaoIA.modulo == modulo))
            if r is None:
                r = RevisaoIA(study_uid=study_uid, modulo=modulo)
                s.add(r)
            r.estado, r.editado, r.usuario, r.dados = estado, bool(editado), usuario or "", dados or ""
            r.quando = datetime.now()
            s.commit()

    # ---- achados de IA revisáveis (0.99.46)
    @staticmethod
    def _achado_dict(a: AchadoIA) -> dict:
        import json

        def _j(t, padrao):
            try:
                return json.loads(t) if t else padrao
            except ValueError:
                return padrao
        return {"id": a.id, "study_uid": a.study_uid, "series_uid": a.series_uid, "ferramenta": a.ferramenta,
                "rotulo": a.rotulo, "tipo": a.tipo, "local": a.local, "posicao": _j(a.posicao, None),
                "numeros": _j(a.numeros, {}), "corrigidos": _j(a.corrigidos, {}), "modelo": a.modelo,
                "versao": a.versao, "elegibilidade": a.elegibilidade, "segmento": a.segmento,
                "estado": a.estado, "revisor": a.revisor, "revisado_em": a.revisado_em, "nota": a.nota,
                "lesao_id": a.lesao_id, "criado_em": a.criado_em}

    def achados(self, study_uid: str, ferramenta: str | None = None) -> list[dict]:
        with self.db.session() as s:
            q = select(AchadoIA).where(AchadoIA.study_uid == study_uid)
            if ferramenta:
                q = q.where(AchadoIA.ferramenta == ferramenta)
            return [self._achado_dict(a) for a in s.scalars(q.order_by(AchadoIA.ferramenta, AchadoIA.id))]

    def achado(self, achado_id: int) -> dict | None:
        with self.db.session() as s:
            a = s.get(AchadoIA, achado_id)
            return None if a is None else self._achado_dict(a)

    def gravar_achados(self, study_uid: str, ferramenta: str, itens: list[dict]) -> list[int]:
        """Troca os achados **ainda sugeridos** desta ferramenta pelos novos (uma rodada nova da IA).
        Os já revisados (confirmados, corrigidos, descartados) ficam: são decisão do médico."""
        import json
        with self.db.session() as s:
            for a in s.scalars(select(AchadoIA).where(AchadoIA.study_uid == study_uid,
                                                      AchadoIA.ferramenta == ferramenta,
                                                      AchadoIA.estado == "sugerido")):
                s.delete(a)
            ids = []
            for it in itens:
                a = AchadoIA(study_uid=study_uid, ferramenta=ferramenta, series_uid=it.get("series_uid", ""),
                             rotulo=it.get("rotulo", ""), tipo=it.get("tipo", ""), local=it.get("local", ""),
                             posicao=json.dumps(it.get("posicao")) if it.get("posicao") is not None else "",
                             numeros=json.dumps(it.get("numeros") or {}, ensure_ascii=False),
                             modelo=it.get("modelo", ""), versao=it.get("versao", ""),
                             elegibilidade=it.get("elegibilidade", ""), segmento=int(it.get("segmento") or 0),
                             estado="sugerido")
                s.add(a)
                s.flush()
                ids.append(a.id)
            s.commit()
            return ids

    def revisar_achado(self, achado_id: int, estado: str, revisor: str = "", corrigidos: dict | None = None,
                       nota: str | None = None, lesao_id: int | None = None) -> dict | None:
        import json
        if estado not in ("sugerido", "confirmado", "corrigido", "descartado"):
            raise ValueError(f"estado desconhecido: {estado}")
        with self.db.session() as s:
            a = s.get(AchadoIA, achado_id)
            if a is None:
                return None
            a.estado = estado
            a.revisor = revisor or ""
            a.revisado_em = None if estado == "sugerido" else datetime.now()
            if corrigidos is not None:
                a.corrigidos = json.dumps(corrigidos, ensure_ascii=False) if corrigidos else ""
            if nota is not None:
                a.nota = nota
            if lesao_id is not None:
                a.lesao_id = lesao_id or None
            s.commit()
            return self._achado_dict(a)

    def revisoes_ia_do_paciente(self, study_uid: str, modulo: str) -> list[dict]:
        """As conferências deste módulo nos **outros** exames do mesmo paciente (0.99.23: a numeração da
        coluna que ele confirmou num exame vale de aviso no seguinte). Mais recentes primeiro."""
        with self.db.session() as s:
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is None:
                return []
            q = (select(RevisaoIA, Study).join(Study, Study.study_uid == RevisaoIA.study_uid)
                 .where(Study.patient_fk == st.patient_fk, RevisaoIA.modulo == modulo,
                        RevisaoIA.study_uid != study_uid))
            out = [{"study_uid": r.study_uid, "data": e.study_date, "estado": r.estado, "usuario": r.usuario,
                    "quando": r.quando, "dados": r.dados, "descricao": e.description}
                   for r, e in s.execute(q)]
        return sorted(out, key=lambda d: d["data"] or "", reverse=True)

    def save_registration(self, study_a: str, study_b: str, offset, rel: float = 0.0,
                          method: str = "manual", matriz=None) -> None:
        """`matriz` (0.99.38): 4 × 4 do registro rígido (ponto de A → ponto de B). Mexer na translação à
        mão (Alt+rodinha) grava sem matriz e apaga a rígida: o que vale é o último ajuste."""
        if study_a == study_b:
            return
        sign = 1.0
        import json
        import numpy as np
        M = None if matriz is None else np.asarray(matriz, dtype=float)
        if study_b < study_a:                 # guarda sempre na mesma ordem
            study_a, study_b, sign = study_b, study_a, -1.0
            if M is not None:
                M = np.linalg.inv(M)
        with self.db.session() as s:
            r = s.scalar(select(StudyRegistration).where(StudyRegistration.study_a == study_a,
                                                          StudyRegistration.study_b == study_b))
            if r is None:
                r = StudyRegistration(study_a=study_a, study_b=study_b)
                s.add(r)
            r.dx, r.dy, r.dz = (sign * float(v) for v in offset)
            r.rel, r.method = sign * float(rel), method
            r.matriz = json.dumps(M.tolist()) if M is not None else ""

    # ------------------------------------------------------- grupos de séries (fases)
    def series_groups(self, study_uid: str) -> list[dict]:
        with self.db.session() as s:
            return [{"id": g.id, "study_uid": g.study_uid, "name": g.name, "kind": g.kind,
                     "series_uids": [u for u in g.series_uids.split(",") if u]}
                    for g in s.scalars(select(SeriesGroup).where(SeriesGroup.study_uid == study_uid)
                                       .order_by(SeriesGroup.id))]

    def save_series_group(self, study_uid: str, series_uids: list[str], name: str = "Dinâmica",
                          group_id: int | None = None) -> int:
        with self.db.session() as s:
            g = s.get(SeriesGroup, group_id) if group_id else None
            if g is None:
                g = SeriesGroup(study_uid=study_uid)
                s.add(g)
            g.name, g.series_uids = name, ",".join(series_uids)
            s.flush()
            return g.id

    # ------------------------------------------------------------------ filmes
    def save_film(self, name: str, data: dict, study_uids: list[str], patient_name: str = "",
                  film_id: int | None = None, user: str = "") -> int:
        import json
        with self.db.session() as s:
            f = s.get(SavedFilm, film_id) if film_id else None
            if f is None:
                f = SavedFilm(created_by=user or "")
                s.add(f)
            elif not f.created_by and user:
                f.created_by = user
            f.name, f.data = name, json.dumps(data, ensure_ascii=False)
            f.study_uids, f.patient_name = ",".join(study_uids), patient_name
            f.sheets = len(data.get("sheets", []))
            f.images = sum(1 for sh in data.get("sheets", []) for c in sh.get("cells", []) if c)
            f.updated_at = datetime.now()
            s.flush()
            return f.id

    def films(self, study_uid: str | None = None) -> list[dict]:
        with self.db.session() as s:
            q = select(SavedFilm).order_by(SavedFilm.updated_at.desc())
            out = []
            for f in s.scalars(q):
                uids = [u for u in f.study_uids.split(",") if u]
                if study_uid and study_uid not in uids:
                    continue
                out.append({"id": f.id, "name": f.name, "study_uids": uids, "patient_name": f.patient_name,
                            "sheets": f.sheets, "images": f.images, "created_at": f.created_at,
                            "updated_at": f.updated_at, "printed_at": f.printed_at,
                            "patient_id": f.patient_id or "", "id_source": f.id_source or ""})
            return out

    def set_film_patient(self, film_id: int, patient_name: str, patient_id: str, id_source: str,
                         extra: dict | None = None) -> None:
        """Paciente de um filme montado com imagens recebidas (0.89): na linha e dentro do filme."""
        import json
        with self.db.session() as s:
            f = s.get(SavedFilm, film_id)
            if f is None:
                return
            f.patient_name, f.patient_id, f.id_source = patient_name or "", patient_id or "", id_source or ""
            try:
                d = json.loads(f.data or "{}")
            except ValueError:
                d = {}
            pac = dict(d.get("paciente") or {})
            pac.update({"patient_name": patient_name or "", "patient_id": patient_id or "",
                        "id_source": id_source or ""})
            if extra:
                pac.update(extra)
            d["paciente"] = pac
            f.data = json.dumps(d, ensure_ascii=False)
            f.updated_at = datetime.now()

    def film_data(self, film_id: int) -> dict | None:
        import json
        with self.db.session() as s:
            f = s.get(SavedFilm, film_id)
            return json.loads(f.data or "{}") if f is not None else None

    def mark_film_printed(self, film_id: int, user: str = "", destination: str = "") -> None:
        """Mais uma impressão do filme: guarda a hora, quem, para onde e soma uma na contagem."""
        with self.db.session() as s:
            f = s.get(SavedFilm, film_id)
            if f is not None:
                antes = int(f.print_count or 0)
                if antes == 0 and f.printed_at is not None:
                    antes = 1                   # impresso antes da 0.77, quando não se contava
                f.printed_at = datetime.now()
                f.print_count = antes + 1
                f.printed_by = user or ""
                f.print_destination = (destination or "")[:128]

    def studies_for_ocr(self) -> list[dict]:
        """Todos os exames, só com o que a identificação por OCR precisa (consulta leve)."""
        from ipe.printing.matching import _quando
        with self.db.session() as s:
            q = (select(Study.study_uid, Patient.name, Patient.patient_id, Study.study_date,
                        Study.study_time, Study.modalities, Study.description)
                 .join(Patient, Study.patient_fk == Patient.id))
            out = []
            from types import SimpleNamespace
            for uid, nome, pid, data, hora, mods, desc in s.execute(q):
                quando = _quando(SimpleNamespace(study_date=data or "", study_time=hora or ""))
                out.append({"study_uid": uid, "patient_name": nome or "", "patient_id": pid or "",
                            "modalities": mods or "", "description": desc or "", "when": quando})
            return out

    def film_stats_rows(self) -> list[dict]:
        """Um filme por linha, com o que o painel de filmes precisa: o exame (data, hora,
        modalidade, descrição) e a modalidade **das imagens do filme** — num PET/CT, um filme só
        de TC é TC. Só lê o banco; a conta fica em `core.film_stats`."""
        import json
        with self.db.session() as s:
            filmes = list(s.scalars(select(SavedFilm).order_by(SavedFilm.created_at)))
            uids = {u for f in filmes for u in (f.study_uids or "").split(",") if u}
            estudos = {}
            if uids:
                for st in s.scalars(select(Study).where(Study.study_uid.in_(uids))):
                    estudos[st.study_uid] = {"date": st.study_date or "", "time": st.study_time or "",
                                             "modalities": st.modalities or "",
                                             "description": st.description or "",
                                             "accession": st.accession or ""}
            series_uids = set()
            dados = {}
            for f in filmes:
                try:
                    d = json.loads(f.data or "{}")
                except ValueError:
                    d = {}
                cel = [c for sh in d.get("sheets", []) for c in sh.get("cells", []) if c]
                dados[f.id] = cel
                series_uids |= {c.get("series_uid", "") for c in cel if c.get("series_uid")}
            mod_serie = {}
            lista = list(series_uids)
            for i in range(0, len(lista), 500):
                for uid, mod in s.execute(select(Series.series_uid, Series.modality)
                                          .where(Series.series_uid.in_(lista[i:i + 500]))):
                    mod_serie[uid] = mod or ""
            out = []
            for f in filmes:
                fu = [u for u in (f.study_uids or "").split(",") if u]
                exs = [estudos[u] for u in fu if u in estudos]
                mods = sorted({mod_serie.get(c.get("series_uid", ""), "") for c in dados[f.id]} - {""})
                if not mods:
                    mods = sorted({m for e in exs for m in e["modalities"].split("\\") if m})
                primeiro = min(exs, key=lambda e: (e["date"], e["time"])) if exs else {}
                out.append({"id": f.id, "name": f.name, "patient_name": f.patient_name,
                            "study_uids": fu, "sheets": f.sheets, "images": f.images,
                            "created_at": f.created_at, "updated_at": f.updated_at,
                            "printed_at": f.printed_at, "created_by": f.created_by or "",
                            "printed_by": f.printed_by or "",
                            "print_count": int(f.print_count or 0) or (1 if f.printed_at else 0),
                            "print_destination": f.print_destination or "",
                            "modalities": mods, "study_date": primeiro.get("date", ""),
                            "study_time": primeiro.get("time", ""),
                            "study_description": primeiro.get("description", ""),
                            "accession": primeiro.get("accession", "")})
            return out

    def print_job_stats_rows(self) -> list[dict]:
        """As impressões que chegaram prontas pela impressora DICOM, no formato do painel de filmes.

        A impressão não traz exame. Com o paciente identificado (OCR ou à mão), o exame é o dele no
        mesmo aparelho... que não sabemos: é o exame mais recente do paciente feito até a hora da
        chegada, no mesmo dia ou no anterior. O exame criado com as próprias folhas não conta.
        """
        from datetime import timedelta

        from ipe.core.film_stats import hora_do_exame
        with self.db.session() as s:
            jobs = list(s.scalars(select(PrintJobRecord).order_by(PrintJobRecord.received_at)))
            ultimos = self.last_sends("scp")
            vezes = self.count_sends("scp")

            def _quem(envio: dict) -> str:
                """Quem mandou: o usuário; envio pela regra diz "regra" (0.84, histórico de envios)."""
                if envio.get("how") == "regra":
                    return "regra (automático)"
                return envio.get("user") or ""
            ids = {j.patient_id for j in jobs if j.patient_id}
            por_paciente: dict[str, list[dict]] = {}
            if ids:
                lista = list(ids)
                for i in range(0, len(lista), 500):
                    q = (select(Patient.patient_id, Study.study_uid, Study.study_date, Study.study_time,
                                Study.modalities, Study.description, Study.accession)
                         .join(Study, Study.patient_fk == Patient.id)
                         .where(Patient.patient_id.in_(lista[i:i + 500])))
                    for pid, uid, d, t, mods, desc, acc in s.execute(q):
                        por_paciente.setdefault(pid, []).append(
                            {"uid": uid, "date": d or "", "time": t or "", "quando": hora_do_exame(d, t),
                             "modalities": mods or "", "description": desc or "", "accession": acc or ""})
            out = []
            for j in jobs:
                exame = {}
                chegou = j.received_at
                if j.patient_id and chegou is not None:
                    cands = [e for e in por_paciente.get(j.patient_id, [])
                             if e["uid"] != j.study_uid and e["quando"] is not None
                             and chegou - timedelta(days=2) <= e["quando"] <= chegou + timedelta(minutes=5)]
                    if cands:
                        exame = max(cands, key=lambda e: e["quando"])
                mods = sorted({m for m in exame.get("modalities", "").split("\\") if m})
                if not mods and j.modality:          # 0.84: a modalidade guardada (ex.: da origem)
                    mods = sorted({m for m in j.modality.split("\\") if m})
                enviado = j.status == "sent"
                ultimo = ultimos.get(str(j.id))
                out.append({"tipo": "dicom", "id": j.id, "name": j.label or "",
                            "patient_name": " ".join((j.patient_name or "").replace("^", " ").split()),
                            "study_uid": j.study_uid or "", "sheets": j.sheets, "images": j.images,
                            "created_at": chegou, "printed_at": (j.sent_at or chegou) if enviado else None,
                            "created_by": "",
                            "printed_by": (_quem(ultimo) if ultimo else "") if enviado else "",
                            "print_count": max(1, vezes.get(str(j.id), 0)) if enviado else 0,
                            "print_destination": j.destination or "", "modalities": mods,
                            "calling_ae": j.calling_ae, "remote_host": j.remote_host, "server": j.server,
                            "study_date": exame.get("date", ""), "study_time": exame.get("time", ""),
                            "study_description": exame.get("description", ""),
                            "accession": exame.get("accession", "")})
            return out

    def delete_film(self, film_id: int) -> None:
        with self.db.session() as s:
            f = s.get(SavedFilm, film_id)
            if f is not None:
                s.delete(f)

    # ------------------------------------------------------------------ acervo
    def storage_rows(self) -> list[dict]:
        """Uma linha por (modalidade, sintaxe de transferência): arquivos, bytes e pixels.

        É uma agregação só, sem abrir arquivo nenhum — é o que deixa o relatório do acervo
        responder na hora mesmo com centenas de milhares de instâncias.
        """
        quadros = case((Instance.number_of_frames < 1, 1), else_=Instance.number_of_frames)
        with self.db.session() as s:
            q = (select(Series.modality, Instance.transfer_syntax,
                        func.count(Instance.id), func.sum(Instance.file_size),
                        func.sum(Instance.rows * Instance.columns * quadros))
                 .join(Series, Instance.series_fk == Series.id)
                 .where(Instance.in_storage.is_(True))
                 .group_by(Series.modality, Instance.transfer_syntax))
            return [{"modality": m or "", "syntax": t or "", "files": int(n or 0),
                     "bytes": int(b or 0), "pixels": int(p or 0)}
                    for m, t, n, b, p in s.execute(q)]

    def storage_samples(self, modality: str, syntax: str, limit: int = 3) -> list[str]:
        """Caminhos de amostra desse par, **de séries diferentes** — medir três cortes vizinhos
        da mesma série diria a taxa daquela série, não a do acervo."""
        with self.db.session() as s:
            q = (select(Instance.file_path, Series.id)
                 .join(Series, Instance.series_fk == Series.id)
                 .where(Series.modality == modality, Instance.transfer_syntax == syntax,
                        Instance.in_storage.is_(True))
                 .order_by(Series.id, Instance.instance_number)
                 .limit(max(1, limit) * 400))
            vistas: set[int] = set()
            out: list[str] = []
            for caminho, serie in s.execute(q):
                if serie in vistas:
                    continue
                vistas.add(serie)
                out.append(caminho)
                if len(out) >= max(1, limit):
                    break
            return out

    def instances_to_compress(self, antes_de, minimo_bytes: int = 0,
                              pular_protegidos: bool = True, limite: int = 400) -> list[dict]:
        """Arquivos que o prazo já liberou para comprimir.

        O prazo conta da **entrada do exame no sistema** (`study.date_added`), que é o que o
        usuário enxerga como "há quantos dias isso está aqui" — e não da data do exame, que pode
        ser de anos atrás e liberaria tudo no primeiro dia.
        """
        from ipe.core.acervo import SEM, SINTAXES
        cruas = [u for u, s in SINTAXES.items() if s.tipo == SEM]
        with self.db.session() as s:
            q = (select(Instance.sop_uid, Instance.file_path, Instance.file_size,
                        Study.study_uid, Series.modality)
                 .join(Series, Instance.series_fk == Series.id)
                 .join(Study, Series.study_fk == Study.id)
                 .where(Instance.in_storage.is_(True),
                        Instance.transfer_syntax.in_(cruas),
                        Instance.file_size >= int(minimo_bytes or 0),
                        Study.date_added < antes_de))
            if pular_protegidos:
                q = q.where(Study.locked.is_(False))
            q = q.order_by(Instance.file_size.desc()).limit(max(1, int(limite)))
            return [{"sop_uid": sop, "path": caminho, "bytes": int(tam or 0),
                     "study_uid": st, "modality": mod or ""}
                    for sop, caminho, tam, st, mod in s.execute(q)]

    def set_instance_storage(self, sop_uid: str, transfer_syntax: str, file_size: int) -> None:
        """Depois que o arquivo no disco mudou de formato, o banco precisa saber."""
        with self.db.session() as s:
            inst = s.scalar(select(Instance).where(Instance.sop_uid == sop_uid))
            if inst is None:
                return
            inst.transfer_syntax = transfer_syntax
            inst.file_size = int(file_size)

    def valores_do_acervo(self, campo: str, limite: int = 300) -> list[tuple[str, int]]:
        """Os valores que **existem** no acervo para um campo, com quantas séries cada um tem.

        É o que faz o menu de seleção oferecer a realidade do serviço em vez de uma lista que eu
        imaginei: descrição de série, aparelho e parte do corpo mudam de lugar para lugar.
        """
        colunas = {"modalidade": Series.modality, "descricao": Series.description,
                   "lado": Series.laterality, "parte": Series.body_part,
                   "aparelho": Series.device, "estacao": Series.station}
        col = colunas.get(campo)
        if col is None:
            return []
        with self.db.session() as s:
            q = (select(col, func.count(Series.id)).group_by(col)
                 .order_by(func.count(Series.id).desc()).limit(max(1, limite)))
            return [(str(v or ""), int(n)) for v, n in s.execute(q) if str(v or "").strip()]

    def series_para_analise(self, modalidades=(), limite: int = 20000) -> list[dict]:
        """Séries com os atributos que o banco sabe, para a seleção filtrar barato."""
        with self.db.session() as s:
            q = (select(Series.series_uid, Study.study_uid, Series.modality, Series.description,
                        Series.laterality, Series.body_part, Series.device, Series.station,
                        func.count(Instance.id))
                 .join(Study, Series.study_fk == Study.id)
                 .join(Instance, Instance.series_fk == Series.id)
                 .group_by(Series.id).limit(max(1, limite)))
            if modalidades:
                q = q.where(Series.modality.in_(list(modalidades)))
            return [{"series_uid": su, "study_uid": st, "modalidade": mod or "",
                     "descricao": desc or "", "lado": lat or "", "parte": parte or "",
                     "aparelho": dev or "", "estacao": sta or "", "imagens": int(n or 0)}
                    for su, st, mod, desc, lat, parte, dev, sta, n in s.execute(q)]

    # ------------------------------------------------------------------ impressões
    _PRINT_FIELDS = {"uid", "source", "calling_ae", "remote_host", "server", "label", "medium", "film_size",
                     "sheets", "images", "patient_name", "patient_id", "id_source", "study_uid",
                     "folder", "status", "destination", "message", "modality"}

    def add_print_job(self, **fields) -> int:
        """Registra um trabalho de impressão (recebido ou montado aqui)."""
        with self.db.session() as s:
            r = PrintJobRecord()
            for k, v in fields.items():
                if k in self._PRINT_FIELDS:
                    setattr(r, k, v)
            if fields.get("received_at"):
                r.received_at = fields["received_at"]
            s.add(r)
            s.flush()
            return r.id

    def print_jobs(self, limit: int = 1000) -> list[dict]:
        with self.db.session() as s:
            q = select(PrintJobRecord).order_by(PrintJobRecord.received_at.desc()).limit(limit)
            return [self._print_row(r) for r in s.scalars(q)]

    def print_job(self, job_id: int) -> dict | None:
        with self.db.session() as s:
            r = s.get(PrintJobRecord, job_id)
            return self._print_row(r) if r is not None else None

    def print_job_by_uid(self, uid: str) -> dict | None:
        with self.db.session() as s:
            r = s.scalars(select(PrintJobRecord).where(PrintJobRecord.uid == uid)).first()
            return self._print_row(r) if r is not None else None

    @staticmethod
    def _print_row(r: PrintJobRecord) -> dict:
        return {"id": r.id, "uid": r.uid, "source": r.source, "received_at": r.received_at,
                "calling_ae": r.calling_ae, "remote_host": r.remote_host, "server": r.server,
                "label": r.label,
                "medium": r.medium, "film_size": r.film_size, "sheets": r.sheets, "images": r.images,
                "patient_name": r.patient_name, "patient_id": r.patient_id, "id_source": r.id_source,
                "study_uid": r.study_uid, "folder": r.folder, "status": r.status,
                "destination": r.destination, "sent_at": r.sent_at, "message": r.message,
                "modality": r.modality or ""}

    def update_print_job(self, job_id: int, **fields) -> None:
        with self.db.session() as s:
            r = s.get(PrintJobRecord, job_id)
            if r is None:
                return
            for k, v in fields.items():
                if k in self._PRINT_FIELDS:
                    setattr(r, k, v)
            if fields.get("status") == "sent":
                r.sent_at = fields.get("sent_at") or datetime.now()

    # ------------------------------------------------------------------ histórico de envios (0.84)
    def add_send(self, kind: str, ref, destination: str, user: str = "", how: str = "manual",
                 ok: bool = True, message: str = "", at: datetime | None = None, template: str = "") -> int:
        with self.db.session() as s:
            r = PrintSendRecord(kind=kind, ref=str(ref), destination=(destination or "")[:256],
                                user=user or "", how=how or "manual", ok=bool(ok), message=message or "",
                                at=at or datetime.now(), template=(template or "")[:128])
            s.add(r)
            s.flush()
            return r.id

    @staticmethod
    def _send_row(r: PrintSendRecord) -> dict:
        return {"id": r.id, "kind": r.kind, "ref": r.ref, "at": r.at, "destination": r.destination,
                "user": r.user, "how": r.how, "ok": bool(r.ok), "message": r.message,
                "template": r.template or ""}

    def delete_sends(self, kind: str, ref) -> None:
        with self.db.session() as s:
            for r in s.scalars(select(PrintSendRecord).where(PrintSendRecord.kind == kind,
                                                             PrintSendRecord.ref == str(ref))):
                s.delete(r)

    def sends(self, kind: str, ref) -> list[dict]:
        """Os envios de um filme, do mais recente para o mais antigo."""
        with self.db.session() as s:
            q = (select(PrintSendRecord).where(PrintSendRecord.kind == kind, PrintSendRecord.ref == str(ref))
                 .order_by(PrintSendRecord.at.desc(), PrintSendRecord.id.desc()))
            return [self._send_row(r) for r in s.scalars(q)]

    def last_sends(self, kind: str, so_ok: bool = True) -> dict[str, dict]:
        """O último envio de cada filme da lista `kind` (ref -> linha)."""
        with self.db.session() as s:
            q = select(PrintSendRecord).where(PrintSendRecord.kind == kind)
            if so_ok:
                q = q.where(PrintSendRecord.ok.is_(True))
            out: dict[str, dict] = {}
            for r in s.scalars(q.order_by(PrintSendRecord.at, PrintSendRecord.id)):
                out[r.ref] = self._send_row(r)
            return out

    def count_sends(self, kind: str) -> dict[str, int]:
        with self.db.session() as s:
            q = (select(PrintSendRecord.ref, func.count(PrintSendRecord.id))
                 .where(PrintSendRecord.kind == kind, PrintSendRecord.ok.is_(True))
                 .group_by(PrintSendRecord.ref))
            return {ref: int(n) for ref, n in s.execute(q)}

    def study_modalities(self, uids: list[str]) -> dict[str, str]:
        """UID do estudo -> modalidades ("MG", "CT\\PT")."""
        out: dict[str, str] = {}
        uids = [u for u in uids if u]
        with self.db.session() as s:
            for i in range(0, len(uids), 500):
                for uid, mods in s.execute(select(Study.study_uid, Study.modalities)
                                           .where(Study.study_uid.in_(uids[i:i + 500]))):
                    out[uid] = mods or ""
        return out

    def exame_do_paciente(self, patient_id: str, quando: datetime, excluir_uid: str = "") -> dict | None:
        """O exame mais recente do paciente feito até `quando` (no mesmo dia ou no anterior)."""
        from datetime import timedelta

        from ipe.core.film_stats import hora_do_exame
        if not patient_id or quando is None:
            return None
        with self.db.session() as s:
            q = (select(Study.study_uid, Study.study_date, Study.study_time, Study.modalities,
                        Study.description, Study.accession)
                 .join(Patient, Study.patient_fk == Patient.id).where(Patient.patient_id == patient_id))
            melhor = None
            for uid, d, t, mods, desc, acc in s.execute(q):
                h = hora_do_exame(d, t)
                if uid == excluir_uid or h is None:
                    continue
                if not (quando - timedelta(days=2) <= h <= quando + timedelta(minutes=5)):
                    continue
                if melhor is None or h > melhor["quando"]:
                    melhor = {"uid": uid, "date": d or "", "time": t or "", "quando": h,
                              "modalities": mods or "", "description": desc or "", "accession": acc or ""}
            return melhor

    def delete_print_job(self, job_id: int) -> str:
        """Apaga o registro e devolve a pasta do trabalho (quem chama decide apagá-la)."""
        with self.db.session() as s:
            r = s.get(PrintJobRecord, job_id)
            if r is None:
                return ""
            folder = r.folder or ""
            s.delete(r)
            return folder

    def study_uids_in_films(self) -> set[str]:
        with self.db.session() as s:
            return {u for v in s.scalars(select(SavedFilm.study_uids)) for u in (v or "").split(",") if u}

    def series_group(self, group_id: int) -> dict | None:
        with self.db.session() as s:
            g = s.get(SeriesGroup, group_id)
            if g is None:
                return None
            return {"id": g.id, "study_uid": g.study_uid, "name": g.name, "kind": g.kind,
                    "series_uids": [u for u in g.series_uids.split(",") if u]}

    def series_info(self, series_uid: str) -> dict | None:
        """Estudo e descrição de uma série."""
        with self.db.session() as s:
            row = s.execute(select(Series, Study.study_uid).join(Study, Series.study_fk == Study.id)
                            .where(Series.series_uid == series_uid)).first()
            if row is None:
                return None
            se, study_uid = row
            return {"series_uid": se.series_uid, "study_uid": study_uid, "description": se.description or "",
                    "modality": se.modality or "", "number": se.series_number}

    def delete_series_group(self, group_id: int) -> None:
        with self.db.session() as s:
            g = s.get(SeriesGroup, group_id)
            if g is not None:
                s.delete(g)

    # ------------------------------------------------------- automação
    def rules(self, kind: str | None = None, visiveis: bool = False, gerenciar: bool = False) -> list[dict]:
        """As regras de automação. Quem trabalha pela máquina (o motor da automação) recebe todas; a
        tela pede `visiveis=True` (0.99.36): as do serviço, as suas e as compartilhadas com quem está
        logado; `gerenciar` = o administrador vê as de todos. O dono mora no JSON da regra."""
        import json
        with self.db.session() as s:
            q = select(AutomationRule).order_by(AutomationRule.id)
            if kind:
                q = q.where(AutomationRule.kind == kind)
            out = []
            for r in s.scalars(q):
                cfg = json.loads(r.config or "{}")
                out.append({"id": r.id, "kind": r.kind, "name": r.name, "active": r.active, "config": cfg,
                            "last_run": r.last_run, "next_run": r.next_run,
                            "dono": str(cfg.get("dono", "") or ""),
                            "visivel_para": str(cfg.get("visivel_para", "") or "")})
        if visiveis:
            from ipe.auth import visibilidade as V
            out = V.filtrar(out, gerenciar=gerenciar)
        return out

    def escopo_da_regra(self, rule_id: int, dono: str = "", visivel_para: str = "") -> None:
        """Quem vê a regra de automação (0.99.36), com as mesmas regras das listas e dos nós: o dono ou o
        administrador mudam; pôr para todos ou tirar de todos pede configurar; passar para outro, só o
        administrador."""
        from ipe.auth import visibilidade as V
        r = self.rule(rule_id)
        if r is None:
            raise PermissionError("regra não encontrada")
        v = V.visao_atual()
        dono = (dono or "").strip()
        if v is not None and not v.admin:
            atual = r["dono"].lower()
            if atual not in ("", v.usuario.lower()):
                raise PermissionError("a regra é de outro usuário")
            if dono and dono.lower() != v.usuario.lower():
                raise PermissionError("só o administrador passa uma regra para outro usuário")
            if (not atual or not dono) and not V.pode("configure"):
                raise PermissionError("mexer numa regra de todos pede a permissão de configurar")
        cfg = dict(r["config"])
        cfg["dono"], cfg["visivel_para"] = dono, (visivel_para or "").strip() if dono else ""
        self.save_rule({"id": rule_id, "config": cfg})

    def rule(self, rule_id: int) -> dict | None:
        return next((r for r in self.rules() if r["id"] == rule_id), None)

    def save_rule(self, data: dict) -> int:
        import json
        with self.db.session() as s:
            r = s.get(AutomationRule, data.get("id")) if data.get("id") else None
            if r is None:
                r = AutomationRule(kind=data["kind"])
                s.add(r)
            for k in ("name", "active", "last_run", "next_run"):
                if k in data:
                    setattr(r, k, data[k])
            if "config" in data:
                cfg = dict(data["config"] or {})
                antes = json.loads(r.config or "{}") if r.config else {}
                for k in ("dono", "visivel_para"):          # 0.99.36: o dono mora no JSON da regra
                    if k in data:
                        cfg[k] = data[k] or ""
                    elif k not in cfg and k in antes:       # quem grava a configuração sem o dono não o apaga
                        cfg[k] = antes[k]
                r.config = json.dumps(cfg, ensure_ascii=False)
            elif "dono" in data or "visivel_para" in data:
                cfg = json.loads(r.config or "{}")
                for k in ("dono", "visivel_para"):
                    if k in data:
                        cfg[k] = data[k] or ""
                r.config = json.dumps(cfg, ensure_ascii=False)
            s.flush()
            return r.id

    def delete_rule(self, rule_id: int) -> None:
        with self.db.session() as s:
            r = s.get(AutomationRule, rule_id)
            if r is not None:
                s.delete(r)

    def add_job_run(self, kind: str, name: str, status: str, items: int, message: str,
                    rule_id: int | None = None, started: datetime | None = None) -> None:
        with self.db.session() as s:
            s.add(JobRun(rule_id=rule_id, kind=kind, name=name, status=status, items=items,
                         message=message[:2000], started=started or datetime.now(), finished=datetime.now()))

    def job_runs(self, limit: int = 300) -> list[dict]:
        with self.db.session() as s:
            return [{"started": j.started, "finished": j.finished, "kind": j.kind, "name": j.name,
                     "status": j.status, "items": j.items, "message": j.message}
                    for j in s.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(limit))]

    def log_deletion(self, study_uid: str, patient: str, description: str, reason: str,
                     action: str = "trash") -> None:
        with self.db.session() as s:
            s.add(DeletionLog(study_uid=study_uid, patient=patient, description=description,
                              reason=reason, action=action))

    def deletion_log(self, limit: int = 300) -> list[dict]:
        with self.db.session() as s:
            return [{"at": d.at, "study_uid": d.study_uid, "patient": d.patient, "description": d.description,
                     "reason": d.reason, "action": d.action}
                    for d in s.scalars(select(DeletionLog).order_by(DeletionLog.id.desc()).limit(limit))]

    def retention_stats(self):
        """Tudo o que a limpeza precisa saber de cada estudo (tamanho, uso, proteções)."""
        from ipe.automation.rules import StudyStat
        with self.db.session() as s:
            size = dict(s.execute(select(Series.study_fk, func.sum(Instance.file_size))
                                  .join(Instance, Instance.series_fk == Series.id)
                                  .where(Instance.in_storage.is_(True)).group_by(Series.study_fk)).all())
            listed = set(s.scalars(select(CaseListItem.study_uid)))
            commented = set(s.scalars(select(Comment.target_uid)))
            keys = set(s.scalars(select(KeyImage.study_uid)))
            measured = set(s.scalars(select(AnnotationRecord.study_uid)))
            dx = set(s.scalars(select(Diagnosis.study_uid)))
            filmed = {u for v in s.scalars(select(SavedFilm.study_uids)) for u in (v or "").split(",") if u}
            out = []
            for st, p in s.execute(select(Study, Patient).join(Patient, Study.patient_fk == Patient.id)):
                prot = []
                if st.locked:
                    prot.append("protegido")
                for flag, name in ((listed, "em lista"), (commented, "com comentário"),
                                   (keys, "com imagem-chave"), (measured, "com medidas"),
                                   (dx, "com diagnóstico"), (filmed, "em filme salvo")):
                    if st.study_uid in flag:
                        prot.append(name)
                out.append(StudyStat(st.study_uid, p.name, st.description, st.modalities, st.origin,
                                     st.date_added, st.last_accessed, int(size.get(st.id) or 0), prot))
            return out

    def studies_of_patient(self, patient_id: str) -> list[StudyRow]:
        if not patient_id:
            return []
        return [r for r in self.search_studies(limit=10000) if r.patient_id == patient_id]

    def set_study_origin(self, study_uid: str, origin: str) -> None:
        with self.db.session() as s:
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is not None:
                st.origin = origin

    # ------------------------------------------------------- rede DICOM
    NODE_FIELDS = ("name", "kind", "ae_title", "host", "port", "base_url", "username", "password",
                   "verify_tls", "retrieve",
                   "move_destination", "use_in_search", "use_in_priors", "use_in_send", "stream_open",
                   "priority", "active", "note", "dono", "visivel_para")
    IDENTITY_FIELDS = ("name", "ae_title", "move_destination", "allowed_nodes", "note", "dono", "visivel_para")

    def nodes(self, only_active: bool = False, todos: bool = False, gerenciar: bool = False) -> list[dict]:
        """Os nós. 0.99.26: filtrados pelo que a sessão aberta enxerga (os do serviço, os dela e os
        compartilhados com ela); `gerenciar` = tela de configuração (o administrador vê todos); `todos` =
        quem trabalha pela máquina (o nó DICOM que recebe, a automação), que precisa de todos."""
        lista = self._nodes(only_active)
        if todos:
            return lista
        from ipe.auth import visibilidade as V
        return V.filtrar(lista, gerenciar=gerenciar)

    def _nodes(self, only_active: bool = False) -> list[dict]:
        with self.db.session() as s:
            q = select(DicomNode).order_by(DicomNode.priority, DicomNode.name)
            if only_active:
                q = q.where(DicomNode.active.is_(True))
            out = []
            for n in s.scalars(q):
                d = {"id": n.id, **{f: getattr(n, f) for f in self.NODE_FIELDS}}
                if d["use_in_priors"] is None:
                    d["use_in_priors"] = bool(d["use_in_search"])
                if d["use_in_send"] is None:
                    d["use_in_send"] = True
                out.append(d)
            return out

    def node(self, node_id: int) -> dict | None:
        return next((n for n in self.nodes(todos=True) if n["id"] == node_id), None)

    def node_by_ae(self, ae_title: str) -> dict | None:
        ae = ae_title.strip()
        return next((n for n in self.nodes(todos=True) if n["ae_title"].strip() == ae), None)

    def save_node(self, data: dict) -> int:
        with self.db.session() as s:
            n = s.get(DicomNode, data.get("id")) if data.get("id") else None
            if n is None:
                n = DicomNode()
                s.add(n)
            for f in self.NODE_FIELDS:
                if f in data:
                    setattr(n, f, data[f])
            s.flush()
            return n.id

    def delete_node(self, node_id: int) -> None:
        with self.db.session() as s:
            n = s.get(DicomNode, node_id)
            if n is not None:
                s.delete(n)

    def identities(self, todos: bool = False, gerenciar: bool = False) -> list[dict]:
        lista = self._identities()
        if todos:
            return lista
        from ipe.auth import visibilidade as V
        return V.filtrar(lista, gerenciar=gerenciar)

    def _identities(self) -> list[dict]:
        with self.db.session() as s:
            return [{"id": i.id, **{f: getattr(i, f) for f in self.IDENTITY_FIELDS}}
                    for i in s.scalars(select(AeIdentity).order_by(AeIdentity.name))]

    def identity(self, ident_id: int | None) -> dict | None:
        if not ident_id:
            return None
        return next((i for i in self.identities(todos=True) if i["id"] == ident_id), None)

    def save_identity(self, data: dict) -> int:
        with self.db.session() as s:
            i = s.get(AeIdentity, data.get("id")) if data.get("id") else None
            if i is None:
                i = AeIdentity()
                s.add(i)
            for f in self.IDENTITY_FIELDS:
                if f in data:
                    setattr(i, f, data[f])
            s.flush()
            return i.id

    def delete_identity(self, ident_id: int) -> None:
        with self.db.session() as s:
            i = s.get(AeIdentity, ident_id)
            if i is not None:
                s.delete(i)

    def audit(self, action: str, detail: str, user: str = "local", study_uid: str = "", host: str = "") -> None:
        log.info("Auditoria: %s %s — %s", user, action, detail)
        if not host:
            import socket
            host = socket.gethostname()
        try:
            with self.db.session() as s:
                s.add(AuditLog(action=action, detail=detail, user=user, study_uid=study_uid or None,
                               host=host or None))
        except Exception as e:  # noqa: BLE001
            log.warning("Falha ao gravar auditoria: %s", e)

    def audit_entries(self, limit: int = 200) -> list[tuple]:
        with self.db.session() as s:
            return [(a.at, a.user, a.action, a.detail) for a in
                    s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))]

    def access_log(self, limit: int = 500, user: str = "", action: str = "", study_uid: str = "",
                   text: str = "", since: datetime | None = None) -> list[dict]:
        """Registro de acesso com filtros (mais recentes primeiro)."""
        with self.db.session() as s:
            q = select(AuditLog).order_by(AuditLog.id.desc())
            if user:
                q = q.where(AuditLog.user == user)
            if action:
                q = q.where(AuditLog.action == action)
            if study_uid:
                q = q.where(AuditLog.study_uid == study_uid)
            if text:
                q = q.where(AuditLog.detail.ilike(f"%{text}%"))
            if since is not None:
                q = q.where(AuditLog.at >= since)
            return [{"at": a.at, "user": a.user, "action": a.action, "detail": a.detail,
                     "study_uid": a.study_uid or "", "host": a.host or ""} for a in s.scalars(q.limit(limit))]

    # ------------------------------------------------------- usuários
    @staticmethod
    def _user_dict(u: User) -> dict:
        return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
                "active": bool(u.active), "must_change": bool(u.must_change), "created": u.created,
                "last_login": u.last_login, "conta_sistema": u.conta_sistema or ""}

    def users(self) -> list[dict]:
        with self.db.session() as s:
            return [self._user_dict(u) for u in s.scalars(select(User).order_by(User.username))]

    def user_count(self) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count(User.id))) or 0

    def user_by_name(self, username: str) -> dict | None:
        with self.db.session() as s:
            u = s.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
            return self._user_dict(u) if u else None

    def user_by_conta_sistema(self, conta: str) -> dict | None:
        """O usuário ativo ligado a esta conta do Windows/Linux (0.99.25). Sem diferença de maiúsculas."""
        conta = str(conta or "").strip().lower()
        if not conta:
            return None
        with self.db.session() as s:
            for u in s.scalars(select(User).where(func.lower(User.conta_sistema) == conta)):
                if u.active:
                    return self._user_dict(u)
        return None

    def save_user(self, data: dict) -> int:
        """Cria/edita (username, full_name, role, active, must_change; "password" opcional)."""
        from ipe.auth.passwords import hash_password
        with self.db.session() as s:
            u = s.get(User, data.get("id")) if data.get("id") else None
            if u is None:
                other = s.scalar(select(User).where(func.lower(User.username) == data["username"].strip().lower()))
                if other is not None:
                    raise ValueError(f"Já existe o usuário {data['username']}.")
                u = User(username=data["username"].strip())
                s.add(u)
            for f in ("full_name", "role", "active", "must_change", "conta_sistema"):
                if f in data:
                    setattr(u, f, data[f])
            if data.get("password"):
                u.password_hash = hash_password(data["password"])
            s.flush()
            return u.id

    def set_password(self, user_id: int, password: str, must_change: bool = False) -> None:
        from ipe.auth.passwords import hash_password
        with self.db.session() as s:
            u = s.get(User, user_id)
            if u is not None:
                u.password_hash = hash_password(password)
                u.must_change = must_change

    def delete_user(self, user_id: int) -> None:
        with self.db.session() as s:
            u = s.get(User, user_id)
            if u is not None:
                s.delete(u)

    def authenticate(self, username: str, password: str) -> dict | None:
        """Confere usuário e senha (só ativos); grava o último acesso."""
        from ipe.auth.passwords import verify_password
        with self.db.session() as s:
            u = s.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
            if u is None or not u.active or not verify_password(password, u.password_hash):
                return None
            u.last_login = datetime.now()
            return self._user_dict(u)

    def user_prefs(self, user_id: int) -> dict:
        import json
        with self.db.session() as s:
            u = s.get(User, user_id)
            try:
                return json.loads(u.prefs or "{}") if u else {}
            except ValueError:
                return {}

    def save_user_prefs(self, user_id: int, prefs: dict) -> None:
        import json
        with self.db.session() as s:
            u = s.get(User, user_id)
            if u is not None:
                u.prefs = json.dumps(prefs, ensure_ascii=False, default=str)

    def get_app_setting(self, key: str, default=None):
        import json
        with self.db.session() as s:
            a = s.get(AppSetting, key)
            if a is None:
                return default
            try:
                return json.loads(a.value)
            except ValueError:
                return default

    def set_app_setting(self, key: str, value) -> None:
        import json
        with self.db.session() as s:
            a = s.get(AppSetting, key)
            if a is None:
                a = AppSetting(key=key)
                s.add(a)
            a.value = json.dumps(value, ensure_ascii=False)

    # ------------------------------------------------------- acompanhamento de lesões
    @staticmethod
    def _lesion_dict(le: Lesion) -> dict:
        import json
        try:
            data = json.loads(le.data or "{}")
        except ValueError:
            data = {}
        return {"id": le.id, "patient_id": le.patient_id, "name": le.name, "location": le.location,
                "kind": le.kind, "nodal": bool(le.nodal), "data": data}

    def lesions(self, patient_id: str) -> list[dict]:
        if not patient_id:
            return []
        with self.db.session() as s:
            return [self._lesion_dict(le) for le in
                    s.scalars(select(Lesion).where(Lesion.patient_id == patient_id).order_by(Lesion.id))]

    def save_lesion(self, data: dict) -> int:
        import json
        with self.db.session() as s:
            le = s.get(Lesion, data.get("id")) if data.get("id") else None
            if le is None:
                le = Lesion(patient_id=data.get("patient_id", ""))
                s.add(le)
            for k in ("name", "location", "kind"):
                if k in data:
                    setattr(le, k, str(data[k] or ""))
            if "nodal" in data:
                le.nodal = bool(data["nodal"])
            if "data" in data:
                le.data = json.dumps(data["data"] or {}, ensure_ascii=False)
            s.flush()
            return le.id

    def delete_lesion(self, lesion_id: int) -> None:
        with self.db.session() as s:
            le = s.get(Lesion, lesion_id)
            if le is not None:
                s.delete(le)

    def lesion_track(self, patient_id: str) -> dict:
        with self.db.session() as s:
            t = s.scalar(select(LesionTrack).where(LesionTrack.patient_id == patient_id))
            if t is None:
                return {"patient_id": patient_id, "criterion": "recist", "baseline_study": ""}
            return {"patient_id": patient_id, "criterion": t.criterion, "baseline_study": t.baseline_study}

    def save_lesion_track(self, patient_id: str, criterion: str | None = None,
                          baseline_study: str | None = None) -> None:
        with self.db.session() as s:
            t = s.scalar(select(LesionTrack).where(LesionTrack.patient_id == patient_id))
            if t is None:
                t = LesionTrack(patient_id=patient_id)
                s.add(t)
            if criterion is not None:
                t.criterion = criterion
            if baseline_study is not None:
                t.baseline_study = baseline_study

    def annotations_for_studies(self, study_uids: list[str]) -> list[dict]:
        if not study_uids:
            return []
        with self.db.session() as s:
            q = (select(AnnotationRecord).where(AnnotationRecord.study_uid.in_(list(study_uids)))
                 .order_by(AnnotationRecord.id))
            return [{"id": a.id, "study_uid": a.study_uid, "series_uid": a.series_uid,
                     "sop_uid": a.sop_uid, "frame_index": a.frame_index, "kind": a.kind,
                     "data": a.data} for a in s.scalars(q)]

    # ------------------------------------------------------- laudos
    @staticmethod
    def _report_dict(r: Report) -> dict:
        import json
        try:
            fields = json.loads(r.fields or "{}")
        except ValueError:
            fields = {}
        fmt = "%Y-%m-%d %H:%M"
        return {"id": r.id, "study_uid": r.study_uid, "template": r.template, "title": r.title,
                "status": r.status, "text": r.text, "fields": fields, "author": r.author,
                "signed_by": r.signed_by,
                "created_at": r.created_at.strftime(fmt) if r.created_at else "",
                "updated_at": r.updated_at.strftime(fmt) if r.updated_at else "",
                "signed_at": r.signed_at.strftime(fmt) if r.signed_at else ""}

    def reports(self, study_uid: str) -> list[dict]:
        with self.db.session() as s:
            return [self._report_dict(r) for r in
                    s.scalars(select(Report).where(Report.study_uid == study_uid).order_by(Report.id))]

    def report(self, report_id: int) -> dict | None:
        with self.db.session() as s:
            r = s.get(Report, report_id)
            return self._report_dict(r) if r is not None else None

    def save_report(self, data: dict) -> int:
        """Grava o rascunho. Um laudo assinado não muda (a retificação cria um laudo novo)."""
        import json
        with self.db.session() as s:
            r = s.get(Report, data.get("id")) if data.get("id") else None
            if r is not None and r.status != "draft":
                raise ValueError("Laudo já assinado: crie uma retificação.")
            if r is None:
                r = Report(study_uid=data["study_uid"])
                s.add(r)
            for k in ("template", "title", "text", "author"):
                if k in data:
                    setattr(r, k, str(data[k] or ""))
            if "fields" in data:
                r.fields = json.dumps(data["fields"] or {}, ensure_ascii=False)
            s.flush()
            return r.id

    def sign_report(self, report_id: int, signed_by: str, status: str = "final") -> dict | None:
        """Assina (libera) o laudo; depois disso ele não muda mais."""
        with self.db.session() as s:
            r = s.get(Report, report_id)
            if r is None:
                return None
            if r.status == "draft":
                r.status = status if status in ("final", "amended") else "final"
                r.signed_by = signed_by
                r.signed_at = datetime.now()
            s.flush()
            return self._report_dict(r)

    def report_templates(self) -> list[dict]:
        """Modelos de laudo (os de fábrica, se ninguém editou). 0.99.30: cada um vê os do serviço, os
        seus e os compartilhados com ele (core/itens.py)."""
        from ipe.auth import visibilidade as V
        from ipe.core import itens
        from ipe.reporting.templates import default_templates
        t = self.get_app_setting("report_templates", None)
        if not (isinstance(t, list) and t):
            return default_templates()
        # 0.99.31: modelo de fábrica novo (ex.: OIT) entra uma vez na lista de quem já editou a dele;
        # o que ele apagar depois não volta (fica em "report_templates_vistos")
        vistos = self.get_app_setting("report_templates_vistos", None)
        fabrica = default_templates()
        if not isinstance(vistos, list):
            vistos = [x.get("id") for x in fabrica if x.get("id") not in MODELOS_NOVOS]
        ids = {x.get("id") for x in t}
        novos = [x for x in fabrica if x.get("id") not in ids and x.get("id") not in vistos]
        if novos:
            t = list(t) + [{**x, "dono": "", "visivel_para": ""} for x in novos]
            self.set_app_setting("report_templates", t)
        if novos or len(vistos) != len(fabrica):
            self.set_app_setting("report_templates_vistos", [x.get("id") for x in fabrica])
        return [{k: v for k, v in x.items() if k not in itens.CAMPOS}
                for x in itens.visiveis("report_templates", t, V.visao_atual())]

    def save_report_templates(self, templates: list[dict]) -> list[str]:
        from ipe.core import itens
        from ipe.reporting.templates import default_templates
        fabrica = default_templates()
        avisos = itens.gravar(self, "report_templates", list(templates or []), fabrica)
        # quem grava já viu todos os de fábrica: o que ele tirou não volta (0.99.31)
        self.set_app_setting("report_templates_vistos", [x.get("id") for x in fabrica])
        return avisos

    # ------------------------------------------------------------------ trava de leitura (0.99.31)
    # Num computador só não há outro médico laudando ao mesmo tempo: a trava é do servidor central
    # (central/leituras.py). Aqui as chamadas respondem "pode".
    def leitura_comecar(self, study_uid: str, forcar: bool = False) -> dict:
        return {"ok": True}

    def leitura_manter(self, study_uids) -> int:
        return 0

    def leitura_terminar(self, study_uid: str) -> bool:
        return True

    def leituras_ativas(self) -> dict:
        return {}

    # ------------------------------------------------------------------ configurações em três níveis (0.99.30)
    def itens_de_config(self, chave: str, gerenciar: bool = False):
        from ipe.core import itens
        return itens.ler(self, chave, gerenciar)

    def salvar_itens_de_config(self, chave: str, editados, base=None) -> list[str]:
        from ipe.core import itens
        return itens.gravar(self, chave, editados, base)

    def adotar_itens_de_config(self, chave: str, pessoais, base=None) -> None:
        from ipe.core import itens
        itens.adotar(self, chave, pessoais, base)

    def escopo_de_item_de_config(self, chave: str, nome: str, dono_atual: str, novo_dono: str = "",
                                 visivel_para: str = "", copiar: bool = False, base=None) -> None:
        from ipe.core import itens
        if chave == "report_templates" and base is None:
            from ipe.reporting.templates import default_templates
            base = default_templates()
        itens.escopo(self, chave, nome, dono_atual, novo_dono, visivel_para, copiar=copiar, base=base)

    def delete_report(self, report_id: int) -> None:
        with self.db.session() as s:
            r = s.get(Report, report_id)
            if r is not None and r.status == "draft":
                s.delete(r)

    # ------------------------------------------------------------------ busca ativa (0.99.51, onda B8)
    @staticmethod
    def _busca_dict(b) -> dict:
        fmt = "%Y-%m-%d %H:%M"
        return {"id": b.id, "study_uid": b.study_uid, "report_id": b.report_id, "patient_id": b.patient_id,
                "patient_name": b.patient_name, "study_date": b.study_date, "modalidade": b.modalidade,
                "categoria": b.categoria, "motivo": b.motivo, "prazo": b.prazo, "estado": b.estado,
                "retorno_uid": b.retorno_uid, "historico": b.historico, "criado_por": b.criado_por,
                "criado_em": b.criado_em.strftime(fmt) if b.criado_em else "",
                "atualizado_em": b.atualizado_em.strftime(fmt) if b.atualizado_em else ""}

    def buscas_ativas(self, estados=None, study_uid: str = "") -> list[dict]:
        """Pedidos de busca ativa (por prazo); `estados` = só esses ("pendente", "contatado"…)."""
        with self.db.session() as s:
            q = select(BuscaAtiva)
            if estados:
                q = q.where(BuscaAtiva.estado.in_(list(estados)))
            if study_uid:
                q = q.where(BuscaAtiva.study_uid == study_uid)
            return [self._busca_dict(b) for b in s.scalars(q.order_by(BuscaAtiva.prazo, BuscaAtiva.id))]

    def criar_busca_ativa(self, item: dict) -> int:
        """Cria o pedido; se o exame já tem um aberto, ele é trocado (retificação do laudo)."""
        from ipe.reporting import busca_ativa as BA
        with self.db.session() as s:
            b = s.scalar(select(BuscaAtiva).where(BuscaAtiva.study_uid == item["study_uid"],
                                                  BuscaAtiva.estado.in_(BA.ABERTOS)))
            novo = b is None
            if novo:
                b = BuscaAtiva(study_uid=item["study_uid"])
                s.add(b)
            for k in ("report_id", "patient_id", "patient_name", "study_date", "modalidade", "categoria",
                      "motivo", "prazo", "criado_por"):
                if k in item and item[k] is not None:
                    setattr(b, k, item[k] if k == "report_id" else str(item[k]))
            acao = (f"pedido criado: {b.motivo}, prazo {BA.fmt(b.prazo)}" if novo
                    else f"laudo retificado: {b.motivo}, prazo {BA.fmt(b.prazo)}")
            b.historico = ((b.historico + "\n") if b.historico else "") + BA.linha(acao, item.get("criado_por", ""))
            b.atualizado_em = datetime.now()
            s.flush()
            return b.id

    def atualizar_busca_ativa(self, busca_id: int, estado: str = "", nota: str = "", usuario: str = "") -> dict | None:
        from ipe.reporting import busca_ativa as BA
        with self.db.session() as s:
            b = s.get(BuscaAtiva, busca_id)
            if b is None:
                return None
            partes = []
            if estado and estado in BA.ESTADOS and estado != b.estado:
                partes.append(f"{BA.ESTADOS.get(b.estado, b.estado)} → {BA.ESTADOS[estado]}")
                b.estado = estado
            if nota.strip():
                partes.append(nota.strip())
            if partes:
                b.historico = ((b.historico + "\n") if b.historico else "") + BA.linha(" — ".join(partes), usuario)
                b.atualizado_em = datetime.now()
            s.flush()
            return self._busca_dict(b)

    def encerrar_buscas_do_exame(self, study_uid: str, motivo: str, usuario: str = "") -> int:
        from ipe.reporting import busca_ativa as BA
        n = 0
        with self.db.session() as s:
            for b in s.scalars(select(BuscaAtiva).where(BuscaAtiva.study_uid == study_uid,
                                                        BuscaAtiva.estado.in_(BA.ABERTOS))):
                b.estado = "encerrado"
                b.historico = ((b.historico + "\n") if b.historico else "") + BA.linha(f"encerrada — {motivo}", usuario)
                b.atualizado_em = datetime.now()
                n += 1
        return n

    def conferir_retornos_busca_ativa(self) -> int:
        """Marca *retornou* quando o paciente já tem exame de mama novo (data ≥ e chegou depois do pedido)."""
        from ipe.reporting import busca_ativa as BA
        n = 0
        with self.db.session() as s:
            abertos = list(s.scalars(select(BuscaAtiva).where(BuscaAtiva.estado.in_(BA.ABERTOS))))
            for b in abertos:
                if not b.patient_id:
                    continue
                q = (select(Study).join(Patient, Study.patient_fk == Patient.id)
                     .where(Patient.patient_id == b.patient_id, Study.study_uid != b.study_uid,
                            Study.study_date >= (b.study_date or "")))
                for st in s.scalars(q.order_by(Study.study_date)):
                    if st.date_added is not None and b.criado_em is not None and st.date_added <= b.criado_em:
                        continue
                    if not BA.exame_de_retorno({"modalities": st.modalities, "description": st.description}):
                        continue
                    b.estado, b.retorno_uid = "retornou", st.study_uid
                    b.historico = ((b.historico + "\n") if b.historico else "") + BA.linha(
                        f"retornou: exame de {BA.fmt(st.study_date)} ({st.modalities} {st.description})".strip(),
                        "Ipê")
                    b.atualizado_em = datetime.now()
                    n += 1
                    break
        return n

    def busca_ativa_por_exame(self, study_uids) -> dict[str, str]:
        """{exame: estado do pedido mais recente}."""
        uids = list(study_uids or [])
        if not uids:
            return {}
        out: dict[str, str] = {}
        with self.db.session() as s:
            for uid, est in s.execute(select(BuscaAtiva.study_uid, BuscaAtiva.estado)
                                      .where(BuscaAtiva.study_uid.in_(uids)).order_by(BuscaAtiva.id)):
                out[uid] = est
        return out

    # ------------------------------------------------------------------ produtividade (0.99.53, onda B6)
    def produtividade_dados(self, de: str, ate: str) -> list[dict]:
        """Um item por laudo assinado entre `de` e `ate` (AAAA-MM-DD, inclusive): quem assinou, quando, a
        modalidade, a subespecialidade, a prioridade, as horas da chegada à assinatura e se foi no prazo."""
        from ipe.core import sla as SLA
        cfg = SLA.config(self)
        ini = datetime.strptime(de, "%Y-%m-%d")
        fim = datetime.strptime(ate, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        out = []
        with self.db.session() as s:
            q = (select(Report, Study).join(Study, Study.study_uid == Report.study_uid)
                 .where(Report.status != "draft", Report.signed_at.is_not(None),
                        Report.signed_at >= ini, Report.signed_at <= fim).order_by(Report.signed_at))
            for r, st in s.execute(q):
                res = SLA.resolver({"description": st.description or "", "modalities": st.modalities or "",
                                    "prioridade_manual": st.prioridade or "",
                                    "subesp_manual": st.subespecialidade or "", "chegada": st.date_added,
                                    "laudado_em": r.signed_at}, cfg)
                horas = ((r.signed_at - st.date_added).total_seconds() / 3600
                         if st.date_added is not None else None)
                out.append({"medico": r.signed_by or "—", "assinado_em": r.signed_at.strftime("%Y-%m-%d %H:%M"),
                            "dia": r.signed_at.strftime("%Y-%m-%d"), "study_uid": r.study_uid,
                            "modalidade": (st.modalities or "").split("\\")[0] or "—",
                            "subesp": res["subesp"], "prioridade": res["prioridade"],
                            "retificacao": r.status == "amended", "horas": horas,
                            "no_prazo": res["sla_estado"] == "no_prazo"})
        return out

    def report_counts(self, study_uids: list[str]) -> dict[str, str]:
        """Estado do laudo por estudo: "final" se houver assinado, senão "draft"."""
        if not study_uids:
            return {}
        out: dict[str, str] = {}
        with self.db.session() as s:
            for uid, st in s.execute(select(Report.study_uid, Report.status)
                                     .where(Report.study_uid.in_(list(study_uids)))):
                if st != "draft" or uid not in out:
                    out[uid] = st
        return out

    def study_uids_present(self, uids: list[str]) -> set[str]:
        if not uids:
            return set()
        with self.db.session() as s:
            return set(s.scalars(select(Study.study_uid).where(Study.study_uid.in_(list(uids)))))

    def sop_uids_for_study(self, study_uid: str) -> list[str]:
        with self.db.session() as s:
            q = (select(Instance.sop_uid).join(Series, Instance.series_fk == Series.id)
                 .join(Study, Series.study_fk == Study.id).where(Study.study_uid == study_uid))
            return list(s.scalars(q))

    def files_with_sops(self, study_uid: str) -> list[tuple[str, str]]:
        with self.db.session() as s:
            q = (select(Instance.sop_uid, Instance.file_path).join(Series, Instance.series_fk == Series.id)
                 .join(Study, Series.study_fk == Study.id).where(Study.study_uid == study_uid))
            return [(a, b) for a, b in s.execute(q)]

    def paths_for_sops(self, sop_uids: list[str]) -> dict[str, str]:
        if not sop_uids:
            return {}
        with self.db.session() as s:
            q = select(Instance.sop_uid, Instance.file_path).where(Instance.sop_uid.in_(list(sop_uids)))
            return {a: b for a, b in s.execute(q)}

    def instance_counts(self, study_uids: list[str]) -> dict[str, int]:
        if not study_uids:
            return {}
        with self.db.session() as s:
            q = (select(Study.study_uid, func.count(Instance.id)).join(Series, Series.study_fk == Study.id)
                 .join(Instance, Instance.series_fk == Series.id)
                 .where(Study.study_uid.in_(list(study_uids))).group_by(Study.study_uid))
            return {u: n for u, n in s.execute(q)}

    def assinatura_dos_exames(self, study_uids: list[str]) -> dict[str, tuple[int, int]]:
        """(séries, imagens) de cada exame: o visualizador compara de tempos em tempos para saber
        se chegou série nova (tabela, SEG, captura, imagens da rede) e refazer a tira (0.99.4)."""
        if not study_uids:
            return {}
        with self.db.session() as s:
            q = (select(Study.study_uid, func.count(func.distinct(Series.id)), func.count(Instance.id))
                 .join(Series, Series.study_fk == Study.id)
                 .outerjoin(Instance, Instance.series_fk == Series.id)
                 .where(Study.study_uid.in_(list(study_uids))).group_by(Study.study_uid))
            return {u: (int(a), int(b)) for u, a, b in s.execute(q)}

    def series_instance_counts(self, series_uids: list[str]) -> dict[str, int]:
        """Quantas imagens de cada série já estão no banco (status por série na busca do PACS)."""
        if not series_uids:
            return {}
        with self.db.session() as s:
            q = (select(Series.series_uid, func.count(Instance.id))
                 .join(Instance, Instance.series_fk == Series.id)
                 .where(Series.series_uid.in_(list(series_uids))).group_by(Series.series_uid))
            return {u: n for u, n in s.execute(q)}

    def files_for_study(self, study_uid: str, series_uids: list[str] | None = None) -> list[str]:
        with self.db.session() as s:
            q = (select(Instance.file_path).join(Series, Instance.series_fk == Series.id)
                 .join(Study, Series.study_fk == Study.id).where(Study.study_uid == study_uid))
            if series_uids:
                q = q.where(Series.series_uid.in_(list(series_uids)))
            return list(s.scalars(q))

    # ------------------------------------------------------- anteriores
    def other_studies_same_patient(self, study_uid: str) -> list[StudyRow]:
        with self.db.session() as s:
            st = s.scalar(select(Study).where(Study.study_uid == study_uid))
            if st is None:
                return []
            pid = st.patient.patient_id
        if not pid:
            return []
        # filtra pelo ID já na busca (antes lia o banco inteiro a cada pedido); "|" separaria termos
        texto = pid if "|" not in pid else ""
        rows = [r for r in self.search_studies(text=texto, limit=10000)
                if r.patient_id == pid and r.study_uid != study_uid]
        return rows

    def counts(self) -> dict[str, int]:
        with self.db.session() as s:
            return {
                "patients": s.scalar(select(func.count(Patient.id))) or 0,
                "studies": s.scalar(select(func.count(Study.id))) or 0,
                "series": s.scalar(select(func.count(Series.id))) or 0,
                "instances": s.scalar(select(func.count(Instance.id))) or 0,
            }


def _safe(uid: str) -> str:
    return "".join(c for c in uid if c.isalnum() or c in ".-_")[:64] or "unknown"
