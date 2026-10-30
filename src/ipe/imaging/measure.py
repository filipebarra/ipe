"""Medidas e anotações (sem depender de Qt): régua, ângulo, ROIs, seta e texto.

Coordenadas de imagem: (x, y) = (coluna, linha), com o pixel (0, 0) ocupando o
quadrado [0, 1) × [0, 1). O centro do pixel (c, r) fica em (c + 0.5, r + 0.5).
Distâncias, ângulos e áreas usam o espaçamento real do pixel (mm), inclusive
quando o pixel não é quadrado.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

KINDS = {
    "line": "Régua",
    "polyline": "Polilinha",
    "angle": "Ângulo",
    "cobb": "Ângulo de Cobb",
    "ellipse": "ROI elíptica",
    "rect": "ROI retangular",
    "polygon": "ROI poligonal / livre",
    "probe": "Intensidade (valor do pixel)",
    "height": "Diferença de altura",
    "ctr": "Índice cardiotorácico",
    "spine": "Rotular coluna",
    "tic": "Curva tempo-intensidade",
    "calibration": "Linha de calibração",
    "arrow": "Seta",
    "text": "Texto",
    "pencil": "Lápis",
    "seg": "Segmentação 3D (volume)",
}
ROI_KINDS = ("ellipse", "polygon", "rect", "tic")
SPINE_LABELS = ([f"C{i}" for i in range(1, 8)] + [f"T{i}" for i in range(1, 13)]
                + [f"L{i}" for i in range(1, 6)] + ["S1", "S2", "S3", "S4", "S5", "Cóccix"])


def spine_label(start: str, i: int) -> str:
    k = SPINE_LABELS.index(start) if start in SPINE_LABELS else 0
    return SPINE_LABELS[min(k + i, len(SPINE_LABELS) - 1)]

Point = tuple[float, float]


@dataclass
class Annotation:
    kind: str
    frame_key: tuple[str, int]            # (SOPInstanceUID, quadro); "" nos quadros de MPR
    points: list[Point]
    text: str = ""
    study_uid: str = ""
    series_uid: str = ""
    db_id: int | None = None
    done: bool = True                     # False enquanto o desenho não terminou
    cache: dict = field(default_factory=dict, repr=False, compare=False)
    meta: dict = field(default_factory=dict, compare=False)   # ex.: {"lesion": id, "mm": 23.1}

    @property
    def persistent(self) -> bool:
        return bool(self.frame_key[0]) and self.done

    def data_json(self) -> str:
        d = {"points": [list(p) for p in self.points], "text": self.text}
        if self.meta:
            d["meta"] = self.meta
        return json.dumps(d)

    @staticmethod
    def from_record(r: dict) -> "Annotation":
        d = json.loads(r.get("data") or "{}")
        return Annotation(r["kind"], (r["sop_uid"], int(r["frame_index"])),
                          [tuple(p) for p in d.get("points", [])], d.get("text", ""),
                          r.get("study_uid", ""), r.get("series_uid", ""), r.get("id"),
                          meta=dict(d.get("meta") or {}))


# --------------------------------------------------------------- geometria
def length_mm(p1: Point, p2: Point, spacing: tuple[float, float] | None) -> float:
    rs, cs = spacing or (1.0, 1.0)
    return math.hypot((p2[0] - p1[0]) * cs, (p2[1] - p1[1]) * rs)


def angle_deg(p1: Point, vertex: Point, p3: Point, spacing: tuple[float, float] | None) -> float:
    """Ângulo no vértice, em graus (0–180), no espaço físico."""
    rs, cs = spacing or (1.0, 1.0)
    a = np.array([(p1[0] - vertex[0]) * cs, (p1[1] - vertex[1]) * rs])
    b = np.array([(p3[0] - vertex[0]) * cs, (p3[1] - vertex[1]) * rs])
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.degrees(np.arccos(np.clip(a @ b / (na * nb), -1.0, 1.0))))


def cobb_deg(p0: Point, p1: Point, p2: Point, p3: Point, spacing: tuple[float, float] | None) -> float:
    """Ângulo (agudo) entre duas retas, cada uma definida por dois pontos."""
    rs, cs = spacing or (1.0, 1.0)
    a = np.array([(p1[0] - p0[0]) * cs, (p1[1] - p0[1]) * rs])
    b = np.array([(p3[0] - p2[0]) * cs, (p3[1] - p2[1]) * rs])
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.degrees(np.arccos(np.clip(abs(a @ b) / (na * nb), 0.0, 1.0))))


def polyline_mm(points: list[Point], spacing: tuple[float, float] | None) -> float:
    return sum(length_mm(points[i], points[i + 1], spacing) for i in range(len(points) - 1))


def calibration_spacing(ann: "Annotation") -> tuple[float, float] | None:
    """Espaçamento (mm/pixel) definido por uma linha de calibração."""
    try:
        mm = float(str(ann.text).replace(",", "."))
    except ValueError:
        return None
    if len(ann.points) < 2 or mm <= 0:
        return None
    px = math.hypot(ann.points[1][0] - ann.points[0][0], ann.points[1][1] - ann.points[0][1])
    return (mm / px, mm / px) if px > 0 else None


def pixel_value(pixels: np.ndarray, p: Point) -> float | None:
    c, r = int(math.floor(p[0])), int(math.floor(p[1]))
    if pixels.ndim != 2 or not (0 <= r < pixels.shape[0] and 0 <= c < pixels.shape[1]):
        return None
    return float(pixels[r, c])


def polygon_area_px(points: list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    x = np.array([p[0] for p in points])
    y = np.array([p[1] for p in points])
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def roi_area_px(kind: str, points: list[Point]) -> float:
    if kind in ("ellipse", "tic") and len(points) >= 2:
        (x1, y1), (x2, y2) = points[:2]
        return math.pi * abs(x2 - x1) / 2 * abs(y2 - y1) / 2
    if kind == "rect" and len(points) >= 2:
        (x1, y1), (x2, y2) = points[:2]
        return abs(x2 - x1) * abs(y2 - y1)
    return polygon_area_px(points)


def roi_mask(kind: str, points: list[Point], shape: tuple[int, int]):
    """Máscara dos pixels cujo centro está dentro da ROI.
    Devolve ((fatia_linhas, fatia_colunas), máscara) ou None se a ROI está fora da imagem."""
    h, w = shape[:2]
    if len(points) < 2 or (kind == "polygon" and len(points) < 3):
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = max(0, int(math.floor(min(xs)))), min(w, int(math.ceil(max(xs))))
    y0, y1 = max(0, int(math.floor(min(ys)))), min(h, int(math.ceil(max(ys))))
    if x1 <= x0 or y1 <= y0:
        return None
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64) + 0.5
    if kind == "rect":
        mask = ((xx >= min(xs)) & (xx <= max(xs)) & (yy >= min(ys)) & (yy <= max(ys)))
    elif kind in ("ellipse", "tic"):
        (ax, ay), (bx, by) = points[:2]
        cx, cy = (ax + bx) / 2, (ay + by) / 2
        rx, ry = abs(bx - ax) / 2, abs(by - ay) / 2
        if rx <= 0 or ry <= 0:
            return None
        mask = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
    else:
        mask = _inside_polygon(xx, yy, points)
    return (slice(y0, y1), slice(x0, x1)), mask


def _inside_polygon(xx: np.ndarray, yy: np.ndarray, pts: list[Point]) -> np.ndarray:
    """Regra par-ímpar (ray casting), vetorizada."""
    inside = np.zeros(xx.shape, dtype=bool)
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if yi != yj:
            crosses = (yi > yy) != (yj > yy)
            x_at = (xj - xi) * (yy - yi) / (yj - yi) + xi
            inside ^= crosses & (xx < x_at)
        j = i
    return inside


@dataclass
class RoiStats:
    n: int
    mean: float | None
    sd: float | None
    minimum: float | None
    maximum: float | None
    area_px: float
    area_mm2: float | None


def roi_stats(pixels: np.ndarray, kind: str, points: list[Point],
              spacing: tuple[float, float] | None) -> RoiStats:
    area_px = roi_area_px(kind, points)
    area_mm2 = area_px * spacing[0] * spacing[1] if spacing else None
    res = roi_mask(kind, points, pixels.shape)
    if res is None or pixels.ndim != 2:
        return RoiStats(0, None, None, None, None, area_px, area_mm2)
    sl, mask = res
    vals = pixels[sl][mask]
    if vals.size == 0:
        return RoiStats(0, None, None, None, None, area_px, area_mm2)
    vals = vals.astype(np.float64)
    return RoiStats(int(vals.size), float(vals.mean()), float(vals.std(ddof=1)) if vals.size > 1 else 0.0,
                    float(vals.min()), float(vals.max()), area_px, area_mm2)


def unit_for(modality: str) -> str:
    return "HU" if modality.upper() == "CT" else ""


def _num(v: float) -> str:
    return f"{v:.1f}" if abs(v) < 1000 else f"{v:.0f}"


def labels(ann: Annotation, pixels: np.ndarray | None, spacing: tuple[float, float] | None,
           modality: str = "", suv: float | None = None) -> list[str]:
    """Texto que acompanha a medida na tela."""
    pts, k = ann.points, ann.kind
    unit = "mm" if spacing else "px"
    if k in ("line", "calibration") and len(pts) >= 2:
        d = length_mm(pts[0], pts[1], spacing)
        if k == "calibration":
            if not ann.text:
                return ["Calibração"]
            if (ann.meta or {}).get("escopo") == "imagem":
                return [f"Calibração: {ann.text} mm (só esta imagem)"]
            return [f"Calibração: {ann.text} mm"]
        return [f"{d:.1f} mm" if spacing else f"{d:.0f} px"]
    if k == "polyline" and len(pts) >= 2:
        return [f"{polyline_mm(pts, spacing):.1f} {unit}"]
    if k == "angle" and len(pts) >= 3:
        return [f"{angle_deg(pts[0], pts[1], pts[2], spacing):.1f}°"]
    if k == "cobb" and len(pts) >= 4:
        return [f"Cobb {cobb_deg(*pts[:4], spacing):.1f}°"]
    if k == "height" and len(pts) >= 2:
        rs, cs = spacing or (1.0, 1.0)
        dv, dh = abs(pts[1][1] - pts[0][1]) * rs, abs(pts[1][0] - pts[0][0]) * cs
        return [f"Δ vertical {dv:.1f} {unit}", f"Δ horizontal {dh:.1f} {unit}"]
    if k == "ctr" and len(pts) >= 2:
        cs = (spacing or (1.0, 1.0))[1]
        heart = abs(pts[1][0] - pts[0][0]) * cs
        out = [f"Coração {heart:.1f} {unit}"]
        if len(pts) >= 4:
            chest = abs(pts[3][0] - pts[2][0]) * cs
            out.append(f"Tórax {chest:.1f} {unit}")
            if chest > 0:
                out.append(f"ICT {heart / chest:.2f}")
        return out
    if k == "probe" and pts and pixels is not None:
        v = pixel_value(pixels, pts[0])
        if v is None:
            return []
        u = unit_for(modality)
        if suv:
            return [f"SUV {v * suv:.2f}", f"{_num(v)} Bq/ml"]
        return [f"{_num(v)}{' ' + u if u else ''}"]
    if k in ROI_KINDS and pixels is not None:
        key = (tuple(pts), id(pixels), spacing)
        st = ann.cache.get(key)
        if st is None:
            st = roi_stats(pixels, k, pts, spacing)
            keep = {kk: vv for kk, vv in ann.cache.items() if isinstance(kk, str)}
            ann.cache.clear()
            ann.cache.update(keep)
            ann.cache[key] = st
        out = []
        u = unit_for(modality)
        u = f" {u}" if u else ""
        if st.mean is not None and suv:
            out.append(f"SUVmáx {st.maximum * suv:.2f}  SUVméd {st.mean * suv:.2f}")
        if st.mean is not None:
            out.append(f"Média {_num(st.mean)} ± {_num(st.sd)}{u}")
            out.append(f"Mín {_num(st.minimum)}  Máx {_num(st.maximum)}")
        if st.area_mm2 is not None:
            out.append(f"Área {st.area_mm2 / 100:.2f} cm²" if st.area_mm2 >= 100
                       else f"Área {st.area_mm2:.1f} mm²")
        else:
            out.append(f"Área {st.area_px:.0f} px²")
        if k == "tic":
            out.append(ann.text or "Curva: duplo clique")
        return out
    if k == "seg":
        m = ann.meta or {}
        out = [f"{m.get('ml', 0):.2f} mL"]
        eixos = m.get("eixos_mm")
        if eixos and len(eixos) == 3:      # os três eixos perpendiculares: é o que vai no laudo
            out.append(f"Eixos {eixos[0]:.1f} × {eixos[1]:.1f} × {eixos[2]:.1f} mm")
        elif m.get("mm"):
            out.append(f"Maior eixo {m['mm']:.1f} mm")
        if m.get("dist_mamilo_mm") is not None:
            out.append(f"Mamilo {m['dist_mamilo_mm']:.0f} mm")
        if m.get("suvmax") is not None:
            out.append(f"SUVmáx {m['suvmax']:.2f}  SUVpk {m.get('suvpeak') or 0:.2f}")
            out.append(f"TLG {m.get('tlg') or 0:.1f}")
        elif m.get("mean") is not None:
            u = unit_for(modality)
            out.append(f"Média {_num(m['mean'])}{' ' + u if u else ''}")
        return out
    if k in ("text", "arrow") and ann.text:
        return [ann.text]
    return []


# --------------------------------------------------------------- edição
def nearest_handle(ann: Annotation, p: Point, tol: float) -> int | None:
    """Índice do ponto de controle mais próximo (até `tol`, em pixels de imagem)."""
    if ann.kind in ("polygon", "pencil"):
        return None                         # desenho livre: move-se inteiro, não ponto a ponto
    best, best_d = None, tol
    for i, q in enumerate(ann.points):
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d <= best_d:
            best, best_d = i, d
    return best


def _dist_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def hit(ann: Annotation, p: Point, tol: float) -> bool:
    """O ponto está sobre a anotação (linha, borda ou interior da ROI)?"""
    pts = ann.points
    if not pts:
        return False
    k = ann.kind
    if k in ("text", "probe", "spine", "seg"):
        return any(math.hypot(q[0] - p[0], q[1] - p[1]) <= tol * 3 for q in pts)
    if k in ("line", "arrow", "calibration", "height") and len(pts) >= 2:
        return _dist_segment(p, pts[0], pts[1]) <= tol
    if k in ("angle", "polyline", "pencil"):
        return any(_dist_segment(p, pts[i], pts[i + 1]) <= tol for i in range(len(pts) - 1))
    if k in ("cobb", "ctr"):
        return any(_dist_segment(p, pts[i], pts[i + 1]) <= tol for i in range(0, len(pts) - 1, 2))
    if k == "rect" and len(pts) >= 2:
        xs, ys = (pts[0][0], pts[1][0]), (pts[0][1], pts[1][1])
        return min(xs) - tol <= p[0] <= max(xs) + tol and min(ys) - tol <= p[1] <= max(ys) + tol
    if k in ("ellipse", "tic") and len(pts) >= 2:
        (ax, ay), (bx, by) = pts[:2]
        cx, cy, rx, ry = (ax + bx) / 2, (ay + by) / 2, abs(bx - ax) / 2 + tol, abs(by - ay) / 2 + tol
        return ((p[0] - cx) / rx) ** 2 + ((p[1] - cy) / ry) ** 2 <= 1.0
    if ann.kind == "polygon" and len(pts) >= 3:
        xx, yy = np.array([[p[0]]]), np.array([[p[1]]])
        if _inside_polygon(xx, yy, pts)[0, 0]:
            return True
        return any(_dist_segment(p, pts[i], pts[(i + 1) % len(pts)]) <= tol for i in range(len(pts)))
    return False


def translate(ann: Annotation, dx: float, dy: float) -> None:
    ann.points = [(x + dx, y + dy) for x, y in ann.points]


# --------------------------------------------------------------- curva tempo-intensidade
def tic_analysis(times: list[float], values: list[float]) -> dict:
    """Curva cinética (RM de mama). `times` em segundos desde a 1ª fase (pré-contraste).

    Fase inicial: realce máximo nos primeiros 2 minutos (lento < 50%, médio 50–100%,
    rápido > 100%). Fase tardia: última fase comparada com esse pico: > +10% persistente
    (tipo I), entre −10% e +10% platô (tipo II), < −10% washout (tipo III)."""
    out: dict = {"enhancement": [], "initial": None, "initial_class": "", "delayed": None,
                 "curve_type": "", "summary": ""}
    if len(values) < 2 or not values[0]:
        out["summary"] = "Curva: precisa de 2+ fases" if len(values) < 2 else "Curva: pré-contraste nulo"
        return out
    base = values[0]
    enh = [(v - base) / abs(base) * 100.0 for v in values]
    out["enhancement"] = enh
    early = [i for i in range(1, len(values)) if times[i] - times[0] <= 120.0] or [1]
    i_peak = max(early, key=lambda i: values[i])
    initial = enh[i_peak]
    out["initial"] = initial
    out["initial_class"] = "lento" if initial < 50 else "médio" if initial <= 100 else "rápido"
    if len(values) >= 3 and i_peak < len(values) - 1:
        delayed = (values[-1] - values[i_peak]) / abs(values[i_peak]) * 100.0 if values[i_peak] else 0.0
        out["delayed"] = delayed
        out["curve_type"] = ("I (persistente)" if delayed > 10 else
                             "III (washout)" if delayed < -10 else "II (platô)")
        out["summary"] = f"Curva tipo {out['curve_type']}, inicial {out['initial_class']}"
    else:
        out["summary"] = f"Realce inicial {initial:.0f}% ({out['initial_class']})"
    return out
