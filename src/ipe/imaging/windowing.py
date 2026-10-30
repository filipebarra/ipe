"""Janela/nível, orientação anatômica e miniaturas (sem depender de Qt)."""

from __future__ import annotations

import struct
import zlib

import numpy as np

from ipe.imaging.series import FrameImage


def auto_window(px: np.ndarray) -> tuple[float, float]:
    """Janela automática pelos percentis 1–99 (ignora fundo extremo)."""
    sample = px[:: max(1, px.shape[0] // 256), :: max(1, px.shape[1] // 256)]
    lo, hi = np.percentile(sample, [1, 99])
    if hi <= lo:
        lo, hi = float(sample.min()), float(sample.max()) + 1
    return float(hi - lo), float((hi + lo) / 2)


def tissue_window(px: np.ndarray, monochrome1: bool = False) -> tuple[float, float]:
    """Janela automática de mamografia/tomossíntese: percentis só do tecido (sem o fundo preto nem
    letreiros), para a mama não ficar “lavada”."""
    sample = px[:: max(1, px.shape[0] // 512), :: max(1, px.shape[1] // 512)].astype(np.float32)
    dv = -sample if monochrome1 else sample
    lo, hi = np.percentile(dv, [1, 99.8])
    if hi <= lo:
        return auto_window(px)
    tissue = dv > lo + 0.08 * (hi - lo)
    if tissue.sum() < 0.02 * dv.size:
        return auto_window(px)
    vals = sample[tissue]
    a, b = np.percentile(vals, [0.5, 99.7])
    if b <= a:
        return auto_window(px)
    # uma folga embaixo para a pele/gordura não saturar
    a -= 0.05 * (b - a)
    return float(b - a), float((a + b) / 2)


def apply_window(px: np.ndarray, width: float, level: float,
                 invert: bool = False, function: str = "") -> np.ndarray:
    """Converte pixels reais em 8 bits para exibição (fórmula DICOM linear ou sigmoide)."""
    width = max(width, 1.0)
    if function == "SIGMOID":
        out = 255.0 / (1.0 + np.exp(-4.0 * (px.astype(np.float32) - level) / width))
    else:
        lo = level - width / 2.0
        out = (px - lo) * (255.0 / width)
    np.clip(out, 0, 255, out=out)
    out = out.astype(np.uint8)
    if invert:
        out = 255 - out
    return out


def to_display(img: FrameImage, width: float, level: float, invert: bool = False,
               cmap: str | None = None) -> np.ndarray:
    """8 bits para exibir. `cmap`: tabela de cores (imaging.colormaps) aplicada após a janela."""
    if img.is_color:
        return 255 - img.pixels if invert else img.pixels
    mono1 = img.header.get("_monochrome1") == "1"
    out = apply_window(img.pixels, width, level, invert != mono1, img.header.get("_voi_function", ""))
    if cmap:
        from ipe.imaging.colormaps import apply
        out = apply(out, cmap)
    return out


# ------------------------------------------------------------ orientação

def _axis_letter(v: np.ndarray) -> str:
    """Letras (paciente LPS) para a direção de um vetor, ex.: 'L', 'AS'."""
    letters = ""
    pos = ("L", "P", "S")
    neg = ("R", "A", "I")
    order = np.argsort(-np.abs(v))
    for idx in order:
        if abs(v[idx]) < 0.25:
            break
        letters += pos[idx] if v[idx] > 0 else neg[idx]
        if len(letters) == 2:
            break
    return letters


def orientation_labels(orientation: np.ndarray | None) -> dict[str, str]:
    """Rótulos das bordas: {'left','right','top','bottom'}."""
    if orientation is None or len(orientation) != 6:
        return {}
    row = np.asarray(orientation[:3], dtype=float)   # direção ao longo da linha (->)
    col = np.asarray(orientation[3:], dtype=float)   # direção ao longo da coluna (v)
    return {
        "right": _axis_letter(row), "left": _axis_letter(-row),
        "bottom": _axis_letter(col), "top": _axis_letter(-col),
    }


# ------------------------------------------------------------ miniaturas

def make_thumbnail(img: FrameImage, size: int = 96) -> bytes:
    if img.is_color:
        disp = img.pixels
    else:
        w, l = img.window or auto_window(img.pixels)
        disp = to_display(img, w, l)
    h, w_ = disp.shape[:2]
    step = max(1, int(np.ceil(max(h, w_) / size)))
    small = disp[::step, ::step]
    return encode_png(small)


def encode_png(arr: np.ndarray) -> bytes:
    """PNG mínimo (tons de cinza ou RGB 8 bits) sem dependências externas."""
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 2:
        color_type, channels = 0, 1
    else:
        color_type, channels = 2, 3
        arr = arr[..., :3]
    h, w = arr.shape[:2]
    raw = b"".join(b"\x00" + arr[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    del channels
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
