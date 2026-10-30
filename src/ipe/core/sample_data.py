"""Gera exames DICOM sintéticos (fantomas) para testar o programa sem dados reais.

Uso: python -m ipe sample <pasta>

Cria: uma TC de 60 cortes (esferas com HU realistas), uma RM de 2 séries
com anterior, uma MG (CC/MLO bilateral), um US colorido e um multiframe.
Nenhum dado de paciente real é usado.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import (
    CTImageStorage, ExplicitVRLittleEndian, MRImageStorage, PYDICOM_IMPLEMENTATION_UID,
    SecondaryCaptureImageStorage, UltrasoundImageStorage, generate_uid,
)

DIGITAL_MG = "1.2.840.10008.5.1.4.1.1.1.2"   # Digital Mammography X-Ray Image Storage - For Presentation
NM_STORAGE = "1.2.840.10008.5.1.4.1.1.20"    # Nuclear Medicine Image Storage


def _base(sop_class: str, patient: dict, study: dict, series: dict, modality: str) -> Dataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    ds = Dataset()
    ds.file_meta = meta
    ds.SpecificCharacterSet = "ISO_IR 192"   # UTF-8 (acentos)
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.PatientName = patient["name"]
    ds.PatientID = patient["id"]
    ds.PatientBirthDate = patient["birth"]
    ds.PatientSex = patient["sex"]
    ds.StudyInstanceUID = study["uid"]
    ds.StudyDate = study["date"]
    ds.StudyTime = "101500"
    ds.AccessionNumber = study["accession"]
    ds.StudyDescription = study["description"]
    ds.StudyID = "1"
    ds.ReferringPhysicianName = "Solicitante^Teste"
    ds.InstitutionName = "Instituição Fictícia"
    ds.OperatorsName = ["Técnica^Maria", "Técnico^João"] if modality == "MR" else "Técnica^Maria"
    ds.StationName = f"{modality}01"
    ds.Manufacturer = "Fantoma"
    ds.ManufacturerModelName = f"Modelo {modality}"
    ds.SeriesInstanceUID = series["uid"]
    ds.SeriesNumber = series["number"]
    ds.SeriesDescription = series["description"]
    ds.Modality = modality
    ds.FrameOfReferenceUID = study.get("for", generate_uid())
    return ds


def _mono(ds: Dataset, px: np.ndarray, signed: bool) -> None:
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows, ds.Columns = px.shape
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1 if signed else 0
    ds.PixelData = px.astype(np.int16 if signed else np.uint16).tobytes()


def _save(ds: Dataset, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{ds.SOPInstanceUID}.dcm"
    ds.save_as(path, enforce_file_format=True)
    return path


def _ct_volume(n: int, size: int, shift: float = 0.0) -> np.ndarray:
    z, y, x = np.mgrid[0:n, 0:size, 0:size].astype(np.float32)
    cx = cy = size / 2
    vol = np.full((n, size, size), -1000, np.float32)                       # ar
    body = ((x - cx) / (size * 0.42)) ** 2 + ((y - cy) / (size * 0.32)) ** 2 < 1
    vol[body] = 40                                                           # partes moles
    lung_l = ((x - cx + size * 0.18) / (size * 0.13)) ** 2 + ((y - cy) / (size * 0.2)) ** 2 < 1
    lung_r = ((x - cx - size * 0.18) / (size * 0.13)) ** 2 + ((y - cy) / (size * 0.2)) ** 2 < 1
    vol[lung_l | lung_r] = -850                                              # pulmões
    spine = ((x - cx) ** 2 + (y - cy - size * 0.24) ** 2) < (size * 0.05) ** 2
    vol[spine] = 700                                                         # osso
    nod = ((x - cx - size * 0.2) ** 2 + (y - cy + size * 0.05) ** 2
           + ((z - n * (0.5 + shift)) * 2) ** 2) < (size * 0.035) ** 2
    vol[nod] = 30                                                            # nódulo
    rng = np.random.default_rng(0)
    vol += rng.normal(0, 12, vol.shape).astype(np.float32)
    return vol



# ---------------------------------------------------------------- medicina nuclear
def _elem(ds: Dataset, tag: tuple[int, int], vr: str, value) -> None:
    from pydicom.dataelem import DataElement
    ds[tag] = DataElement(tag, vr, value)


def _view_code(meaning: str) -> Dataset:
    code = Dataset()
    code.CodeValue = "T-D1000"
    code.CodingSchemeDesignator = "SRT"
    code.CodeMeaning = meaning
    det = Dataset()
    det.ViewCodeSequence = Sequence([code])
    return det


def _nm_pixels(ds: Dataset, frames: np.ndarray) -> None:
    px = np.clip(frames, 0, 65535).astype(np.uint16)
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.NumberOfFrames = int(px.shape[0])
    ds.Rows, ds.Columns = int(px.shape[1]), int(px.shape[2])
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = px.tobytes()


def _radiopharm(ds: Dataset, name: str, dose_bq: float, half_life_s: float, time: str = "090000") -> None:
    it = Dataset()
    it.Radiopharmaceutical = name
    it.RadionuclideTotalDose = dose_bq
    it.RadionuclideHalfLife = half_life_s
    it.RadiopharmaceuticalStartTime = time
    _elem(ds, (0x0054, 0x0016), "SQ", Sequence([it]))


def _bone_phantom(h: int, w: int, posterior: bool) -> np.ndarray:
    """Esqueleto grosseiro de corpo inteiro, com um foco quente numa costela."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = w / 2
    img = np.full((h, w), 12.0, np.float32)                     # fundo de partes moles
    img += 25 * np.exp(-(((xx - cx) / (w * 0.34)) ** 2))        # silhueta do corpo
    skull = ((xx - cx) / (w * 0.15)) ** 2 + ((yy - h * 0.06) / (h * 0.045)) ** 2 < 1
    img[skull] += 120
    spine = (np.abs(xx - cx) < w * 0.035) & (yy > h * 0.12) & (yy < h * 0.58)
    img[spine] += 300 if posterior else 120                      # coluna rende mais na POST
    sternum = (np.abs(xx - cx) < w * 0.03) & (yy > h * 0.16) & (yy < h * 0.32)
    img[sternum] += 40 if posterior else 190                     # esterno rende mais na ANT
    for k in range(7):                                           # arcos costais
        y0 = h * (0.17 + 0.035 * k)
        rib = np.abs(yy - y0 - 0.22 * np.abs(xx - cx)) < h * 0.006
        img[rib & (np.abs(xx - cx) < w * 0.3)] += 90
    pelvis = ((xx - cx) / (w * 0.26)) ** 2 + ((yy - h * 0.62) / (h * 0.05)) ** 2 < 1
    img[pelvis] += 210
    for side in (-1, 1):
        femur = (np.abs(xx - cx - side * w * 0.12) < w * 0.03) & (yy > h * 0.66) & (yy < h * 0.95)
        img[femur] += 110
        kidney = ((xx - cx - side * w * 0.14) / (w * 0.05)) ** 2 + ((yy - h * 0.46) / (h * 0.03)) ** 2 < 1
        img[kidney] += 70 if posterior else 30
    bladder = ((xx - cx) / (w * 0.07)) ** 2 + ((yy - h * 0.67) / (h * 0.025)) ** 2 < 1
    img[bladder] += 320
    # foco quente só à direita do paciente: some se a POST não for espelhada
    foco = ((xx - cx + w * 0.2) ** 2 + (yy - h * 0.28) ** 2) < (w * 0.035) ** 2
    img[foco] += 400
    if posterior:
        img = img[:, ::-1]              # a vista posterior é a imagem espelhada
    rng = np.random.default_rng(3 if posterior else 2)
    return np.clip(rng.poisson(np.clip(img, 0, None)), 0, None).astype(np.float32)


