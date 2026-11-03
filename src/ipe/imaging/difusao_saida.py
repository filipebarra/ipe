"""Grava os mapas da difusão (ADC, DWI sintética) como série de RM do exame (0.99.37).

A série nova tem a geometria de cada corte da DWI de origem (posição, orientação, espaçamento,
Frame of Reference): sincroniza com as outras séries, mede com as ROIs de sempre, vai para o filme,
para a exportação e para o PACS. Os arquivos de origem não mudam.

- ADC: inteiros em 10⁻⁶ mm²/s (como o "ADC (10^-6 mm²/s)" da GE, só que sem o intercept −1),
  ImageType DERIVED\\PRIMARY\\DIFFUSION\\ADC.
- DWI sintética: ImageType DERIVED\\SECONDARY\\DIFFUSION\\SYNTHETIC, b no (0018,9087), e a descrição
  diz "sintética" — para ninguém calcular ADC em cima dela.
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

log = logging.getLogger(__name__)

MR_SOP = "1.2.840.10008.5.1.4.1.1.4"
_COPIAR = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "PatientWeight",
           "StudyInstanceUID", "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription",
           "ReferringPhysicianName", "InstitutionName", "FrameOfReferenceUID", "BodyPartExamined",
           "Manufacturer", "ManufacturerModelName", "PatientPosition", "SeriesDate", "SeriesTime",
           "ImagePositionPatient", "ImageOrientationPatient", "PixelSpacing", "SliceThickness",
           "SpacingBetweenSlices", "SliceLocation", "MagneticFieldStrength", "EchoTime", "RepetitionTime",
           "ScanningSequence", "SequenceVariant", "Laterality"]


def gravar(db, storage_root, mapa, volume: np.ndarray, descricao: str, tipo: str = "adc",
           b: float | None = None, series_number: int = 0) -> tuple[str, list[str]]:
    """`volume`: (n, h, w), um corte por `mapa.cortes`. Devolve (SeriesInstanceUID, SOPs)."""
    from ipe.importer.scanner import Importer
    from ipe.imaging.derived import _miniaturas
    serie_uid = generate_uid()
    agora = datetime.now()
    if tipo == "adc":
        slope, intercept = 1.0, 0.0
        image_type = ["DERIVED", "PRIMARY", "DIFFUSION", "ADC"]
        janela = (2000.0, 1000.0)
    else:
        vmax = float(np.percentile(volume[volume > 0], 99.5)) if (volume > 0).any() else 1.0
        slope = max(vmax / 30000.0, 1e-6)
        intercept = 0.0
        image_type = ["DERIVED", "SECONDARY", "DIFFUSION", "SYNTHETIC"]
        janela = (vmax, vmax / 2)
    numero = series_number or (980 if tipo == "adc" else 981)
    tmp = Path(tempfile.mkdtemp(prefix="ipe_dwi_"))
    sops = []
    try:
        for n, (corte, px) in enumerate(zip(mapa.cortes, volume), 1):
            origem = corte.imagens[min(corte.imagens)]
            src = pydicom.dcmread(origem, stop_before_pixels=True, force=True)
            ds = pydicom.Dataset()
            for kw in _COPIAR:
                if kw in src:
                    setattr(ds, kw, src.data_element(kw).value)
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = MR_SOP
            sop = generate_uid()
            meta.MediaStorageSOPInstanceUID = sop
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.file_meta = meta
            ds.SOPClassUID, ds.SOPInstanceUID = MR_SOP, sop
            ds.Modality = "MR"
            ds.SeriesInstanceUID, ds.SeriesNumber, ds.SeriesDescription = serie_uid, numero, descricao[:64]
            ds.InstanceNumber = n
            ds.ImageType = image_type
            ds.DerivationDescription = (f"Ipe: {descricao}; b usados {', '.join(str(int(x)) for x in mapa.bs)}; "
                                        f"limiar de ruido {mapa.limiar:.1f}")[:1024]
            ds.SourceImageSequence = [pydicom.Dataset()]
            ds.SourceImageSequence[0].ReferencedSOPClassUID = str(src.get("SOPClassUID", MR_SOP))
            ds.SourceImageSequence[0].ReferencedSOPInstanceUID = str(src.get("SOPInstanceUID", ""))
            ds.ContentDate, ds.ContentTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
            if b is not None:
                ds.add_new((0x0018, 0x9087), "FD", float(b))
            raw = np.clip(np.round((np.asarray(px, dtype=np.float64) - intercept) / slope), 0, 32767).astype(np.int16)
            ds.Rows, ds.Columns = raw.shape
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
            ds.RescaleSlope, ds.RescaleIntercept = f"{slope:.8g}", f"{intercept:.8g}"
            ds.WindowWidth, ds.WindowCenter = f"{janela[0]:.1f}", f"{janela[1]:.1f}"
            ds.PixelData = raw.tobytes()
            ds.save_as(tmp / f"{n:05d}.dcm", enforce_file_format=True)
            sops.append(sop)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        _miniaturas(db, r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return serie_uid, sops
