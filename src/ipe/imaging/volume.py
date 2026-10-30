"""Volume 3D de uma série e reconstrução multiplanar (MPR) ortogonal com slab.

Geometria (coordenadas do paciente, LPS, em mm):
    P(i, j, k) = origem + i·dx·row_dir + j·dy·col_dir + k·slice_vec
onde i = coluna, j = linha, k = corte, e slice_vec já inclui o espaçamento
entre cortes (inclusive com gantry tilt, em que slice_vec não é perpendicular).

Os planos reformatados são exibidos na convenção radiológica:
coronal e sagital com superior em cima; direita do paciente à esquerda da tela.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ipe.imaging.series import Frame, FrameCache, FrameImage

log = logging.getLogger(__name__)

SLAB_MODES = {"avg": "Média", "mip": "MIP", "minip": "MinIP"}


class VolumeError(ValueError):
    """A série não forma um volume (ex.: poucas imagens, tamanhos diferentes)."""


@dataclass
class Volume:
    data: np.ndarray            # (nz, ny, nx), int16 ou float32
    origin: np.ndarray          # posição do voxel (0,0,0)
    row_dir: np.ndarray         # direção de i (colunas)
    col_dir: np.ndarray         # direção de j (linhas)
    slice_vec: np.ndarray       # vetor entre cortes consecutivos (mm)
    dx: float
    dy: float
    window: tuple[float, float] | None
    source_path: str
    warnings: list[str] = field(default_factory=list)
    monochrome1: bool = False

    @property
    def dz(self) -> float:
        return float(np.linalg.norm(self.slice_vec))

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.data.shape   # type: ignore[return-value]

    def matrix(self) -> np.ndarray:
        """Matriz 3x3 que leva índices (i, j, k) a deslocamento em mm."""
        return np.column_stack([self.row_dir * self.dx, self.col_dir * self.dy, self.slice_vec])

    def voxel_to_patient(self, i: float, j: float, k: float) -> np.ndarray:
        return self.origin + self.matrix() @ np.array([i, j, k], dtype=float)

    def patient_to_voxel(self, p: np.ndarray) -> np.ndarray:
        return np.linalg.solve(self.matrix(), np.asarray(p, dtype=float) - self.origin)

    @property
    def nbytes_mb(self) -> float:
        return self.data.nbytes / 1024 / 1024


def build_volume(frames: list[Frame], cache: FrameCache,
                 progress: Callable[[int, int], bool] | None = None, phase: int = 0) -> Volume:
    """Monta o volume a partir dos quadros já ordenados geometricamente.
    `progress(feitos, total)` pode devolver False para cancelar.
    `phase`: em série 4D (cardíaca, cine), qual fase usar em cada posição."""
    if phase:
        from ipe.imaging.cardiac import detect as _detect_4d
        info = _detect_4d(frames)
        if info is not None and info.is_4d:
            frames = info.phase_frames(frames, phase)
    if len(frames) < 3:
        raise VolumeError("MPR precisa de pelo menos 3 imagens na série.")
    if any(f.position is None or f.orientation is None for f in frames):
        raise VolumeError("A série não tem informação de posição (ImagePositionPatient).")
    ori = frames[0].orientation
    normal = np.cross(ori[:3], ori[3:])
    for f in frames:
        if not np.allclose(np.cross(f.orientation[:3], f.orientation[3:]), normal, atol=1e-3):
            raise VolumeError("Os cortes da série não são paralelos (ex.: localizador).")
    positions = np.array([f.position for f in frames], dtype=float)
    # remove posições repetidas (ex.: várias fases no mesmo corte): usa a primeira
    s = positions @ normal
    keep = np.concatenate([[True], np.diff(s) > 1e-3])
    if keep.sum() < len(frames):
        n_phases = len(frames) / keep.sum()
        frames = [f for f, k in zip(frames, keep) if k]
        positions = positions[keep]
        s = s[keep]
        warnings = [f"Cortes repetidos na mesma posição (≈{n_phases:.0f} fases/ecos); "
                    "usada a primeira de cada posição."]
    else:
        warnings = []
    if len(frames) < 3:
        raise VolumeError("Poucas posições diferentes para montar um volume.")

    gaps = np.diff(s)
    if gaps.max() - gaps.min() > 0.1 * max(abs(gaps.mean()), 1e-6):
        warnings.append(f"Espaçamento entre cortes irregular ({gaps.min():.2f}–{gaps.max():.2f} mm); "
                        "o MPR usa o espaçamento médio.")
    slice_vec = (positions[-1] - positions[0]) / (len(frames) - 1)
    if abs(np.dot(slice_vec / np.linalg.norm(slice_vec), normal)) < 0.995:
        warnings.append("Gantry inclinado: reconstruções levam em conta a inclinação.")

    first = cache.get(frames[0])
    if first.is_color:
        raise VolumeError("MPR de imagens coloridas ainda não é suportado.")
    h, w = first.pixels.shape
    rs, cs = first.pixel_spacing or (1.0, 1.0)
    data = None
    integral = True
    total = len(frames)
    for k, f in enumerate(frames):
        img = first if k == 0 else cache.get(f)
        if img.pixels.shape != (h, w):
            raise VolumeError("As imagens da série têm tamanhos diferentes.")
        px = img.pixels
        if data is None:
            data = np.empty((total, h, w), dtype=np.float32)
        data[k] = px
        if integral and not np.all(np.equal(np.mod(px[:: max(1, h // 64), :: max(1, w // 64)], 1), 0)):
            integral = False
        if progress and not progress(k + 1, total):
            raise VolumeError("Cancelado.")
    assert data is not None
    if integral and data.min() >= -32768 and data.max() <= 32767:
        data = data.astype(np.int16)        # metade da memória
    return Volume(data=data, origin=positions[0].copy(),
                  row_dir=np.asarray(ori[:3], float), col_dir=np.asarray(ori[3:], float),
                  slice_vec=slice_vec, dx=float(cs), dy=float(rs), window=first.window,
                  source_path=frames[0].path, warnings=warnings,
                  monochrome1=first.header.get("_monochrome1") == "1")


# ---------------------------------------------------------------------------

def alvos_da_tela(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Para onde a tela deve apontar neste plano: (direita, baixo), em coordenadas do paciente.

    Convenção de leitura, não do arquivo: axial com anterior em cima e esquerda do paciente à
    direita; coronal e sagital com superior em cima; sagital com posterior à direita. No DICOM
    x cresce para a esquerda do paciente, y para posterior e z para superior.
    """
    ax = int(np.argmax(np.abs(np.asarray(normal, float))))
    if ax == 2:                                   # axial
        return np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    if ax == 1:                                   # coronal
        return np.array([1.0, 0, 0]), np.array([0, 0, -1.0])
    return np.array([0, 1.0, 0]), np.array([0, 0, -1.0])      # sagital


