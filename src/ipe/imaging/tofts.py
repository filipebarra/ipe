"""Farmacocinética da dinâmica com contraste (DCE): modelo de Tofts e Tofts estendido (0.100.67).

O que o modelo diz (Tofts et al., JMRI 1999): a concentração de contraste no tecido, Ct(t), vem do plasma, Cp(t):

    Tofts:            Ct(t) = Ktrans · ∫ Cp(u) · exp(−kep · (t − u)) du                kep = Ktrans / ve
    Tofts estendido:  Ct(t) = vp · Cp(t) + Ktrans · ∫ Cp(u) · exp(−kep · (t − u)) du

* **Ktrans** (min⁻¹): passagem do plasma para o espaço extravascular extracelular (fluxo × permeabilidade).
* **ve** (0–1): fração do espaço extravascular extracelular. **kep** (min⁻¹) = Ktrans / ve: a volta para o plasma.
* **vp** (0–1): fração de plasma (só no estendido).

Três passos, todos aqui e sem Qt:

1. **Sinal → concentração**: pela equação do gradiente-eco com spoiler (SPGR), com TR e ângulo do exame e o T1 do
   tecido antes do contraste (T10, suposto: não há mapa de T1 no exame de rotina). Sem TR ou ângulo, cai na
   aproximação linear (concentração proporcional ao realce relativo) — e avisa.
2. **Função de entrada arterial (AIF)**: a populacional de Parker (MRM 2006) ou a curva de uma ROI numa artéria.
3. **Ajuste**: mínimos quadrados lineares (Murase, MRM 2004), voxel a voxel, vetorizado.

**Limite honesto**: o modelo pede uma imagem a cada 5–15 s. A RM de mama de rotina faz uma fase a cada 60–90 s: o
pico arterial não é amostrado, o T10 é suposto e a AIF é a populacional. Os números servem para comparar regiões e
exames do mesmo protocolo; **não** são Ktrans absoluto. `avisos()` diz isso com os números do exame.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MODELOS = {"tofts": "Tofts", "estendido": "Tofts estendido (com vp)"}
AIFS = {"parker": "Populacional (Parker)", "roi": "ROI numa artéria"}
#: chave -> (nome, descrição, unidade)
MAPAS = {
    "ktrans": ("Ktrans", "Passagem do plasma para o interstício (Tofts)", "1/min"),
    "ve": ("ve", "Fração do espaço extravascular extracelular (Tofts)", ""),
    "kep": ("kep", "Volta do interstício para o plasma: Ktrans / ve (Tofts)", "1/min"),
    "vp": ("vp", "Fração de plasma (Tofts estendido)", ""),
}
#: acima disto (s por fase) o Ktrans é só indicativo; acima de RESOLUCAO_ESTENDIDO o vp não tem sentido
RESOLUCAO_BOA = 15.0
RESOLUCAO_ESTENDIDO = 20.0
KTRANS_MAX, KEP_MAX = 5.0, 20.0          # min⁻¹: acima disso é ajuste que não fechou (ruído, vaso)


@dataclass
class Config:
    modelo: str = "tofts"
    aif: str = "parker"
    tr_ms: float = 0.0                    # 0 = não se sabe: aproximação linear
    angulo: float = 0.0                   # graus
    t10_ms: float = 1400.0                # T1 do tecido antes do contraste
    t10_sangue_ms: float = 1600.0
    r1: float = 4.5                       # relaxividade do contraste, 1/(mM·s)
    hematocrito: float = 0.42
    inicio_s: float = 0.0                 # início da injeção, em segundos depois da fase pré
    aif_sinal: list = field(default_factory=list)      # sinal da ROI arterial em todas as fases (aif = "roi")
    campo_t: float = 0.0

    def linear(self) -> bool:
        return not (self.tr_ms > 0 and 0 < self.angulo < 90)

    def para_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, (list, tuple, np.ndarray)) else v) for k, v in self.__dict__.items()}

    @classmethod
    def de_dict(cls, d: dict | None) -> "Config":
        c = cls()
        for k, v in (d or {}).items():
            if hasattr(c, k):
                setattr(c, k, list(v) if k == "aif_sinal" else v)
        return c


def t1_padrao(campo_t: float) -> tuple[float, float]:
    """(T1 do tecido fibroglandular, T1 do sangue) em ms, valores de literatura para 1,5 T e 3 T."""
    return (1450.0, 1650.0) if campo_t and campo_t >= 2.5 else (1250.0, 1450.0)


# ====================================================================== AIF
def aif_parker(t_min, hematocrito: float = 0.42) -> np.ndarray:
    """A função de entrada arterial populacional de Parker et al. (MRM 2006;56:993) — concentração no **plasma**
    (mM) para uma dose padrão de 0,1 mmol/kg; `t_min` em minutos desde o início da injeção (antes disso, zero)."""
    t = np.asarray(t_min, np.float64)
    a = (0.809, 0.330)
    tm = (0.17046, 0.365)
    sg = (0.0563, 0.132)
    alfa, beta, s, tau = 1.050, 0.1685, 38.078, 0.483
    cb = np.zeros_like(t)
    for an, tn, sn in zip(a, tm, sg):
        cb += an / (sn * np.sqrt(2 * np.pi)) * np.exp(-((t - tn) ** 2) / (2 * sn * sn))
    cb += alfa * np.exp(-beta * t) / (1.0 + np.exp(-s * (t - tau)))
    cb = np.where(t > 0, cb, 0.0)
    return cb / max(1.0 - hematocrito, 1e-3)


# ====================================================================== sinal → concentração
def concentracao(sinal, s0, cfg: Config, t10_ms: float | None = None) -> np.ndarray:
    """Concentração de contraste (mM) a partir do sinal `sinal` (fases no eixo 0) e do pré-contraste `s0`.

    SPGR: S ∝ sen α · (1 − E1) / (1 − E1 · cos α), E1 = exp(−TR / T1); 1/T1 = 1/T10 + r1 · C.
    Sem TR/ângulo: C ≈ realce relativo / (r1 · T10) (vale para realce pequeno)."""
    s = np.asarray(sinal, np.float64)
    b = np.maximum(np.asarray(s0, np.float64), 1e-6)
    t10 = (t10_ms if t10_ms is not None else cfg.t10_ms) / 1000.0
    r10 = 1.0 / max(t10, 1e-3)
    razao = s / b
    if cfg.linear():
        return (razao - 1.0) * r10 / cfg.r1
    tr = cfg.tr_ms / 1000.0
    ca = np.cos(np.deg2rad(cfg.angulo))
    e10 = np.exp(-tr * r10)
    k = (1.0 - e10) / (1.0 - e10 * ca)
    x = np.clip(razao * k, 0.0, 0.999)                   # x → 1: sinal saturado (T1 → 0)
    e1 = (1.0 - x) / (1.0 - x * ca)
    r1 = -np.log(np.clip(e1, 1e-6, 1.0)) / tr
    return (r1 - r10) / cfg.r1


# ====================================================================== ajuste
def _integral(y: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Integral acumulada (trapézios) ao longo do eixo 0; começa em 0."""
    dt = np.diff(t).reshape((-1,) + (1,) * (y.ndim - 1))
    passo = 0.5 * (y[1:] + y[:-1]) * dt
    return np.concatenate([np.zeros_like(y[:1]), np.cumsum(passo, axis=0)], axis=0)


