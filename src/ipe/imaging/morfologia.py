"""Morfologia binária e suavização só com NumPy (0.100.7), para volumes `(cortes, linhas, colunas)`.

O programa não leva o SciPy (é grande, e o instalador já é grande): o que a análise da mama precisa — dilatar e
erodir no plano, distância no plano, preencher buracos, suavizar — cabe em deslocamentos de matriz. Tudo trabalha
**corte a corte** (no plano), que é o que a RM de cortes grossos pede, mas de uma vez em todos os cortes.
"""
from __future__ import annotations

import numpy as np


def _desloca(m: np.ndarray, dy: int, dx: int, fundo) -> np.ndarray:
    """`m` deslocada de (dy, dx) no plano; o que entra pela borda vale `fundo`."""
    out = np.full_like(m, fundo)
    h, w = m.shape[-2:]
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[..., yd, xd] = m[..., ys, xs]
    return out


_CRUZ = ((0, 1), (0, -1), (1, 0), (-1, 0))
_QUADRADO = _CRUZ + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def dilatar(m: np.ndarray, vezes: int = 1, quadrado: bool = True) -> np.ndarray:
    m = np.asarray(m, bool)
    viz = _QUADRADO if quadrado else _CRUZ
    for _ in range(int(vezes)):
        out = m.copy()
        for dy, dx in viz:
            out |= _desloca(m, dy, dx, False)
        m = out
    return m


def erodir(m: np.ndarray, vezes: int = 1, quadrado: bool = True) -> np.ndarray:
    """Como a do SciPy com borda 0: o que encosta na borda da imagem também erode."""
    m = np.asarray(m, bool)
    viz = _QUADRADO if quadrado else _CRUZ
    for _ in range(int(vezes)):
        out = m.copy()
        for dy, dx in viz:
            out &= _desloca(m, dy, dx, False)
        m = out
    return m


def abrir(m: np.ndarray, quadrado: bool = False) -> np.ndarray:
    return dilatar(erodir(m, 1, quadrado), 1, quadrado)


def distancia(alvo: np.ndarray, pixel_mm=(1.0, 1.0), maximo: float = 50.0) -> np.ndarray:
    """Distância (mm) no plano de cada voxel ao conjunto `alvo` (0 nele), por chanfro, limitada a `maximo`.
    `pixel_mm` = (linha, coluna). Cortes sem alvo ficam em `maximo`."""
    sy, sx = (float(v) for v in pixel_mm)
    alvo = np.asarray(alvo, bool)
    # longe do alvo tudo vale `maximo`: a conta fica na caixa do alvo com a folga de `maximo`
    js, is_ = np.flatnonzero(alvo.any(axis=(0, 2))), np.flatnonzero(alvo.any(axis=(0, 1)))
    if not js.size:
        return np.full(alvo.shape, np.float32(maximo))
    folga = int(np.ceil(maximo / min(sx, sy))) + 1
    j0, j1 = max(0, js[0] - folga), min(alvo.shape[-2], js[-1] + folga + 1)
    i0, i1 = max(0, is_[0] - folga), min(alvo.shape[-1], is_[-1] + folga + 1)
    if (j1 - j0) * (i1 - i0) < 0.9 * alvo.shape[-2] * alvo.shape[-1]:
        out = np.full(alvo.shape, np.float32(maximo))
        out[..., j0:j1, i0:i1] = distancia(alvo[..., j0:j1, i0:i1], pixel_mm, maximo)
        return out
    sd = float(np.hypot(sx, sy))
    passos = ((0, 1, sx), (0, -1, sx), (1, 0, sy), (-1, 0, sy), (1, 1, sd), (1, -1, sd), (-1, 1, sd), (-1, -1, sd))
    d = np.where(np.asarray(alvo, bool), 0.0, np.inf).astype(np.float32)
    for _ in range(int(maximo / min(sx, sy)) + 2):
        novo = d.copy()
        for dy, dx, c in passos:
            np.minimum(novo, _desloca(d, dy, dx, np.inf) + np.float32(c), out=novo)
        if np.array_equal(novo, d):
            break
        d = novo
    return np.minimum(d, np.float32(maximo))


def preencher_buracos(m: np.ndarray) -> np.ndarray:
    """Em cada corte, o fundo que não chega à borda da imagem (pelos 4 vizinhos) vira parte da máscara."""
    from ipe.imaging.estruturas import rotular
    m = np.asarray(m, bool)
    out = m.copy()
    for k in range(m.shape[0]):
        livre = ~m[k]
        rot, n = rotular(livre)
        if not n:
            continue
        borda = np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]]))
        out[k] |= livre & ~np.isin(rot, borda)
    return out


def _caixa(a: np.ndarray, r: int, eixo: int) -> np.ndarray:
    """Soma numa janela de 2r+1 ao longo de `eixo` (fora da borda conta zero)."""
    if r <= 0:
        return a
    a = np.moveaxis(a, eixo, -1)
    pad = [(0, 0)] * (a.ndim - 1) + [(r + 1, r)]
    c = np.cumsum(np.pad(a, pad), axis=-1, dtype=np.float64)
    out = (c[..., 2 * r + 1:] - c[..., :-(2 * r + 1)]).astype(np.float32)
    return np.moveaxis(out, -1, eixo)


def suavizar(a: np.ndarray, sigma_px: tuple) -> np.ndarray:
    """Aproxima a gaussiana por três médias móveis em cada eixo (com zero fora da borda: use em convolução
    normalizada, dividindo pela suavização do peso)."""
    out = np.asarray(a, np.float32)
    for eixo, s in enumerate(sigma_px):
        # três caixas de largura w têm variância 3·(w²−1)/12 = σ²
        r = int(round((np.sqrt(4.0 * float(s) ** 2 + 1.0) - 1.0) / 2.0))
        for _ in range(3):
            out = _caixa(out, r, eixo) / float(2 * r + 1)
    return out


def suavizar_reduzido(a: np.ndarray, sigma_px: tuple, fator: int = 4) -> np.ndarray:
    """`suavizar` para campos lisos (σ de dezenas de pixels): faz a conta numa grade `fator` vezes menor no plano
    (média em blocos) e volta por repetição. O campo da bobina não tem detalhe abaixo de alguns milímetros."""
    a = np.asarray(a, np.float32)
    nz, ny, nx = a.shape
    f = int(fator)
    if f <= 1 or min(ny, nx) < 4 * f:
        return suavizar(a, sigma_px)
    py, px = (-ny) % f, (-nx) % f
    b = np.pad(a, ((0, 0), (0, py), (0, px)))
    b = b.reshape(nz, b.shape[1] // f, f, b.shape[2] // f, f).mean(axis=(2, 4))
    b = suavizar(b, (sigma_px[0], sigma_px[1] / f, sigma_px[2] / f))
    return np.repeat(np.repeat(b, f, axis=1), f, axis=2)[:, :ny, :nx]