def _renal_phantom(n_flow: int, n_dyn: int, size: int) -> np.ndarray:
    """Renograma: fluxo rápido + dinâmico, com rim direito normal e esquerdo obstruído."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = size / 2

    def blob(dx: float, dy: float, rx: float, ry: float) -> np.ndarray:
        return np.clip(1 - (((xx - cx - dx) / rx) ** 2 + ((yy - dy) / ry) ** 2), 0, None)

    rim_d = blob(-size * 0.17, size * 0.42, size * 0.075, size * 0.115)
    rim_e = blob(size * 0.17, size * 0.42, size * 0.075, size * 0.115)
    bexiga = blob(0, size * 0.82, size * 0.09, size * 0.06)
    fundo = blob(0, size * 0.5, size * 0.45, size * 0.48)
    frames = []
    t = 0.0
    for i in range(n_flow + n_dyn):
        dur = 2.0 if i < n_flow else 30.0
        t += dur / 2
        # direito: sobe até 3 min e drena; esquerdo: sobe e não drena (obstrução)
        d = 100 * (1 - np.exp(-t / 45)) * np.exp(-max(t - 180, 0) / 220)
        e = 95 * (1 - np.exp(-t / 70))
        b = 4 * max(t - 120, 0) / 60
        vasc = 60 * np.exp(-t / 25)
        img = fundo * (6 + vasc) + rim_d * (d + vasc) + rim_e * (e + vasc) + bexiga * b
        rng = np.random.default_rng(100 + i)
        frames.append(rng.poisson(np.clip(img * dur / 10, 0, None)).astype(np.float32))
        t += dur / 2
    return np.stack(frames)


def _dmsa_phantom(h: int, w: int, posterior: bool) -> np.ndarray:
    """Dois rins com captação diferente (70/30) e um fundo de partes moles."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = w / 2
    img = np.full((h, w), 4.0, np.float32)
    img += 10 * np.exp(-(((xx - cx) / (w * 0.42)) ** 2 + ((yy - h * 0.5) / (h * 0.45)) ** 2))
    for side, forca in ((-1, 210.0), (1, 90.0)):          # direito do paciente rende mais
        rim = np.clip(1 - (((xx - cx - side * w * 0.2) / (w * 0.10)) ** 2
                           + ((yy - h * 0.46) / (h * 0.17)) ** 2), 0, None)
        img += rim * (forca if not posterior else forca * 1.6)   # POST conta mais (rim posterior)
    if posterior:
        img = img[:, ::-1]
    rng = np.random.default_rng(11 if posterior else 10)
    return np.clip(rng.poisson(np.clip(img, 0, None)), 0, None).astype(np.float32)


