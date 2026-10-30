"""Salvar o filme no exame, no formato do "filme eletrônico" da estação AW da GE.

São três objetos, como a AW grava (conferido no exame de RM de mama que ele mandou, 10/10/2026):

- **SR** (*Enhanced SR*) "AW electronic film" — a planta do filme, sem pixel: uma página por
  folha, um grupo de vagas por página e uma vaga por imagem, com a referência da imagem e a
  posição/tamanho relativos (0 a 1) dentro do grupo. Códigos 99GEMS / modelo "AW41 EF TID".
- **imagens soltas** "AW electronic film" — cada célula como Secondary Capture, com a
  modalidade do exame (MR, CT…), o texto da célula gravado e `PixelSpacing` quando dá para
  medir. Mesmo número de série do SR.
- **folhas prontas** "AW electronic pages" — cada folha inteira, RGB, como sairia impressa.

A numeração das instâncias é intercalada como na AW: as imagens da folha 1, a folha 1, as
imagens da folha 2, a folha 2…

O que não se copia da AW: o fabricante. O arquivo diz que foi o Ipê quem gravou.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

log = logging.getLogger(__name__)

SC = "1.2.840.10008.5.1.4.1.1.7"
ENHANCED_SR = "1.2.840.10008.5.1.4.1.1.88.22"
DESC_FILME = "AW electronic film"
DESC_FOLHAS = "AW electronic pages"
DPI_PADRAO = 220            # A4 em pé sai 2560 px de altura, como as folhas da AW

# nomes do modelo de filme da AW (99GEMS)
C_RAIZ = ("AWVF-0001", "99GEMS", "Electronic Film Presentation")
C_PAGINA = ("AWVF-0002", "99GEMS", "Page Presentation")
C_GRUPO = ("AWVF-0003", "99GEMS", "Slot Group Presentation")
C_VAGA = ("AWVF-0004", "99GEMS", "Slot Presentation")
C_X = ("AWVF-0005", "99GEMS", "Relative horizontal position of top left corner")
C_Y = ("AWVF-0006", "99GEMS", "Relative vertical position of top left corner")
C_L = ("AWVF-0007", "99GEMS", "Relative horizontal size")
C_A = ("AWVF-0008", "99GEMS", "Relative vertical size")
C_OBSERVADOR = ("121008", "DCM", "Person Observer Name")
C_INSTITUICAO = ("121009", "DCM", "Person Observer's Organization Name")
C_TITULO = ("113011", "DCM", "Document Title Modifier")
C_PCT = ("%", "UCUM", "percent")

# do exame de origem para os objetos novos
_DO_EXAME = ["PatientName", "PatientID", "IssuerOfPatientID", "PatientBirthDate", "PatientSex",
             "PatientAge", "StudyInstanceUID", "StudyDate", "StudyTime", "StudyID", "AccessionNumber",
             "StudyDescription", "ReferringPhysicianName", "InstitutionName", "BodyPartExamined"]


@dataclass
class Vaga:
    imagem: object               # array H×W (cinza) ou H×W×3 (RGB), uint8
    mm_por_pixel: float | None   # na imagem gravada
    x: float                     # relativos (0 a 1) dentro do grupo de vagas
    y: float
    largura: float
    altura: float


@dataclass
class Folha:
    imagem: object               # H×W×3 uint8
    vagas: list[Vaga] = field(default_factory=list)


@dataclass
class ResultadoFilme:
    study_uid: str = ""
    serie_filme: str = ""
    serie_sr: str = ""
    serie_folhas: str = ""
    imagens: int = 0
    folhas: int = 0
    numero: int = 0              # número da série do filme (a das folhas é o seguinte)


# ------------------------------------------------------------------ desenho
def _rgb(q) -> np.ndarray:
    from ipe.imaging.derived import qimage_to_rgb
    return qimage_to_rgb(q)


def _cinza_se_der(rgb: np.ndarray):
    """Célula sem cor nenhuma vira cinza (como na AW); com cor (mapa, anotação) fica RGB."""
    if np.array_equal(rgb[..., 0], rgb[..., 1]) and np.array_equal(rgb[..., 1], rgb[..., 2]):
        return np.ascontiguousarray(rgb[..., 0])
    return rgb


def desenhar(film, src, cache, settings, dpi: float = DPI_PADRAO) -> list[Folha]:
    """Folhas e células do filme como imagens, na mesma resolução (a célula solta tem o mesmo
    tamanho que tem dentro da folha). Folha sem imagem nenhuma fica de fora."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    from ipe.ui.film.cell import FilmCell
    from ipe.ui.film.render import page_size_px, render_sheet_image, sheet_geometry
    k = dpi / 96.0
    out: list[Folha] = []
    cellw = FilmCell(cache, settings)
    cellw.interactive = False
    cellw.overlay, cellw.ruler, cellw.anonymize = film.overlay, film.ruler, film.anonymize
    try:
        for i, sheet in enumerate(film.sheets):
            if not any(c is not None for c in sheet.cells):
                continue
            size = page_size_px(sheet)
            _h, _f, rects = sheet_geometry(film, sheet, size)
            area = rects[0].united(rects[-1])
            folha = Folha(_rgb(render_sheet_image(film, i, src, cache, settings, dpi)))
            for cell, rect in zip(sheet.cells, rects):
                if cell is None:
                    continue
                img = QImage(max(1, round(rect.width() * k)), max(1, round(rect.height() * k)),
                             QImage.Format_RGB32)
                img.setDotsPerMeterX(round(96 / 0.0254))
                img.setDotsPerMeterY(round(96 / 0.0254))
                img.fill(QColor(0, 0, 0))
                p = QPainter(img)
                p.setRenderHint(QPainter.Antialiasing, True)
                p.setRenderHint(QPainter.TextAntialiasing, True)
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.scale(k, k)
                cellw.load(cell, src.frames(cell.series_uid), src.study_info(cell.study_uid), src.store)
                cellw.paint_to(p, QRectF(0, 0, rect.width(), rect.height()))
                mm = cellw.mm_por_pixel()
                p.end()
                folha.vagas.append(Vaga(
                    _cinza_se_der(_rgb(img)), mm / k if mm else None,
                    (rect.x() - area.x()) / area.width(), (rect.y() - area.y()) / area.height(),
                    rect.width() / area.width(), rect.height() / area.height()))
            out.append(folha)
    finally:
        cellw.deleteLater()
    return out


