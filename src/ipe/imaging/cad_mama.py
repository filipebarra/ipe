"""Números do CAD de RM de mama para uma lesão segmentada (estilo CADstream).

O que cada número é, e de onde vem:

* **Volume** — o volume da região crescida, em mL.
* **Angiovolume** — o volume **da parte que realça de verdade**, isto é, dos voxels que entram no
  mapa cinético. Exclui necrose, fibrose, cisto e o que ficou dentro da região sem realçar. É o
  número que o artigo de prognóstico usa; o volume total sozinho não distingue uma massa sólida de
  uma com centro necrótico.
* **Realce de pico** — maior aumento percentual do sinal em relação ao pré-contraste, na fase de
  pico; vem junto a média da região.
* **Eixos perpendiculares** — os três maiores eixos perpendiculares entre si: o maior, o maior
  perpendicular a ele e o maior perpendicular aos dois. **Não** é a caixa nos eixos da série:
  uma lesão oblíqua tem caixa grande e eixos pequenos, e é o eixo que vai para o laudo.
* **Percentual de cada um dos seis padrões** — quanto do angiovolume é médio/rápido ×
  persistente/platô/washout. É a distribuição que o mapa mostra em cor, em número.
* **Heterogeneidade cinética** — a fórmula do CADstream **não é publicada**, então aqui ela é a
  entropia de Shannon da distribuição dos seis padrões, normalizada de 0 a 1 (0 = tudo num padrão
  só, 1 = igualmente espalhado pelos seis). Vai rotulada assim na tela: rótulo deduzido é rótulo
  marcado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ipe.imaging.dynamic import CLASSES
from ipe.imaging.segment import tres_eixos


@dataclass
class MedidasCAD:
    ml: float = 0.0
    angio_ml: float = 0.0
    realce_pico: float = 0.0
    realce_medio: float = 0.0
    diametros_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)   # eixos perpendiculares, maior→menor
    maior_3d_mm: float = 0.0
    percentuais: dict[str, float] = field(default_factory=dict)   # classe -> % do angiovolume
    heterogeneidade: float = 0.0
    alongamento: float = 0.0        # maior diâmetro ÷ diâmetro da esfera de mesmo volume
    avisos: list[str] = field(default_factory=list)

    @property
    def fracao_que_realca(self) -> float:
        return (self.angio_ml / self.ml * 100.0) if self.ml > 0 else 0.0

    @property
    def padrao_dominante(self) -> str:
        if not self.percentuais:
            return ""
        return max(self.percentuais.items(), key=lambda kv: kv[1])[0]

    def linhas(self) -> list[tuple[str, str]]:
        """(rótulo, valor) na ordem em que o radiologista lê."""
        d = self.diametros_mm
        out = [("Volume", f"{self.ml:.2f} mL"),
               ("Angiovolume", f"{self.angio_ml:.2f} mL ({self.fracao_que_realca:.0f}% da lesão)"),
               ("Realce de pico", f"{self.realce_pico:.0f}% (média {self.realce_medio:.0f}%)"),
               ("Eixos perpendiculares", f"{d[0]:.1f} × {d[1]:.1f} × {d[2]:.1f} mm"),
               ("Maior eixo", f"{self.maior_3d_mm:.1f} mm "
                f"(alongamento {self.alongamento:.1f}×)")]
        if self.percentuais:
            out.append(("Padrão dominante", self.padrao_dominante))
            out.append(("Heterogeneidade cinética", f"{self.heterogeneidade:.2f} (entropia das classes, 0–1)"))
        return out

    def meta(self) -> dict:
        d = {"ml": round(self.ml, 3), "angio_ml": round(self.angio_ml, 3),
             "realce_pico": round(self.realce_pico, 1), "realce_medio": round(self.realce_medio, 1),
             "eixos_mm": [round(x, 1) for x in self.diametros_mm],
             "maior_3d_mm": round(self.maior_3d_mm, 1),
             "heterogeneidade": round(self.heterogeneidade, 3),
             "alongamento": round(self.alongamento, 2)}
        for nome, pct in self.percentuais.items():
            d["pct_" + nome.replace("/", "_")] = round(pct, 1)
        return d


def _entropia(fracoes: np.ndarray) -> float:
    """Entropia de Shannon normalizada (0 a 1). Zero quando tudo cai numa classe só."""
    p = np.asarray([x for x in fracoes if x > 0], float)
    if p.size <= 1:
        return 0.0
    p = p / p.sum()
    return float(-(p * np.log(p)).sum() / math.log(len(fracoes)))


def maior_diametro(pontos_mm: np.ndarray, voxel_mm: np.ndarray) -> float:
    """Maior distância entre dois pontos da lesão, com o voxel contado nas pontas.

    Reusar o `max_diam_mm` do segmentador dava um absurdo visível: ele soma só o menor lado
    **no plano**, e com corte de 10 mm o "maior diâmetro 3D" saía **menor** que o diâmetro
    crânio-caudal da própria caixa (26,4 mm contra 30,0 mm). Aqui a correção é meio voxel em
    cada ponta, projetado na direção medida — assim o maior diâmetro nunca fica abaixo de um
    dos lados.
    """
    if len(pontos_mm) < 2:
        return float(np.abs(voxel_mm).sum())
    pts = pontos_mm
    if len(pts) > 1500:
        pts = pts[np.random.default_rng(0).choice(len(pts), 1500, replace=False)]
    d2 = ((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
    a, b = np.unravel_index(int(np.argmax(d2)), d2.shape)
    v = pts[b] - pts[a]
    comp = float(np.linalg.norm(v))
    if comp < 1e-6:
        return float(np.abs(voxel_mm).sum())
    u = v / comp
    return comp + float(np.abs(u * voxel_mm).sum())


def medir(vol_realce, classes: np.ndarray, res, vol_classes_offset=None) -> MedidasCAD:
    """Mede a lesão já segmentada.

    `vol_realce`: volume do realce no pico (%); `classes`: volume das classes cinéticas (0 a 6),
    na mesma grade; `res`: o `SegResult` do crescimento de região.
    """
    m = MedidasCAD()
    if res is None or not res.voxels:
        m.avisos.append("Nada segmentado.")
        return m
    k0, j0, i0 = res.offset
    nk, nj, ni = res.mask.shape
    corte = (slice(k0, k0 + nk), slice(j0, j0 + nj), slice(i0, i0 + ni))
    realce = np.asarray(vol_realce.data[corte])[res.mask]
    cls = np.asarray(classes[corte])[res.mask].astype(int)

    dx, dy, dz = vol_realce.dx, vol_realce.dy, vol_realce.dz
    voxel_ml = dx * dy * dz / 1000.0
    m.ml = float(res.voxels) * voxel_ml
    coloridos = cls > 0
    m.angio_ml = float(coloridos.sum()) * voxel_ml
    m.realce_pico = float(realce.max()) if realce.size else 0.0
    m.realce_medio = float(realce.mean()) if realce.size else 0.0
    # Os três eixos **perpendiculares** da lesão, do maior para o menor — não a caixa nos eixos da
    # série: uma lesão oblíqua tem caixa grande e eixos pequenos, e é o eixo que vai no laudo.
    kk, jj, ii = np.nonzero(res.mask)
    pontos = (np.stack([ii + i0, jj + j0, kk + k0], axis=1).astype(float)) @ vol_realce.matrix().T
    eixos = res.eixos_mm or tres_eixos(pontos, (dx, dy, dz))
    m.diametros_mm = (float(eixos[0]), float(eixos[1]), float(eixos[2]))
    m.maior_3d_mm = float(eixos[0])

    if coloridos.any():
        contagem = np.array([int((cls == c).sum()) for c in range(1, 7)], float)
        total = contagem.sum()
        m.percentuais = {CLASSES[c]: float(contagem[c - 1] / total * 100.0) for c in range(1, 7)}
        m.heterogeneidade = _entropia(contagem)
    else:
        m.avisos.append("Nenhum voxel da lesão entra no mapa cinético: só volume e diâmetros valem.")
    # Forma: numa RM de mama tudo o que realça está ligado pelos vasos, e a região cresce por
    # dentro deles. Massa é compacta; vaso é fino e comprido. O programa não decide por ele, mas
    # avisa — medido no acervo, uma semente em vaso deu 15 mL com 105 mm de maior diâmetro.
    if m.ml > 0:
        esfera = 2.0 * (3.0 * m.ml * 1000.0 / (4.0 * math.pi)) ** (1.0 / 3.0)
        m.alongamento = m.maior_3d_mm / esfera if esfera > 0 else 0.0
        if m.alongamento >= 3.0:
            m.avisos.append("A região é fina e comprida (forma de vaso, não de nódulo): aperte o "
                            "limiar ou clique mais dentro da lesão.")
    if res.truncated:
        m.avisos.append("A região encostou no limite do raio de busca: aumente o raio ou suba o limiar.")
    return m


# ---------------------------------------------------------------------------
# Números do exame inteiro (fora da lesão)
# ---------------------------------------------------------------------------

@dataclass
class ExameCAD:
    """O que se mede na mama inteira, não numa lesão."""
    mama_ml: float = 0.0
    angio_ml: float = 0.0
    angio_pct: float = 0.0          # angiovolume / volume da mama
    realce_medio: float = 0.0       # realce (%) médio do tecido da mama na fase de pico
    realce_mediana: float = 0.0
    percentuais: dict[str, float] = field(default_factory=dict)
    mascara: str = ""
    formula: str = ""
    avisos: list[str] = field(default_factory=list)

    def linhas(self) -> list[tuple[str, str]]:
        angio = f"{self.angio_ml:.1f} mL" + " · " + f"{self.angio_pct:.1f}%" + " da mama"
        out = [("Volume da mama na máscara", f"{self.mama_ml:.0f} mL"),
               ("Angiovolume do exame", angio),
               ("Realce de fundo, média", f"{self.realce_medio:.1f}%"),
               ("Realce de fundo, mediana", f"{self.realce_mediana:.1f}%")]
        out += [("   " + nome, f"{pct:.1f}%" + " do angiovolume") for nome, pct in self.percentuais.items()]
        return out


def medir_exame(pre: np.ndarray, pico: np.ndarray, classes: np.ndarray, mascara: np.ndarray,
                voxel_ml: float, texto_mascara: str = "") -> ExameCAD:
    """Realce de fundo do parênquima e angiovolume do **exame**, dentro da máscara da mama.

    `pre` e `pico`: volumes de sinal (pré-contraste e fase de pico). `classes`: o volume do mapa
    cinético (0 a 6) na mesma grade. `mascara`: o que é mama (ver `imaging/mama_mascara.py`).

    Sobre o que este número **é**: o realce de fundo aqui é o realce percentual médio do tecido
    que a máscara chama de mama, e o angiovolume é o volume desse tecido que o mapa cinético
    pinta. A máscara mantém pele e músculo peitoral, que realçam — então este número é maior que
    o realce do parênquima puro, e serve para comparar o **mesmo** serviço ao longo do tempo, não
    para virar categoria. Categoria de realce de fundo (mínimo/leve/moderado/acentuado) é leitura
    do médico: o programa devolve número.
    """
    e = ExameCAD(mascara=texto_mascara)
    m = np.asarray(mascara, bool)
    if not m.any():
        e.avisos.append("Máscara da mama vazia: nada a medir.")
        return e
    pre_m = np.asarray(pre, np.float32)[m]
    realce = (np.asarray(pico, np.float32)[m] - pre_m) / np.maximum(pre_m, 1e-6) * 100.0
    e.mama_ml = float(m.sum() * voxel_ml)
    e.realce_medio = float(np.mean(realce))
    e.realce_mediana = float(np.median(realce))
    cls = np.asarray(classes)[m]
    pintado = cls > 0
    e.angio_ml = float(pintado.sum() * voxel_ml)
    e.angio_pct = float(pintado.mean() * 100.0)
    total = int(pintado.sum())
    if total:
        contagem = np.bincount(cls[pintado].astype(np.int64), minlength=7)
        e.percentuais = {CLASSES[c]: float(contagem[c] / total * 100.0) for c in range(1, 7)}
    e.formula = ("Realce de fundo = média de (pico − pré) / pré, em %, nos voxels da máscara da "
                 "mama. Angiovolume do exame = volume dos voxels da máscara que o mapa cinético "
                 "pinta (passam do limiar de realce inicial).")
    return e
