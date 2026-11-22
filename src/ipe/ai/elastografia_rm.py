"""Rigidez hepática na elastografia por RM (0.100.94) — sem rede neural para a medida.

Pedido dele (22/11/2026): *"a gente calcula manualmente a rigidez hepática com ROI nas sequências … algo parecido com o
do JIIM de outubro de 2026, porém sem DL"* (El Oued et al., J Imaging Inform Med 2026, doi 10.1007/s10278-026-02441-w:
região válida = fígado ∩ confiança, depois a amostragem; e o ALEC da Mayo — Dzyubak et al., JMRI 2016,
doi 10.1002/jmri.25072 — que faz o mesmo com processamento de imagem clássico).

O que entra (o aparelho já grava):
* **elastograma** em Pa (ImageType …\\MR_ELASTOGRAPHY\\ELASTOGRAM). Na GE (MR-Touch) vêm dois: "STGRY" (o mapa inteiro)
  e "STGRYM" (o mesmo com a área de **baixa confiança** hachurada — os pixels do xadrez valem 0). A confiança sai da
  comparação dos dois: onde o mascarado tem o xadrez de zeros e o inteiro não.
* **magnitude** da própria aquisição (a série de origem, as imagens ≥ 0): para tirar os vasos grandes (vazio de fluxo).
* **fígado**: a máscara do TotalSegmentator (`total_mr`), a mesma da gordura e do ferro, levada ponto a ponto para a
  grade do elastograma.

A conta (por corte, como a ROI à mão — QIBA/Mayo):
1. fígado erodido no plano (`BORDA_MM`, longe da borda, da cápsula e do desalinhamento entre apneias);
2. ∩ dentro da confiança; 3. − vasos (magnitude < `VASO_FRACAO` × mediana do fígado no corte); 4. ilhas pequenas fora;
5. corte com menos de `MIN_AREA_MM2` de ROI fica de fora;
6. rigidez = **média ponderada pela área** (a média de todos os pixels das ROIs) — é a do laudo; também a mediana,
   p25–p75, a média de cada corte e a heterogeneidade (CV entre cortes e IQR/mediana).

Faixas de referência (2D, 60 Hz; Venkatesh, Yin & Ehman, JMRI 2013;37:544 — tabela de interpretação da Mayo), como
texto ao lado do número: < 2,5 kPa normal; 2,5–2,9 normal ou inflamação; 2,9–3,5 fibrose estágio 1–2; 3,5–4,0
estágio 2–3; 4,0–5,0 estágio 3–4; > 5,0 estágio 4 ou cirrose.
"""
from __future__ import annotations

import logging
import re

import numpy as np

log = logging.getLogger(__name__)

BORDA_MM = 5.0
VASO_FRACAO = 0.5
MIN_AREA_MM2 = 150.0
MIN_ILHA_MM2 = 40.0
CONFIANCA_MINIMA = 0.30          # menos que isso do fígado dentro da confiança: aviso

#: (limite superior kPa, texto) — Venkatesh, Yin & Ehman, JMRI 2013 (2D GRE, 60 Hz)
FAIXAS = ((2.5, "normal"), (2.9, "normal ou inflamação"), (3.5, "fibrose estágio 1–2"),
          (4.0, "fibrose estágio 2–3"), (5.0, "fibrose estágio 3–4"), (float("inf"), "fibrose estágio 4 ou cirrose"))
REF = ("< 2,5 kPa normal; 2,5–2,9 normal ou inflamação; 2,9–3,5 estágio 1–2; 3,5–4,0 estágio 2–3; 4,0–5,0 estágio "
       "3–4; > 5,0 estágio 4 ou cirrose (2D, 60 Hz — Venkatesh, Yin & Ehman, JMRI 2013)")


def faixa(kpa: float | None) -> str:
    if kpa is None:
        return ""
    for lim, txt in FAIXAS:
        if kpa < lim:
            return txt
    return FAIXAS[-1][1]


