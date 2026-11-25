"""0.100.117: conferir e reconstruir o banco — como o *Rebuild Database* do OsiriX/Horos, sem perder o que só existe
no Ipê.

Pedido dele (25/11/2026): *"crie uma opção de reconstruir o banco de dados, como no OsiriX/Horos. acho que tem como
reconstruir o BD parcialmente ou reimportar tudo"* — e aprovou: conferir primeiro (relatório, sem mudar nada),
reconstrução parcial e completa; sem o "do zero".

O índice das imagens são as tabelas patient, study, series e instance. Todo o resto (comentários, listas, medidas,
imagens-chave, laudos, IA, links…) se liga ao exame pelo UID — por isso a reconstrução mexe só no índice e nunca
apaga o que o médico criou.

- `conferir`: imagens cujo arquivo sumiu (no Storage / referenciadas), arquivos do Storage fora do banco, séries e
  exames vazios, pacientes sem exame, séries sem miniatura e pastas vazias. Não muda nada.
- `parcial`: a partir do relatório — indexa os arquivos do Storage que estão fora; tira os registros dos arquivos que
  sumiram do Storage (os referenciados só se pedir: disco externo desligado volta); séries/exames que ficaram vazios
  saem do índice (os comentários, listas, laudos… do exame ficam); pacientes sem exame; miniaturas; pastas vazias.
- `completa`: relê o cabeçalho de todos os arquivos e atualiza o índice (paciente, exame, série, imagem). Antes,
  `copia_do_indice` grava as quatro tabelas num .json.gz (`restaurar_indice` volta). Retoma de onde parou.

Sem Qt.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, exists, func, select

from ipe.db.models import Instance, Patient, Series, Study

log = logging.getLogger(__name__)

CHAVE_RETOMAR = "banco.reconstrucao_completa"            # {"ultimo_exame": id, "inicio": iso}
PASTAS_IGNORADAS = {".chegando"}                          # passagem do modo cliente
LOTE = 2000
DERIVADAS = {"SR", "PR", "KO", "OT", "SEG", "DOC", "RTSTRUCT"}


class Cancelado(Exception):
    pass


@dataclass
class Relatorio:
    imagens: int = 0
    faltando_storage: list[int] = field(default_factory=list)       # ids de instance
    faltando_ref: list[int] = field(default_factory=list)
    caminhos_faltando_ref: list[str] = field(default_factory=list)
    arquivos_fora: list[str] = field(default_factory=list)          # no Storage, fora do banco
    series_vazias: list[int] = field(default_factory=list)
    exames_vazios: list[int] = field(default_factory=list)
    pacientes_sem_exame: int = 0
    sem_miniatura: list[str] = field(default_factory=list)          # series_uid
    pastas_vazias: list[str] = field(default_factory=list)
    segundos: float = 0.0

    @property
    def problemas(self) -> int:
        return (len(self.faltando_storage) + len(self.faltando_ref) + len(self.arquivos_fora)
                + len(self.series_vazias) + len(self.exames_vazios) + self.pacientes_sem_exame
                + len(self.sem_miniatura) + len(self.pastas_vazias))

    def linhas(self) -> list[tuple[str, int]]:
        return [
            ("Imagens no banco", self.imagens),
            ("Imagens do Storage cujo arquivo sumiu", len(self.faltando_storage)),
            ("Imagens referenciadas (fora do Storage) cujo arquivo não está lá", len(self.faltando_ref)),
            ("Arquivos no Storage que não estão no banco", len(self.arquivos_fora)),
            ("Séries sem nenhuma imagem", len(self.series_vazias)),
            ("Exames sem nenhuma série", len(self.exames_vazios)),
            ("Pacientes sem exame", self.pacientes_sem_exame),
            ("Séries sem miniatura", len(self.sem_miniatura)),
            ("Pastas vazias no Storage", len(self.pastas_vazias)),
        ]

    def texto(self) -> str:
        """Para gravar (os caminhos ficam aqui, não na tela)."""
        out = [f"Ipê — conferência do banco ({datetime.now():%d/%m/%Y %H:%M})", ""]
        out += [f"{n:>9}  {t}" for t, n in self.linhas()]
        if self.arquivos_fora:
            out += ["", "Arquivos no Storage fora do banco:"] + self.arquivos_fora
        if self.caminhos_faltando_ref:
            out += ["", "Arquivos referenciados que não estão no lugar:"] + self.caminhos_faltando_ref
        return "\n".join(out) + "\n"


def _passo(progresso, feito: int, total: int, msg: str, parar) -> None:
    if parar is not None and parar.is_set():
        raise Cancelado()
    if progresso is not None:
        progresso(feito, total, msg)


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def conferir(db, storage, progresso=None, parar=None) -> Relatorio:
    """O relatório; não muda nada."""
    t0 = time.monotonic()
    rel = Relatorio()
    storage = Path(storage)
    conhecidos: set[str] = set()
    with db.session() as s:
        rel.imagens = int(s.scalar(select(func.count(Instance.id))) or 0)
        feito, ultimo = 0, 0
        while True:
            linhas = s.execute(select(Instance.id, Instance.file_path, Instance.in_storage)
                               .where(Instance.id > ultimo).order_by(Instance.id).limit(LOTE)).all()
            if not linhas:
                break
            for iid, caminho, no_storage in linhas:
                if no_storage:
                    conhecidos.add(_norm(caminho))
                if not caminho or not os.path.exists(caminho):
                    (rel.faltando_storage if no_storage else rel.faltando_ref).append(iid)
                    if not no_storage and len(rel.caminhos_faltando_ref) < 5000:
                        rel.caminhos_faltando_ref.append(str(caminho))
            ultimo = linhas[-1][0]
            feito += len(linhas)
            _passo(progresso, feito, rel.imagens, "conferindo as imagens do banco…", parar)
        rel.series_vazias = list(s.scalars(select(Series.id).where(~exists().where(Instance.series_fk == Series.id))))
        rel.exames_vazios = list(s.scalars(select(Study.id).where(~exists().where(Series.study_fk == Study.id))))
        rel.pacientes_sem_exame = int(s.scalar(select(func.count(Patient.id))
                                               .where(~exists().where(Study.patient_fk == Patient.id))) or 0)
        rel.sem_miniatura = list(s.scalars(select(Series.series_uid).where(
            Series.thumbnail.is_(None), exists().where(Instance.series_fk == Series.id))))
    if storage.is_dir():
        n = 0
        for raiz, pastas, arquivos in os.walk(storage):
            pastas[:] = [p for p in pastas if p not in PASTAS_IGNORADAS]
            for a in arquivos:
                if a.lower().endswith(".dcm"):
                    caminho = os.path.join(raiz, a)
                    if _norm(caminho) not in conhecidos:
                        rel.arquivos_fora.append(caminho)
            if raiz != str(storage) and not pastas and not arquivos:
                rel.pastas_vazias.append(raiz)
            n += 1
            if n % 200 == 0:
                _passo(progresso, 0, 0, "conferindo os arquivos do Storage…", parar)
    rel.segundos = time.monotonic() - t0
    return rel


def _apagar_vazios(s) -> tuple[int, int, int]:
    """Séries sem imagem, exames sem série e pacientes sem exame — só o índice: os comentários, listas, laudos… do
    exame ficam (ligados pelo UID, voltam se o exame voltar)."""
    a = s.execute(delete(Series).where(~exists().where(Instance.series_fk == Series.id))
                  .execution_options(synchronize_session=False)).rowcount or 0
    b = s.execute(delete(Study).where(~exists().where(Series.study_fk == Study.id))
                  .execution_options(synchronize_session=False)).rowcount or 0
    c = s.execute(delete(Patient).where(~exists().where(Study.patient_fk == Patient.id))
                  .execution_options(synchronize_session=False)).rowcount or 0
    return int(a), int(b), int(c)


def _modalidades(s, ids_exames=None) -> None:
    """Refaz o "CT\\PT" dos exames pelas séries."""
    q = select(Study)
    if ids_exames is not None:
        if not ids_exames:
            return
        q = q.where(Study.id.in_(list(ids_exames)))
    for st in s.scalars(q):
        mods = sorted({(m or "").strip() for m in s.scalars(select(Series.modality).where(Series.study_fk == st.id))
                       if (m or "").strip()})
        texto = "\\".join(mods)[:64]
        if texto and st.modalities != texto:
            st.modalities = texto


def parcial(repo, db, storage, rel: Relatorio, remover_referenciados: bool = False, progresso=None,
            parar=None) -> dict:
    """Conserta o que o relatório achou. Devolve o que fez."""
    from ipe.importer.scanner import Importer
    out = {"indexadas": 0, "removidas": 0, "series": 0, "exames": 0, "pacientes": 0, "miniaturas": 0, "pastas": 0}
    if rel.arquivos_fora:
        _passo(progresso, 0, len(rel.arquivos_fora), "indexando os arquivos do Storage…", parar)
        imp = Importer(db, Path(storage), copy_to_storage=True, mover=True, origin="import")
        for i in range(0, len(rel.arquivos_fora), 500):
            parte = [Path(p) for p in rel.arquivos_fora[i:i + 500] if os.path.exists(p)]
            r = imp.import_paths(parte)
            out["indexadas"] += int(getattr(r, "added", 0) or 0)
            _passo(progresso, min(i + 500, len(rel.arquivos_fora)), len(rel.arquivos_fora),
                   "indexando os arquivos do Storage…", parar)
    ids = list(rel.faltando_storage) + (list(rel.faltando_ref) if remover_referenciados else [])
    afetados: set[int] = set()
    with db.session() as s:
        for i in range(0, len(ids), LOTE):
            parte = ids[i:i + LOTE]
            # confere de novo: o arquivo pode ter voltado (disco religado) entre a conferência e agora
            linhas = s.execute(select(Instance.id, Instance.file_path, Series.study_fk)
                               .join(Series, Instance.series_fk == Series.id).where(Instance.id.in_(parte))).all()
            sumiram = [iid for iid, caminho, _ in linhas if not caminho or not os.path.exists(caminho)]
            afetados.update(st for iid, _c, st in linhas if iid in set(sumiram))
            if sumiram:
                s.execute(delete(Instance).where(Instance.id.in_(sumiram)).execution_options(synchronize_session=False))
            out["removidas"] += len(sumiram)
            _passo(progresso, min(i + LOTE, len(ids)), len(ids), "tirando do banco o que sumiu…", parar)
        s.flush()
        out["series"], out["exames"], out["pacientes"] = _apagar_vazios(s)
        _modalidades(s, afetados)
    if rel.sem_miniatura:
        from ipe.importer.thumbnails import generate_thumbnails
        for i in range(0, len(rel.sem_miniatura), 50):
            try:
                out["miniaturas"] += int(generate_thumbnails(repo, rel.sem_miniatura[i:i + 50]) or 0)
            except Exception as e:  # noqa: BLE001
                log.warning("miniaturas na reconstrução: %s", e)
            _passo(progresso, min(i + 50, len(rel.sem_miniatura)), len(rel.sem_miniatura), "miniaturas…", parar)
    # pastas vazias: as que a conferência achou e as que esvaziaram agora (arquivo solto que foi para o lugar)
    storage = Path(storage)
    if storage.is_dir():
        for raiz, pastas, arquivos in os.walk(storage, topdown=False):
            if raiz == str(storage) or any(p in PASTAS_IGNORADAS for p in Path(raiz).relative_to(storage).parts):
                continue
            try:
                if not os.listdir(raiz):
                    os.rmdir(raiz)
                    out["pastas"] += 1
            except OSError:
                pass
    try:
        repo.audit("banco_reconstrucao_parcial", json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return out


# ------------------------------------------------------------------ cópia do índice
_TABELAS = ((Patient, "patient"), (Study, "study"), (Series, "series"), (Instance, "instance"))


def _valor(v):
    if isinstance(v, datetime):
        return {"__dt__": v.isoformat()}
    if isinstance(v, (bytes, bytearray)):
        import base64
        return {"__b64__": base64.b64encode(bytes(v)).decode()}
    return v


def _de_volta(v):
    if isinstance(v, dict) and "__dt__" in v:
        return datetime.fromisoformat(v["__dt__"])
    if isinstance(v, dict) and "__b64__" in v:
        import base64
        return base64.b64decode(v["__b64__"])
    return v


def copia_do_indice(db, pasta, progresso=None) -> Path:
    """As quatro tabelas do índice num .json.gz (uma linha por registro). As miniaturas ficam de fora (refazem)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"indice-{datetime.now():%Y%m%d-%H%M%S}.json.gz"
    with gzip.open(destino, "wt", encoding="utf-8") as f, db.session() as s:
        for modelo, nome in _TABELAS:
            colunas = [c.name for c in modelo.__table__.columns if c.name != "thumbnail"]
            ultimo = 0
            while True:
                linhas = s.execute(select(*[modelo.__table__.c[c] for c in colunas])
                                   .where(modelo.__table__.c.id > ultimo).order_by(modelo.__table__.c.id)
                                   .limit(LOTE)).all()
                if not linhas:
                    break
                for ln in linhas:
                    f.write(json.dumps({"t": nome, "d": {c: _valor(v) for c, v in zip(colunas, ln)}},
                                       ensure_ascii=False) + "\n")
                ultimo = linhas[-1][0]
                if progresso is not None:
                    progresso(0, 0, f"cópia do índice ({nome})…")
    return destino


