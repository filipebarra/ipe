"""0.100.55: as escalas publicadas das calcificações arteriais da mama, estimadas a partir do que a SCU-Net marcou.

- **Margolies** (JACC Cardiovasc Imaging 2016; adaptada do escore de 12 pontos do cálcio coronário de Shemesh,
  Radiology 2010), por mama: vasos (1 ponto por vaso, até 6) + extensão no vaso mais acometido (0; 1 < 1/3;
  2 = 1/3–2/3; 3 > 2/3) + densidade da pior área (0; 1 leve — luz visível ou uma parede; 2 moderada — as duas paredes;
  3 acentuada — sem luz visível). 0–12; vale a pior mama; 0 negativa, 1–3 leve, 4–12 moderada a acentuada.
- **CSBI** (Canadian Society of Breast Imaging, 2023): 0 nenhuma; 1 leve — algumas puntiformes, sem trilho;
  2 moderada — grosseiras ou em trilho em menos de 3 vasos; 3 acentuada — 3 ou mais vasos.
- **Loberant** (J Clin Imaging Sci 2013): 0 nenhuma; 1 poucas puntiformes ou lineares curtas; 2 mais abundantes;
  3 contínuas, circunferenciais.
- **BAC-SS** (Trimboli et al., Quant Imaging Med Surg 2021), na MLO de cada mama: Nv (vasos) + Ov (1 se o cálcio cobre
  a artéria de lado a lado por ≥ 1 mm) + L (classe do comprimento somado: 0 sem; 1–4 pelos quartis da amostra dos
  autores — o artigo dá mediana 33 mm e intervalo interquartil 12–84 mm, usados aqui como cortes).

Tudo é **estimativa**: "vaso" é o conjunto de trechos ligados a até 2,5 mm uns dos outros; "trilho" são dois trechos
alongados paralelos a 0,5–3,5 mm; "sem luz" é um trecho com 1 mm ou mais de espessura por pelo menos 1 mm; a
extensão do vaso é o comprimento dele sobre a profundidade da mama na imagem. O médico confere nas imagens.
"""
from __future__ import annotations

import logging
import math

import numpy as np

log = logging.getLogger(__name__)

JUNTAR_MM = 2.5           # trechos a até esta distância são do mesmo vaso
ALONGADO_MM = 3.0         # como em calc_vascular.COMPRIMENTO_MIN
TRILHO_MM = (0.5, 3.5)    # distância entre as duas paredes
OPACO_MM = 1.0            # espessura de "sem luz" (cobre o vaso de lado a lado)
QUARTIS_BACSS = (12.0, 33.0, 84.0)
CATEGORIAS = {"negativa": "Negativa", "leve": "Leve", "moderada_acentuada": "Moderada a acentuada"}
NOMES_CSBI = {0: "Nenhuma", 1: "Leve", 2: "Moderada", 3: "Acentuada"}