def classificar(kpa: float | None) -> str:
    """A frase da classificação sugerida (como a da gordura e do ferro)."""
    if kpa is None:
        return ""
    f = faixa(kpa)
    if f == "normal":
        return "Rigidez hepática normal"
    if f == "normal ou inflamação":
        return "Rigidez no limite: normal ou inflamação"
    return f"Rigidez compatível com {f}"


# ------------------------------------------------------------------ achar as séries
def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)) or (hasattr(v, "__iter__") and not isinstance(v, (str, bytes))):
        return "\\".join(str(x) for x in v)
    return str(v)


def eh_elastograma(image_type, descricao: str = "") -> bool:
    it = _texto(image_type).upper()
    if "ELASTOGRAM" in it:
        return True
    if "SCREEN SAVE" in it or "SECONDARY" in it:
        return False
    d = (descricao or "").upper()
    return bool(re.search(r"\bSTGRY|ELASTOGRAM|STIFFNESS|\bMRE\b.*\(K?PA\)", d))


def eh_atenuacao(image_type) -> bool:
    return "ATTENUATION" in _texto(image_type).upper()


def aquisicoes(repo, study_uid: str, cabecalho) -> list[dict]:
    """As aquisições de elastografia do exame: [{"elastogramas": [uid…], "atenuacao": uid, "origem": uid,
    "descricao": str}] — agrupadas pela centena do número da série (GE: 12 → 1250…1257) e, sem isso, juntas."""
    series = [s for s in repo.series_for_study(study_uid) if (s.modality or "").upper() == "MR"]
    grupos: dict[int, dict] = {}
    for s in series:
        ds = cabecalho(repo, s.series_uid)
        it = ds.get("ImageType") if ds is not None else None
        n = int(getattr(s, "series_number", 0) or 0)
        g = n // 100 if n >= 100 else 0
        if eh_elastograma(it, s.description or ""):
            grupos.setdefault(g, {"elastogramas": [], "atenuacao": None, "origem": None})["elastogramas"].append(
                s.series_uid)
        elif eh_atenuacao(it):
            grupos.setdefault(g, {"elastogramas": [], "atenuacao": None, "origem": None})["atenuacao"] = s.series_uid
    for g, d in grupos.items():
        for s in series:
            n = int(getattr(s, "series_number", 0) or 0)
            if g and n == g:
                d["origem"] = s.series_uid
                d["descricao"] = s.description or ""
        if not d.get("origem"):
            for s in series:
                if re.search(r"TOUCH|\bMRE\b|ELASTO", (s.description or "").upper()) and \
                        "ORIGINAL" in _texto((cabecalho(repo, s.series_uid) or {}).get("ImageType")).upper():
                    d["origem"], d["descricao"] = s.series_uid, s.description or ""
                    break
        d.setdefault("descricao", "")
    return [d for _g, d in sorted(grupos.items()) if d["elastogramas"]]


# ------------------------------------------------------------------ confiança
def confianca(mascarado: np.ndarray, inteiro: np.ndarray | None) -> np.ndarray:
    """Pixels dentro da confiança (bool, mesmo formato). O xadrez de zeros do mascarado (onde o inteiro tem valor)
    é a área de baixa confiança: fecha-se o xadrez (3 × 3) para virar área. Sem o inteiro: o próprio mascarado > 0
    com o mesmo fechamento sobre os zeros isolados."""
    from ipe.imaging import morfologia as MO
    m = np.asarray(mascarado)
    if inteiro is not None and np.asarray(inteiro).shape == m.shape:
        xadrez = (m <= 0) & (np.asarray(inteiro) > 0)
        fora = np.asarray(inteiro) <= 0
    else:
        xadrez = m <= 0
        fora = np.zeros(m.shape, bool)
    # fechamento 3 × 3 (2×) e uma dilatação, no plano — só NumPy: o programa não leva o SciPy (0.100.95)
    ruim = MO.erodir(MO.dilatar(xadrez, 2), 2) | MO.dilatar(xadrez, 1)
    return ~(ruim | fora)