def plasma(t_min: np.ndarray, cfg: Config, sinal_aif=None, s0_aif=None) -> tuple[np.ndarray, np.ndarray]:
    """(Cp nas fases, ∫Cp nas fases), mM e mM·min. Parker: a integral é feita numa malha fina (1 s), para a
    amostragem grossa das fases não comer o pico. ROI: do sinal medido (trapézios — é o que há)."""
    t = np.asarray(t_min, np.float64)
    if cfg.aif == "roi" and sinal_aif is not None and len(sinal_aif) == len(t):
        cb = concentracao(np.asarray(sinal_aif, float), float(s0_aif), cfg, cfg.t10_sangue_ms)
        cp = np.clip(cb, 0, None) / max(1.0 - cfg.hematocrito, 1e-3)
        return cp, _integral(cp, t)
    t0 = cfg.inicio_s / 60.0
    fim = float(t.max())
    fino = np.arange(0.0, max(fim, 1 / 60.0) + 1 / 60.0, 1 / 60.0)
    cpf = aif_parker(fino - t0, cfg.hematocrito)
    intf = _integral(cpf, fino)
    return np.interp(t, fino, cpf), np.interp(t, fino, intf)


def ajustar(ct: np.ndarray, t_min: np.ndarray, cp: np.ndarray, int_cp: np.ndarray, estendido: bool = False) -> dict:
    """Mínimos quadrados lineares (Murase 2004) ao longo do eixo 0 de `ct` (fases, ...):

        Tofts:      Ct = Ktrans · ∫Cp − kep · ∫Ct
        estendido:  Ct = (Ktrans + kep · vp) · ∫Cp − kep · ∫Ct + vp · Cp

    Devolve {"ktrans", "ve", "kep", "vp", "ok"} com a forma de `ct[0]` (min⁻¹ e frações; 0 onde não fechou)."""
    ct = np.asarray(ct, np.float64)
    t = np.asarray(t_min, np.float64)
    forma = ct.shape[1:]
    n = len(t)
    y = ct.reshape(n, -1)                                           # (T, N)
    ict = _integral(y, t)
    col = [np.broadcast_to(np.asarray(int_cp, np.float64)[:, None], y.shape), -ict]
    if estendido:
        col.append(np.broadcast_to(np.asarray(cp, np.float64)[:, None], y.shape))
    p = len(col)
    g = np.empty((y.shape[1], p, p))
    b = np.empty((y.shape[1], p))
    for i in range(p):
        b[:, i] = (col[i] * y).sum(axis=0)
        for j in range(i, p):
            g[:, i, j] = g[:, j, i] = (col[i] * col[j]).sum(axis=0)
    traco = np.trace(g, axis1=1, axis2=2)
    g = g + (np.eye(p) * 1e-9)[None] * np.maximum(traco, 1e-12)[:, None, None]
    det = np.linalg.det(g)
    bom = np.isfinite(det) & (np.abs(det) > 1e-30)
    sol = np.zeros((y.shape[1], p))
    if bom.any():
        sol[bom] = np.linalg.solve(g[bom], b[bom][..., None])[..., 0]
    kep = sol[:, 1]
    if estendido:
        vp = sol[:, 2]
        ktrans = sol[:, 0] - kep * vp
    else:
        vp = np.zeros_like(kep)
        ktrans = sol[:, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        ve = np.where(kep > 1e-6, ktrans / kep, 0.0)
    ok = bom & np.isfinite(ktrans) & (ktrans > 1e-4) & (ktrans <= KTRANS_MAX) & (kep >= 0) & (kep <= KEP_MAX)
    # kep ≈ 0 (o contraste só entra, sem volta medida no tempo do exame): ve fica sem medida
    ve = np.where(ok & (ve > 0) & (ve <= 1.0), ve, 0.0)
    out = {"ktrans": np.where(ok, ktrans, 0.0), "kep": np.where(ok, np.clip(kep, 0, None), 0.0), "ve": ve,
           "vp": np.where(ok, np.clip(vp, 0, 1), 0.0), "ok": ok}
    return {k: v.reshape(forma) for k, v in out.items()}


def mapas(pilha: np.ndarray, t_min: np.ndarray, s0: np.ndarray, cfg: Config, sinal_aif=None, s0_aif=None) -> dict:
    """Os mapas de um corte: `pilha` (fases a partir da pré, H, W), `t_min` (minutos desde a pré), `s0` (H, W)."""
    ct = concentracao(pilha, s0, cfg)
    ct[0] = 0.0
    cp, icp = plasma(t_min, cfg, sinal_aif, s0_aif)
    return ajustar(ct, t_min, cp, icp, cfg.modelo == "estendido")


def da_curva(valores, t_min, s0: float, cfg: Config, sinal_aif=None, s0_aif=None) -> dict:
    """Os números de uma curva (a média de uma ROI): {"ktrans", "ve", "kep", "vp", "ok"} em float."""
    r = mapas(np.asarray(valores, float).reshape(-1, 1, 1), np.asarray(t_min, float), np.full((1, 1), float(s0)),
              cfg, sinal_aif, s0_aif)
    return {k: (bool(v[0, 0]) if k == "ok" else float(v[0, 0])) for k, v in r.items()}


def simular(t_min, ktrans: float, ve: float, cfg: Config, vp: float = 0.0, s0: float = 100.0) -> np.ndarray:
    """O sinal que um tecido com estes parâmetros daria (AIF de Parker, convolução em malha fina de 1 s) — para
    testes e para conferir o ajuste."""
    t = np.asarray(t_min, np.float64)
    fino = np.arange(0.0, float(t.max()) + 1 / 60.0, 1 / 60.0)
    cp = aif_parker(fino - cfg.inicio_s / 60.0, cfg.hematocrito)
    kep = ktrans / max(ve, 1e-6)
    dt = fino[1] - fino[0]
    ct = np.zeros_like(fino)
    decai = np.exp(-kep * dt)
    for i in range(1, len(fino)):                       # convolução recursiva (exata para Cp linear por trecho)
        ct[i] = ct[i - 1] * decai + ktrans * 0.5 * (cp[i] + cp[i - 1] * decai) * dt
    ct = ct + vp * cp
    c = np.interp(t, fino, ct)
    r1 = 1000.0 / cfg.t10_ms + cfg.r1 * c
    if cfg.linear():
        return s0 * (1.0 + cfg.r1 * c * cfg.t10_ms / 1000.0)
    tr, ca = cfg.tr_ms / 1000.0, np.cos(np.deg2rad(cfg.angulo))
    e1, e10 = np.exp(-tr * r1), np.exp(-tr * 1000.0 / cfg.t10_ms)
    return s0 * ((1 - e1) / (1 - e1 * ca)) / ((1 - e10) / (1 - e10 * ca))


# ====================================================================== avisos
def resolucao_temporal(tempos_s) -> float:
    """O intervalo típico entre as fases pós-contraste (s)."""
    t = np.asarray(tempos_s, float)
    d = np.diff(t)
    d = d[d > 0]
    return float(np.median(d)) if d.size else 0.0


def avisos(cfg: Config, tempos_s, n_pos: int) -> list[str]:
    """O que o médico precisa saber antes de ler o número — em frases curtas."""
    out = []
    res = resolucao_temporal(tempos_s)
    if res > RESOLUCAO_BOA:
        out.append(f"Uma fase a cada {res:.0f} s: o modelo pede 5 a 15 s. O Ktrans aqui é indicativo — serve para "
                   "comparar regiões e exames do mesmo protocolo, não como valor absoluto.")
    if n_pos < 4:
        out.append(f"Só {n_pos} fases depois do contraste: o ajuste tem pouca folga.")
    if cfg.modelo == "estendido" and res > RESOLUCAO_ESTENDIDO:
        out.append("Tofts estendido com esta resolução temporal: o vp não é confiável (o pico arterial não é visto).")
    if cfg.linear():
        out.append("Sem TR ou ângulo no exame: concentração pela aproximação linear (realce relativo).")
    out.append(f"T1 do tecido antes do contraste suposto em {cfg.t10_ms:.0f} ms (não há mapa de T1).")
    if cfg.aif == "roi" and cfg.aif_sinal:
        out.append("Entrada arterial medida na ROI: confira se ela está inteira dentro do vaso e sem saturação.")
    else:
        out.append("Entrada arterial populacional (Parker), para a dose padrão de 0,1 mmol/kg.")
    return out
