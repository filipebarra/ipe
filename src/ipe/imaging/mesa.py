"""Tirar a mesa da TC no MPR e no 3D (0.99.31, onda A5 — ideia da Eden).

Na reconstrução 3D e no MIP a mesa aparece como uma placa embaixo do paciente e atrapalha (no 3D de
osso, ela é o primeiro objeto da cena). Aqui, só com numpy:

1. num volume reduzido (≈4 mm), o que tem mais de −400 HU é "coisa";
2. o corpo é a coisa conectada que passa pelo meio do volume (a mesa fica separada por ar/colchão);
3. em cada corte, tudo o que o ar de fora alcança a partir da borda é fora do corpo — assim os pulmões
   e as vias aéreas, cercados pelo corpo, ficam;
4. o que é fora do corpo vira ar (−1000 HU) no volume em tamanho original.

A série original não muda: é só o volume montado para o MPR e o 3D.
"""
from __future__ import annotations

import numpy as np

LIMIAR_HU = -400.0
AR_HU = -1000


def _reduzir(m: np.ndarray, f: tuple[int, int, int]) -> np.ndarray:
    fz, fy, fx = f
    nz, ny, nx = (m.shape[0] // fz) * fz, (m.shape[1] // fy) * fy, (m.shape[2] // fx) * fx
    if min(nz, ny, nx) == 0:
        return m.copy()
    r = m[:nz, :ny, :nx].reshape(nz // fz, fz, ny // fy, fy, nx // fx, fx)
    return r.any(axis=(1, 3, 5))


def _crescer(dentro: np.ndarray, semente: np.ndarray, em_z: bool = True, max_iter: int = 2000) -> np.ndarray:
    """Região conectada (6 vizinhos; sem z quando `em_z` é falso) de `dentro` a partir das sementes."""
    reg = semente & dentro
    for _ in range(max_iter):
        g = reg.copy()
        if em_z:
            g[1:] |= reg[:-1]
            g[:-1] |= reg[1:]
        g[:, 1:] |= reg[:, :-1]
        g[:, :-1] |= reg[:, 1:]
        g[:, :, 1:] |= reg[:, :, :-1]
        g[:, :, :-1] |= reg[:, :, 1:]
        g &= dentro
        if np.array_equal(g, reg):
            break
        reg = g
    return reg


def _dilatar(m: np.ndarray, r: int = 1) -> np.ndarray:
    out = m.copy()
    for _ in range(r):
        g = out.copy()
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        g[:, :, 1:] |= out[:, :, :-1]
        g[:, :, :-1] |= out[:, :, 1:]
        out = g
    return out


def mascara_do_corpo(data: np.ndarray, dx: float = 1.0, dy: float = 1.0, dz: float = 1.0) -> np.ndarray | None:
    """Máscara (mesmo tamanho de `data`) do corpo com o que ele cerca. None quando não acha o corpo."""
    if data.ndim != 3 or data.size == 0:
        return None
    f = (max(1, int(round(4.0 / max(dz, 0.1)))), max(1, int(round(4.0 / max(dy, 0.1)))),
         max(1, int(round(4.0 / max(dx, 0.1)))))
    coisa = _reduzir(data > LIMIAR_HU, f)
    if not coisa.any():
        return None
    nz, ny, nx = coisa.shape
    # semente: a "coisa" mais perto do centro do volume (no corte do meio; se vazio, nos vizinhos)
    semente = np.zeros_like(coisa)
    for k in [nz // 2] + [nz // 2 + d * s for d in range(1, nz) for s in (1, -1)]:
        if not 0 <= k < nz:
            continue
        ys, xs = np.nonzero(coisa[k])
        if ys.size:
            i = int(np.argmin((ys - ny / 2) ** 2 + (xs - nx / 2) ** 2))
            semente[k, ys[i], xs[i]] = True
            break
    corpo = _crescer(coisa, semente)
    if corpo.sum() < 0.02 * coisa.size and corpo.sum() < 0.3 * coisa.sum():
        return None                                     # não achou um corpo de verdade: não mexe
    corpo = _dilatar(corpo, 1)
    borda = np.zeros_like(corpo)
    borda[:, 0, :] = borda[:, -1, :] = True
    borda[:, :, 0] = borda[:, :, -1] = True
    fora = _crescer(~corpo, borda, em_z=False)          # o ar de fora, corte a corte
    dentro = ~fora
    # volta ao tamanho original
    full = np.repeat(np.repeat(np.repeat(dentro, f[0], 0), f[1], 1), f[2], 2)
    out = np.zeros(data.shape, dtype=bool)
    sz, sy, sx = min(full.shape[0], data.shape[0]), min(full.shape[1], data.shape[1]), min(full.shape[2], data.shape[2])
    out[:sz, :sy, :sx] = full[:sz, :sy, :sx]
    if sz < data.shape[0]:
        out[sz:] = out[sz - 1:sz] if sz else True
    if sy < data.shape[1]:
        out[:, sy:] = out[:, sy - 1:sy] if sy else True
    if sx < data.shape[2]:
        out[:, :, sx:] = out[:, :, sx - 1:sx] if sx else True
    return out


def tirar_a_mesa(data: np.ndarray, dx: float = 1.0, dy: float = 1.0, dz: float = 1.0) -> tuple[np.ndarray, bool]:
    """(volume sem a mesa, se mexeu). O volume original não é alterado."""
    m = mascara_do_corpo(data, dx, dy, dz)
    if m is None:
        return data, False
    out = data.copy()
    out[~m] = AR_HU if np.issubdtype(out.dtype, np.integer) or out.dtype.kind == "f" else out.min()
    return out, True
