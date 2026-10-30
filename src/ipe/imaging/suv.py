"""SUV (standardized uptake value, pelo peso corporal) em PET.

SUVbw = concentração (Bq/ml) × peso (g) / dose injetada corrigida pelo decaimento até o início da
aquisição (Bq). Os pixels do PET já vêm em Bq/ml quando Units = BQML (depois do rescale).
"""

from __future__ import annotations

import math
from datetime import datetime

import pydicom


def _dt(date: str, time: str) -> datetime | None:
    date, time = (date or "").strip(), (time or "").strip()
    if not date or not time:
        return None
    t = time.split(".")[0].ljust(6, "0")[:6]
    try:
        return datetime.strptime(date[:8] + t, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def suv_factor(ds) -> tuple[float | None, str]:
    """(fator, motivo). Multiplicar o valor do pixel (Bq/ml) pelo fator dá o SUVbw."""
    if str(ds.get("Modality", "")).upper() != "PT":
        return None, "não é PET"
    units = str(ds.get("Units", "")).upper()
    if units == "GML":
        return 1.0, "a imagem já está em SUV (g/ml)"
    if units not in ("BQML", ""):
        return None, f"unidade {units} (SUV só com Bq/ml)"
    try:
        weight_kg = float(ds.get("PatientWeight") or 0)
    except (TypeError, ValueError):
        weight_kg = 0
    if weight_kg <= 0:
        return None, "sem o peso do paciente"
    seq = ds.get("RadiopharmaceuticalInformationSequence")
    if not seq:
        return None, "sem dados do radiofármaco"
    rp = seq[0]
    try:
        dose = float(rp.get("RadionuclideTotalDose") or 0)
        half = float(rp.get("RadionuclideHalfLife") or 0)
    except (TypeError, ValueError):
        return None, "dose ou meia-vida inválidas"
    if dose <= 0 or half <= 0:
        return None, "sem dose ou meia-vida"
    inj = None
    if rp.get("RadiopharmaceuticalStartDateTime"):
        v = str(rp.RadiopharmaceuticalStartDateTime)
        inj = _dt(v[:8], v[8:])
    if inj is None:
        inj = _dt(str(ds.get("SeriesDate", "") or ds.get("StudyDate", "")), str(rp.get("RadiopharmaceuticalStartTime", "")))
    decay_corr = str(ds.get("DecayCorrection", "START")).upper()
    ref = None
    if decay_corr == "START":
        ref = _dt(str(ds.get("SeriesDate", "") or ds.get("AcquisitionDate", "")),
                  str(ds.get("SeriesTime", "") or ds.get("AcquisitionTime", "")))
    elif decay_corr == "ADMIN":
        ref = inj
    if inj is None or ref is None:
        return None, "sem horário da injeção ou da aquisição"
    dt = (ref - inj).total_seconds()
    if dt < -3600 * 12:            # injeção no dia anterior à meia-noite, etc.
        dt += 24 * 3600
    decayed = dose * math.exp(-math.log(2) * dt / half)
    if decayed <= 0:
        return None, "dose corrigida inválida"
    return weight_kg * 1000.0 / decayed, "SUVbw"


def suv_factor_for_file(path: str) -> tuple[float | None, str]:
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    return suv_factor(ds)
