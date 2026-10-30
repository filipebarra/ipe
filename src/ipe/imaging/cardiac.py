"""Exames com fases no tempo (cardíaco 4D, cine de RM, eco).

Uma série 4D tem os mesmos cortes repetidos em várias fases do ciclo. Descobrimos isso pela
**posição**: se cada posição aparece o mesmo número de vezes, aquilo são fases — não precisa
de tag nenhuma além da que toda imagem tem.

Com isso dá para rolar os cortes dentro de uma fase, tocar o ciclo parado num corte, comparar
duas fases lado a lado e montar o volume de uma fase escolhida (MPR/3D).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Cardiac:
    """Como a série está organizada: quantos cortes, quantas fases e em que ordem."""
    n_slices: int
    n_phases: int
    order: str                       # "phase_major" (fases juntas) | "slice_major"
    index: list[list[int]] = field(default_factory=list)   # index[corte][fase] = quadro

    @property
    def is_4d(self) -> bool:
        return self.n_phases > 1 and self.n_slices >= 1

    def frame_index(self, slice_i: int, phase: int) -> int:
        s = max(0, min(int(slice_i), self.n_slices - 1))
        p = max(0, min(int(phase), self.n_phases - 1))
        return self.index[s][p]

    def where(self, frame_index: int) -> tuple[int, int]:
        """(corte, fase) de um quadro."""
        for s, linha in enumerate(self.index):
            for p, k in enumerate(linha):
                if k == frame_index:
                    return s, p
        return 0, 0

    def phase_frames(self, frames: list, phase: int) -> list:
        """Os quadros de uma fase, na ordem dos cortes (é o volume daquele instante)."""
        p = max(0, min(int(phase), self.n_phases - 1))
        return [frames[linha[p]] for linha in self.index]

    def summary(self) -> str:
        return f"{self.n_slices} corte(s) × {self.n_phases} fases"


def _position_key(f) -> tuple | None:
    pos = getattr(f, "position", None)
    if pos is None:
        loc = getattr(f, "slice_location", None)
        return (round(float(loc), 2),) if loc is not None else None
    return tuple(round(float(v), 2) for v in pos)


def detect(frames: list) -> Cardiac | None:
    """Descobre cortes × fases pela repetição das posições. None = série comum."""
    if not frames or len(frames) < 4:
        return None
    grupos: dict[tuple, list[int]] = {}
    ordem: list[tuple] = []
    for i, f in enumerate(frames):
        chave = _position_key(f)
        if chave is None:
            return None
        if chave not in grupos:
            grupos[chave] = []
            ordem.append(chave)
        grupos[chave].append(i)
    tamanhos = {len(v) for v in grupos.values()}
    if len(tamanhos) != 1:
        return None                       # posições com contagens diferentes: não é 4D regular
    n_phases = tamanhos.pop()
    n_slices = len(ordem)
    if n_phases < 2 or n_slices < 1:
        return None
    index = [sorted(grupos[c]) for c in ordem]
    # fases juntas = os quadros da mesma posição são vizinhos
    juntas = all(linha[-1] - linha[0] == n_phases - 1 for linha in index)
    return Cardiac(n_slices=n_slices, n_phases=n_phases,
                   order="phase_major" if juntas else "slice_major", index=index)


def phase_times(frames: list, info: Cardiac) -> list[float]:
    """Instante de cada fase (ms), quando o aparelho informa; senão, fases numeradas."""
    tempos = []
    for p in range(info.n_phases):
        f = frames[info.frame_index(0, p)]
        t = getattr(f, "trigger_time", None) or getattr(f, "acquisition_time", None)
        try:
            tempos.append(float(t))
        except (TypeError, ValueError):
            tempos.append(float(p))
    return tempos


def phase_label(info: Cardiac, phase: int) -> str:
    return f"Fase {int(phase) + 1}/{info.n_phases}"


def volume_frames(frames: list, phase: int = 0) -> list:
    """Quadros de uma fase, para montar o volume; série comum devolve tudo."""
    info = detect(frames)
    if info is None or not info.is_4d:
        return frames
    return info.phase_frames(frames, phase)


def mean_phase(pixels: list[np.ndarray]) -> np.ndarray:
    """Média das fases de um corte — útil para ver o que não se mexe."""
    return np.stack([p.astype(np.float32) for p in pixels], axis=0).mean(axis=0)