def _seringa(h: int, w: int, forca: float) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ponto = np.clip(1 - (((xx - w / 2) / (w * 0.08)) ** 2 + ((yy - h / 2) / (h * 0.08)) ** 2), 0, None)
    rng = np.random.default_rng(int(forca) % 97)
    return np.clip(rng.poisson(np.clip(ponto * forca + 1.0, 0, None)), 0, None).astype(np.float32)


def _make_nm(out: Path, patient: dict, today) -> list[Path]:
    """Dois exames de medicina nuclear: corpo inteiro ósseo (ANT/POST) e renograma."""
    files: list[Path] = []
    tc99m = 6.0058 * 3600

    # cintilografia óssea de corpo inteiro: ANT e POST no mesmo arquivo
    study = {"uid": generate_uid(), "date": today.strftime("%Y%m%d"), "accession": "ACC5001",
             "description": "CINTILOGRAFIA ÓSSEA DE CORPO INTEIRO", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "Corpo inteiro ANT/POST"}
    ds = _base(NM_STORAGE, patient, study, series, "NM")
    ds.InstanceNumber = 1
    ds.ImageType = ["ORIGINAL", "PRIMARY", "WHOLE BODY", "EMISSION"]
    _elem(ds, (0x0054, 0x1000), "CS", ["WHOLE BODY", "IMAGE"])
    _elem(ds, (0x0054, 0x0020), "US", [1, 2])                       # Detector Vector
    _elem(ds, (0x0054, 0x0021), "US", 2)                            # Number of Detectors
    _elem(ds, (0x0054, 0x0022), "SQ",
          Sequence([_view_code("anterior"), _view_code("posterior")]))
    ds.ActualFrameDuration = 600000                                  # 10 min de varredura
    ds.PixelSpacing = [2.2, 2.2]
    _radiopharm(ds, "Tc-99m MDP", 7.4e8, tc99m)
    h, w = 512, 256
    _nm_pixels(ds, np.stack([_bone_phantom(h, w, False), _bone_phantom(h, w, True)]))
    files.append(_save(ds, out / "NM_ossea"))

    # folha de laudo da estação (Secondary Capture colorida): vira imagem-chave sozinha
    series = {"uid": generate_uid(), "number": 99, "description": "ScreenCap"}
    ds = _base(SecondaryCaptureImageStorage, patient, study, series, "NM")
    ds.InstanceNumber = 1
    ds.ImageType = ["DERIVED", "SECONDARY"]
    ds.ConversionType = "WSD"
    h, w = 240, 320
    yy, xx = np.mgrid[0:h, 0:w]
    folha = np.full((h, w, 3), 245, np.uint8)
    folha[:28] = (30, 60, 110)                                    # tarja do cabeçalho
    for cx in (80, 240):                                          # duas miniaturas
        alvo = ((xx - cx) / 55.0) ** 2 + ((yy - 140) / 85.0) ** 2 < 1
        folha[alvo] = 60
    ds.SamplesPerPixel = 3
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0
    ds.Rows, ds.Columns = h, w
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = folha.tobytes()
    files.append(_save(ds, out / "NM_folha"))

    # renograma: fluxo (2 s) + dinâmico (30 s), num arquivo só
    study = {"uid": generate_uid(), "date": today.strftime("%Y%m%d"), "accession": "ACC5002",
             "description": "CINTILOGRAFIA RENAL DINÂMICA (DTPA)", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "Fluxo + dinâmico posterior"}
    ds = _base(NM_STORAGE, patient, study, series, "NM")
    ds.InstanceNumber = 1
    ds.ImageType = ["ORIGINAL", "PRIMARY", "DYNAMIC", "EMISSION"]
    _elem(ds, (0x0054, 0x1000), "CS", ["DYNAMIC", "IMAGE"])
    n_flow, n_dyn, size = 20, 20, 128
    _elem(ds, (0x0054, 0x0030), "US", [1] * n_flow + [2] * n_dyn)   # Phase Vector
    _elem(ds, (0x0054, 0x0031), "US", 2)                            # Number of Phases
    fases = []
    for dur, n in ((2000, n_flow), (30000, n_dyn)):
        it = Dataset()
        it.ActualFrameDuration = dur
        it.NumberOfFramesInPhase = n
        it.PhaseDelay = 0
        fases.append(it)
    _elem(ds, (0x0054, 0x0032), "SQ", Sequence(fases))
    _elem(ds, (0x0054, 0x0100), "US", list(range(1, n_flow + 1)) + list(range(1, n_dyn + 1)))
    _elem(ds, (0x0054, 0x0101), "US", max(n_flow, n_dyn))
    _elem(ds, (0x0054, 0x0020), "US", [1] * (n_flow + n_dyn))
    _elem(ds, (0x0054, 0x0021), "US", 1)
    _elem(ds, (0x0054, 0x0022), "SQ", Sequence([_view_code("posterior")]))
    ds.ActualFrameDuration = 2000
    ds.PixelSpacing = [4.4, 4.4]
    _radiopharm(ds, "Tc-99m DTPA", 1.85e8, tc99m)
    _nm_pixels(ds, _renal_phantom(n_flow, n_dyn, size))
    files.append(_save(ds, out / "NM_renal"))

    # DMSA: ANT/POST num arquivo + o par de seringas (padrão da dose), como no protocolo real
    study = {"uid": generate_uid(), "date": today.strftime("%Y%m%d"), "accession": "ACC5003",
             "description": "CINTILOGRAFIA RENAL ESTÁTICA (DMSA)", "for": generate_uid()}
    h, w = 128, 128
    series = {"uid": generate_uid(), "number": 1, "description": "ANT/POST"}
    ds = _base(NM_STORAGE, patient, study, series, "NM")
    ds.InstanceNumber = 1
    ds.ImageType = ["ORIGINAL", "PRIMARY", "STATIC", "EMISSION"]
    _elem(ds, (0x0054, 0x0020), "US", [1, 2])
    _elem(ds, (0x0054, 0x0021), "US", 2)
    _elem(ds, (0x0054, 0x0022), "SQ",
          Sequence([_view_code("anterior"), _view_code("posterior")]))
    ds.ActualFrameDuration = 300000
    ds.AcquisitionTime = "103000"
    ds.PixelSpacing = [2.2, 2.2]
    _radiopharm(ds, "Tc-99m DMSA", 1.1e8, tc99m, "090000")
    _nm_pixels(ds, np.stack([_dmsa_phantom(h, w, False), _dmsa_phantom(h, w, True)]))
    files.append(_save(ds, out / "NM_dmsa"))

    for nome, forca, hora, num in (("SERINGA CHEIA", 900.0, "090000", 2),
                                   ("SERINGA VAZIA", 90.0, "091000", 3)):
        series = {"uid": generate_uid(), "number": num, "description": nome}
        ds = _base(NM_STORAGE, patient, study, series, "NM")
        ds.InstanceNumber = 1
        ds.ImageType = ["ORIGINAL", "PRIMARY", "STATIC", "EMISSION"]
        ds.ActualFrameDuration = 60000
        ds.AcquisitionTime = hora
        ds.PixelSpacing = [2.2, 2.2]
        _radiopharm(ds, "Tc-99m DMSA", 1.1e8, tc99m, "090000")
        _nm_pixels(ds, _seringa(h, w, forca)[None, ...])
        files.append(_save(ds, out / "NM_dmsa"))
    return files


