"""Densidade óssea oportunista na TC de abdome sem contraste: HU do osso trabecular em L1 e em L1–L4 (0.100.129).

Roda junto com a composição corporal (mesma série, mesmo TotalSegmentator `total`, vértebras L1 a L4).

**O que mede.** Em cada vértebra lombar que a IA achou, uma ROI de osso trabecular dentro do corpo vertebral:
1. a máscara da vértebra é erodida no plano axial (5 mm por padrão), o que tira a cortical e, por serem finos,
   os pedículos e os elementos posteriores (o plexo venoso posterior sai junto com a borda);
2. fica a maior ilha 3D (o corpo) e só o **terço central** dela no eixo craniocaudal (os platôs e os discos
   não entram);
3. voxels fora de −50 a 700 HU saem (ar, gás, cimento).
Saem a média, a mediana, o desvio padrão e o volume da ROI de cada nível, e o HU médio de **L1** e de **L1–L4**
(média dos níveis medidos, ponderada pelo volume).

**Classificação provisória (só L1).** Pickhardt et al., Ann Intern Med 2013;158:588 (2.063 pares TC–DXA, TC de
abdome, L1, osteoporose pela DXA): ≤ 160 HU sensibilidade 90% / especificidade 52%; ≤ 135 HU 75% / 75%;
≤ 110 HU 52% / 91%. Aqui: > 160 sem sinais de baixa densidade; 135 a 160 zona cinzenta; ≤ 135 baixa densidade;
≤ 110 compatível com osteoporose. Os três cortes são **editáveis** em Configurações ▸ CAD/IA. A média de
L1–L4 não tem corte validado na literatura (cada serviço e cada scanner têm o seu): o corte é opcional
(0 = só mostra o número), para ser achado comparando com a DMO (coluna e fêmur) do próprio serviço.

Sempre texto de referência, nunca diagnóstico: a densitometria (DXA) continua sendo o padrão para o diagnóstico.
Série com contraste ou kVp diferente de 120: mede, mas não classifica.
"""
from __future__ import annotations

import numpy as np

from ipe.ai import achados as AC

NIVEIS = ("L1", "L2", "L3", "L4")
CLASSES = tuple(f"vertebrae_{n}" for n in NIVEIS)
TIPO_OSSO = "Densidade óssea (TC)"
EROSAO_MM = 5.0
FRACAO_CENTRAL = 1.0 / 3.0
FAIXA_HU = (-50.0, 700.0)
MIN_VOXELS = 200
CORES = {"L1": (255, 150, 60), "L2": (255, 190, 90), "L3": (230, 120, 40), "L4": (255, 220, 120)}

CHAVE_LIMITE_OSTEOPOROSE = "composicao.osso_osteoporose_hu"
CHAVE_LIMITE_BAIXA = "composicao.osso_baixa_hu"
CHAVE_LIMITE_NORMAL = "composicao.osso_normal_hu"
CHAVE_LIMITE_L1L4 = "composicao.osso_l1l4_hu"
CHAVE_EROSAO = "composicao.osso_erosao_mm"
PADROES = {CHAVE_LIMITE_OSTEOPOROSE: 110.0, CHAVE_LIMITE_BAIXA: 135.0, CHAVE_LIMITE_NORMAL: 160.0,
           CHAVE_LIMITE_L1L4: 0.0, CHAVE_EROSAO: EROSAO_MM}

OSSO_NORMAL = "Sem sinais de baixa densidade óssea (L1 acima de {normal:.0f} HU)"
OSSO_CINZA = "Zona cinzenta: L1 entre {baixa:.0f} e {normal:.0f} HU (pode ser normal ou baixa densidade)"
OSSO_BAIXA = "Compatível com baixa densidade óssea: L1 entre {osteo:.0f} e {baixa:.0f} HU"
OSSO_OSTEO = "Compatível com osteoporose: L1 até {osteo:.0f} HU"
OSSO_NAO_CLASSIFICADO = "Não classificado: {motivo}"
REFERENCIA = ("referência (Pickhardt et al., Ann Intern Med 2013): na TC de abdome, L1 ≤ 160 HU tem sensibilidade "
              "90% e especificidade 52% para osteoporose pela DXA; ≤ 135 HU, 75% e 75%; ≤ 110 HU, 52% e 91%. O HU "
              "varia entre scanners e protocolos; a densitometria continua sendo o padrão — texto de referência, "
              "não diagnóstico")


def _config(settings, chave, padrao):
    if settings is None:
        return padrao
    try:
        v = settings.get(chave, padrao)
    except Exception:  # noqa: BLE001
        return padrao
    try:
        return float(padrao if v is None else v)
    except (TypeError, ValueError):
        return padrao


