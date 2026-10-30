"""Laudo em DICOM: PDF encapsulado (Encapsulated PDF) e relatório estruturado de texto (Basic Text SR).

Os dois entram no próprio estudo (série nova) e vão junto ao enviar ao PACS ou exportar.
"""

from __future__ import annotations

from datetime import datetime

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

ENCAPSULATED_PDF = "1.2.840.10008.5.1.4.1.1.104.1"
BASIC_TEXT_SR = "1.2.840.10008.5.1.4.1.1.88.11"
_PATIENT_STUDY = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge",
                  "StudyInstanceUID", "StudyDate", "StudyTime", "StudyID", "AccessionNumber",
                  "StudyDescription", "ReferringPhysicianName", "InstitutionName"]


def _code(value: str, scheme: str, meaning: str) -> Dataset:
    c = Dataset()
    c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = value, scheme, meaning
    return c


REPORT_CODE = ("18748-4", "LN", "Diagnostic imaging report")


def _base(src_path: str, sop_class: str, modality: str, description: str, series_number: int) -> Dataset:
    src = pydicom.dcmread(src_path, stop_before_pixels=True, force=True)
    ds = Dataset()
    for kw in _PATIENT_STUDY:
        if kw in src:
            setattr(ds, kw, src.data_element(kw).value)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    sop = generate_uid()
    meta.MediaStorageSOPInstanceUID = sop
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop
    ds.Modality = modality
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = series_number
    ds.SeriesDescription = description[:64]
    ds.InstanceNumber = 1
    ds.Manufacturer = "Ipe"
    now = datetime.now()
    ds.ContentDate, ds.ContentTime = now.strftime("%Y%m%d"), now.strftime("%H%M%S")
    ds.SeriesDate, ds.SeriesTime = ds.ContentDate, ds.ContentTime
    ds.SpecificCharacterSet = "ISO_IR 192"          # UTF-8 (acentos)
    return ds


def encapsulated_pdf(pdf: bytes, src_path: str, title: str = "Laudo", series_number: int = 990) -> Dataset:
    ds = _base(src_path, ENCAPSULATED_PDF, "DOC", "Laudo (PDF)", series_number)
    ds.ConversionType = "WSD"
    ds.BurnedInAnnotation = "YES"
    ds.DocumentTitle = title[:64]
    ds.ConceptNameCodeSequence = Sequence([_code(*REPORT_CODE)])
    ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
    ds.AcquisitionDateTime = datetime.now().strftime("%Y%m%d%H%M%S")
    if len(pdf) % 2:
        pdf += b"\x00"
    ds.EncapsulatedDocument = pdf
    return ds


def split_sections(text: str) -> list[tuple[str, str]]:
    """Separa o texto em (seção, conteúdo): achados e impressão/conclusão."""
    findings, impression, cur = [], [], None
    for line in (text or "").splitlines():
        head = line.strip().rstrip(":").upper()
        if head in ("IMPRESSÃO", "IMPRESSAO", "CONCLUSÃO", "CONCLUSAO", "IMPRESSÃO DIAGNÓSTICA", "OPINIÃO"):
            cur = impression
            continue
        (cur if cur is not None else findings).append(line)
    out = [("Findings", "\n".join(findings).strip())]
    if any(x.strip() for x in impression):
        out.append(("Impression", "\n".join(impression).strip()))
    return [(k, v) for k, v in out if v]


SECTION_CODES = {"Findings": ("121071", "DCM", "Finding"), "Impression": ("121073", "DCM", "Impression")}


def text_sr(text: str, src_path: str, title: str = "Laudo", author: str = "", signed: bool = False,
            signed_by: str = "", birads: str = "", series_number: int = 991) -> Dataset:
    ds = _base(src_path, BASIC_TEXT_SR, "SR", "Laudo (SR)", series_number)
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = Sequence([_code(*REPORT_CODE)])
    ds.ContinuityOfContent = "SEPARATE"
    ds.CompletionFlag = "COMPLETE"
    ds.VerificationFlag = "VERIFIED" if signed else "UNVERIFIED"
    if signed:
        v = Dataset()
        v.VerifyingObserverName = (signed_by or author or "Médico")[:64]
        v.VerificationDateTime = datetime.now().strftime("%Y%m%d%H%M%S")
        v.VerifyingOrganization = "Ipe"
        v.VerifyingObserverIdentificationCodeSequence = Sequence([])
        ds.VerifyingObserverSequence = Sequence([v])
    items = []
    if author:
        a = Dataset()
        a.RelationshipType, a.ValueType = "HAS OBS CONTEXT", "PNAME"
        a.ConceptNameCodeSequence = Sequence([_code("121008", "DCM", "Person Observer Name")])
        a.PersonName = author[:64]
        items.append(a)
    t = Dataset()
    t.RelationshipType, t.ValueType = "CONTAINS", "TEXT"
    t.ConceptNameCodeSequence = Sequence([_code("121050", "DCM", "Equivalent Meaning of Concept Name")])
    t.TextValue = title[:1024]
    for name, content in split_sections(text):
        c = Dataset()
        c.RelationshipType, c.ValueType = "CONTAINS", "CONTAINER"
        c.ConceptNameCodeSequence = Sequence([_code(*SECTION_CODES[name])])
        c.ContinuityOfContent = "SEPARATE"
        tx = Dataset()
        tx.RelationshipType, tx.ValueType = "CONTAINS", "TEXT"
        tx.ConceptNameCodeSequence = Sequence([_code(*SECTION_CODES[name])])
        tx.TextValue = content
        c.ContentSequence = Sequence([tx])
        items.append(c)
    if birads:
        b = Dataset()
        b.RelationshipType, b.ValueType = "CONTAINS", "TEXT"
        b.ConceptNameCodeSequence = Sequence([_code("111005", "DCM", "Assessment Category")])
        b.TextValue = f"BI-RADS {birads}"
        items.append(b)
    ds.ContentSequence = Sequence(items)
    return ds