def tomo_geometry(ds, n: int, thickness_mm: float = 55.0, force_n: float = 80.0,
                  angle_deg: float = 0.0, side: str = "R", step_mm: float = 5.0) -> None:
    """Põe num fantoma de tomossíntese a geometria que o aparelho de verdade grava.

    É o que o indicador de profundidade lê: posição de cada corte (Per-Frame Functional
    Groups), espessura comprimida e força (X-Ray 3D Acquisition Sequence) e o ângulo do
    braço. Sem isso o fantoma tem pixels mas não tem onde o corte está.
    """
    import numpy as np
    from pydicom.dataset import Dataset

    a = np.radians(float(angle_deg))
    if angle_deg:                      # MLO: eixo de compressão inclinado, como no Pristina
        linha, coluna = np.array([0.0, 1.0, 0.0]), np.array([np.sin(a), 0.0, -np.cos(a)])
    else:                              # CC: compressão crânio-caudal
        linha, coluna = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    normal = np.cross(linha, coluna)
    passo = -normal if normal[2] < 0 else normal        # os cortes sobem: detector embaixo

    compartilhado = Dataset()
    ori = Dataset()
    ori.ImageOrientationPatient = [float(x) for x in np.concatenate([linha, coluna])]
    compartilhado.PlaneOrientationSequence = [ori]
    medidas = Dataset()
    medidas.SliceThickness = 10.0
    medidas.PixelSpacing = [0.1, 0.1]
    compartilhado.PixelMeasuresSequence = [medidas]
    anat = Dataset()
    anat.FrameLaterality = side
    compartilhado.FrameAnatomySequence = [anat]
    ds.SharedFunctionalGroupsSequence = [compartilhado]

    quadros = []
    base = np.array([-100.0, -50.0, 100.0])
    for k in range(n):
        fr = Dataset()
        pos = Dataset()
        pos.ImagePositionPatient = [float(x) for x in (base + passo * (k * step_mm))]
        fr.PlanePositionSequence = [pos]
        quadros.append(fr)
    ds.PerFrameFunctionalGroupsSequence = quadros

    aq = Dataset()
    aq.BodyPartThickness = float(thickness_mm)
    aq.CompressionForce = float(force_n)
    aq.PaddleDescription = "24x29 Standard Paddle"
    aq.PrimaryPositionerScanStartAngle = float(angle_deg)
    ds.XRay3DAcquisitionSequence = [aq]