def plane_name(normal: np.ndarray) -> str:
    ax = int(np.argmax(np.abs(normal)))
    return ("Sagital", "Coronal", "Axial")[ax]


class MPRPlane:
    """Uma direção de reconstrução do volume, vista como uma "série virtual"."""

    # eixo do volume que fica fixo e os dois que sobram, por plano. 0 = i (colunas do volume),
    # 1 = j (linhas), 2 = k (cortes).
    EIXOS = {0: (2, 1, 0), 1: (1, 2, 0), 2: (0, 2, 1)}      # plano -> (fixo, vertical, horizontal)

    def __init__(self, vol: Volume, axis: int, slab_mm: float = 0.0, mode: str = "avg",
                 cache_slices: int = 64):
        self.vol, self.axis = vol, axis
        self.slab_mm, self.mode = slab_mm, mode
        nz, ny, nx = vol.shape
        passos = {0: vol.row_dir * vol.dx, 1: vol.col_dir * vol.dy, 2: vol.slice_vec}
        tamanhos = {0: nx, 1: ny, 2: nz}
        fixo, v_idx, h_idx = self.EIXOS[axis]
        self.n = tamanhos[fixo]
        self.transposto = False
        if axis == 0:
            # Plano original: mostra como o equipamento gravou, sem girar nem espelhar.
            self.flip_v = self.flip_h = False
        else:
            # Reconstrução: a tela segue a convenção de leitura, não a ordem dos índices do
            # volume. Sem isto, uma série sagital reconstruída em axial saía **girada 90°**:
            # as linhas eram o eixo dos cortes (direita-esquerda) e as colunas, anterior-posterior.
            normal = np.cross(passos[h_idx], passos[v_idx])
            alvo_h, alvo_v = alvos_da_tela(normal)
            def _u(v):
                n = float(np.linalg.norm(v))
                return v / n if n else v
            if abs(float(_u(passos[h_idx]) @ alvo_h)) < abs(float(_u(passos[v_idx]) @ alvo_h)):
                v_idx, h_idx = h_idx, v_idx          # as linhas é que andam na horizontal: gira
                self.transposto = True
            self.flip_h = float(_u(passos[h_idx]) @ alvo_h) < 0
            self.flip_v = float(_u(passos[v_idx]) @ alvo_v) < 0
        self._fixo, self._v_idx, self._h_idx = fixo, v_idx, h_idx
        self._tam = tamanhos
        v_vec, h_vec = passos[v_idx], passos[h_idx]
        self._v_vec = -v_vec if self.flip_v else v_vec
        self._h_vec = -h_vec if self.flip_h else h_vec
        self.row_spacing = float(np.linalg.norm(v_vec))
        self.col_spacing = float(np.linalg.norm(h_vec))
        self.orientation = np.concatenate([self._h_vec / self.col_spacing,
                                           self._v_vec / self.row_spacing])
        self.normal = np.cross(self.orientation[:3], self.orientation[3:])
        self.name = plane_name(self.normal)
        self._cache: OrderedDict[tuple, FrameImage] = OrderedDict()
        self._cache_n = cache_slices

    # --------------------------------------------------------------------
    @property
    def step_mm(self) -> float:
        return {0: self.vol.dx, 1: self.vol.dy, 2: self.vol.dz}[self._fixo]

    def set_slab(self, slab_mm: float, mode: str) -> None:
        if (slab_mm, mode) != (self.slab_mm, self.mode):
            self.slab_mm, self.mode = slab_mm, mode
            self._cache.clear()

    def _extract(self, idx: int) -> np.ndarray:
        d = self.vol.data
        half = int(round(self.slab_mm / self.step_mm / 2)) if self.slab_mm > 0 else 0
        lo, hi = max(0, idx - half), min(self.n, idx + half + 1)
        sl = [slice(None)] * 3
        sl[self.axis] = slice(lo, hi)
        block = d[tuple(sl)]
        if hi - lo == 1:
            img = np.take(block, 0, axis=self.axis).astype(np.float32)
        elif self.mode == "mip":
            img = block.max(axis=self.axis).astype(np.float32)
        elif self.mode == "minip":
            img = block.min(axis=self.axis).astype(np.float32)
        else:
            img = block.mean(axis=self.axis, dtype=np.float32)
        # após remover o eixo fixo sobram os dois eixos do volume, nessa ordem; se a leitura pede
        # o contrário, transpõe antes de espelhar
        if self.transposto:
            img = img.T
        if self.flip_v:
            img = img[::-1, :]
        if self.flip_h:
            img = img[:, ::-1]
        return np.ascontiguousarray(img)

    def image(self, idx: int) -> FrameImage:
        key = (idx, self.slab_mm, self.mode)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        px = self._extract(idx)
        header = {"SliceThickness": str(max(self.slab_mm, self.step_mm))}
        if self.vol.monochrome1:
            header["_monochrome1"] = "1"
        img = FrameImage(px, False, self.vol.window, (self.row_spacing, self.col_spacing),
                         "PixelSpacing", "MONOCHROME2", header)
        self._cache[key] = img
        while len(self._cache) > self._cache_n:
            self._cache.popitem(last=False)
        return img

    def position(self, idx: int) -> np.ndarray:
        """Posição (mm) do pixel superior esquerdo do plano `idx`."""
        ijk = [0.0, 0.0, 0.0]          # (i, j, k)
        ijk[self._fixo] = idx
        if self.flip_v:
            ijk[self._v_idx] = self._tam[self._v_idx] - 1
        if self.flip_h:
            ijk[self._h_idx] = self._tam[self._h_idx] - 1
        return self.vol.voxel_to_patient(*ijk)

    def index_for_point(self, p: np.ndarray) -> int:
        ijk = self.vol.patient_to_voxel(p)
        comp = ijk[self._fixo]
        return int(np.clip(round(comp), 0, self.n - 1))

    def frames(self) -> list[Frame]:
        """Quadros virtuais: o viewport os trata como uma série comum."""
        out = []
        for k in range(self.n):
            out.append(Frame(path=self.vol.source_path, frame_index=k, sop_uid="", instance_number=k + 1,
                             position=self.position(k), orientation=self.orientation,
                             provider=self.image))
        return out


