"""Medicina nuclear: ROI sobre série dinâmica, curva atividade-tempo e imagem condensada.

Esta é a máquina que sete exames usam (renograma, salivar, dacrio, cistocintilografia,
refluxo GI, esvaziamento gástrico e trifásico ósseo). Todos eles são a mesma coisa: contar
os pixels de uma região em cada quadro, descontar o fundo, pôr no eixo de tempo certo e
aplicar uma fórmula publicada. Só a fórmula muda.

Três decisões que valem para todos:

* **O tempo de cada ponto é o meio do quadro**, não o início. Um quadro de 30 s representa
  a atividade média nesses 30 s; plotar no início desloca a curva meio quadro para a esquerda,
  e é isso que estraga um T½.
* **Contagens por segundo, não contagens.** Um estudo com fluxo de 2 s e dinâmico de 30 s tem
  quadros 15 vezes mais longos na segunda fase; sem dividir pela duração a curva dá um degrau
  que não existe.
* **O fundo é escolha do operador e fica registrado.** Cada curva carrega o método e o quanto
  foi subtraído, porque o mesmo rim dá números diferentes conforme o fundo.

Sem Qt e sem scipy: só numpy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.imaging import nm
from ipe.imaging.measure import roi_mask

log = logging.getLogger(__name__)

# método de fundo -> (nome na tela, precisa de outra ROI?)
BACKGROUND_METHODS: dict[str, tuple[str, bool]] = {
    "none": ("Sem subtrair fundo", False),
    "roi": ("ROI de fundo própria", True),
    "ring": ("Anel em volta da ROI", False),
    "fraction": ("Fração fixa das contagens", False),
}


@dataclass
class Roi:
    """Uma região desenhada sobre a série.

    Três origens: uma forma geométrica (elipse, retângulo), um traçado à mão livre (vira
    polígono) ou um **contorno automático** — e nesse caso a região é uma máscara de pixels,
    não uma lista de pontos, porque a borda de um contorno por limiar não é uma figura.
    """
    name: str
    kind: str = "ellipse"                  # ellipse, rect, polygon (os mesmos do measure) ou auto
    points: list = field(default_factory=list)
    role: str = "alvo"                     # alvo | fundo
    background: str = "none"               # método de fundo desta ROI
    background_roi: str = ""               # nome da ROI de fundo, quando o método é "roi"
    ring_px: int = 3                       # largura do anel, quando o método é "ring"
    fraction: float = 0.0                  # fração fixa, quando o método é "fraction"
    auto_mask: np.ndarray | None = field(default=None, repr=False)   # contorno automático
    auto_pct: float = 40.0                 # limiar usado, em % do máximo (só para mostrar)
    auto_box: tuple | None = None          # caixa de busca original (y0, y1, x0, x1)

    @property
    def is_auto(self) -> bool:
        return self.auto_mask is not None

    def mask(self, shape: tuple[int, int]):
        if self.auto_mask is not None:
            if self.auto_mask.shape != tuple(shape[:2]):
                return None
            return (slice(0, shape[0]), slice(0, shape[1])), self.auto_mask
        return roi_mask(self.kind, self.points, shape)

    def mirrored(self, width: int) -> Roi:
        """Cópia espelhada no eixo vertical da imagem, com os mesmos ajustes de fundo."""
        novo = Roi(name=self.name, kind=self.kind, role=self.role, background=self.background,
                   background_roi=self.background_roi, ring_px=self.ring_px,
                   fraction=self.fraction, auto_pct=self.auto_pct)
        if self.auto_mask is not None:
            novo.auto_mask = self.auto_mask[:, ::-1].copy()
            if self.auto_box is not None:
                y0, y1, x0, x1 = self.auto_box
                w = self.auto_mask.shape[1]
                novo.auto_box = (y0, y1, w - x1, w - x0)
        else:
            novo.points = [(width - x, y) for x, y in self.points]
        return novo


@dataclass
class Curve:
    """Curva atividade-tempo de uma ROI."""
    name: str
    times_s: np.ndarray                    # meio de cada quadro, em segundos
    counts: np.ndarray                     # contagens já com o fundo descontado
    raw: np.ndarray                        # contagens brutas na ROI
    background: np.ndarray                 # o que foi subtraído em cada quadro
    durations_s: np.ndarray                # duração de cada quadro
    pixels: int = 0                        # área da ROI, em pixels
    method: str = "none"                   # método de fundo usado
    decay_corrected: bool = False
    note: str = ""                         # o que não deu certo (fundo faltando etc.)

    @property
    def cps(self) -> np.ndarray:
        """Contagens por segundo — é o que permite comparar fases de duração diferente."""
        return nm.counts_per_second(self.counts, self.durations_s * 1000.0)

    @property
    def peak_index(self) -> int:
        return int(np.argmax(self.counts)) if self.counts.size else 0


# ------------------------------------------------------------------ máscaras
def _dilate(mask: np.ndarray, n: int) -> np.ndarray:
    """Engorda a máscara em n pixels (vizinhança 8), sem scipy."""
    out = mask
    for _ in range(max(0, int(n))):
        p = np.pad(out, 1, mode="constant", constant_values=False)
        h, w = out.shape
        acc = np.zeros(out.shape, bool)
        for dy in range(3):
            for dx in range(3):
                acc |= p[dy:dy + h, dx:dx + w]
        out = acc
    return out


def ring_mask(mask: np.ndarray, width: int, gap: int = 1) -> np.ndarray:
    """Anel em volta da ROI: engorda `gap + width` e tira o miolo engordado por `gap`.

    O intervalo existe para o anel não encostar na borda da região — a captação vaza um
    pouco para fora, e um anel colado mede o alvo, não o fundo.
    """
    dentro = _dilate(mask, gap)
    fora = _dilate(mask, gap + max(1, int(width)))
    return fora & ~dentro


def grow_from(pixels: np.ndarray, seed: tuple[int, int], pct: float = 40.0,
              box=None, max_steps: int = 400) -> np.ndarray | None:
    """Contorno automático: cresce a partir de um ponto enquanto o pixel passa do limiar.

    O limiar é uma **porcentagem do máximo dentro da caixa de busca** — é o critério usado em
    medicina nuclear (40% do máximo é o mais comum), e não um valor absoluto, porque contagem
    bruta muda com dose, tempo e câmara.

    Só entra no contorno o que está **ligado ao ponto de partida**: dois rins próximos não
    viram uma região só, e um foco vizinho acima do limiar fica de fora.
    """
    px = np.asarray(pixels, np.float64)
    if px.ndim != 2:
        return None
    dentro = np.ones(px.shape, bool)
    if box is not None:
        dentro = np.zeros(px.shape, bool)
        dentro[box[0], box[1]] = True
    if not dentro.any():
        return None
    topo = float(px[dentro].max())
    if topo <= 0:
        return None
    limiar = topo * float(np.clip(pct, 1.0, 99.0)) / 100.0
    aceito = dentro & (px >= limiar)
    y, x = int(seed[1]), int(seed[0])
    if not (0 <= y < px.shape[0] and 0 <= x < px.shape[1]) or not aceito[y, x]:
        if not aceito.any():
            return None
        yy, xx = np.nonzero(aceito & (px == px[aceito].max()))   # cai no pixel mais quente
        y, x = int(yy[0]), int(xx[0])
    atual = np.zeros(px.shape, bool)
    atual[y, x] = True
    for _ in range(max_steps):
        novo = _dilate(atual, 1) & aceito
        if novo.sum() == atual.sum():
            break
        atual = novo
    return atual if atual.any() else None


def mask_outline(mask: np.ndarray) -> np.ndarray:
    """Pixels de borda da máscara — é o que se desenha na tela."""
    if mask is None or not mask.any():
        return np.zeros((0, 0), bool)
    p = np.pad(mask, 1, mode="constant", constant_values=False)
    h, w = mask.shape
    vizinhos = (p[0:h, 1:w + 1] & p[2:h + 2, 1:w + 1]
                & p[1:h + 1, 0:w] & p[1:h + 1, 2:w + 2])
    return mask & ~vizinhos


# ------------------------------------------------------------------ curvas
def frame_counts(frames: list, cache, rois: list[Roi], progress=None) -> dict[str, dict]:
    """Percorre a série uma vez e soma os pixels de cada ROI em cada quadro.

    Devolve {nome: {"raw": [...], "pixels": n, "ring": [...]}} — as contagens do anel já
    saem daqui para não ter que ler tudo de novo.
    """
    if not frames:
        return {}
    shape = cache.get(frames[0]).pixels.shape[:2]
    prep: dict[str, dict] = {}
    for r in rois:
        res = r.mask(shape)
        if res is None:
            prep[r.name] = {"raw": [], "pixels": 0, "ring": [], "erro": "ROI fora da imagem"}
            continue
        sl, m = res
        cheia = np.zeros(shape, bool)
        cheia[sl] = m
        anel = ring_mask(cheia, r.ring_px) if r.background == "ring" else None
        prep[r.name] = {"mask": cheia, "ring_mask": anel, "raw": [], "ring": [],
                        "pixels": int(cheia.sum()),
                        "ring_pixels": int(anel.sum()) if anel is not None else 0}
    for i, f in enumerate(frames):
        if progress is not None and progress(i, len(frames)) is False:
            break
        px = cache.get(f).pixels
        if px.ndim != 2:
            px = px.astype(np.float64).mean(axis=2)
        px = px.astype(np.float64, copy=False)
        for dados in prep.values():
            m = dados.get("mask")
            if m is None:
                continue
            dados["raw"].append(float(px[m].sum()))
            if dados.get("ring_mask") is not None:
                dados["ring"].append(float(px[dados["ring_mask"]].sum()))
    for dados in prep.values():
        dados.pop("mask", None)
        dados.pop("ring_mask", None)
    return prep


def curves(frames: list, cache, rois: list[Roi], info: nm.NMInfo | None = None,
           decay: bool = False, progress=None) -> list[Curve]:
    """Curvas atividade-tempo de todas as ROIs, já com fundo e (se pedido) decaimento."""
    if not frames:
        return []
    if info is None:
        info = nm.info_for_file(frames[0].path)
    idx = [f.frame_index for f in frames]
    tempos = np.asarray(info.mid_times_s(idx), float)
    dur = np.asarray([d / 1000.0 for d in _durations_of(info, idx)], float)
    if tempos.size != len(frames):                 # cabeçalho incompleto: 1 s por quadro
        tempos = np.arange(len(frames), dtype=float)
        dur = np.ones(len(frames), float)
    dados = frame_counts(frames, cache, rois, progress)
    por_nome = {r.name: r for r in rois}
    saida: list[Curve] = []
    for r in rois:
        d = dados.get(r.name, {})
        raw = np.asarray(d.get("raw", []), float)
        if raw.size != len(frames):
            saida.append(Curve(r.name, tempos, np.zeros(len(frames)), np.zeros(len(frames)),
                               np.zeros(len(frames)), dur, 0, r.background,
                               note=d.get("erro", "Não deu para medir esta ROI.")))
            continue
        fundo, nota = _background(r, d, raw, dados, por_nome, frames, cache, len(frames))
        limpo = np.clip(raw - fundo, 0, None)
        corrigido = False
        if decay:
            meia = nm.half_life_for(info)
            if meia > 0:
                limpo = nm.decay_correct(limpo, tempos, meia)
                corrigido = True
            else:
                nota = (nota + " " if nota else "") + "Sem meia-vida no cabeçalho: não corrigiu o decaimento."
        saida.append(Curve(r.name, tempos, limpo, raw, fundo, dur, int(d.get("pixels", 0)),
                           r.background, corrigido, nota.strip()))
    return saida


def _durations_of(info: nm.NMInfo, idx: list[int]) -> list[float]:
    todas = info.durations_ms()
    return [todas[i] if i < len(todas) else info.frame_duration_ms for i in idx]


def _background(r: Roi, d: dict, raw: np.ndarray, dados: dict, por_nome: dict,
                frames: list, cache, n: int) -> tuple[np.ndarray, str]:
    """Fundo de cada quadro e o aviso, quando o método pedido não pôde ser usado."""
    zero = np.zeros(n)
    px_alvo = int(d.get("pixels", 0))
    if r.background == "none" or px_alvo == 0:
        return zero, ""
    if r.background == "fraction":
        return raw * float(np.clip(r.fraction, 0.0, 0.95)), ""
    if r.background == "ring":
        anel = np.asarray(d.get("ring", []), float)
        px_anel = int(d.get("ring_pixels", 0))
        if anel.size != n or px_anel == 0:
            return zero, "Não coube anel de fundo em volta da ROI: fundo não subtraído."
        return anel / px_anel * px_alvo, ""
    if r.background == "roi":
        outra = por_nome.get(r.background_roi)
        dd = dados.get(r.background_roi, {})
        bruto = np.asarray(dd.get("raw", []), float)
        px_f = int(dd.get("pixels", 0))
        if outra is None or bruto.size != n or px_f == 0:
            return zero, f"Fundo não subtraído: não achei a ROI de fundo {r.background_roi}."
        return bruto / px_f * px_alvo, ""
    return zero, ""


# ------------------------------------------------------------------ números da curva
def peak(curve: Curve) -> tuple[float, float]:
    """(tempo do pico em s, valor do pico)."""
    if not curve.counts.size:
        return 0.0, 0.0
    i = curve.peak_index
    return float(curve.times_s[i]), float(curve.counts[i])


def half_time(curve: Curve, from_peak: bool = True) -> float | None:
    """Tempo, em segundos **depois do pico**, para cair à metade do pico.

    Devolve None quando a curva não chega à metade dentro do estudo — que é a resposta certa
    numa obstrução, e é diferente de "não calculei". Quem chama precisa dizer isso na tela.
    """
    if curve.counts.size < 2:
        return None
    i0 = curve.peak_index if from_peak else 0
    alvo = curve.counts[i0] / 2.0
    t, c = curve.times_s, curve.counts
    for i in range(i0 + 1, c.size):
        if c[i] <= alvo:
            if c[i - 1] == c[i]:
                return float(t[i] - t[i0])
            f = (c[i - 1] - alvo) / (c[i - 1] - c[i])       # interpola entre os dois quadros
            return float(t[i - 1] + f * (t[i] - t[i - 1]) - t[i0])
    return None


def integral(curve: Curve, t0_s: float, t1_s: float) -> float:
    """Área sob a curva entre dois instantes (trapézios), em contagens·s."""
    t, c = curve.times_s, curve.counts
    if t.size < 2:
        return 0.0
    dentro = (t >= t0_s) & (t <= t1_s)
    if dentro.sum() < 2:
        return 0.0
    return float(np.trapezoid(c[dentro], t[dentro]) if hasattr(np, "trapezoid")
                 else np.trapz(c[dentro], t[dentro]))


def value_at(curve: Curve, t_s: float) -> float:
    """Valor da curva num instante (interpolado)."""
    if not curve.counts.size:
        return 0.0
    return float(np.interp(t_s, curve.times_s, curve.counts))


def retention(curve: Curve, t_s: float, reference_s: float = 0.0) -> float | None:
    """% do valor de referência que ainda resta no instante pedido (esvaziamento gástrico)."""
    base = value_at(curve, reference_s) if reference_s else (
        float(curve.counts[0]) if curve.counts.size else 0.0)
    if base <= 0:
        return None
    return float(value_at(curve, t_s) / base * 100.0)


# ------------------------------------------------------------------ imagem condensada
def condensed(frames: list, cache, axis: str = "rows", roi: Roi | None = None,
              progress=None) -> np.ndarray:
    """Imagem condensada: um quadro por coluna, a anatomia no eixo vertical.

    Colapsa cada quadro numa linha (somando as colunas) e empilha os quadros lado a lado.
    É como se lê refluxo esofágico e trânsito: o tempo vira o eixo horizontal e dá para ver
    o bolo subindo e descendo numa figura só, sem rodar o cine.
    """
    if not frames:
        return np.zeros((1, 1), np.float32)
    shape = cache.get(frames[0]).pixels.shape[:2]
    m = None
    if roi is not None:
        res = roi.mask(shape)
        if res is not None:
            sl, mm = res
            m = np.zeros(shape, bool)
            m[sl] = mm
    colunas = []
    eixo = 1 if axis == "rows" else 0
    for i, f in enumerate(frames):
        if progress is not None and progress(i, len(frames)) is False:
            break
        px = cache.get(f).pixels
        if px.ndim != 2:
            px = px.astype(np.float64).mean(axis=2)
        px = px.astype(np.float32, copy=False)
        if m is not None:
            px = np.where(m, px, 0.0)
        colunas.append(px.sum(axis=eixo))
    return np.stack(colunas, axis=1) if colunas else np.zeros((1, 1), np.float32)


# ------------------------------------------------------------------ exportação
def to_csv(curvas: list[Curve], cps: bool = True) -> str:
    """Tabela de contagens para planilha: uma linha por quadro, uma coluna por ROI."""
    if not curvas:
        return ""
    ref = curvas[0]
    cab = ["tempo_s", "duracao_s"] + [f"{c.name}{'_cps' if cps else '_contagens'}" for c in curvas]
    linhas = [";".join(cab)]
    for i in range(ref.times_s.size):
        vals = [f"{ref.times_s[i]:.2f}", f"{ref.durations_s[i]:.2f}"]
        for c in curvas:
            v = c.cps[i] if cps else c.counts[i]
            vals.append(f"{float(v):.3f}" if i < c.counts.size else "")
        linhas.append(";".join(vals))
    return "\n".join(linhas)