def make_sample_data(out: Path) -> list[Path]:
    out = Path(out)
    files: list[Path] = []
    today = date.today()
    pat_a = {"name": "TESTE^Ana^Maria", "id": "FANT001", "birth": "19700315", "sex": "F"}
    pat_b = {"name": "FANTOMA^João", "id": "FANT002", "birth": "19581102", "sex": "M"}
    pat_c = {"name": "CINTILO^Pedro", "id": "FANT003", "birth": "19650720", "sex": "M"}

    # ---- TC tórax atual e anterior (mesmo paciente) -----------------------
    for years_ago, acc, shift in ((0, "ACC1001", 0.0), (1, "ACC0901", 0.05)):
        study = {"uid": generate_uid(), "date": (today - timedelta(days=365 * years_ago)).strftime("%Y%m%d"),
                 "accession": acc, "description": "TC TÓRAX", "for": generate_uid()}
        series = {"uid": generate_uid(), "number": 2, "description": "Axial 3mm"}
        n, size = 60, 256
        vol = _ct_volume(n, size, shift)
        for k in range(n):
            ds = _base(CTImageStorage, pat_a, study, series, "CT")
            ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
            ds.InstanceNumber = n - k        # propositalmente invertido: ordenação deve usar a geometria
            ds.ImagePositionPatient = [-192.0, -192.0, -90.0 + 3.0 * k]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.SliceLocation = -90.0 + 3.0 * k
            ds.SliceThickness = 3.0
            ds.PixelSpacing = [1.5, 1.5]
            ds.RescaleIntercept = -1024
            ds.RescaleSlope = 1
            ds.WindowCenter = -600
            ds.WindowWidth = 1500
            ds.KVP = 120
            _mono(ds, np.clip(vol[k] + 1024, 0, 4095), signed=False)
            files.append(_save(ds, out / f"CT_{acc}"))

    # ---- RM (2 séries: axial e sagital) -------------------------------------
    study = {"uid": generate_uid(), "date": today.strftime("%Y%m%d"),
             "accession": "ACC2001", "description": "RM MAMAS", "for": generate_uid()}
    size = 192
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    for num, desc, ori, npos in ((3, "T2 axial", [1, 0, 0, 0, 1, 0], 2),
                                 (5, "T1 sagital", [0, 1, 0, 0, 0, -1], 0)):
        series = {"uid": generate_uid(), "number": num, "description": desc}
        for k in range(24):
            ds = _base(MRImageStorage, pat_a, study, series, "MR")
            ds.InstanceNumber = k + 1
            pos = [-150.0, -150.0, 150.0]
            pos[npos] = -60.0 + 5.0 * k
            ds.ImagePositionPatient = pos
            ds.ImageOrientationPatient = ori
            ds.PixelSpacing = [1.5625, 1.5625]
            ds.SliceThickness = 5.0
            ds.RepetitionTime = 4000
            ds.EchoTime = 90
            img = 300 + 700 * np.exp(-(((xx - size / 2) / 60) ** 2 + ((yy - size / 2) / 45) ** 2))
            img += 400 * (((xx - 70 - k) ** 2 + (yy - 90) ** 2) < 64)
            _mono(ds, img, signed=False)
            files.append(_save(ds, out / f"MR_{desc.replace(' ', '_')}"))

    # ---- MG (4 incidências) ---------------------------------------------------
    study = {"uid": generate_uid(), "date": today.strftime("%Y%m%d"),
             "accession": "ACC3001", "description": "MAMOGRAFIA BILATERAL", "for": generate_uid()}
    h, w = 512, 400
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for num, (lat, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO")), 1):
        series = {"uid": generate_uid(), "number": num, "description": f"{lat} {view}"}
        ds = _base(DIGITAL_MG, pat_a, study, series, "MG")
        ds.InstanceNumber = 1
        ds.ImageLaterality = lat
        ds.ViewPosition = view
        ds.PatientOrientation = {"RCC": ["P", "L"], "LCC": ["A", "R"], "RMLO": ["P", "F"],
                                 "LMLO": ["A", "F"]}[lat + view]
        ds.ImagerPixelSpacing = [0.1, 0.1]
        ds.PresentationIntentType = "FOR PRESENTATION"
        # rótulo da incidência como o aparelho da GE grava (0045,101B): é por ele que o programa
        # distingue a incidência da variante (RMLO x RSMLO)
        _elem(ds, (0x0045, 0x101B), "LO", lat + view)
        ds.PresentationIntentType = "FOR PRESENTATION"
        # convenção de exibição: mama direita com parede torácica à direita da imagem
        cx = w if lat == "R" else 0
        breast = ((xx - cx) / (w * 0.95)) ** 2 + ((yy - h / 2) / (h * 0.45)) ** 2 < 1
        img = np.where(breast, 1800 + 600 * np.cos(yy / 25) * np.sin(xx / 30), 200)
        _mono(ds, img, signed=False)
        ds.WindowCenter = 2000
        ds.WindowWidth = 2500
        files.append(_save(ds, out / "MG"))

    # ---- US colorido (RGB) ---------------------------------------------------
    study = {"uid": generate_uid(), "date": (today - timedelta(days=30)).strftime("%Y%m%d"),
             "accession": "ACC4001", "description": "US ABDOME", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "Doppler"}
    ds = _base(UltrasoundImageStorage, pat_b, study, series, "US")
    ds.InstanceNumber = 1
    h, w = 300, 400
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.zeros((h, w, 3), np.uint8)
    gray = (80 + 60 * np.sin(xx / 12) * np.cos(yy / 9)).astype(np.uint8)
    rgb[..., 0] = rgb[..., 1] = rgb[..., 2] = gray
    vessel = ((xx - 200) ** 2 + (yy - 150) ** 2) < 900
    rgb[vessel] = [200, 30, 30]
    ds.SamplesPerPixel = 3
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0
    ds.Rows, ds.Columns = h, w
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = rgb.tobytes()
    # Regiões calibradas como o aparelho grava: a imagem 2D em centímetros e, embaixo, a janela
    # do Doppler espectral (tempo × velocidade). A segunda não mede distância — o fantoma tem de
    # ter as duas, senão não prova que o programa sabe recusar a errada.
    imagem = Dataset()
    imagem.RegionLocationMinX0, imagem.RegionLocationMinY0 = 20, 30
    imagem.RegionLocationMaxX1, imagem.RegionLocationMaxY1 = 380, 280
    imagem.PhysicalDeltaX = imagem.PhysicalDeltaY = 0.02          # cm/pixel → 0,2 mm
    imagem.PhysicalUnitsXDirection = imagem.PhysicalUnitsYDirection = 3   # 3 = cm
    imagem.RegionSpatialFormat, imagem.RegionDataType = 1, 1
    espectro = Dataset()
    espectro.RegionLocationMinX0, espectro.RegionLocationMinY0 = 20, 285
    espectro.RegionLocationMaxX1, espectro.RegionLocationMaxY1 = 380, 299
    espectro.PhysicalDeltaX, espectro.PhysicalDeltaY = 0.004, 0.5
    espectro.PhysicalUnitsXDirection, espectro.PhysicalUnitsYDirection = 4, 7   # s e cm/s
    espectro.RegionSpatialFormat, espectro.RegionDataType = 3, 4
    ds.SequenceOfUltrasoundRegions = [imagem, espectro]
    files.append(_save(ds, out / "US"))

    # ---- Multiframe (captura secundária com 10 quadros) ----------------------
    series = {"uid": generate_uid(), "number": 2, "description": "Cine multiframe"}
    ds = _base(SecondaryCaptureImageStorage, pat_b, study, series, "US")
    ds.InstanceNumber = 1
    ds.NumberOfFrames = 10
    frames = np.stack([(np.roll(gray, 8 * i, axis=1)).astype(np.uint8) for i in range(10)])
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows, ds.Columns = h, w
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = frames.tobytes()
    files.append(_save(ds, out / "US_cine"))

    # ---- medicina nuclear (corpo inteiro ósseo e renograma) ------------------
    files.extend(_make_nm(out, pat_c, today))
    return files
