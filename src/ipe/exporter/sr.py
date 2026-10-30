"""Medidas como DICOM SR (Comprehensive SR), para abrir em outros sistemas/PACS.

Estrutura: CONTAINER "Imaging Measurement Report" → para cada medida, NUM (comprimento, área,
média, DP, ângulo, SUV) ou TEXT (texto/seta), cada um INFERRED FROM um SCOORD (a geometria em
pixels) SELECTED FROM a IMAGE de origem.
"""

from __future__ import annotations

import json
from datetime import datetime

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.imaging import measure as M

COMPREHENSIVE_SR = "1.2.840.10008.5.1.4.1.1.88.33"
CODES = {
    "report": ("126000", "DCM", "Imaging Measurement Report"),
    "length": ("410668003", "SCT", "Length"),
    "area": ("42798000", "SCT", "Area"),
    "mean": ("373098007", "SCT", "Mean"),
    "sd": ("386136009", "SCT", "Standard Deviation"),
    "min": ("255605001", "SCT", "Minimum"),
    "max": ("56851009", "SCT", "Maximum"),
    "angle": ("1483009", "SCT", "Angle"),
    "suvmax": ("126032", "DCM", "SUVbw max"),
    "comment": ("121106", "DCM", "Comment"),
    "value": ("PIXVAL", "99DICOMVIEWER", "Pixel value"),
}
UNITS = {"mm": ("mm", "UCUM", "millimeter"), "mm2": ("mm2", "UCUM", "square millimeter"),
         "deg": ("deg", "UCUM", "degree"), "HU": ("[hnsf'U]", "UCUM", "Hounsfield unit"),
         "1": ("1", "UCUM", "no units"), "g/ml": ("g/ml{SUVbw}", "UCUM", "Standardized Uptake Value body weight")}
_COPY = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "StudyInstanceUID",
         "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription", "ReferringPhysicianName",
         "InstitutionName"]


def _code(key) -> Dataset:
    v, scheme, meaning = CODES[key] if isinstance(key, str) else key
    d = Dataset()
    d.CodeValue, d.CodingSchemeDesignator, d.CodeMeaning = v, scheme, meaning
    return d


def _item(value_type: str, rel: str, name=None) -> Dataset:
    d = Dataset()
    d.RelationshipType, d.ValueType = rel, value_type
    if name is not None:
        d.ConceptNameCodeSequence = [_code(name)]
    return d


def _image_ref(ref: dict) -> Dataset:
    img = _item("IMAGE", "SELECTED FROM")
    r = Dataset()
    r.ReferencedSOPClassUID, r.ReferencedSOPInstanceUID = ref["sop_class"], ref["sop_uid"]
    if ref.get("frames", 1) > 1:
        r.ReferencedFrameNumber = ref["frame_index"] + 1
    img.ReferencedSOPSequence = [r]
    return img