def limites(settings=None) -> dict:
    return {"osteo": _config(settings, CHAVE_LIMITE_OSTEOPOROSE, PADROES[CHAVE_LIMITE_OSTEOPOROSE]),
            "baixa": _config(settings, CHAVE_LIMITE_BAIXA, PADROES[CHAVE_LIMITE_BAIXA]),
            "normal": _config(settings, CHAVE_LIMITE_NORMAL, PADROES[CHAVE_LIMITE_NORMAL]),
            "l1l4": _config(settings, CHAVE_LIMITE_L1L4, PADROES[CHAVE_LIMITE_L1L4])}


def classificar(l1_hu, lim: dict, motivo_nao: str = "") -> str | None:
    """O resultado provisório de L1 pelos cortes (texto), ou None sem L1."""
    if l1_hu is None:
        return None
    if motivo_nao:
        return OSSO_NAO_CLASSIFICADO.format(motivo=motivo_nao)
    if l1_hu <= lim["osteo"]:
        return OSSO_OSTEO.format(**lim)
    if l1_hu <= lim["baixa"]:
        return OSSO_BAIXA.format(**lim)
    if l1_hu <= lim["normal"]:
        return OSSO_CINZA.format(**lim)
    return OSSO_NORMAL.format(**lim)


def _kvp(t) -> float | None:
    try:
        import pydicom
        ds = pydicom.dcmread(t.frames[0].path, stop_before_pixels=True, force=True, specific_tags=["KVP"])
        return float(ds.get("KVP")) if ds.get("KVP") not in (None, "") else None
    except Exception:  # noqa: BLE001
        return None


def roi_trabecular(vert: np.ndarray, hu: np.ndarray, dx: float, dy: float, erosao_mm: float = EROSAO_MM):
    """ROI trabecular (máscara 3D, mesma grade) do corpo da vértebra `vert`, ou None se não sobrar o suficiente."""
    from ipe.ai.composicao import _ero2
    from ipe.imaging import estruturas as E
    ks = np.nonzero(vert.any(axis=(1, 2)))[0]
    if not len(ks):
        return None
    px = max(1, int(round(erosao_mm / max(min(dx, dy), 1e-3))))
    nucleo = np.zeros(vert.shape, bool)
    for k in range(int(ks[0]), int(ks[-1]) + 1):
        if vert[k].any():
            nucleo[k] = _ero2(vert[k], px)
    nucleo &= (hu >= FAIXA_HU[0]) & (hu <= FAIXA_HU[1])
    if not nucleo.any():
        return None
    rot, n = E.rotular(nucleo)
    if n == 0:
        return None
    cont = np.bincount(rot.ravel())
    cont[0] = 0
    corpo = rot == int(np.argmax(cont))
    kz = np.nonzero(corpo.any(axis=(1, 2)))[0]
    n_cortes = len(kz)
    if n_cortes == 0:
        return None
    manter = max(1, int(round(n_cortes * FRACAO_CENTRAL)))
    ini = int(kz[0]) + (n_cortes - manter) // 2
    roi = np.zeros(vert.shape, bool)
    roi[ini:ini + manter] = corpo[ini:ini + manter]
    return roi if roi.sum() >= 1 else None


