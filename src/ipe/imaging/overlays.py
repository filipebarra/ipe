"""Objetos DICOM que desenham sobre as imagens: resultados de CAD/IA e anotações de outros programas.

- SR (inclusive Mammography CAD SR e resultados de IA em TID 1500): SCOORD (2D, ligado a uma
  imagem) e SCOORD3D (em mm); o rótulo vem do tipo de achado e da certeza, quando houver.
- SEG (segmentação DICOM): máscaras por quadro, com a cor e o nome de cada segmento.
- RTSTRUCT: contornos em mm (ROIs de radioterapia / contornos de IA).
- GSPS (Grayscale Softcopy Presentation State): textos e desenhos de outro visualizador.

Nada aqui depende de Qt; o viewport só desenha o que estes objetos devolvem para o quadro atual.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
import pydicom

from ipe import FABRICANTES_NOSSOS

log = logging.getLogger(__name__)

SR_CLASSES_CAD = {"1.2.840.10008.5.1.4.1.1.88.50": "CAD de mamografia",
                  "1.2.840.10008.5.1.4.1.1.88.65": "CAD de tórax",
                  "1.2.840.10008.5.1.4.1.1.88.69": "CAD de colonografia"}
SEG_CLASS = "1.2.840.10008.5.1.4.1.1.66.4"
RTSTRUCT_CLASS = "1.2.840.10008.5.1.4.1.1.481.3"
GSPS_CLASSES = {"1.2.840.10008.5.1.4.1.1.11.1", "1.2.840.10008.5.1.4.1.1.11.2",
                "1.2.840.10008.5.1.4.1.1.11.3", "1.2.840.10008.5.1.4.1.1.11.4"}
PALETTE = [(255, 80, 80), (80, 200, 255), (120, 230, 90), (255, 200, 60), (220, 120, 255),
           (255, 140, 40), (60, 220, 200), (255, 110, 190)]
OVERLAY_MODALITIES = {"SR", "SEG", "RTSTRUCT", "PR"}

# Tipos que o médico liga e desliga, e que o programa lembra de um exame para o outro.
# A chave é o `source` do objeto; a IA de fora escreve SEG, GSPS ou SR.
TIPOS = {"SEG": "Segmentações (SEG)", "GSPS": "Anotações de outro sistema (GSPS)",
         "SR": "Achados de CAD/IA (SR)", "RTSTRUCT": "Contornos de radioterapia (RTSTRUCT)",
         "CAD": "Achados de CAD/IA"}
CHAVE_OCULTOS = "viewer.cad_ia_oculto"


def tipos_ocultos(settings) -> set:
    """Tipos que o médico mandou começar oculto (vale para os próximos exames)."""
    if settings is None:
        return set()
    v = settings.get(CHAVE_OCULTOS, []) or []
    return {str(x) for x in v} if isinstance(v, (list, tuple, set)) else set()


def guardar_tipos_ocultos(settings, tipos) -> None:
    """Guarda em disco na hora: desligar o overlay da IA é escolha para valer, não para a sessão."""
    if settings is None:
        return
    settings.set(CHAVE_OCULTOS, sorted(str(t) for t in tipos))
    try:
        settings.save()
    except OSError as e:
        log.warning("não gravei a escolha de CAD/IA: %s", e)


@dataclass
class Graphic:
    kind: str                                  # polyline, polygon, point, text
    points: list = field(default_factory=list)   # (x, y) em pixels da imagem (coluna, linha)
    text: str = ""
    points3d: np.ndarray | None = None         # (N, 3) mm, para contornos 3D
    color: tuple | None = None


@dataclass
class MaskFrame:
    mask: np.ndarray                           # bool (linhas, colunas)
    color: tuple
    label: str
    position: np.ndarray | None = None         # posição do pixel (0,0) em mm
    orientation: np.ndarray | None = None      # 6 valores
    spacing: tuple | None = None               # (linha, coluna) mm
    ref: tuple | None = None                   # (SOP, quadro) da imagem de origem
    #: (linhas, colunas) da imagem de origem, quando a máscara está numa **grade menor** que ela.
    #: Sem isso, uma máscara medida em resolução reduzida sai desenhada do tamanho da própria
    #: grade, encolhida e encostada no canto de cima — foi o que aconteceu com a densidade (0.39.1).
    alvo: tuple | None = None


@dataclass
class MaskVolume:
    """Máscara 3D em milímetros: aparece em **qualquer** plano de **qualquer** série do exame.

    Pedido dele (10/10/2026): *"replique a segmentação em TODAS as sequências"*. A `MaskFrame`
    só se desenha numa imagem paralela à da aquisição (e a 0,5 corte dela); numa reconstrução
    coronal de um sagital, ou na sequência T2 em outro plano, a lesão simplesmente não aparecia.
    Aqui a máscara guarda a própria grade (canto e passos em mm) e cada quadro pergunta, pixel a
    pixel, se aquele ponto do paciente cai num voxel da lesão (`fatia`).
    """
    mascara: np.ndarray                        # bool (k, j, i) — o recorte da lesão
    origem: np.ndarray                         # mm do voxel (0, 0, 0) do recorte
    matriz: np.ndarray                         # 3x3: colunas = passo em i, j, k (mm)
    color: tuple
    label: str = ""

    def __post_init__(self) -> None:
        self.mascara = np.asarray(self.mascara, bool)
        self.origem = np.asarray(self.origem, float)
        self.matriz = np.asarray(self.matriz, float).reshape(3, 3)
        self._inv = np.linalg.inv(self.matriz)
        self._cache: dict = {}

    @classmethod
    def do_volume(cls, vol, mascara, offset, color, label: str = "") -> "MaskVolume":
        k0, j0, i0 = (int(v) for v in offset)
        return cls(mascara, vol.voxel_to_patient(i0, j0, k0), vol.matrix(), tuple(color), label)

    # -------------------------------------------------------------- guardar na medida
    def para_meta(self) -> dict:
        import base64
        import zlib
        bits = np.packbits(self.mascara.ravel())
        return {"forma": list(self.mascara.shape), "origem": [round(float(x), 4) for x in self.origem],
                "matriz": [round(float(x), 6) for x in self.matriz.ravel()],
                "bits": base64.b64encode(zlib.compress(bits.tobytes(), 9)).decode("ascii")}

    @classmethod
    def da_meta(cls, d: dict, color, label: str = "") -> "MaskVolume":
        import base64
        import zlib
        forma = tuple(int(x) for x in d["forma"])
        bits = np.frombuffer(zlib.decompress(base64.b64decode(d["bits"])), np.uint8)
        m = np.unpackbits(bits)[: int(np.prod(forma))].reshape(forma).astype(bool)
        return cls(m, d["origem"], d["matriz"], tuple(color), label)

    def contem(self, p, folga: int = 0) -> bool:
        """O ponto do paciente (mm) cai num voxel da máscara (com `folga` voxels em volta)?"""
        ijk = np.rint(self._inv @ (np.asarray(p, float) - self.origem)).astype(int)
        nz, ny, nx = self.mascara.shape
        i, j, k = int(ijk[0]), int(ijk[1]), int(ijk[2])
        k0, k1 = max(k - folga, 0), min(k + folga + 1, nz)
        j0, j1 = max(j - folga, 0), min(j + folga + 1, ny)
        i0, i1 = max(i - folga, 0), min(i + folga + 1, nx)
        if k0 >= k1 or j0 >= j1 or i0 >= i1:
            return False
        return bool(self.mascara[k0:k1, j0:j1, i0:i1].any())

    # -------------------------------------------------------------- corte por um plano
    def cantos(self) -> np.ndarray:
        nz, ny, nx = self.mascara.shape
        c = np.array([[i, j, k] for i in (-0.5, nx - 0.5) for j in (-0.5, ny - 0.5)
                      for k in (-0.5, nz - 0.5)], float)
        return self.origem + c @ self.matriz.T

    def fatia(self, pos, row, col, normal, spacing, forma) -> tuple | None:
        """(x0, y0, máscara 2D) da lesão no plano do quadro, ou None se o plano não a corta.

        `pos` é o centro do pixel (0, 0); x0/y0 são o índice do primeiro pixel da máscara 2D.
        Cada pixel olha o voxel mais próximo do ponto do paciente onde ele está — numa
        aquisição de 3 mm o reconstruído sai em degraus, que é o que a aquisição tem."""
        pos, row, col, normal = (np.asarray(v, float) for v in (pos, row, col, normal))
        rs, cs = (float(x) for x in spacing)
        h, w = (int(x) for x in forma[:2])
        chave = (tuple(np.round(pos, 3)), tuple(np.round(row, 4)), tuple(np.round(col, 4)),
                 round(rs, 4), round(cs, 4), h, w)
        if chave in self._cache:
            return self._cache[chave]
        res = self._fatia(pos, row, col, normal, rs, cs, h, w)
        if len(self._cache) > 400:
            self._cache.clear()
        self._cache[chave] = res
        return res

    def _fatia(self, pos, row, col, normal, rs, cs, h, w):
        cant = self.cantos()
        d = (cant - pos) @ normal
        if d.min() > 0 or d.max() < 0:
            return None
        u = (cant - pos) @ row / cs
        v = (cant - pos) @ col / rs
        x0, x1 = max(0, int(np.floor(u.min()))), min(w - 1, int(np.ceil(u.max())))
        y0, y1 = max(0, int(np.floor(v.min()))), min(h - 1, int(np.ceil(v.max())))
        if x0 > x1 or y0 > y1:
            return None
        xs = np.arange(x0, x1 + 1, dtype=float)
        ys = np.arange(y0, y1 + 1, dtype=float)
        pts = (pos[None, None, :] + ys[:, None, None] * rs * col[None, None, :]
               + xs[None, :, None] * cs * row[None, None, :])
        ijk = np.rint((pts - self.origem) @ self._inv.T).astype(np.int64)
        nz, ny, nx = self.mascara.shape
        dentro = ((ijk[..., 0] >= 0) & (ijk[..., 0] < nx) & (ijk[..., 1] >= 0) & (ijk[..., 1] < ny)
                  & (ijk[..., 2] >= 0) & (ijk[..., 2] < nz))
        m = np.zeros(dentro.shape, bool)
        ii, jj, kk = ijk[..., 0][dentro], ijk[..., 1][dentro], ijk[..., 2][dentro]
        m[dentro] = self.mascara[kk, jj, ii]
        if not m.any():
            return None
        return x0, y0, MaskFrame(m, self.color, self.label)


@dataclass
class OverlayObject:
    key: str                                   # SOPInstanceUID do objeto
    source: str                                # "CAD", "SR", "SEG", "RTSTRUCT", "GSPS", "Segmentação"
    label: str
    color: tuple = (255, 170, 60)
    enabled: bool = True
    study_uid: str = ""
    by_frame: dict = field(default_factory=dict)      # (SOP, quadro) -> [Graphic]; quadro -1 = todos
    all_frames: list = field(default_factory=list)    # Graphic para qualquer imagem (GSPS sem referência)
    planar: list = field(default_factory=list)        # Graphic com points3d
    masks: list = field(default_factory=list)         # MaskFrame
    volumes: list = field(default_factory=list)       # MaskVolume (segmentação 3D, em mm)
    findings: list = field(default_factory=list)      # textos dos achados (lista no menu / laudo)
    stats: dict = field(default_factory=dict)         # volume, SUV… (segmentação feita aqui)
    version: int = 0

    def graphics_for(self, sop: str, frame: int) -> list[Graphic]:
        return self.by_frame.get((sop, frame), []) + self.by_frame.get((sop, -1), []) + self.all_frames

    @property
    def title(self) -> str:
        n = len(self.findings)
        return f"{self.source}: {self.label}" + (f" ({n} achado{'s' if n != 1 else ''})" if n else "")


# ------------------------------------------------------------------ cores
def lab_to_rgb(v) -> tuple:
    """CIELab da DICOM (0–65535) -> RGB 0–255."""
    try:
        L = float(v[0]) / 65535 * 100
        a = float(v[1]) / 65535 * 255 - 128
        b = float(v[2]) / 65535 * 255 - 128
    except (TypeError, IndexError, ValueError):
        return PALETTE[0]
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def f(t):
        return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787
    X, Y, Z = 0.95047 * f(fx), 1.0 * f(fy), 1.08883 * f(fz)
    r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
    g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
    bb = 0.0557 * X - 0.2040 * Y + 1.0570 * Z

    def gam(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return tuple(int(round(gam(c) * 255)) for c in (r, g, bb))


# ------------------------------------------------------------------ geometria
def _ellipse_points(cx, cy, ax, ay, bx, by, n: int = 48) -> list:
    """Elipse com semieixos (ax, ay) e (bx, by) em volta do centro."""
    return [(cx + ax * math.cos(t) + bx * math.sin(t), cy + ay * math.cos(t) + by * math.sin(t))
            for t in np.linspace(0, 2 * math.pi, n, endpoint=False)]


def graphic_2d(gtype: str, data, text: str = "") -> Graphic | None:
    """Converte GraphicType/GraphicData (SR ou GSPS) em pontos (coluna, linha) da imagem."""
    try:
        vals = [float(v) for v in data]
    except (TypeError, ValueError):
        return None
    pts = list(zip(vals[0::2], vals[1::2]))
    if not pts:
        return None
    g = (gtype or "").upper()
    if g == "POINT" or g == "MULTIPOINT":
        return Graphic("point", pts, text)
    if g == "CIRCLE" and len(pts) >= 2:
        (cx, cy), (px, py) = pts[:2]
        r = math.hypot(px - cx, py - cy)
        return Graphic("polygon", _ellipse_points(cx, cy, r, 0, 0, r), text)
    if g == "ELLIPSE" and len(pts) >= 4:
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = pts[:4]
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        return Graphic("polygon", _ellipse_points(cx, cy, (x2 - x1) / 2, (y2 - y1) / 2,
                                                  (x4 - x3) / 2, (y4 - y3) / 2), text)
    if g in ("POLYGON",) or (g in ("POLYLINE", "INTERPOLATED") and len(pts) > 2 and pts[0] == pts[-1]):
        return Graphic("polygon", pts, text)
    return Graphic("polyline", pts, text)


# ------------------------------------------------------------------ SR
def _meaning(item, attr: str = "ConceptNameCodeSequence") -> str:
    seq = item.get(attr)
    if seq:
        return str(seq[0].get("CodeMeaning", "") or "")
    return ""


def _num_text(item) -> str:
    try:
        mv = item.MeasuredValueSequence[0]
        v = float(mv.NumericValue)
        unit = _meaning(mv, "MeasurementUnitsCodeSequence")
        unit = "" if unit in ("no units", "unity", "{ratio}") else f" {unit}"
        return f"{v:g}{unit}"
    except Exception:  # noqa: BLE001
        return ""


def _image_refs(item) -> list[tuple[str, int]]:
    refs = []
    for ch in item.get("ContentSequence", []) or []:
        if str(ch.get("ValueType", "")) == "IMAGE":
            for r in ch.get("ReferencedSOPSequence", []) or []:
                sop = str(r.get("ReferencedSOPInstanceUID", ""))
                frames = r.get("ReferencedFrameNumber")
                if frames:
                    fl = frames if isinstance(frames, (list, pydicom.multival.MultiValue)) else [frames]
                    refs += [(sop, int(f) - 1) for f in fl]
                else:
                    refs.append((sop, -1))
    return refs


def parse_sr(ds) -> OverlayObject:
    cls = str(ds.get("SOPClassUID", ""))
    ours = str(ds.get("Manufacturer", "")) in FABRICANTES_NOSSOS
    title = _meaning(ds) or str(ds.get("SeriesDescription", "")) or "Relatório estruturado"
    src = "CAD" if cls in SR_CLASSES_CAD else "SR"
    obj = OverlayObject(str(ds.get("SOPInstanceUID", "")), src, title, (255, 170, 60) if src == "CAD" else (120, 200, 255),
                        enabled=not ours, study_uid=str(ds.get("StudyInstanceUID", "")))

    def walk(items, context: str) -> None:
        # rótulo do grupo: tipo do achado (CODE) + certeza/probabilidade (NUM)
        codes, nums = [], []
        for it in items:
            vt = str(it.get("ValueType", ""))
            name = _meaning(it)
            if vt == "CODE":
                val = _meaning(it, "ConceptCodeSequence")
                if val and any(k in name.lower() for k in ("type", "finding", "tipo", "achado", "category",
                                                              "classification", "birads", "bi-rads")):
                    codes.append(val)
            elif vt == "NUM" and any(k in name.lower() for k in ("certainty", "probability", "score",
                                                                   "likelihood", "suspicion")):
                t = _num_text(it)
                if t:
                    nums.append(f"{name.split(' of ')[0]} {t}" if len(name) < 30 else t)
            elif vt == "NUM" and not nums:
                t = _num_text(it)
                if t and name:
                    nums.append(f"{name}: {t}")
        label = " · ".join(codes + nums[:2]) or context
        for it in items:
            vt = str(it.get("ValueType", ""))
            if vt == "SCOORD":
                g = graphic_2d(str(it.get("GraphicType", "")), it.get("GraphicData", []), label)
                if g is None:
                    continue
                for sop, fr in _image_refs(it) or []:
                    obj.by_frame.setdefault((sop, fr), []).append(g)
            elif vt == "SCOORD3D":
                try:
                    vals = np.array([float(v) for v in it.get("GraphicData", [])], dtype=float).reshape(-1, 3)
                except ValueError:
                    continue
                gt = str(it.get("GraphicType", "")).upper()
                kind = "point" if gt in ("POINT", "MULTIPOINT") else "polygon" if gt in ("POLYGON", "ELLIPSE") else "polyline"
                obj.planar.append(Graphic(kind, [], label, vals))
            sub = it.get("ContentSequence")
            if sub and vt in ("CONTAINER", "CODE", "NUM", "TEXT"):
                inner = _meaning(it) if vt == "CONTAINER" else label
                walk(sub, inner or label)
        if codes or (nums and any(str(i.get("ValueType", "")).startswith("SCOORD") or i.get("ContentSequence")
                                  for i in items)):
            if label and label not in obj.findings:
                obj.findings.append(label)

    walk(ds.get("ContentSequence", []) or [], title)
    return obj


# ------------------------------------------------------------------ GSPS
def parse_gsps(ds) -> OverlayObject:
    obj = OverlayObject(str(ds.get("SOPInstanceUID", "")), "GSPS",
                        str(ds.get("ContentLabel", "") or ds.get("ContentDescription", "") or "Anotações"),
                        (255, 230, 80), study_uid=str(ds.get("StudyInstanceUID", "")))
    series_refs = []
    for rs in ds.get("ReferencedSeriesSequence", []) or []:
        for ri in rs.get("ReferencedImageSequence", []) or []:
            series_refs.append(str(ri.get("ReferencedSOPInstanceUID", "")))
    for ga in ds.get("GraphicAnnotationSequence", []) or []:
        refs = []
        for ri in ga.get("ReferencedImageSequence", []) or []:
            sop = str(ri.get("ReferencedSOPInstanceUID", ""))
            fr = ri.get("ReferencedFrameNumber")
            refs.append((sop, int(fr[0] if isinstance(fr, (list, pydicom.multival.MultiValue)) else fr) - 1)
                        if fr else (sop, -1))
        if not refs:
            refs = [(s, -1) for s in series_refs]
        graphics = []
        for go in ga.get("GraphicObjectSequence", []) or []:
            g = graphic_2d(str(go.get("GraphicType", "")), go.get("GraphicData", []))
            if g is not None:
                if str(go.get("GraphicAnnotationUnits", "PIXEL")).upper() == "DISPLAY":
                    g.text = "__display__"
                graphics.append(g)
        for to in ga.get("TextObjectSequence", []) or []:
            txt = str(to.get("UnformattedTextValue", ""))
            pt = to.get("AnchorPoint") or to.get("BoundingBoxTopLeftHandCorner")
            if not txt or not pt:
                continue
            g = Graphic("text", [(float(pt[0]), float(pt[1]))], txt)
            units = to.get("AnchorPointAnnotationUnits") or to.get("BoundingBoxAnnotationUnits") or "PIXEL"
            if str(units).upper() == "DISPLAY":
                g.color = (-1, -1, -1)        # marca: coordenadas relativas à tela
            graphics.append(g)
            obj.findings.append(txt)
        for sop, fr in refs:
            obj.by_frame.setdefault((sop, fr), []).extend(graphics)
    return obj


# ------------------------------------------------------------------ RTSTRUCT
def parse_rtstruct(ds) -> OverlayObject:
    obj = OverlayObject(str(ds.get("SOPInstanceUID", "")), "RTSTRUCT",
                        str(ds.get("StructureSetLabel", "") or ds.get("SeriesDescription", "") or "Contornos"),
                        (80, 220, 120), study_uid=str(ds.get("StudyInstanceUID", "")))
    names = {int(r.ROINumber): str(r.get("ROIName", "")) for r in ds.get("StructureSetROISequence", []) or []}
    for k, rc in enumerate(ds.get("ROIContourSequence", []) or []):
        num = int(rc.get("ReferencedROINumber", 0) or 0)
        color = tuple(int(c) for c in rc.get("ROIDisplayColor", PALETTE[k % len(PALETTE)]))[:3]
        name = names.get(num, f"ROI {num}")
        obj.findings.append(name)
        for c in rc.get("ContourSequence", []) or []:
            try:
                pts = np.array([float(v) for v in c.ContourData], dtype=float).reshape(-1, 3)
            except (AttributeError, ValueError):
                continue
            gt = str(c.get("ContourGeometricType", "CLOSED_PLANAR")).upper()
            kind = "point" if gt == "POINT" else "polygon" if gt.startswith("CLOSED") else "polyline"
            obj.planar.append(Graphic(kind, [], name, pts, color))
    return obj


# ------------------------------------------------------------------ SEG
def parse_seg(ds, path: str | None = None) -> OverlayObject:
    obj = OverlayObject(str(ds.get("SOPInstanceUID", "")), "SEG",
                        str(ds.get("SeriesDescription", "") or ds.get("ContentLabel", "") or "Segmentação"),
                        (80, 200, 255), study_uid=str(ds.get("StudyInstanceUID", "")))
    segs = {}
    for k, s in enumerate(ds.get("SegmentSequence", []) or []):
        num = int(s.get("SegmentNumber", k + 1))
        lab = str(s.get("SegmentLabel", "") or f"Segmento {num}")
        col = lab_to_rgb(s.RecommendedDisplayCIELabValue) if "RecommendedDisplayCIELabValue" in s \
            else PALETTE[k % len(PALETTE)]
        segs[num] = (lab, col)
        obj.findings.append(lab)
    try:
        arr = ds.pixel_array
    except Exception as e:  # noqa: BLE001
        log.warning("SEG sem pixels legíveis: %s", e)
        return obj
    if arr.ndim == 2:
        arr = arr[None]
    frac = str(ds.get("SegmentationType", "BINARY")).upper() == "FRACTIONAL"
    thr = (float(ds.get("MaximumFractionalValue", 255)) / 2) if frac else 0
    shared = (ds.get("SharedFunctionalGroupsSequence") or [None])[0]
    s_ori = s_sp = None
    if shared is not None:
        try:
            s_ori = np.array([float(v) for v in shared.PlaneOrientationSequence[0].ImageOrientationPatient])
        except Exception:  # noqa: BLE001
            pass
        try:
            s_sp = tuple(float(v) for v in shared.PixelMeasuresSequence[0].PixelSpacing)
        except Exception:  # noqa: BLE001
            pass
    per = ds.get("PerFrameFunctionalGroupsSequence") or []
    for i in range(arr.shape[0]):
        m = arr[i] > thr
        if not m.any():
            continue
        fg = per[i] if i < len(per) else None
        num, pos, ori, sp, ref = 1, None, s_ori, s_sp, None
        if fg is not None:
            try:
                num = int(fg.SegmentIdentificationSequence[0].ReferencedSegmentNumber)
            except Exception:  # noqa: BLE001
                pass
            try:
                pos = np.array([float(v) for v in fg.PlanePositionSequence[0].ImagePositionPatient])
            except Exception:  # noqa: BLE001
                pass
            try:
                ori = np.array([float(v) for v in fg.PlaneOrientationSequence[0].ImageOrientationPatient])
            except Exception:  # noqa: BLE001
                pass
            try:
                sp = tuple(float(v) for v in fg.PixelMeasuresSequence[0].PixelSpacing)
            except Exception:  # noqa: BLE001
                pass
            try:
                src = fg.DerivationImageSequence[0].SourceImageSequence[0]
                fr = src.get("ReferencedFrameNumber")
                ref = (str(src.ReferencedSOPInstanceUID), int(fr) - 1 if fr else 0)
            except Exception:  # noqa: BLE001
                pass
        lab, col = segs.get(num, (f"Segmento {num}", PALETTE[(num - 1) % len(PALETTE)]))
        if pos is not None and ori is not None and sp is not None:
            # guarda só o recorte do segmento: o quadro do SEG tem o tamanho da imagem inteira, e
            # uma SEG de órgãos (19 estruturas × centenas de cortes) passaria de 1 GB em memória.
            # O desenho e o 3D acham o lugar pela posição do pixel (0,0), que acompanha o recorte.
            rs_, cs_ = np.flatnonzero(m.any(axis=1)), np.flatnonzero(m.any(axis=0))
            r0, c0 = int(rs_[0]), int(cs_[0])
            m = m[r0:int(rs_[-1]) + 1, c0:int(cs_[-1]) + 1].copy()
            pos = pos + c0 * sp[1] * ori[:3] + r0 * sp[0] * ori[3:]
        obj.masks.append(MaskFrame(m, col, lab, pos, ori, sp, ref))
    return obj


def por_segmento(obj: "OverlayObject") -> list:
    """Uma SEG com vários segmentos vira um objeto por segmento, para ligar e desligar cada órgão
    na lista de sobreposições. Com um segmento só, devolve o próprio objeto."""
    rotulos = list(dict.fromkeys(mf.label for mf in obj.masks))
    if obj.source != "SEG" or len(rotulos) < 2:
        return [obj]
    out = []
    for lab in rotulos:
        mfs = [mf for mf in obj.masks if mf.label == lab]
        out.append(OverlayObject(f"{obj.key}#{lab}", "SEG", lab, tuple(mfs[0].color), obj.enabled,
                                 obj.study_uid, masks=mfs, findings=[lab]))
    return out


# ------------------------------------------------------------------ qualquer plano (0.99.16)
#: teto de um volume derivado (voxels): acima disso o objeto fica só nos cortes paralelos
MAX_VOXELS_DERIVADO = 250_000_000


def _normal(ori) -> np.ndarray:
    n = np.cross(np.asarray(ori[:3], float), np.asarray(ori[3:], float))
    return n / max(float(np.linalg.norm(n)), 1e-9)


def paralela(mf: MaskFrame, normal) -> bool:
    """A máscara de um corte está no mesmo plano (paralelo) do quadro? Sem posição: trata como sim
    (é desenhada pela referência à imagem, como sempre foi)."""
    if mf.position is None or mf.orientation is None or normal is None:
        return True
    return abs(float(_normal(mf.orientation) @ np.asarray(normal, float))) >= 0.99


def volumes_das_mascaras(masks: list) -> list:
    """Máscaras de corte (SEG) empilhadas numa `MaskVolume` por rótulo, para aparecerem em **qualquer**
    plano — o sagital reformatado de uma SEG axial, por exemplo. Pedido dele (30/10/2026): *"aplique a
    opção de ver as marcações quando reformatar para todas as IAs e segmentações que já temos e que
    teremos"*. Os cortes que faltam (sem nada daquele rótulo) ficam vazios no volume."""
    grupos: dict = {}
    for mf in masks:
        if mf.position is None or mf.orientation is None or mf.spacing is None or mf.alvo:
            continue
        grupos.setdefault(mf.label, []).append(mf)
    out = []
    for lab, mfs in grupos.items():
        ori = np.asarray(mfs[0].orientation, float)
        row, col, n = ori[:3], ori[3:], _normal(ori)
        mfs = [m for m in mfs if abs(float(_normal(m.orientation) @ n)) >= 0.99]
        rs, cs = (float(x) for x in mfs[0].spacing)
        ds = np.array([float(np.asarray(m.position, float) @ n) for m in mfs])
        uniq = np.unique(np.round(ds, 2))
        dz = float(np.median(np.diff(uniq))) if len(uniq) > 1 else max(rs, cs)
        if dz <= 1e-3:
            continue
        us = np.array([float(np.asarray(m.position, float) @ row) / cs for m in mfs])
        vs = np.array([float(np.asarray(m.position, float) @ col) / rs for m in mfs])
        u0, v0, d0 = float(us.min()), float(vs.min()), float(ds.min())
        W = int(round(max(u + m.mask.shape[1] for u, m in zip(us, mfs)) - u0))
        H = int(round(max(v + m.mask.shape[0] for v, m in zip(vs, mfs)) - v0))
        K = int(round((float(ds.max()) - d0) / dz)) + 1
        if W <= 0 or H <= 0 or K * H * W > MAX_VOXELS_DERIVADO:
            continue
        vol = np.zeros((K, H, W), bool)
        for m, u, v, d in zip(mfs, us, vs, ds):
            k, x, y = int(round((d - d0) / dz)), int(round(u - u0)), int(round(v - v0))
            h, w = m.mask.shape
            vol[k, y:y + h, x:x + w] |= m.mask[: H - y, : W - x]
        origem = u0 * cs * row + v0 * rs * col + d0 * n
        out.append(MaskVolume(vol, origem, np.column_stack([row * cs, col * rs, n * dz]),
                              tuple(mfs[0].color), lab))
    return out


