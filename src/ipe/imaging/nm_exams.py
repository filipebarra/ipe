"""Receitas de exame: a mesma máquina de curvas, uma fórmula publicada para cada estudo.

O motor (`nm_roi`) conta os pixels e devolve curvas. Aqui cada exame diz **quais regiões**
desenhar, **que conta fazer** com elas e **como escrever no laudo**. Nenhuma receita reimplementa
contagem: todas trabalham em cima de `Curve`.

Uma regra atravessa o módulo: **o programa mede, não classifica.** Os valores de referência dos
guias aparecem como texto ao lado do número, para você comparar — nunca como um veredito. Eles
mudam com radiofármaco, refeição, protocolo e idade, e são do serviço.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ipe.imaging import renogram
from ipe.imaging.nm_roi import Curve, half_time, peak, retention, value_at


@dataclass
class ExamResult:
    """O que uma receita devolve: tabela, texto do laudo e avisos."""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    text: str = ""
    notes: list[str] = field(default_factory=list)
    reference: str = ""          # referência do guia, mostrada ao lado — não é veredito


@dataclass
class Protocol:
    """Um exame: nomes prontos das regiões, a conta e o que ele precisa perguntar."""
    key: str
    name: str
    rois: list[str]
    needs_stimulus: bool = False        # pede o instante do estímulo (sincalida, limão…)
    stimulus_label: str = ""
    reference: str = ""

    def run(self, curves: list[Curve], stimulus_s: float = 0.0) -> ExamResult:
        raise NotImplementedError


def _min_after(curve: Curve, t_s: float) -> tuple[float, float]:
    """(instante, valor) do menor ponto depois de t_s. (0, 0) se não houver pontos depois."""
    depois = curve.times_s >= t_s
    if not depois.any():
        return 0.0, 0.0
    i = int(np.argmin(np.where(depois, curve.counts, np.inf)))
    return float(curve.times_s[i]), float(curve.counts[i])


def _max_until(curve: Curve, t_s: float) -> tuple[float, float]:
    """(instante, valor) do maior ponto até t_s — o pico antes do estímulo."""
    antes = curve.times_s <= t_s
    if not antes.any():
        return peak(curve)
    i = int(np.argmax(np.where(antes, curve.counts, -np.inf)))
    return float(curve.times_s[i]), float(curve.counts[i])


# ------------------------------------------------------------------ renograma
class _Renograma(Protocol):
    def run(self, curves: list[Curve], stimulus_s: float = 0.0) -> ExamResult:
        res = renogram.analyse(curves)
        notas = list(res.notes) + [k.note for k in res.kidneys if k.note]
        return ExamResult(renogram.SUMMARY_HEADERS, renogram.summary_rows(res),
                          renogram.report_text(res), [n for n in notas if n], self.reference)


# ------------------------------------------------------------------ esvaziamento gástrico
class _Gastrico(Protocol):
    """% de retenção nos tempos do guia, em relação ao primeiro ponto da curva.

    A referência é o instante zero (logo após a refeição), por isso a aquisição tem que começar
    junto com ela — se a curva começar depois, a retenção sai subestimada e o aviso diz isso.
    """
    MARCOS_S = (1800.0, 3600.0, 7200.0, 14400.0)     # 30 min, 1 h, 2 h, 4 h

    def run(self, curves: list[Curve], stimulus_s: float = 0.0) -> ExamResult:
        linhas, notas, partes = [], [], []
        for c in curves:
            if not c.counts.size:
                continue
            fim = float(c.times_s[-1])
            vals = []
            for t in self.MARCOS_S:
                vals.append("—" if t > fim else f"{retention(c, t) or 0:.0f}%")
            meia = half_time(c, from_peak=False)
            linhas.append([c.name, *vals, "não atingido" if meia is None else f"{meia / 60:.0f} min"])
            meia_txt = "T½ não atingido." if meia is None else f"T½ de {meia / 60:.0f} min."
            partes.append(f"{c.name}: retenção de {vals[1]} em 1 h, {vals[2]} em 2 h e "
                          f"{vals[3]} em 4 h. {meia_txt}")
            if fim < self.MARCOS_S[-1]:
                notas.append(f"{c.name}: estudo de {fim / 3600:.1f} h, mais curto que as 4 h do guia.")
        headers = ["Região", "30 min", "1 h", "2 h", "4 h", "T½"]
        return ExamResult(headers, linhas, " ".join(partes), notas, self.reference)


# ------------------------------------------------------------------ vesícula (DISIDA)
class _Vesicula(Protocol):
    """Fração de ejeção vesicular: (máximo antes do estímulo − mínimo depois) ÷ máximo."""

    def run(self, curves: list[Curve], stimulus_s: float = 0.0) -> ExamResult:
        linhas, notas, partes = [], [], []
        for c in curves:
            if not c.counts.size:
                continue
            t_max, v_max = _max_until(c, stimulus_s) if stimulus_s > 0 else peak(c)
            t_min, v_min = _min_after(c, max(stimulus_s, t_max))
            if v_max <= 0:
                notas.append(f"{c.name}: sem contagem antes do estímulo; não dá para calcular a fração.")
                linhas.append([c.name, "—", "—", "—"])
                continue
            fe = max(0.0, (v_max - v_min) / v_max * 100.0)
            linhas.append([c.name, f"{t_max / 60:.0f} min", f"{t_min / 60:.0f} min", f"{fe:.0f}%"])
            partes.append(f"{c.name}: fração de ejeção de {fe:.0f}%, com máximo aos "
                          f"{t_max / 60:.0f} min e mínimo aos {t_min / 60:.0f} min.")
            if stimulus_s <= 0:
                notas.append(f"{c.name}: sem o instante do estímulo, o máximo usado foi o pico da "
                             f"curva inteira.")
        headers = ["Região", "Máximo", "Mínimo", "Fração de ejeção"]
        return ExamResult(headers, linhas, " ".join(partes), notas, self.reference)


# ------------------------------------------------------------------ glândulas salivares
class _Salivar(Protocol):
    """Captação relativa das glândulas e fração de excreção depois do estímulo."""

    def run(self, curves: list[Curve], stimulus_s: float = 0.0) -> ExamResult:
        linhas, notas, partes = [], [], []
        picos = []
        for c in curves:
            if not c.counts.size:
                picos.append(0.0)
                continue
            _t, v = _max_until(c, stimulus_s) if stimulus_s > 0 else peak(c)
            picos.append(max(v, 0.0))
        total = sum(picos) or 1.0
        for c, v_max in zip(curves, picos):
            if not c.counts.size:
                continue
            rel = v_max / total * 100.0
            if stimulus_s > 0 and v_max > 0:
                _tm, v_min = _min_after(c, stimulus_s)
                fe = max(0.0, (v_max - v_min) / v_max * 100.0)
                fe_txt = f"{fe:.0f}%"
                partes.append(f"{c.name}: captação relativa de {rel:.0f}% e excreção de {fe:.0f}%.")
            else:
                fe_txt = "—"
                partes.append(f"{c.name}: captação relativa de {rel:.0f}%.")
            linhas.append([c.name, f"{rel:.0f}%", fe_txt])
        if stimulus_s <= 0:
            notas.append("Sem o instante do estímulo não dá para calcular a fração de excreção.")
        headers = ["Glândula", "Captação relativa", "Fração de excreção"]
        return ExamResult(headers, linhas, " ".join(partes), notas, self.reference)


# ------------------------------------------------------------------ razão lesão/contralateral
class _Razao(Protocol):
    """Razão entre a primeira região e a segunda — trifásico ósseo, foco × lado normal."""

    def run(self, curves: list[Curve], stimulus_s: float = 0.0) -> ExamResult:
        linhas, notas = [], []
        validas = [c for c in curves if c.counts.size and c.pixels]
        if len(validas) < 2:
            return ExamResult(["Região", "Média por pixel", "Razão"], [],
                              "", ["A razão precisa de duas regiões: o alvo e o lado normal."],
                              self.reference)
        base = validas[1]
        med_base = float(base.counts.sum()) / max(base.pixels, 1) / max(base.counts.size, 1)
        for i, c in enumerate(validas):
            med = float(c.counts.sum()) / max(c.pixels, 1) / max(c.counts.size, 1)
            razao = "—" if i == 1 or med_base <= 0 else f"{med / med_base:.2f}"
            linhas.append([c.name, f"{med:.1f}", razao])
        alvo = validas[0]
        med_alvo = float(alvo.counts.sum()) / max(alvo.pixels, 1) / max(alvo.counts.size, 1)
        texto = ""
        if med_base > 0:
            texto = (f"{alvo.name} / {base.name}: razão de {med_alvo / med_base:.2f} "
                     "(média por pixel, mesmas regiões em todos os quadros).")
        if alvo.pixels != base.pixels:
            notas.append("As duas regiões têm áreas diferentes; a razão usa a média por pixel, "
                         "mas regiões do mesmo tamanho são mais comparáveis.")
        return ExamResult(["Região", "Média por pixel", "Razão"], linhas, texto, notas,
                          self.reference)


# ------------------------------------------------------------------ registro
PROTOCOLS: dict[str, Protocol] = {
    "livre": Protocol("livre", "Livre (só as curvas)", ["ROI 1", "ROI 2", "ROI 3", "Fundo"]),
    "renograma": _Renograma(
        "renograma", "Renograma (DTPA / MAG3)", ["Rim direito", "Rim esquerdo", "Fundo"],
        reference="Função relativa pela integral de 1 a 2,5 min."),
    "gastrico": _Gastrico(
        "gastrico", "Esvaziamento gástrico", ["Estômago", "Fundo"],
        reference="Guia SNMMI 3.0 (refeição sólida): retenção acima de 90% em 1 h, 60% em 2 h ou "
                  "10% em 4 h costuma ser considerada retardada. Confira o protocolo do serviço."),
    "vesicula": _Vesicula(
        "vesicula", "Vesícula (DISIDA) — fração de ejeção", ["Vesícula", "Fígado (fundo)"],
        needs_stimulus=True, stimulus_label="Sincalida aos",
        reference="Guia SNM 4.0: fração de ejeção de 38% ou mais aos 60 min após sincalida é o "
                  "corte mais usado. Confira o protocolo do serviço."),
    "salivar": _Salivar(
        "salivar", "Glândulas salivares", ["Parótida direita", "Parótida esquerda",
                                           "Submandibular direita", "Submandibular esquerda",
                                           "Cavidade oral", "Fundo"],
        needs_stimulus=True, stimulus_label="Estímulo aos"),
    "razao": _Razao(
        "razao", "Razão lesão / lado normal", ["Lesão", "Lado normal"],
        reference="A segunda região é a referência. Desenhe as duas do mesmo tamanho."),
}

ORDER = ["livre", "renograma", "gastrico", "vesicula", "salivar", "razao"]


def protocol(key: str) -> Protocol:
    return PROTOCOLS.get(key) or PROTOCOLS["livre"]


def run(key: str, curves: list[Curve], stimulus_s: float = 0.0) -> ExamResult:
    """Roda a receita do exame. O protocolo "livre" devolve só os números gerais da curva."""
    p = protocol(key)
    if p.key == "livre":
        return _free(curves)
    return p.run(curves, stimulus_s)


def _free(curves: list[Curve]) -> ExamResult:
    """Sem exame escolhido: pico, T½ e área de cada região, sem fórmula de nenhum protocolo."""
    linhas, partes = [], []
    for c in curves:
        if not c.counts.size:
            continue
        t_pico, v_pico = peak(c)
        meia = half_time(c)
        linhas.append([c.name, f"{t_pico / 60:.1f} min", f"{v_pico:,.0f}".replace(",", " "),
                       "não atingido" if meia is None else f"{meia / 60:.1f} min",
                       f"{c.pixels}"])
        meia_txt = "T½ não atingido." if meia is None else f"T½ de {meia / 60:.1f} min."
        partes.append(f"{c.name}: pico aos {t_pico / 60:.1f} min. {meia_txt}")
    return ExamResult(["Região", "Tempo ao pico", "Valor no pico", "T½ após o pico", "Pixels"],
                      linhas, " ".join(partes), [], "")
