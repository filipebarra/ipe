"""Imagens-chave (KO) e anotações (GSPS) em DICOM, para ir ao PACS e abrir em outro visualizador (0.99.41).

Pesquisa de visualizadores (Weasis, MedDream): no Ipê as imagens-chave e as medidas só existiam no banco
dele. Aqui:

- **KO** — Key Object Selection Document (TID 2010, título "Of Interest"): a lista das imagens-chave do
  exame, cada uma pela referência (SOP Class + SOP Instance + quadro). Quem recebe o exame (o PACS, o
  Weasis, o OHIF, outro Ipê) mostra as mesmas imagens marcadas.
- **GSPS** — Grayscale Softcopy Presentation State: as medidas, setas e textos desenhados, como gráficos
  (POLYLINE, ELLIPSE, POINT) e textos em coordenadas de pixel da imagem de origem, numa camada; o texto da
  medida (o número) vai junto, ancorado na ponta. Medida **rascunho** fica de fora.
- Leitura: os KO que chegam no exame (de outro sistema, ou o nosso de volta) viram imagens-chave aqui.

As coordenadas do Ipê já são as do DICOM (o canto de cima à esquerda do primeiro pixel é 0,0), sem conversão.

Sem Qt.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.imaging import measure as M

log = logging.getLogger(__name__)

KO_CLASS = "1.2.840.10008.5.1.4.1.1.88.59"
GSPS_CLASS = "1.2.840.10008.5.1.4.1.1.11.1"
DESC_KO = "Imagens-chave (Ipe)"
DESC_GSPS = "Anotações (Ipe)"
_COPY = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "StudyInstanceUID",
         "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription", "ReferringPhysicianName",
         "InstitutionName"]
#: medidas que não são desenho (vão por outros objetos: SEG, curva…) — ficam fora do GSPS
FORA_DO_GSPS = {"seg", "ponto3d", "spine"}
CHAVE_LIDOS = "ko.lidos"


def _code(v, s, m) -> Dataset:
    c = Dataset()
    c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = v, s, m
    return c


def _cabecalho(src, sop_class: str, modality: str, descricao: str, numero: int) -> Dataset:
    ds = Dataset()
    for kw in _COPY:
        if kw in src:
            setattr(ds, kw, src.data_element(kw).value)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    ds.SOPClassUID = sop_class
    ds.Modality = modality
    ds.SeriesInstanceUID, ds.SeriesNumber, ds.InstanceNumber = generate_uid(), numero, 1
    ds.SeriesDescription = descricao[:64]
    ds.Manufacturer = "Ipe"
    agora = datetime.now()
    ds.ContentDate, ds.ContentTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
    ds.SeriesDate, ds.SeriesTime = ds.ContentDate, ds.ContentTime
    return ds


def _referencias(repo, study_uid: str, chaves) -> dict:
    """(sop, quadro) -> {"series_uid", "sop_class", "frames", "path"}: o que é preciso para referenciar."""
    queremos = {sop for sop, _f in chaves}
    out = {}
    for s in repo.series_for_study(study_uid):
        for inst in repo.instances_for_series(s.series_uid):
            if inst["sop_uid"] not in queremos:
                continue
            try:
                ds = pydicom.dcmread(inst["path"], stop_before_pixels=True, force=True)
            except Exception as e:  # noqa: BLE001
                log.warning("referência %s: %s", inst["sop_uid"], e)
                continue
            out[inst["sop_uid"]] = {"series_uid": s.series_uid, "sop_class": str(ds.get("SOPClassUID", "")),
                                   "frames": int(ds.get("NumberOfFrames", 1) or 1), "path": inst["path"],
                                   "rows": int(ds.get("Rows", 0) or 0), "cols": int(ds.get("Columns", 0) or 0),
                                   "ds": ds}
    return out


def _evidencia(ds: Dataset, study_uid: str, refs: dict, usados) -> None:
    """CurrentRequestedProcedureEvidenceSequence (KO) — o que o objeto referencia, por série."""
    por_serie: dict = {}
    for sop in usados:
        r = refs[sop]
        por_serie.setdefault(r["series_uid"], []).append((r["sop_class"], sop))
    est = Dataset()
    est.StudyInstanceUID = study_uid
    series = []
    for suid, itens in por_serie.items():
        se = Dataset()
        se.SeriesInstanceUID = suid
        lst = []
        for cls, sop in dict.fromkeys(itens):
            it = Dataset()
            it.ReferencedSOPClassUID, it.ReferencedSOPInstanceUID = cls, sop
            lst.append(it)
        se.ReferencedSOPSequence = Sequence(lst)
        series.append(se)
    est.ReferencedSeriesSequence = Sequence(series)
    ds.CurrentRequestedProcedureEvidenceSequence = Sequence([est])


# ====================================================================== KO
def build_ko(repo, study_uid: str, descricao: str = "") -> Dataset | None:
    """O KO com as imagens-chave do exame (None se não há nenhuma)."""
    chaves = [(k["sop_uid"], int(k.get("frame_index") or 0)) for k in repo.key_images(study_uid)]
    if not chaves:
        return None
    refs = _referencias(repo, study_uid, chaves)
    chaves = [c for c in chaves if c[0] in refs]
    if not chaves:
        return None
    src = refs[chaves[0][0]]["ds"]
    ds = _cabecalho(src, KO_CLASS, "KO", DESC_KO, 998)
    ds.ValueType = "CONTAINER"
    ds.ContinuityOfContent = "SEPARATE"
    ds.ConceptNameCodeSequence = Sequence([_code("113000", "DCM", "Of Interest")])
    tpl = Dataset()
    tpl.MappingResource, tpl.TemplateIdentifier = "DCMR", "2010"
    ds.ContentTemplateSequence = Sequence([tpl])
    ds.ReferencedPerformedProcedureStepSequence = Sequence([])
    itens = []
    if descricao:
        t = Dataset()
        t.RelationshipType, t.ValueType = "CONTAINS", "TEXT"
        t.ConceptNameCodeSequence = Sequence([_code("113012", "DCM", "Key Object Description")])
        t.TextValue = descricao[:1024]
        itens.append(t)
    for sop, quadro in chaves:
        r = refs[sop]
        img = Dataset()
        img.RelationshipType, img.ValueType = "CONTAINS", "IMAGE"
        rs = Dataset()
        rs.ReferencedSOPClassUID, rs.ReferencedSOPInstanceUID = r["sop_class"], sop
        if r["frames"] > 1:
            rs.ReferencedFrameNumber = [quadro + 1]
        img.ReferencedSOPSequence = Sequence([rs])
        itens.append(img)
    ds.ContentSequence = Sequence(itens)
    _evidencia(ds, study_uid, refs, [s for s, _q in chaves])
    return ds


def ler_ko(ds) -> list[tuple[str, int]]:
    """(SOP, quadro) de cada imagem que o KO aponta."""
    out = []

    def andar(itens):
        for it in itens or []:
            if str(it.get("ValueType", "")) == "IMAGE":
                for r in it.get("ReferencedSOPSequence", []) or []:
                    fr = r.get("ReferencedFrameNumber")
                    if fr is not None and not isinstance(fr, int):
                        fr = list(fr)[0] if len(list(fr)) else None
                    out.append((str(r.ReferencedSOPInstanceUID), int(fr) - 1 if fr else 0))
            andar(it.get("ContentSequence"))
    andar(ds.get("ContentSequence"))
    return out


def marcar_kos_do_exame(repo, study_uid: str, settings=None) -> int:
    """Os KO do exame (de outro sistema, ou o nosso que voltou do PACS) viram imagens-chave aqui.
    Cada KO é lido uma vez só (lembrado em `ko.lidos`): desmarcar uma imagem depois não a traz de volta."""
    lidos = set(settings.get(CHAVE_LIDOS, []) or []) if settings is not None else set()
    marcadas = 0
    novos = []
    for s in repo.series_for_study(study_uid):
        if (s.modality or "").upper() != "KO":
            continue
        for inst in repo.instances_for_series(s.series_uid):
            if inst["sop_uid"] in lidos:
                continue
            try:
                ds = pydicom.dcmread(inst["path"], force=True)
            except Exception as e:  # noqa: BLE001
                log.warning("KO %s: %s", inst["path"], e)
                continue
            novos.append(inst["sop_uid"])
            alvos = ler_ko(ds)
            if not alvos:
                continue
            por_sop = {}
            for se in repo.series_for_study(study_uid):
                for i2 in repo.instances_for_series(se.series_uid):
                    por_sop[i2["sop_uid"]] = se.series_uid
            linhas = [(study_uid, por_sop[sop], sop, q) for sop, q in alvos if sop in por_sop]
            marcadas += _marcar(repo, linhas)
    if novos and settings is not None:
        settings.set(CHAVE_LIDOS, (sorted(lidos | set(novos)))[-5000:])
    return marcadas


def _marcar(repo, linhas) -> int:
    """Marca sem travar o exame (não foi escolha de quem está lendo), respeitando o quadro."""
    feitas = 0
    ja = {(k["sop_uid"], int(k.get("frame_index") or 0)) for k in repo.key_images(linhas[0][0])} if linhas else set()
    for study_uid, series_uid, sop, q in linhas:
        if (sop, q) in ja:
            continue
        if q == 0:
            feitas += repo.add_key_images([(study_uid, series_uid, sop)])
        else:
            repo.toggle_key_image(study_uid, series_uid, sop, q)
            feitas += 1
        ja.add((sop, q))
    return feitas


# ====================================================================== GSPS
def _graficos(kind: str, pts: list) -> list[tuple[str, list, bool]]:
    """[(GraphicType, pontos, preenchido)] de uma medida."""
    p = [(float(x), float(y)) for x, y in pts]
    if kind in ("ellipse", "tic") and len(p) >= 2:
        (x0, y0), (x1, y1) = p[0], p[1]
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
        return [("ELLIPSE", [(cx - rx, cy), (cx + rx, cy), (cx, cy - ry), (cx, cy + ry)], False)]
    if kind == "rect" and len(p) >= 2:
        (x0, y0), (x1, y1) = p[0], p[1]
        return [("POLYLINE", [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], False)]
    if kind == "polygon" and len(p) >= 3:
        return [("POLYLINE", p + p[:1], False)]
    if kind == "cobb" and len(p) >= 4:
        return [("POLYLINE", p[:2], False), ("POLYLINE", p[2:4], False)]
    if kind == "arrow" and len(p) >= 2:
        import math
        (ax, ay), (bx, by) = p[0], p[1]          # a ponta está no 1º ponto (como o Ipê desenha)
        ang = math.atan2(ay - by, ax - bx)
        tam = max(4.0, 0.15 * math.hypot(ax - bx, ay - by))
        asa1 = (ax - tam * math.cos(ang - 0.45), ay - tam * math.sin(ang - 0.45))
        asa2 = (ax - tam * math.cos(ang + 0.45), ay - tam * math.sin(ang + 0.45))
        return [("POLYLINE", [p[1], p[0]], False), ("POLYLINE", [asa1, p[0], asa2], False)]
    if kind == "probe" and p:
        return [("POINT", p[:1], False)]
    if kind == "text":
        return []
    if len(p) == 1:
        return [("POINT", p, False)]
    if len(p) >= 2:
        return [("POLYLINE", p, False)]
    return []


def escala(ann: "M.Annotation", ds, todas) -> tuple | None:
    """A escala da medida, na mesma ordem do quadro (`measure_spacing`): calibração desta imagem,
    calibração da série, região calibrada do ultrassom, PixelSpacing. `todas`: as medidas do exame."""
    cals = [a for a in reversed(list(todas)) if a.kind == "calibration" and M.calibration_spacing(a)]
    for a in cals:
        if a.frame_key == ann.frame_key:
            return M.calibration_spacing(a)
    for a in cals:
        if (a.meta or {}).get("escopo") != "imagem" and a.series_uid == ann.series_uid:
            return M.calibration_spacing(a)
    try:
        from ipe.imaging import us_regioes as US
        regs = US.regioes(ds)
        if regs:
            return US.espacamento_dos_pontos(regs, ann.points) if ann.points else US.espacamento(regs)
    except Exception:  # noqa: BLE001
        pass
    if "PixelSpacing" in ds:
        try:
            return tuple(float(v) for v in ds.PixelSpacing)
        except (TypeError, ValueError):
            return None
    return None


def _rotulo(ann: "M.Annotation", ref: dict, todas) -> str:
    """O número da medida, como aparece na tela, lido da imagem de origem com a escala certa."""
    try:
        ds = ref["ds"]
        sp = escala(ann, ds, todas)
        arr = None
        if ann.kind in M.ROI_KINDS or ann.kind == "probe":
            px = pydicom.dcmread(ref["path"], force=True)
            arr = px.pixel_array
            nfr = int(px.get("NumberOfFrames", 1) or 1)
            if arr.ndim == 3 and nfr > 1:
                arr = arr[min(ann.frame_key[1], nfr - 1)]
            if arr.ndim == 3:
                arr = None                     # colorido: sem estatística
            else:
                arr = arr.astype("float64") * float(px.get("RescaleSlope", 1) or 1) \
                    + float(px.get("RescaleIntercept", 0) or 0)
        return " · ".join(M.labels(ann, arr, sp, str(ds.get("Modality", ""))))
    except Exception as e:  # noqa: BLE001
        log.debug("rótulo do GSPS: %s", e)
        return ann.text


def build_gsps(repo, study_uid: str, incluir_rascunho: bool = False) -> tuple[Dataset | None, int]:
    """O GSPS com as medidas e anotações do exame. Devolve (dataset, nº de anotações)."""
    recs = [r for r in repo.annotations_for_studies([study_uid])
            if r.get("kind") not in FORA_DO_GSPS and (incluir_rascunho or not M.e_rascunho(r))]
    chaves = {(r["sop_uid"], int(r["frame_index"])) for r in recs if r.get("sop_uid")}
    if not chaves:
        return None, 0
    refs = _referencias(repo, study_uid, chaves)
    por_imagem: dict = {}
    for r in recs:
        if r.get("sop_uid") not in refs:
            continue
        por_imagem.setdefault((r["sop_uid"], int(r["frame_index"])), []).append(r)
    if not por_imagem:
        return None, 0
    todas = [M.Annotation.from_record(r) for r in repo.annotations_for_studies([study_uid])]
    src = refs[next(iter(por_imagem))[0]]["ds"]
    ds = _cabecalho(src, GSPS_CLASS, "PR", DESC_GSPS, 997)
    agora = datetime.now()
    ds.ContentLabel = "ANOTACOES"
    ds.ContentDescription = "Medidas e anotações (Ipe)"
    ds.ContentCreatorName = "Ipe"
    ds.PresentationCreationDate, ds.PresentationCreationTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
    camada = Dataset()
    camada.GraphicLayer = "IPE"
    camada.GraphicLayerOrder = 1
    camada.GraphicLayerDescription = "Medidas do Ipe"
    camada.GraphicLayerRecommendedDisplayGrayscaleValue = 0xFFFF
    camada.GraphicLayerRecommendedDisplayCIELabValue = [65535, 32896, 61695]   # amarelo
    ds.GraphicLayerSequence = Sequence([camada])
    ds.PresentationLUTShape = "IDENTITY"
    # séries referenciadas
    por_serie: dict = {}
    for (sop, q) in por_imagem:
        por_serie.setdefault(refs[sop]["series_uid"], []).append((sop, q))
    rss = []
    for suid, lst in por_serie.items():
        rs = Dataset()
        rs.SeriesInstanceUID = suid
        imgs = []
        for sop, q in lst:
            it = Dataset()
            it.ReferencedSOPClassUID, it.ReferencedSOPInstanceUID = refs[sop]["sop_class"], sop
            if refs[sop]["frames"] > 1:
                it.ReferencedFrameNumber = [q + 1]
            imgs.append(it)
        rs.ReferencedImageSequence = Sequence(imgs)
        rss.append(rs)
    ds.ReferencedSeriesSequence = Sequence(rss)
    areas, anots = [], []
    n = 0
    for (sop, q), lst in por_imagem.items():
        ref = refs[sop]
        ri = Dataset()
        ri.ReferencedSOPClassUID, ri.ReferencedSOPInstanceUID = ref["sop_class"], sop
        if ref["frames"] > 1:
            ri.ReferencedFrameNumber = [q + 1]
        da = Dataset()
        da.ReferencedImageSequence = Sequence([ri])
        da.PixelOriginInterpretation = "FRAME"
        da.DisplayedAreaTopLeftHandCorner = [1, 1]
        da.DisplayedAreaBottomRightHandCorner = [max(ref["cols"], 1), max(ref["rows"], 1)]
        da.PresentationSizeMode = "SCALE TO FIT"
        if "PixelSpacing" in ref["ds"]:
            da.PresentedPixelSpacing = list(ref["ds"].PixelSpacing)
        areas.append(da)
        ga = Dataset()
        ga.ReferencedImageSequence = Sequence([ri])
        ga.GraphicLayer = "IPE"
        gos, tos = [], []
        for r in lst:
            d = json.loads(r.get("data") or "{}")
            pts = [tuple(p) for p in d.get("points", [])]
            if not pts:
                continue
            kind, texto = r["kind"], d.get("text", "")
            for gt, gp, cheio in _graficos(kind, pts):
                go = Dataset()
                go.GraphicAnnotationUnits = "PIXEL"
                go.GraphicDimensions = 2
                go.NumberOfGraphicPoints = len(gp)
                go.GraphicData = [round(v, 3) for xy in gp for v in xy]
                go.GraphicType = gt
                go.GraphicFilled = "Y" if cheio else "N"
                gos.append(go)
            rot = texto if kind in ("text", "arrow") else _rotulo(M.Annotation.from_record(r), ref, todas)
            if rot:
                to = Dataset()
                to.UnformattedTextValue = rot[:1024]
                ax, ay = (max(p[0] for p in pts), min(p[1] for p in pts)) if kind != "text" else pts[0]
                to.AnchorPointAnnotationUnits = "PIXEL"
                to.AnchorPoint = [round(float(ax), 3), round(float(ay), 3)]
                to.AnchorPointVisibility = "N"
                tos.append(to)
            n += 1
        if gos:
            ga.GraphicObjectSequence = Sequence(gos)
        if tos:
            ga.TextObjectSequence = Sequence(tos)
        if gos or tos:
            anots.append(ga)
    if not n:
        return None, 0
    ds.DisplayedAreaSelectionSequence = Sequence(areas)
    ds.GraphicAnnotationSequence = Sequence(anots)
    return ds, n


# ====================================================================== gravar no exame
def gravar_no_exame(repo, storage_root, *datasets) -> list[str]:
    """Importa os objetos no exame (e manda ao servidor central, se for cliente). Devolve as séries novas."""
    import shutil
    import tempfile
    from pathlib import Path
    from ipe.importer.scanner import Importer
    dss = [d for d in datasets if d is not None]
    if not dss:
        return []
    tmp = Path(tempfile.mkdtemp(prefix="ipe_ko_"))
    try:
        for i, d in enumerate(dss):
            d.save_as(tmp / f"obj{i}.dcm", enforce_file_format=True)
        Importer(repo.db, Path(storage_root)).import_paths([tmp])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        from ipe.central.client_repo import upload_if_client
        upload_if_client(repo, str(dss[0].StudyInstanceUID))
    except Exception:  # noqa: BLE001
        log.exception("KO/GSPS: enviar ao servidor")
    return [str(d.SeriesInstanceUID) for d in dss]