def _dentro_do_poligono(px: np.ndarray, py: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Par-ímpar (raio horizontal), vetorizado: px, py da grade; poly (N, 2)."""
    dentro = np.zeros(px.shape, bool)
    x, y = poly[:, 0], poly[:, 1]
    xj, yj = np.roll(x, 1), np.roll(y, 1)
    for a, b, c, d in zip(x, y, xj, yj):
        cruza = ((b > py) != (d > py)) & (px < (c - a) * (py - b) / ((d - b) if d != b else 1e-12) + a)
        dentro ^= cruza
    return dentro


def volumes_dos_contornos(planar: list, passo: float = 1.0) -> list:
    """Contornos fechados (RTSTRUCT, SR 3D) de um mesmo nome, empilhados e preenchidos numa `MaskVolume`,
    para aparecerem cortados em qualquer plano. Contornos de planos diferentes entre si ficam de fora."""
    grupos: dict = {}
    for g in planar:
        if g.kind != "polygon" or g.points3d is None or len(g.points3d) < 3:
            continue
        grupos.setdefault((g.text, g.color), []).append(np.asarray(g.points3d, float))
    out = []
    for (nome, cor), conts in grupos.items():
        c0 = conts[0] - conts[0].mean(axis=0)
        try:
            n = np.linalg.svd(c0, full_matrices=False)[2][2]
        except np.linalg.LinAlgError:
            continue
        n = n / np.linalg.norm(n)
        a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
        row = a - (a @ n) * n
        row /= np.linalg.norm(row)
        col = np.cross(n, row)
        planos = [c for c in conts if np.abs((c - c.mean(axis=0)) @ n).max() < 0.5]
        if not planos:
            continue
        ds = np.array([float(c.mean(axis=0) @ n) for c in planos])
        uniq = np.unique(np.round(ds, 2))
        dz = float(np.median(np.diff(uniq))) if len(uniq) > 1 else passo
        todos = np.concatenate(planos)
        us, vs = todos @ row, todos @ col
        u0, v0, d0 = float(us.min()) - passo, float(vs.min()) - passo, float(ds.min())
        W = int(np.ceil((float(us.max()) - u0) / passo)) + 2
        H = int(np.ceil((float(vs.max()) - v0) / passo)) + 2
        K = int(round((float(ds.max()) - d0) / dz)) + 1
        if K * H * W > MAX_VOXELS_DERIVADO:
            continue
        vol = np.zeros((K, H, W), bool)
        for c, d in zip(planos, ds):
            k = int(round((d - d0) / dz))
            pu, pv = (c @ row - u0) / passo, (c @ col - v0) / passo
            x0, x1 = max(0, int(pu.min())), min(W, int(np.ceil(pu.max())) + 1)
            y0, y1 = max(0, int(pv.min())), min(H, int(np.ceil(pv.max())) + 1)
            gx, gy = np.meshgrid(np.arange(x0, x1, dtype=float), np.arange(y0, y1, dtype=float))
            vol[k, y0:y1, x0:x1] ^= _dentro_do_poligono(gx, gy, np.column_stack([pu, pv]))   # buracos: par-ímpar
        origem = u0 * row + v0 * col + d0 * n
        out.append(MaskVolume(vol, origem, np.column_stack([row * passo, col * passo, n * dz]),
                              tuple(cor) if cor else (80, 220, 120), nome))
    return out


def volumes_derivados(obj: "OverlayObject") -> list:
    """As `MaskVolume` que o objeto ganha para os planos que não são o da aquisição (com cache)."""
    chave = (len(obj.masks), len(obj.planar), obj.version)
    cache = getattr(obj, "_derivados", None)
    if cache is not None and cache[0] == chave:
        return cache[1]
    try:
        vols = volumes_das_mascaras(obj.masks) + volumes_dos_contornos(obj.planar)
    except Exception:  # noqa: BLE001
        log.exception("volume derivado de %s", obj.label)
        vols = []
    obj._derivados = (chave, vols)
    return vols


# ------------------------------------------------------------------ leitura
def load_object(path: str) -> OverlayObject | None:
    try:
        ds = pydicom.dcmread(path, force=True)
    except Exception as e:  # noqa: BLE001
        log.warning("objeto %s ilegível: %s", path, e)
        return None
    cls = str(ds.get("SOPClassUID", ""))
    mod = str(ds.get("Modality", "")).upper()
    try:
        if cls == SEG_CLASS or mod == "SEG":
            return parse_seg(ds, path)
        if cls == RTSTRUCT_CLASS or mod == "RTSTRUCT":
            return parse_rtstruct(ds)
        if cls in GSPS_CLASSES or mod == "PR":
            return parse_gsps(ds)
        if mod == "SR" or cls.startswith("1.2.840.10008.5.1.4.1.1.88."):
            obj = parse_sr(ds)
            has = obj.by_frame or obj.planar
            return obj if has else None
    except Exception as e:  # noqa: BLE001
        log.warning("objeto %s: %s", path, e)
    return None


# ------------------------------------------------------------------ projeção num plano
def project(points3d: np.ndarray, pos: np.ndarray, row: np.ndarray, col: np.ndarray, normal: np.ndarray,
            spacing: tuple, tol_mm: float) -> list | None:
    """Pontos 3D (mm) -> (coluna, linha) no plano da imagem, se estiverem nele (distância ≤ tol)."""
    d = points3d - pos
    dist = d @ normal
    if np.abs(dist).mean() > tol_mm:
        return None
    rs, cs = spacing
    u = d @ row / cs + 0.5            # posição DICOM = centro do pixel; aqui o pixel (0,0) vai de 0 a 1
    v = d @ col / rs + 0.5
    return list(zip(u.tolist(), v.tolist()))


def mask_rect(mf: MaskFrame, pos, row, col, normal, spacing, tol_mm: float, sop: str, frame: int):
    """Onde desenhar a máscara na imagem: (x0, y0, largura, altura) em pixels da imagem, ou None."""
    h, w = mf.mask.shape
    if mf.position is not None and mf.orientation is not None and pos is not None:
        if abs(float(np.dot(np.cross(mf.orientation[:3], mf.orientation[3:]), normal))) < 0.99:
            return None
        if abs(float((mf.position - pos) @ normal)) > tol_mm:
            return None
        rs, cs = spacing
        mrs, mcs = mf.spacing or spacing
        d = mf.position - pos
        x0, y0 = float(d @ row / cs), float(d @ col / rs)
        # centro do pixel (0,0) -> canto
        x0 -= 0.5 * mcs / cs - 0.5
        y0 -= 0.5 * mrs / rs - 0.5
        return x0, y0, w * mcs / cs, h * mrs / rs
    if mf.ref is not None and mf.ref[0] == sop and mf.ref[1] in (frame, -1):
        if mf.alvo:                              # máscara em grade menor: estica sobre a imagem
            return 0.0, 0.0, float(mf.alvo[1]), float(mf.alvo[0])
        return 0.0, 0.0, float(w), float(h)
    return None
