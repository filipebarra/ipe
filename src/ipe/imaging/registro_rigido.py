"""Registro rígido em 3D — rotação e translação (6 graus de liberdade) — entre dois volumes (0.99.38).

Item F1 do plano da AW (`claude/ideias-aw-server.md`): a base do seguimento (exame atual × anterior),
de clonar ROI entre exames e da correção de movimento. Até a 0.99.37 o Ipê só fazia **translação**
(`imaging/register.py`, correlação de fase): cabeça girada entre dois exames ficava desalinhada.

Como funciona (só NumPy, sem SciPy nem SimpleITK, como o resto do programa):

- **A** é o volume fixo (o exame atual), **B** o que se move (o anterior, outra sequência). O
  resultado é a transformação T que leva um ponto do paciente em A ao ponto correspondente em B:
  p_B = R·(p_A − c) + c + t, com c o centro de A. Guardada como matriz 4 × 4.
- Ponto de partida: a translação da correlação de fase (`register.register_translation`).
- Busca em três resoluções (grade isotrópica de 8, 4 e 2 mm): em cada uma, descida por coordenada
  nos seis parâmetros com passos que caem pela metade (rotação 4° → 0,25°; translação 8 → 0,5 mm).
- Medida de semelhança: **correlação normalizada** (mesma modalidade e mesma sequência) ou
  **informação mútua** (modalidades ou sequências diferentes: TC × RM, T1 × T2, PET × TC), escolhida
  sozinha pela modalidade ou à mão.
- Interpolação trilinear. Só conta a região em que os dois volumes têm imagem e A tem sinal.

Conferência por **pares de pontos** (o mesmo ponto anatômico marcado nos dois exames): erro médio e
máximo em mm — o que a AW chama de validação do registro.

Sem Qt.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

NIVEIS = (8.0, 4.0, 2.0)          # mm por voxel em cada resolução
#: (rotação em graus, translação em mm) de cada rodada, por resolução
ESCALA = (((4.0, 8.0), (2.0, 4.0), (1.0, 2.0)),
          ((1.0, 2.0), (0.5, 1.0)),
          ((0.5, 1.0), (0.25, 0.5)))
MAX_LADO = 128                    # voxels por lado em cada resolução (limita memória e tempo)


# ------------------------------------------------------------------ geometria
def rotacao(rx: float, ry: float, rz: float) -> np.ndarray:
    """Matriz de rotação (graus, em torno de x, depois y, depois z do paciente)."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def matriz(params, centro) -> np.ndarray:
    """4 × 4 que leva p_A a p_B: p_B = R·(p_A − c) + c + t."""
    rx, ry, rz, tx, ty, tz = params
    R = rotacao(rx, ry, rz)
    c = np.asarray(centro, dtype=float)
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = c - R @ c + np.array([tx, ty, tz])
    return M


def aplicar(M: np.ndarray, pontos) -> np.ndarray:
    p = np.atleast_2d(np.asarray(pontos, dtype=float))
    return p @ M[:3, :3].T + M[:3, 3]


def angulos(M: np.ndarray) -> tuple[float, float, float]:
    """Os três ângulos (graus) de volta da matriz (mesma convenção de `rotacao`)."""
    R = M[:3, :3]
    ry = math.degrees(math.asin(max(-1.0, min(1.0, -R[2, 0]))))
    rx = math.degrees(math.atan2(R[2, 1], R[2, 2]))
    rz = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    return rx, ry, rz


def _cantos(vol) -> np.ndarray:
    nz, ny, nx = vol.shape
    return np.array([vol.voxel_to_patient(i, j, k) for i in (0, nx - 1) for j in (0, ny - 1) for k in (0, nz - 1)])


def amostrar(vol, pontos: np.ndarray, fora: float = np.nan) -> np.ndarray:
    """Valores do volume nos pontos do paciente (N × 3), trilinear; fora do volume = `fora`."""
    M = vol.matrix()
    ijk = np.linalg.solve(M, (pontos - vol.origin).T).T          # (N, 3): i (coluna), j (linha), k (corte)
    nz, ny, nx = vol.shape
    i, j, k = ijk[:, 0], ijk[:, 1], ijk[:, 2]
    ok = (i >= 0) & (i <= nx - 1) & (j >= 0) & (j <= ny - 1) & (k >= -0.5) & (k <= nz - 0.5)
    out = np.full(len(pontos), fora, dtype=np.float32)
    if not ok.any():
        return out
    i, j, k = i[ok], j[ok], np.clip(k[ok], 0, nz - 1)
    i0, j0, k0 = np.floor(i).astype(int), np.floor(j).astype(int), np.floor(k).astype(int)
    i1, j1, k1 = np.minimum(i0 + 1, nx - 1), np.minimum(j0 + 1, ny - 1), np.minimum(k0 + 1, nz - 1)
    fi, fj, fk = i - i0, j - j0, k - k0
    d = vol.data
    c000 = d[k0, j0, i0]; c100 = d[k0, j0, i1]; c010 = d[k0, j1, i0]; c110 = d[k0, j1, i1]  # noqa: E702
    c001 = d[k1, j0, i0]; c101 = d[k1, j0, i1]; c011 = d[k1, j1, i0]; c111 = d[k1, j1, i1]  # noqa: E702
    c00 = c000 * (1 - fi) + c100 * fi
    c10 = c010 * (1 - fi) + c110 * fi
    c01 = c001 * (1 - fi) + c101 * fi
    c11 = c011 * (1 - fi) + c111 * fi
    out[ok] = ((c00 * (1 - fj) + c10 * fj) * (1 - fk) + (c01 * (1 - fj) + c11 * fj) * fk).astype(np.float32)
    return out


