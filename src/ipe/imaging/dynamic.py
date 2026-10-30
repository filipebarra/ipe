"""Avaliação dinâmica (RM de mama): mapas paramétricos MSI, PEI, SER e curvas tempo-intensidade.

Definições (sinal S(t), S0 = fase pré-contraste; realce relativo E(t) = (S − S0)/S0 × 100%):

* **MSI** (maximum slope of increase): maior inclinação entre fases consecutivas,
  em %/min (ou sinal/min no modo absoluto).
* **PEI** (positive enhancement integral): integral (trapézios) da parte positiva da
  curva de realce, em %·min (ou sinal·min).
* **SER** (signal enhancement ratio, Hylton): (S_inicial − S0) / (S_tardia − S0).
  > 1,1 washout · 0,9–1,1 platô · < 0,9 persistente. Só onde o realce inicial passa
  do limiar; fora dele o mapa fica preto.
* **Realce inicial** (%) na fase inicial, **subtração** (fase inicial − pré) e **tempo até o pico**.

As fases podem vir de séries separadas (uma por fase) ou de uma série só com as
fases repetidas em cada posição. Ferramenta de pesquisa e ensino.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np

from ipe.imaging.phases import compatible, phase_time
from ipe.imaging.series import Frame, FrameCache, FrameImage

log = logging.getLogger(__name__)

# chave -> (nome curto, descrição, unidade relativa, unidade absoluta, tabela de cores padrão)
MAPS: dict[str, tuple[str, str, str, str, str]] = {
    "msi": ("MSI", "Inclinação máxima de subida", "%/min", "sinal/min", "rainbow"),
    "pei": ("PEI", "Integral do realce positivo", "%·min", "sinal·min", "rainbow"),
    "ser": ("SER", "Razão de realce do sinal", "", "", "ser"),
    "ei": ("Realce inicial", "Realce na fase inicial", "%", "sinal", "rainbow"),
    "sub": ("Subtração", "Fase inicial − pré-contraste", "sinal", "sinal", ""),
    "ttp": ("Tempo até o pico", "Tempo até o pico", "s", "s", "rainbow"),
    "cin": ("Cinética", "Mapa cinético em 6 classes", "classe", "classe", "cinetico"),
}
MASKED = -1.0

# Classes do mapa cinético, na ordem do valor do pixel (0 = sem cor).
CLASSES = ["sem cor", "médio/persistente", "médio/platô", "médio/washout",
           "rápido/persistente", "rápido/platô", "rápido/washout"]


def shift_image(img: np.ndarray, dy: float, dx: float) -> np.ndarray:
    """img amostrada em (y + dy, x + dx), bilinear; bordas repetidas."""
    h, w = img.shape
    out = img
    if abs(dy) > 1e-3:
        y0 = int(np.floor(dy))
        fy = dy - y0
        r0 = np.clip(np.arange(h) + y0, 0, h - 1)
        r1 = np.clip(r0 + 1, 0, h - 1)
        out = out[r0] * (1 - fy) + out[r1] * fy
    if abs(dx) > 1e-3:
        x0 = int(np.floor(dx))
        fx = dx - x0
        c0 = np.clip(np.arange(w) + x0, 0, w - 1)
        c1 = np.clip(c0 + 1, 0, w - 1)
        out = out[:, c0] * (1 - fx) + out[:, c1] * fx
    return out.astype(np.float32, copy=False)


def box3(a: np.ndarray) -> np.ndarray:
    """Média 3×3 nos dois últimos eixos (bordas repetidas)."""
    p = np.pad(a, [(0, 0)] * (a.ndim - 2) + [(1, 1), (1, 1)], mode="edge")
    h, w = a.shape[-2:]
    acc = np.zeros(a.shape, np.float32)
    for dy in range(3):
        for dx in range(3):
            acc += p[..., dy:dy + h, dx:dx + w]
    return acc / 9.0


def split_single_series(frames: list[Frame]) -> list[list[Frame]] | None:
    """Série com as fases no mesmo arquivo de série: k quadros em cada posição -> k fases."""
    if len(frames) < 4 or any(f.position is None or f.orientation is None for f in frames):
        return None
    n = frames[0].normal
    keys = [round(float(np.dot(f.position, n)), 1) for f in frames]
    groups: OrderedDict[float, list[Frame]] = OrderedDict()
    for k, f in zip(keys, frames):
        groups.setdefault(k, []).append(f)
    counts = {len(g) for g in groups.values()}
    if len(counts) != 1 or counts == {1}:
        return None
    k = counts.pop()
    for g in groups.values():
        g.sort(key=lambda f: (f.acquisition_time, f.instance_number, f.frame_index))
    return [[g[j] for g in groups.values()] for j in range(k)]


def split_por_aquisicao(frames: list[Frame]) -> list[list[Frame]] | None:
    """Série com mais de uma **aquisição** dentro: cada horário de aquisição é uma fase.

    Medido no acervo: o caso real da TC não é "k quadros em cada posição" (que é o que
    `split_single_series` acha). O "ABDOMEN TRIFASICO" dele tem 142 imagens em **dois** horários —
    52 imagens de -274 a -19 mm e 90 de -464 a -19 mm —, cada uma uma pilha inteira, com
    coberturas diferentes. Por isso quem manda aqui é o horário, não a contagem por posição.

    Recusa quando não é esse caso: um horário só, grupo pequeno demais, posição repetida dentro
    do grupo (aí é outra coisa) ou horários demais (aquisição contínua, não fases).
    """
    if len(frames) < 6 or any(f.position is None or f.orientation is None for f in frames):
        return None
    grupos: OrderedDict[str, list[Frame]] = OrderedDict()
    for f in frames:
        grupos.setdefault(str(f.acquisition_time or ""), []).append(f)
    if not 2 <= len(grupos) <= 12 or "" in grupos:
        return None
    n = frames[0].normal
    saida, faixas = [], []
    for _h, g in sorted(grupos.items()):
        if len(g) < 3:
            return None
        z = [round(float(np.dot(f.position, n)), 2) for f in g]
        if len(set(z)) != len(z):          # posição repetida dentro da fase: não é uma pilha
            return None
        faixas.append((min(z), max(z)))
        saida.append([f for _k, f in sorted(zip(z, g), key=lambda kv: kv[0])])
    # Fase é a **mesma** anatomia de novo; mesa de PET e estação de RM são regiões diferentes,
    # uma depois da outra. Medido no acervo: o TRIFÁSICO tem 100% de sobreposição entre as duas
    # aquisições, e as 7 mesas do PET de corpo inteiro quase nenhuma.
    for i, (a0, a1) in enumerate(faixas):
        for b0, b1 in faixas[i + 1:]:
            comum = min(a1, b1) - max(a0, b0)
            menor = min(a1 - a0, b1 - b0)
            if menor <= 0 or comum < 0.6 * menor:
                return None
    return saida


def separar_fases(frames: list[Frame]) -> list[list[Frame]] | None:
    """Reparte em fases uma série que traz várias: por posição repetida ou por aquisição."""
    return split_single_series(frames) or split_por_aquisicao(frames)


@dataclass
class DynamicSet:
    phases: list[list[Frame]]
    labels: list[str]
    times: list[float] = field(default_factory=list)     # s desde a 1ª fase
    timed: bool = True

    def __post_init__(self) -> None:
        if not self.times:
            ts = [phase_time(ph) for ph in self.phases]
            if all(t is not None for t in ts) and len(set(ts)) == len(ts):
                order = sorted(range(len(ts)), key=lambda i: ts[i])
                self.phases = [self.phases[i] for i in order]
                self.labels = [self.labels[i] for i in order]
                ts = [ts[i] for i in order]
                self.times = [t - ts[0] for t in ts]
                self.timed = True
            else:
                self.times = [60.0 * i for i in range(len(self.phases))]
                self.timed = False

    @property
    def n_slices(self) -> int:
        return len(self.phases[0]) if self.phases else 0

    def check(self) -> str:
        """"" se as fases combinam; senão o motivo."""
        if len(self.phases) < 3:
            return "São necessárias pelo menos 3 fases (pré + 2 pós-contraste)."
        for ph, lab in zip(self.phases[1:], self.labels[1:]):
            ok, why = compatible(self.phases[0], ph, tol_mm=1.5)
            if not ok:
                return f"{lab}: {why}."
        return ""

    def default_early(self, pre: int = 0) -> int:
        """Fase pós-contraste mais próxima de 2 min após a pré (critério BI-RADS de fase inicial)."""
        post = list(range(pre + 1, len(self.phases)))
        if not post:
            return pre
        if not self.timed:
            return post[0]
        return min(post, key=lambda i: abs(self.times[i] - self.times[pre] - 120.0))


class DynamicMaps:
    """Calcula os mapas corte a corte (sob demanda, com cache)."""

    def __init__(self, dset: DynamicSet, cache: FrameCache, pre: int = 0, early: int | None = None,
                 late: int | None = None, threshold_pct: float = 50.0, noise_pct: float = 5.0,
                 relative: bool = True, threshold_all: bool = False, motion: bool = False, progress=None,
                 rapido_pct: float = 100.0, tardio_pct: float = 10.0, sinal_min_pct: float = 10.0):
        self.dset, self.cache = dset, cache
        self.pre = pre
        self.early = dset.default_early(pre) if early is None else early
        self.late = len(dset.phases) - 1 if late is None else late
        self.threshold_pct, self.noise_pct = threshold_pct, noise_pct
        # Limiares do mapa cinético. Vêm da convenção do CADstream (médio 50–100%, rápido > 100%,
        # tardio ±10%) e são **editáveis**: dependem de dose, velocidade de injeção, resolução
        # temporal e campo. O que valeu para a imagem fica escrito junto dela.
        self.rapido_pct, self.tardio_pct, self.sinal_min_pct = rapido_pct, tardio_pct, sinal_min_pct
        self.relative, self.threshold_all = relative, threshold_all
        self.source_path = dset.phases[0][0].path
        self._stacks: OrderedDict[int, np.ndarray] = OrderedDict()
        self._maps: OrderedDict[int, dict] = OrderedDict()
        self._windows: dict[str, tuple[float, float]] = {}
        self._noise: float | None = None
        self._ref: float | None = None
        first = cache.get(dset.phases[0][0])
        self.shape = first.pixels.shape[:2]
        self.pixel_spacing = first.pixel_spacing
        self.header = {"Modality": first.header.get("Modality", "MR") or "MR"}
        # deslocamento (cortes, linhas, colunas) de cada fase em relação à pré-contraste
        self.shifts: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(dset.phases)
        if motion:
            self.estimate_motion(progress)

    # ------------------------------------------------------------ movimento
    def _small_volume(self, i: int, zs: list[int], f: int) -> np.ndarray:
        ph = self.dset.phases[i]
        vol = np.stack([self.cache.get(ph[min(k, len(ph) - 1)]).pixels[::f, ::f].astype(np.float32) for k in zs])
        lo, hi = np.percentile(vol, 2), np.percentile(vol, 99.5)
        vol = np.clip((vol - lo) / max(hi - lo, 1e-6), 0, 1)
        return vol - vol.mean()

    def estimate_motion(self, progress=None) -> list[tuple[float, float, float]]:
        """Translação 3D de cada fase em relação à pré (correlação de fase em volume reduzido).
        `progress(feitas, total)` pode devolver False para cancelar."""
        from ipe.imaging.register import phase_shift
        n = self.n
        m = max(1, int(np.ceil(n / 96)))
        zs = list(range(0, n, m))
        f = max(1, int(np.ceil(max(self.shape) / 128)))
        ref = self._small_volume(self.pre, zs, f)
        total = len(self.dset.phases)
        shifts = []
        for i in range(total):
            if progress and progress(i, total) is False:
                break
            if i == self.pre:
                shifts.append((0.0, 0.0, 0.0))
                continue
            (dz, dy, dx), _score = phase_shift(ref, self._small_volume(i, zs, f))
            s = (dz * m, dy * f, dx * f)
            shifts.append(tuple(0.0 if abs(v) < 0.3 else float(v) for v in s))
        if len(shifts) == total:
            self.shifts = shifts
            self._stacks.clear()
            self._maps.clear()
            self._windows.clear()
        return self.shifts

    @property
    def motion_corrected(self) -> bool:
        return any(any(v) for v in self.shifts)

    # ------------------------------------------------------------ dados
    @property
    def n(self) -> int:
        return self.dset.n_slices

    def stack(self, k: int) -> np.ndarray:
        """(fases, H, W) float32 do corte k."""
        if k in self._stacks:
            self._stacks.move_to_end(k)
            return self._stacks[k]
        imgs = []

        def read(ph, kk):
            px = self.cache.get(ph[int(np.clip(kk, 0, len(ph) - 1))]).pixels
            if px.ndim != 2 or px.shape != self.shape:
                return np.zeros(self.shape, np.float32)
            return px.astype(np.float32, copy=False)
        for ph, (dz, dy, dx) in zip(self.dset.phases, self.shifts):
            if not (dz or dy or dx):
                imgs.append(read(ph, k))
                continue
            z = k + dz
            z0 = int(np.floor(z))
            fz = z - z0
            px = read(ph, z0) if fz < 1e-3 else read(ph, z0) * (1 - fz) + read(ph, z0 + 1) * fz
            imgs.append(shift_image(px, dy, dx))
        st = np.stack(imgs)
        self._stacks[k] = st
        while len(self._stacks) > 12:
            self._stacks.popitem(last=False)
        return st

    def reference_level(self) -> float:
        """Sinal "cheio" do exame: percentil 99,5 do máximo entre as fases.

        Serve de régua para a máscara de tecido. O mapa cinético é em **porcentagem do
        pré-contraste**, e onde o pré é quase zero (ar, pulmão) qualquer variação vira centenas
        por cento: sem máscara, 36 a 44% do campo sai colorido nas RM de mama medidas.
        """
        if self._ref is None:
            n = self.n
            vals = []
            for k in sorted({n // 3, n // 2, (2 * n) // 3}):
                vals.append(float(np.percentile(self.stack(k).max(axis=0), 99.5)))
            self._ref = max(vals) if vals else 1.0
        return self._ref

    def noise_level(self) -> float:
        if self._noise is None:
            n = self.n
            vals = []
            for k in sorted({n // 3, n // 2, (2 * n) // 3}):
                st = self.stack(k)
                vals.append(np.percentile(st.max(axis=0), 99.5))
            self._noise = float(max(vals)) * self.noise_pct / 100.0
        return self._noise

    def times_min(self) -> np.ndarray:
        return np.asarray(self.dset.times, dtype=np.float32) / 60.0

    # ------------------------------------------------------------ mapas
    def compute(self, k: int) -> dict[str, np.ndarray]:
        if k in self._maps:
            self._maps.move_to_end(k)
            return self._maps[k]
        st = self.stack(k)
        t = self.times_min()
        s0 = st[self.pre]
        noise = self.noise_level()
        valid = st.mean(axis=0) > max(noise, 1e-6)       # média das fases: o ruído do ar não passa
        base = np.maximum(s0, max(noise, 1e-6))
        post = st[self.pre:]
        tp = t[self.pre:]
        diff = post - s0
        e = diff / base * 100.0 if self.relative else diff
        with np.errstate(divide="ignore", invalid="ignore"):
            slopes = np.diff(e, axis=0) / np.maximum(np.diff(tp), 1e-6)[:, None, None]
        msi = np.clip(slopes.max(axis=0), 0, None) if len(slopes) else np.zeros(self.shape, np.float32)
        pos = np.clip(e, 0, None)
        pei = (0.5 * (pos[1:] + pos[:-1]) * np.diff(tp)[:, None, None]).sum(axis=0)
        s1, s2 = st[self.early], st[self.late]
        ei_rel = (s1 - s0) / base * 100.0
        enh = valid & (ei_rel >= self.threshold_pct)
        with np.errstate(divide="ignore", invalid="ignore"):
            ser = (s1 - s0) / (s2 - s0)
        ser = np.where(np.isfinite(ser) & (s2 - s0 > 0), np.clip(ser, 0, 3), 3.0)
        ser = np.where(enh, ser, MASKED)
        ei = ei_rel if self.relative else (s1 - s0)
        ttp = np.asarray(self.dset.times, np.float32)[self.pre + np.argmax(post, axis=0)] - self.dset.times[self.pre]
        out = {"msi": msi, "pei": pei, "ser": ser, "ei": ei, "sub": s1 - s0, "ttp": ttp,
               "cin": self._cinetica(st, s0, base, valid)}
        for key in ("msi", "pei", "ei", "ttp"):
            m = enh if self.threshold_all else valid
            out[key] = np.where(m, out[key], 0.0).astype(np.float32)
        out["ser"] = out["ser"].astype(np.float32)
        out["sub"] = out["sub"].astype(np.float32)
        out["cin"] = out["cin"].astype(np.float32)
        self._maps[k] = out
        while len(self._maps) > 24:
            self._maps.popitem(last=False)
        return out

    def _cinetica(self, st: np.ndarray, s0: np.ndarray, base: np.ndarray, valid: np.ndarray) -> np.ndarray:
        """Classe de cada voxel: 0 sem cor, 1–3 realce médio, 4–6 realce rápido.

        **Pico é a fase inicial escolhida, não o máximo voxel a voxel.** Com o máximo, o tardio
        nunca supera o pico e "persistente" fica impossível por construção — foi assim que a
        primeira medição no acervo deu 0,00% de persistente em todos os exames.
        """
        tecido = valid & (s0 >= self.reference_level() * self.sinal_min_pct / 100.0)
        pico, tardio = st[self.early], st[self.late]
        realce = (pico - s0) / base * 100.0
        with np.errstate(divide="ignore", invalid="ignore"):
            var = (tardio - pico) / np.maximum(pico, 1e-6) * 100.0
        var = np.where(np.isfinite(var), var, 0.0)
        cls = np.zeros(s0.shape, np.float32)
        for faixa, (lo, hi) in enumerate(((self.threshold_pct, self.rapido_pct),
                                          (self.rapido_pct, np.inf))):
            m = tecido & (realce >= lo) & (realce < hi)
            cls = np.where(m & (var >= self.tardio_pct), 1 + faixa * 3, cls)
            cls = np.where(m & (np.abs(var) < self.tardio_pct), 2 + faixa * 3, cls)
            cls = np.where(m & (var <= -self.tardio_pct), 3 + faixa * 3, cls)
        return cls

    def legenda_cinetica(self) -> str:
        """Os limiares que produziram o mapa — o mapa sem eles é uma imagem bonita sem medida."""
        t = self.dset.times
        # Duas frases inteiras, juntadas sem literal no meio: padrão de tradução com mais de
        # seis buracos não é extraído, e padrão que começa com buraco sequestra outros textos.
        limiares = (f"Realce médio de {self.threshold_pct:.0f} a {self.rapido_pct:.0f}%, rápido "
                    f"acima disso; tardio ±{self.tardio_pct:.0f}%; tecido com pré-contraste de pelo "
                    f"menos {self.sinal_min_pct:.0f}% do sinal de referência.")
        fases = (f"Pico na fase {self.early} ({t[self.early] - t[self.pre]:.0f} s) e tardia na "
                 f"fase {self.late} ({t[self.late] - t[self.pre]:.0f} s).")
        return " ".join((limiares, fases))

    def classe_cinetica(self, valores: np.ndarray) -> str:
        """A classe de uma curva, com os mesmos limiares do mapa — número e cor não podem divergir."""
        v = np.asarray(valores, float)
        s0 = v[self.pre]
        base = s0 if abs(s0) > 1e-6 else 1e-6
        realce = (v[self.early] - s0) / abs(base) * 100.0
        pico = v[self.early]
        var = (v[self.late] - pico) / (abs(pico) if abs(pico) > 1e-6 else 1e-6) * 100.0
        if realce < self.threshold_pct:
            return CLASSES[0]
        faixa = 0 if realce < self.rapido_pct else 1
        if var >= self.tardio_pct:
            return CLASSES[1 + faixa * 3]
        if abs(var) < self.tardio_pct:
            return CLASSES[2 + faixa * 3]
        return CLASSES[3 + faixa * 3]

    def window(self, kind: str) -> tuple[float, float]:
        if kind == "cin":
            # 7 faixas chapadas (0 = sem cor, 1–6 = as classes). O nível 3,0 e não 3,5 põe cada
            # classe no **meio** da sua faixa de cor: com 3,5 a classe caía exatamente na emenda
            # entre duas faixas e a última saía com a cor da anterior.
            return 7.0, 3.0
        if kind == "ser":
            return 2.0, 1.0               # 0 a 2: < 0,9 persistente, > 1,1 washout
        if kind not in self._windows:
            n = self.n
            vals = []
            for k in sorted({n // 3, n // 2, (2 * n) // 3}):
                m = self.compute(k)[kind]
                v = m[m > 0] if kind != "sub" else m
                if v.size:
                    vals.append(np.percentile(v, 99.5 if kind != "sub" else 99.8))
            hi = max(vals) if vals else 1.0
            if kind == "sub":
                self._windows[kind] = (max(hi, 1.0), max(hi, 1.0) / 3)
            else:
                self._windows[kind] = (max(hi, 1e-3), max(hi, 1e-3) / 2)
        return self._windows[kind]

    def image(self, kind: str, k: int) -> FrameImage:
        px = self.compute(k)[kind]
        return FrameImage(px, False, self.window(kind), self.pixel_spacing, "PixelSpacing", "MONOCHROME2",
                          dict(self.header))

    def phase_frames(self, i: int) -> list[Frame]:
        return self.dset.phases[i]

    def frames(self, kind: str) -> list[Frame]:
        ref = self.dset.phases[0]
        return [Frame(path=f.path, frame_index=k, sop_uid="", instance_number=k + 1, position=f.position,
                      orientation=f.orientation, provider=lambda kk, kd=kind: self.image(kd, kk))
                for k, f in enumerate(ref)]

    def volume_do_mapa(self, kind: str = "ei", progresso=None, so_tecido: bool = False):
        """Monta um volume 3D de um mapa (realce no pico, classe cinética…), na geometria da série.

        É o que permite crescer a lesão em três dimensões sobre o **realce**, e não sobre o sinal
        bruto: no sinal bruto a gordura é tão clara quanto a lesão.
        """
        from ipe.imaging.volume import Volume, VolumeError
        ref = self.dset.phases[self.pre]
        if len(ref) < 3 or ref[0].position is None or ref[0].orientation is None:
            raise VolumeError("A dinâmica precisa de pelo menos 3 cortes com posição.")
        limiar_tecido = self.reference_level() * self.sinal_min_pct / 100.0 if so_tecido else None
        dados = np.empty((self.n, *self.shape), np.float32)
        for k in range(self.n):
            px = self.compute(k)[kind]
            if limiar_tecido is not None:
                # Fora do tecido o realce em porcentagem explode (pré ≈ 0), e um voxel de ruído
                # com 3.000% vira o "máximo da lesão" e derruba o limiar relativo: medindo no
                # acervo, um exame inteiro não segmentava nada por causa disso.
                px = np.where(self.stack(k)[self.pre] >= limiar_tecido, px, 0.0)
            dados[k] = px
            if progresso is not None and not progresso(k + 1, self.n):
                raise VolumeError("Cancelado.")
        ori = np.asarray(ref[0].orientation, float)
        passo = np.asarray(ref[1].position, float) - np.asarray(ref[0].position, float)
        rs, cs = self.pixel_spacing or (1.0, 1.0)
        return Volume(data=dados, origin=np.asarray(ref[0].position, float), row_dir=ori[:3],
                      col_dir=ori[3:], slice_vec=passo, dx=float(cs), dy=float(rs),
                      window=None, source_path=self.source_path)

    def volume_da_fase(self, i: int | None = None, progresso=None):
        """Volume de uma fase (padrão: a inicial/pico), na grade do mapa — a mesma da lesão.

        É a imagem anatômica da captura da lesão: a máscara da segmentação nasce na grade da
        pré-contraste, e a fase vem de `stack()`, que já aplica a correção de movimento — então
        a borda desenhada cai no lugar certo nas três direções. Guarda só a última pedida (~100 MB).
        """
        from ipe.imaging.volume import Volume, VolumeError
        i = self.early if i is None else int(i)
        guardado = getattr(self, "_vol_fase", None)
        if guardado is not None and guardado[0] == i:
            return guardado[1]
        ref = self.dset.phases[self.pre]
        if len(ref) < 3 or ref[0].position is None or ref[0].orientation is None:
            raise VolumeError("A dinâmica precisa de pelo menos 3 cortes com posição.")
        dados = np.empty((self.n, *self.shape), np.float32)
        for k in range(self.n):
            dados[k] = self.stack(k)[i]
            if progresso is not None and not progresso(k + 1, self.n):
                raise VolumeError("Cancelado.")
        ori = np.asarray(ref[0].orientation, float)
        passo = np.asarray(ref[1].position, float) - np.asarray(ref[0].position, float)
        rs, cs = self.pixel_spacing or (1.0, 1.0)
        vol = Volume(data=dados, origin=np.asarray(ref[0].position, float), row_dir=ori[:3],
                     col_dir=ori[3:], slice_vec=passo, dx=float(cs), dy=float(rs),
                     window=None, source_path=self.source_path)
        self._vol_fase = (i, vol)
        return vol

    def curva_da_lesao(self, mask: np.ndarray, offset) -> np.ndarray | None:
        """Sinal médio da lesão em cada fase (todos os voxels dela, em todos os cortes).

        É a curva que vai para a captura: a da lesão inteira, não a do pixel mais suspeito nem a
        de uma ROI num corte só.
        """
        m = np.asarray(mask, bool)
        if not m.any():
            return None
        k0, j0, i0 = (int(v) for v in offset)
        soma = np.zeros(len(self.dset.phases), np.float64)
        n = 0
        for dk in range(m.shape[0]):
            sl = m[dk]
            if not sl.any():
                continue
            k = k0 + dk
            if not 0 <= k < self.n:
                continue
            st = self.stack(k)
            bloco = st[:, j0:j0 + sl.shape[0], i0:i0 + sl.shape[1]]
            sel = sl[:bloco.shape[1], :bloco.shape[2]]
            soma += bloco[:, sel].sum(axis=1)
            n += int(sel.sum())
        return (soma / n).astype(np.float32) if n else None

    def mascara_da_mama(self, progresso=None):
        """(máscara booleana da mama, explicação). Monta só o pré-contraste, corte a corte."""
        from ipe.imaging.mama_mascara import mascara_da_mama
        from ipe.imaging.volume import VolumeError
        ref = self.dset.phases[self.pre]
        pre = np.empty((self.n, *self.shape), np.float32)
        for k in range(self.n):
            pre[k] = self.stack(k)[self.pre]
            if progresso is not None and not progresso(k + 1, self.n):
                raise VolumeError("Cancelado.")
        return mascara_da_mama(pre, self.reference_level(), ref[0].orientation,
                               self.pixel_spacing or (1.0, 1.0), self.sinal_min_pct)

    def referencias_da_mama(self, progresso=None):
        """Pele, limite posterior e mamilo deste exame, em mm no paciente (uma vez por exame).

        Monta o pré-contraste inteiro, como a máscara da mama: a pele e a parede são forma do
        tórax, não detalhe de um corte. Guardado na instância porque medir a segunda lesão com
        isto já pronto leva 0,05 s — e montar leva uns 15.
        """
        from ipe.imaging import mama_distancias as MD
        from ipe.imaging.volume import VolumeError
        if getattr(self, "_refs_mama", None) is not None:
            return self._refs_mama
        ref = self.dset.phases[self.pre]
        if len(ref) < 2 or ref[0].position is None or ref[0].orientation is None:
            raise VolumeError("As distâncias precisam de cortes com posição e orientação.")
        total = self.n + 2
        pre = np.empty((self.n, *self.shape), np.float32)
        for k in range(self.n):
            pre[k] = self.stack(k)[self.pre]
            if progresso is not None and not progresso(k + 1, total):
                raise VolumeError("Cancelado.")
        nivel = self.reference_level()
        corpo = pre >= nivel * float(self.sinal_min_pct) / 100.0
        pos = np.asarray([f.position for f in ref], float)
        passo = pos[1] - pos[0]
        rs, cs = self.pixel_spacing or (1.0, 1.0)
        afim = MD.afim_do_volume(pos[0], ref[0].orientation, cs, rs, passo)
        def passo_refs(feito, _t):
            return progresso is None or progresso(self.n + feito, total)
        self._refs_mama = MD.construir(corpo, afim, ref[0].orientation, passo, passo_refs)
        return self._refs_mama

    def numeros_do_exame(self, progresso=None):
        """Realce de fundo do parênquima e angiovolume da mama inteira.

        Vai corte a corte de propósito: guardar pré, pico e classes inteiros seriam uns 300 MB
        numa RM de mama do acervo. Só o pré fica na memória, porque a máscara precisa da forma
        do tórax; o resto entra na conta e sai.
        """
        from ipe.imaging import mama_mascara
        from ipe.imaging.cad_mama import medir_exame
        from ipe.imaging.volume import VolumeError
        ref = self.dset.phases[self.pre]
        if len(ref) < 2 or ref[0].position is None:
            raise VolumeError("A dinâmica precisa de cortes com posição para medir o exame.")
        def passo(feitos, total):
            return progresso(feitos, total * 2) if progresso is not None else True
        mascara, det = self.mascara_da_mama(passo)
        rs, cs = self.pixel_spacing or (1.0, 1.0)
        espessura = float(np.linalg.norm(np.asarray(ref[1].position, float)
                                         - np.asarray(ref[0].position, float)))
        voxel_ml = float(rs) * float(cs) * espessura / 1000.0
        pre = np.empty((self.n, *self.shape), np.float32)
        pico = np.empty_like(pre)
        classes = np.empty((self.n, *self.shape), np.uint8)
        for k in range(self.n):
            st = self.stack(k)
            pre[k], pico[k] = st[self.pre], st[self.early]
            classes[k] = self.compute(k)["cin"].astype(np.uint8)
            if progresso is not None and not progresso(self.n + k + 1, self.n * 2):
                raise VolumeError("Cancelado.")
        e = medir_exame(pre, pico, classes, mascara, voxel_ml, det.get("texto", ""))
        if det.get("modo") != mama_mascara.MODO_PAREDE:
            e.avisos.append("Sem o corte na parede torácica, estes números incluem tórax e coração.")
        e.avisos.append(self.legenda_cinetica())
        return e

    def plane(self, kind: str) -> "MapPlane":
        return MapPlane(self, kind)

    # ------------------------------------------------------------ curvas
    def curve(self, k: int, mask_slices=None, mask=None, point: tuple[float, float] | None = None,
              radius: int = 1) -> np.ndarray | None:
        """Média por fase: numa ROI (fatias + máscara de roi_mask) ou em (2r+1)² pixels em volta do ponto."""
        st = self.stack(k)
        if point is not None:
            h, w = self.shape
            x, y = int(np.floor(point[0])), int(np.floor(point[1]))
            if not (0 <= x < w and 0 <= y < h):
                return None
            block = st[:, max(0, y - radius):y + radius + 1, max(0, x - radius):x + radius + 1]
            return block.reshape(len(st), -1).mean(axis=1)
        if mask_slices is None or mask is None or not mask.any():
            return None
        sub = st[:, mask_slices[0], mask_slices[1]]
        return sub[:, mask].mean(axis=1)

    def worst_pixel(self, k: int, mask_slices, mask) -> tuple[tuple[float, float], np.ndarray] | None:
        """Pixel mais suspeito da ROI (média 3×3), entre os que passam do limiar de realce inicial:
        pior tipo de curva pelo SER (washout > platô > persistente) e, no mesmo tipo, maior realce
        inicial; se nenhum passar do limiar, o de maior realce inicial.
        Devolve ((x, y) centro do pixel, curva)."""
        if mask is None or not mask.any():
            return None
        st = box3(self.stack(k)[:, mask_slices[0], mask_slices[1]])
        s0, s1, s2 = st[self.pre], st[self.early], st[self.late]
        base = np.maximum(s0, max(self.noise_level(), 1e-6))
        ei = (s1 - s0) / base * 100.0
        with np.errstate(divide="ignore", invalid="ignore"):
            ser = np.where(s2 - s0 > 0, (s1 - s0) / (s2 - s0), 3.0)
        ok = mask & (ei >= self.threshold_pct)
        if ok.any():
            cat = np.where(ser > 1.1, 3, np.where(ser >= 0.9, 2, 1))
            score = np.where(ok, cat * 1e6 + ei, -np.inf)
        else:
            score = np.where(mask, ei, -np.inf)
        yy, xx = np.unravel_index(int(np.argmax(score)), score.shape)
        y = yy + mask_slices[0].start
        x = xx + mask_slices[1].start
        return (x + 0.5, y + 0.5), st[:, yy, xx].copy()

    def curve_stats(self, values: np.ndarray) -> dict:
        """Números da curva: realce inicial/pico (%), SER, MSI, PEI e tipo (BI-RADS)."""
        from ipe.imaging.measure import tic_analysis
        t = np.asarray(self.dset.times, float)
        v = np.asarray(values, float)
        s0 = v[self.pre]
        base = s0 if abs(s0) > 1e-6 else 1e-6
        e = (v - s0) / abs(base) * 100.0
        tp = t[self.pre:] / 60.0
        ep = e[self.pre:] if self.relative else (v - s0)[self.pre:]
        slopes = np.diff(ep) / np.maximum(np.diff(tp), 1e-6) if len(ep) > 1 else np.array([0.0])
        pos = np.clip(ep, 0, None)
        pei = float((0.5 * (pos[1:] + pos[:-1]) * np.diff(tp)).sum()) if len(ep) > 1 else 0.0
        den = v[self.late] - s0
        ser = float((v[self.early] - s0) / den) if den > 0 else None
        tic = tic_analysis(list(t[self.pre:] - t[self.pre]), list(v[self.pre:]))
        return {"enh": e, "initial": float(e[self.early]), "peak": float(e.max()),
                "msi": float(max(slopes.max(), 0.0)), "pei": pei, "ser": ser,
                "type": tic.get("curve_type", ""), "initial_class": tic.get("initial_class", ""),
                # a mesma régua do mapa: o número da tabela e a cor do pixel não podem divergir
                "cinetica": self.classe_cinetica(v)}


class MapPlane:
    """Adaptador: o mapa se comporta como uma reconstrução (salvar como série, filme, exportar)."""

    supports_slab = False

    def __init__(self, maps: DynamicMaps, kind: str):
        self.maps, self.kind = maps, kind
        self.vol = SimpleNamespace(source_path=maps.source_path)
        self.axis = f"dyn-{kind}-{id(maps)}"
        self.name = MAPS[kind][0]
        self.label = f"{self.name} (dinâmica)"
        self.image_type = ["DERIVED", "SECONDARY", "DYNAMIC", kind.upper()]
        self.slab_mm, self.mode = 0.0, "avg"
        self.n = maps.n
        ref = maps.dset.phases[0]
        self._ref = ref
        ori = ref[0].orientation
        self.orientation = np.asarray(ori, float)
        rs, cs = maps.pixel_spacing or (1.0, 1.0)
        self.row_spacing, self.col_spacing = float(rs), float(cs)
        if len(ref) > 1:
            self.step_mm = float(np.linalg.norm(np.asarray(ref[1].position) - np.asarray(ref[0].position)))
        else:
            self.step_mm = 1.0

    def set_slab(self, *_a) -> None:
        pass

    def image(self, idx: int) -> FrameImage:
        return self.maps.image(self.kind, idx)

    def position(self, idx: int) -> np.ndarray:
        return np.asarray(self._ref[idx].position, float)

    def index_for_point(self, p: np.ndarray) -> int:
        d = [float(np.linalg.norm(np.asarray(f.position) - p)) for f in self._ref]
        return int(np.argmin(d))

    def frames(self) -> list[Frame]:
        return self.maps.frames(self.kind)