def _eixo(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Centro, direção principal (unitária), comprimento e largura (em pixels) de um conjunto de pontos (y, x)."""
    c = pts.mean(axis=0)
    d = pts - c
    if len(pts) < 2:
        return c, np.array([1.0, 0.0]), 1.0, 1.0
    cov = d.T @ d / len(pts)
    _w, v = np.linalg.eigh(cov)
    u = v[:, 1]
    p = d @ u
    q = d @ v[:, 0]
    return c, u, float(p.max() - p.min() + 1), float(q.max() - q.min() + 1)


def _profundidade(img8: np.ndarray | None, passo: float) -> float:
    """Profundidade da mama na imagem (mm): a maior faixa horizontal de tecido (mamilo ↔ parede)."""
    if img8 is None:
        return 0.0
    t = img8 > 12
    if not t.any():
        return 0.0
    return float(t.sum(axis=1).max()) * passo


def caracteristicas(m: np.ndarray, img8: np.ndarray | None, passo: float) -> dict:
    """O que as escalas precisam de uma imagem: os vasos (comprimento, extensão, trilho, sem luz) e as puntiformes."""
    try:
        import cv2
    except ImportError:
        return {}
    m8 = m.astype(np.uint8)
    out = {"vasos": [], "puntiformes": 0, "profundidade_mm": round(_profundidade(img8, passo), 1)}
    if not m8.any():
        return out
    n, lab, st, _c = cv2.connectedComponentsWithStats(m8, connectivity=8)
    r = max(1, round(JUNTAR_MM / 2 / passo))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    _ng, grupo = cv2.connectedComponents(cv2.dilate(m8, ker), connectivity=8)
    pecas: dict[int, list] = {}
    for i in range(1, n):
        x0, y0, w, h = (int(st[i, k]) for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH,
                                                  cv2.CC_STAT_HEIGHT))
        sub = (lab[y0:y0 + h, x0:x0 + w] == i)
        ys, xs = np.nonzero(sub)
        if len(ys) < 2:
            continue
        pts = np.stack([ys + y0, xs + x0], axis=1).astype(float)
        c, u, comp, _larg = _eixo(pts)
        dt = cv2.distanceTransform(np.pad(sub.astype(np.uint8), 1), cv2.DIST_L2, 3)
        grosso = dt >= (OPACO_MM / 2) / passo
        opaco = False
        if grosso.any():
            gy, gx = np.nonzero(grosso)
            _c2, _u2, cg, _l2 = _eixo(np.stack([gy, gx], axis=1).astype(float))
            opaco = cg * passo >= OPACO_MM / 2  # o miolo grosso se estende: ≥ 1 mm de espessura por ≥ ~1 mm
        g = int(grupo[int(ys[0]) + y0, int(xs[0]) + x0])
        pecas.setdefault(g, []).append({"c": c, "u": u, "comp": comp * passo, "pts": pts, "opaco": bool(opaco)})
    for g, lista in pecas.items():
        total = sum(p["comp"] for p in lista)
        longos = [p for p in lista if p["comp"] >= ALONGADO_MM]
        if not longos and total < ALONGADO_MM:
            out["puntiformes"] += len(lista)
            continue
        todos = np.concatenate([p["pts"] for p in lista])
        _c, _u, ext, _l = _eixo(todos)
        trilho = False
        cos20 = math.cos(math.radians(20))
        for a_i, a in enumerate(longos[:30]):
            for b in longos[a_i + 1:30]:
                if abs(float(a["u"] @ b["u"])) < cos20:
                    continue
                d = b["c"] - a["c"]
                perp = abs(float(a["u"][0] * d[1] - a["u"][1] * d[0])) * passo
                ao_longo = abs(float(a["u"] @ d)) * passo
                if TRILHO_MM[0] <= perp <= TRILHO_MM[1] and ao_longo <= (a["comp"] + b["comp"]) / 2:
                    trilho = True
                    break
            if trilho:
                break
        # no trilho as duas paredes contam uma vez
        out["vasos"].append({"comprimento_mm": round(total / 2 if trilho else total, 1),
                             "extensao_mm": round(ext * passo, 1),
                             "trechos": len(lista), "trilho": trilho, "opaco": any(p["opaco"] for p in lista)})
    out["vasos"].sort(key=lambda v: -v["comprimento_mm"])
    out["vasos"] = out["vasos"][:30]
    return out


def _densidade(v: dict) -> int:
    return 3 if v.get("opaco") else 2 if v.get("trilho") else 1


def _classe_extensao(frac: float) -> int:
    if frac <= 0:
        return 0
    return 1 if frac < 1 / 3 else 2 if frac <= 2 / 3 else 3


def _classe_l(mm: float, cortes=QUARTIS_BACSS) -> int:
    if mm <= 0:
        return 0
    return 1 + sum(mm > c for c in cortes)


def _da_imagem(v: dict) -> dict | None:
    e = v.get("tracado")
    if not isinstance(e, dict) or "vasos" not in e:
        return None
    vasos = e["vasos"]
    prof = float(e.get("profundidade_mm") or 0)
    maior = max((x["extensao_mm"] for x in vasos), default=0.0)
    frac = (maior / prof) if prof > 0 else (1.0 if maior else 0.0)
    return {"vasos": len(vasos), "extensao": _classe_extensao(min(frac, 1.0)),
            "densidade": max((_densidade(x) for x in vasos), default=0),
            "comprimento_mm": round(sum(x["comprimento_mm"] for x in vasos), 1),
            "opaco": any(x.get("opaco") for x in vasos), "trilho": any(x.get("trilho") for x in vasos),
            "puntiformes": int(e.get("puntiformes") or 0)}


def calcular(imagens: list[dict]) -> dict | None:
    """As quatro escalas do exame a partir das imagens medidas (`medida["imagens"]`); None se nenhuma tem os dados
    (medida de antes da 0.100.55: medir de novo)."""
    por_lado: dict[str, list] = {}
    mlo: dict[str, list] = {}
    for v in imagens:
        if v.get("extra"):
            continue
        d = _da_imagem(v)
        if d is None:
            continue
        lado = v.get("lado") or (v.get("chave") or "?")[0]
        por_lado.setdefault(lado, []).append(d)
        if "MLO" in (v.get("incidencia") or v.get("chave") or ""):
            mlo.setdefault(lado, []).append(d)
    if not por_lado:
        return None
    marg, bac = {}, {}
    tot_vasos, tot_punt = 0, 0
    pior_continua = False
    for lado, ds in por_lado.items():
        nv = max(d["vasos"] for d in ds)
        ext = max(d["extensao"] for d in ds)
        den = max(d["densidade"] for d in ds)
        punt = max(d["puntiformes"] for d in ds)
        tot_vasos += nv
        tot_punt += punt
        marg[lado] = {"vasos": min(nv, 6), "extensao": ext, "densidade": den, "total": min(nv, 6) + ext + den}
        pior_continua |= den >= 2 and ext >= 2
        base = mlo.get(lado) or ds
        b_nv = max(d["vasos"] for d in base)
        b_ov = int(any(d["opaco"] for d in base))
        b_mm = max(d["comprimento_mm"] for d in base)
        b_l = _classe_l(b_mm)
        bac[lado] = {"nv": b_nv, "ov": b_ov, "l": b_l, "comprimento_mm": b_mm, "total": b_nv + b_ov + b_l,
                     "so_mlo": bool(mlo.get(lado))}
    m_total = max(x["total"] for x in marg.values())
    cat = "negativa" if m_total == 0 else "leve" if m_total <= 3 else "moderada_acentuada"
    nada = tot_vasos == 0 and tot_punt < 3
    csbi = 0 if nada else 3 if tot_vasos >= 3 else 2 if tot_vasos >= 1 else 1
    lob = 0 if nada else 3 if pior_continua else 2 if (tot_vasos >= 2 or tot_punt >= 10) else 1
    return {"estimada": True,
            "margolies": {"total": m_total, "categoria": cat, "por_mama": marg},
            "csbi": {"grau": csbi, "vasos": tot_vasos},
            "loberant": {"grau": lob},
            "bacss": {"maior": max(x["total"] for x in bac.values()), "por_mama": bac, "cortes_l": list(QUARTIS_BACSS)}}


DICAS = {
    "margolies": "Por mama: vasos (até 6) + extensão no vaso mais acometido (0–3) + densidade da pior área (0–3); "
                 "vale a pior mama. 0 negativa, 1–3 leve, 4–12 moderada a acentuada. Margolies et al., JACC "
                 "Cardiovasc Imaging 2016.",
    "csbi": "0 nenhuma; 1 algumas puntiformes, sem trilho; 2 grosseiras ou em trilho em menos de 3 vasos; "
            "3 três ou mais vasos. Canadian Society of Breast Imaging, 2023.",
    "loberant": "0 nenhuma; 1 poucas puntiformes ou lineares curtas; 2 mais abundantes; 3 contínuas, "
                "circunferenciais. Loberant et al., J Clin Imaging Sci 2013.",
    "bacss": "Na MLO de cada mama: Nv (vasos) + Ov (1 se o cálcio cobre a artéria de lado a lado por 1 mm ou mais) + "
             "L (comprimento somado: 1 até 12 mm, 2 até 33, 3 até 84, 4 acima). Trimboli et al., Quant Imaging Med "
             "Surg 2021.",
}


def resumo(e: dict | None, tr=lambda s: s) -> list[tuple[str, str, str]]:
    """(escala, valor, dica) para a tela; `tr` traduz as partes fixas."""
    if not e:
        return []
    lado = {"R": tr("D"), "L": tr("E")}
    mg, bc = e["margolies"], e["bacss"]
    pm = ", ".join(f"{lado.get(k, k)} {x['total']} ({x['vasos']}+{x['extensao']}+{x['densidade']})"
                   for k, x in sorted(mg["por_mama"].items(), reverse=True))
    pb = ", ".join(f"{lado.get(k, k)} {x['total']} ({x['nv']}+{x['ov']}+{x['l']})"
                   for k, x in sorted(bc["por_mama"].items(), reverse=True))
    return [
        ("Margolies (0–12)", f"{mg['total']} — {tr(CATEGORIAS[mg['categoria']])} · {pm}", tr(DICAS["margolies"])),
        ("CSBI (0–3)", f"{e['csbi']['grau']} — {tr(NOMES_CSBI[e['csbi']['grau']])}", tr(DICAS["csbi"])),
        ("Loberant (0–3)", f"{e['loberant']['grau']}", tr(DICAS["loberant"])),
        ("BAC-SS", f"{bc['maior']} · {pb}", tr(DICAS["bacss"])),
    ]
