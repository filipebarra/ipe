"""Os modelos extras (0.99.83): MedSAM2, autoPET e BraTS — onde ficam, se estão prontos e como instalar.

Pedido dele (06/11/2026): "faça então as etapas 1 a 5" da lista do MedMLX (`docs/projeto/pesquisa-medmlx.md`).
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

MODELOS = ("medsam2", "autopet", "brats", "flames", "medula")
#: 0.100.79: modelos de PESQUISA (licença não comercial / só pesquisa): nunca entram no "instalar todos", só
#: instalam com a licença aceita (`--aceito-uso-em-pesquisa`) e as saídas saem marcadas "não usar para diagnóstico"
PESQUISA = ("prostata_zonas", "picai")
TODOS = MODELOS + PESQUISA
NOMES = {"medsam2": "MedSAM2 (segmentar pela caixa)", "autopet": "autoPET (lesões no PET-FDG)",
         "brats": "BraTS (glioma na RM)", "flames": "FLAMeS (lesões no FLAIR)",
         "medula": "TotalSpineSeg (medula e canal)",
         "prostata_zonas": "Zonas da próstata — MONAI/Prostate158 (PESQUISA)",
         "picai": "Lesões da próstata — PI-CAI (PESQUISA)"}
CREDITOS = {
    "medsam2": "MedSAM2 — Ma J. et al., arXiv 2504.03600 (2025); código Apache-2.0, pesos CC BY-SA 4.0",
    "autopet": "nnU-Net autoPET II — Isensee F. et al., arXiv 2309.13747 (2023); nnU-Net Apache-2.0",
    "brats": "MONAI brats_mri_segmentation (SegResNet, Myronenko 2018); Apache-2.0",
    "medula": "TotalSpineSeg — Warszawer Y., Molinier N. et al., arXiv 2411.09344 (2024); LGPL-3.0",
    "flames": "FLAMeS — Dereskewicz E., La Rosa F. et al., J Neuroimaging 2025;35(5):e70085; pesos CC BY 4.0",
    "prostata_zonas": "MONAI prostate_mri_anatomy (Bressem K.; Adams L.C. et al., Comput Biol Med 2022;148:105817 — "
                      "Prostate158); código Apache-2.0; treinado no Prostate158 (uso em pesquisa)",
    "picai": "PI-CAI baseline nnU-Net semi-supervisionado (Saha A., Bosma J.S. et al., Lancet Oncol 2024;25(7):879-887; "
             "DIAGNijmegen, Radboudumc); código Apache-2.0; pesos CC BY-NC-SA 4.0",
}

#: o que a pessoa lê e aceita antes de baixar um modelo de pesquisa (a versão muda quando o texto mudar)
LICENCA_VERSAO = 1
CHAVE_LICENCAS = "extras.licencas_pesquisa"
ACEITE = "uso em pesquisa e ensino, não clínico, não comercial"
LICENCAS = {
    "prostata_zonas": {
        "titulo": "Zonas da próstata — MONAI prostate_mri_anatomy (Prostate158)",
        "baixa": "os pesos do modelo (Zenodo, registro 7040585, algumas dezenas de MB)",
        "texto": (
            "O modelo é do MONAI Model Zoo (prostate_mri_anatomy, autor Keno Bressem), código sob a licença "
            "Apache-2.0, treinado nas imagens do Prostate158 (Charité — Universitätsmedizin Berlin), que são "
            "distribuídas para pesquisa. O próprio modelo diz: \"This is an example, not to be used for diagnostic "
            "purposes\" e \"for research/developmental purposes only and cannot be used directly for clinical "
            "procedures\".\n\n"
            "O Ipê não distribui os pesos: eles são baixados por você, direto da fonte, para este computador. "
            "Use só em pesquisa e ensino, não clínico, não comercial. As zonas saem marcadas \"modelo de pesquisa — "
            "não usar para diagnóstico\" na tela, na SEG, no SR e no laudo."),
        "links": ["https://github.com/Project-MONAI/model-zoo/tree/dev/models/prostate_mri_anatomy",
                  "https://doi.org/10.5281/zenodo.6481141"],
    },
    "picai": {
        "titulo": "Lesões da próstata — PI-CAI baseline nnU-Net (DIAGNijmegen)",
        "baixa": "um ambiente Python próprio (PyTorch de CPU, nnU-Net 1.7, picai_prep; cerca de 3 GB) e os pesos "
                 "de um fold do modelo (GitHub, 360 MB, conferidos pelo SHA-256)",
        "texto": (
            "O modelo é o de base do desafio PI-CAI (Diagnostic Image Analysis Group, Radboudumc, Nijmegen). O código é "
            "Apache-2.0; os pesos são distribuídos sob a licença Creative Commons Atribuição-NãoComercial-"
            "CompartilhaIgual 4.0 (CC BY-NC-SA 4.0) e foram treinados nos dados públicos do PI-CAI (CC BY-NC 4.0). O "
            "grupo diz: \"For research use only\" e \"Do not use the model in the clinic without further "
            "evaluation\"; foi treinado só com aparelhos Siemens e Philips, sem bobina endorretal, em pacientes sem "
            "tratamento prévio.\n\n"
            "O Ipê não distribui os pesos: eles são baixados por você, direto da fonte, para este computador, e não "
            "podem ser usados com fins comerciais. Use só em pesquisa e ensino, não clínico, não comercial. As "
            "sugestões saem marcadas \"modelo de pesquisa — não usar para diagnóstico\" na tela, na SEG, no SR e no "
            "laudo, e entram no PI-RADS como lesões a conferir."),
        "links": ["https://github.com/DIAGNijmegen/picai_nnunet_semi_supervised_gc_algorithm",
                  "https://creativecommons.org/licenses/by-nc-sa/4.0/", "https://pi-cai.grand-challenge.org/"],
    },
}


def e_pesquisa(modelo: str) -> bool:
    return modelo in PESQUISA


def _aceites(settings) -> dict:
    try:
        v = settings.get(CHAVE_LICENCAS, {}) if settings is not None else {}
    except Exception:  # noqa: BLE001
        v = {}
    return v if isinstance(v, dict) else {}


def licenca_aceita(settings, modelo: str) -> bool:
    """A pessoa leu e aceitou a licença deste modelo de pesquisa (nesta versão do texto)?"""
    if modelo not in PESQUISA:
        return True
    a = _aceites(settings).get(modelo) or {}
    return isinstance(a, dict) and int(a.get("versao") or 0) >= LICENCA_VERSAO


def aceitar_licenca(settings, modelo: str, quem: str = "") -> dict:
    from datetime import datetime
    if modelo not in PESQUISA:
        raise ValueError("não é um modelo de pesquisa")
    v = dict(_aceites(settings))
    v[modelo] = {"versao": LICENCA_VERSAO, "quem": quem or "", "quando": datetime.now().isoformat(timespec="seconds"),
                 "aceite": ACEITE}
    settings.set(CHAVE_LICENCAS, v)
    if hasattr(settings, "save"):
        settings.save()
    return v[modelo]


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
    elif modelo == "flames":
        if not _pacote("nnunetv2"):
            return Prontidao(modelo, False, "falta o nnU-Net")
        if not _pacote("dipy"):
            return Prontidao(modelo, False, "falta a DIPY (SynthSeg): rode de novo o instalar_segmentacao")
        pasta = p / "flames"
        if not (pasta.is_dir() and any(pasta.rglob("fold_0/checkpoint_final.pth"))):
            return Prontidao(modelo, False, "faltam os pesos do FLAMeS (2,4 GB)")
    elif modelo == "prostata_zonas":
        if not _pacote("monai"):
            return Prontidao(modelo, False, "falta o MONAI")
        if not (p / "prostata_zonas" / "model.pt").is_file():
            return Prontidao(modelo, False, "faltam os pesos das zonas da próstata (modelo de pesquisa)")
    elif modelo == "picai":
        base = TS.pasta_base() / "venv_picai"
        if not ((base / "Scripts" / "python.exe").is_file() or (base / "bin" / "python").is_file()):
            return Prontidao(modelo, False, "falta o ambiente do PI-CAI (modelo de pesquisa)")
        pesos = p / "picai"
        if not (pesos.is_dir() and any(pesos.rglob("fold_0/model_best.model"))):
            return Prontidao(modelo, False, "faltam os pesos do PI-CAI (modelo de pesquisa)")
    elif modelo == "medula":
        base = TS.pasta_base() / "venv_medula"
        if not ((base / "Scripts" / "python.exe").is_file() or (base / "bin" / "python").is_file()):
            return Prontidao(modelo, False, "falta o ambiente do TotalSpineSeg")
        sps = [base / "Lib" / "site-packages", *sorted((base / "lib").glob("python3*/site-packages"))]
        if not any((sp / "totalspineseg").is_dir() for sp in sps):
            return Prontidao(modelo, False, "falta o pacote do TotalSpineSeg")
    else:
        return Prontidao(modelo, False, "modelo desconhecido")
    return Prontidao(modelo, True)


def texto_prontidao(settings=None, modelos=MODELOS) -> str:
    linhas = []
    for m in modelos:
        pr = prontidao(m, settings)
        linhas.append(f"{NOMES[m]}: " + ("pronto" if pr.pronto else pr.falta))
    return "\n".join(linhas)


def motivo(modelo: str, settings=None) -> str:
    pr = prontidao(modelo, settings)
    if pr.pronto:
        return ""
    if modelo in PESQUISA:
        return (f"{NOMES[modelo]}: {pr.falta}. É um modelo de pesquisa (não clínico, não comercial): instale à parte, "
                f"depois de ler e aceitar a licença.")
    return (f"{NOMES[modelo]}: {pr.falta}. Instale em Configurações ▸ Instalar os modelos extras (MedSAM2, autoPET, "
            f"BraTS, FLAMeS, medula)… — uma vez, com internet.")


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
    """[python do ambiente, instalador, modelos…] — None sem a segmentação instalada. Os modelos de pesquisa só
    entram com a licença aceita (e levam `--aceito-uso-em-pesquisa`); sem aceite, ficam de fora."""
    from ipe.ai import totalseg as TS
    py = TS.python_do_ambiente(settings)
    if py is None:
        return None
    pedidos = [m for m in modelos if m in MODELOS or (m in PESQUISA and licenca_aceita(settings, m))]
    extra = ["--aceito-uso-em-pesquisa"] if any(m in PESQUISA for m in pedidos) else []
    return [str(py), str(caminho_do_instalador()), *pedidos, *extra]
