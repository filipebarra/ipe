"""Fusão (ex.: PET sobre TC): a série "de cima" vira um volume e é reamostrada no plano de
cada quadro (mesmas coordenadas do paciente), colorida e sobreposta com transparência."""

from __future__ import annotations

import numpy as np

from ipe.imaging import colormaps as CM
from ipe.imaging.volume import Volume, sample_trilinear


class Fusion:
    def __init__(self, vol: Volume, label: str, suv: float | None = None, cmap: str = "hot",
                 alpha: float = 0.5, hide_below: bool = True, series_uid: str = ""):
        self.vol, self.label, self.suv = vol, label, suv
        self.cmap, self.alpha, self.hide_below = cmap, alpha, hide_below
        self.series_uid = series_uid
        self.minv = np.linalg.inv(vol.matrix())
        sample = vol.data[:: max(1, vol.shape[0] // 48), ::2, ::2].astype(np.float32) * self.factor
        hi = float(np.percentile(sample, 99.7)) or float(sample.max()) or 1.0
        self.lo, self.hi = 0.08 * hi, hi
        self.version = 0

    @property
    def factor(self) -> float:
        return float(self.suv) if self.suv else 1.0

    @property
    def unit(self) -> str:
        return "SUV" if self.suv else ""

    def changed(self) -> None:
        self.version += 1

    def values(self, pos, row, col, rs: float, cs: float, h: int, w: int, max_side: int = 320):
        """Valores (unidade de exibição) numa grade reduzida sobre o plano; devolve (valores, passo)."""
        stride = max(1, int(np.ceil(max(h, w) / max_side)))
        hh, ww = int(np.ceil(h / stride)), int(np.ceil(w / stride))
        c = (np.arange(ww, dtype=np.float32) * stride + (stride - 1) / 2)
        r = (np.arange(hh, dtype=np.float32) * stride + (stride - 1) / 2)
        base = self.minv @ (np.asarray(pos, float) - self.vol.origin)
        bu = self.minv @ (np.asarray(row, float) * cs)
        bv = self.minv @ (np.asarray(col, float) * rs)
        ijk = (base.astype(np.float32) + c[None, :, None] * bu.astype(np.float32)
               + r[:, None, None] * bv.astype(np.float32))
        vals = sample_trilinear(self.vol.data, ijk) * self.factor
        return vals, stride

    def rgba(self, vals: np.ndarray) -> np.ndarray:
        t = np.clip((np.nan_to_num(vals, nan=self.lo - 1) - self.lo) / max(self.hi - self.lo, 1e-9), 0, 1)
        idx = (t * 255).astype(np.uint8)
        lut = CM.lut(self.cmap) if self.cmap in CM.COLORMAPS else np.repeat(np.arange(256, dtype=np.uint8)[:, None], 3, 1)
        out = np.empty(vals.shape + (4,), np.uint8)
        out[..., :3] = lut[idx]
        a = np.full(vals.shape, int(round(self.alpha * 255)), np.uint8)
        a[np.isnan(vals)] = 0
        if self.hide_below:
            a[~(vals > self.lo)] = 0
        out[..., 3] = a
        return out

    def value_at(self, p) -> float | None:
        ijk = self.minv @ (np.asarray(p, float) - self.vol.origin)
        v = sample_trilinear(self.vol.data, ijk.astype(np.float32)[None, :])[0]
        return None if np.isnan(v) else float(v) * self.factor
