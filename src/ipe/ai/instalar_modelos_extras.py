"""Instala os modelos extras (0.99.83) no ambiente da segmentação: MedSAM2, autoPET e BraTS.

Roda com o **Python do ambiente da segmentação** (o mesmo do TotalSegmentator), numa janela própria, aberta
pelo programa em Configurações ▸ CAD/IA ▸ Instalar os modelos extras… Não importa nada do Ipê.

    python instalar_modelos_extras.py [medsam2] [autopet] [brats] [flames]      (sem nada = todos)

O que baixa (uma vez; depois funciona sem internet):

- MedSAM2: o pacote do GitHub (bowang-lab/MedSAM2, Apache-2.0), sem compilar CUDA, e os pesos
  MedSAM2_latest.pt (156 MB, Hugging Face wanglab/MedSAM2, CC BY-SA 4.0);
- autoPET: o modelo nnU-Net do autoPET II (DKFZ; Zenodo, registro 8362371), extraído em pesos/autopet;
- FLAMeS: o modelo nnU-Net das lesões no FLAIR (Zenodo, registro 17955359, CC BY 4.0), só o fold 0, em pesos/flames;
- BraTS: o MONAI e os pesos do bundle brats_mri_segmentation (19 MB, Hugging Face MONAI, Apache-2.0).
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


def pasta_pesos() -> Path:
    if os.environ.get("IPE_PESOS"):
        return Path(os.environ["IPE_PESOS"])
    # o Python do ambiente mora em …/segmentacao/venv/(Scripts|bin)/python
    return Path(sys.executable).resolve().parents[2] / "pesos"


def pip(*args: str) -> None:
    print("  pip install", " ".join(args), flush=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", *args])
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
    subprocess.run([sys.executable, "-c", "from sam2.build_sam import build_sam2_video_predictor_npz; "
                    "print('  MedSAM2 ok')"], check=True)


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


PASSOS = {"medsam2": medsam2, "autopet": autopet, "brats": brats, "flames": flames}


def main(argv: list[str]) -> int:
    pedidos = [a for a in argv if a in PASSOS] or list(PASSOS)
    print("=== Ipe: modelos extras (" + ", ".join(pedidos) + ") ===", flush=True)
    print("Pasta dos pesos:", pasta_pesos(), flush=True)
    erros = []
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
