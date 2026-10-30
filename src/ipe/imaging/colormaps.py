"""Tabelas de cores (CLUT / pseudocor) aplicadas depois da janela/nível.

Cada tabela é definida por pontos de controle (posição 0–1, R, G, B) e interpolada
linearmente em 256 cores. As versões são aproximações das tabelas usuais em
estações de trabalho (OsiriX/Horos, medicina nuclear)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

_B, _W = (0, 0, 0), (255, 255, 255)

# chave -> (nome exibido, pontos de controle)
COLORMAPS: dict[str, tuple[str, list[tuple[float, tuple[int, int, int]]]]] = {
    "inverse": ("Cinza inverso", [(0, _W), (1, _B)]),
    "hot": ("Hot Iron (ferro quente)", [(0, _B), (0.375, (255, 0, 0)), (0.75, (255, 255, 0)), (1, _W)]),
    "gold": ("Gold (ouro)", [(0, _B), (0.35, (140, 80, 10)), (0.7, (225, 180, 50)), (1, (255, 250, 215))]),
    "hotmetal": ("Hot Metal Blue", [(0, _B), (0.25, (0, 0, 160)), (0.5, (170, 0, 130)),
                                     (0.75, (255, 140, 0)), (1, _W)]),
    "pet": ("PET", [(0, _B), (0.2, (0, 0, 150)), (0.4, (130, 0, 170)), (0.6, (235, 0, 60)),
                    (0.8, (255, 165, 0)), (1, _W)]),
    "thallium": ("Tálio (Thallium)", [(0, _B), (0.2, (0, 0, 190)), (0.4, (0, 190, 190)), (0.55, (0, 200, 0)),
                                      (0.7, (255, 255, 0)), (0.85, (255, 60, 0)), (1, _W)]),
    # PUH Thallium da GE (Advantage Workstation / FuncTool): o padrão do mapa de fluxo (CBF) na
    # perfusão, e muito usado em ADC e R2*. **Não** é uma escala quente — é um arco-íris
    # escurecido, inspirado nas escalas de medicina nuclear: preto → azul → ciano/verde →
    # amarelo-esverdeado → amarelo → laranja, com o verde e o amarelo de propósito mais escuros e
    # menos saturados que num arco-íris comum.
    #
    # Os pontos vêm da **medição dos pixels de uma faixa da própria GE**, amostrada pelo usuário
    # (ver `claude/andamento.md`); a primeira versão que escrevi aqui era chute meu, e era outra
    # escala. Ressalva que fica: a amostra não mostra o extremo direito inteiro — na AW o fim pode
    # continuar até laranja forte/vermelho, então a última faixa é a parte menos firme da tabela.
    "puh_thalium": ("Tálio PUH (GE AW)", [(0.00, (0, 0, 12)), (0.06, (0, 0, 107)),
                                          (0.12, (0, 16, 154)), (0.18, (0, 46, 175)),
                                          (0.24, (0, 80, 193)), (0.30, (0, 109, 162)),
                                          (0.36, (0, 130, 139)), (0.42, (0, 150, 125)),
                                          (0.48, (7, 159, 106)), (0.54, (57, 180, 48)),
                                          (0.60, (137, 202, 6)), (0.66, (192, 211, 0)),
                                          (0.72, (210, 219, 1)), (0.80, (214, 232, 1)),
                                          (0.90, (214, 198, 0)), (0.96, (223, 165, 0)),
                                          (1.00, (220, 130, 0))]),
    "rainbow": ("Arco-íris (Rainbow)", [(0, _B), (0.15, (90, 0, 160)), (0.3, (0, 0, 255)), (0.45, (0, 200, 255)),
                                        (0.6, (0, 220, 0)), (0.75, (255, 255, 0)), (0.9, (255, 100, 0)),
                                        (1, (255, 0, 0))]),
    "spectrum": ("Espectro", [(0, _B), (0.17, (130, 0, 200)), (0.33, (0, 0, 255)), (0.5, (0, 255, 0)),
                              (0.67, (255, 255, 0)), (0.83, (255, 0, 0)), (1, _W)]),
    "jet": ("Jet", [(0, (0, 0, 128)), (0.125, (0, 0, 255)), (0.375, (0, 255, 255)), (0.625, (255, 255, 0)),
                    (0.875, (255, 0, 0)), (1, (128, 0, 0))]),
    "nih": ("NIH", [(0, _B), (0.17, (85, 0, 136)), (0.33, (0, 0, 255)), (0.5, (0, 200, 80)),
                    (0.67, (255, 255, 0)), (0.83, (255, 120, 0)), (1, (255, 0, 0))]),
    "ge": ("GE Color", [(0, _B), (0.25, (0, 70, 140)), (0.5, (120, 130, 120)), (0.75, (255, 130, 0)), (1, _W)]),
    "cardiac": ("Cardíaco / perfusão", [(0, _B), (0.2, (0, 0, 255)), (0.4, (0, 255, 255)), (0.6, (0, 255, 0)),
                                        (0.8, (255, 255, 0)), (1, (255, 0, 0))]),
    "flow": ("Fluxo (azul-vermelho)", [(0, (150, 220, 255)), (0.25, (0, 0, 255)), (0.5, _B), (0.75, (255, 0, 0)),
                                       (1, (255, 235, 130))]),
    # SER com janela 0–2: < 0,9 azul (persistente), 0,9–1,1 amarelo (platô), > 1,1 vermelho (washout);
    # o índice 0 (fora da máscara) fica preto
    "ser": ("SER (azul / amarelo / vermelho)", [(0, _B), (0.0039, (0, 30, 150)), (0.4489, (40, 140, 255)),
                                               (0.449, (255, 230, 0)), (0.5489, (255, 190, 0)),
                                               (0.549, (230, 0, 0)), (1, (255, 120, 255))]),
    # Mapa cinético (estilo CADstream): 7 faixas chapadas, uma por classe. A cor **não**
    # interpola: o tom diz o comportamento tardio (azul persistente, verde platô, vermelho
    # washout) e o brilho diz a intensidade do realce (escuro = médio, vivo = rápido).
    "cinetico": ("Cinética (6 classes)", [
        (0.000, _B), (0.142, _B),
        (0.143, (0, 60, 150)), (0.285, (0, 60, 150)),
        (0.286, (0, 115, 60)), (0.428, (0, 115, 60)),
        (0.429, (140, 35, 35)), (0.571, (140, 35, 35)),
        (0.572, (70, 150, 255)), (0.714, (70, 150, 255)),
        (0.715, (60, 230, 90)), (0.857, (60, 230, 90)),
        (0.858, (255, 55, 55)), (1.000, (255, 55, 55))]),
    "vr_bone": ("VR osso", [(0, (120, 90, 60)), (0.4, (220, 190, 150)), (1, (255, 250, 240))]),
    "vr_vessel": ("VR vasos", [(0, (110, 0, 0)), (0.35, (210, 40, 30)), (0.75, (250, 170, 140)), (1, _W)]),
    "vr_skin": ("VR pele", [(0, (150, 90, 70)), (0.5, (225, 170, 140)), (1, (255, 225, 200))]),
    "bone": ("Osso (bege)", [(0, _B), (0.5, (150, 120, 90)), (1, (255, 245, 225))]),
}


def name(key: str) -> str:
    return COLORMAPS[key][0] if key in COLORMAPS else "Cinza"


@lru_cache(maxsize=None)
def lut(key: str) -> np.ndarray:
    """Tabela 256×3 (uint8)."""
    pts = COLORMAPS[key][1]
    xs = np.array([p[0] for p in pts]) * 255
    rgb = np.array([p[1] for p in pts], dtype=float)
    t = np.arange(256)
    out = np.stack([np.interp(t, xs, rgb[:, c]) for c in range(3)], axis=1)
    out = np.round(out).astype(np.uint8)
    out.setflags(write=False)
    return out


def apply(gray8: np.ndarray, key: str | None) -> np.ndarray:
    """Cinza 8 bits (H×W) -> RGB (H×W×3). Sem tabela ou imagem já colorida: devolve igual."""
    if not key or key not in COLORMAPS or gray8.ndim != 2:
        return gray8
    return lut(key)[gray8]
