"""Corrigir tags DICOM gravando uma cópia — o exame original nunca é tocado.

Serve para o que acontece na rotina: nome trocado, lado errado, incidência errada, data
digitada errada no aparelho. A cópia corrigida entra no banco ao lado do original, com UIDs
novos e uma referência à imagem de onde veio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pydicom
from pydicom.uid import generate_uid

log = logging.getLogger(__name__)

NOTE = "Tags corrigidas no Ipê"


@dataclass(frozen=True)
class Field:
    keyword: str
    label: str
    level: str            # patient | study | series | image
    hint: str = ""


FIELDS: list[Field] = [
    Field("PatientName", "Nome do paciente", "patient", "Sobrenome^Nome"),
    Field("PatientID", "ID do paciente", "patient"),
    Field("PatientBirthDate", "Nascimento", "patient", "AAAAMMDD"),
    Field("PatientSex", "Sexo", "patient", "M, F ou O"),
    Field("AccessionNumber", "Accession", "study"),
    Field("StudyDate", "Data do exame", "study", "AAAAMMDD"),
    Field("StudyTime", "Hora do exame", "study", "HHMMSS"),
    Field("StudyDescription", "Descrição do exame", "study"),
    Field("ReferringPhysicianName", "Médico solicitante", "study"),
    Field("InstitutionName", "Instituição", "study"),
    Field("Modality", "Modalidade", "series", "MG, CT, MR…"),
    Field("SeriesNumber", "Número da série", "series"),
    Field("SeriesDescription", "Descrição da série", "series"),
    Field("BodyPartExamined", "Parte examinada", "series"),
    Field("ProtocolName", "Protocolo", "series"),
    Field("StationName", "Aparelho (estação)", "series"),
    Field("OperatorsName", "Técnico", "series"),
    Field("ImageLaterality", "Lado (mamografia)", "image", "R ou L"),
    Field("Laterality", "Lado", "image", "R ou L"),
    Field("ViewPosition", "Incidência", "image", "CC, MLO, AP…"),
    Field("PatientOrientation", "Orientação", "image", "Ex.: A\\F"),
    Field("InstanceNumber", "Número da imagem", "image"),
]

BY_KEYWORD = {f.keyword: f for f in FIELDS}
LEVELS = {"patient": "Paciente", "study": "Exame", "series": "Série", "image": "Imagem"}


def read_values(path: Path | str) -> dict[str, str]:
    """Valores atuais dos campos que dá para corrigir."""
    ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
    out: dict[str, str] = {}
    for f in FIELDS:
        v = ds.get(f.keyword, None)
        out[f.keyword] = "" if v is None else str(v)
    return out


def needs_new_study(edits: dict[str, str]) -> bool:
    """Mexer em paciente ou exame cria um exame novo; série e imagem ficam no mesmo exame."""
    return any(BY_KEYWORD[k].level in ("patient", "study") for k in edits if k in BY_KEYWORD)


def describe(edits: dict[str, str], antes: dict[str, str]) -> list[str]:
    """Frases do tipo "Lado (mamografia): R → L", para você conferir antes de gravar."""
    linhas = []
    for k, v in edits.items():
        f = BY_KEYWORD.get(k)
        if f is None:
            continue
        de = (antes or {}).get(k, "")
        linhas.append(f"{f.label}: {de or '(vazio)'} → {v or '(vazio)'}")
    return linhas


def apply_to_files(files: list[Path | str], edits: dict[str, str], out_dir: Path | str,
                   mark: bool = True) -> list[Path]:
    """Grava cópias corrigidas em `out_dir` (não mexe nos arquivos de origem).

    UIDs novos: sempre a imagem e a série; o exame só quando a correção é de paciente/exame,
    para a cópia não se misturar com o original no banco.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    novo_exame = needs_new_study(edits)
    series_map: dict[str, str] = {}
    study_map: dict[str, str] = {}
    saida: list[Path] = []
    for i, origem in enumerate(files):
        try:
            ds = pydicom.dcmread(str(origem), force=True)
        except Exception:  # noqa: BLE001
            log.exception("Não foi possível ler %s", origem)
            continue
        antigo_sop = str(ds.get("SOPInstanceUID", "") or "")
        antiga_serie = str(ds.get("SeriesInstanceUID", "") or "")
        antigo_estudo = str(ds.get("StudyInstanceUID", "") or "")
        for k, v in edits.items():
            if k not in BY_KEYWORD:
                continue
            try:
                setattr(ds, k, v)
            except Exception:  # noqa: BLE001
                log.warning("Tag %s não aceitou o valor %r", k, v)
        ds.SeriesInstanceUID = series_map.setdefault(antiga_serie, generate_uid())
        if novo_exame:
            ds.StudyInstanceUID = study_map.setdefault(antigo_estudo, generate_uid())
        ds.SOPInstanceUID = generate_uid()
        if mark:
            ds.DerivationDescription = NOTE
            if "SeriesDescription" not in edits:
                atual = str(ds.get("SeriesDescription", "") or "")
                if "corrigid" not in atual.lower():
                    ds.SeriesDescription = (atual + " (corrigido)").strip()[:64]
            if antigo_sop:
                ref = pydicom.dataset.Dataset()
                ref.ReferencedSOPClassUID = ds.get("SOPClassUID", "")
                ref.ReferencedSOPInstanceUID = antigo_sop
                ds.SourceImageSequence = [ref]
        if getattr(ds, "file_meta", None) is not None:
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            if "SOPClassUID" in ds:
                ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        destino = out_dir / f"corrigido_{i + 1:05d}.dcm"
        try:
            ds.save_as(destino, enforce_file_format=True)
        except Exception:  # noqa: BLE001
            log.exception("Não foi possível gravar %s", destino)
            continue
        saida.append(destino)
    return saida