# ---------------------------------------------------------------------------
# MPR oblíquo

def sample_trilinear(data: np.ndarray, ijk: np.ndarray) -> np.ndarray:
    """Amostra `data[k, j, i]` nos pontos `ijk` (..., 3) com interpolação trilinear.
    Pontos fora do volume viram NaN."""
    nz, ny, nx = data.shape
    i, j, k = ijk[..., 0], ijk[..., 1], ijk[..., 2]
    inside = (i >= -0.5) & (i <= nx - 0.5) & (j >= -0.5) & (j <= ny - 0.5) & (k >= -0.5) & (k <= nz - 0.5)
    i = np.clip(i, 0, nx - 1)
    j = np.clip(j, 0, ny - 1)
    k = np.clip(k, 0, nz - 1)
    i0 = np.minimum(np.floor(i).astype(np.intp), max(nx - 2, 0))
    j0 = np.minimum(np.floor(j).astype(np.intp), max(ny - 2, 0))
    k0 = np.minimum(np.floor(k).astype(np.intp), max(nz - 2, 0))
    fi, fj, fk = (i - i0).astype(np.float32), (j - j0).astype(np.float32), (k - k0).astype(np.float32)
    i1, j1, k1 = np.minimum(i0 + 1, nx - 1), np.minimum(j0 + 1, ny - 1), np.minimum(k0 + 1, nz - 1)
    flat = data.reshape(-1)
    sj, sk = nx, nx * ny

    def g(kk, jj, ii):
        return flat[kk * sk + jj * sj + ii].astype(np.float32)
    c00 = g(k0, j0, i0) * (1 - fi) + g(k0, j0, i1) * fi
    c01 = g(k0, j1, i0) * (1 - fi) + g(k0, j1, i1) * fi
    c10 = g(k1, j0, i0) * (1 - fi) + g(k1, j0, i1) * fi
    c11 = g(k1, j1, i0) * (1 - fi) + g(k1, j1, i1) * fi
    c0 = c00 * (1 - fj) + c01 * fj
    c1 = c10 * (1 - fj) + c11 * fj
    out = c0 * (1 - fk) + c1 * fk
    out[~inside] = np.nan
    return out


