"""Instala os modelos extras (0.99.83) no ambiente da segmentação: MedSAM2, autoPET e BraTS.

Roda com o **Python do ambiente da segmentação** (o mesmo do TotalSegmentator), numa janela própria, aberta
pelo programa em Configurações ▸ CAD/IA ▸ Instalar os modelos extras… Não importa nada do Ipê.

    python instalar_modelos_extras.py [medsam2] [autopet] [brats] [flames] [medula]      (sem nada = todos)

O que baixa (uma vez; depois funciona sem internet):

- MedSAM2: o pacote do GitHub (bowang-lab/MedSAM2, Apache-2.0), sem compilar CUDA, e os pesos
  MedSAM2_latest.pt (156 MB, Hugging Face wanglab/MedSAM2, CC BY-SA 4.0);
- autoPET: o modelo nnU-Net do autoPET II (DKFZ; Zenodo, registro 8362371), extraído em pesos/autopet;
- FLAMeS: o modelo nnU-Net das lesões no FLAIR (Zenodo, registro 17955359, CC BY 4.0), só o fold 0, em pesos/flames;
- medula: o TotalSpineSeg (NeuroPoly, LGPL-3.0) num ambiente próprio, venv_medula; o modelo (2 GB) baixa no
  primeiro uso, para pesos/totalspineseg;
- BraTS: o MONAI e os pesos do bundle brats_mri_segmentation (19 MB, Hugging Face MONAI, Apache-2.0).

0.100.79 — **modelos de pesquisa** (só com `--aceito-uso-em-pesquisa`, que o Ipê passa depois que a pessoa leu e
aceitou a licença na tela; nunca entram no "todos"):

- prostata_zonas: os pesos do MONAI prostate_mri_anatomy (Zenodo, registro 7040585), em pesos/prostata_zonas;
- picai: o ambiente próprio venv_picai (nnU-Net 1.7, picai_prep, picai_baseline, report_guided_annotation) e os
  pesos de um fold do PI-CAI baseline semi-supervisionado (GitHub LFS, CC BY-NC-SA 4.0), conferidos pelo SHA-256.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

URL_MEDSAM2_CODIGO = "https://github.com/bowang-lab/MedSAM2/archive/refs/heads/main.zip"
URL_MEDSAM2_PESOS = "https://huggingface.co/wanglab/MedSAM2/resolve/main/MedSAM2_latest.pt"
ZENODO_AUTOPET = "https://zenodo.org/api/records/8362371"
ZENODO_FLAMES = "https://zenodo.org/api/records/17955359"
URL_BRATS = "https://huggingface.co/MONAI/brats_mri_segmentation/resolve/main/models/model.pt"
AGENTE = "Ipe-instalador-de-modelos"
URL_ZONAS = "https://zenodo.org/records/7040585/files/anatomy.pt?download=1"
#: PI-CAI: o repositório e o commit conferidos (os pesos estão no Git LFS; o SHA-256 é o "oid" do LFS)
PICAI_REPO = "DIAGNijmegen/picai_nnunet_semi_supervised_gc_algorithm"
PICAI_COMMIT = "6129f7e0fe3fc3994064672aa2c7f629584004a3"
PICAI_PASTA = "results/nnUNet/3d_fullres/Task2203_picai_baseline/nnUNetTrainerV2_Loss_FL_and_CE_checkpoints__nnUNetPlansv2.1"
PICAI_PESOS = {
    "plans.pkl": ("2fe49c3272eb8cceef401b44f5c140a8f7b1d7e65d6b70393e2c867951d8669b", 950601),
    "fold_0/model_best.model": ("66ca93a14c4eebe98dfe72c4d8b7303a843b100f25fb6c5b1a18ef892c527db0", 358653454),
    "fold_0/model_best.model.pkl": ("0dfb583e815c32a92ff709e49983829c984e96450ba1468b396a2a12496871e1", 951121),
}
#: os treinadores próprios do PI-CAI (Apache-2.0), copiados para dentro do nnU-Net como no Dockerfile deles
PICAI_TREINADORES = {
    "nnUNetTrainerV2_focalLoss.py": "training/network_training/nnUNet_variants/loss_function",
    "nnUNetTrainerV2_Loss_CE_checkpoints.py": "training/network_training",
    "nnUNetTrainerV2_Loss_FL_and_CE.py": "training/network_training",
}
PESQUISA = ("prostata_zonas", "picai")
#: 0.100.82: o PyTorch de CPU (Linux e Windows); no macOS o do PyPI já é o certo
INDICE_CPU = "https://download.pytorch.org/whl/cpu"
#: 0.100.82: o par torch + torchvision abre e roda um operador de verdade (o nms é o que quebra quando não combinam)
TESTE_TORCH = ("import torch, torchvision; torchvision.ops.nms(torch.zeros((1, 4)), torch.zeros(1), 0.5); "
               "print('  PyTorch', torch.__version__, '+ torchvision', torchvision.__version__, 'ok', flush=True)")
ACEITE = "--aceito-uso-em-pesquisa"


def pasta_pesos() -> Path:
    if os.environ.get("IPE_PESOS"):
        return Path(os.environ["IPE_PESOS"])
    # o Python do ambiente mora em …/segmentacao/venv/(Scripts|bin)/python
    return Path(sys.executable).resolve().parents[2] / "pesos"


def indice_torch() -> list[str]:
    return [] if sys.platform == "darwin" else ["--index-url", INDICE_CPU]


def par_torch(py: str | Path, env: dict | None = None) -> None:
    """0.100.82: confere o torch + torchvision do ambiente e, se não combinam, reinstala os dois juntos.

    O torchvision entra por tabela (o nnU-Net puxa o timm, que pede o torchvision) e vinha do PyPI, numa versão
    feita para outro PyTorch (e, no Linux, para CUDA); um `pip install` depois também podia trocar o torch de CPU
    pelo do PyPI. Com o par descasado, qualquer import do torchvision cai em "operator torchvision::nms does not
    exist" — e com ele o TotalSegmentator inteiro."""
    if subprocess.run([str(py), "-c", TESTE_TORCH], env=env, capture_output=True).returncode == 0:
        subprocess.run([str(py), "-c", TESTE_TORCH], env=env)
        return
    print("  o torchvision não combina com o PyTorch deste ambiente: reinstalando os dois juntos…", flush=True)
    base = [str(py), "-m", "pip", "install"]
    if subprocess.run([*base, "--force-reinstall", "--no-deps", "torch", "torchvision", *indice_torch()],
                      env=env).returncode != 0:
        raise RuntimeError("o pip falhou ao reinstalar o PyTorch (veja as mensagens acima)")
    extra = [] if sys.platform == "darwin" else ["--extra-index-url", "https://pypi.org/simple"]
    subprocess.run([*base, "torch", "torchvision", *indice_torch(), *extra], env=env)   # só o que faltar
    if subprocess.run([str(py), "-c", TESTE_TORCH], env=env).returncode != 0:
        raise RuntimeError("o PyTorch e o torchvision continuam sem combinar (veja as mensagens acima)")


