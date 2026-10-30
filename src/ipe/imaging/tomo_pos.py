"""Onde está o corte dentro da mama comprimida (tomossíntese).

A estação de trabalho mostra num canto um desenho pequeno: o relógio da mama e a mama
comprimida de perfil, com um marcador no corte que está na tela. Tudo o que esse desenho
precisa já vem no arquivo do Pristina e de qualquer aparelho que siga o IOD de
tomossíntese de mama:

- **posição de cada corte** (`ImagePositionPatient` por quadro, dentro da Per-Frame
  Functional Groups) — é o que dá a profundidade em milímetros, não "corte 5 de 10";
- **espessura comprimida** (`BodyPartThickness`) e força (`CompressionForce`), na
  X-Ray 3D Acquisition Sequence (0018,9507);
- **ângulo do braço** (`PrimaryPositionerScanStartAngle` / `PositionerPrimaryAngle`):
  0° na CC, 45° na MLO — é a inclinação com que as placas são desenhadas;
- **lado** (`FrameLaterality` / `ImageLaterality`).

Nada aqui usa Qt: o desenho fica em `ui/viewer/tomo_dial.py`.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

ACQ_3D = 0x00189507            # X-Ray 3D Acquisition Sequence
MAX_CACHE = 24
_cache: dict = {}


@dataclass
class TomoGeometry:
    """Profundidade de cada corte e a geometria da compressão."""

    depths_mm: list = field(default_factory=list)   # 0 = junto do detector
    thickness_mm: float | None = None               # espessura comprimida
    slab_mm: float | None = None                    # espessura de cada laje
    force_n: float | None = None
    paddle: str = ""
    angle_deg: float = 0.0                          # 0 = CC, 45 = MLO
    side: str = ""                                  # "R" / "L" / ""
    source: str = "estimado"                        # "quadros" | "arquivo" | "estimado"
    detector_known: bool = True                     # de que lado fica o detector

    # ------------------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.depths_mm)

    @property
    def span_mm(self) -> float:
        return (max(self.depths_mm) - min(self.depths_mm)) if self.depths_mm else 0.0

    @property
    def scale_mm(self) -> float:
        """Altura da faixa desenhada: tudo o que os cortes cobrem.

        A reconstrução passa da mama — 80 mm de cortes para 72 mm de compressão é o
        normal. A faixa mostra o que dá para rolar; a pá ganha uma marca própria.
        """
        return max(self.span_mm, self.thickness_mm or 0.0, 1.0)

    def paddle_fraction(self) -> float | None:
        """Onde a pá de compressão cai na faixa (None quando a espessura não veio)."""
        if not self.thickness_mm or self.span_mm <= 0:
            return None
        return float(np.clip(self.thickness_mm / self.scale_mm, 0.05, 1.0))

    def depth(self, i: int) -> float:
        if not self.depths_mm:
            return 0.0
        return self.depths_mm[max(0, min(i, self.n - 1))]

    def fraction(self, i: int) -> float:
        """0 = colado no detector, 1 = colado na pá de compressão."""
        return float(np.clip(self.depth(i) / self.scale_mm, 0.0, 1.0))

    def index_at(self, fraction: float) -> int:
        """Corte mais próximo de uma profundidade relativa — é o que o arrasto usa."""
        if not self.depths_mm:
            return 0
        alvo = float(np.clip(fraction, 0.0, 1.0)) * self.scale_mm
        return int(np.argmin([abs(d - alvo) for d in self.depths_mm]))

    # ------------------------------------------------------------------ texto
    def depth_text(self, i: int) -> str:
        return f"{self.depth(i):.0f} mm"

    def thickness_text(self) -> str:
        return f"comprimida {self.thickness_mm:.0f} mm" if self.thickness_mm else ""

    def tip_text(self, i: int) -> str:
        partes = [f"Corte {i + 1} de {self.n}", f"{self.depth(i):.0f} mm a partir do detector"]
        if self.thickness_mm:
            partes.append(f"mama comprimida em {self.thickness_mm:.0f} mm")
        if self.slab_mm:
            partes.append(f"laje de {self.slab_mm:.0f} mm")
        if self.force_n:
            partes.append(f"compressão de {self.force_n:.0f} N")
        if self.paddle:
            partes.append(self.paddle)
        if self.source == "estimado":
            partes.append("profundidade estimada: o arquivo não traz a posição de cada corte")
        elif not self.detector_known:
            partes.append("de que lado fica o detector foi deduzido da ordem dos cortes")
        return " · ".join(partes)


# ---------------------------------------------------------------------- leitura
def _first(seq):
    try:
        return seq[0] if seq else None
    except Exception:  # noqa: BLE001
        return None


def _num(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _acq(ds):
    """Item da X-Ray 3D Acquisition Sequence, onde ficam espessura, força e ângulo."""
    try:
        return _first(ds[ACQ_3D].value)
    except (KeyError, IndexError):
        return None


def _angle_from(ds, acq, normal) -> float:
    for fonte, chave in ((acq, "PrimaryPositionerScanStartAngle"), (ds, "PositionerPrimaryAngle")):
        if fonte is not None:
            v = _num(fonte.get(chave))
            if v is not None:
                return abs(float(v))
    if acq is not None:
        proj = _first(acq.get("PerProjectionAcquisitionSequence"))
        v = _num(proj.get("PositionerPrimaryAngle")) if proj is not None else None
        if v is not None:
            return abs(float(v))
    if normal is not None:
        # inclinação do eixo de compressão no plano coronal: 0 = crânio-caudal
        return float(math.degrees(math.atan2(abs(float(normal[0])), abs(float(normal[2])) + 1e-9)))
    return 0.0


def _side_from(ds) -> str:
    fa = _first(ds.get("SharedFunctionalGroupsSequence"))
    if fa is not None:
        anat = _first(fa.get("FrameAnatomySequence"))
        lado = str(anat.get("FrameLaterality", "")) if anat is not None else ""
        if lado:
            return lado.upper()[:1]
    for chave in ("ImageLaterality", "Laterality"):
        lado = str(ds.get(chave, "") or "")
        if lado:
            return lado.upper()[:1]
    return ""


def _orientation(ds):
    sfg = _first(ds.get("SharedFunctionalGroupsSequence"))
    if sfg is not None:
        po = _first(sfg.get("PlaneOrientationSequence"))
        if po is not None and "ImageOrientationPatient" in po:
            return np.array([float(x) for x in po.ImageOrientationPatient], float)
    if "ImageOrientationPatient" in ds:
        return np.array([float(x) for x in ds.ImageOrientationPatient], float)
    return None


def _positions(ds) -> list:
    pfg = ds.get("PerFrameFunctionalGroupsSequence")
    if not pfg:
        return []
    saida = []
    for fr in pfg:
        pp = _first(fr.get("PlanePositionSequence"))
        if pp is None or "ImagePositionPatient" not in pp:
            return []
        saida.append(np.array([float(x) for x in pp.ImagePositionPatient], float))
    return saida


def _slab_mm(ds) -> float | None:
    sfg = _first(ds.get("SharedFunctionalGroupsSequence"))
    if sfg is not None:
        pm = _first(sfg.get("PixelMeasuresSequence"))
        if pm is not None:
            v = _num(pm.get("SliceThickness"))
            if v:
                return v
    return _num(ds.get("SliceThickness"))


def depths_from_positions(positions: list, normal) -> tuple[list, bool]:
    """Profundidade de cada corte a partir do detector.

    O detector é o lado de baixo: em CC e em MLO os cortes caminham do inferior para o
    superior. Quando a incidência é lateral pura (o eixo não tem componente vertical),
    a ordem do arquivo é mantida e o chamador avisa que foi deduzida.
    """
    if len(positions) < 2:
        return [0.0] * len(positions), True
    v = np.asarray(positions[-1], float) - np.asarray(positions[0], float)
    norma = float(np.linalg.norm(v))
    eixo = v / norma if norma > 1e-6 else (np.asarray(normal, float) if normal is not None
                                           else np.array([0.0, 0.0, 1.0]))
    certo = abs(float(eixo[2])) >= 0.2
    if certo and float(eixo[2]) < 0:
        eixo = -eixo                     # do detector (inferior) para a pá (superior)
    t = [float(np.dot(np.asarray(p, float), eixo)) for p in positions]
    base = min(t)
    return [x - base for x in t], certo


def from_dataset(ds, n_frames: int = 0) -> TomoGeometry | None:
    """Geometria a partir de um arquivo já lido (multiquadro de tomossíntese)."""
    acq = _acq(ds)
    normal = None
    ori = _orientation(ds)
    if ori is not None and len(ori) == 6:
        normal = np.cross(ori[:3], ori[3:])
    espessura = _num(acq.get("BodyPartThickness")) if acq is not None else None
    if espessura is None:
        espessura = _num(ds.get("BodyPartThickness"))
    forca = _num(acq.get("CompressionForce")) if acq is not None else None
    if forca is None:
        forca = _num(ds.get("CompressionForce"))
    pa = str((acq.get("PaddleDescription", "") if acq is not None else "")
             or ds.get("PaddleDescription", "") or "")
    pos = _positions(ds)
    n = n_frames or len(pos) or int(_num(ds.get("NumberOfFrames")) or 0)
    if n < 2:
        return None
    if len(pos) == n:
        depths, certo = depths_from_positions(pos, normal)
        fonte = "arquivo"
    else:
        alvo = espessura or float(n)
        depths = [alvo * i / max(n - 1, 1) for i in range(n)]
        certo, fonte = True, "estimado"
    return TomoGeometry(depths_mm=depths, thickness_mm=espessura, slab_mm=_slab_mm(ds),
                        force_n=forca, paddle=pa, angle_deg=_angle_from(ds, acq, normal),
                        side=_side_from(ds), source=fonte, detector_known=certo)


def from_frames(frames) -> TomoGeometry | None:
    """Geometria da tomo de uma lista de quadros (multiquadro num arquivo só ou um por corte)."""
    if not frames or len(frames) < 2:
        return None
    chave = (frames[0].path, len(frames), frames[0].frame_index, frames[-1].frame_index)
    if chave in _cache:
        return _cache[chave]
    geo = None
    try:
        posicoes = [f.position for f in frames]
        if all(p is not None for p in posicoes) and len({tuple(np.round(p, 3)) for p in posicoes}) > 1:
            # um arquivo por corte: a posição já veio do banco
            ori = frames[0].orientation
            normal = np.cross(ori[:3], ori[3:]) if ori is not None and len(ori) == 6 else None
            depths, certo = depths_from_positions(posicoes, normal)
            geo = TomoGeometry(depths_mm=depths, source="quadros", detector_known=certo)
            extra = _read(frames[0].path, 0)
            if extra is not None:
                geo.thickness_mm, geo.slab_mm = extra.thickness_mm, extra.slab_mm
                geo.force_n, geo.paddle = extra.force_n, extra.paddle
                geo.angle_deg, geo.side = extra.angle_deg, extra.side
        else:
            geo = _read(frames[0].path, len(frames))
    except Exception:  # noqa: BLE001
        log.exception("geometria da tomossíntese")
        geo = None
    if len(_cache) > MAX_CACHE:
        _cache.clear()
    _cache[chave] = geo
    return geo


def _read(path: str, n_frames: int) -> TomoGeometry | None:
    import pydicom
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
    except Exception:  # noqa: BLE001
        log.exception("lendo %s", path)
        return None
    return from_dataset(ds, n_frames)


def forget() -> None:
    """Esvazia o cache (trocar de local, reimportar)."""
    _cache.clear()