class ObliquePlane(MPRPlane):
    """Plano oblíquo que contém a linha p0→p1 (desenhada num quadro) e a normal desse quadro.
    A rolagem move o plano ao longo da própria normal. Mesmo "contrato" do MPRPlane."""

    MAX_SIDE = 768

    def __init__(self, vol: Volume, p0, p1, source_normal, slab_mm: float = 0.0, mode: str = "avg",
                 cache_slices: int = 32):
        p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
        ns = np.asarray(source_normal, float)
        ns = ns / np.linalg.norm(ns)
        d = p1 - p0
        d = d - (d @ ns) * ns
        if np.linalg.norm(d) < 1e-3:
            raise VolumeError("Desenhe uma linha mais longa para o plano oblíquo.")
        d = d / np.linalg.norm(d)
        # o vetor "mais vertical" (cabeça-pés; senão ântero-posterior) fica na vertical da tela
        if max(abs(d[2]), abs(ns[2])) > 0.5:
            v, h = (d, ns) if abs(d[2]) >= abs(ns[2]) else (ns, d)
        else:
            v, h = (d, ns) if abs(d[1]) >= abs(ns[1]) else (ns, d)
        alvo_h, alvo_v = alvos_da_tela(np.cross(h, v))
        if float(v @ alvo_v) < 0:
            v = -v
        if float(h @ alvo_h) < 0:
            h = -h
        n = np.cross(h, v)
        self.line = (p0, p1)
        self._montar(vol, h, v, p0, slab_mm, mode, cache_slices)

    @classmethod
    def do_plano(cls, vol: Volume, h, v, ponto, slab_mm: float = 0.0, mode: str = "avg",
                 cache_slices: int = 32) -> "ObliquePlane":
        """Oblíquo que **é** o plano dado (mesma orientação, passando pelo ponto).

        É o que o usuário pediu ao escolher "oblíquo" no canto: a imagem não muda, só passa a
        poder girar. Sem isto, só dava para criar oblíquo desenhando uma linha — que já nasce
        perpendicular ao que estava na tela.
        """
        obj = cls.__new__(cls)
        h = np.asarray(h, float)
        v = np.asarray(v, float)
        h = h / max(np.linalg.norm(h), 1e-9)
        v = v - (v @ h) * h
        v = v / max(np.linalg.norm(v), 1e-9)
        obj.line = None
        obj._montar(vol, h, v, np.asarray(ponto, float), slab_mm, mode, cache_slices)
        return obj

    def girar(self, graus_h: float, graus_v: float, ponto=None) -> "ObliquePlane":
        """Gira o plano em torno dos eixos **da tela**, em volta do ponto que está sendo olhado.

        `graus_h`: gira em torno do eixo vertical da tela (vira para os lados).
        `graus_v`: gira em torno do eixo horizontal da tela (inclina).
        """
        h, v, n = self._h.copy(), self._v.copy(), self.normal.copy()
        for eixo, graus in ((v, graus_h), (h, graus_v)):
            a = np.radians(float(graus))
            if abs(a) < 1e-9:
                continue
            k = eixo / max(np.linalg.norm(eixo), 1e-9)

            def gira(x):                     # Rodrigues
                return x * np.cos(a) + np.cross(k, x) * np.sin(a) + k * (k @ x) * (1 - np.cos(a))
            h, v, n = gira(h), gira(v), gira(n)
        centro = np.asarray(ponto, float) if ponto is not None else self.p0
        return ObliquePlane.do_plano(self.vol, h, v, centro, self.slab_mm, self.mode, self._cache_n)

    def _montar(self, vol: Volume, h, v, p0, slab_mm: float, mode: str, cache_slices: int) -> None:
        n = np.cross(h, v)
        self.vol = vol
        self.slab_mm, self.mode = slab_mm, mode
        self.p0 = p0
        self._h, self._v, self.normal = h, v, n
        step = max(min(vol.dx, vol.dy, vol.dz), 0.25)
        self._step = step
        nz, ny, nx = vol.shape
        corners = np.array([vol.voxel_to_patient(i, j, k) for i in (-0.5, nx - 0.5)
                            for j in (-0.5, ny - 0.5) for k in (-0.5, nz - 0.5)]) - p0
        hs, vs, ds = corners @ h, corners @ v, corners @ n
        sp = max(step, (hs.max() - hs.min()) / self.MAX_SIDE, (vs.max() - vs.min()) / self.MAX_SIDE)
        self.col_spacing = self.row_spacing = float(sp)
        self._w = int(np.ceil((hs.max() - hs.min()) / sp)) + 1
        self._hgt = int(np.ceil((vs.max() - vs.min()) / sp)) + 1
        self._hmin, self._vmin = float(hs.min()), float(vs.min())
        self._nmin = float(ds.min())
        self.n = max(1, int(np.floor((ds.max() - ds.min()) / step)) + 1)
        self.idx0 = int(np.clip(round(-self._nmin / step), 0, self.n - 1))
        self.orientation = np.concatenate([h, v])
        self.name = "Oblíquo"
        self.axis = "o%06d" % (abs(hash((tuple(np.round(p0, 2)), tuple(np.round(h, 4)),
                                         tuple(np.round(v, 4))))) % 1_000_000)
        self.flip_v = self.flip_h = False
        minv = np.linalg.inv(vol.matrix())
        corner0 = p0 + self._hmin * h + self._vmin * v
        a = minv @ (corner0 - vol.origin)
        bc, br = minv @ (h * sp), minv @ (v * sp)
        self._bn = minv @ n
        rr, cc = np.mgrid[0:self._hgt, 0:self._w].astype(np.float32)
        self._base = (a.astype(np.float32) + cc[..., None] * bc.astype(np.float32)
                      + rr[..., None] * br.astype(np.float32))
        self._fill = float(vol.data.min())
        self._cache: OrderedDict[tuple, FrameImage] = OrderedDict()
        self._cache_n = cache_slices

    @property
    def step_mm(self) -> float:
        return self._step

    def _offset(self, idx: float) -> float:
        return self._nmin + idx * self._step

    def _slice_at(self, off: float) -> np.ndarray:
        return sample_trilinear(self.vol.data, self._base + (off * self._bn).astype(np.float32))

    def _extract(self, idx: int) -> np.ndarray:
        off = self._offset(idx)
        if self.slab_mm <= 0:
            img = self._slice_at(off)
        else:
            m = int(min(60, max(2, round(self.slab_mm / self._step))))
            offs = off + np.linspace(-self.slab_mm / 2, self.slab_mm / 2, m)
            stack = np.stack([self._slice_at(o) for o in offs])
            valid = ~np.isnan(stack)
            with np.errstate(all="ignore"):
                if self.mode == "mip":
                    img = np.fmax.reduce(stack, axis=0)
                elif self.mode == "minip":
                    img = np.fmin.reduce(stack, axis=0)
                else:
                    cnt = valid.sum(axis=0)
                    img = np.where(cnt > 0, np.nansum(stack, axis=0) / np.maximum(cnt, 1), np.nan)
        img = np.where(np.isnan(img), self._fill, img).astype(np.float32)
        return np.ascontiguousarray(img)

    def position(self, idx: int) -> np.ndarray:
        return self.p0 + self._offset(idx) * self.normal + self._hmin * self._h + self._vmin * self._v

    def index_for_point(self, p: np.ndarray) -> int:
        d = float((np.asarray(p, float) - self.p0) @ self.normal)
        return int(np.clip(round((d - self._nmin) / self._step), 0, self.n - 1))