def _scoord(kind: str, pts: list, ref: dict) -> Dataset:
    sc = _item("SCOORD", "INFERRED FROM")
    p = [(float(x), float(y)) for x, y in pts]
    if kind == "ellipse" and len(p) >= 2:
        (x0, y0), (x1, y1) = p[0], p[1]
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
        gt, p = "ELLIPSE", [(cx - rx, cy), (cx + rx, cy), (cx, cy - ry), (cx, cy + ry)]
    elif kind == "rect" and len(p) >= 2:
        (x0, y0), (x1, y1) = p[0], p[1]
        gt, p = "POLYLINE", [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    elif kind == "polygon":
        gt, p = "POLYLINE", p + p[:1]
    elif len(p) == 1:
        gt = "POINT"
    else:
        gt = "POLYLINE"
    sc.GraphicType = gt
    sc.GraphicData = [round(v, 3) for xy in p for v in xy]
    sc.ContentSequence = [_image_ref(ref)]
    return sc


def _num(name, value: float, unit: str, scoord: Dataset) -> Dataset:
    n = _item("NUM", "CONTAINS", name)
    mv = Dataset()
    mv.NumericValue = f"{value:.4g}"[:16]
    mv.MeasurementUnitsCodeSequence = [_code(UNITS[unit])]
    n.MeasuredValueSequence = [mv]
    n.ContentSequence = [scoord]
    return n


def build_sr(repo, study_uid: str, series_uids: list[str] | None = None, suv_factors: dict | None = None):
    """Monta o SR com as medidas do estudo (ou só destas séries). Devolve (dataset, nº de medidas)."""
    from ipe.imaging.series import build_frames, read_frame
    series = [s for s in repo.series_for_study(study_uid) if not series_uids or s.series_uid in series_uids]
    anns = repo.annotations_for_series([s.series_uid for s in series])
    if not anns:
        return None, 0
    items, first_ds = [], None
    frames_by_series = {}
    for a in anns:
        fr = frames_by_series.get(a["series_uid"])
        if fr is None:
            fr = frames_by_series[a["series_uid"]] = {(f.sop_uid, f.frame_index): f for f in
                                                      build_frames(repo.instances_for_series(a["series_uid"]),
                                                                   a["series_uid"])}
        f = fr.get((a["sop_uid"], int(a["frame_index"])))
        if f is None:
            continue
        ds = pydicom.dcmread(f.path, stop_before_pixels=True, force=True)
        first_ds = first_ds or ds
        ref = {"sop_class": str(ds.SOPClassUID), "sop_uid": a["sop_uid"], "frame_index": int(a["frame_index"]),
               "frames": int(ds.get("NumberOfFrames", 1) or 1)}
        d = json.loads(a.get("data") or "{}")
        pts = [tuple(p) for p in d.get("points", [])]
        kind, text = a["kind"], d.get("text", "")
        if not pts:
            continue
        img = read_frame(f)
        sp = img.pixel_spacing
        modality = str(ds.get("Modality", ""))
        unit_v = "HU" if modality == "CT" else "1"
        sc = lambda: _scoord(kind, pts, ref)  # noqa: E731
        if kind in ("line", "arrow") and len(pts) >= 2 and kind == "line":
            items.append(_num("length", M.length_mm(pts[0], pts[1], sp), "mm", sc()))
        elif kind == "polyline" and len(pts) >= 2:
            items.append(_num("length", M.polyline_mm(pts, sp), "mm", sc()))
        elif kind == "angle" and len(pts) >= 3:
            items.append(_num("angle", M.angle_deg(pts[0], pts[1], pts[2], sp), "deg", sc()))
        elif kind == "cobb" and len(pts) >= 4:
            items.append(_num("angle", M.cobb_deg(*pts[:4], sp), "deg", sc()))
        elif kind in M.ROI_KINDS and len(pts) >= 2 and not img.is_color:
            st = M.roi_stats(img.pixels, kind if kind != "tic" else "ellipse", pts, sp)
            if st.area_mm2 is not None:
                items.append(_num("area", st.area_mm2, "mm2", sc()))
            if st.mean is not None:
                items.append(_num("mean", st.mean, unit_v, sc()))
                items.append(_num("sd", st.sd, unit_v, sc()))
                items.append(_num("min", st.minimum, unit_v, sc()))
                items.append(_num("max", st.maximum, unit_v, sc()))
                fac = (suv_factors or {}).get(a["series_uid"])
                if fac:
                    items.append(_num("suvmax", st.maximum * fac, "g/ml", sc()))
        elif kind == "probe" and not img.is_color:
            v = M.pixel_value(img.pixels, pts[0])
            if v is not None:
                items.append(_num("value", v, unit_v, sc()))
        if text and kind in ("text", "arrow", "tic", "probe", "line"):
            t = _item("TEXT", "CONTAINS", "comment")
            t.TextValue = text[:1024]
            t.ContentSequence = [sc()]
            items.append(t)
    if not items or first_ds is None:
        return None, 0
    ds = Dataset()
    for kw in _COPY:
        if kw in first_ds:
            setattr(ds, kw, first_ds.data_element(kw).value)
    now = datetime.now()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = COMPREHENSIVE_SR
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    ds.SOPClassUID = COMPREHENSIVE_SR
    ds.Modality = "SR"
    ds.SeriesInstanceUID, ds.SeriesNumber, ds.InstanceNumber = generate_uid(), 999, 1
    ds.SeriesDescription = "Medidas (Ipe)"
    ds.ContentDate, ds.ContentTime = now.strftime("%Y%m%d"), now.strftime("%H%M%S")
    ds.InstanceCreationDate, ds.InstanceCreationTime = ds.ContentDate, ds.ContentTime
    ds.Manufacturer = "Ipe"
    ds.CompletionFlag, ds.VerificationFlag = "COMPLETE", "UNVERIFIED"
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = [_code("report")]
    ds.ContinuityOfContent = "SEPARATE"
    ds.ContentTemplateSequence = []
    ds.ContentSequence = Sequence(items)
    return ds, len(items)


def summarize(ds) -> list[str]:
    """Linhas legíveis do SR (para conferência/testes)."""
    out = []
    for it in ds.ContentSequence:
        name = it.ConceptNameCodeSequence[0].CodeMeaning if "ConceptNameCodeSequence" in it else ""
        if it.ValueType == "NUM":
            mv = it.MeasuredValueSequence[0]
            out.append(f"{name}: {mv.NumericValue} {mv.MeasurementUnitsCodeSequence[0].CodeValue}")
        elif it.ValueType == "TEXT":
            out.append(f"{name}: {it.TextValue}")
    return out


