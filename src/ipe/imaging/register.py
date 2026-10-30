"""Registro automático (translação 3D) entre dois volumes do mesmo paciente — ex.: exame atual ×
anterior — por correlação de fase sobre os volumes reamostrados numa grade comum (coordenadas do
paciente). Rápido (segundos) e sem bibliotecas extras; corrige posicionamento diferente da mesa/paciente.
Rotação e deformação não são corrigidas.
"""

from __future__ import annotations

import numpy as np

from ipe.imaging.volume import Volume


def _corners(vol: Volume) -> np.ndarray:
    nz, ny, nx = vol.shape
    pts = [vol.voxel_to_patient(i, j, k) for i in (0, nx - 1) for j in (0, ny - 1) for k in (0, nz - 1)]
    return np.array(pts)


def _normalize(vol: Volume) -> np.ndarray:
    d = vol.data[:: max(1, vol.shape[0] // 64), :: 4, :: 4].astype(np.float32)
    lo, hi = np.percentile(d, 2), np.percentile(d, 99.5)
    return lo, max(hi - lo, 1e-6)


def resample(vol: Volume, lo: np.ndarray, shape: tuple[int, int, int], step: float) -> np.ndarray:
    """Volume numa grade alinhada ao paciente (x, y, z), vizinho mais próximo; fora = 0."""
    nz, ny, nx = shape
    zs, ys, xs = np.meshgrid(np.arange(nz, dtype=np.float32), np.arange(ny, dtype=np.float32),
                             np.arange(nx, dtype=np.float32), indexing="ij")
    P = np.stack([lo[0] + xs * step, lo[1] + ys * step, lo[2] + zs * step], axis=-1).reshape(-1, 3)
    inv = np.linalg.inv(vol.matrix()).astype(np.float32)
    ijk = (P - vol.origin.astype(np.float32)) @ inv.T
    ijk = np.rint(ijk).astype(np.int32)
    vz, vy, vx = vol.shape
    ok = (ijk[:, 0] >= 0) & (ijk[:, 0] < vx) & (ijk[:, 1] >= 0) & (ijk[:, 1] < vy) & (ijk[:, 2] >= 0) & (ijk[:, 2] < vz)
    out = np.zeros(len(P), np.float32)
    sel = ijk[ok]
    base, scale = _normalize(vol)
    out[ok] = (vol.data[sel[:, 2], sel[:, 1], sel[:, 0]].astype(np.float32) - base) / scale
    np.clip(out, 0, 1, out=out)
    return out.reshape(shape)


def _parabola(a: float, b: float, c: float) -> float:
    d = a - 2 * b + c
    return 0.0 if abs(d) < 1e-12 else 0.5 * (a - c) / d


def register_translation(a: Volume, b: Volume, step: float = 4.0, max_side: int = 160) -> tuple[np.ndarray, float]:
    """Translação t (mm) tal que o ponto p de A corresponde a p + t em B; e a qualidade (0–1)."""
    ca, cb = _corners(a), _corners(b)
    lo = np.minimum(ca.min(0), cb.min(0))
    hi = np.maximum(ca.max(0), cb.max(0))
    ext = hi - lo
    step = max(step, float(ext.max()) / max_side)
    shape = tuple(int(np.ceil(e / step)) + 1 for e in ext[::-1])     # (z, y, x)
    va = resample(a, lo, shape, step)
    vb = resample(b, lo, shape, step)
    (dz, dy, dx), score = phase_shift(va - va.mean() * (va > 0), vb - vb.mean() * (vb > 0))
    return np.array([dx, dy, dz]) * step, max(0.0, min(1.0, score))


def phase_shift(va: np.ndarray, vb: np.ndarray) -> tuple[tuple[float, float, float], float]:
    """Deslocamento (dz, dy, dx) em voxels de B em relação a A (correlação de fase 3D com
    preenchimento de zeros e refinamento subvoxel) e a altura do pico."""
    shape = va.shape
    # preenche com zeros (metade de cada lado) para a correlação não "dar a volta" na grade
    pshape = tuple(n + n // 2 + 2 for n in shape)
    pa = np.zeros(pshape, np.float32)
    pb = np.zeros(pshape, np.float32)
    pa[: shape[0], : shape[1], : shape[2]] = va
    pb[: shape[0], : shape[1], : shape[2]] = vb
    fa, fb = np.fft.rfftn(pa), np.fft.rfftn(pb)
    R = fb * np.conj(fa)
    R /= np.abs(R) + 1e-9
    r = np.fft.irfftn(R, s=pshape, axes=(0, 1, 2))
    shape = pshape
    peak = np.unravel_index(int(np.argmax(r)), r.shape)
    score = float(r[peak])
    shift = []
    for ax, (pk, n) in enumerate(zip(peak, shape)):
        idx = [slice(None)] * 3
        vals = []
        for dlt in (-1, 0, 1):
            p = list(peak)
            p[ax] = (pk + dlt) % n
            vals.append(float(r[tuple(p)]))
        s = pk + _parabola(*vals)
        if s > n / 2:
            s -= n
        shift.append(s)
    return (shift[0], shift[1], shift[2]), score
