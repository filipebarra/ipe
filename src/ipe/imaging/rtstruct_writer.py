"""Grava estruturas (imaging.estruturas) como DICOM RTSTRUCT — contornos fechados corte a corte (0.99.40).

É a língua da radioterapia: o sistema de planejamento lê os contornos direto. Cada corte da grade vira
um ou mais polígonos fechados (CLOSED_PLANAR) que seguem a **borda dos pixels** (não o centro): ao
preencher o polígono pelos centros dos pixels, como os planejadores fazem, a máscara sai idêntica.
Buracos (anel, necrose central) viram um segundo contorno dentro do primeiro — a convenção é o
"par-ímpar" (o que está dentro de dois contornos está fora), que é como o Ipê também lê.

Sem Qt.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

RTSTRUCT_CLASS = "1.2.840.10008.5.1.4.1.1.481.3"
_COPY = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "StudyInstanceUID",
         "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription", "ReferringPhysicianName",
         "InstitutionName"]
#: tipo da estrutura → RTROIInterpretedType
INTERPRETACAO = {"lesão": "GTV", "órgão": "ORGAN", "outro": "CONTROL"}


def contornos_do_corte(m: np.ndarray) -> list[np.ndarray]:
    """Polígonos fechados (N × 2, em coordenadas de pixel (coluna, linha), nos cantos dos pixels) que
    contornam a máscara 2D — um por borda (externas no sentido horário da tela, buracos no outro)."""
    m = np.asarray(m, bool)
    if not m.any():
        return []
    h, w = m.shape
    p = np.pad(m, 1)
    # arestas orientadas com o pixel marcado à direita de quem anda (cantos em (x, y) da grade de cantos)
    prox: dict = {}

    def add(a, b):
        prox.setdefault(a, []).append(b)
    ys, xs = np.nonzero(m)
    for y, x in zip(ys.tolist(), xs.tolist()):
        py, px = y + 1, x + 1
        if not p[py - 1, px]:                  # vizinho de cima vazio: aresta de cima, para a direita
            add((x, y), (x + 1, y))
        if not p[py, px + 1]:                  # direita: para baixo
            add((x + 1, y), (x + 1, y + 1))
        if not p[py + 1, px]:                  # baixo: para a esquerda
            add((x + 1, y + 1), (x, y + 1))
        if not p[py, px - 1]:                  # esquerda: para cima
            add((x, y + 1), (x, y))
    usados = set()
    polis = []
    for ini in list(prox):
        for alvo in list(prox[ini]):
            if (ini, alvo) in usados:
                continue
            caminho = [ini]
            a, b = ini, alvo
            while True:
                usados.add((a, b))
                caminho.append(b)
                if b == ini:
                    break
                saidas = [c for c in prox.get(b, []) if (b, c) not in usados]
                if not saidas:
                    break
                if len(saidas) > 1:
                    # cruzamento em diagonal: vira para a direita (separa os dois pixels que se tocam no canto)
                    d = (b[0] - a[0], b[1] - a[1])
                    direita = (-d[1], d[0])
                    saidas.sort(key=lambda c: 0 if (c[0] - b[0], c[1] - b[1]) == direita else 1)
                a, b = b, saidas[0]
            if len(caminho) >= 4 and caminho[-1] == caminho[0]:
                polis.append(_simplificar(np.array(caminho[:-1], float)))
    return polis


def _simplificar(pts: np.ndarray) -> np.ndarray:
    """Tira os pontos no meio de uma reta (sobram só os cantos da escada)."""
    if len(pts) < 4:
        return pts
    ant, prox = np.roll(pts, 1, axis=0), np.roll(pts, -1, axis=0)
    a, b = pts - ant, prox - pts
    canto = (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) != 0
    return pts[canto]


def build_rtstruct(vol, estruturas: list, src_path: str, frames=None, descricao: str = "Estruturas (Ipe)",
                   rotulo: str = "IPE") -> Dataset:
    """`estruturas`: lista de `Estrutura` (imaging.estruturas) na grade do `vol`."""
    src = pydicom.dcmread(src_path, stop_before_pixels=True, force=True)
    ds = Dataset()
    for kw in _COPY:
        if kw in src:
            setattr(ds, kw, src.data_element(kw).value)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = RTSTRUCT_CLASS
    sop = generate_uid()
    meta.MediaStorageSOPInstanceUID = sop
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    agora = datetime.now()
    ds.SOPClassUID, ds.SOPInstanceUID = RTSTRUCT_CLASS, sop
    ds.Modality = "RTSTRUCT"
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber, ds.InstanceNumber = 985, 1
    ds.SeriesDescription = descricao[:64]
    ds.Manufacturer, ds.ManufacturerModelName, ds.SoftwareVersions = "Ipe", "Ipe", "1"
    ds.StructureSetLabel = rotulo[:16]
    ds.StructureSetName = descricao[:64]
    ds.StructureSetDate, ds.StructureSetTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
    ds.SeriesDate, ds.SeriesTime = ds.StructureSetDate, ds.StructureSetTime
    ds.ContentDate, ds.ContentTime = ds.StructureSetDate, ds.StructureSetTime
    ds.ApprovalStatus = "UNAPPROVED"
    for_uid = str(src.get("FrameOfReferenceUID", "") or generate_uid())
    src_class = str(src.get("SOPClassUID", ""))
    # o corte k da grade -> a imagem de origem (pela posição)
    normal = np.cross(vol.row_dir, vol.col_dir)
    por_pos = [(float(np.asarray(f.position, float) @ normal), f) for f in (frames or []) if f.position is not None]

    def imagem_do_corte(k):
        z = float(vol.voxel_to_patient(0, 0, k) @ normal)
        melhor = min(por_pos, key=lambda t: abs(t[0] - z), default=None)
        if melhor is None or abs(melhor[0] - z) > max(vol.dz * 0.5, 0.2):
            return None
        return melhor[1]

    usadas: dict = {}
    roi_set, roi_cont, obs = [], [], []
    for n, e in enumerate([e for e in estruturas if not e.vazia()], 1):
        r = Dataset()
        r.ROINumber = n
        r.ReferencedFrameOfReferenceUID = for_uid
        r.ROIName = e.nome[:64]
        r.ROIGenerationAlgorithm = "MANUAL" if e.fonte in ("manual", "combinação") else "SEMIAUTOMATIC"
        roi_set.append(r)
        o = Dataset()
        o.ObservationNumber = n
        o.ReferencedROINumber = n
        o.RTROIInterpretedType = INTERPRETACAO.get(e.tipo, "CONTROL")
        o.ROIInterpreter = ""
        obs.append(o)
        rc = Dataset()
        rc.ReferencedROINumber = n
        rc.ROIDisplayColor = [int(c) for c in e.cor[:3]]
        conts = []
        k0, j0, i0 = e.offset
        for dk in range(e.mascara.shape[0]):
            sl = e.mascara[dk]
            if not sl.any():
                continue
            k = k0 + dk
            f = imagem_do_corte(k)
            for poli in contornos_do_corte(sl):
                # canto de pixel (x, y) do recorte -> índice contínuo (centro do pixel = inteiro)
                ii = poli[:, 0] + i0 - 0.5
                jj = poli[:, 1] + j0 - 0.5
                pts = np.array([vol.voxel_to_patient(a, b, k) for a, b in zip(ii, jj)])
                c = Dataset()
                c.ContourGeometricType = "CLOSED_PLANAR"
                c.NumberOfContourPoints = len(pts)
                c.ContourData = [f"{v:.3f}" for v in pts.ravel()]
                if f is not None:
                    ci = Dataset()
                    ci.ReferencedSOPClassUID = src_class
                    ci.ReferencedSOPInstanceUID = f.sop_uid
                    c.ContourImageSequence = Sequence([ci])
                    usadas[f.sop_uid] = src_class
                conts.append(c)
        rc.ContourSequence = Sequence(conts)
        roi_cont.append(rc)
    fr = Dataset()
    fr.FrameOfReferenceUID = for_uid
    est = Dataset()
    est.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"        # Detached Study Management (o de praxe)
    est.ReferencedSOPInstanceUID = str(src.get("StudyInstanceUID", ""))
    ser = Dataset()
    ser.SeriesInstanceUID = str(src.get("SeriesInstanceUID", ""))
    imgs = []
    for uid, cls in usadas.items():
        it = Dataset()
        it.ReferencedSOPClassUID, it.ReferencedSOPInstanceUID = cls, uid
        imgs.append(it)
    ser.ContourImageSequence = Sequence(imgs)
    est.RTReferencedSeriesSequence = Sequence([ser])
    fr.RTReferencedStudySequence = Sequence([est])
    ds.ReferencedFrameOfReferenceSequence = Sequence([fr])
    ds.StructureSetROISequence = Sequence(roi_set)
    ds.ROIContourSequence = Sequence(roi_cont)
    ds.RTROIObservationsSequence = Sequence(obs)
    return ds