def restaurar_indice(db, arquivo) -> dict:
    """Volta o índice da cópia: apaga as quatro tabelas e grava as linhas (com os mesmos números)."""
    from sqlalchemy import insert, text
    contagem = {n: 0 for _m, n in _TABELAS}
    lotes: dict[str, list] = {n: [] for _m, n in _TABELAS}
    modelos = {n: m for m, n in _TABELAS}
    with db.session() as s:
        for modelo, _n in reversed(_TABELAS):
            s.execute(delete(modelo))

        def descarregar(nome):
            if lotes[nome]:
                s.execute(insert(modelos[nome]), lotes[nome])
                contagem[nome] += len(lotes[nome])
                lotes[nome] = []
        with gzip.open(arquivo, "rt", encoding="utf-8") as f:
            ordem = [n for _m, n in _TABELAS]
            atual = 0
            for ln in f:
                x = json.loads(ln)
                i = ordem.index(x["t"])
                while i > atual:                 # tabela nova: grava o resto da anterior (as chaves estrangeiras)
                    descarregar(ordem[atual])
                    atual += 1
                lotes[x["t"]].append({k: _de_volta(v) for k, v in x["d"].items()})
                if len(lotes[x["t"]]) >= LOTE:
                    descarregar(x["t"])
            for n in ordem:
                descarregar(n)
        if s.get_bind().dialect.name == "postgresql":
            for _m, n in _TABELAS:
                s.execute(text(f"SELECT setval(pg_get_serial_sequence('{n}', 'id'), "
                               f"COALESCE((SELECT MAX(id) FROM {n}), 1))"))
    return contagem


