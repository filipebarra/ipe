"""Calibração de ultrassom pelas regiões gravadas no próprio arquivo (0018,6011).

No ultrassom não existe `PixelSpacing`: a escala muda de imagem para imagem, porque o médico
mexe na profundidade e no zoom durante o exame — na mesma série deste acervo há imagem com
0,047 mm/pixel e imagem com 0,153 mm/pixel. Calibrar a série toda por uma imagem erraria por
três vezes. Por isso a calibração é **por imagem**.

O aparelho grava a escala na *Sequence of Ultrasound Regions*: um item por retângulo da tela,
com o tamanho físico do pixel (`PhysicalDeltaX/Y`) e, o que importa mais, **a unidade de cada
eixo**. Só a região cujos dois eixos estão em centímetros mede distância; a janela do Doppler
espectral tem o eixo x em segundos e o y em cm/s, e usá-la como régua daria um número com cara
de milímetro que não é milímetro.

Ler a tag é medida. Achar a régua desenhada na imagem seria chute — e imagem sem a tag
(captura de tela secundária, por exemplo) fica em pixels até o médico calibrar à mão.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CM = 3                 # PhysicalUnitsXDirection/YDirection: 3 = centímetros
POR_CM = 10.0          # mm por cm
FORMATO_2D = 1         # RegionSpatialFormat: 1 = imagem 2D


@dataclass(frozen=True)
class Regiao:
    """Um retângulo calibrado da imagem de ultrassom (coordenadas em pixels da imagem)."""
    x0: int
    y0: int
    x1: int
    y1: int
    mm_linha: float        # mm por pixel na vertical
    mm_coluna: float       # mm por pixel na horizontal
    formato: int = 0
    tipo: int = 0

    @property
    def espacamento(self) -> tuple[float, float]:
        return (self.mm_linha, self.mm_coluna)

    @property
    def area(self) -> int:
        return max(0, self.x1 - self.x0) * max(0, self.y1 - self.y0)

    def contem(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _inteiro(v) -> int | None:
    f = _num(v)
    return None if f is None else int(round(f))


def regioes(ds) -> list[Regiao]:
    """Regiões que servem para medir distância (os dois eixos em centímetros)."""
    seq = ds.get("SequenceOfUltrasoundRegions")
    if not seq:
        return []
    out: list[Regiao] = []
    for item in seq:
        if _inteiro(item.get("PhysicalUnitsXDirection")) != CM:
            continue
        if _inteiro(item.get("PhysicalUnitsYDirection")) != CM:
            continue
        dx, dy = _num(item.get("PhysicalDeltaX")), _num(item.get("PhysicalDeltaY"))
        if not dx or not dy or dx <= 0 or dy <= 0:
            continue
        x0 = _inteiro(item.get("RegionLocationMinX0"))
        y0 = _inteiro(item.get("RegionLocationMinY0"))
        x1 = _inteiro(item.get("RegionLocationMaxX1"))
        y1 = _inteiro(item.get("RegionLocationMaxY1"))
        if None in (x0, y0, x1, y1) or x1 <= x0 or y1 <= y0:
            continue
        out.append(Regiao(x0, y0, x1, y1, dy * POR_CM, dx * POR_CM,
                          _inteiro(item.get("RegionSpatialFormat")) or 0,
                          _inteiro(item.get("RegionDataType")) or 0))
    return out


def maior(regs) -> Regiao | None:
    """A região que ocupa mais tela — a imagem principal, quando há painel duplo."""
    return max(regs, key=lambda r: r.area) if regs else None


def espacamento(regs) -> tuple[float, float] | None:
    r = maior(regs)
    return r.espacamento if r is not None else None


def regiao_do_ponto(regs, x: float, y: float) -> Regiao | None:
    """Região que contém o ponto; entre regiões sobrepostas, a menor (a mais específica)."""
    dentro = [r for r in regs or () if r.contem(x, y)]
    return min(dentro, key=lambda r: r.area) if dentro else None


def espacamento_dos_pontos(regs, pontos) -> tuple[float, float] | None:
    """Escala de uma medida. `None` se a medida sai da região ou atravessa duas.

    Medir de um painel para o outro (lado direito e lado esquerdo na mesma imagem, 2D e
    Doppler) não é distância nenhuma: a medida fica em pixels em vez de virar milímetro errado.
    """
    if not regs or not pontos:
        return None
    achadas = [regiao_do_ponto(regs, p[0], p[1]) for p in pontos]
    if any(r is None for r in achadas):
        return None
    primeira = achadas[0]
    if any(r is not primeira for r in achadas):
        return None
    return primeira.espacamento


def texto(regs) -> str:
    """Resumo para a tela/estado (frases inteiras: pedaço de frase não se traduz)."""
    if not regs:
        return ""
    r = maior(regs)
    outras = len(regs) - 1
    v = f"{r.mm_coluna:.3f}"
    if outras == 1:
        return f"escala {v} mm por pixel (mais 1 região na imagem)"
    if outras:
        return f"escala {v} mm por pixel (mais {outras} regiões na imagem)"
    return f"escala {v} mm por pixel"
