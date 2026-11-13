"""Importação de arquivos DICOM: pastas, arquivos soltos, CD (DICOMDIR) e compactados (ZIP, RAR, 7z…).

- Lê só o cabeçalho (stop_before_pixels) para indexar rápido.
- Deduplica pelo SOPInstanceUID.
- Copia para Storage/<StudyUID>/<SeriesUID>/<SOPUID>.dcm ou apenas referencia
  o arquivo no local original (configurável).
- Não depende de Qt: pode rodar na linha de comando, em thread ou no servidor.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

import pydicom
from pydicom.errors import InvalidDicomError
from sqlalchemy import select

from ipe.db.models import Instance, KeyImage, Patient, Series, Study
from ipe.db.session import Database

log = logging.getLogger(__name__)

DICOMDIR_CLASS = "1.2.840.10008.1.3.10"
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
# Captura de tela da estação de medicina nuclear (Xeleris e afins): sai como Secondary
# Capture colorida dentro de um exame NM/PT. É a folha que vai para o paciente e para o
# solicitante, então entra como imagem-chave sozinha, sem ninguém precisar marcar.
AUTO_KEY_MODALITIES = {"NM", "PT"}
SKIP_NAMES = {"dicomdir", "thumbs.db", "desktop.ini", ".ds_store"}
SKIP_SUFFIXES = {".txt", ".pdf", ".exe", ".dll", ".html", ".htm", ".xml", ".ini",
                 ".inf", ".jpg", ".png", ".js", ".css", ".jar", ".bat", ".sh", ".json"}

ProgressFn = Callable[[int, int, str], None]


@dataclass
class ImportResult:
    added: int = 0
    duplicates: int = 0
    not_dicom: int = 0
    errors: int = 0
    new_series: set[str] = field(default_factory=set)
    new_studies: set[str] = field(default_factory=set)
    studies: set[str] = field(default_factory=set)      # todos os estudos vistos (novos ou já no banco)
    error_files: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.added} imagens importadas em {len(self.new_studies)} estudo(s); "
                f"{self.duplicates} já existiam; {self.not_dicom} arquivos não DICOM; "
                f"{self.errors} com erro.")


# --------------------------------------------------------------------- util

def _s(ds, keyword: str, default: str = "") -> str:
    v = ds.get(keyword, None)
    if v is None or v == "":
        return default
    try:
        if hasattr(v, "value"):
            v = v.value
        if isinstance(v, (list, tuple, pydicom.multival.MultiValue)):
            return "\\".join(str(x) for x in v)
        return str(v).strip()
    except Exception:  # valor mal codificado não pode derrubar a importação
        return default


def _i(ds, keyword: str, default: int = 0) -> int:
    try:
        v = ds.get(keyword, None)
        return int(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _f(ds, keyword: str) -> float | None:
    try:
        v = ds.get(keyword, None)
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def person_names(ds, keyword: str) -> str:
    """Campo com vários nomes (ex.: Operators' Name) -> "Sobrenome, Nome; Outro"."""
    v = ds.get(keyword, None)
    if v is None or v == "":
        return ""
    vals = v if isinstance(v, (list, tuple, pydicom.multival.MultiValue)) else [v]
    out = []
    for x in vals:
        parts = [p.strip() for p in str(x).split("=")[0].split("^")]
        name = f"{parts[0]}, {' '.join(p for p in parts[1:] if p)}".strip(", ") if len(parts) > 1 else parts[0]
        if name and name not in out:
            out.append(name)
    return "; ".join(out)


def is_workstation_capture(ds, sop_class: str) -> bool:
    """Captura de tela da estação de medicina nuclear — a folha do laudo.

    Reconhecida pelo que ela é no padrão, não pelo texto da descrição: exame de MN ou PET
    gravado como Secondary Capture pela estação de trabalho (ConversionType WSD). Serve para
    qualquer fabricante, não só para o "ScreenCap" da GE.
    """
    if sop_class != SECONDARY_CAPTURE:
        return False
    if _s(ds, "Modality").upper() not in AUTO_KEY_MODALITIES:
        return False
    tipo = " ".join(str(x).upper() for x in (ds.get("ImageType") or []))
    conv = _s(ds, "ConversionType").upper()
    return conv == "WSD" or "SECONDARY" in tipo


def series_details(ds) -> tuple[str, str, str]:
    """(operadores, estação, aparelho) de um cabeçalho."""
    device = " ".join(x for x in (_s(ds, "Manufacturer"), _s(ds, "ManufacturerModelName")) if x)
    return person_names(ds, "OperatorsName"), _s(ds, "StationName"), device


def person_name(ds, keyword: str) -> str:
    raw = _s(ds, keyword)
    # DICOM: Sobrenome^Nome^Meio=ideográfico=fonético -> "Sobrenome, Nome Meio"
    parts = [p.strip() for p in raw.split("=")[0].split("^")]
    if len(parts) > 1 and parts[1]:
        return f"{parts[0]}, {' '.join(p for p in parts[1:] if p)}".strip(", ")
    return parts[0] if parts else ""


def safe_name(uid: str) -> str:
    return "".join(c for c in uid if c.isalnum() or c in ".-_")[:64] or "unknown"


def iter_candidate_files(paths: Iterable[Path]) -> Iterator[Path]:
    for p in paths:
        p = Path(p)
        if p.is_file():
            yield p
        elif p.is_dir():
            for root, _dirs, files in os.walk(p):
                for name in files:
                    low = name.lower()
                    if low in SKIP_NAMES or Path(low).suffix in SKIP_SUFFIXES:
                        continue
                    yield Path(root) / name


# ---------------------------------------------------------------- importer

class Importer:
    def __init__(self, db: Database, storage_root: Path, copy_to_storage: bool = True,
                 origin: str = "import", mover: bool = False):
        self.db = db
        self.storage = Path(storage_root)
        self.copy = copy_to_storage
        self.origin = origin          # import, received, retrieved, prefetch
        #: 0.100.38: o arquivo é **movido** para o armazenamento (o cache do modo cliente: o que chegou da rede
        #: já está no mesmo disco, numa pasta de passagem — copiar e apagar gravava cada imagem duas vezes)
        self.mover = mover
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def import_paths(self, paths: Iterable[Path | str],
                     progress: ProgressFn | None = None,
                     batch_size: int = 200,
                     on_scan: Callable[[int], None] | None = None) -> ImportResult:
        self._cancel = False
        result = ImportResult()
        tmp_dirs: list[Path] = []
        try:
            # 0.99.66: ZIP, RAR, 7z, TAR, ISO… (importer/compactados.py)
            from ipe.importer import compactados as CP
            expanded, temps, erros = CP.expandir(paths, lambda: tempfile.mkdtemp(prefix="dv_zip_"))
            tmp_dirs.extend(temps)
            for e in erros:
                log.warning("Compactado: %s", e)
                result.errors += 1
                result.error_files.append(e)
            files: list[Path] = []
            for f in iter_candidate_files(expanded):
                if self._cancel:
                    break
                files.append(f)
                if on_scan and len(files) % 200 == 0:
                    on_scan(len(files))
            # arquivos de compactados precisam ser copiados (a pasta temporária some)
            force_copy = {str(t) for t in tmp_dirs}
            total = len(files)
            with self.db.session() as s:
                cache = _Cache(s, self.origin)
                n = 0
                # 0.100.38: em lotes — os cabeçalhos do lote são lidos, **uma** consulta diz quais imagens já estão
                # no banco e **um** comando grava as novas (antes: uma consulta e uma gravação por imagem, o que
                # no PostgreSQL eram duas idas e voltas ao servidor do banco para cada corte)
                for ini in range(0, total, batch_size):
                    if self._cancel:
                        log.info("Importação cancelada pelo usuário")
                        break
                    lote = files[ini:ini + batch_size]
                    lidos = [(f, self._ler_cabecalho(f, result)) for f in lote]
                    cache.conferir_no_banco([_s(ds, "SOPInstanceUID") for _f2, ds in lidos if ds is not None])
                    for f, ds in lidos:
                        n += 1
                        if self._cancel:
                            log.info("Importação cancelada pelo usuário")
                            break
                        if ds is not None:
                            copy = self.copy or any(str(f).startswith(t) for t in force_copy)
                            self._import_one(s, cache, f, copy, result, ds)
                        if progress and (n % 5 == 0 or n == total):
                            progress(n, total, str(f))
                    cache.gravar_instancias()
                    s.commit()
                cache.gravar_instancias()
                s.commit()
                self._refresh_modalities(s, result.new_studies)
        finally:
            for t in tmp_dirs:
                shutil.rmtree(t, ignore_errors=True)
        log.info(result.summary())
        return result

    # ----------------------------------------------------------------------
    def _ler_cabecalho(self, f: Path, r: ImportResult):
        """O cabeçalho do arquivo, ou None (não é DICOM, ou não deu para ler — já contado em `r`)."""
        try:
            return pydicom.dcmread(f, stop_before_pixels=True, force=False)
        except InvalidDicomError:
            # arquivos antigos/de CD às vezes vêm sem o cabeçalho "DICM":
            # tenta ler assim mesmo e só aceita se tiver os UIDs obrigatórios
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True, force=True)
                if "SOPInstanceUID" not in ds:
                    r.not_dicom += 1
                    return None
                return ds
            except Exception:  # noqa: BLE001
                r.not_dicom += 1
                return None
        except (EOFError, IsADirectoryError, PermissionError):
            r.not_dicom += 1
            return None
        except Exception as e:  # noqa: BLE001
            r.errors += 1
            r.error_files.append(f"{f}: {e}")
            return None

    def _import_one(self, s, cache: "_Cache", f: Path, copy: bool, r: ImportResult, ds=None) -> None:
        if ds is None:
            ds = self._ler_cabecalho(f, r)
            if ds is None:
                return
            cache.conferir_no_banco([_s(ds, "SOPInstanceUID")])

        sop_class = _s(ds, "SOPClassUID") or _s(getattr(ds, "file_meta", {}), "MediaStorageSOPClassUID")
        sop_uid = _s(ds, "SOPInstanceUID")
        study_uid = _s(ds, "StudyInstanceUID")
        series_uid = _s(ds, "SeriesInstanceUID")
        if sop_class == DICOMDIR_CLASS or not (sop_uid and study_uid and series_uid):
            r.not_dicom += 1
            return
        if sop_uid in cache.known_sops:
            r.duplicates += 1
            r.studies.add(study_uid)
            return

        # --- arquivo
        if copy:
            pasta = self.storage / safe_name(study_uid) / safe_name(series_uid)
            dest = pasta / f"{safe_name(sop_uid)}.dcm"
            try:
                if pasta not in cache.pastas:
                    pasta.mkdir(parents=True, exist_ok=True)
                    cache.pastas.add(pasta)
                if os.path.abspath(f) == os.path.abspath(dest):
                    pass                                    # já está no lugar
                elif self.mover:
                    try:
                        os.replace(f, dest)                 # mesmo disco: só troca o nome
                    except OSError:
                        shutil.copy2(f, dest)               # outro disco: copia (quem chamou apaga o original)
                elif f.resolve() != dest.resolve():
                    shutil.copy2(f, dest)
            except OSError as e:
                r.errors += 1
                r.error_files.append(f"{f}: {e}")
                return
            file_path, in_storage = dest, True
        else:
            file_path, in_storage = f.resolve(), False

        series = cache.series_map.get(series_uid)
        if series is None:                       # a 1ª imagem da série neste lote: paciente, exame e série
            patient = cache.patient(ds)
            study = cache.study(ds, patient, r)
            series = cache.series(ds, study, r)
        else:
            r.new_studies.add(study_uid)
            r.new_series.add(series_uid)
        ts = ""
        if getattr(ds, "file_meta", None) is not None:
            ts = _s(ds.file_meta, "TransferSyntaxUID")
        try:
            tamanho = os.path.getsize(file_path)
        except OSError:
            tamanho = 0
        cache.instancias.append((series, dict(
            sop_uid=sop_uid, sop_class_uid=sop_class,
            instance_number=_i(ds, "InstanceNumber"),
            file_path=str(file_path), in_storage=in_storage, transfer_syntax=ts,
            rows=_i(ds, "Rows"), columns=_i(ds, "Columns"),
            number_of_frames=max(1, _i(ds, "NumberOfFrames", 1)),
            image_position=_s(ds, "ImagePositionPatient"),
            image_orientation=_s(ds, "ImageOrientationPatient"),
            slice_location=_f(ds, "SliceLocation"),
            acquisition_time=_s(ds, "AcquisitionTime") or _s(ds, "ContentTime"),
            file_size=tamanho,
        )))
        cache.known_sops.add(sop_uid)
        if is_workstation_capture(ds, sop_class):
            # não trava o exame (locked): marcar sozinho não é o usuário dizendo "guarde isto"
            s.add(KeyImage(study_uid=study_uid, series_uid=series_uid, sop_uid=sop_uid,
                           frame_index=0))
        r.studies.add(study_uid)
        r.added += 1

    def _refresh_modalities(self, s, study_uids: set[str]) -> None:
        for uid in study_uids:
            st = s.scalar(select(Study).where(Study.study_uid == uid))
            if st is None:
                continue
            mods = sorted({se.modality for se in st.series if se.modality})
            st.modalities = "\\".join(mods)
        s.commit()


