"""Grava o exame registrado "no plano do outro" como série nova (0.99.38).

Depois do registro rígido, o exame B (o anterior, outra sequência) é reamostrado na grade de A: mesmos
cortes, mesma orientação, mesmo espaçamento e **o mesmo Frame of Reference** de A. A série nova fica no
exame de B (os dados são dele), e por ter a geometria de A sincroniza com A corte a corte: o cursor 3D,
as linhas de referência e uma ROI desenhada num caem no mesmo lugar do outro.

Os arquivos de B não mudam. A descrição diz que é registrada e com qual exame.
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

_DO_PACIENTE = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "PatientWeight",
                "StudyInstanceUID", "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription",
                "ReferringPhysicianName", "InstitutionName", "Modality", "BodyPartExamined", "Manufacturer",
                "SeriesDate", "SeriesTime", "Units", "RescaleType", "EchoTime", "RepetitionTime"]
KEEP = {"1.2.840.10008.5.1.4.1.1.2": "CT", "1.2.840.10008.5.1.4.1.1.4": "MR", "1.2.840.10008.5.1.4.1.1.128": "PT"}


def gravar(db, storage_root, vol_a, dados: np.ndarray, origem_b: str, origem_a: str, descricao: str,
           M=None, progresso=None) -> tuple[str, list[str]]:
    """`dados`: (nz, ny, nx) de B na grade de A. `origem_b`/`origem_a`: um arquivo de cada série (paciente
    e estudo de B; Frame of Reference de A). Devolve (SeriesInstanceUID, SOPs)."""
    from ipe.importer.scanner import Importer
    from ipe.imaging.derived import _miniaturas
    src_b = pydicom.dcmread(origem_b, stop_before_pixels=True, force=True)
    src_a = pydicom.dcmread(origem_a, stop_before_pixels=True, force=True)
    sop_class = str(src_b.get("SOPClassUID", ""))
    if sop_class not in KEEP:
        sop_class = "1.2.840.10008.5.1.4.1.1.7"
    serie = generate_uid()
    agora = datetime.now()
    v = dados[np.isfinite(dados)]
    vmin, vmax = (float(v.min()), float(v.max())) if v.size else (0.0, 1.0)
    inteiro = np.allclose(v[: 5000], np.round(v[: 5000])) if v.size else True
    if inteiro and vmin >= -32768 and vmax <= 32767:
        slope, intercept = 1.0, 0.0
    else:
        slope = max((vmax - vmin) / 60000.0, 1e-6)
        intercept = vmin + 30000 * slope
    janela = None
    if "WindowWidth" in src_b and "WindowCenter" in src_b:
        try:
            ww, wc = src_b.WindowWidth, src_b.WindowCenter
            janela = (float(ww[0] if hasattr(ww, "__len__") and not isinstance(ww, str) else ww),
                      float(wc[0] if hasattr(wc, "__len__") and not isinstance(wc, str) else wc))
        except (TypeError, ValueError):
            janela = None
    nz = dados.shape[0]
    tmp = Path(tempfile.mkdtemp(prefix="ipe_reg_"))
    sops = []
    try:
        for k in range(nz):
            ds = pydicom.Dataset()
            for kw in _DO_PACIENTE:
                if kw in src_b:
                    setattr(ds, kw, src_b.data_element(kw).value)
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = sop_class
            sop = generate_uid()
            meta.MediaStorageSOPInstanceUID = sop
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.file_meta = meta
            ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop
            ds.Modality = str(src_b.get("Modality", KEEP.get(sop_class, "OT")))
            ds.SeriesInstanceUID, ds.SeriesNumber, ds.SeriesDescription = serie, 990, descricao[:64]
            ds.InstanceNumber = k + 1
            ds.ImageType = ["DERIVED", "SECONDARY", "REGISTERED"]
            mtxt = "" if M is None else "; matriz " + " ".join(f"{x:.5g}" for x in np.asarray(M)[:3].ravel())
            ds.DerivationDescription = f"Ipe: registro rigido no exame {src_a.get('StudyDate', '')}{mtxt}"[:1024]
            if "FrameOfReferenceUID" in src_a:
                ds.FrameOfReferenceUID = src_a.FrameOfReferenceUID       # a geometria agora é a de A
            ds.ContentDate, ds.ContentTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
            ds.ImagePositionPatient = [f"{x:.4f}" for x in vol_a.voxel_to_patient(0, 0, k)]
            ds.ImageOrientationPatient = [f"{x:.6f}" for x in (*vol_a.row_dir, *vol_a.col_dir)]
            ds.PixelSpacing = [f"{vol_a.dy:.6f}", f"{vol_a.dx:.6f}"]
            ds.SliceThickness = f"{vol_a.dz:.4f}"
            ds.SpacingBetweenSlices = f"{vol_a.dz:.4f}"
            raw = np.clip(np.round((np.nan_to_num(dados[k]) - intercept) / slope), -32768, 32767).astype(np.int16)
            ds.Rows, ds.Columns = raw.shape
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
            ds.RescaleSlope, ds.RescaleIntercept = f"{slope:.8g}", f"{intercept:.8g}"
            if janela:
                ds.WindowWidth, ds.WindowCenter = f"{janela[0]:.1f}", f"{janela[1]:.1f}"
            ds.PixelData = raw.tobytes()
            ds.save_as(tmp / f"{k + 1:05d}.dcm", enforce_file_format=True)
            sops.append(sop)
            if progresso is not None and progresso(k + 1, nz) is False:
                raise InterruptedError("Gravação interrompida.")
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        _miniaturas(db, r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return serie, sops
