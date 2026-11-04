"""Documentos anexados ao exame (0.99.57): PDF e imagens viram DICOM dentro do próprio exame.

Pedido dele (04/11/2026): *"quero poder acrescentar PDFs e outros documentos nos exames, arrastando no
viewer, no BD (com um exame selecionado) ou pelo menu. quero que sejam convertidos para Dicom"*. Combinado:
só PDF e imagens (nada para instalar); cada imagem vira uma imagem; o anexo segue as regras de envio do exame.

- **PDF** → *Encapsulated PDF Storage* (1.2.840.10008.5.1.4.1.1.104.1), modalidade DOC, uma instância por
  arquivo, na série "Documentos anexados" (número 995). O título do documento é o nome do arquivo.
- **Imagem** (JPG, PNG, TIFF com várias páginas, BMP, GIF, WEBP) → *Secondary Capture Image Storage*
  (1.2.840.10008.5.1.4.1.1.7), modalidade OT, RGB de 8 bits, uma instância por imagem (ou por página do
  TIFF), na série "Imagens anexadas" (996), com a conversão marcada como "DI" (imagem digitalizada).
- Paciente e exame copiados de um arquivo do próprio exame: nome, ID, nascimento, sexo, idade, Study
  Instance UID, data, accession, descrição, solicitante e instituição — o anexo é do mesmo exame.
- Outros formatos (Word, Excel…) são recusados com o motivo: salve como PDF antes.

A leitura das imagens é a do Qt (QImage), que já vem com o programa.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

ENCAPSULATED_PDF = "1.2.840.10008.5.1.4.1.1.104.1"
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
PDF = {".pdf"}
IMAGENS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
OUTROS_DOCUMENTOS = {".doc", ".docx", ".odt", ".rtf", ".txt", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx",
                     ".odp", ".html", ".htm", ".heic", ".svg"}
SERIE_DOC, SERIE_IMG = 995, 996
DESC_DOC, DESC_IMG = "Documentos anexados", "Imagens anexadas"
_PACIENTE_EXAME = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "StudyInstanceUID",
                   "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription",
                   "ReferringPhysicianName", "InstitutionName", "IssuerOfPatientID"]


def tipo(p: Path) -> str:
    """"pdf", "imagem", "recusado" (documento que não sabemos converter) ou "" (vai para a importação)."""
    s = Path(p).suffix.lower()
    if Path(p).is_dir():
        return ""
    if s in PDF:
        return "pdf"
    if s in IMAGENS:
        return "imagem"
    if s in OUTROS_DOCUMENTOS:
        return "recusado"
    return ""


def separar(paths) -> tuple[list[Path], list[Path], list[Path]]:
    """(documentos para anexar, o resto para a importação de DICOM, recusados)."""
    docs, resto, recusados = [], [], []
    for p in paths:
        t = tipo(Path(p))
        (docs if t in ("pdf", "imagem") else recusados if t == "recusado" else resto).append(Path(p))
    return docs, resto, recusados


def _base(fonte: Dataset, sop_class: str, modalidade: str, serie_uid: str, numero: int, descricao: str,
          instancia: int, quem: str) -> Dataset:
    ds = Dataset()
    for kw in _PACIENTE_EXAME:
        if kw in fonte:
            setattr(ds, kw, fonte.data_element(kw).value)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    sop = generate_uid()
    meta.MediaStorageSOPInstanceUID = sop
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop
    ds.Modality = modalidade
    ds.SeriesInstanceUID = serie_uid
    ds.SeriesNumber = numero
    ds.SeriesDescription = descricao
    ds.InstanceNumber = instancia
    ds.Manufacturer = "Ipe"
    agora = datetime.now()
    ds.ContentDate, ds.ContentTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
    ds.SeriesDate, ds.SeriesTime = ds.ContentDate, ds.ContentTime
    ds.InstanceCreationDate, ds.InstanceCreationTime = ds.ContentDate, ds.ContentTime
    ds.SpecificCharacterSet = "ISO_IR 192"
    if quem:
        ds.OperatorsName = quem[:64]
    return ds


def pdf_dicom(arquivo: Path, fonte: Dataset, serie_uid: str, instancia: int = 1, quem: str = "") -> Dataset:
    dados = Path(arquivo).read_bytes()
    if not dados.startswith(b"%PDF"):
        raise ValueError(f"{Path(arquivo).name}: não parece um PDF")
    ds = _base(fonte, ENCAPSULATED_PDF, "DOC", serie_uid, SERIE_DOC, DESC_DOC, instancia, quem)
    ds.ConversionType = "WSD"
    ds.BurnedInAnnotation = "YES"
    ds.DocumentTitle = Path(arquivo).stem[:64]
    ds.ConceptNameCodeSequence = []
    ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
    ds.AcquisitionDateTime = datetime.now().strftime("%Y%m%d%H%M%S")
    if len(dados) % 2:
        dados += b"\x00"
    ds.EncapsulatedDocument = dados
    return ds


def paginas_da_imagem(arquivo: Path) -> list[np.ndarray]:
    """As páginas da imagem como RGB (altura × largura × 3, uint8). TIFF de várias páginas dá várias."""
    from PySide6.QtGui import QImage, QImageReader
    leitor = QImageReader(str(arquivo))
    leitor.setAutoTransform(True)                     # foto de celular deitada: respeita a orientação EXIF
    out = []
    n = max(1, leitor.imageCount())
    for i in range(n):
        if i:
            leitor.jumpToImage(i)
        img = leitor.read()
        if img.isNull():
            if not out:
                raise ValueError(f"{Path(arquivo).name}: não consegui ler a imagem ({leitor.errorString()})")
            break
        img = img.convertToFormat(QImage.Format_RGB888)
        w, h, bpl = img.width(), img.height(), img.bytesPerLine()
        buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=bpl * h).reshape(h, bpl)
        out.append(buf[:, : w * 3].reshape(h, w, 3).copy())
    return out


def imagem_dicom(rgb: np.ndarray, nome: str, fonte: Dataset, serie_uid: str, instancia: int = 1,
                 quem: str = "") -> Dataset:
    ds = _base(fonte, SECONDARY_CAPTURE, "OT", serie_uid, SERIE_IMG, DESC_IMG, instancia, quem)
    ds.ConversionType = "DI"
    ds.ImageComments = nome[:10240]
    ds.DerivationDescription = f"Anexado ao exame a partir de {nome}"[:1024]
    ds.BurnedInAnnotation = "YES"
    h, w = rgb.shape[:2]
    ds.Rows, ds.Columns = h, w
    ds.SamplesPerPixel = 3
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = np.ascontiguousarray(rgb, dtype=np.uint8).tobytes()
    return ds


def criar(arquivos, fonte, quem: str = "") -> tuple[list[Dataset], list[str]]:
    """Os objetos DICOM dos anexos (uma série de documentos e uma de imagens) e os avisos. `fonte`: um
    arquivo do exame (caminho) ou um Dataset com os dados do paciente e do exame."""
    if not isinstance(fonte, Dataset):
        fonte = pydicom.dcmread(str(fonte), stop_before_pixels=True, force=True)
    serie_doc, serie_img = generate_uid(), generate_uid()
    n_doc = n_img = 0
    out, avisos = [], []
    for arq in arquivos:
        arq = Path(arq)
        try:
            t = tipo(arq)
            if t == "pdf":
                n_doc += 1
                out.append(pdf_dicom(arq, fonte, serie_doc, n_doc, quem))
            elif t == "imagem":
                pags = paginas_da_imagem(arq)
                for i, rgb in enumerate(pags, 1):
                    n_img += 1
                    nome = arq.name + (f" (página {i} de {len(pags)})" if len(pags) > 1 else "")
                    out.append(imagem_dicom(rgb, nome, fonte, serie_img, n_img, quem))
            else:
                avisos.append(f"{arq.name}: formato não aceito — salve como PDF")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"{arq.name}: {e}")
    return out, avisos


def gravar(datasets: list[Dataset], pasta: Path) -> list[Path]:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for ds in datasets:
        p = pasta / f"{ds.SOPInstanceUID}.dcm"
        ds.save_as(p, enforce_file_format=True)
        caminhos.append(p)
    return caminhos


def documento_de(caminho: str) -> tuple[bytes, str, str]:
    """(bytes do documento, tipo MIME, título) de um arquivo DICOM com documento encapsulado."""
    ds = pydicom.dcmread(caminho, force=True)
    dados = bytes(ds.get("EncapsulatedDocument", b"") or b"")
    mime = str(ds.get("MIMETypeOfEncapsulatedDocument", "") or "application/pdf")
    if mime == "application/pdf" and dados.endswith(b"\x00"):
        fim = dados.rfind(b"%%EOF")
        if fim >= 0:
            dados = dados[: fim + 5] + dados[fim + 5:].rstrip(b"\x00")
    titulo = str(ds.get("DocumentTitle", "") or ds.get("SeriesDescription", "") or "Documento")
    return dados, mime, titulo