class _Cache:
    """Evita consultas repetidas ao banco durante uma importação."""

    def __init__(self, s, origin: str = "import"):
        self.s = s
        self.origin = origin
        self.patients: dict[tuple, Patient] = {}
        self.studies: dict[str, Study] = {}
        self.series_map: dict[str, Series] = {}
        self.known_sops: set[str] = set()      # as que já estão no banco e as que este lote vai gravar
        self.conferidos: set[str] = set()
        self.instancias: list[tuple] = []      # (série, colunas) à espera de gravar_instancias
        self.pastas: set[Path] = set()         # pastas do armazenamento já criadas

    def conferir_no_banco(self, sop_uids: list[str]) -> None:
        """Uma consulta para o lote: quais destas imagens já estão no banco (entram em `known_sops`)."""
        novos = [u for u in dict.fromkeys(sop_uids) if u and u not in self.conferidos]
        for i in range(0, len(novos), 500):
            parte = novos[i:i + 500]
            self.known_sops.update(self.s.scalars(select(Instance.sop_uid).where(Instance.sop_uid.in_(parte))))
        self.conferidos.update(novos)

    def gravar_instancias(self) -> None:
        """Grava de uma vez as imagens do lote. Outra importação pode ter gravado a mesma imagem nesse meio
        tempo (o exame chegando por dois caminhos): no PostgreSQL a repetida é ignorada, sem derrubar o lote."""
        if not self.instancias:
            return
        self.s.flush()                         # paciente, exame e série ganham o número
        linhas = [dict(cols, series_fk=se.id) for se, cols in self.instancias]
        self.instancias = []
        if self.s.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            self.s.execute(pg_insert(Instance).on_conflict_do_nothing(index_elements=["sop_uid"]), linhas)
        else:
            from sqlalchemy import insert
            self.s.execute(insert(Instance), linhas)

    def patient(self, ds) -> Patient:
        key = (_s(ds, "PatientID"), _s(ds, "IssuerOfPatientID"),
               person_name(ds, "PatientName"), _s(ds, "PatientBirthDate"))
        p = self.patients.get(key)
        if p is None:
            p = self.s.scalar(select(Patient).where(
                Patient.patient_id == key[0], Patient.issuer == key[1],
                Patient.name == key[2], Patient.birth_date == key[3]))
            if p is None:
                p = Patient(patient_id=key[0], issuer=key[1], name=key[2],
                            birth_date=key[3], sex=_s(ds, "PatientSex"))
                self.s.add(p)
            self.patients[key] = p
        return p

    def study(self, ds, patient: Patient, r: ImportResult) -> Study:
        uid = _s(ds, "StudyInstanceUID")
        st = self.studies.get(uid)
        if st is None:
            st = self.s.scalar(select(Study).where(Study.study_uid == uid))
            if st is None:
                st = Study(study_uid=uid, patient=patient,
                           study_date=_s(ds, "StudyDate"), study_time=_s(ds, "StudyTime"),
                           accession=_s(ds, "AccessionNumber"),
                           description=_s(ds, "StudyDescription"),
                           referring=person_name(ds, "ReferringPhysicianName"),
                           institution=_s(ds, "InstitutionName"),
                           patient_age=_s(ds, "PatientAge"), origin=self.origin)
                self.s.add(st)
            self.studies[uid] = st
        r.new_studies.add(uid)
        return st

    def series(self, ds, study: Study, r: ImportResult) -> Series:
        uid = _s(ds, "SeriesInstanceUID")
        se = self.series_map.get(uid)
        if se is None:
            se = self.s.scalar(select(Series).where(Series.series_uid == uid))
            if se is None:
                se = Series(series_uid=uid, study=study, modality=_s(ds, "Modality"),
                            series_number=_i(ds, "SeriesNumber"),
                            description=_s(ds, "SeriesDescription"),
                            body_part=_s(ds, "BodyPartExamined"),
                            laterality=_s(ds, "ImageLaterality") or _s(ds, "Laterality"),
                            frame_of_reference=_s(ds, "FrameOfReferenceUID"))
                se.operators, se.station, se.device = series_details(ds)
                self.s.add(se)
            self.series_map[uid] = se
        r.new_series.add(uid)
        return se


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extrai o ZIP sem permitir caminhos que escapem da pasta (zip-slip)."""
    dest = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if dest not in target.parents and target != dest:
            log.warning("Ignorando entrada suspeita no ZIP: %s", member.filename)
            continue
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