def travar_torch(py: str | Path, env: dict | None = None) -> list[str]:
    """0.100.82: ["-c", arquivo] que prende o torch e o torchvision nas versões já instaladas, para nenhum
    `pip install` seguinte trocá-los pelos do PyPI."""
    r = subprocess.run([str(py), "-c", "import importlib.metadata as m\nfor n in ('torch', 'torchvision'):\n"
                        "    try: print(n + '==' + m.version(n))\n    except Exception: pass"],
                       env=env, capture_output=True, text=True)
    linhas = [l.strip() for l in r.stdout.splitlines() if "==" in l]
    if r.returncode != 0 or not linhas:
        return []
    import tempfile
    arq = Path(tempfile.gettempdir()) / f"ipe-travar-torch-{os.getpid()}-{abs(hash(str(py)))}.txt"
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return ["-c", str(arq)]


def pip(*args: str) -> None:
    print("  pip install", " ".join(args), flush=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", *args, *travar_torch(sys.executable)])
    if r.returncode != 0:
        raise RuntimeError("o pip falhou (veja as mensagens acima)")


def baixar(url: str, destino: Path, rotulo: str = "") -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    print(f"  baixando {rotulo or destino.name}…", flush=True)
    with urllib.request.urlopen(req, timeout=120) as r, open(parcial, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        feito, ultimo = 0, -1
        while True:
            bloco = r.read(1024 * 1024)
            if not bloco:
                break
            f.write(bloco)
            feito += len(bloco)
            pct = int(100 * feito / total) if total else -1
            if pct != ultimo and (pct % 10 == 0 or pct < 0):
                print(f"    {feito // (1024 * 1024)} MB" + (f" ({pct}%)" if pct >= 0 else ""), flush=True)
                ultimo = pct
    parcial.replace(destino)
    return destino


def medsam2() -> None:
    print("\n[MedSAM2] pacote (sem compilar CUDA) e pesos", flush=True)
    os.environ["SAM2_BUILD_CUDA"] = "0"
    pip("hydra-core>=1.3.2", "iopath>=0.1.10", "SimpleITK>=2.4.0", "tqdm", "pillow")
    pip("--no-build-isolation", "--no-deps", URL_MEDSAM2_CODIGO)
    alvo = pasta_pesos() / "medsam2" / "MedSAM2_latest.pt"
    if not alvo.is_file():
        baixar(URL_MEDSAM2_PESOS, alvo, "MedSAM2_latest.pt (156 MB)")
    # 0.100.33: o pacote instalado vem sem os .yaml de sam2/configs — o Ipê põe a cópia dele, e a conferência
    # passa a montar a configuração do modelo de verdade (antes só importava o pacote, e o erro aparecia no uso)
    origem = Path(__file__).with_name("medsam2_sam2.1_hiera_t512.yaml")
    subprocess.run([sys.executable, "-c",
                    "import sys, shutil, importlib.util\n"
                    "from pathlib import Path\n"
                    "alvo = Path(list(importlib.util.find_spec('sam2').submodule_search_locations)[0]) / 'configs' "
                    "/ 'sam2.1_hiera_t512.yaml'\n"
                    "origem = Path(sys.argv[1])\n"
                    "if not alvo.is_file():\n"
                    "    alvo.parent.mkdir(parents=True, exist_ok=True)\n"
                    "    shutil.copyfile(origem, alvo)\n"
                    "    print('  configuracao do modelo copiada para', alvo)\n"
                    "import sam2\n"
                    "from hydra import compose\n"
                    "from sam2.build_sam import build_sam2_video_predictor_npz\n"
                    "c = compose(config_name='configs/sam2.1_hiera_t512.yaml')\n"
                    "assert c.model.image_encoder and c.model.memory_attention, 'configuracao incompleta'\n"
                    "print('  MedSAM2 ok')", str(origem)], check=True)


def autopet() -> None:
    print("\n[autoPET] modelo nnU-Net do autoPET II (Zenodo)", flush=True)
    raiz = pasta_pesos() / "autopet"
    if raiz.is_dir() and any(raiz.rglob("fold_0/checkpoint_final.pth")):
        print("  já instalado", flush=True)
        return
    req = urllib.request.Request(ZENODO_AUTOPET, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rec = json.loads(r.read().decode("utf-8"))
    arquivos = [(f.get("key") or f.get("filename") or "", (f.get("links") or {}).get("self")
                 or (f.get("links") or {}).get("download"), int(f.get("size") or 0)) for f in rec.get("files", [])]
    zips = [a for a in arquivos if a[0].lower().endswith(".zip") and a[1]]
    if not zips:
        raise RuntimeError("o registro do Zenodo não tem o .zip do modelo")
    print("  licença do registro:", (rec.get("metadata") or {}).get("license", {}), flush=True)
    escolhido = next((z for z in zips if "bs80" in z[0].lower()), None) or \
        next((z for z in zips if "resenc" in z[0].lower()), None) or min(zips, key=lambda z: z[2] or 1 << 60)
    nome, url, tam = escolhido
    zipf = baixar(url, raiz / "_baixado" / nome, f"{nome} ({tam // (1024 * 1024)} MB)" if tam else nome)
    print("  extraindo…", flush=True)
    with zipfile.ZipFile(zipf) as z:
        z.extractall(raiz)
    shutil.rmtree(raiz / "_baixado", ignore_errors=True)
    if not any(raiz.rglob("fold_0/checkpoint_final.pth")):
        raise RuntimeError("o .zip não tinha o fold_0/checkpoint_final.pth esperado")
    print("  autoPET ok", flush=True)


def brats() -> None:
    print("\n[BraTS] MONAI e pesos do SegResNet", flush=True)
    pip("monai>=1.3")
    alvo = pasta_pesos() / "brats" / "model.pt"
    if not alvo.is_file():
        baixar(URL_BRATS, alvo, "model.pt (19 MB)")
    subprocess.run([sys.executable, "-c", "import monai; print('  MONAI', monai.__version__, 'ok')"], check=True)


def flames() -> None:
    """0.100.25: FLAMeS (lesões de substância branca no FLAIR) — nnU-Net do Zenodo, CC BY 4.0, 2,4 GB."""
    print("\n[FLAMeS] modelo nnU-Net das lesões no FLAIR (Zenodo, 2,4 GB)", flush=True)
    raiz = pasta_pesos() / "flames"
    if raiz.is_dir() and any(raiz.rglob("fold_0/checkpoint_final.pth")):
        print("  já instalado", flush=True)
        return
    req = urllib.request.Request(ZENODO_FLAMES, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rec = json.loads(r.read().decode("utf-8"))
    zips = [((f.get("key") or f.get("filename") or ""), (f.get("links") or {}).get("self")
             or (f.get("links") or {}).get("download"), int(f.get("size") or 0)) for f in rec.get("files", [])]
    zips = [z for z in zips if z[0].lower().endswith(".zip") and z[1]]
    if not zips:
        raise RuntimeError("o registro do Zenodo não tem o .zip do modelo")
    nome, url, tam = max(zips, key=lambda z: z[2])
    zipf = baixar(url, raiz / "_baixado" / nome, f"{nome} ({tam // (1024 * 1024)} MB)" if tam else nome)
    print("  extraindo (só o fold 0: o Ipê roda um fold, em CPU)…", flush=True)
    with zipfile.ZipFile(zipf) as z:
        for m in z.namelist():
            partes = m.replace("\\", "/").split("/")
            if any(p.startswith("fold_") and p != "fold_0" for p in partes):
                continue                                    # os outros folds (~2 GB) não são usados
            z.extract(m, raiz)
    shutil.rmtree(raiz / "_baixado", ignore_errors=True)
    if not any(raiz.rglob("fold_0/checkpoint_final.pth")):
        raise RuntimeError("o .zip não tinha o fold_0/checkpoint_final.pth esperado")
    print("  FLAMeS ok", flush=True)


def medula() -> None:
    """0.100.26: TotalSpineSeg (medula, canal, discos e vértebras; LGPL-3.0) num ambiente SÓ dele.

    Ele copia um treinador para dentro do nnU-Net e depende do auglab, que hoje só funciona com o kornia 0.8.1
    (com o 0.9 o import quebra). No ambiente comum isso derrubaria o TotalSegmentator; por isso `venv_medula`."""
    print("\n[Medula] TotalSpineSeg num ambiente próprio (PyTorch de CPU + pacote; o modelo de 2 GB baixa no "
          "primeiro uso)", flush=True)
    base = pasta_pesos().parent / "venv_medula"
    py = base / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.is_file():
        print("  criando o ambiente em", base, flush=True)
        r = subprocess.run([sys.executable, "-m", "venv", str(base)])
        if r.returncode != 0 or not py.is_file():
            raise RuntimeError("não consegui criar o ambiente (venv)")

    def pip_m(*args: str) -> None:
        print("  pip install", " ".join(args), flush=True)
        if subprocess.run([str(py), "-m", "pip", "install", *args]).returncode != 0:
            raise RuntimeError("o pip falhou (veja as mensagens acima)")
    pip_m("--upgrade", "pip")
    pip_m("torch", "torchvision", *indice_torch())         # 0.100.82: os dois juntos, do mesmo índice
    par_torch(py)
    pip_m("totalspineseg[nnunetv2]", "kornia==0.8.1", *travar_torch(py))
    subprocess.run([str(py), "-c", "import totalspineseg, nnunetv2; from auglab.transforms.gpu.transforms import "
                    "AugTransformsGPU; print('  TotalSpineSeg ok')"], check=True)


def _sha256(arq: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(arq, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def prostata_zonas() -> None:
    """0.100.79: zonas da próstata (MONAI prostate_mri_anatomy; modelo de PESQUISA, treinado no Prostate158)."""
    print("\n[Zonas da próstata] MONAI prostate_mri_anatomy — MODELO DE PESQUISA (não clínico, não comercial)",
          flush=True)
    pip("monai>=1.3")
    alvo = pasta_pesos() / "prostata_zonas" / "model.pt"
    if not alvo.is_file():
        baixar(URL_ZONAS, alvo, "anatomy.pt (Zenodo 7040585)")
    # confere que é um checkpoint só de tensores (sem código): weights_only=True recusa qualquer outra coisa
    teste = ("import sys, torch; d = torch.load(sys.argv[1], map_location='cpu', weights_only=True); "
             "d = d.get('model', d) if isinstance(d, dict) else d; print('  pesos ok:', len(d), 'tensores')")
    if subprocess.run([sys.executable, "-c", teste, str(alvo)]).returncode != 0:
        alvo.unlink(missing_ok=True)
        raise RuntimeError("o arquivo baixado não é um checkpoint de pesos válido (apagado)")


def picai() -> None:
    """0.100.79: PI-CAI baseline (nnU-Net 1.7) num ambiente só dele; os pesos de um fold, conferidos pelo SHA-256."""
    print("\n[PI-CAI] lesões da próstata — MODELO DE PESQUISA (pesos CC BY-NC-SA 4.0: não clínico, não comercial)",
          flush=True)
    base = pasta_pesos().parent / "venv_picai"
    py = base / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.is_file():
        print("  criando o ambiente em", base, flush=True)
        r = subprocess.run([sys.executable, "-m", "venv", str(base)])
        if r.returncode != 0 or not py.is_file():
            raise RuntimeError("não consegui criar o ambiente (venv)")
    env = dict(os.environ)
    env["SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL"] = "True"     # o nnU-Net 1.7 ainda pede "sklearn"

    def pip_p(*args: str) -> None:
        print("  pip install", " ".join(args), flush=True)
        if subprocess.run([str(py), "-m", "pip", "install", *args], env=env).returncode != 0:
            raise RuntimeError("o pip falhou (veja as mensagens acima)")
    pip_p("--upgrade", "pip")
    pip_p("torch", "torchvision", *indice_torch())         # 0.100.82: os dois juntos, do mesmo índice
    par_torch(py, env)
    # numpy < 2 onde há roda pronta (até o Python 3.12); no 3.13 só existe o numpy 2
    pip_p('numpy<2; python_version < "3.13"', "nnunet==1.7.0", "SimpleITK>=2.1.1.2", "picai_prep>=2.0.0", "picai_baseline>=0.5.2",
          "report_guided_annotation", "nibabel", *travar_torch(py, env))
    sitio = subprocess.run([str(py), "-c", "import nnunet, os; print(os.path.dirname(nnunet.__file__))"],
                           capture_output=True, text=True, env=env)
    if sitio.returncode != 0 or not sitio.stdout.strip():
        raise RuntimeError("o nnU-Net 1.7 não instalou no ambiente do PI-CAI")
    nn = Path(sitio.stdout.strip().splitlines()[-1].strip())     # o nnU-Net imprime um aviso de citação antes
    if not (nn / "training" / "network_training").is_dir():
        raise RuntimeError(f"não achei a pasta do nnU-Net 1.7 ({nn})")
    for nome, sub in PICAI_TREINADORES.items():
        url = f"https://raw.githubusercontent.com/{PICAI_REPO}/{PICAI_COMMIT}/{nome}"
        baixar(url, nn / sub / nome, nome)
    raiz = pasta_pesos() / "picai" / PICAI_PASTA
    for rel, (sha, tam) in PICAI_PESOS.items():
        alvo = raiz / rel
        if alvo.is_file() and alvo.stat().st_size == tam and _sha256(alvo) == sha:
            print("  já baixado:", rel, flush=True)
            continue
        url = f"https://media.githubusercontent.com/media/{PICAI_REPO}/{PICAI_COMMIT}/{PICAI_PASTA}/{rel}"
        baixar(url, alvo, f"{rel} ({tam // (1024 * 1024)} MB)")
        if _sha256(alvo) != sha:
            alvo.unlink(missing_ok=True)
            raise RuntimeError(f"{rel}: o SHA-256 não confere com o do repositório do PI-CAI (arquivo apagado)")
    licenca = pasta_pesos() / "picai" / "LICENCA-dos-pesos.txt"
    licenca.write_text("Pesos do PI-CAI baseline nnU-Net (DIAGNijmegen, Radboudumc): Creative Commons "
                       "Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0).\n"
                       f"Fonte: https://github.com/{PICAI_REPO} (commit {PICAI_COMMIT}).\n"
                       "Uso só em pesquisa e ensino, não clínico, não comercial.\n", encoding="utf-8")
    subprocess.run([str(py), "-c", "import nnunet, picai_prep, report_guided_annotation, SimpleITK; "
                    "from picai_baseline.nnunet.softmax_export import save_softmax_nifti_from_softmax; "
                    "print('  PI-CAI ok')"], check=True, env=env)


PASSOS = {"medsam2": medsam2, "autopet": autopet, "brats": brats, "flames": flames, "medula": medula,
          "prostata_zonas": prostata_zonas, "picai": picai}


def main(argv: list[str]) -> int:
    # "todos" são só os comuns: os de pesquisa precisam ser pedidos pelo nome E com o aceite da licença
    pedidos = [a for a in argv if a in PASSOS] or [p for p in PASSOS if p not in PESQUISA]
    if any(p in PESQUISA for p in pedidos) and ACEITE not in argv:
        print("[ERRO] os modelos de pesquisa (" + ", ".join(p for p in pedidos if p in PESQUISA) + ") só instalam "
              "depois de aceita a licença no Ipê (uso em pesquisa e ensino, não clínico, não comercial).", flush=True)
        pedidos = [p for p in pedidos if p not in PESQUISA]
        if not pedidos:
            return 1
    print("=== Ipe: modelos extras (" + ", ".join(pedidos) + ") ===", flush=True)
    print("Pasta dos pesos:", pasta_pesos(), flush=True)
    erros = []
    # 0.100.82: antes de tudo, o ambiente comum (o do TotalSegmentator): torch e torchvision precisam combinar
    print("\n[PyTorch] conferindo o ambiente da segmentação", flush=True)
    try:
        par_torch(sys.executable)
    except Exception as e:  # noqa: BLE001
        erros.append(f"PyTorch: {e}")
        print(f"[ERRO] PyTorch: {e}", flush=True)
    for p in pedidos:
        try:
            PASSOS[p]()
        except Exception as e:  # noqa: BLE001
            erros.append(f"{p}: {e}")
            print(f"[ERRO] {p}: {e}", flush=True)
    print("\n" + ("Pronto." if not erros else "Terminou com erros:\n  " + "\n  ".join(erros)), flush=True)
    if "--sem-pausa" not in argv:
        try:
            input("\nEnter para fechar…")
        except EOFError:
            pass
    return 0 if not erros else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
