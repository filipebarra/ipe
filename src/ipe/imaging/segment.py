"""Segmentação 3D semiautomática (sem scipy): crescimento de região a partir de um clique.

Métodos:
- "range": voxels conectados (6 vizinhos) com valor entre mín e máx (TC em HU, RM em sinal);
- "pet_pct": PET, limiar em % do SUVmáx da lesão (padrão 41%);
- "pet_abs": PET, SUV acima de um valor fixo (padrão 2,5);
- "realce_pct": RM dinâmica, limiar em % do realce **da própria lesão** (padrão 50%);
- "realce": RM dinâmica, realce no pico acima de um limiar fixo em %.

Nas duas, o crescimento é sobre o **realce**, não sobre o sinal bruto — no sinal bruto a gordura
é tão clara quanto a lesão. E o limiar relativo existe porque o fixo **vaza**: numa RM de mama
tudo o que realça está ligado pelos vasos, e um limiar de 50% a partir de um vaso cresce pela mama
inteira (medido no acervo: 996 mL e 120 mm de diâmetro, o que é a mama, não a lesão).

Resultado: máscara (recortada na caixa da lesão), volume em mL e estatísticas; no PET também
SUVmáx, SUVmédio, SUVpeak (esfera de 1 cm³) e TLG (SUVmédio × volume). TMTV = soma dos volumes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

METHODS = {"range": "Faixa de valores (mín–máx)", "pet_pct": "PET: % do SUVmáx", "pet_abs": "PET: SUV fixo",
           "realce_pct": "RM dinâmica: % do realce da própria lesão",
           "realce": "RM dinâmica: realce acima de um limiar fixo",
           "medsam2": "IA: contorno pela caixa (MedSAM2)"}


@dataclass
class SegResult:
    mask: np.ndarray                 # bool (nz, ny, nx) do recorte
    offset: tuple[int, int, int]     # (k0, j0, i0) do recorte no volume
    seed: tuple[int, int, int]       # (k, j, i)
    lo: float
    hi: float
    method: str
    voxels: int = 0
    ml: float = 0.0
    mean: float | None = None
    maximum: float | None = None
    minimum: float | None = None
    suvmax: float | None = None
    suvmean: float | None = None
    suvpeak: float | None = None
    tlg: float | None = None
    max_diam_mm: float | None = None
    eixos_mm: tuple[float, float, float] | None = None   # 3 eixos perpendiculares, do maior ao menor
    truncated: bool = False
    notes: list[str] = field(default_factory=list)
    sul_razao: float | None = None   # 0.99.60: massa magra / peso (SUL = SUV × razão)
    glic: float | None = None        # 0.99.88: glicemia ÷ 100 (SUVglic = SUV × glic)

    def summary(self) -> str:
        s = f"{self.ml:.2f} mL"
        if self.suvmax is not None:
            s += f" · SUVmáx {self.suvmax:.2f} · SUVméd {self.suvmean:.2f}"
            if self.suvpeak is not None:
                s += f" · SUVpeak {self.suvpeak:.2f}"
            s += f" · TLG {self.tlg:.1f}"
        elif self.mean is not None:
            s += f" · média {self.mean:.1f}"
        if self.eixos_mm:
            a, b, c = self.eixos_mm
            s += f" · eixos {a:.1f} × {b:.1f} × {c:.1f} mm"
        elif self.max_diam_mm:
            s += f" · maior eixo {self.max_diam_mm:.1f} mm"
        return s

    def meta(self) -> dict:
        d = {"ml": round(self.ml, 3), "lo": self.lo, "hi": self.hi, "method": self.method}
        for k in ("mean", "maximum", "suvmax", "suvmean", "suvpeak", "tlg", "max_diam_mm"):
            v = getattr(self, k)
            if v is not None:
                d[k] = round(float(v), 3)
        if self.sul_razao:
            for k in ("suvmax", "suvmean", "suvpeak"):
                if k in d:
                    d["sul" + k[3:]] = round(d[k] * self.sul_razao, 3)
        if self.glic:
            for k in ("suvmax", "suvmean", "suvpeak"):
                if k in d:
                    d["suvg" + k[3:]] = round(d[k] * self.glic, 3)
        if self.max_diam_mm:
            d["mm"] = round(self.max_diam_mm, 2)
        if self.eixos_mm:
            d["eixos_mm"] = [round(float(x), 1) for x in self.eixos_mm]
        return d


def tres_eixos(pontos_mm: np.ndarray, voxel_mm) -> tuple[float, float, float]:
    """Os três maiores eixos **perpendiculares entre si** da lesão, em mm, do maior para o menor.

    É a medida que o radiologista escreve no laudo, e não é a caixa nos eixos da série: uma lesão
    oblíqua tem caixa grande e eixos pequenos. O caminho é o clássico:

    1. **Eixo 1** — a maior distância entre dois pontos da lesão.
    2. **Eixo 2** — projeta tudo no plano perpendicular ao eixo 1 e mede a maior distância ali.
    3. **Eixo 3** — a extensão na direção perpendicular aos dois primeiros.

    Cada eixo leva **um voxel inteiro projetado na própria direção** (meio em cada ponta): sem
    isso, uma lesão de um corte só mede zero na direção do corte.
    """
    voxel = np.abs(np.asarray(voxel_mm, float))
    minimo = float(voxel.min()) if voxel.size else 0.0
    pts = np.asarray(pontos_mm, float)
    if len(pts) < 2:
        return (minimo, minimo, minimo)
    if len(pts) > 1500:                      # o pareamento é O(n²): amostra estável (semente fixa)
        pts = pts[np.random.default_rng(0).choice(len(pts), 1500, replace=False)]

    def _par_mais_distante(q: np.ndarray) -> tuple[float, np.ndarray]:
        d2 = ((q[:, None, :] - q[None, :, :]) ** 2).sum(-1)
        a, b = np.unravel_index(int(np.argmax(d2)), d2.shape)
        v = q[b] - q[a]
        return float(np.linalg.norm(v)), v

    def _com_voxel(comp: float, u: np.ndarray) -> float:
        return comp + float(np.abs(u * voxel).sum())

    l1, v1 = _par_mais_distante(pts)
    if l1 < 1e-6:
        return (minimo, minimo, minimo)
    u1 = v1 / l1
    plano = pts - np.outer(pts @ u1, u1)          # tudo rebatido no plano perpendicular ao eixo 1
    l2, v2 = _par_mais_distante(plano)
    if l2 < 1e-6:
        u2 = np.array([1.0, 0.0, 0.0]) if abs(u1[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u2 = u2 - u1 * float(u2 @ u1)
        u2 /= np.linalg.norm(u2)
    else:
        u2 = v2 / l2
    u3 = np.cross(u1, u2)
    n3 = float(np.linalg.norm(u3))
    l3 = float(np.ptp(pts @ (u3 / n3))) if n3 > 1e-9 else 0.0
    if n3 > 1e-9:
        u3 = u3 / n3
    eixos = sorted([_com_voxel(l1, u1), _com_voxel(l2, u2), _com_voxel(l3, u3)], reverse=True)
    return (eixos[0], eixos[1], eixos[2])


def _grow(inside: np.ndarray, seed: tuple[int, int, int], max_iter: int = 100000) -> np.ndarray:
    """Componente conectada (6 vizinhos) de `inside` que contém a semente. Dilatação restrita à caixa."""
    reg = np.zeros_like(inside)
    if not inside[seed]:
        return reg
    reg[seed] = True
    nz, ny, nx = inside.shape
    k0, k1, j0, j1, i0, i1 = seed[0], seed[0] + 1, seed[1], seed[1] + 1, seed[2], seed[2] + 1
    for _ in range(max_iter):
        a0, a1 = max(0, k0 - 1), min(nz, k1 + 1)
        b0, b1 = max(0, j0 - 1), min(ny, j1 + 1)
        c0, c1 = max(0, i0 - 1), min(nx, i1 + 1)
        r = reg[a0:a1, b0:b1, c0:c1]
        g = r.copy()
        g[1:] |= r[:-1]
        g[:-1] |= r[1:]
        g[:, 1:] |= r[:, :-1]
        g[:, :-1] |= r[:, 1:]
        g[:, :, 1:] |= r[:, :, :-1]
        g[:, :, :-1] |= r[:, :, 1:]
        g &= inside[a0:a1, b0:b1, c0:c1]
        if g.sum() == r.sum():
            break
        reg[a0:a1, b0:b1, c0:c1] = g
        ks, js, is_ = np.nonzero(g.any(axis=(1, 2)))[0], np.nonzero(g.any(axis=(0, 2)))[0], np.nonzero(g.any(axis=(0, 1)))[0]
        k0, k1 = a0 + int(ks[0]), a0 + int(ks[-1]) + 1
        j0, j1 = b0 + int(js[0]), b0 + int(js[-1]) + 1
        i0, i1 = c0 + int(is_[0]), c0 + int(is_[-1]) + 1
    return reg


def default_range(data: np.ndarray, seed: tuple[int, int, int], modality: str = "") -> tuple[float, float]:
    """Faixa inicial: média ± 2,5 DP numa vizinhança 5×5×3 da semente (mín. ±40 HU na TC)."""
    k, j, i = seed
    sub = data[max(0, k - 1):k + 2, max(0, j - 2):j + 3, max(0, i - 2):i + 3].astype(np.float64)
    m, sd = float(sub.mean()), float(sub.std())
    half = max(2.5 * sd, 40.0 if modality.upper() == "CT" else 0.15 * abs(m) + 1.0)
    return m - half, m + half


def segment(vol, seed: tuple[int, int, int], method: str = "range", lo: float | None = None,
            hi: float | None = None, suv: float | None = None, pct: float = 41.0, abs_suv: float = 2.5,
            radius_mm: float = 120.0, modality: str = "") -> SegResult:
    """Segmenta a partir da semente (k, j, i) do volume `vol` (imaging.volume.Volume)."""
    data = vol.data
    nz, ny, nx = data.shape
    k, j, i = (int(np.clip(seed[0], 0, nz - 1)), int(np.clip(seed[1], 0, ny - 1)), int(np.clip(seed[2], 0, nx - 1)))
    dz = max(vol.dz, 1e-6)
    rk, rj, ri = int(radius_mm / dz), int(radius_mm / max(vol.dy, 1e-6)), int(radius_mm / max(vol.dx, 1e-6))
    k0, k1 = max(0, k - rk), min(nz, k + rk + 1)
    j0, j1 = max(0, j - rj), min(ny, j + rj + 1)
    i0, i1 = max(0, i - ri), min(nx, i + ri + 1)
    sub = data[k0:k1, j0:j1, i0:i1].astype(np.float32)
    s = (k - k0, j - j0, i - i0)
    notes: list[str] = []
    if method == "realce":
        lo, hi = (50.0 if lo is None else float(lo)), float("inf")
    elif method in ("pet_pct", "pet_abs", "realce_pct"):
        f = suv or 1.0
        if method.startswith("pet") and not suv:
            notes.append("sem fator de SUV: valores em unidades do arquivo")
        if method == "pet_abs":
            lo_v, hi_v = abs_suv / f, float("inf")
        else:
            # máximo local: na região acima de 50% do valor da semente, perto dela (até 3 cm).
            # Serve igual para SUV e para realce: o que importa é "quanto da própria lesão".
            r3 = (max(1, int(30 / dz)), max(1, int(30 / vol.dy)), max(1, int(30 / vol.dx)))
            box = sub[max(0, s[0] - r3[0]):s[0] + r3[0] + 1, max(0, s[1] - r3[1]):s[1] + r3[1] + 1,
                      max(0, s[2] - r3[2]):s[2] + r3[2] + 1]
            near = _grow(box >= 0.5 * float(sub[s]), (min(s[0], r3[0]), min(s[1], r3[1]), min(s[2], r3[2])))
            vmax = float(box[near].max()) if near.any() else float(sub[s])
            lo_v, hi_v = pct / 100.0 * vmax, float("inf")
        lo, hi = lo_v, hi_v
    else:
        if lo is None or hi is None:
            lo, hi = default_range(data, (k, j, i), modality)
    inside = (sub >= lo) & (sub <= hi)
    reg = _grow(inside, s)
    res = SegResult(np.zeros((0, 0, 0), bool), (k0, j0, i0), (k, j, i), float(lo), float(hi), method, notes=notes)
    if not reg.any():
        res.notes.append("a semente está fora da faixa")
        return res
    kk, jj, ii = np.nonzero(reg)
    a, b, c = kk.min(), jj.min(), ii.min()
    res.mask = reg[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
    res.offset = (k0 + int(a), j0 + int(b), i0 + int(c))
    res.truncated = (kk.min() == 0 and k0 > 0) or (kk.max() == reg.shape[0] - 1 and k1 < nz) or \
        (jj.min() == 0 and j0 > 0) or (jj.max() == reg.shape[1] - 1 and j1 < ny) or \
        (ii.min() == 0 and i0 > 0) or (ii.max() == reg.shape[2] - 1 and i1 < nx)
    if res.truncated:
        res.notes.append(f"a região passou de {radius_mm:.0f} mm do clique (cortada): ajuste a faixa")
    vals = sub[reg]
    res.voxels = int(vals.size)
    res.ml = res.voxels * vol.dx * vol.dy * dz / 1000.0
    res.mean, res.maximum, res.minimum = float(vals.mean()), float(vals.max()), float(vals.min())
    # os três eixos perpendiculares da lesão (o maior deles é o "maior eixo")
    pts = np.stack([ii, jj, kk], axis=1).astype(float)
    mm = pts @ vol.matrix().T
    if len(mm) > 1:
        res.eixos_mm = tres_eixos(mm, (vol.dx, vol.dy, dz))
        res.max_diam_mm = res.eixos_mm[0]
    if suv and method != "range" or (suv and modality.upper() == "PT"):
        res.suvmax = res.maximum * suv
        res.suvmean = res.mean * suv
        res.tlg = res.suvmean * res.ml
        res.suvpeak = suv_peak(vol, sub, reg, suv)
    return res


def de_mascara(vol, mascara: np.ndarray, seed: tuple[int, int, int], method: str = "medsam2",
               suv: float | None = None, modality: str = "") -> SegResult:
    """0.99.83: uma máscara pronta (do tamanho do volume, ou de outro método como o MedSAM2) com as mesmas
    medidas da segmentação por crescimento: volume, média, eixos, SUV, TLG."""
    m = np.asarray(mascara, bool)
    dz = max(vol.dz, 1e-6)
    res = SegResult(np.zeros((0, 0, 0), bool), (0, 0, 0), tuple(int(x) for x in seed), float("nan"), float("nan"),
                    method)
    if not m.any():
        return res
    kk, jj, ii = np.nonzero(m)
    a, b, c = kk.min(), jj.min(), ii.min()
    res.mask = m[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
    res.offset = (int(a), int(b), int(c))
    vals = vol.data[m].astype(np.float32)
    res.voxels = int(vals.size)
    res.ml = res.voxels * vol.dx * vol.dy * dz / 1000.0
    res.mean, res.maximum, res.minimum = float(vals.mean()), float(vals.max()), float(vals.min())
    res.lo, res.hi = res.minimum, res.maximum
    pts = np.stack([ii, jj, kk], axis=1).astype(float)
    mm = pts @ vol.matrix().T
    if len(mm) > 1:
        res.eixos_mm = tres_eixos(mm, (vol.dx, vol.dy, dz))
        res.max_diam_mm = res.eixos_mm[0]
    if suv and modality.upper() == "PT":
        sub = vol.data[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].astype(np.float32)
        res.suvmax = res.maximum * suv
        res.suvmean = res.mean * suv
        res.tlg = res.suvmean * res.ml
        res.suvpeak = suv_peak(vol, sub, res.mask, suv)
    return res


def box_mean_max(arr: np.ndarray, mask: np.ndarray, size: tuple[int, ...]) -> float | None:
    """Maior média de uma caixa (tamanho em voxels por eixo) centrada num voxel da máscara.
    Usa soma acumulada (rápido, sem scipy); fora da imagem conta só o que existe."""
    if not mask.any():
        return None
    a = arr.astype(np.float64)
    ones = np.ones_like(a)
    s, c = a, ones
    for ax in range(a.ndim):
        s = np.cumsum(s, axis=ax)
        c = np.cumsum(c, axis=ax)
    pad = [(1, 0)] * a.ndim
    s = np.pad(s, pad)
    c = np.pad(c, pad)
    idx = np.nonzero(mask)
    lo = [np.clip(i - k // 2, 0, n) for i, k, n in zip(idx, size, a.shape)]
    hi = [np.clip(i - k // 2 + k, 0, n) for i, k, n in zip(idx, size, a.shape)]

    def box(t):
        tot = 0.0
        for corner in range(2 ** a.ndim):
            sel, sign = [], 1
            for d in range(a.ndim):
                if corner >> d & 1:
                    sel.append(hi[d])
                else:
                    sel.append(lo[d])
                    sign = -sign
            tot = tot + sign * t[tuple(sel)]
        return tot
    sums, cnts = box(s), box(c)
    means = sums / np.maximum(cnts, 1)
    return float(means.max())


def suv_peak(vol, sub: np.ndarray, reg: np.ndarray, suv: float) -> float | None:
    """SUVpeak: maior média num cubo de 1 cm³ (10 mm de lado) centrado dentro da lesão."""
    size = tuple(max(1, int(round(10.0 / max(d, 1e-6)))) for d in (vol.dz, vol.dy, vol.dx))
    v = box_mean_max(sub, reg, size)
    return v * suv if v is not None else None


def mask_frames(vol, res: SegResult, color: tuple, label: str) -> list:
    """Máscaras por corte (imaging.overlays.MaskFrame) para desenhar no viewport."""
    from ipe.imaging.overlays import MaskFrame
    out = []
    k0, j0, i0 = res.offset
    ori = np.concatenate([vol.row_dir, vol.col_dir])
    for dk in range(res.mask.shape[0]):
        m = res.mask[dk]
        if not m.any():
            continue
        pos = vol.voxel_to_patient(i0, j0, k0 + dk)
        out.append(MaskFrame(m, color, label, pos, ori, (vol.dy, vol.dx)))
    return out


def tmtv(results: list[dict]) -> tuple[float, float]:
    """(TMTV em mL, TLG total) de uma lista de metas de segmentação de PET."""
    ml = sum(float(r.get("ml") or 0) for r in results if r.get("suvmean") is not None)
    tlg = sum(float(r.get("tlg") or 0) for r in results if r.get("suvmean") is not None)
    return ml, tlg
