"""MedSAM2: segmentar qualquer lesão por uma caixa (0.99.83; item 1 da lista do MedMLX).

A ferramenta **Segmentar pela caixa (IA)** do botão esquerdo: o médico desenha uma caixa em volta da lesão num
corte; o MedSAM2 (bowang-lab, 2025) faz a máscara nesse corte e a propaga para os cortes vizinhos, para cima e
para baixo (o modo "vídeo" do SAM2). Serve para TC, RM e PET — o modelo foi treinado em lesões de muitos
órgãos —, e a janela da tela é a que entra no modelo (como no artigo: janela → 0–255).

O resultado abre na mesma janela da **Segmentação 3D** do clique (volume, eixos, SUV/TLG no PET, ligar a uma
lesão do acompanhamento, gravar a SEG), com o método "IA: caixa (MedSAM2)". Fica só a parte contígua ao corte
da caixa (a propagação às vezes "pula" para outra estrutura longe).

Roda no ambiente da segmentação, pelo trabalhador (`totalseg_worker.py`, tarefa especial "medsam2"), em CPU.
"""
from __future__ import annotations

import numpy as np

TITULO = "Segmentar pela caixa (MedSAM2)"
MODALIDADES = ("CT", "MR", "PT", "NM")
ALCANCE = 60               # cortes para cada lado do corte da caixa
METODO = "medsam2"


def tarefa(caixa_ijk: tuple, janela: tuple[float, float], alcance: int = ALCANCE) -> dict:
    """A tarefa do trabalhador: (k, i0, j0, i1, j1) no volume e a janela (mín, máx)."""
    k, i0, j0, i1, j1 = caixa_ijk
    return {"nome": "medsam2", "rotulo": "MedSAM2 (caixa → máscara 3D)", "caixa": [int(k), float(i0), float(j0),
            float(i1), float(j1)], "janela": [float(janela[0]), float(janela[1])], "alcance": int(alcance)}


def caixa_no_volume(vol, cantos_mm: list) -> tuple[int, float, float, float, float] | None:
    """Os cantos da caixa (pontos do paciente, mm) → (k, i0, j0, i1, j1) no volume; None fora dele."""
    ijk = np.array([vol.patient_to_voxel(np.asarray(p, float)) for p in cantos_mm])
    nz, ny, nx = vol.shape
    k = int(round(float(ijk[:, 2].mean())))
    if not 0 <= k < nz:
        return None
    i0, i1 = float(np.clip(ijk[:, 0].min(), 0, nx - 1)), float(np.clip(ijk[:, 0].max(), 0, nx - 1))
    j0, j1 = float(np.clip(ijk[:, 1].min(), 0, ny - 1)), float(np.clip(ijk[:, 1].max(), 0, ny - 1))
    if i1 - i0 < 2 or j1 - j0 < 2:
        return None
    return k, i0, j0, i1, j1


def resultado(vol, rotulos: np.ndarray, caixa_ijk: tuple, suv: float | None = None, modality: str = ""):
    """A máscara do trabalhador (k, j, i) → `SegResult` com as mesmas medidas da segmentação do clique."""
    from ipe.imaging.segment import de_mascara
    k, i0, j0, i1, j1 = caixa_ijk
    semente = (int(k), int(round((j0 + j1) / 2)), int(round((i0 + i1) / 2)))
    res = de_mascara(vol, np.asarray(rotulos) > 0, semente, METODO, suv=suv, modality=modality)
    if not res.voxels:
        res.notes.append("o MedSAM2 não achou nada dentro da caixa")
    return res