# ------------------------------------------------------------------ completa
def _s(ds, k: str) -> str:
    from ipe.importer.scanner import _s as s_
    return s_(ds, k)


def completa(repo, db, storage, pasta_copias, progresso=None, parar=None, settings=None,
             recomecar: bool = False) -> dict:
    """Relê o cabeçalho de todas as imagens e atualiza o índice. Retoma de onde parou (settings)."""
    import pydicom

    from ipe.importer.scanner import _i, person_name, series_details
    out = {"exames": 0, "series": 0, "imagens": 0, "ilegiveis": 0, "pacientes_trocados": 0, "copia": "",
           "retomou": False}
    estado = (settings.get(CHAVE_RETOMAR, {}) if settings is not None else {}) or {}
    ultimo = 0 if recomecar else int(estado.get("ultimo_exame") or 0)
    if ultimo:
        out["retomou"] = True
        out["copia"] = str(estado.get("copia") or "")
    else:
        out["copia"] = str(copia_do_indice(db, pasta_copias, progresso))
    if settings is not None:
        settings.set(CHAVE_RETOMAR, {"ultimo_exame": ultimo, "copia": out["copia"],
                                     "inicio": estado.get("inicio") or datetime.now().isoformat(timespec="seconds")})
    with db.session() as s:
        total = int(s.scalar(select(func.count(Study.id))) or 0)
        ja = int(s.scalar(select(func.count(Study.id)).where(Study.id <= ultimo)) or 0)
    feitos = ja
    while True:
        with db.session() as s:
            st = s.scalar(select(Study).where(Study.id > ultimo).order_by(Study.id).limit(1))
            if st is None:
                break
            ultimo = st.id
            primeiro_do_exame = None
            for se in s.scalars(select(Series).where(Series.study_fk == st.id)):
                primeiro = None
                for inst in s.scalars(select(Instance).where(Instance.series_fk == se.id)):
                    if parar is not None and parar.is_set():
                        raise Cancelado()
                    try:
                        ds = pydicom.dcmread(inst.file_path, stop_before_pixels=True)
                    except Exception:  # noqa: BLE001 - sumiu ou não é DICOM: a conferência cuida
                        out["ilegiveis"] += 1
                        continue
                    if _s(ds, "SOPInstanceUID") != inst.sop_uid:
                        out["ilegiveis"] += 1               # o arquivo no lugar é outro: não mexe
                        continue
                    inst.sop_class_uid = _s(ds, "SOPClassUID") or inst.sop_class_uid
                    inst.instance_number = _i(ds, "InstanceNumber")
                    inst.rows, inst.columns = _i(ds, "Rows"), _i(ds, "Columns")
                    inst.number_of_frames = max(1, _i(ds, "NumberOfFrames", 1))
                    inst.image_position = _s(ds, "ImagePositionPatient")[:128]
                    inst.image_orientation = _s(ds, "ImageOrientationPatient")[:256]
                    try:
                        inst.slice_location = float(ds.SliceLocation) if "SliceLocation" in ds else None
                    except (TypeError, ValueError):
                        inst.slice_location = None
                    inst.acquisition_time = _s(ds, "AcquisitionTime")[:16]
                    try:
                        inst.file_size = os.path.getsize(inst.file_path)
                    except OSError:
                        pass
                    if getattr(ds, "file_meta", None) is not None:
                        inst.transfer_syntax = _s(ds.file_meta, "TransferSyntaxUID") or inst.transfer_syntax
                    out["imagens"] += 1
                    if primeiro is None:
                        primeiro = ds
                if primeiro is not None:
                    ds = primeiro
                    se.modality = _s(ds, "Modality")[:16] or se.modality
                    se.series_number = _i(ds, "SeriesNumber")
                    se.description = _s(ds, "SeriesDescription")[:256]
                    se.body_part = _s(ds, "BodyPartExamined")[:64]
                    se.laterality = (_s(ds, "ImageLaterality") or _s(ds, "Laterality"))[:4]
                    se.frame_of_reference = _s(ds, "FrameOfReferenceUID")[:64]
                    se.operators, se.station, se.device = series_details(ds)
                    out["series"] += 1
                    # os dados do exame e do paciente vêm de uma imagem "de verdade", não do resultado da IA
                    derivada = _s(ds, "Modality") in DERIVADAS
                    if primeiro_do_exame is None or (not derivada and _s(primeiro_do_exame, "Modality") in DERIVADAS):
                        primeiro_do_exame = ds
            if primeiro_do_exame is not None:
                ds = primeiro_do_exame
                st.study_date = _s(ds, "StudyDate")[:8]
                st.study_time = _s(ds, "StudyTime")[:16]
                st.accession = _s(ds, "AccessionNumber")[:64]
                st.description = _s(ds, "StudyDescription")[:256]
                st.referring = person_name(ds, "ReferringPhysicianName")[:256]
                st.institution = _s(ds, "InstitutionName")[:256]
                st.patient_age = _s(ds, "PatientAge")[:8]
                chave = (_s(ds, "PatientID")[:64], _s(ds, "IssuerOfPatientID")[:64],
                         person_name(ds, "PatientName")[:256], _s(ds, "PatientBirthDate")[:8])
                p = s.get(Patient, st.patient_fk)
                if p is not None and (p.patient_id, p.issuer, p.name, p.birth_date) != chave:
                    outro = s.scalar(select(Patient).where(Patient.patient_id == chave[0], Patient.issuer == chave[1],
                                                           Patient.name == chave[2], Patient.birth_date == chave[3]))
                    if outro is None:
                        outro = Patient(patient_id=chave[0], issuer=chave[1], name=chave[2], birth_date=chave[3],
                                        sex=_s(ds, "PatientSex")[:16])
                        s.add(outro)
                        s.flush()
                    st.patient_fk = outro.id
                    out["pacientes_trocados"] += 1
                elif p is not None:
                    p.sex = _s(ds, "PatientSex")[:16] or p.sex
                s.flush()
                _modalidades(s, [st.id])
            out["exames"] += 1
        feitos += 1
        if settings is not None:
            settings.set(CHAVE_RETOMAR, {**(settings.get(CHAVE_RETOMAR, {}) or {}), "ultimo_exame": ultimo})
        _passo(progresso, feitos, total, "relendo os arquivos…", parar)
    with db.session() as s:
        s.execute(delete(Patient).where(~exists().where(Study.patient_fk == Patient.id))
                  .execution_options(synchronize_session=False))
    if settings is not None:
        settings.set(CHAVE_RETOMAR, {})
    try:
        repo.audit("banco_reconstrucao_completa", json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
    return out


def em_andamento(settings) -> dict:
    """A reconstrução completa que parou no meio ({} = nenhuma)."""
    d = settings.get(CHAVE_RETOMAR, {}) if settings is not None else {}
    return dict(d) if isinstance(d, dict) and d.get("ultimo_exame") else {}
