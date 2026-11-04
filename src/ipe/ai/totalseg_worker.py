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


def main(pasta: str) -> int:
    d = Path(pasta)
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    resultado = {"ok": False, "tarefas": {}, "erro": "", "versao": ""}
    try:
        import numpy as np
        vol = np.load(d / "volume.npy")
        if job.get("simular"):
            etapa("simulando (teste)")
            for nome, (lab, classes) in _simular(vol, job["tarefas"], job.get("affine")).items():
                np.save(d / f"rotulos_{nome}.npy", lab)
                resultado["tarefas"][nome] = {"classes": {str(k): v for k, v in classes.items()}, "segundos": 0.0}
                if nome == "synthseg" and job.get("affine") is not None:
                    # como o de verdade: a grade "de 1 mm" (aqui, a própria série, nos eixos i, j, k)
                    np.save(d / f"rotulos_{nome}_1mm.npy", np.ascontiguousarray(lab.transpose(2, 1, 0)))
                    resultado["tarefas"][nome]["afim_1mm"] = job["affine"]
            resultado["versao"] = "simulado"
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
            for t in job["tarefas"]:
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
