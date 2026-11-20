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
ENHANCED_SR = "1.2.840.10008.5.1.4.1.1.88.22"       # 0.100.72: com esquemas (o Basic Text não aceita SCOORD)
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
            signed_by: str = "", birads: str = "", series_number: int = 991, esquemas: list | None = None) -> Dataset:
    """`esquemas` (0.100.72, de `esquemas_saida.para_o_exame`): cada esquema vira uma seção com a referência à
    imagem gravada no exame, a legenda e, por marca, o texto com a posição (SCOORD) e a imagem ligada a ela.
    Com esquemas o objeto é um Enhanced SR (o Basic Text SR não aceita coordenadas)."""
    esquemas = [e for e in (esquemas or []) if e.get("sop_uid")]
    ds = _base(src_path, ENHANCED_SR if esquemas else BASIC_TEXT_SR, "SR", "Laudo (SR)", series_number)
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
    evidencia: dict[str, list[tuple[str, str]]] = {}
    for e in esquemas:
        items.append(_secao_do_esquema(e, evidencia))
    _declarar(ds, evidencia)
    ds.ContentSequence = Sequence(items)
    return ds


def _declarar(ds: Dataset, evidencia: dict) -> None:
    """O SR declara as imagens que cita (do próprio exame)."""
    if not evidencia:
        return
    ev = Dataset()
    ev.StudyInstanceUID = ds.get("StudyInstanceUID", "")
    series = []
    for serie, sops in evidencia.items():
        se = Dataset()
        se.SeriesInstanceUID = serie
        se.ReferencedSOPSequence = Sequence([_ref(c, u) for c, u in dict.fromkeys(sops)])
        series.append(se)
    ev.ReferencedSeriesSequence = Sequence(series)
    ds.CurrentRequestedProcedureEvidenceSequence = Sequence([ev])


def esquemas_sr(src_path: str, esquemas: list, author: str = "", series_number: int = 993,
                description: str = "Esquemas do laudo (SR)") -> Dataset:
    """0.100.73: o SR só dos esquemas-guia (gravados no exame sem laudo assinado): cada esquema com a figura, as
    marcas com a posição e a imagem ligada. Não é laudo: fica como não verificado."""
    ds = _base(src_path, ENHANCED_SR, "SR", description, series_number)
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = Sequence([_code("121070", "DCM", "Findings")])
    ds.ContinuityOfContent = "SEPARATE"
    ds.CompletionFlag = "PARTIAL"
    ds.VerificationFlag = "UNVERIFIED"
    items = []
    if author:
        a = Dataset()
        a.RelationshipType, a.ValueType = "HAS OBS CONTEXT", "PNAME"
        a.ConceptNameCodeSequence = Sequence([_code("121008", "DCM", "Person Observer Name")])
        a.PersonName = author[:64]
        items.append(a)
    evidencia: dict[str, list[tuple[str, str]]] = {}
    for e in esquemas or []:
        if e.get("sop_uid"):
            items.append(_secao_do_esquema(e, evidencia))
    _declarar(ds, evidencia)
    ds.ContentSequence = Sequence(items)
    return ds


def _ref(sop_class: str, sop_uid: str, frame: int = 0) -> Dataset:
    r = Dataset()
    r.ReferencedSOPClassUID, r.ReferencedSOPInstanceUID = sop_class, sop_uid
    if frame:
        r.ReferencedFrameNumber = int(frame) + 1
    return r


def _imagem(rel: str, sop_class: str, sop_uid: str, frame: int = 0, conceito: tuple | None = None) -> Dataset:
    i = Dataset()
    i.RelationshipType, i.ValueType = rel, "IMAGE"
    if conceito:
        i.ConceptNameCodeSequence = Sequence([_code(*conceito)])
    i.ReferencedSOPSequence = Sequence([_ref(sop_class, sop_uid, frame)])
    return i


def _secao_do_esquema(e: dict, evidencia: dict) -> Dataset:
    c = Dataset()
    c.RelationshipType, c.ValueType = "CONTAINS", "CONTAINER"
    c.ConceptNameCodeSequence = Sequence([_code("121070", "DCM", "Findings")])
    c.ContinuityOfContent = "SEPARATE"
    filhos = []
    t = Dataset()
    t.RelationshipType, t.ValueType = "CONTAINS", "TEXT"
    t.ConceptNameCodeSequence = Sequence([_code("121050", "DCM", "Equivalent Meaning of Concept Name")])
    t.TextValue = ("Esquema: " + e.get("titulo", ""))[:1024]
    filhos.append(t)
    filhos.append(_imagem("CONTAINS", e["sop_class"], e["sop_uid"], 0, ("121080", "DCM", "Best illustration of finding")))
    evidencia.setdefault(e["series_uid"], []).append((e["sop_class"], e["sop_uid"]))
    for m in e.get("marcas") or []:
        tx = Dataset()
        tx.RelationshipType, tx.ValueType = "CONTAINS", "TEXT"
        tx.ConceptNameCodeSequence = Sequence([_code("121071", "DCM", "Finding")])
        tx.TextValue = m.get("texto", "")[:1024] or "-"
        de = []
        if m.get("grafico") and m.get("dados"):
            sc = Dataset()
            sc.RelationshipType, sc.ValueType = "INFERRED FROM", "SCOORD"
            sc.ConceptNameCodeSequence = Sequence([_code("111030", "DCM", "Image Region")])
            sc.GraphicType = m["grafico"]
            sc.GraphicData = [float(v) for v in m["dados"]]
            sc.ContentSequence = Sequence([_imagem("SELECTED FROM", e["sop_class"], e["sop_uid"])])
            de.append(sc)
        im = m.get("imagem")
        if im and im.get("sop_class"):
            de.append(_imagem("INFERRED FROM", im["sop_class"], im["sop_uid"], im.get("frame", 0),
                              ("121080", "DCM", "Best illustration of finding")))
            evidencia.setdefault(im.get("series_uid") or "", []).append((im["sop_class"], im["sop_uid"]))
        if de:
            tx.ContentSequence = Sequence(de)
        filhos.append(tx)
    for linha in e.get("setores") or []:
        tx = Dataset()
        tx.RelationshipType, tx.ValueType = "CONTAINS", "TEXT"
        tx.ConceptNameCodeSequence = Sequence([_code("121071", "DCM", "Finding")])
        tx.TextValue = linha[:1024]
        filhos.append(tx)
    c.ContentSequence = Sequence(filhos)
    return c
