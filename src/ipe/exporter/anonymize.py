"""Anonimização configurável das cópias exportadas (perfil inspirado no DICOM PS3.15 básico)."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

UID_ROOT = "2.25."

# identificação direta da pessoa
PERSON = ["OtherPatientIDs", "OtherPatientIDsSequence", "OtherPatientNames", "PatientBirthName",
          "PatientMotherBirthName", "PatientAddress", "PatientTelephoneNumbers", "MilitaryRank",
          "MedicalRecordLocator", "PatientInsurancePlanCodeSequence", "IssuerOfPatientID",
          "CurrentPatientLocation", "Occupation", "PatientReligiousPreference", "EthnicGroup",
          "PatientBirthTime", "ReferencedPatientSequence", "PatientComments", "AdditionalPatientHistory",
          "AdmittingDiagnosesDescription", "PatientState", "ResponsiblePerson", "ResponsibleOrganization"]
# equipe e local
STAFF_PLACE = ["InstitutionName", "InstitutionAddress", "InstitutionalDepartmentName", "ReferringPhysicianName",
               "ReferringPhysicianAddress", "ReferringPhysicianTelephoneNumbers", "PerformingPhysicianName",
               "NameOfPhysiciansReadingStudy", "PhysiciansOfRecord", "OperatorsName", "RequestingPhysician",
               "ScheduledPerformingPhysicianName", "StationName", "DeviceSerialNumber", "RequestingService",
               "RequestAttributesSequence", "StudyID", "RequestedProcedureID", "PerformedProcedureStepID",
               "ScheduledProcedureStepID", "ReferencedStudySequence", "ReferencedPerformedProcedureStepSequence"]
DATES = ["StudyDate", "SeriesDate", "AcquisitionDate", "ContentDate", "InstanceCreationDate",
         "PerformedProcedureStepStartDate"]
TIMES = ["StudyTime", "SeriesTime", "AcquisitionTime", "ContentTime", "InstanceCreationTime",
         "PerformedProcedureStepStartTime", "AcquisitionDateTime"]
DESCRIPTIONS = ["StudyDescription", "SeriesDescription", "PerformedProcedureStepDescription",
                "RequestedProcedureDescription", "ProtocolName", "ImageComments"]
UID_TAGS = ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "FrameOfReferenceUID"]


@dataclass
class AnonOptions:
    enabled: bool = False
    name: str = "ANONIMO"              # nome do paciente na cópia ({n} = número do exame na exportação)
    patient_id: str = "ANON{n:03d}"
    keep_sex: bool = True
    keep_age: bool = True              # idade (0010,1010); o nascimento sempre sai
    keep_dates: bool = False           # datas do exame (senão: data ficam em branco)
    #: 0.99.42: datas deslocadas — o mesmo número de dias (30 a 329) para todo o paciente nesta sessão;
    #: o intervalo entre os exames continua o mesmo (o perfil Ensino)
    shift_dates: bool = False
    keep_descriptions: bool = True     # descrição do exame/série (pode conter nome em alguns serviços)
    keep_institution: bool = False
    remove_private: bool = True
    new_uids: bool = True              # UIDs novos (consistentes dentro da exportação)
    burned: str = "auto"               # texto gravado na imagem: none | auto | top
    top_pct: float = 8.0               # faixa superior tarjada (modo top, ou auto sem regiões de US)

    @staticmethod
    def from_dict(d: dict | None) -> "AnonOptions":
        known = AnonOptions.__dataclass_fields__
        return AnonOptions(**{k: v for k, v in (d or {}).items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)


def new_uid(old: str, salt: str) -> str:
    h = hashlib.sha256(f"{salt}|{old}".encode()).hexdigest()
    return UID_ROOT + str(int(h[:30], 16))


def _fmt(template: str, n: int) -> str:
    try:
        return template.format(n=n)
    except (KeyError, ValueError, IndexError):
        return template


def anonymize(ds, opts: AnonOptions, n: int, salt: str) -> None:
    """Anonimiza o dataset na memória. `n` = número do paciente/exame nesta exportação."""
    if not opts.enabled:
        return
    chave_original = str(ds.get("PatientID", "") or ds.get("PatientName", "") or "")
    ds.PatientName = _fmt(opts.name, n)[:64] or "ANONIMO"
    ds.PatientID = _fmt(opts.patient_id, n)[:64] or f"ANON{n:03d}"
    if "PatientBirthDate" in ds:
        ds.PatientBirthDate = ""
    if not opts.keep_sex and "PatientSex" in ds:
        ds.PatientSex = ""
    if not opts.keep_age and "PatientAge" in ds:
        del ds.PatientAge
    ds.AccessionNumber = ""
    for kw in PERSON:
        if kw in ds:
            delattr(ds, kw)
    for kw in STAFF_PLACE:
        if kw in ds and not (opts.keep_institution and kw in ("InstitutionName", "InstitutionalDepartmentName")):
            delattr(ds, kw)
    if opts.shift_dates and not opts.keep_dates:
        from ipe.core import mascara as MK
        dias = MK.dias_de_deslocamento(chave_original)
        for kw in DATES:
            if kw in ds and ds.data_element(kw).value:
                setattr(ds, kw, MK.deslocar_data(str(ds.data_element(kw).value), dias))
    elif not opts.keep_dates:
        for kw in DATES:
            if kw in ds:
                setattr(ds, kw, "")
        for kw in TIMES:
            if kw in ds:
                delattr(ds, kw)
    if not opts.keep_descriptions:
        for kw in DESCRIPTIONS:
            if kw in ds:
                delattr(ds, kw)
    if opts.new_uids:
        for kw in UID_TAGS:
            if kw in ds and ds.data_element(kw).value:
                setattr(ds, kw, new_uid(str(ds.data_element(kw).value), salt))
        for seq_kw in ("ReferencedSeriesSequence", "ReferencedImageSequence", "SourceImageSequence"):
            if seq_kw in ds:
                for item in ds.data_element(seq_kw).value:
                    for kw in ("ReferencedSOPInstanceUID", "SeriesInstanceUID"):
                        if kw in item:
                            setattr(item, kw, new_uid(str(item.data_element(kw).value), salt))
    redact_burned_in(ds, opts.burned, opts.top_pct)
    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "Ipe: exportacao anonimizada"
    if opts.remove_private:
        ds.remove_private_tags()
    if getattr(ds, "file_meta", None) is not None and "SOPInstanceUID" in ds:
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID


def _us_regions(ds) -> list[tuple[int, int, int, int]]:
    out = []
    for r in ds.get("SequenceOfUltrasoundRegions", []) or []:
        try:
            out.append((int(r.RegionLocationMinX0), int(r.RegionLocationMinY0),
                        int(r.RegionLocationMaxX1), int(r.RegionLocationMaxY1)))
        except (AttributeError, TypeError, ValueError):
            continue
    return out


def burned_in_plan(ds, mode: str) -> str | None:
    """O que fazer com o texto gravado: "regions" (US: apaga fora das regiões de imagem), "top" ou None."""
    if mode == "none" or "PixelData" not in ds:
        return None
    if mode == "top":
        return "top"
    modality = str(ds.get("Modality", "")).upper()
    flagged = str(ds.get("BurnedInAnnotation", "")).upper() == "YES"
    if modality == "US" and _us_regions(ds):
        return "regions"
    if modality in ("US", "XA", "RF", "ES", "SC", "OT") or flagged:
        return "top"
    return None


def redact_burned_in(ds, mode: str = "auto", top_pct: float = 8.0) -> bool:
    """Apaga (preto) as áreas onde costuma haver texto gravado nos pixels. Devolve True se mexeu.
    US com "Sequence of Ultrasound Regions": tudo fora das regiões de imagem; outros: faixa superior."""
    plan = burned_in_plan(ds, mode)
    if plan is None:
        return False
    import numpy as np
    from pydicom.uid import ExplicitVRLittleEndian
    arr = ds.pixel_array.copy()
    rows, cols = int(ds.Rows), int(ds.Columns)
    spp = int(ds.get("SamplesPerPixel", 1) or 1)
    frames = int(ds.get("NumberOfFrames", 1) or 1)
    photometric = str(ds.get("PhotometricInterpretation", "")).upper()
    black = (2 ** int(ds.BitsStored) - 1) if photometric == "MONOCHROME1" else 0
    if frames == 1:
        arr = arr[None]
    if spp == 1 and arr.ndim == 3:
        arr = arr[..., None]
    mask = np.zeros((rows, cols), bool)
    if plan == "regions":
        mask[:] = True
        for x0, y0, x1, y1 in _us_regions(ds):
            mask[max(0, y0):min(rows, y1 + 1), max(0, x0):min(cols, x1 + 1)] = False
    else:
        mask[: max(1, int(round(rows * top_pct / 100.0)))] = True
    arr[:, mask, :] = black
    if spp == 1:
        arr = arr[..., 0]
    if frames == 1:
        arr = arr[0]
    ds.PixelData = np.ascontiguousarray(arr).tobytes()
    if spp == 3:
        ds.PhotometricInterpretation = "RGB"
        ds.PlanarConfiguration = 0
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    if "BitsAllocated" in ds and arr.dtype.itemsize * 8 != int(ds.BitsAllocated):
        ds.BitsAllocated = arr.dtype.itemsize * 8
    ds.BurnedInAnnotation = "NO"
    return True
