"""Filtros de imagem: nitidez (máscara de desfoque) e suavização.

Tudo em numpy, com somas acumuladas — sem scipy. O filtro é aplicado nos valores da imagem,
antes da janela, para o resultado não depender do brilho da tela; o que sai no filme, no PDF e
na exportação é a mesma imagem filtrada que você vê.
"""

from __future__ import annotations

import numpy as np

# nome interno -> (rótulo, tipo, força)
FILTERS: dict[str, tuple[str, str, float]] = {
    "": ("Sem filtro", "", 0.0),
    "sharp1": ("Nitidez leve", "sharp", 0.6),
    "sharp2": ("Nitidez média", "sharp", 1.2),
    "sharp3": ("Nitidez forte", "sharp", 2.0),
    "smooth1": ("Suavizar leve", "smooth", 1.0),
    "smooth2": ("Suavizar médio", "smooth", 2.0),
}
ORDER = ["", "sharp1", "sharp2", "sharp3", "smooth1", "smooth2"]


def label(name: str) -> str:
    return FILTERS.get(name, FILTERS[""])[0]


def _box(a: np.ndarray, r: int) -> np.ndarray:
    """Média em janela (2r+1)², por somas acumuladas, com as bordas repetidas."""
    if r < 1:
        return a
    pad = np.pad(a.astype(np.float32), r + 1, mode="edge")
    soma = pad.cumsum(axis=0).cumsum(axis=1)
    soma = np.pad(soma, ((1, 0), (1, 0)))
    k = 2 * r + 1
    h, w = a.shape
    y0, x0 = np.arange(h)[:, None], np.arange(w)[None, :]
    total = (soma[y0 + k, x0 + k] - soma[y0, x0 + k] - soma[y0 + k, x0] + soma[y0, x0])
    return total / float(k * k)


def blur(a: np.ndarray, raio: float = 1.0) -> np.ndarray:
    """Desfoque gaussiano aproximado: duas passadas de média em janela (bem mais rápido)."""
    r = max(1, int(round(raio)))
    return _box(_box(a, r), r)


def apply(pixels: np.ndarray, name: str) -> np.ndarray:
    """Devolve a imagem filtrada (ou a mesma, quando não há filtro)."""
    cfg = FILTERS.get(name)
    if not cfg or not cfg[1]:
        return pixels
    _rotulo, tipo, forca = cfg
    if pixels.ndim == 3:                       # colorida: filtra cada canal
        saida = np.stack([apply(pixels[..., c], name) for c in range(pixels.shape[2])], axis=-1)
        return saida.astype(pixels.dtype)
    a = pixels.astype(np.float32)
    if tipo == "smooth":
        out = blur(a, forca)
    else:
        suave = blur(a, 1.0 if forca <= 1.2 else 2.0)
        out = a + forca * (a - suave)          # máscara de desfoque
    if np.issubdtype(pixels.dtype, np.integer):
        info = np.iinfo(pixels.dtype)
        return np.clip(out, info.min, info.max).astype(pixels.dtype)
    return out.astype(pixels.dtype)