# ------------------------------------------------------------------ semelhança
def ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else 0.0


def informacao_mutua(a: np.ndarray, b: np.ndarray, caixas: int = 32) -> float:
    """Informação mútua normalizada (Studholme): (H(A)+H(B))/H(A,B), entre 1 e 2."""
    def faixa(x):
        lo, hi = np.percentile(x, 1), np.percentile(x, 99)
        return np.clip(((x - lo) / max(hi - lo, 1e-9) * (caixas - 1)).astype(int), 0, caixas - 1)
    h = np.bincount(faixa(a) * caixas + faixa(b), minlength=caixas * caixas).astype(np.float64)
    p = h / h.sum()
    pa, pb = p.reshape(caixas, caixas).sum(1), p.reshape(caixas, caixas).sum(0)

    def H(x):
        x = x[x > 0]
        return float(-(x * np.log(x)).sum())
    hab = H(p)
    return (H(pa) + H(pb)) / hab if hab > 0 else 1.0


def metrica_para(mod_a: str, mod_b: str, desc_a: str = "", desc_b: str = "") -> str:
    """'ncc' quando é a mesma modalidade e a mesma sequência; 'mi' nos outros casos."""
    if (mod_a or "").upper() != (mod_b or "").upper():
        return "mi"
    if (mod_a or "").upper() == "MR":
        import re

        def seq(d):
            d = (d or "").upper()
            for s in ("T1", "T2", "FLAIR", "DWI", "DIF", "ADC", "STIR", "SWI", "TOF", "PD"):
                if re.search(rf"(?<![A-Z]){s}", d):
                    return s
            return ""
        sa, sb = seq(desc_a), seq(desc_b)
        if sa and sb and sa != sb:
            return "mi"
    return "ncc"


# ------------------------------------------------------------------ o registro
@dataclass
class Resultado:
    M: np.ndarray                         # 4 × 4, p_A → p_B
    params: tuple                         # (rx, ry, rz, tx, ty, tz)
    centro: np.ndarray
    metrica: str
    valor: float                          # a semelhança no fim (NCC −1..1; IM 1..2)
    valor_inicial: float
    segundos: float
    avisos: list = field(default_factory=list)

    @property
    def translacao(self) -> np.ndarray:
        """O deslocamento do centro de A (o que a sincronização por translação usa)."""
        return aplicar(self.M, self.centro)[0] - self.centro

    @property
    def rotacao_total(self) -> float:
        """Ângulo de rotação total (graus)."""
        c = (np.trace(self.M[:3, :3]) - 1) / 2
        return math.degrees(math.acos(max(-1.0, min(1.0, c))))

    def qualidade(self) -> str:
        if self.metrica == "ncc":
            return "boa" if self.valor > 0.8 else ("razoável" if self.valor > 0.5 else "fraca")
        return "boa" if self.valor > 1.15 else ("razoável" if self.valor > 1.07 else "fraca")


def _grade(vol_a, passo: float):
    """Pontos do paciente numa grade isotrópica dentro de A (no máximo MAX_LADO por lado)."""
    nz, ny, nx = vol_a.shape
    ext = np.array([nx * vol_a.dx, ny * vol_a.dy, nz * vol_a.dz])
    passo = max(passo, float(ext.max()) / MAX_LADO)
    n = np.maximum((ext / passo).astype(int), 2)
    ii = np.linspace(0, nx - 1, n[0])
    jj = np.linspace(0, ny - 1, n[1])
    kk = np.linspace(0, nz - 1, n[2])
    K, J, I = np.meshgrid(kk, jj, ii, indexing="ij")
    ijk = np.stack([I.ravel(), J.ravel(), K.ravel()], axis=1)
    return vol_a.origin + ijk @ vol_a.matrix().T, passo