# ------------------------------------------------------------------ DICOM
def _codigo(c) -> Dataset:
    d = Dataset()
    d.CodeValue, d.CodingSchemeDesignator, d.CodeMeaning = c
    return d


def _item(rel: str, tipo: str, nome=None) -> Dataset:
    d = Dataset()
    d.RelationshipType = rel
    d.ValueType = tipo
    if nome is not None:
        d.ConceptNameCodeSequence = [_codigo(nome)]
    if tipo == "CONTAINER":
        d.ContinuityOfContent = "SEPARATE"
    return d


def _num(nome, valor: float) -> Dataset:
    d = _item("CONTAINS", "NUM", nome)
    mv = Dataset()
    mv.NumericValue = f"{round(float(valor), 6):g}"
    mv.MeasurementUnitsCodeSequence = [_codigo(C_PCT)]
    d.MeasuredValueSequence = [mv]
    return d


def _posicao(x, y, w, h) -> list[Dataset]:
    return [_num(C_X, x), _num(C_Y, y), _num(C_L, w), _num(C_A, h)]


def _base(origem: Dataset, sop_class: str, serie_uid: str, numero: int, descricao: str,
          modalidade: str, instancia: int, agora: datetime) -> Dataset:
    ds = Dataset()
    meta = FileMetaDataset()
    sop = generate_uid()
    meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID = sop_class, sop
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    ds.SpecificCharacterSet = "ISO_IR 192"
    for kw in _DO_EXAME:
        if kw in origem:
            setattr(ds, kw, origem.data_element(kw).value)
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop
    ds.Modality = modalidade
    ds.SeriesInstanceUID, ds.SeriesNumber, ds.SeriesDescription = serie_uid, numero, descricao
    ds.InstanceNumber = instancia
    ds.SeriesDate = ds.ContentDate = ds.InstanceCreationDate = agora.strftime("%Y%m%d")
    ds.SeriesTime = ds.ContentTime = ds.InstanceCreationTime = agora.strftime("%H%M%S")
    ds.Manufacturer = "Ipe"
    ds.ManufacturerModelName = "Ipe film"
    try:
        from ipe import __version__
        ds.SoftwareVersions = __version__
    except Exception:  # noqa: BLE001
        pass
    return ds


