"""MPR curvo ("esticado"): corte ao longo de um caminho 3D (ex.: aorta, coronária, ureter, ducto
pancreático). Linhas da imagem = posição ao longo do caminho; colunas = afastamento lateral.
A "rolagem" gira o plano de corte em torno do caminho (0–180°)."""

from __future__ import annotations

from collections import OrderedDict

import numpy as np

from ipe.imaging.series import Frame, FrameImage
from ipe.imaging.volume import Volume, VolumeError, sample_trilinear


def smooth_path(points: np.ndarray, step: float) -> np.ndarray:
    """Catmull-Rom pelos pontos clicados, reamostrado a cada `step` mm."""
    pts = np.asarray(points, float)
    keep = [0]
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - pts[keep[-1]]) > 0.5:
            keep.append(i)
    pts = pts[keep]
    if len(pts) < 2:
        raise VolumeError("Marque pelo menos 2 pontos diferentes para o MPR curvo.")
    ext = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
    dense = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        n = max(2, int(np.linalg.norm(p2 - p1) / max(step / 4, 0.05)))
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                            + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    dense.append(pts[-1][None, :])
    dense = np.vstack(dense)
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    total = s[-1]
    si = np.arange(0, total + 1e-6, step)
    return np.stack([np.interp(si, s, dense[:, c]) for c in range(3)], axis=1)


class CurvedPlane:
    supports_slab = False

    def __init__(self, vol: Volume, points, view_normal, width_mm: float = 80.0, angles: int = 36,
                 cache_slices: int = 12):
        self.vol = vol
        self.step = max(min(vol.dx, vol.dy, vol.dz), 0.3)
        self.path = smooth_path(points, self.step)
        self.points = np.asarray(points, float)
        up = np.asarray(view_normal, float)
        up = up / np.linalg.norm(up)
        tang = np.gradient(self.path, axis=0)
        tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
        # referência lateral: perpendicular ao caminho, no plano de onde os pontos foram marcados
        normals = []
        prev = None
        for t in tang:
            n = np.cross(t, up)
            if np.linalg.norm(n) < 1e-3:
                n = prev if prev is not None else np.cross(t, [1.0, 0, 0])
            n = n / np.linalg.norm(n)
            if prev is not None and n @ prev < 0:
                n = -n
            normals.append(n)
            prev = n
        self.tangents = tang
        self.normals = np.array(normals)
        self.binormals = np.cross(self.tangents, self.normals)
        self.n = angles
        self.angles = np.arange(angles) * 180.0 / angles
        self.cols = int(width_mm / self.step) | 1
        self.row_spacing = self.col_spacing = self.step
        self.name = "MPR curvo"
        self.label = "MPR curvo"
        self.axis = f"cpr-{abs(hash(self.points.round(2).tobytes())) % 1_000_000}"
        self.image_type = ["DERIVED", "SECONDARY", "MPR", "CURVED"]
        self.slab_mm, self.mode = 0.0, "avg"
        self.step_mm = 180.0 / angles
        self.minv = np.linalg.inv(vol.matrix())
        self.orientation = np.concatenate([self.normals[0], self.tangents[0]])
        self._cache: OrderedDict[int, FrameImage] = OrderedDict()
        self._cache_n = cache_slices

    def set_slab(self, *_a) -> None:
        pass

    def lateral(self, idx: int) -> np.ndarray:
        a = np.radians(self.angles[idx])
        return np.cos(a) * self.normals + np.sin(a) * self.binormals

    def image(self, idx: int) -> FrameImage:
        if idx in self._cache:
            self._cache.move_to_end(idx)
            return self._cache[idx]
        lat = self.lateral(idx)
        offs = (np.arange(self.cols) - self.cols // 2) * self.step
        P = self.path[:, None, :] + offs[None, :, None] * lat[:, None, :]
        ijk = ((P - self.vol.origin) @ self.minv.T).astype(np.float32)
        px = sample_trilinear(self.vol.data, ijk)
        px = np.where(np.isnan(px), float(self.vol.data.min()), px).astype(np.float32)
        header = {"SliceThickness": f"{self.step:.2f}"}
        if self.vol.monochrome1:
            header["_monochrome1"] = "1"
        img = FrameImage(px, False, self.vol.window, (self.step, self.step), "PixelSpacing", "MONOCHROME2", header)
        self._cache[idx] = img
        while len(self._cache) > self._cache_n:
            self._cache.popitem(last=False)
        return img

    def position(self, idx: int) -> np.ndarray:
        return self.path[0] - (self.cols // 2) * self.step * self.lateral(idx)[0]

    def index_for_point(self, _p) -> int:
        return 0

    @property
    def length_mm(self) -> float:
        return float(np.linalg.norm(np.diff(self.path, axis=0), axis=1).sum())

    def frames(self) -> list[Frame]:
        # sem posição/orientação: o corte não é plano (sem linhas de referência nem sincronização)
        return [Frame(path=self.vol.source_path, frame_index=k, sop_uid="", instance_number=k + 1,
                      provider=self.image) for k in range(self.n)]
