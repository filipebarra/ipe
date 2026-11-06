"""Os modelos extras (0.99.83): MedSAM2, autoPET e BraTS — onde ficam, se estão prontos e como instalar.

Pedido dele (06/11/2026): "faça então as etapas 1 a 5" da lista do MedMLX (`claude/pesquisa-medmlx.md`).
Os três rodam no **mesmo ambiente** da segmentação (`…/segmentacao/venv`, com PyTorch de CPU), pelo mesmo
trabalhador (`totalseg_worker.py`, tarefas especiais). O que cada um precisa a mais é instalado uma vez
pelo `instalar_modelos_extras` (programa `ai/instalar_modelos_extras.py`, que roda com o Python do
ambiente):

- **MedSAM2** (bowang-lab, código Apache-2.0, pesos CC BY-SA 4.0): o pacote (do GitHub, sem compilar
  CUDA) e `pesos/medsam2/MedSAM2_latest.pt` (156 MB, Hugging Face wanglab/MedSAM2);
- **autoPET** (DKFZ, autoPET II, "Look Ma, no code", nnU-Net v2 comum): o modelo do Zenodo (registro 8362371)
  em `pesos/autopet/…/fold_0/checkpoint_final.pth`;
- **BraTS** (MONAI model zoo `brats_mri_segmentation`, SegResNet, Apache-2.0): `monai` e
  `pesos/brats/model.pt` (19 MB).

A "prontidão" (a ideia do `readiness` do MedMLX) só olha os arquivos, sem rodar nada: é instantânea.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODELOS = ("medsam2", "autopet", "brats")
NOMES = {"medsam2": "MedSAM2 (segmentar pela caixa)", "autopet": "autoPET (lesões no PET-FDG)",
         "brats": "BraTS (glioma na RM)"}
CREDITOS = {
    "medsam2": "MedSAM2 — Ma J. et al., arXiv 2504.03600 (2025); código Apache-2.0, pesos CC BY-SA 4.0",
    "autopet": "nnU-Net autoPET II — Isensee F. et al., arXiv 2309.13747 (2023); nnU-Net Apache-2.0",
    "brats": "MONAI brats_mri_segmentation (SegResNet, Myronenko 2018); Apache-2.0",
}


def pasta_pesos() -> Path:
    from ipe.ai import totalseg as TS
    return TS.pasta_base() / "pesos"


def _site_packages() -> list[Path]:
    from ipe.ai import totalseg as TS
    base = TS.pasta_base() / "venv"
    return [base / "Lib" / "site-packages", *sorted((base / "lib").glob("python3*/site-packages"))]


def _pacote(nome: str) -> bool:
    return any((sp / nome).is_dir() for sp in _site_packages())


@dataclass
class Prontidao:
    modelo: str
    pronto: bool
    falta: str = ""


def prontidao(modelo: str, settings=None) -> Prontidao:
    """O que falta para o modelo rodar neste computador (vazio = pronto)."""
    from ipe.ai import totalseg as TS
    if not TS.instalado(settings):
        return Prontidao(modelo, False, "a segmentação (TotalSegmentator) ainda não está instalada")
    p = pasta_pesos()
    if modelo == "medsam2":
        if not _pacote("sam2"):
            return Prontidao(modelo, False, "falta o pacote do MedSAM2")
        if not (p / "medsam2" / "MedSAM2_latest.pt").is_file():
            return Prontidao(modelo, False, "faltam os pesos do MedSAM2 (156 MB)")
    elif modelo == "autopet":
        if not _pacote("nnunetv2"):
            return Prontidao(modelo, False, "falta o nnU-Net")
        pasta = p / "autopet"
        if not (pasta.is_dir() and any(pasta.rglob("fold_0/checkpoint_final.pth"))):
            return Prontidao(modelo, False, "faltam os pesos do autoPET")
    elif modelo == "brats":
        if not _pacote("monai"):
            return Prontidao(modelo, False, "falta o MONAI")
        if not (p / "brats" / "model.pt").is_file():
            return Prontidao(modelo, False, "faltam os pesos do BraTS (19 MB)")
    else:
        return Prontidao(modelo, False, "modelo desconhecido")
    return Prontidao(modelo, True)


def texto_prontidao(settings=None) -> str:
    linhas = []
    for m in MODELOS:
        pr = prontidao(m, settings)
        linhas.append(f"{NOMES[m]}: " + ("pronto" if pr.pronto else pr.falta))
    return "\n".join(linhas)


def motivo(modelo: str, settings=None) -> str:
    pr = prontidao(modelo, settings)
    if pr.pronto:
        return ""
    return (f"{NOMES[modelo]}: {pr.falta}. Instale em Configurações ▸ Instalar os modelos extras (MedSAM2, autoPET, "
            f"BraTS)… — uma vez, com internet.")


# ------------------------------------------------------------------ outra série na grade desta
def na_grade(alvo, fonte, M: np.ndarray | None = None, fora: float = 0.0, progresso=None) -> np.ndarray:
    """O volume `fonte` amostrado nos voxels do volume `alvo` (trilinear), corte a corte.

    `M` (4 × 4, de `registro_rigido`): leva o ponto do paciente em `alvo` ao ponto em `fonte`; sem ela,
    vale a posição do DICOM (mesmo Frame of Reference, o caso do PET/CT)."""
    from ipe.imaging.registro_rigido import amostrar, aplicar
    nz, ny, nx = alvo.shape
    jj, ii = np.mgrid[0:ny, 0:nx].astype(np.float64)
    m = alvo.matrix()
    out = np.empty(alvo.shape, np.float32)
    for k in range(nz):
        pts = np.stack([ii.ravel(), jj.ravel(), np.full(ii.size, float(k))], 1) @ m.T + alvo.origin
        if M is not None:
            pts = aplicar(M, pts)
        out[k] = amostrar(fonte, pts, fora=fora).reshape(ny, nx)
        if progresso is not None and k % 16 == 0 and progresso(k, nz) is False:
            raise InterruptedError
    return out


def caminho_do_instalador() -> Path:
    """O .py do instalador dos extras: ao lado deste módulo (código) ou nos recursos do pacote."""
    perto = Path(__file__).with_name("instalar_modelos_extras.py")
    if perto.is_file():
        return perto
    from ipe.core.runtime import resource_dir
    return resource_dir() / "ai" / "instalar_modelos_extras.py"


def comando_do_instalador(modelos=(), settings=None) -> list[str] | None:
    """[python do ambiente, instalador, modelos…] — None sem a segmentação instalada."""
    from ipe.ai import totalseg as TS
    py = TS.python_do_ambiente(settings)
    if py is None:
        return None
    return [str(py), str(caminho_do_instalador()), *[m for m in modelos if m in MODELOS]]
