"""0.100.79: roda o modelo de PESQUISA do PI-CAI (nnU-Net de base, DIAGNijmegen) — no ambiente próprio `venv_picai`,
chamado pelo trabalhador da segmentação (`totalseg_worker._picai`). **Não importa nada do Ipê.**

    python -I picai_trabalhador.py <entrada> <saída> <pasta results dos pesos>

Entrada: `t2w.nii.gz`, `adc.nii.gz`, `hbv.nii.gz` (as três já na grade do T2). Saída: `mapa.npy` — o mapa de detecção
na grade do T2, (k, j, i), cada candidato com a sua probabilidade — e `caso.json`.

Os passos são os do algoritmo publicado por eles (`process.py` do picai_nnunet_semi_supervised_gc_algorithm,
Apache-2.0): o `Sample` do picai_prep, o `nnUNet_predict` (aqui um fold, sem o espelhamento do TTA, em CPU), o
softmax de volta ao espaço do T2, o corte fora do meio (que fica longe da próstata) e
`extract_lesion_candidates(threshold="dynamic")` do report_guided_annotation.
"""
from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

TAREFA = "Task2203_picai_baseline"
TREINADOR = "nnUNetTrainerV2_Loss_FL_and_CE_checkpoints"


def main(entrada: str, saida: str, results: str) -> int:
    import numpy as np
    import SimpleITK as sitk
    from picai_baseline.nnunet.softmax_export import save_softmax_nifti_from_softmax
    from picai_prep.data_utils import atomic_image_write
    from picai_prep.preprocessing import Sample, crop_or_pad
    from report_guided_annotation import extract_lesion_candidates

    ent, sai = Path(entrada), Path(saida)
    nn_in, nn_out = sai / "nnunet_in", sai / "nnunet_out"
    nn_in.mkdir(parents=True, exist_ok=True)
    nn_out.mkdir(parents=True, exist_ok=True)
    scans = [sitk.ReadImage(str(ent / f"{n}.nii.gz")) for n in ("t2w", "adc", "hbv")]
    amostra = Sample(scans=[sitk.Image(s) for s in scans])
    amostra.preprocess()
    for i, scan in enumerate(amostra.scans):
        atomic_image_write(scan, str(nn_in / f"scan_{i:04d}.nii.gz"))
    print("ETAPA PI-CAI: nnU-Net (um fold, CPU)", flush=True)
    env = dict(os.environ)
    env["RESULTS_FOLDER"] = str(results)
    # os pesos (conferidos pelo SHA-256 na instalação) são um checkpoint completo do nnU-Net 1.7, não só tensores
    env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    exe = Path(sys.executable).parent / ("nnUNet_predict.exe" if os.name == "nt" else "nnUNet_predict")
    cmd = [str(exe), "-t", TAREFA, "-i", str(nn_in), "-o", str(nn_out), "-m", "3d_fullres", "-tr", TREINADOR,
           "-f", "0", "-chk", "model_best", "--save_npz", "--num_threads_preprocessing", "1",
           "--num_threads_nifti_save", "1", "--disable_tta", "--disable_mixed_precision"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                       encoding="utf-8", errors="replace")
    print(r.stdout[-4000:], flush=True)
    if r.returncode != 0:
        raise RuntimeError(f"nnUNet_predict terminou com {r.returncode}")
    pred = np.array(np.load(nn_out / "scan.npz")["softmax"][1]).astype("float32")
    with open(nn_out / "scan.pkl", "rb") as f:
        props = pickle.load(f)                      # gerado agora pelo próprio nnU-Net, nesta pasta
    save_softmax_nifti_from_softmax(segmentation_softmax=np.array([1 - pred, pred]),
                                    out_fname=str(nn_out / "softmax.nii.gz"), properties_dict=props)
    soft = sitk.ReadImage(str(nn_out / "softmax.nii.gz"))
    arr = sitk.GetArrayFromImage(soft)
    tam = arr.shape
    arr = crop_or_pad(crop_or_pad(arr, (20, 384, 384)), tam)       # zera o que fica longe do meio (como eles)
    det = extract_lesion_candidates(arr, threshold="dynamic")[0].astype("float32")
    img = sitk.GetImageFromArray(det)
    img.CopyInformation(soft)
    na_t2 = sitk.Resample(img, scans[0], sitk.Transform(), sitk.sitkNearestNeighbor, 0.0, sitk.sitkFloat32)
    mapa = sitk.GetArrayFromImage(na_t2).astype("float32")
    np.save(sai / "mapa.npy", mapa)
    (sai / "caso.json").write_text(json.dumps({"probabilidade_do_caso": float(mapa.max()) if mapa.size else 0.0}),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
