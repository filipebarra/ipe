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


def _simular(vol, tarefas: list, afim=None) -> dict:
    """Para os testes do programa (sem PyTorch e sem modelo): rótulos de geometria conhecida."""
    import numpy as np
    saida = {}
    nz, ny, nx = vol.shape
    for t in tarefas:
        nome = t["nome"]
        lab = np.zeros(vol.shape, np.uint8)
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
            afim = np.asarray(job["affine"], float)
            img = nib.Nifti1Image(np.ascontiguousarray(vol.transpose(2, 1, 0)), afim)
            for t in job["tarefas"]:
                nome = t["nome"]
                etapa(f"{t.get('rotulo', nome)}")
                t0 = time.time()
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