def _pixels(ds: Dataset, arr: np.ndarray) -> None:
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    ds.Rows, ds.Columns = arr.shape[:2]
    if arr.ndim == 2:
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.WindowCenter, ds.WindowWidth = 127.5, 256
    else:
        ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.PixelData = arr.tobytes()


def montar(folhas: list[Folha], origem: Dataset, modalidade: str, numero: int,
           agora: datetime | None = None, instituicao: str = "") -> list[Dataset]:
    """Os objetos do filme: [imagens soltas e folhas, intercaladas…, SR]."""
    agora = agora or datetime.now()
    s_filme, s_sr, s_folhas = generate_uid(), generate_uid(), generate_uid()
    out: list[Dataset] = []
    paginas: list[list[tuple[Dataset, Vaga]]] = []
    n = 0
    for folha in folhas:
        da_folha = []
        for v in folha.vagas:
            n += 1
            ds = _base(origem, SC, s_filme, numero, DESC_FILME, modalidade, n, agora)
            _sc(ds)
            _pixels(ds, v.imagem)
            if v.mm_por_pixel:
                ds.PixelSpacing = [f"{v.mm_por_pixel:.10g}"] * 2
            out.append(ds)
            da_folha.append((ds, v))
        n += 1
        pg = _base(origem, SC, s_folhas, numero + 1, DESC_FOLHAS, modalidade, n, agora)
        _sc(pg)
        _pixels(pg, folha.imagem)
        out.append(pg)
        paginas.append(da_folha)
    out.append(_sr(origem, s_sr, numero, paginas, agora, instituicao))
    return out


def _sc(ds: Dataset) -> None:
    ds.ImageType = ["DERIVED", "SECONDARY", "SCREEN SAVE"]
    ds.ConversionType = "WSD"
    ds.BurnedInAnnotation = "YES"
    ds.ImageComments = "Ipe"


