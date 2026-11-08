"""Trabalhador do TotalSegmentator — roda no **ambiente próprio** da segmentação, não no programa.

O programa (`ipe.ai.totalseg`) grava numa pasta de trabalho:

* `volume.npy` — o volume da série, (k, j, i), na escala do visualizador (HU na TC);
* `job.json` — a matriz afim (RAS, nibabel), as tarefas, o dispositivo.

e roda `python totalseg_worker.py <pasta>` com o Python do ambiente da segmentação. Aqui o volume
vira imagem NIfTI **em memória** (sem dcm2niix), o TotalSegmentator roda tarefa por tarefa e cada
resultado volta como `rotulos_<tarefa>.npy` (uint8, a mesma grade do volume), mais `resultado.json`.

Este arquivo **não importa nada do Ipê**: o ambiente da segmentação não tem o programa, e o
programa não tem o PyTorch. A conversa é só por arquivos — se o trabalhador cair (memória, modelo
que não baixou), o visualizador não cai junto.

Linhas que começam com "ETAPA " são o progresso que o programa mostra na tela.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def etapa(texto: str) -> None:
    print(f"ETAPA {texto}", flush=True)


#: rótulos do SynthSeg (FreeSurfer) — só para o modo simulado; o de verdade vem da DIPY
NOMES_SYNTHSEG = {
    2: "left cerebral white matter", 3: "left cerebral cortex", 4: "left lateral ventricle",
    5: "left inferior lateral ventricle", 7: "left cerebellum white matter", 8: "left cerebellum cortex",
    10: "left thalamus", 11: "left caudate", 12: "left putamen", 13: "left pallidum", 14: "3rd ventricle",
    15: "4th ventricle", 16: "brain-stem", 17: "left hippocampus", 18: "left amygdala", 24: "CSF",
    26: "left accumbens area", 28: "left ventral DC", 41: "right cerebral white matter", 42: "right cerebral cortex",
    43: "right lateral ventricle", 44: "right inferior lateral ventricle", 46: "right cerebellum white matter",
    47: "right cerebellum cortex", 49: "right thalamus", 50: "right caudate", 51: "right putamen",
    52: "right pallidum", 53: "right hippocampus", 54: "right amygdala", 58: "right accumbens area",
    60: "right ventral DC",
}


#: fantoma dos níveis linfonodais: tarefa -> {id da classe: (código, nome)}
LINFO_SIM = {
    "headneck_bones_vessels": {3: (1, "hyoid"), 4: (2, "cricoid_cartilage"), 2: (3, "thyroid_cartilage"),
                               9: (4, "internal_carotid_artery_right"), 10: (5, "internal_carotid_artery_left"),
                               11: (6, "internal_jugular_vein_right"), 12: (7, "internal_jugular_vein_left")},
    "headneck_muscles": {1: (8, "sternocleidomastoid_right"), 2: (9, "sternocleidomastoid_left")},
    "head_glands_cavities": {9: (10, "submandibular_gland_right"), 10: (11, "submandibular_gland_left")},
    "head_muscles": {10: (12, "digastric_right"), 11: (13, "digastric_left")},
    "total": {1: (14, "skull"), 2: (15, "sternum"), 3: (16, "clavicula_left"), 4: (17, "clavicula_right"),
              5: (18, "common_carotid_artery_left"), 6: (19, "common_carotid_artery_right")},
}


def _recorte_da_cabeca(dados, afim):
    """O SynthSeg trabalha num cubo de 192 mm: com o pescoço na série, o alto da cabeça poderia ficar
    de fora. Recorta a cabeça (o que é mais claro que o fundo) e, no eixo crânio-caudal, os 200 mm de
    cima. Devolve (fatias, afim do recorte)."""
    import numpy as np
    ref = float(np.percentile(dados, 99.5))
    cabeca = dados > 0.08 * ref if ref > 0 else dados > dados.min()
    if not cabeca.any():
        return tuple(slice(None) for _ in range(3)), afim
    idx = [np.nonzero(cabeca.any(axis=tuple(a for a in range(3) if a != e)))[0] for e in range(3)]
    lo = [max(0, int(i[0]) - 4) for i in idx]
    hi = [min(n, int(i[-1]) + 5) for i, n in zip(idx, dados.shape)]
    M = np.asarray(afim, float)[:3, :3]
    eixo_z = int(np.argmax(np.abs(M[2, :])))          # o eixo dos dados mais perto do S-I
    passo = float(np.linalg.norm(M[:, eixo_z]))
    n_max = int(200.0 / max(passo, 1e-3))
    if hi[eixo_z] - lo[eixo_z] > n_max:
        if M[2, eixo_z] > 0:                          # índice crescente = mais para cima
            lo[eixo_z] = hi[eixo_z] - n_max
        else:
            hi[eixo_z] = lo[eixo_z] + n_max
    fat = tuple(slice(a, b) for a, b in zip(lo, hi))
    novo = np.array(afim, float)
    novo[:3, 3] = novo[:3, 3] + M @ np.array(lo, float)
    return fat, novo


def _synthseg(vol_kji, afim) -> tuple:
    """SynthSeg pela DIPY (PyTorch). `vol_kji` como o programa manda.

    Devolve (rótulos na grade da série (k,j,i), classes, rótulos a 1 mm (i,j,k), afim RAS da grade de
    1 mm). O SynthSeg segmenta a 1 mm qualquer que seja a série — é a "super-resolução" dele: uma
    sagital de 5 mm com 6,5 mm entre cortes tem o 3º ventrículo num corte só, mas a segmentação a 1 mm
    tem a largura dele. As medidas são feitas nesta grade; a da série serve à SEG e à tela."""
    import numpy as np
    os.environ.setdefault("DIPY_NN_BACKEND", "torch")
    from dipy.nn.torch.synthseg import SynthSeg
    from dipy.nn.utils import inv_pad_crop, recover_img, transform_img
    dados = np.ascontiguousarray(vol_kji.transpose(2, 1, 0)).astype(np.float32)     # (i, j, k)
    fat, afim_r = _recorte_da_cabeca(dados, afim)
    recorte = np.ascontiguousarray(dados[fat])
    modelo = SynthSeg()
    prob = modelo.predict(recorte, afim_r, return_prob=True)            # (192,)*3 + (33,), já limpo
    lab192 = np.asarray(modelo.labels_segmentation)[np.asarray(prob).argmax(-1)].astype(np.int32)
    del prob
    _t, params = transform_img(recorte, afim_r, target_voxsize=(1.0, 1.0, 1.0), final_size=(192, 192, 192),
                               order=0)
    lab_1mm = lab192
    if params.get("crop_value") is not None and params.get("pad_value") is not None:
        lab_1mm = inv_pad_crop(lab192, params["crop_value"], params["pad_value"])
    afim_1mm = np.eye(4)
    afim_1mm[:3, :3] = np.diag(np.asarray(params["target_voxsize"], float))
    afim_1mm[:3, 3] = np.asarray(params["new_origin_world"], float)
    serie = np.round(recover_img(lab192, params, order=0)).astype(np.uint8)
    lab = np.zeros(dados.shape, np.uint8)
    lab[fat] = serie
    nomes = {int(k): str(v) for k, v in modelo.label_dict.items() if int(k)}
    return lab.transpose(2, 1, 0), nomes, np.asarray(lab_1mm).astype(np.uint8), afim_1mm


#: 0.99.89: fantoma da carga tumoral no PET — {tarefa: {id: (código do HU, classe)}}
CARGA_SIM = {
    "total": {1: (1, "liver"), 2: (2, "spleen"), 3: (3, "kidney_left"), 4: (4, "kidney_right"),
              5: (5, "urinary_bladder"), 6: (6, "brain"), 7: (7, "heart"), 8: (8, "aorta"),
              9: (9, "vertebrae_L3"), 10: (10, "hip_left"), 11: (11, "hip_right"), 12: (12, "prostate"),
              13: (13, "lung_upper_lobe_left")},
    "head_glands_cavities": {1: (21, "parotid_gland_left"), 2: (22, "parotid_gland_right")},
}


def _simular(vol, tarefas: list, afim=None) -> dict:
    """Para os testes do programa (sem PyTorch e sem modelo): rótulos de geometria conhecida."""
    import numpy as np
    saida = {}
    nz, ny, nx = vol.shape
    for t in tarefas:
        nome = t["nome"]
        lab = np.zeros(vol.shape, np.uint8)
        if t.get("linfo"):
            # fantoma dos níveis linfonodais (0.99.20): HU = 2000 + código da estrutura
            codigos = LINFO_SIM.get(nome, {})
            for cid, (cod, _n) in codigos.items():
                lab[vol == 2000 + cod] = cid
            saida[nome] = (lab, {cid: n for cid, (_c, n) in codigos.items()})
            continue
        if t.get("carga"):                   # 0.99.89: carga tumoral PET — HU = 4000 + código do órgão
            codigos = CARGA_SIM.get(nome, {})
            for cid, (cod, _n) in codigos.items():
                lab[vol == 4000 + cod] = cid
            saida[nome] = (lab, {cid: n for cid, (_c, n) in codigos.items()})
            continue
        if t.get("figado_rm"):               # 0.99.49: fígado = 600 (metade esquerda S2, direita S7), baço = 500
            if nome == "liver_segments_mr":
                fig = vol == 600
                meio = nx // 2
                lab[:, :, :meio][fig[:, :, :meio]] = 7
                lab[:, :, meio:][fig[:, :, meio:]] = 2
                saida[nome] = (lab, {7: "liver_segment_7", 2: "liver_segment_2"})
            else:
                lab[vol == 600] = 5
                lab[vol == 500] = 1
                saida[nome] = (lab, {5: "liver", 1: "spleen"})
            continue
        if t.get("fig_lesoes"):              # 0.99.82: fígado = 620 ou 630, lesão = 630; segmentos por terço de x
            fig = (vol == 620) | (vol == 630)
            if nome.startswith("liver_lesions"):
                lab[vol == 630] = 1
                saida[nome] = (lab, {1: "liver_lesions"})
            else:
                terco = np.arange(nx)[None, None, :]
                lab[fig & (terco < nx // 3)] = 7
                lab[fig & (terco >= nx // 3) & (terco < 2 * nx // 3)] = 4
                lab[fig & (terco >= 2 * nx // 3)] = 2
                saida[nome] = (lab, {7: "liver_segment_7", 4: "liver_segment_4", 2: "liver_segment_2"})
            continue
        if t.get("enfisema"):                # 0.99.77: pulmão = −998 a −700 HU, traqueia = −999
            pulmao = (vol >= -998) & (vol <= -700)
            ks = np.nonzero(pulmao.any(axis=(1, 2)))[0]
            if len(ks):
                k0, k1 = int(ks[0]), int(ks[-1]) + 1
                kk = np.arange(nz)[:, None, None]
                dir_ = np.zeros(vol.shape, bool)
                dir_[:, :, : nx // 2] = True
                terco1, terco2 = k0 + (k1 - k0) / 3.0, k0 + 2 * (k1 - k0) / 3.0
                meio = (k0 + k1) / 2.0
                lab[pulmao & dir_ & (kk < terco1)] = 3            # inferior direito (k cresce para cima)
                lab[pulmao & dir_ & (kk >= terco1) & (kk < terco2)] = 2
                lab[pulmao & dir_ & (kk >= terco2)] = 1
                lab[pulmao & ~dir_ & (kk < meio)] = 5
                lab[pulmao & ~dir_ & (kk >= meio)] = 4
            lab[vol == -999] = 6
            saida[nome] = (lab, {1: "lung_upper_lobe_right", 2: "lung_middle_lobe_right",
                                 3: "lung_lower_lobe_right", 4: "lung_upper_lobe_left", 5: "lung_lower_lobe_left",
                                 6: "trachea"})
            continue
        if t.get("composicao"):              # 0.99.47: L3 = 701, fígado = 61, baço = 51, cavidade = −101/61/51/21
            if nome == "trunk_cavities":
                lab[np.isin(vol, (-101, 61, 51, 21))] = 1
                saida[nome] = (lab, {1: "abdominal_cavity"})
            else:
                lab[vol == 701] = 27
                lab[vol == 61] = 5
                lab[vol == 51] = 1
                saida[nome] = (lab, {27: "vertebrae_L3", 5: "liver", 1: "spleen"})
            continue
        if t.get("nodulos"):                  # 0.99.46: nódulo sólido = 45 HU, vidro fosco = −601, pulmão = −850
            pulmao = np.isin(vol, (-850, 45, -601))
            if nome == "lung_nodules":
                lab[vol == -850] = 1
                lab[np.isin(vol, (45, -601))] = 2
                saida[nome] = (lab, {1: "lung", 2: "lung_nodules"})
            else:
                metade = np.zeros(vol.shape, bool)
                metade[:, :, : nx // 2] = True
                lab[pulmao & metade] = 10
                lab[pulmao & ~metade] = 11
                saida[nome] = (lab, {10: "lung_upper_lobe_right", 11: "lung_upper_lobe_left"})
            continue
        if t.get("neuro"):
            # fantoma do SynthSeg (0.99.17): HU = 1000 + rótulo do FreeSurfer
            lab = np.where(vol >= 1000, np.clip(vol - 1000, 0, 255), 0).astype(np.uint8)
            saida[nome] = (lab, {int(k): NOMES_SYNTHSEG.get(int(k), str(k)) for k in np.unique(lab) if k})
            continue
        if t.get("cefalo"):
            # fantoma da cefalometria (0.99.15): cada estrutura tem um HU próprio
            codigos = {
                "head_glands_cavities": {12: (-1100, -900), 18: (61, 61), 19: (1101, 1101)},
                "headneck_bones_vessels": {3: (1201, 1201)},
                "craniofacial_structures": {1: (1301, 1301)},
                "head_muscles": {9: (62, 62)},
                "total": {26: (402, 402), 27: (403, 403), 28: (404, 404)},
            }.get(nome, {})
            nomes = {12: "oropharynx", 18: "soft_palate", 19: "hard_palate", 3: "hyoid", 1: "mandible",
                     9: "tongue", 26: "vertebrae_C2", 27: "vertebrae_C3", 28: "vertebrae_C4"}
            for cid, (a, b) in codigos.items():
                lab[(vol >= a) & (vol <= b)] = cid
            saida[nome] = (lab, {c: nomes[c] for c in codigos})
            continue
        coluna = nome in ("vertebrae_mr", "vertebrae_body") or any("vertebrae" in r or "discs" in r
                                                                     for r in (t.get("roi") or []))
        if coluna:
            # fantoma da coluna: osso = 300, disco = 150; as vértebras são as faixas de osso ao longo
            # de k, nomeadas de cima para baixo a partir de t["_sim_inicio"] (padrão L1)
            if nome in ("vertebrae_body",) or "intervertebral_discs" in (t.get("roi") or []):
                lab[vol == 150] = 2
                saida[nome] = (lab, {2: "intervertebral_discs"})
                continue
            ossos = (vol == 300).any(axis=(1, 2))
            faixas, k = [], 0
            while k < len(ossos):
                if ossos[k]:
                    k1 = k
                    while k1 < len(ossos) and ossos[k1]:
                        k1 += 1
                    faixas.append((k, k1))
                    k = k1
                else:
                    k += 1
            ordem = [f"C{i}" for i in range(1, 8)] + [f"T{i}" for i in range(1, 13)] + \
                [f"L{i}" for i in range(1, 6)] + ["S1"]
            ini = ordem.index(t.get("_sim_inicio", "L1"))
            # como o modelo de verdade, a contagem é anatômica: começa na faixa mais de cima (cabeça).
            # Na matriz afim (RAS), k que cresce para +z vai para cima: aí a de cima é a última.
            if afim is not None and float(afim[2][2]) > 0:
                faixas = faixas[::-1]
            classes = {}
            for n, (k0, k1) in enumerate(faixas, start=1):
                v = ordem[min(ini + n - 1, len(ordem) - 1)]
                classe = "sacrum" if (v == "S1" and nome == "vertebrae_mr") else f"vertebrae_{v}"
                fatia = lab[k0:k1]
                fatia[vol[k0:k1] == 300] = n
                classes[n] = classe
            saida[nome] = (lab, classes)
            continue
        if nome.startswith("total"):
            # "fígado" (5): o bloco claro do fantoma; "baço" (1): um cubo de 10 voxels de lado
            lab[vol > float(t.get("_limiar", 100))] = 5
            lab[nz // 2 - 5:nz // 2 + 5, ny // 2 - 5:ny // 2 + 5, 2:12] = 1
            classes = {1: "spleen", 5: "liver"}
        else:                                       # segmentos do fígado: metade 7, metade 8
            figado = vol > float(t.get("_limiar", 100))
            meio = nx // 2
            lab[:, :, :meio][figado[:, :, :meio]] = 7
            lab[:, :, meio:][figado[:, :, meio:]] = 8
            classes = {7: "liver_segment_7", 8: "liver_segment_8"}
        saida[nome] = (lab, classes)
    return saida


# ================================================================== modelos extras (0.99.83)
# MedSAM2 (caixa → máscara 3D), autoPET (lesões no PET-FDG) e BraTS (glioma). Os pesos ficam em
# IPE_PESOS (…/segmentacao/pesos), baixados pelo instalar_modelos_extras. Nada do Ipê é importado aqui.
ESPECIAIS = ("medsam2", "autopet", "brats")


def _pesos() -> Path:
    return Path(os.environ.get("IPE_PESOS") or os.environ.get("TOTALSEG_HOME_DIR") or ".")


def _canais(d: Path, job: dict) -> dict:
    import numpy as np
    return {n: np.load(d / f"canal_{n}.npy") for n in job.get("canais", [])}


def _maior_ilha_tocando(m, k_ref: int):
    """Só os cortes contíguos ao corte de referência que têm máscara (o resto é vazamento da propagação)."""
    import numpy as np
    tem = m.reshape(m.shape[0], -1).any(1)
    out = np.zeros_like(m)
    if not tem[k_ref]:
        return out
    k0 = k_ref
    while k0 - 1 >= 0 and tem[k0 - 1]:
        k0 -= 1
    k1 = k_ref
    while k1 + 1 < m.shape[0] and tem[k1 + 1]:
        k1 += 1
    out[k0:k1 + 1] = m[k0:k1 + 1]
    return out


def _medsam2(vol, t: dict):
    """Caixa num corte → máscara 3D, propagada para cima e para baixo (vídeo do SAM2)."""
    import numpy as np
    import torch
    from PIL import Image
    from sam2.build_sam import build_sam2_video_predictor_npz
    k, x0, y0, x1, y1 = (int(round(v)) for v in t["caixa"])
    lo, hi = (float(v) for v in t["janela"])
    alcance = int(t.get("alcance", 60))
    nz, ny, nx = vol.shape
    k0, k1 = max(0, k - alcance), min(nz, k + alcance + 1)
    sub = np.clip((vol[k0:k1].astype(np.float32) - lo) / max(hi - lo, 1e-6), 0, 1) * 255.0
    img = np.empty((k1 - k0, 3, 512, 512), np.float32)
    for z in range(k1 - k0):
        r = np.asarray(Image.fromarray(sub[z].astype(np.uint8)).resize((512, 512), Image.BILINEAR), np.float32)
        img[z] = r[None] / 255.0
    media = np.array([0.485, 0.456, 0.406], np.float32)[None, :, None, None]
    desvio = np.array([0.229, 0.224, 0.225], np.float32)[None, :, None, None]
    img = torch.from_numpy((img - media) / desvio)
    ckpt = _pesos() / "medsam2" / "MedSAM2_latest.pt"
    if not ckpt.is_file():
        raise RuntimeError(f"faltam os pesos do MedSAM2 ({ckpt}): rode o instalar_modelos_extras")
    etapa("MedSAM2: carregando o modelo")
    pred = build_sam2_video_predictor_npz("configs/sam2.1_hiera_t512.yaml", str(ckpt), device="cpu")
    caixa = np.array([x0, y0, x1, y1], np.float32)
    mask = np.zeros((k1 - k0, ny, nx), bool)
    with torch.inference_mode():
        estado = pred.init_state(img, ny, nx)
        for reverso in (False, True):
            etapa("MedSAM2: propagando " + ("para baixo" if reverso else "para cima"))
            pred.add_new_points_or_box(inference_state=estado, frame_idx=k - k0, obj_id=1, box=caixa)
            for f, _ids, logits in pred.propagate_in_video(estado, reverse=reverso):
                mask[f] |= (logits[0] > 0.0).cpu().numpy()[0]
            pred.reset_state(estado)
    out = np.zeros(vol.shape, np.uint8)
    out[k0:k1] = _maior_ilha_tocando(mask, k - k0)
    return out, {1: "lesao"}


def _sim_medsam2(vol, t: dict):
    """Simulado: no corte da caixa e nos vizinhos, o que está dentro da caixa e perto do valor do centro."""
    import numpy as np
    k, x0, y0, x1, y1 = (int(round(v)) for v in t["caixa"])
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    ref = float(vol[k, cy, cx])
    out = np.zeros(vol.shape, np.uint8)
    perto = np.abs(vol.astype(np.float32) - ref) <= float(t.get("_tolerancia", 30))
    caixa = np.zeros(vol.shape[1:], bool)
    caixa[y0:y1 + 1, x0:x1 + 1] = True
    for z in range(vol.shape[0]):
        out[z][perto[z] & caixa] = 1
    out = _maior_ilha_tocando(out.astype(bool), k).astype(np.uint8)
    return out, {1: "lesao"}


def _autopet_pasta():
    """A pasta do modelo nnU-Net do autoPET (a que tem plans.json e fold_0/checkpoint_final.pth)."""
    raiz = _pesos() / "autopet"
    achados = sorted(p.parent.parent for p in raiz.rglob("fold_0/checkpoint_final.pth")) if raiz.is_dir() else []
    if not achados:
        raise RuntimeError(f"faltam os pesos do autoPET em {raiz}: rode o instalar_modelos_extras")
    pref = [p for p in achados if "bs80" in p.name] or [p for p in achados if "3d_fullres" in p.name] or achados
    return pref[0]


def _autopet(vol, canais: dict, job: dict):
    """PET (SUV) + TC na grade do PET → lesões (nnU-Net do autoPET II, um fold)."""
    import numpy as np
    import torch
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    ct = canais.get("ct")
    if ct is None:
        raise RuntimeError("a TC do PET/CT não veio (canal_ct)")
    etapa("autoPET: carregando o modelo")
    pred = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=False,
                           device=torch.device("cpu"), verbose=False, allow_tqdm=False)
    pred.initialize_from_trained_model_folder(str(_autopet_pasta()), use_folds=(0,),
                                              checkpoint_name="checkpoint_final.pth")
    suv = canais.get("suv", vol)
    img = np.stack([ct.astype(np.float32), suv.astype(np.float32)])          # _0000 = TC, _0001 = SUV
    props = {"spacing": [float(x) for x in job["espacamento"]]}
    etapa("autoPET: segmentando as lesões")
    seg = pred.predict_single_npy_array(img, props, None, None, False)
    return np.asarray(seg, np.uint8), {1: "lesao_fdg"}


def _sim_autopet(vol, canais: dict, job: dict):
    """Simulado: SUV ≥ 4 fora do 'cérebro' (TC = 37) e da 'bexiga' (TC = 5)."""
    import numpy as np
    ct = canais.get("ct", np.zeros_like(vol))
    suv = canais.get("suv", vol)
    lab = ((suv >= 4.0) & (np.abs(ct - 37) > 0.5) & (np.abs(ct - 5) > 0.5)).astype(np.uint8)
    return lab, {1: "lesao_fdg"}


def _brats(vol, canais: dict, job: dict, cerebro=None):
    """T1 pós, T1, T2 e FLAIR (já na grade da T1 pós) → TC, WT, ET (SegResNet do MONAI)."""
    import numpy as np
    import torch
    from monai.inferers import sliding_window_inference
    from monai.networks.nets import SegResNet
    pesos = _pesos() / "brats" / "model.pt"
    if not pesos.is_file():
        raise RuntimeError(f"faltam os pesos do BraTS ({pesos}): rode o instalar_modelos_extras")
    falta = [n for n in ("t1", "t2", "flair") if n not in canais]
    if falta:
        raise RuntimeError("faltam as sequências: " + ", ".join(falta))
    dz, dy, dx = (float(x) for x in job["espacamento"])
    chans = [vol] + [canais[n] for n in ("t1", "t2", "flair")]
    x = torch.from_numpy(np.stack([c.astype(np.float32) for c in chans]))[None]      # (1, 4, z, y, x)
    if cerebro is not None:
        x = x * torch.from_numpy(cerebro.astype(np.float32))[None, None]
    alvo = (max(8, int(round(vol.shape[0] * dz))), int(round(vol.shape[1] * dy)), int(round(vol.shape[2] * dx)))
    x = torch.nn.functional.interpolate(x, size=alvo, mode="trilinear", align_corners=False)
    # normalização por canal só onde há cérebro (NormalizeIntensityd(nonzero=True, channel_wise=True))
    for c in range(4):
        v = x[0, c]
        nz = v != 0
        if nz.any():
            m, s = v[nz].mean(), v[nz].std().clamp_min(1e-6)
            v[nz] = (v[nz] - m) / s
    x = x.permute(0, 1, 4, 3, 2).contiguous()           # o bundle lê o NIfTI como (x, y, z)
    pad = [(-n) % 8 for n in x.shape[2:]]
    x = torch.nn.functional.pad(x, (0, pad[2], 0, pad[1], 0, pad[0]))
    etapa("BraTS: carregando o modelo")
    net = SegResNet(blocks_down=[1, 2, 2, 4], blocks_up=[1, 1, 1], init_filters=16, in_channels=4, out_channels=3,
                    dropout_prob=0.2)
    sd = torch.load(str(pesos), map_location="cpu")
    net.load_state_dict(sd.get("state_dict", sd) if isinstance(sd, dict) else sd)
    net.eval()
    etapa("BraTS: segmentando o tumor")
    with torch.inference_mode():
        y = sliding_window_inference(x, roi_size=(240, 240, 160), sw_batch_size=1, predictor=net, overlap=0.5)
        y = torch.sigmoid(y) > 0.5
    y = y[..., :y.shape[2] - pad[0] or None, :y.shape[3] - pad[1] or None, :y.shape[4] - pad[2] or None]
    y = y.permute(0, 1, 4, 3, 2).float()
    y = torch.nn.functional.interpolate(y, size=vol.shape, mode="nearest")[0].numpy() > 0.5
    tc, wt, et = y[0], y[1], y[2]
    lab = np.zeros(vol.shape, np.uint8)
    lab[wt] = 2                    # edema (WT − TC)
    lab[tc] = 1                    # necrose / parte não captante (TC − ET)
    lab[et] = 3                    # captação (ET)
    return lab, {1: "necrose", 2: "edema", 3: "captante"}


def _sim_brats(vol, canais: dict, job: dict, cerebro=None):
    """Simulado: T1 pós ≥ 900 = captante; FLAIR ≥ 700 = edema; T1 pós entre 300 e 400 dentro do tumor = necrose."""
    import numpy as np
    flair = canais.get("flair", np.zeros_like(vol))
    lab = np.zeros(vol.shape, np.uint8)
    lab[flair >= 700] = 2
    lab[(vol >= 300) & (vol <= 400) & (flair >= 700)] = 1
    lab[vol >= 900] = 3
    return lab, {1: "necrose", 2: "edema", 3: "captante"}


def _versao_especial(especiais: list) -> str:
    from importlib.metadata import version
    nomes = []
    for t in especiais:
        n = t["nome"]
        pacote = {"medsam2": "MedSAM2", "autopet": "nnunetv2", "brats": "monai"}.get(n, n)
        try:
            nomes.append(f"{n} ({pacote} {version(pacote)})")
        except Exception:  # noqa: BLE001
            nomes.append(n)
    return ", ".join(nomes)


def rodar_especial(nome: str, vol, d: Path, job: dict, t: dict, simular: bool, anteriores: dict):
    canais = _canais(d, job)
    if nome == "medsam2":
        return _sim_medsam2(vol, t) if simular else _medsam2(vol, t)
    if nome == "autopet":
        return _sim_autopet(vol, canais, job) if simular else _autopet(vol, canais, job)
    if nome == "brats":
        cerebro = None
        for lab, classes in anteriores.values():          # a máscara do encéfalo da tarefa anterior (total_mr)
            ids = [k for k, v in classes.items() if v == "brain"]
            if ids:
                import numpy as np
                cerebro = np.isin(lab, ids)
        return (_sim_brats if simular else _brats)(vol, canais, job, cerebro)
    raise RuntimeError(f"tarefa especial desconhecida: {nome}")


def main(pasta: str) -> int:
    d = Path(pasta)
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    resultado = {"ok": False, "tarefas": {}, "erro": "", "versao": ""}
    try:
        import numpy as np
        vol = np.load(d / "volume.npy")
        especiais = [t for t in job["tarefas"] if t["nome"] in ESPECIAIS]
        comuns = [t for t in job["tarefas"] if t["nome"] not in ESPECIAIS]
        if job.get("simular"):
            etapa("simulando (teste)")
            feitos = _simular(vol, comuns, job.get("affine")) if comuns else {}
            for t in especiais:
                feitos[t["nome"]] = rodar_especial(t["nome"], vol, d, job, t, True, dict(feitos))
            for nome, (lab, classes) in feitos.items():
                np.save(d / f"rotulos_{nome}.npy", lab)
                resultado["tarefas"][nome] = {"classes": {str(k): v for k, v in classes.items()}, "segundos": 0.0}
                if nome == "synthseg" and job.get("affine") is not None:
                    # como o de verdade: a grade "de 1 mm" (aqui, a própria série, nos eixos i, j, k)
                    np.save(d / f"rotulos_{nome}_1mm.npy", np.ascontiguousarray(lab.transpose(2, 1, 0)))
                    resultado["tarefas"][nome]["afim_1mm"] = job["affine"]
            resultado["versao"] = "simulado"
        elif not comuns:                                    # 0.99.83: só MedSAM2 / autoPET / BraTS
            feitos = {}
            for t in especiais:
                etapa(t.get("rotulo", t["nome"]))
                t0 = time.time()
                lab, classes = rodar_especial(t["nome"], vol, d, job, t, False, feitos)
                feitos[t["nome"]] = (lab, classes)
                np.save(d / f"rotulos_{t['nome']}.npy", lab.astype(np.uint8))
                resultado["tarefas"][t["nome"]] = {"classes": {str(k): v for k, v in classes.items()},
                                                   "segundos": round(time.time() - t0, 1)}
            resultado["versao"] = _versao_especial(especiais)
        else:
            etapa("carregando o TotalSegmentator")
            import nibabel as nib
            import totalsegmentator as TS
            from totalsegmentator.map_to_binary import class_map
            from totalsegmentator.python_api import totalsegmentator
            try:
                from importlib.metadata import version
                resultado["versao"] = version("TotalSegmentator")
            except Exception:  # noqa: BLE001
                resultado["versao"] = getattr(TS, "__version__", "")
            if all(t["nome"] == "synthseg" for t in job["tarefas"]):
                try:
                    from importlib.metadata import version
                    resultado["versao"] = f"SynthSeg · DIPY {version('dipy')}"
                except Exception:  # noqa: BLE001
                    resultado["versao"] = "SynthSeg · DIPY"
            afim = np.asarray(job["affine"], float)
            img = nib.Nifti1Image(np.ascontiguousarray(vol.transpose(2, 1, 0)), afim)
            feitos = {}
            for t in comuns:
                nome = t["nome"]
                etapa(f"{t.get('rotulo', nome)}")
                t0 = time.time()
                if nome == "synthseg":                  # 0.99.17: encéfalo pela DIPY (não é do TotalSegmentator)
                    lab, classes, lab_1mm, afim_1mm = _synthseg(vol, afim)
                    np.save(d / f"rotulos_{nome}.npy", lab)
                    np.save(d / f"rotulos_{nome}_1mm.npy", lab_1mm)
                    resultado["tarefas"][nome] = {"classes": {str(k): v for k, v in classes.items()},
                                                  "segundos": round(time.time() - t0, 1),
                                                  "afim_1mm": np.asarray(afim_1mm, float).tolist()}
                    continue
                kw = dict(task=nome, ml=True, device=job.get("device", "cpu"), quiet=False,
                          nr_thr_resamp=1, nr_thr_saving=1)
                if t.get("roi"):
                    kw["roi_subset"] = list(t["roi"])
                if t.get("fast"):
                    kw["fast"] = True
                seg = totalsegmentator(img, None, **kw)
                lab = np.asarray(seg.dataobj)
                if lab.shape != img.shape:
                    raise RuntimeError(f"{nome}: a segmentação voltou com outra grade ({lab.shape} × {img.shape})")
                np.save(d / f"rotulos_{nome}.npy", lab.transpose(2, 1, 0).astype(np.uint8))
                resultado["tarefas"][nome] = {"classes": {str(k): v for k, v in class_map[nome].items()},
                                              "segundos": round(time.time() - t0, 1)}
                feitos[nome] = (lab.transpose(2, 1, 0), {int(k): v for k, v in class_map[nome].items()})
            for t in especiais:                             # 0.99.83: o BraTS usa o encéfalo do total_mr
                etapa(t.get("rotulo", t["nome"]))
                t0 = time.time()
                lab, classes = rodar_especial(t["nome"], vol, d, job, t, False, feitos)
                np.save(d / f"rotulos_{t['nome']}.npy", lab.astype(np.uint8))
                resultado["tarefas"][t["nome"]] = {"classes": {str(k): v for k, v in classes.items()},
                                                   "segundos": round(time.time() - t0, 1)}
            if especiais:
                resultado["versao"] += " + " + _versao_especial(especiais)
        resultado["ok"] = True
    except Exception as e:  # noqa: BLE001 - o motivo vai para o programa mostrar
        resultado["erro"] = f"{type(e).__name__}: {e}"
        resultado["detalhe"] = traceback.format_exc()[-4000:]
    (d / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    etapa("pronto" if resultado["ok"] else "erro")
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":           # o TotalSegmentator usa multiprocessamento: isto é obrigatório
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main(sys.argv[1]))
