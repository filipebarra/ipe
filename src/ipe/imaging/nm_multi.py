"""Medicina nuclear entre séries: comparar vistas ou tempos diferentes do mesmo exame.

Quatro exames do IMEB não cabem na análise de uma série dinâmica, porque a conta deles compara
**imagens separadas**:

* **DMSA** — função relativa pela média geométrica de ANT × POST (duas vistas estáticas).
* **Paratireoide** — dupla fase: precoce × tardia (duas séries, horários diferentes).
* **Tireoide** — captação percentual contra o padrão da seringa (cheia × vazia, outro horário).
* **Trânsito colônico** — centro geométrico em 24 h, 48 h e 72 h (três ou mais tempos).

O bloco comum é este módulo: cada imagem vira uma **fonte** com rótulo, papel e horário; as
regiões são desenhadas em cada fonte; a contagem líquida de cada região em cada fonte vira uma
tabela; e cada receita lê essa tabela.

Duas coisas que o módulo trata e que dão erro quando esquecidas:

1. **Horário.** Imagens de horários diferentes só podem ser comparadas depois da correção de
   decaimento. O padrão da seringa medido 20 min antes da tireoide não vale o mesmo.
2. **Área.** Regiões de tamanhos diferentes não se comparam; o fundo é escalado pela área, e as
   receitas avisam quando as regiões do par têm áreas muito diferentes.

Sem Qt e sem scipy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ipe.imaging import nm
from ipe.imaging.nm_exams import ExamResult
from ipe.imaging.nm_roi import Roi


def seconds_of_day(texto: str) -> float | None:
    """HHMMSS[.frac] -> segundos desde a meia-noite. None quando não dá para ler."""
    t = (texto or "").replace(":", "").strip()
    if len(t) < 4:
        return None
    try:
        return int(t[0:2]) * 3600 + int(t[2:4]) * 60 + (float(t[4:]) if len(t) > 4 else 0.0)
    except ValueError:
        return None


@dataclass
class Source:
    """Uma imagem da análise: uma série, uma vista ou uma soma de quadros."""
    key: str
    label: str
    frames: list = field(default_factory=list)
    role: str = "imagem"          # imagem | padrao_cheio | padrao_vazio
    time_s: float | None = None   # segundos desde o dia; preenchido do cabeçalho
    rois: list = field(default_factory=list)      # list[Roi], próprias desta fonte

    def fill_time(self) -> None:
        """Horário da aquisição, lido do quadro (AcquisitionTime/ContentTime)."""
        if self.time_s is not None or not self.frames:
            return
        for f in self.frames:
            t = seconds_of_day(getattr(f, "acquisition_time", ""))
            if t is not None:
                self.time_s = t
                return


@dataclass
class Cell:
    """A contagem de uma região numa fonte."""
    source: str
    roi: str
    raw: float = 0.0
    background: float = 0.0
    pixels: int = 0

    @property
    def net(self) -> float:
        return max(0.0, self.raw - self.background)

    @property
    def per_pixel(self) -> float:
        return self.net / self.pixels if self.pixels else 0.0


class Table:
    """Tabela contagem × (fonte, região), com os horários e a meia-vida para o decaimento."""

    def __init__(self, cells: dict, sources: list[Source], half_life_s: float = 0.0):
        self.cells: dict[tuple[str, str], Cell] = cells
        self.sources = sources
        self.half_life_s = half_life_s

    def source(self, key: str) -> Source | None:
        return next((s for s in self.sources if s.key == key), None)

    def get(self, source_key: str, roi_name: str) -> Cell | None:
        return self.cells.get((source_key, roi_name))

    def rois_of(self, source_key: str) -> list[str]:
        return [r for (s, r) in self.cells if s == source_key]

    def net(self, source_key: str, roi_name: str, decay_to: float | None = None) -> float:
        """Contagem líquida, corrigida do decaimento até um instante de referência."""
        c = self.get(source_key, roi_name)
        if c is None:
            return 0.0
        v = c.net
        if decay_to is None or self.half_life_s <= 0:
            return v
        s = self.source(source_key)
        if s is None or s.time_s is None:
            return v
        dt = s.time_s - decay_to
        return v * math.exp(math.log(2) * dt / self.half_life_s)

    def common_time(self) -> float | None:
        """Horário da primeira fonte — a referência para corrigir as outras."""
        tempos = [s.time_s for s in self.sources if s.time_s is not None]
        return min(tempos) if tempos else None


# ------------------------------------------------------------------ medir
def measure(sources: list[Source], cache, progress=None) -> Table:
    """Soma os pixels de cada região em cada fonte (somando todos os quadros da fonte)."""
    from ipe.imaging.nm_roi import ring_mask

    cells: dict[tuple[str, str], Cell] = {}
    meia = 0.0
    for i, src in enumerate(sources):
        if progress is not None and progress(i, len(sources)) is False:
            break
        if not src.frames:
            continue
        src.fill_time()
        if meia <= 0:
            meia = nm.half_life_for(nm.info_for_file(src.frames[0].path))
        acc = None
        for f in src.frames:
            px = cache.get(f).pixels
            if px.ndim != 2:
                px = px.astype(np.float64).mean(axis=2)
            acc = px.astype(np.float64) if acc is None else acc + px.astype(np.float64)
        if acc is None:
            continue
        por_nome = {r.name: r for r in src.rois}
        for r in src.rois:
            res = r.mask(acc.shape)
            if res is None:
                cells[(src.key, r.name)] = Cell(src.key, r.name, 0.0, 0.0, 0)
                continue
            sl, m = res
            cheia = np.zeros(acc.shape, bool)
            cheia[sl] = m
            n = int(cheia.sum())
            bruto = float(acc[cheia].sum())
            fundo = _background(r, acc, cheia, n, por_nome, ring_mask)
            cells[(src.key, r.name)] = Cell(src.key, r.name, bruto, fundo, n)
    return Table(cells, sources, meia)


def _background(r: Roi, acc: np.ndarray, mask: np.ndarray, n: int, por_nome: dict, ring_mask) -> float:
    if r.background == "fraction":
        return float(acc[mask].sum()) * float(np.clip(r.fraction, 0.0, 0.95))
    if r.background == "ring":
        anel = ring_mask(mask, r.ring_px)
        na = int(anel.sum())
        return float(acc[anel].sum()) / na * n if na else 0.0
    if r.background == "roi":
        outra = por_nome.get(r.background_roi)
        if outra is None:
            return 0.0
        res = outra.mask(acc.shape)
        if res is None:
            return 0.0
        sl, m = res
        cheia = np.zeros(acc.shape, bool)
        cheia[sl] = m
        nf = int(cheia.sum())
        return float(acc[cheia].sum()) / nf * n if nf else 0.0
    return 0.0


# ------------------------------------------------------------------ receitas
def geometric_mean_function(t: Table, ant: str, post: str, left: str, right: str,
                            flip_note: bool = True) -> ExamResult:
    """DMSA: função relativa pela média geométrica √(ANT × POST) de cada rim."""
    notas: list[str] = []
    valores = {}
    for rim in (right, left):
        a = t.net(ant, rim)
        p = t.net(post, rim)
        if a <= 0 and p <= 0:
            notas.append(f"Sem contagem para {rim} nas duas vistas.")
        valores[rim] = math.sqrt(max(a, 0.0) * max(p, 0.0)) if (a > 0 and p > 0) else max(a, p, 0.0)
        if a <= 0 or p <= 0:
            notas.append(f"{rim}: só uma das vistas tem contagem; usei a que tem, sem média geométrica.")
    total = sum(valores.values())
    linhas = []
    for rim in (right, left):
        pct = valores[rim] / total * 100.0 if total > 0 else None
        ca, cp = t.get(ant, rim), t.get(post, rim)
        linhas.append([rim,
                       f"{ca.net:,.0f}".replace(",", " ") if ca else "—",
                       f"{cp.net:,.0f}".replace(",", " ") if cp else "—",
                       f"{valores[rim]:,.0f}".replace(",", " "),
                       "—" if pct is None else f"{pct:.1f}%"])
        if ca and cp and ca.pixels and cp.pixels:
            razao = max(ca.pixels, cp.pixels) / min(ca.pixels, cp.pixels)
            if razao > 1.15:
                notas.append(f"{rim}: as regiões de ANT e POST têm áreas bem diferentes "
                             f"({ca.pixels} e {cp.pixels} pixels).")
    if total <= 0:
        notas.append("As duas regiões somam zero: sem função relativa.")
        texto = ""
    else:
        d = valores[right] / total * 100.0
        e = valores[left] / total * 100.0
        texto = (f"Função relativa por média geométrica: {right} {d:.1f}%, {left} {e:.1f}%.")
    return ExamResult(["Rim", "ANT", "POST", "Média geométrica", "Função relativa"],
                      linhas, texto, notas,
                      "Média geométrica √(ANT × POST). Em rim de posição normal a POST sozinha "
                      "costuma bastar; em hidronefrose a média geométrica é a recomendada.")


def dual_phase(t: Table, early: str, late: str, rois: list[str],
               decay: bool = True) -> ExamResult:
    """Paratireoide dupla fase: retenção relativa entre a imagem precoce e a tardia."""
    notas: list[str] = []
    ref = t.common_time()
    usar = ref if (decay and t.half_life_s > 0) else None
    if decay and t.half_life_s <= 0:
        notas.append("Sem meia-vida no cabeçalho: comparação sem corrigir o decaimento.")
    elif decay and any(t.source(k) is None or t.source(k).time_s is None for k in (early, late)):
        notas.append("Sem horário numa das imagens: comparação sem corrigir o decaimento.")
        usar = None
    linhas, partes = [], []
    for nome in rois:
        p = t.net(early, nome, usar)
        tardio = t.net(late, nome, usar)
        if p <= 0:
            linhas.append([nome, "—", "—", "—"])
            notas.append(f"{nome}: sem contagem na imagem precoce.")
            continue
        retido = tardio / p * 100.0
        linhas.append([nome, f"{p:,.0f}".replace(",", " "),
                       f"{tardio:,.0f}".replace(",", " "), f"{retido:.0f}%"])
        partes.append(f"{nome}: retenção de {retido:.0f}% da precoce para a tardia.")
    return ExamResult(["Região", "Precoce", "Tardia", "Retenção"], linhas, " ".join(partes), notas,
                      "Dupla fase: a lesão de paratireoide costuma reter mais que a tireoide. "
                      "Confira o protocolo do serviço.")


def uptake_percent(t: Table, target_src: str, target_roi: str, full_src: str, empty_src: str,
                   standard_roi: str) -> ExamResult:
    """Tireoide: captação % contra o padrão da seringa, com decaimento até a hora da tireoide."""
    notas: list[str] = []
    alvo_fonte = t.source(target_src)
    ref = alvo_fonte.time_s if alvo_fonte else None
    if t.half_life_s <= 0:
        notas.append("Sem meia-vida no cabeçalho: a captação sai sem corrigir o decaimento.")
        ref = None
    elif ref is None:
        notas.append("Sem horário da imagem da tireoide: a captação sai sem corrigir o decaimento.")
    cheia = t.net(full_src, standard_roi, ref)
    vazia = t.net(empty_src, standard_roi, ref) if empty_src else 0.0
    dose = cheia - vazia
    alvo = t.net(target_src, target_roi, ref)
    linhas = [["Tireoide", f"{alvo:,.0f}".replace(",", " ")],
              ["Seringa cheia", f"{cheia:,.0f}".replace(",", " ")],
              ["Seringa vazia", f"{vazia:,.0f}".replace(",", " ")],
              ["Dose administrada", f"{dose:,.0f}".replace(",", " ")]]
    if dose <= 0:
        notas.append("A seringa cheia menos a vazia deu zero ou negativo: sem captação.")
        return ExamResult(["Medida", "Contagem líquida"], linhas, "", notas, _REF_TIREOIDE)
    pct = alvo / dose * 100.0
    linhas.append(["Captação", f"{pct:.2f}%"])
    texto = f"Captação tireoidiana de {pct:.2f}% da dose administrada."
    if not empty_src:
        notas.append("Sem a seringa vazia, o resíduo não foi descontado da dose.")
    return ExamResult(["Medida", "Contagem líquida"], linhas, texto, notas, _REF_TIREOIDE)


_REF_TIREOIDE = ("Os valores normais de captação dependem do radiofármaco, do tempo até a medida "
                 "e da ingestão de iodo da população. São do serviço, não do programa.")


def geometric_center(t: Table, ordem: list[str], sources: list[str]) -> ExamResult:
    """Trânsito colônico: centro geométrico em cada tempo.

    `GC = Σ (fração da região × peso da região)`, com os pesos 1, 2, 3… na ordem em que as
    regiões foram listadas (ascendente, transverso, descendente, retossigmoide, eliminado).
    Um GC de 1 é tudo no ascendente; o valor cresce conforme o bolo avança.
    """
    notas: list[str] = []
    headers = ["Tempo"] + ordem + ["Centro geométrico"]
    linhas, partes = [], []
    for chave in sources:
        src = t.source(chave)
        rotulo = src.label if src else chave
        vals = [t.net(chave, nome) for nome in ordem]
        total = sum(v for v in vals if v > 0)
        if total <= 0:
            linhas.append([rotulo] + ["—"] * len(ordem) + ["—"])
            notas.append(f"{rotulo}: sem contagem nas regiões.")
            continue
        fracoes = [max(v, 0.0) / total for v in vals]
        gc = sum(f * (i + 1) for i, f in enumerate(fracoes))
        linhas.append([rotulo] + [f"{f * 100:.0f}%" for f in fracoes] + [f"{gc:.2f}"])
        partes.append(f"{rotulo}: centro geométrico de {gc:.2f}.")
    if len(ordem) < 2:
        notas.append("O centro geométrico precisa de pelo menos duas regiões, na ordem do trânsito.")
    return ExamResult(headers, linhas, " ".join(partes), notas,
                      "Pesos 1 a N na ordem em que as regiões aparecem. Os valores normais "
                      "dependem da refeição e do protocolo do serviço.")


def raw_table(t: Table) -> ExamResult:
    """Sem receita: só as contagens líquidas de cada região em cada fonte."""
    fontes = [s for s in t.sources if any(k[0] == s.key for k in t.cells)]
    nomes: list[str] = []
    for s in fontes:
        for n in t.rois_of(s.key):
            if n not in nomes:
                nomes.append(n)
    linhas = []
    for s in fontes:
        linha = [s.label]
        for n in nomes:
            c = t.get(s.key, n)
            linha.append("—" if c is None else f"{c.net:,.0f}".replace(",", " "))
        linhas.append(linha)
    return ExamResult(["Imagem"] + nomes, linhas, "", [], "")


# ------------------------------------------------------------------ protocolos
@dataclass
class MultiProtocol:
    """Exame que compara imagens: que papéis as imagens têm e que regiões desenhar."""
    key: str
    name: str
    roles: list = field(default_factory=list)      # [(chave, rótulo)] — vazio = usa todas em ordem
    rois: list = field(default_factory=list)       # nomes prontos das regiões
    decay_default: bool = True

    def run(self, table: Table, papeis: dict) -> ExamResult:
        return raw_table(table)


def _by_role(papeis: dict, chave: str) -> str:
    """A fonte que ficou com este papel (a primeira, se houver mais de uma)."""
    return next((fonte for fonte, papel in papeis.items() if papel == chave), "")


class _DMSA(MultiProtocol):
    def run(self, table: Table, papeis: dict) -> ExamResult:
        ant, post = _by_role(papeis, "ant"), _by_role(papeis, "post")
        if not ant or not post:
            return ExamResult([], [], "", ["Marque qual imagem é a anterior e qual é a posterior."])
        return geometric_mean_function(table, ant, post, "Rim esquerdo", "Rim direito")


class _DuplaFase(MultiProtocol):
    def run(self, table: Table, papeis: dict) -> ExamResult:
        cedo, tarde = _by_role(papeis, "cedo"), _by_role(papeis, "tarde")
        if not cedo or not tarde:
            return ExamResult([], [], "", ["Marque qual imagem é a precoce e qual é a tardia."])
        nomes = [n for n in table.rois_of(cedo) if n in table.rois_of(tarde)]
        if not nomes:
            return ExamResult([], [], "", ["Desenhe as mesmas regiões nas duas imagens."])
        return dual_phase(table, cedo, tarde, nomes, self.decay_default)


class _Tireoide(MultiProtocol):
    def run(self, table: Table, papeis: dict) -> ExamResult:
        alvo = _by_role(papeis, "tireoide")
        cheia = _by_role(papeis, "cheia")
        vazia = _by_role(papeis, "vazia")
        if not alvo or not cheia:
            return ExamResult([], [], "", ["Marque a imagem da tireoide e a da seringa cheia."])
        if "Tireoide" not in table.rois_of(alvo):
            return ExamResult([], [], "", ["Desenhe a região “Tireoide” na imagem da tireoide."])
        if "Seringa" not in table.rois_of(cheia):
            return ExamResult([], [], "", ["Desenhe a região “Seringa” na imagem da seringa cheia."])
        return uptake_percent(table, alvo, "Tireoide", cheia, vazia, "Seringa")


class _Transito(MultiProtocol):
    def run(self, table: Table, papeis: dict) -> ExamResult:
        usadas = [s for s in table.sources if any(k[0] == s.key for k in table.cells)]
        usadas.sort(key=lambda s: (s.time_s is None, s.time_s or 0.0))
        ordem = [n for n in self.rois if any(table.get(s.key, n) for s in usadas)]
        if not usadas:
            return ExamResult([], [], "", ["Desenhe as regiões do cólon em cada tempo."])
        return geometric_center(table, ordem, [s.key for s in usadas])


MULTI_PROTOCOLS: dict[str, MultiProtocol] = {
    "livre": MultiProtocol("livre", "Livre (só as contagens)"),
    "dmsa": _DMSA("dmsa", "DMSA — função relativa",
                  [("ant", "Anterior"), ("post", "Posterior")],
                  ["Rim direito", "Rim esquerdo", "Fundo"]),
    "paratireoide": _DuplaFase("paratireoide", "Paratireoide — dupla fase",
                               [("cedo", "Precoce"), ("tarde", "Tardia")],
                               ["Nódulo", "Tireoide", "Fundo"]),
    "tireoide": _Tireoide("tireoide", "Tireoide — captação %",
                          [("tireoide", "Tireoide"), ("cheia", "Seringa cheia"),
                           ("vazia", "Seringa vazia")],
                          ["Tireoide", "Seringa", "Fundo"]),
    "transito": _Transito("transito", "Trânsito colônico — centro geométrico", [],
                          ["Ascendente", "Transverso", "Descendente", "Retossigmoide",
                           "Eliminado"]),
}

MULTI_ORDER = ["livre", "dmsa", "paratireoide", "tireoide", "transito"]


def multi_protocol(key: str) -> MultiProtocol:
    return MULTI_PROTOCOLS.get(key) or MULTI_PROTOCOLS["livre"]
