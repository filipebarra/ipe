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
        # 0.99.44 (MITK): conferir o registro — a matriz A→B do registro rígido e o modo de mostrar
        self.matriz: np.ndarray | None = None
        self.matriz_de = None                  # (exame A, exame B) quando é uma conferência de registro
        self.modo = "cor"                      # cor | mistura | xadrez | cortina | diferenca
        self.casas = 8                         # xadrez: casas no lado maior
        self.cortina = 0.5                     # cortina: fração da largura (segue o mouse)
        self.b_lo, self.b_hi = (float(x) for x in np.percentile(sample, [1, 99.5]))
        if self.b_hi <= self.b_lo:
            self.b_hi = self.b_lo + 1.0

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
        pos, row, col = (np.asarray(v, float) for v in (pos, row, col))
        if self.matriz is not None:            # o ponto de A no outro exame: p_B = R·p_A + t
            R = self.matriz[:3, :3]
            pos, row, col = R @ pos + self.matriz[:3, 3], R @ row, R @ col
        base = self.minv @ (pos - self.vol.origin)
        bu = self.minv @ (row * cs)
        bv = self.minv @ (col * rs)
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

    MODOS_DE_CONFERIR = ("mistura", "xadrez", "cortina", "diferenca")

    def cinza(self, vals: np.ndarray) -> np.ndarray:
        """B em tons de cinza (0–255) pela janela dele (percentis 1 e 99,5)."""
        t = np.clip((np.nan_to_num(vals, nan=self.b_lo) - self.b_lo) / (self.b_hi - self.b_lo), 0, 1)
        return (t * 255).astype(np.uint8)

    def conferir(self, vals: np.ndarray, a8: np.ndarray | None) -> np.ndarray:
        """RGBA dos modos de conferir o registro. `a8`: A na tela (0–255) na mesma grade (diferença)."""
        b8 = self.cinza(vals)
        hh, ww = b8.shape
        out = np.empty((hh, ww, 4), np.uint8)
        out[..., 0] = out[..., 1] = out[..., 2] = b8
        alpha = np.zeros((hh, ww), np.uint8)
        if self.modo == "mistura":
            alpha[:] = 128
        elif self.modo == "xadrez":
            lado = max(2, int(np.ceil(max(hh, ww) / max(2, self.casas))))
            yy, xx = np.mgrid[0:hh, 0:ww]
            alpha[((yy // lado) + (xx // lado)) % 2 == 1] = 255
        elif self.modo == "cortina":
            alpha[:, int(round(np.clip(self.cortina, 0, 1) * ww)):] = 255
        elif self.modo == "diferenca":
            if a8 is not None and a8.shape == b8.shape:
                d = np.abs(a8.astype(np.int16) - b8.astype(np.int16)).astype(np.uint8)
                out[..., 0] = out[..., 1] = out[..., 2] = d
            alpha[:] = 255
        alpha[np.isnan(vals)] = 0
        out[..., 3] = alpha
        return out

    def value_at(self, p) -> float | None:
        p = np.asarray(p, float)
        if self.matriz is not None:
            p = self.matriz[:3, :3] @ p + self.matriz[:3, 3]
        ijk = self.minv @ (p - self.vol.origin)
        v = sample_trilinear(self.vol.data, ijk.astype(np.float32)[None, :])[0]
        return None if np.isnan(v) else float(v) * self.factor
