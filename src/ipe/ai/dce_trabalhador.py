"""0.100.119: o trabalhador do alinhamento da dinâmica da mama — roda no ambiente próprio `venv_dce` (itk-elastix).

Não importa nada do Ipê: só `numpy` e `itk`. O programa grava as fases em `.npy` (corte, linha, coluna), chama

    python dce_trabalhador.py <pasta>

e lê de volta `saida.json` e as `alinhada<k>.npy`. Linhas do tipo `ETAPA …` na saída padrão são o andamento.

O método vem do projeto antigo do Filipe (dce-align): **registro conjunto (groupwise) do elastix** — as N fases
empilhadas num volume 4D e alinhadas todas ao mesmo tempo com a métrica de PCA, que trata a variação do sinal ao longo
do tempo (o realce pelo contraste) como esperada e por isso não se deixa enganar por ela. A deformação é B-spline
suave (malha de 32 mm: respiração e movimento do corpo, não detalhe fino). Para caber na memória, o registro é feito
com o plano reduzido (`reduzir` vezes) e a transformação é aplicada depois na resolução cheia (transformix).

A "porta do movimento" mede o quanto o registro reduziu o resíduo |pós − pré|: o realce fica, o desalinhamento sai.
Abaixo do limite o exame não tem movimento que valha corrigir e nada é gerado.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np


def etapa(texto: str) -> None:
    print("ETAPA " + texto, flush=True)


def _reduzir(a: np.ndarray, f: int) -> np.ndarray:
    """Média em blocos de f × f no plano de cada corte."""
    if f <= 1:
        return a
    z, h, w = a.shape
    h2, w2 = h // f * f, w // f * f
    return a[:, :h2, :w2].reshape(z, h2 // f, f, w2 // f, f).mean(axis=(2, 4), dtype=np.float32)


def _para_itk4d(fases: list[np.ndarray], espaco: tuple[float, float, float]):
    import itk
    arr = np.stack([f.astype(np.float32, copy=False) for f in fases], axis=0)          # (t, z, y, x)
    img = itk.image_from_array(arr)                                                    # vira (x, y, z, t)
    img.SetSpacing([float(espaco[0]), float(espaco[1]), float(espaco[2]), 1.0])
    return img


def registrar(fases: list[np.ndarray], espaco, grade_mm: float, iteracoes: int, amostras: int):
    import itk
    img = _para_itk4d(fases, espaco)
    p = itk.ParameterObject.New()
    m = p.GetDefaultParameterMap("groupwise")
    m["MaximumNumberOfIterations"] = [str(int(iteracoes))]
    m["FinalGridSpacingInPhysicalUnits"] = [str(float(grade_mm))]
    m["NumberOfSpatialSamples"] = [str(int(amostras))]
    p.AddParameterMap(m)
    res, tparams = itk.elastix_registration_method(img, img, parameter_object=p, log_to_console=False)
    out = itk.array_from_image(res)
    return [np.asarray(out[t]) for t in range(out.shape[0])], tparams


def aplicar_cheio(fases: list[np.ndarray], espaco, tparams):
    """A transformação achada no plano reduzido, aplicada às fases na resolução cheia (só reamostragem)."""
    import itk
    img = _para_itk4d(fases, espaco)
    tamanho = [str(s) for s in img.GetLargestPossibleRegion().GetSize()]
    esp = [str(s) for s in img.GetSpacing()]
    origem = [str(o) for o in img.GetOrigin()]
    novo = itk.ParameterObject.New()
    for i in range(tparams.GetNumberOfParameterMaps()):
        pm = tparams.GetParameterMap(i)
        pm["Size"], pm["Spacing"], pm["Origin"] = tamanho, esp, origem
        novo.AddParameterMap(pm)
    res = itk.transformix_filter(img, transform_parameter_object=novo, log_to_console=False)
    out = itk.array_from_image(res)
    return [np.asarray(out[t]) for t in range(out.shape[0])]


def residuo(fases: list[np.ndarray]) -> float:
    """Média de |pós − pré| sobre as fases pós."""
    pre = fases[0].astype(np.float32)
    ds = [float(np.abs(f.astype(np.float32) - pre).mean()) for f in fases[1:]]
    return float(np.mean(ds)) if ds else 0.0


def reducao_do_residuo(antes: list[np.ndarray], depois: list[np.ndarray]) -> float:
    """Quanto o registro tirou do resíduo (%): o que é desalinhamento sai, o realce pelo contraste fica."""
    a, d = residuo(antes), residuo(depois)
    return 100.0 * (a - d) / a if a > 0 else 0.0


def main(pasta: str) -> int:
    p = Path(pasta)
    cfg = json.loads((p / "entrada.json").read_text("utf-8"))
    t0 = time.time()
    etapa("lendo as fases")
    cheias = [np.load(p / nome) for nome in cfg["fases"]]
    dx, dy, dz = cfg["espaco"]
    f = max(1, int(cfg.get("reduzir", 2)))
    baixas = [_reduzir(a, f) for a in cheias]
    esp_baixo = (dx * f, dy * f, dz)
    etapa(f"registro conjunto de {len(cheias)} fases (plano reduzido {f}×) — pode levar vários minutos")
    alinhadas_baixas, tparams = registrar(baixas, esp_baixo, cfg.get("grade_mm", 32.0),
                                          cfg.get("iteracoes", 256), cfg.get("amostras", 2048))
    pct = reducao_do_residuo(baixas, alinhadas_baixas)
    saida = {"movimento_pct": round(pct, 2), "sem_movimento": False, "fases": len(cheias),
             "reduzir": f, "grade_mm": cfg.get("grade_mm", 32.0)}
    if not cfg.get("forcar") and pct < float(cfg.get("min_pct", 12.0)):
        saida.update(sem_movimento=True, segundos=round(time.time() - t0, 1))
        (p / "saida.json").write_text(json.dumps(saida), encoding="utf-8")
        etapa(f"sem movimento que valha corrigir ({pct:.1f}%)")
        return 0
    etapa("aplicando a transformação na resolução cheia")
    if f > 1:
        alinhadas = aplicar_cheio(cheias, (dx, dy, dz), tparams)
    else:
        alinhadas = alinhadas_baixas
    for k, a in enumerate(alinhadas):
        np.save(p / f"alinhada{k}.npy", np.asarray(a, np.float32))
    saida["segundos"] = round(time.time() - t0, 1)
    (p / "saida.json").write_text(json.dumps(saida), encoding="utf-8")
    etapa("pronto")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1]))
    except Exception as e:  # noqa: BLE001
        pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
        try:
            (pasta / "saida.json").write_text(json.dumps({"erro": f"{type(e).__name__}: {e}"}), encoding="utf-8")
        except OSError:
            pass
        print(f"ERRO {type(e).__name__}: {e}", flush=True)
        sys.exit(1)