# ------------------------------------------------------------------ a medida
def medir(rigidez_pa: np.ndarray, valido: np.ndarray, figado: np.ndarray, pixel_mm: float,
          magnitude: np.ndarray | None = None) -> dict:
    """Mede corte a corte. Entradas (z, y, x): rigidez em Pa, confiança (bool), fígado (bool), magnitude (opcional).
    Devolve {"kpa_media", "kpa_mediana", "kpa_p25", "kpa_p75", "kpa_dp", "area_cm2", "cortes", "por_corte",
    "fracao_confiavel", "cv_cortes", "iqr_rel", "roi" (bool z,y,x)} — vazio sem ROI."""
    from ipe.imaging import morfologia as MO
    from ipe.imaging.estruturas import rotular
    rig = np.asarray(rigidez_pa, float) / 1000.0
    nz = rig.shape[0]
    px2 = pixel_mm * pixel_mm
    r_borda = max(1, int(round(BORDA_MM / pixel_mm)))
    roi = np.zeros(rig.shape, bool)
    por_corte = []
    area_fig = area_conf = 0.0
    for k in range(nz):
        f = np.asarray(figado[k], bool)
        if f.sum() * px2 < MIN_AREA_MM2:
            continue
        fe = MO.erodir(f, r_borda, quadrado=False)
        area_fig += fe.sum() * px2
        r = fe & np.asarray(valido[k], bool) & (rig[k] > 0)
        area_conf += r.sum() * px2
        if magnitude is not None and r.any():
            mg = np.asarray(magnitude[k], float)
            ref = float(np.median(mg[fe])) if fe.any() else 0.0
            if ref > 0:
                r &= mg >= VASO_FRACAO * ref
        lab, n = rotular(r)
        if n:
            tam = np.bincount(lab.ravel(), minlength=n + 1)[1:] * px2
            for i, t in enumerate(tam, 1):
                if t < MIN_ILHA_MM2:
                    r[lab == i] = False
        a = r.sum() * px2
        if a < MIN_AREA_MM2:
            continue
        v = rig[k][r]
        roi[k] = r
        por_corte.append({"corte": k, "area_mm2": round(a, 0), "kpa_media": round(float(v.mean()), 2),
                          "kpa_mediana": round(float(np.median(v)), 2)})
    if not por_corte:
        return {"fracao_confiavel": round(area_conf / area_fig, 2) if area_fig else 0.0, "roi": roi, "cortes": 0}
    v = rig[roi]
    medias = np.array([c["kpa_media"] for c in por_corte])
    med = float(np.median(v))
    out = {
        "kpa_media": round(float(v.mean()), 2),                    # = média ponderada pela área
        "kpa_mediana": round(med, 2),
        "kpa_p25": round(float(np.percentile(v, 25)), 2),
        "kpa_p75": round(float(np.percentile(v, 75)), 2),
        "kpa_dp": round(float(v.std()), 2),
        "area_cm2": round(roi.sum() * px2 / 100.0, 1),
        "cortes": len(por_corte),
        "por_corte": por_corte,
        "fracao_confiavel": round(area_conf / area_fig, 2) if area_fig else 0.0,
        "cv_cortes": round(float(medias.std() / medias.mean()), 2) if len(medias) > 1 and medias.mean() > 0 else 0.0,
        "iqr_rel": round((float(np.percentile(v, 75)) - float(np.percentile(v, 25))) / med, 2) if med > 0 else 0.0,
        "roi": roi,
    }
    out["heterogeneo"] = bool(out["cv_cortes"] > 0.15 or out["iqr_rel"] > 0.5)
    return out


# ------------------------------------------------------------------ a imagem de conferência
def _cores_rigidez(kpa: np.ndarray, topo: float = 8.0) -> np.ndarray:
    """Mapa de cores parecido com o do aparelho (roxo → azul → verde → amarelo → vermelho), 0–`topo` kPa."""
    t = np.clip(kpa / topo, 0, 1)
    pontos = np.array([0.0, 0.2, 0.45, 0.65, 0.85, 1.0])
    cores = np.array([[40, 0, 90], [0, 40, 255], [0, 220, 120], [255, 240, 0], [255, 110, 0], [230, 0, 0]], float)
    out = np.stack([np.interp(t, pontos, cores[:, c]) for c in range(3)], -1)
    return out.astype(np.uint8)