def registrar(vol_a, vol_b, metrica: str = "ncc", inicio=None, tempo_max: float = 120.0,
              progresso=None, niveis=NIVEIS) -> Resultado:
    """Registro rígido de B sobre A. `inicio`: (rx, ry, rz, tx, ty, tz) de partida (padrão: a
    translação da correlação de fase). `progresso(feito, total, texto)` devolve False para parar
    (levanta InterruptedError). `tempo_max`: para com o melhor achado até ali (o "Fast" da AW)."""
    t0 = time.monotonic()
    centro = _cantos(vol_a).mean(0)
    avisos = []
    if inicio is None:
        try:
            from ipe.imaging.register import register_translation
            t, _q = register_translation(vol_a, vol_b)
            inicio = (0.0, 0.0, 0.0, *map(float, t))
        except Exception as e:  # noqa: BLE001
            log.debug("translação inicial: %s", e)
            inicio = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    p = np.array(inicio, dtype=float)
    p_inicio = p.copy()
    f = ncc if metrica == "ncc" else informacao_mutua
    valor_inicial = None
    atual = None
    total = len(niveis)
    for nivel, passo_mm in enumerate(niveis):
        pts, passo = _grade(vol_a, passo_mm)
        va = amostrar(vol_a, pts)
        limiar = np.nanpercentile(va, 20) if np.isfinite(va).any() else 0.0
        dentro = np.isfinite(va) & (va > limiar)
        if dentro.sum() < 200:
            # 0.100.33: volume pequeno — a grade grossa tem poucos pontos, a fina pode ter o bastante. (Antes parava
            # aqui e, se era a primeira resolução, a função quebrava sem resultado.)
            continue
        pts_d, va_d = pts[dentro], va[dentro]

        def custo(params):
            vb = amostrar(vol_b, aplicar(matriz(params, centro), pts_d))
            ok = np.isfinite(vb)
            if ok.sum() < 0.3 * len(vb):
                return -np.inf
            return f(va_d[ok], vb[ok])
        atual = custo(p)
        if valor_inicial is None:
            valor_inicial = atual
        # passos desta resolução: grossos na grade grossa, finos na fina
        for pr, pt in ESCALA[min(nivel, len(ESCALA) - 1)]:
            melhorou = True
            while melhorou and time.monotonic() - t0 <= tempo_max:
                melhorou = False
                for idx in range(6):
                    passo_p = pr if idx < 3 else pt
                    for sinal in (1, -1):
                        q = p.copy()
                        q[idx] += sinal * passo_p
                        v = custo(q)
                        if v > atual + 1e-7:
                            p, atual, melhorou = q, v, True
                            break
            if time.monotonic() - t0 > tempo_max:
                avisos.append(f"parou no tempo máximo ({tempo_max:.0f} s), com o melhor achado até ali")
                break
        if progresso is not None and progresso(nivel + 1, total, f"resolução de {passo:.0f} mm") is False:
            raise InterruptedError("Registro interrompido.")
        if time.monotonic() - t0 > tempo_max:
            break
    M = matriz(p, centro)
    # o "antes" na mesma grade do "depois" (a da última resolução), para os dois números se compararem
    try:
        valor_inicial = custo(p_inicio)
    except Exception:  # noqa: BLE001  (nenhuma resolução chegou a rodar)
        pass
    if atual is None:                    # nenhuma resolução teve imagem em comum
        avisos.append("pouca imagem em comum para registrar")
        atual = -1.0 if metrica == "ncc" else 1.0
    return Resultado(M, tuple(float(x) for x in p), centro, metrica, float(atual),
                     float(valor_inicial if valor_inicial is not None else atual), time.monotonic() - t0, avisos)


# ------------------------------------------------------------------ conferência e reformatação
def erro_dos_pontos(M: np.ndarray, pares) -> dict | None:
    """Pares (ponto em A, o mesmo ponto em B), em mm do paciente: erro médio e máximo depois do
    registro (a "validação por pares de pontos" da AW)."""
    pares = [(np.asarray(a, float), np.asarray(b, float)) for a, b in pares or []]
    if not pares:
        return None
    erros = [float(np.linalg.norm(aplicar(M, a)[0] - b)) for a, b in pares]
    return {"n": len(erros), "medio": float(np.mean(erros)), "maximo": float(np.max(erros)), "erros": erros}


def reformatar(vol_b, vol_a, M: np.ndarray, progresso=None) -> np.ndarray:
    """B reamostrado na grade de A (corte a corte de A): o anterior "no plano do atual". Fora de B = 0."""
    nz, ny, nx = vol_a.shape
    J, I = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    out = np.zeros((nz, ny, nx), dtype=np.float32)
    for k in range(nz):
        ijk = np.stack([I.ravel(), J.ravel(), np.full(I.size, k)], axis=1).astype(float)
        pts = vol_a.origin + ijk @ vol_a.matrix().T
        v = amostrar(vol_b, aplicar(M, pts), fora=0.0)
        out[k] = np.nan_to_num(v.reshape(ny, nx))
        if progresso is not None and progresso(k + 1, nz) is False:
            raise InterruptedError("Reformatação interrompida.")
    return out
