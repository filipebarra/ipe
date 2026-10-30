"""Renograma: os números que se tiram de duas curvas renais.

Tudo aqui é fórmula publicada, sem banco de normalidade proprietário:

* **Função relativa** pelo método da integral (Patlak-Rutland simplificado): a área sob a curva
  de cada rim entre 1 e 2,5 min, já sem fundo, normalizada entre os dois. A janela é essa porque
  antes de 1 min ainda há sangue no campo e depois de 2,5 min já começou a excreção — nos dois
  casos a área deixa de medir captação.
* **Tempo ao pico** e **T½** (tempo, depois do pico, para cair à metade).
* **Razão 20 min / máximo** e o que resta aos 20 min.

Duas regras de honestidade que o módulo impõe:

1. **T½ que não foi atingido é `None`, não um número grande.** Se a curva não cai à metade dentro
   do estudo, a resposta certa é "não atingiu em X min" — quem lê precisa ver a diferença entre
   isso e um T½ medido.
2. **O módulo não diz "obstruído".** Ele devolve os números e o que aconteceu com a curva; a
   interpretação é do médico. Valores de referência ficam de fora do código porque mudam com
   radiofármaco, protocolo, hidratação e idade.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ipe.imaging.nm_roi import Curve, half_time, integral, peak, value_at

# janela da integral para a função relativa, em segundos
INTEGRAL_START_S = 60.0
INTEGRAL_END_S = 150.0


@dataclass
class KidneyResult:
    """Números de um rim."""
    name: str
    relative_pct: float | None = None       # função relativa (%)
    peak_time_s: float = 0.0
    peak_value: float = 0.0
    half_time_s: float | None = None        # None = não caiu à metade dentro do estudo
    ratio_20min: float | None = None        # valor aos 20 min ÷ pico
    integral: float = 0.0
    note: str = ""

    @property
    def half_time_min(self) -> float | None:
        return None if self.half_time_s is None else self.half_time_s / 60.0

    @property
    def peak_time_min(self) -> float:
        return self.peak_time_s / 60.0


@dataclass
class RenogramResult:
    kidneys: list[KidneyResult]
    duration_s: float = 0.0
    window: tuple[float, float] = (INTEGRAL_START_S, INTEGRAL_END_S)
    notes: list[str] = None                 # avisos gerais (curva curta, fundo ausente…)

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []

    def by_name(self, name: str) -> KidneyResult | None:
        return next((k for k in self.kidneys if k.name == name), None)


def analyse(curves: list[Curve], t0_s: float = INTEGRAL_START_S,
            t1_s: float = INTEGRAL_END_S) -> RenogramResult:
    """Analisa as curvas dos rins (duas, normalmente) e devolve os números de cada um.

    A função relativa só sai quando há exatamente duas curvas — com um rim só, ou com três
    regiões, "relativa a quê?" não tem resposta, e o campo fica vazio em vez de inventado.
    """
    resultados: list[KidneyResult] = []
    avisos: list[str] = []
    duracao = float(max((c.times_s[-1] for c in curves if c.times_s.size), default=0.0))
    if duracao < t1_s:
        avisos.append(f"O estudo tem {duracao / 60:.1f} min: curto para a janela da função relativa.")

    for c in curves:
        k = KidneyResult(c.name, note=c.note)
        if not c.counts.size:
            k.note = (k.note + " " if k.note else "") + "Curva vazia."
            resultados.append(k)
            continue
        k.peak_time_s, k.peak_value = peak(c)
        k.half_time_s = half_time(c, from_peak=True)
        k.integral = integral(c, t0_s, t1_s)
        if duracao >= 1200.0 and k.peak_value > 0:
            k.ratio_20min = float(value_at(c, 1200.0) / k.peak_value)
        if k.half_time_s is None and k.peak_value > 0:
            k.note = (k.note + " " if k.note else "") + \
                f"Não caiu à metade do pico em {duracao / 60:.0f} min de estudo."
        if c.method == "none":
            k.note = (k.note + " " if k.note else "") + "Curva sem subtração de fundo."
        resultados.append(k)

    if len(resultados) == 2:
        total = sum(max(k.integral, 0.0) for k in resultados)
        if total > 0:
            for k in resultados:
                k.relative_pct = max(k.integral, 0.0) / total * 100.0
        else:
            avisos.append("As duas curvas somam zero na janela da integral: sem função relativa.")
    elif len(resultados) != 2:
        avisos.append("A função relativa precisa de exatamente duas curvas (rim direito e esquerdo).")
    return RenogramResult(resultados, duracao, (t0_s, t1_s), avisos)


def summary_rows(res: RenogramResult) -> list[list[str]]:
    """Tabela pronta para a tela e para o laudo."""
    linhas = []
    for k in res.kidneys:
        linhas.append([
            k.name,
            "—" if k.relative_pct is None else f"{k.relative_pct:.1f}%",
            f"{k.peak_time_min:.1f} min",
            "não atingido" if k.half_time_s is None else f"{k.half_time_min:.1f} min",
            "—" if k.ratio_20min is None else f"{k.ratio_20min:.2f}",
        ])
    return linhas


SUMMARY_HEADERS = ["Rim", "Função relativa", "Tempo ao pico", "T½ após o pico", "20 min / pico"]


def report_text(res: RenogramResult) -> str:
    """Parágrafo para o laudo, só com o que foi medido — sem interpretação."""
    partes = []
    for k in res.kidneys:
        p = [k.name]
        if k.relative_pct is not None:
            p.append(f"função relativa {k.relative_pct:.1f}%")
        p.append(f"pico aos {k.peak_time_min:.1f} min")
        p.append("T½ não atingido" if k.half_time_s is None
                 else f"T½ de {k.half_time_min:.1f} min após o pico")
        if k.ratio_20min is not None:
            p.append(f"relação 20 min/pico de {k.ratio_20min:.2f}")
        partes.append(": ".join([p[0], ", ".join(p[1:])]))
    texto = ". ".join(partes) + "."
    if res.notes:
        texto += " " + " ".join(res.notes)
    return texto


def normalise_names(curves: list[Curve]) -> list[Curve]:
    """Garante nomes distintos; o resto do módulo usa o nome como identificador."""
    vistos: dict[str, int] = {}
    for c in curves:
        base = c.name or "ROI"
        n = vistos.get(base, 0) + 1
        vistos[base] = n
        c.name = base if n == 1 else f"{base} ({n})"
    return curves