def imagem_de_conferencia(rigidez_pa: np.ndarray, valido: np.ndarray, figado: np.ndarray, roi: np.ndarray,
                          resultado: dict, titulo: str = "") -> np.ndarray:
    """Mosaico RGB dos cortes com ROI: o elastograma em cor (0–8 kPa), a baixa confiança em cinza, o fígado com
    contorno fino e a ROI com contorno branco de borda preta (vê-se também em monitor P&B), e o valor de cada corte."""
    from PIL import Image, ImageDraw

    from ipe.ai.mama_sr import _fonte
    from ipe.core.i18n import tr
    from ipe.imaging import morfologia as MO
    f_tit, f_txt = _fonte(15), _fonte(12)
    kpa = np.asarray(rigidez_pa, float) / 1000.0
    cortes = [c["corte"] for c in resultado.get("por_corte", [])] or list(range(kpa.shape[0]))
    valores = {c["corte"]: c for c in resultado.get("por_corte", [])}
    h, w = kpa.shape[1:]
    esc = max(1, 384 // max(h, w))
    lado = int(np.ceil(np.sqrt(len(cortes))))
    linhas = int(np.ceil(len(cortes) / lado))
    cab = 46
    mosaico = Image.new("RGB", (lado * w * esc, linhas * h * esc + cab), (0, 0, 0))
    d = ImageDraw.Draw(mosaico)
    txt = titulo or tr("Rigidez hepática — ROI automática")
    if resultado.get("kpa_media") is not None:
        txt += "   " + tr("média {} kPa · mediana {} · {} cortes · {} cm²").format(
            f"{resultado['kpa_media']:.2f}".replace(".", ","), f"{resultado['kpa_mediana']:.2f}".replace(".", ","),
            resultado["cortes"], f"{resultado['area_cm2']:.0f}")
    d.text((8, 5), txt, fill=(255, 255, 255), font=f_tit)
    d.text((8, 26), tr("ROI: contorno branco · fígado: amarelo · cinza = fora da confiança · cor 0–8 kPa"),
           fill=(190, 190, 190), font=f_txt)
    for n, k in enumerate(cortes):
        rgb = _cores_rigidez(kpa[k]).astype(float)
        fora = ~np.asarray(valido[k], bool) & (kpa[k] > 0)
        cinza = kpa[k][..., None] / 8.0 * 120
        rgb[fora] = np.clip(cinza[fora].repeat(3, -1), 30, 120)
        rgb[kpa[k] <= 0] = 0
        f = np.asarray(figado[k], bool)
        rgb[f ^ MO.erodir(f, 1, quadrado=False)] = (255, 220, 0)
        r = np.asarray(roi[k], bool)
        borda = r ^ MO.erodir(r, 1, quadrado=False)
        halo = MO.dilatar(borda, 1, quadrado=False) & ~borda
        rgb[halo] = 0
        rgb[borda] = 255
        im = Image.fromarray(rgb.astype(np.uint8)).resize((w * esc, h * esc), Image.NEAREST)
        x0, y0 = (n % lado) * w * esc, (n // lado) * h * esc + cab
        mosaico.paste(im, (x0, y0))
        c = valores.get(k)
        if c:
            rot = tr("corte {}: {} kPa ({} cm²)").format(k + 1, f"{c['kpa_media']:.2f}".replace(".", ","),
                                                         f"{c['area_mm2'] / 100:.1f}".replace(".", ","))
            larg = int(d.textlength(rot, font=f_txt)) if hasattr(d, "textlength") else 7 * len(rot)
            d.rectangle((x0 + 4, y0 + 4, x0 + 10 + larg, y0 + 21), fill=(0, 0, 0))
            d.text((x0 + 7, y0 + 6), rot, fill=(255, 255, 255), font=f_txt)
    return np.asarray(mosaico)