def medir(t, ms, settings=None, contraste: bool = False) -> dict:
    """{numeros, avisos, mascaras, centro, resultado, niveis}. `numeros` vazio se L1 e os outros não existem."""
    from ipe.ai import cefalometria as CF
    vol = t.vol
    dados = vol.data
    lim = limites(settings)
    erosao = _config(settings, CHAVE_EROSAO, EROSAO_MM)
    out = {"numeros": {}, "avisos": [], "mascaras": {}, "centro": None, "niveis": {}}
    normal = np.asarray(vol.slice_vec, float)
    if abs(normal[2]) / max(float(np.linalg.norm(normal)), 1e-9) <= 0.95:
        out["avisos"].append("a série não é axial: a ROI do osso se mede em cortes axiais")
        return out
    vox_cm3 = float(vol.dx * vol.dy * abs(vol.dz)) / 1000.0
    pesos, medias = [], []
    for nivel, classe in zip(NIVEIS, CLASSES):
        m = ms.get(classe)
        if m is None:
            out["avisos"].append(f"a IA não achou a vértebra {nivel} nesta série")
            continue
        roi = roi_trabecular(m, np.asarray(dados, float), float(vol.dx), float(vol.dy), erosao)
        if roi is None or int(roi.sum()) < MIN_VOXELS:
            out["avisos"].append(f"{nivel}: sobrou pouco osso trabecular na ROI (vértebra cortada, fina ou muito "
                                 "esclerótica)")
            continue
        v = np.asarray(dados[roi], float)
        out["niveis"][nivel] = {"media": float(v.mean()), "n": int(roi.sum())}
        out["mascaras"][nivel] = roi
        pesos.append(float(roi.sum()))
        medias.append(float(v.mean()))
        sufixo = nivel.lower()
        out["numeros"][f"{sufixo}_hu"] = AC.numero(round(float(v.mean()), 1), "HU", f"{nivel} trabecular (média)")
        out["numeros"][f"{sufixo}_mediana"] = AC.numero(round(float(np.median(v)), 1), "HU",
                                                       f"{nivel} trabecular (mediana)")
        out["numeros"][f"{sufixo}_dp"] = AC.numero(round(float(v.std()), 1), "HU", f"{nivel} desvio padrão")
        out["numeros"][f"{sufixo}_cm3"] = AC.numero(round(float(roi.sum()) * vox_cm3, 1), "cm³", f"{nivel} volume da ROI")
        if float(np.median(v)) > 300:
            out["avisos"].append(f"{nivel}: osso muito denso (mediana > 300 HU): esclerose, lesão blástica ou "
                                 "cimento? confira a ROI")
    if not medias:
        return out
    if "L1" in out["niveis"]:
        k_l1 = np.nonzero(out["mascaras"]["L1"].any(axis=(1, 2)))[0]
        out["centro"] = [float(x) for x in CF.pontos(vol, out["mascaras"]["L1"][k_l1[0]:k_l1[-1] + 1],
                                                    (int(k_l1[0]), 0, 0)).mean(axis=0)]
    l1l4 = float(np.average(medias, weights=pesos))
    out["numeros"]["l1l4_hu"] = AC.numero(round(l1l4, 1), "HU", f"L1–L4 trabecular (média de {len(medias)} níveis)")
    out["numeros"]["niveis_n"] = AC.numero(len(medias), "", "Níveis medidos")
    motivo = ""
    kvp = _kvp(t)
    if contraste:
        motivo = "série com contraste (os cortes valem na TC sem contraste)"
        out["avisos"].append("série com contraste: o HU do osso sobe e os cortes de L1 não valem")
    elif kvp is not None and abs(kvp - 120.0) > 1.0:
        motivo = f"{kvp:.0f} kVp (os cortes valem a 120 kVp)"
        out["avisos"].append(f"{kvp:.0f} kVp: o HU do osso muda com a tensão; os cortes valem a 120 kVp")
    l1 = (out["numeros"].get("l1_hu") or {}).get("v")
    resultado = classificar(l1, lim, motivo)
    if resultado is None and "l1l4_hu" in out["numeros"]:
        out["avisos"].append("sem L1: não há classificação (os cortes publicados são de L1); só o HU de L1–L4")
    if resultado:
        out["numeros"]["resultado"] = AC.numero(resultado, "", "Resultado (L1)")
    if lim["l1l4"] > 0 and not motivo:
        out["numeros"]["resultado_l1l4"] = AC.numero(
            ("L1–L4 abaixo do corte do serviço" if l1l4 < lim["l1l4"] else "L1–L4 igual ou acima do corte do serviço")
            + f" ({lim['l1l4']:.0f} HU)", "", "Resultado (L1–L4)")
    out["avisos"].append(REFERENCIA)
    return out


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=0):
        x = (n.get(k) or {}).get("v")
        return None if x is None else f"{float(x):.{casas}f}".replace(".", ",")
    partes = []
    if v("l1_hu"):
        partes.append(f"atenuação do osso trabecular de L1 de {v('l1_hu')} HU")
    if v("l1l4_hu"):
        k = int(float((n.get("niveis_n") or {}).get("v") or 0))
        partes.append(f"média de {v('l1l4_hu')} HU em L1–L4" if k > 1 else f"{v('l1l4_hu')} HU")
    txt = "Densidade óssea na TC: " + ("; ".join(partes) if partes else "não medida") + "."
    res = resultado_do_achado(a)
    if res:
        txt += f" {res}."
    return txt


def resultado_do_achado(a: dict) -> str | None:
    if "resultado" in (a.get("corrigidos") or {}):
        return str(a["corrigidos"]["resultado"] or "").strip() or None
    r = ((a.get("numeros") or {}).get("resultado") or {}).get("v")
    return str(r).strip() if r else None
