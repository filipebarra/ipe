"""Subtração digital (DSA) para angiografia: tirar o osso e deixar só o contraste.

A máscara é um quadro de antes do contraste; cada quadro seguinte é subtraído dela. Em
radiografia o que o detector mede é intensidade, e a atenuação é o **logaritmo** disso — por
isso a subtração logarítmica é a que limpa o osso de verdade. A linear fica como alternativa
para imagens que já vêm em unidades de atenuação.

Quando o paciente se mexe entre a máscara e o quadro, sobra o "fantasma" das bordas: o
deslocamento de pixel (pixel shift) empurra a máscara de volta para o lugar.
"""

from __future__ import annotations

import numpy as np

MODES = {"log": "Logarítmica (padrão)", "lin": "Linear (subtração simples)"}


def mask_pixels(frames_pixels: list[np.ndarray], n: int = 1) -> np.ndarray:
    """Máscara: a média dos `n` primeiros quadros (média tira ruído)."""
    if not frames_pixels:
        raise ValueError("Sem quadros para a máscara.")
    n = max(1, min(int(n), len(frames_pixels)))
    empilhado = np.stack([p.astype(np.float32) for p in frames_pixels[:n]], axis=0)
    return empilhado.mean(axis=0)


def shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Desloca a imagem repetindo as bordas (para casar a máscara com o quadro)."""
    dy, dx = int(dy), int(dx)
    if dy == 0 and dx == 0:
        return a
    h, w = a.shape[:2]
    ys = np.clip(np.arange(h) - dy, 0, h - 1)
    xs = np.clip(np.arange(w) - dx, 0, w - 1)
    return a[ys][:, xs]


def subtract(live: np.ndarray, mask: np.ndarray, mode: str = "log", dy: int = 0, dx: int = 0,
             gain: float = 1.0, invert: bool = False) -> np.ndarray:
    """Quadro menos máscara. Devolve float32 centrado em zero (vasos positivos)."""
    a = live.astype(np.float32)
    m = shift(mask.astype(np.float32), dy, dx)
    if m.shape != a.shape:
        raise ValueError("A máscara tem tamanho diferente do quadro.")
    if mode == "lin":
        out = m - a
    else:
        piso = float(min(a.min(), m.min()))
        desloc = 1.0 - piso if piso <= 0 else 1.0
        out = np.log(m + desloc) - np.log(a + desloc)
    out *= float(gain)
    return -out if invert else out


def auto_window(sub: np.ndarray, percentil: float = 99.0) -> tuple[float, float]:
    """Janela para a imagem subtraída: simétrica em torno de zero, pelos extremos reais."""
    if sub.size == 0:
        return 1.0, 0.0
    alto = float(np.percentile(np.abs(sub), percentil))
    if alto <= 0:
        alto = float(np.abs(sub).max()) or 1.0
    return max(alto * 2.0, 1e-6), 0.0
