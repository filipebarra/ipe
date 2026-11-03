"""Grava segmentações (imaging.segment) como DICOM SEG binário, no referencial da série de origem.

Assim a segmentação fica no exame (vai ao PACS, abre em outros visualizadores e volta a aparecer
aqui como sobreposição)."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.imaging.overlays import SEG_CLASS

_COPY = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "StudyInstanceUID",
         "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription", "ReferringPhysicianName",
         "FrameOfReferenceUID", "InstitutionName"]


def _code(v, s, m) -> Dataset:
    c = Dataset()
    c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = v, s, m
    return c


def rgb_to_lab16(rgb) -> list[int]:
    """RGB 0–255 -> CIELab no formato DICOM (0–65535)."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(x)) for x in rgb[:3])
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    Y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    L = 116 * f(Y) - 16
    a = 500 * (f(X) - f(Y))
    bb = 200 * (f(Y) - f(Z))
    return [int(round(max(0, min(100, L)) / 100 * 65535)), int(round((a + 128) / 255 * 65535)),
            int(round((bb + 128) / 255 * 65535))]


def build_seg(vol, segments: list[tuple], src_path: str, frames=None, series_number: int = 980,
              description: str = "Segmentação (Ipe)",
              algoritmo: tuple[str, str] = ("SEMIAUTOMATIC", "Ipe crescimento de região"),
              anatomia: bool = False) -> Dataset:
    """`segments`: lista de (SegResult, rótulo, cor RGB) — basta ter `.mask` (recorte) e `.offset`.
    `frames`: quadros da série de origem (para referenciar a imagem de cada corte).
    `algoritmo`: (tipo, nome) do SegmentAlgorithm; `anatomia`: órgão em vez de lesão (TotalSegmentator)."""
    src = pydicom.dcmread(src_path, stop_before_pixels=True, force=True)
    ds = Dataset()
    for kw in _COPY:
        if kw in src:
            setattr(ds, kw, src.data_element(kw).value)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SEG_CLASS
    sop = generate_uid()
    meta.MediaStorageSOPInstanceUID = sop
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    now = datetime.now()
    ds.SOPClassUID, ds.SOPInstanceUID = SEG_CLASS, sop
    ds.Modality = "SEG"
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber, ds.InstanceNumber = series_number, 1
    ds.SeriesDescription = description[:64]
    ds.ContentLabel = "SEGMENTACAO"
    ds.ContentDescription = description[:64]
    ds.ContentCreatorName = "Ipe"
    ds.ContentDate, ds.ContentTime = now.strftime("%Y%m%d"), now.strftime("%H%M%S")
    ds.SeriesDate, ds.SeriesTime = ds.ContentDate, ds.ContentTime
    ds.Manufacturer = "Ipe"
    ds.ManufacturerModelName = "Ipe"
    ds.DeviceSerialNumber = "1"
    ds.SoftwareVersions = "1"
    ds.ImageType = ["DERIVED", "PRIMARY"]
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    nz, ny, nx = vol.data.shape
    ds.Rows, ds.Columns = ny, nx
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 1, 1, 0, 0
    ds.LossyImageCompression = "00"
    ds.SegmentationType = "BINARY"
    shared = Dataset()
    po = Dataset()
    po.ImageOrientationPatient = [f"{v:.6f}" for v in np.concatenate([vol.row_dir, vol.col_dir])]
    pm = Dataset()
    pm.PixelSpacing = [f"{vol.dy:.6f}", f"{vol.dx:.6f}"]
    pm.SliceThickness = f"{vol.dz:.4f}"
    pm.SpacingBetweenSlices = f"{vol.dz:.4f}"
    shared.PlaneOrientationSequence = Sequence([po])
    shared.PixelMeasuresSequence = Sequence([pm])
    ds.SharedFunctionalGroupsSequence = Sequence([shared])
    dim_uid = generate_uid()
    d1, d2 = Dataset(), Dataset()
    d1.DimensionOrganizationUID = dim_uid
    d1.DimensionIndexPointer = 0x0062000B          # ReferencedSegmentNumber
    d1.FunctionalGroupPointer = 0x0062000A         # SegmentIdentificationSequence
    d2.DimensionOrganizationUID = dim_uid
    d2.DimensionIndexPointer = 0x00200032          # ImagePositionPatient
    d2.FunctionalGroupPointer = 0x00209113         # PlanePositionSequence
    org = Dataset()
    org.DimensionOrganizationUID = dim_uid
    ds.DimensionOrganizationSequence = Sequence([org])
    ds.DimensionIndexSequence = Sequence([d1, d2])

    # referência às imagens de origem, pela posição de cada corte
    by_pos = []
    src_class = str(src.get("SOPClassUID", ""))
    if frames:
        for f in frames:
            if f.position is not None:
                by_pos.append((np.asarray(f.position, float), f))
    normal = np.cross(vol.row_dir, vol.col_dir)

    def ref_for(pos):
        best, bd = None, 1e9
        for p, f in by_pos:
            d = abs(float((p - pos) @ normal))
            if d < bd:
                best, bd = f, d
        return best if best is not None and bd < max(vol.dz * 0.5, 0.2) else None

    seg_items, per_frame, planes = [], [], []
    used_refs: dict[str, str] = {}
    for n, item in enumerate(segments, 1):
        res, label, color = item[:3]
        # 0.99.40: o 4º elemento, quando vem, é o tipo da estrutura ("órgão" = anatomia; o resto = lesão)
        anat = anatomia if len(item) < 4 else item[3] == "órgão"
        s = Dataset()
        s.SegmentNumber = n
        s.SegmentLabel = (label or f"Segmento {n}")[:64]
        s.SegmentAlgorithmType = algoritmo[0]
        s.SegmentAlgorithmName = algoritmo[1][:64]
        if anat:
            s.SegmentedPropertyCategoryCodeSequence = Sequence([_code("123037004", "SCT", "Anatomical Structure")])
            s.SegmentedPropertyTypeCodeSequence = Sequence([_code("113343008", "SCT", "Organ")])
        else:
            s.SegmentedPropertyCategoryCodeSequence = Sequence([_code("49755003", "SCT", "Morphologically Altered Structure")])
            s.SegmentedPropertyTypeCodeSequence = Sequence([_code("4147007", "SCT", "Mass")])
        s.RecommendedDisplayCIELabValue = rgb_to_lab16(color)
        seg_items.append(s)
        k0, j0, i0 = res.offset
        for dk in range(res.mask.shape[0]):
            m = res.mask[dk]
            if not m.any():
                continue
            full = np.zeros((ny, nx), np.uint8)
            full[j0:j0 + m.shape[0], i0:i0 + m.shape[1]] = m
            planes.append(full)
            k = k0 + dk
            pos = vol.voxel_to_patient(0, 0, k)
            fg = Dataset()
            fc = Dataset()
            fc.DimensionIndexValues = [n, k + 1]
            fg.FrameContentSequence = Sequence([fc])
            pp = Dataset()
            pp.ImagePositionPatient = [f"{v:.4f}" for v in pos]
            fg.PlanePositionSequence = Sequence([pp])
            si = Dataset()
            si.ReferencedSegmentNumber = n
            fg.SegmentIdentificationSequence = Sequence([si])
            f = ref_for(pos)
            if f is not None:
                der = Dataset()
                srci = Dataset()
                srci.ReferencedSOPClassUID = src_class
                srci.ReferencedSOPInstanceUID = f.sop_uid
                srci.PurposeOfReferenceCodeSequence = Sequence([_code("121322", "DCM", "Source image for image processing operation")])
                der.SourceImageSequence = Sequence([srci])
                der.DerivationCodeSequence = Sequence([_code("113076", "DCM", "Segmentation")])
                fg.DerivationImageSequence = Sequence([der])
                used_refs[f.sop_uid] = src_class
            per_frame.append(fg)
    ds.SegmentSequence = Sequence(seg_items)
    ds.PerFrameFunctionalGroupsSequence = Sequence(per_frame)
    ds.NumberOfFrames = len(planes)
    if used_refs:
        rs = Dataset()
        rs.SeriesInstanceUID = str(src.get("SeriesInstanceUID", ""))
        items = []
        for uid, cls in used_refs.items():
            it = Dataset()
            it.ReferencedSOPClassUID, it.ReferencedSOPInstanceUID = cls, uid
            items.append(it)
        rs.ReferencedInstanceSequence = Sequence(items)
        ds.ReferencedSeriesSequence = Sequence([rs])
    bits = np.packbits(np.stack(planes).astype(np.uint8).ravel(), bitorder="little").tobytes() if planes else b""
    if len(bits) % 2:
        bits += b"\x00"
    ds.PixelData = bits
    return ds