def _sr(origem, serie_uid, numero, paginas, agora, instituicao) -> Dataset:
    ds = _base(origem, ENHANCED_SR, serie_uid, numero, DESC_FILME, "SR", 1, agora)
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = [_codigo(C_RAIZ)]
    ds.ContinuityOfContent = "SEPARATE"
    tpl = Dataset()
    tpl.MappingResource = "PRIVATE"
    tpl.TemplateIdentifier = "AW41 EF TID"
    ds.ContentTemplateSequence = [tpl]
    ds.CompletionFlag, ds.VerificationFlag = "COMPLETE", "UNVERIFIED"
    ds.ReferencedPerformedProcedureStepSequence = []
    ds.PerformedProcedureCodeSequence = []
    obs = _item("HAS OBS CONTEXT", "PNAME", C_OBSERVADOR)
    obs.PersonName = ""
    org = _item("HAS OBS CONTEXT", "TEXT", C_INSTITUICAO)
    org.TextValue = instituicao or str(origem.get("InstitutionName", "") or "")
    tit = _item("HAS CONCEPT MOD", "TEXT", C_TITULO)
    tit.TextValue = DESC_FILME
    conteudo = [obs, org, tit]
    refs = []
    for vagas in paginas:
        grupo = _item("CONTAINS", "CONTAINER", C_GRUPO)
        filhos = []
        for img, v in vagas:
            vaga = _item("CONTAINS", "CONTAINER", C_VAGA)
            im = _item("CONTAINS", "IMAGE")
            r = Dataset()
            r.ReferencedSOPClassUID, r.ReferencedSOPInstanceUID = img.SOPClassUID, img.SOPInstanceUID
            im.ReferencedSOPSequence = [r]
            vaga.ContentSequence = [im] + _posicao(v.x, v.y, v.largura, v.altura)
            filhos.append(vaga)
            refs.append(r)
        grupo.ContentSequence = filhos + _posicao(0, 0, 1, 1)
        pagina = _item("CONTAINS", "CONTAINER", C_PAGINA)
        pagina.ContentSequence = [grupo]
        conteudo.append(pagina)
    ds.ContentSequence = conteudo
    if refs:
        serie = Dataset()
        serie.SeriesInstanceUID = paginas[0][0][0].SeriesInstanceUID if paginas and paginas[0] else ""
        serie.ReferencedSOPSequence = refs
        estudo = Dataset()
        estudo.StudyInstanceUID = origem.get("StudyInstanceUID", "")
        estudo.ReferencedSeriesSequence = [serie]
        ds.CurrentRequestedProcedureEvidenceSequence = [estudo]
    return ds


# ------------------------------------------------------------------ para o banco
def exame_principal(film) -> tuple[str, str]:
    """(study_uid, series_uid) da primeira imagem do filme — o filme fica nesse exame."""
    for sheet in film.sheets:
        for c in sheet.cells:
            if c is not None:
                return c.study_uid, c.series_uid
    return "", ""


def proximo_numero(repo, study_uid: str) -> int:
    nums = [int(s.series_number or 0) for s in repo.series_for_study(study_uid, ocultas=True)]
    return max(nums, default=0) + 1


def salvar_no_exame(film, src, cache, settings, db, storage_root, repo, dpi: float = DPI_PADRAO,
                    agora: datetime | None = None) -> ResultadoFilme:
    from ipe.imaging.derived import _miniaturas
    from ipe.importer.scanner import Importer
    study_uid, series_uid = exame_principal(film)
    if not study_uid:
        raise ValueError("O filme está vazio.")
    inst = repo.instances_for_series(series_uid)
    if not inst:
        raise ValueError("A primeira imagem do filme não está no banco.")
    origem = pydicom.dcmread(inst[0]["path"], stop_before_pixels=True, force=True)
    modalidade = str(origem.get("Modality", "") or "OT")
    folhas = desenhar(film, src, cache, settings, dpi)
    numero = proximo_numero(repo, study_uid)
    objs = montar(folhas, origem, modalidade, numero, agora)
    tmp = Path(tempfile.mkdtemp(prefix="dv_filme_"))
    try:
        for k, ds in enumerate(objs, 1):
            ds.save_as(tmp / f"{k:04d}.dcm", enforce_file_format=True)
        r = Importer(db, Path(storage_root)).import_paths([tmp])
        _miniaturas(db, r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sc = [d for d in objs if d.Modality != "SR"]
    return ResultadoFilme(study_uid=study_uid,
                          serie_filme=next((d.SeriesInstanceUID for d in sc if d.SeriesDescription == DESC_FILME), ""),
                          serie_sr=objs[-1].SeriesInstanceUID,
                          serie_folhas=next((d.SeriesInstanceUID for d in sc if d.SeriesDescription == DESC_FOLHAS), ""),
                          imagens=sum(len(f.vagas) for f in folhas), folhas=len(folhas), numero=numero)
