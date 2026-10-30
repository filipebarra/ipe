"""Salva uma reconstrução (MPR, com ou sem slab/MIP) como série DICOM nova no banco.

Assim a reconstrução passa a ser uma série comum: vai para o filme, para a exportação, pode ser
enviada ao PACS e aparece na tira de séries. Os arquivos originais não mudam.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.imaging.volume import SLAB_MODES, MPRPlane

log = logging.getLogger(__name__)

KEEP_CLASSES = {"1.2.840.10008.5.1.4.1.1.2", "1.2.840.10008.5.1.4.1.1.4", "1.2.840.10008.5.1.4.1.1.128"}
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
_COPY = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "PatientWeight",
         "StudyInstanceUID", "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription",
         "ReferringPhysicianName", "InstitutionName", "Modality", "FrameOfReferenceUID", "BodyPartExamined",
         "Manufacturer", "PatientPosition", "Units", "DecayCorrection", "RadiopharmaceuticalInformationSequence",
         "SeriesDate", "SeriesTime", "AcquisitionDate", "AcquisitionTime", "CorrectedImage"]


def plane_description(plane: MPRPlane) -> str:
    if getattr(plane, "label", None):
        return plane.label
    slab = f" {SLAB_MODES.get(plane.mode, plane.mode)} {plane.slab_mm:g}mm" if plane.slab_mm else ""
    return f"MPR {plane.name}{slab}"


def plane_datasets(plane: MPRPlane, indices: list[int] | None = None, description: str | None = None,
                   series_number: int = 900):
    """Gera os datasets (um por corte) da reconstrução, copiando os dados do paciente/estudo."""
    src = pydicom.dcmread(plane.vol.source_path, stop_before_pixels=True, force=True)
    series_uid = generate_uid()
    desc = (description or plane_description(plane))[:64]
    sop_class = str(src.get("SOPClassUID", "")) if str(src.get("SOPClassUID", "")) in KEEP_CLASSES \
        else SECONDARY_CAPTURE
    now = datetime.now()
    idx = list(range(plane.n)) if indices is None else indices
    # escala única da série (int16), a partir de uma amostra de cortes
    sample = [plane.image(i).pixels for i in idx[:: max(1, len(idx) // 12)]]
    vmin = min(float(p.min()) for p in sample)
    vmax = max(float(p.max()) for p in sample)
    integral = all(np.allclose(p, np.round(p)) for p in sample[:3])
    if integral and vmin >= -32768 and vmax <= 32767:
        slope, intercept = 1.0, 0.0
    else:
        slope = max((vmax - vmin) / 60000.0, 1e-6)
        intercept = vmin + 30000 * slope
    thickness = max(plane.slab_mm, plane.step_mm)
    for n, i in enumerate(idx, 1):
        img = plane.image(i)
        px = img.pixels
        raw = np.clip(np.round((px - intercept) / slope), -32768, 32767).astype(np.int16)
        ds = pydicom.Dataset()
        for kw in _COPY:
            if kw in src:
                setattr(ds, kw, src.data_element(kw).value)
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = sop_class
        sop_uid = generate_uid()
        meta.MediaStorageSOPInstanceUID = sop_uid
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta = meta
        ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop_uid
        ds.SeriesInstanceUID, ds.SeriesNumber, ds.SeriesDescription = series_uid, series_number, desc
        ds.InstanceNumber = n
        ds.ImageType = getattr(plane, "image_type", None) or (
            ["DERIVED", "SECONDARY", "MPR"] if plane.slab_mm == 0 else
            ["DERIVED", "SECONDARY", "MPR", SLAB_MODES.get(plane.mode, plane.mode).upper()[:16]])
        ds.DerivationDescription = f"Ipe: {desc}"
        ds.ContentDate, ds.ContentTime = now.strftime("%Y%m%d"), now.strftime("%H%M%S")
        ds.ImagePositionPatient = [f"{v:.4f}" for v in plane.position(i)]
        ds.ImageOrientationPatient = [f"{v:.6f}" for v in plane.orientation]
        ds.PixelSpacing = [f"{plane.row_spacing:.6f}", f"{plane.col_spacing:.6f}"]
        ds.SliceThickness = f"{thickness:.3f}"
        ds.SpacingBetweenSlices = f"{plane.step_mm:.4f}"
        ds.Rows, ds.Columns = raw.shape
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleSlope, ds.RescaleIntercept = f"{slope:.8g}", f"{intercept:.8g}"
        if ds.get("Modality") == "CT":
            ds.RescaleType = "HU"
        if img.window:
            ds.WindowWidth, ds.WindowCenter = f"{img.window[0]:.1f}", f"{img.window[1]:.1f}"
        ds.PixelData = raw.tobytes()
        yield ds


class Cancelado(Exception):
    """O usuário parou a gravação no meio. Nada fica no banco."""


def save_plane_series(plane: MPRPlane, db, storage_root: Path, indices: list[int] | None = None,
                      description: str | None = None, progresso=None) -> tuple[str, list[str]]:
    """Grava e importa a série. Devolve (SeriesInstanceUID, SOPInstanceUIDs na ordem).

    `progresso(feitos, total, etapa)` é chamado a cada corte e devolve False para parar. Cada
    corte de uma reconstrução é **calculado** na hora de gravar, e num mapa de RM de mama são
    centenas: sem isso o programa fica parado, sem dizer nada, por dezenas de segundos.
    """
    from ipe.importer.scanner import Importer
    import shutil
    total = len(indices) if indices is not None else plane.n
    tmp = Path(tempfile.mkdtemp(prefix="dv_mpr_"))
    sops, series_uid = [], ""
    try:
        for n, ds in enumerate(plane_datasets(plane, indices, description), 1):
            ds.save_as(tmp / f"{n:05d}.dcm", enforce_file_format=True)
            sops.append(ds.SOPInstanceUID)
            series_uid = ds.SeriesInstanceUID
            if progresso is not None and not progresso(n, total, "cortes"):
                raise Cancelado("Gravação interrompida.")
        if progresso is not None:
            progresso(total, total, "importando")
        r = Importer(db, storage_root, copy_to_storage=True, origin="import").import_paths([tmp])
        _miniaturas(db, r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return series_uid, sops


def save_secondary_capture(rgb: np.ndarray, source_path: str, db, storage_root: Path,
                           description: str = "Gráfico", series_number: int = 950,
                           extra: dict | None = None) -> tuple[str, list[str]]:
    """Grava uma imagem RGB (H×W×3, uint8) como Secondary Capture no estudo do arquivo de origem
    e importa no banco. Devolve (SeriesInstanceUID, [SOPInstanceUID]).
    `extra`: atributos a mais (ex.: BurnedInAnnotation = "YES" quando a imagem traz o nome escrito)."""
    from ipe.importer.scanner import Importer
    src = pydicom.dcmread(source_path, stop_before_pixels=True, force=True)
    ds = pydicom.Dataset()
    for kw in _COPY:
        if kw in src and kw not in ("Modality", "FrameOfReferenceUID", "Units", "DecayCorrection",
                                    "RadiopharmaceuticalInformationSequence", "CorrectedImage"):
            setattr(ds, kw, src.data_element(kw).value)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SECONDARY_CAPTURE
    sop_uid, series_uid = generate_uid(), generate_uid()
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    now = datetime.now()
    ds.SOPClassUID, ds.SOPInstanceUID = SECONDARY_CAPTURE, sop_uid
    ds.Modality = "OT"
    ds.ConversionType = "WSD"
    ds.SeriesInstanceUID, ds.SeriesNumber, ds.SeriesDescription = series_uid, series_number, description[:64]
    ds.InstanceNumber = 1
    ds.ImageType = ["DERIVED", "SECONDARY"]
    ds.ContentDate, ds.ContentTime = now.strftime("%Y%m%d"), now.strftime("%H%M%S")
    rgb = np.ascontiguousarray(rgb[..., :3], dtype=np.uint8)
    ds.Rows, ds.Columns = rgb.shape[:2]
    ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.PixelData = rgb.tobytes()
    for k, v in (extra or {}).items():
        setattr(ds, k, v)
    tmp = Path(tempfile.mkdtemp(prefix="dv_sc_"))
    ds.save_as(tmp / "sc.dcm", enforce_file_format=True)
    r = Importer(db, Path(storage_root)).import_paths([tmp])
    _miniaturas(db, r)
    shutil.rmtree(tmp, ignore_errors=True)
    return series_uid, [sop_uid]


def _miniaturas(db, resultado) -> None:
    """A série gravada aqui aparece com miniatura no banco e na tira (antes vinha em branco)."""
    try:
        from ipe.db.repository import Repository
        from ipe.importer.thumbnails import generate_thumbnails
        generate_thumbnails(Repository(db), resultado.new_series)
    except Exception:  # noqa: BLE001
        log.exception("miniatura da série gravada")


def qimage_to_rgb(img) -> np.ndarray:
    """QImage -> array RGB uint8 (H×W×3)."""
    from PySide6.QtGui import QImage
    q = img.convertToFormat(QImage.Format_RGB888)
    w, h = q.width(), q.height()
    buf = np.frombuffer(q.constBits(), np.uint8, count=q.sizeInBytes()).reshape(h, q.bytesPerLine())
    return buf[:, : w * 3].reshape(h, w, 3).copy()
