"""Exportar e importar listas de casos.

Pacote = ZIP com `lista.json` (nome, descrição e, por caso: nome amigável, história, resposta,
notas, tags, séries a mostrar, imagens-chave e medidas) e, se pedido, `dicom/` com CÓPIAS
anonimizadas das imagens (os arquivos do banco não são alterados). Na cópia anonimizada os UIDs são
trocados de forma consistente, para o caso poder ser importado até no mesmo computador sem se
misturar com o exame original.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pydicom


log = logging.getLogger(__name__)

FORMAT = "dicomviewer-caselist"
VERSION = 1
UID_ROOT = "2.25."

# atributos que identificam a pessoa, o local ou a equipe: somem na cópia anonimizada
_REMOVE = [
    "PatientBirthDate", "PatientBirthTime", "OtherPatientIDs", "OtherPatientIDsSequence", "OtherPatientNames",
    "PatientAddress", "PatientTelephoneNumbers", "PatientMotherBirthName", "MilitaryRank", "EthnicGroup",
    "PatientReligiousPreference", "MedicalRecordLocator", "PatientInsurancePlanCodeSequence",
    "InstitutionName", "InstitutionAddress", "InstitutionalDepartmentName", "ReferringPhysicianName",
    "ReferringPhysicianAddress", "ReferringPhysicianTelephoneNumbers", "PerformingPhysicianName",
    "NameOfPhysiciansReadingStudy", "PhysiciansOfRecord", "OperatorsName", "RequestingPhysician",
    "ScheduledPerformingPhysicianName", "StationName", "DeviceSerialNumber", "RequestAttributesSequence",
    "AdmittingDiagnosesDescription", "AdditionalPatientHistory", "PatientComments", "StudyID",
    "IssuerOfPatientID", "CurrentPatientLocation", "PatientState", "Occupation", "RequestedProcedureID",
    "PerformedProcedureStepID", "ScheduledProcedureStepID", "ResponsibleOrganization", "ResponsiblePerson",
    "ReferencedPatientSequence", "ReferencedStudySequence", "ReferencedPerformedProcedureStepSequence",
]
_UID_TAGS = ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "FrameOfReferenceUID",
             "MediaStorageSOPInstanceUID"]


class PackageError(Exception):
    pass


def new_uid(old: str, salt: str) -> str:
    """UID novo, sempre o mesmo para o mesmo (UID antigo, pacote)."""
    h = hashlib.sha256(f"{salt}|{old}".encode()).hexdigest()
    return UID_ROOT + str(int(h[:30], 16))


def anonymize_dataset(ds, case_no: int, case_name: str, salt: str, keep_age: bool = True) -> None:
    """Anonimiza o dataset na memória (a cópia a ser gravada)."""
    ds.PatientName = f"CASO^{case_no:03d}"
    ds.PatientID = f"CASO{case_no:03d}"
    if not keep_age and "PatientAge" in ds:
        del ds.PatientAge
    ds.AccessionNumber = ""
    for kw in _REMOVE:
        if kw in ds:
            delattr(ds, kw)
    if case_name:
        ds.StudyDescription = case_name[:64]
    for kw in _UID_TAGS:
        if kw == "MediaStorageSOPInstanceUID":
            continue
        if kw in ds and ds.data_element(kw).value:
            setattr(ds, kw, new_uid(str(ds.data_element(kw).value), salt))
    for seq_kw in ("ReferencedSeriesSequence", "ReferencedImageSequence", "SourceImageSequence"):
        if seq_kw in ds:
            for item in ds.data_element(seq_kw).value:
                for kw in ("ReferencedSOPInstanceUID", "SeriesInstanceUID"):
                    if kw in item:
                        setattr(item, kw, new_uid(str(item.data_element(kw).value), salt))
    from ipe.exporter.anonymize import redact_burned_in
    redact_burned_in(ds, "auto")
    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "Ipe: identificacao removida, UIDs novos"
    ds.remove_private_tags()
    if getattr(ds, "file_meta", None) is not None and "SOPInstanceUID" in ds:
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID


@dataclass
class ExportResult:
    path: Path
    cases: int = 0
    files: int = 0
    missing: list[str] = field(default_factory=list)     # casos sem exame no banco


def export_case_list(repo, list_id: int, dest: Path, with_images: bool = True, progress=None,
                     cancel=None) -> ExportResult:
    """Grava o pacote ZIP. `progress(feito, total)`; `cancel()` -> True interrompe."""
    info = repo.case_list_info(list_id)
    if info is None or info["kind"] == "folder":
        raise PackageError("Escolha uma lista (não uma pasta).")
    items = repo.list_items(list_id)
    salt = hashlib.sha256(f"{list_id}|{datetime.now().isoformat()}".encode()).hexdigest()[:16]
    remap = (lambda u: new_uid(u, salt)) if with_images else (lambda u: u)
    dest = Path(dest)
    res = ExportResult(dest)
    cases = []
    files_plan: list[tuple[int, dict, str]] = []
    for it in items:
        if not it["present"]:
            res.missing.append(it["friendly_name"] or it["study_uid"])
            if with_images:
                continue
        su = it["study_uid"]
        series = repo.series_for_study(su) if it["present"] else []
        series_uids = [s.series_uid for s in series]
        keys = [{"series_uid": remap(k["series_uid"]), "sop_uid": remap(k["sop_uid"]),
                 "frame_index": k["frame_index"]} for k in (repo.key_images(su) if it["present"] else [])]
        anns = [{"series_uid": remap(a["series_uid"]), "sop_uid": remap(a["sop_uid"]),
                 "frame_index": a["frame_index"], "kind": a["kind"], "data": a["data"]}
                for a in repo.annotations_for_series(series_uids)]
        case = {
            "n": it["n"], "study_uid": remap(su), "friendly_name": it["friendly_name"],
            "clinical_summary": it["clinical_summary"], "hidden_diagnosis": it["hidden_diagnosis"],
            "note": it["note"], "tags": it["tags"], "show_series": [remap(u) for u in it["show_series"]],
            "description": it["description"], "modalities": it["modalities"],
            "key_images": keys, "annotations": anns,
        }
        if not with_images:
            case["study_date"] = it["study_date"]
        cases.append(case)
        if with_images:
            for f in repo.files_for_study(su):
                files_plan.append((it["n"], it, f))
    manifest = {"format": FORMAT, "version": VERSION, "name": info["name"], "description": info["description"],
                "kind": info["kind"], "anonymized": with_images, "with_images": with_images,
                "created": datetime.now().isoformat(timespec="seconds"), "cases": cases}
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    total = len(files_plan)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("lista.json", json.dumps(manifest, ensure_ascii=False, indent=1))
            for k, (n, it, path) in enumerate(files_plan, 1):
                if cancel is not None and cancel():
                    raise PackageError("Exportação cancelada.")
                try:
                    ds = pydicom.dcmread(path)
                    anonymize_dataset(ds, n, it["friendly_name"], salt)
                    import io
                    buf = io.BytesIO()
                    ds.save_as(buf, enforce_file_format=True)
                    zf.writestr(f"dicom/caso{n:03d}/{ds.SOPInstanceUID}.dcm", buf.getvalue())
                    res.files += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("não exportou %s: %s", path, e)
                if progress is not None:
                    progress(k, total)
        shutil.move(str(tmp), str(dest))
    finally:
        if tmp.exists():
            tmp.unlink()
    res.cases = len(cases)
    return res


def read_manifest(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as zf:
            data = json.loads(zf.read("lista.json").decode("utf-8"))
    except KeyError:
        raise PackageError("O arquivo não é um pacote de lista do Ipê (falta lista.json).") from None
    except zipfile.BadZipFile:
        raise PackageError("O arquivo não é um ZIP válido.") from None
    if data.get("format") != FORMAT:
        raise PackageError("Formato de pacote desconhecido.")
    return data


@dataclass
class ImportListResult:
    list_id: int = 0
    cases: int = 0
    missing: list[str] = field(default_factory=list)     # casos cujo exame não está no banco
    files: int = 0


def import_case_list(repo, db, storage_root: Path, path: Path, name: str | None = None,
                     parent: int | None = None, progress=None) -> ImportListResult:
    """Importa as imagens (se houver) e recria a lista, com imagens-chave e medidas."""
    data = read_manifest(path)
    res = ImportListResult()
    if data.get("with_images"):
        from ipe.importer.scanner import Importer
        tmp = Path(tempfile.mkdtemp(prefix="dv_lista_"))
        try:
            with zipfile.ZipFile(path) as zf:
                for m in zf.namelist():
                    if m.startswith("dicom/") and not m.endswith("/") and ".." not in m:
                        zf.extract(m, tmp)
            r = Importer(db, storage_root).import_paths([tmp / "dicom"], progress=progress)
            res.files = r.added + r.duplicates
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    list_id = repo.create_case_list(name or data.get("name") or "Lista importada", data.get("kind") or "normal",
                                    parent, data.get("description", ""))
    res.list_id = list_id
    present = repo.study_uids_present([c["study_uid"] for c in data.get("cases", [])])
    for c in data.get("cases", []):
        su = c["study_uid"]
        if su not in present:
            res.missing.append(c.get("friendly_name") or c.get("description") or su)
            continue
        repo.add_to_case_list(list_id, su, c.get("friendly_name", ""),
                              clinical_summary=c.get("clinical_summary", ""),
                              hidden_diagnosis=c.get("hidden_diagnosis", ""), note=c.get("note", ""),
                              tags=c.get("tags", []), show_series=c.get("show_series", []))
        have_keys = repo.key_image_set(su)
        for k in c.get("key_images", []):
            if (k["sop_uid"], k["frame_index"]) not in have_keys:
                repo.toggle_key_image(su, k["series_uid"], k["sop_uid"], k["frame_index"])
        if c.get("annotations"):
            existing = {(a["sop_uid"], a["frame_index"], a["kind"], a["data"])
                        for a in repo.annotations_for_series(sorted({a["series_uid"] for a in c["annotations"]}))}
            for a in c["annotations"]:
                if (a["sop_uid"], a["frame_index"], a["kind"], a["data"]) in existing:
                    continue
                repo.save_annotation(db_id=None, study_uid=su, series_uid=a["series_uid"], sop_uid=a["sop_uid"],
                                     frame_index=a["frame_index"], kind=a["kind"], data=a["data"])
        res.cases += 1
    return res


