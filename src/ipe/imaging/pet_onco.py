"""PET no seguimento oncológico (0.99.60, item 7 do backlog, parte 2), sem Qt.

- **SUL** (SUV pela massa magra, Janmahasatian et al., Clin Pharmacokinet 2005): o PERCIST 1.0 mede em SUL.
  LBM (kg) = 9270 × peso / (6680 + 216 × IMC) nos homens e 9270 × peso / (8780 + 244 × IMC) nas mulheres.
  SUL = SUV × LBM / peso. Precisa da altura (PatientSize) e do sexo (PatientSex) no arquivo.
- **Referências**: fígado — esfera de 3 cm no lobo direito, longe das bordas e dos vasos (o PERCIST pede o
  SULmédio e o desvio-padrão); aqui a esfera procura, perto do ponto, o lugar com o menor desvio-padrão (e,
  com a máscara do fígado, só onde a esfera cabe inteira dentro dele). Mediastino (pool sanguíneo) — esfera de
  1 cm na aorta descendente.
- **Limiar de mensurabilidade do PERCIST**: 1,5 × SULmédio do fígado + 2 × DP (Wahl et al., J Nucl Med 2009).
- **Deauville** (escala de 5 pontos, Lugano 2014): 1 sem captação; 2 ≤ mediastino; 3 > mediastino e ≤ fígado;
  4 > fígado; 5 bem acima do fígado (aqui, SUVmáx > 2 × o SUVmáx do fígado, ajustável) ou lesão nova; X captação
  nova provavelmente não linfoma. Proposta pelos números, com troca à mão.
- **Q.Check**: os dados do cabeçalho que mudam o SUV, em cada exame e entre dois exames (tempo de captação
  de 50–70 min e diferença de até 15 min, peso, dose, meia-vida, unidade, correções, matriz, espessura,
  reconstrução, aparelho e software).
"""
from __future__ import annotations

import math

import numpy as np

from ipe.imaging.suv import _dt, suv_factor

DIAM_FIGADO_MM = 30.0
DIAM_MEDIASTINO_MM = 10.0
BUSCA_MM = 20.0
CAPTACAO_MIN = (50.0, 70.0)
DIF_CAPTACAO_MAX_MIN = 15.0
FATOR_DEAUVILLE_5 = 2.0
MEIA_VIDA_F18 = 6586.2
DEAUVILLE = {"1": "1 — sem captação", "2": "2 — ≤ mediastino", "3": "3 — > mediastino, ≤ fígado",
             "4": "4 — > fígado", "5": "5 — bem acima do fígado ou lesão nova",
             "X": "X — captação nova, provavelmente não linfoma"}
NIVEIS = {"ok": "✓", "info": "·", "aviso": "⚠", "erro": "✗"}


# ------------------------------------------------------------------ SUL
def massa_magra_kg(peso_kg: float, altura_m: float, sexo: str) -> float | None:
    """Massa magra de Janmahasatian (2005); None sem peso, altura ou sexo (M/F)."""
    sexo = (sexo or "").upper()[:1]
    if not peso_kg or not altura_m or peso_kg <= 0 or altura_m <= 0 or sexo not in ("M", "F"):
        return None
    if altura_m > 3:                      # veio em cm
        altura_m /= 100.0
    imc = peso_kg / (altura_m * altura_m)
    if sexo == "M":
        return 9270.0 * peso_kg / (6680.0 + 216.0 * imc)
    return 9270.0 * peso_kg / (8780.0 + 244.0 * imc)


def razao_sul(ds) -> tuple[float | None, str]:
    """(LBM / peso, motivo): SUL = SUVbw × razão."""
    try:
        peso = float(ds.get("PatientWeight") or 0)
        altura = float(ds.get("PatientSize") or 0)
    except (TypeError, ValueError):
        return None, "peso ou altura inválidos"
    if peso <= 0:
        return None, "sem o peso do paciente"
    if altura <= 0:
        return None, "sem a altura do paciente (PatientSize)"
    sexo = str(ds.get("PatientSex", "") or "")
    lbm = massa_magra_kg(peso, altura, sexo)
    if lbm is None:
        return None, "sem o sexo do paciente (PatientSex)"
    return lbm / peso, "SUL (Janmahasatian)"


def fatores(ds) -> dict:
    """{suv, sul_razao, motivo_suv, motivo_sul} de um arquivo de PET."""
    f, m = suv_factor(ds)
    r, ms = razao_sul(ds) if f is not None else (None, m)
    return {"suv": f, "sul_razao": r, "motivo_suv": m, "motivo_sul": ms}


def fatores_do_arquivo(path: str) -> dict:
    try:
        import pydicom
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
    except Exception as e:  # noqa: BLE001
        return {"suv": None, "sul_razao": None, "motivo_suv": str(e), "motivo_sul": str(e)}
    return fatores(ds)


# ------------------------------------------------------------------ referências
def _esfera(dz: float, dy: float, dx: float, diam_mm: float) -> np.ndarray:
    r = diam_mm / 2.0
    rk, rj, ri = (max(0, int(math.floor(r / max(d, 1e-6)))) for d in (dz, dy, dx))
    kk, jj, ii = np.mgrid[-rk:rk + 1, -rj:rj + 1, -ri:ri + 1]
    return (kk * dz) ** 2 + (jj * dy) ** 2 + (ii * dx) ** 2 <= r * r + 1e-6


def referencia(data: np.ndarray, espac: tuple[float, float, float], centro_kji, diam_mm: float = DIAM_FIGADO_MM,
               mascara: np.ndarray | None = None, busca_mm: float = BUSCA_MM, fator: float = 1.0) -> dict | None:
    """Esfera de referência: perto de `centro_kji` (até `busca_mm`), o lugar de menor desvio-padrão; com
    `mascara`, só onde a esfera cabe inteira dentro dela. Valores × `fator` (SUV ou SUL por Bq/ml).
    Devolve {media, dp, max, n, centro (k, j, i), diam_mm} ou None."""
    dz, dy, dx = (float(v) for v in espac)
    nz, ny, nx = data.shape
    bola = _esfera(dz, dy, dx, diam_mm)
    bk, bj, bi = (s // 2 for s in bola.shape)
    ck, cj, ci = (int(round(v)) for v in centro_kji)
    sk, sj, si = (int(busca_mm / max(d, 1e-6)) for d in (dz, dy, dx))
    passo = (max(1, sk // 6), max(1, sj // 6), max(1, si // 6))
    melhor = None
    for k in range(ck - sk, ck + sk + 1, passo[0]):
        if k - bk < 0 or k + bk >= nz:
            continue
        for j in range(cj - sj, cj + sj + 1, passo[1]):
            if j - bj < 0 or j + bj >= ny:
                continue
            for i in range(ci - si, ci + si + 1, passo[2]):
                if i - bi < 0 or i + bi >= nx:
                    continue
                if ((k - ck) * dz) ** 2 + ((j - cj) * dy) ** 2 + ((i - ci) * dx) ** 2 > busca_mm * busca_mm:
                    continue
                sl = (slice(k - bk, k + bk + 1), slice(j - bj, j + bj + 1), slice(i - bi, i + bi + 1))
                if mascara is not None and not mascara[sl][bola].all():
                    continue
                v = data[sl][bola].astype(np.float64)
                dp = float(v.std())
                if melhor is None or dp < melhor[0]:
                    melhor = (dp, (k, j, i), v)
    if melhor is None:
        return None
    dp, c, v = melhor
    return {"media": round(float(v.mean()) * fator, 3), "dp": round(dp * fator, 3),
            "max": round(float(v.max()) * fator, 3), "n": int(v.size), "centro": [int(x) for x in c],
            "diam_mm": diam_mm}


def centro_da_mascara(mascara: np.ndarray) -> tuple[int, int, int] | None:
    """Ponto de partida automático no fígado: o voxel mais fundo (mais longe da borda) do lobo direito (a metade
    da máscara do lado esquerdo da imagem, que é o lado direito do paciente na axial padrão)."""
    if mascara is None or not mascara.any():
        return None
    m = mascara.copy()
    ks, js, is_ = np.nonzero(m)
    meio = int(np.median(is_))
    m[:, :, meio + 1:] = False                  # lobo direito do paciente: colunas menores (axial LPS padrão)
    if not m.any():
        m = mascara
    prof = m.copy()
    ultimo = m
    for _ in range(40):                          # erosão de 6 vizinhos até sobrar o miolo
        e = prof.copy()
        e[1:] &= prof[:-1]
        e[:-1] &= prof[1:]
        e[:, 1:] &= prof[:, :-1]
        e[:, :-1] &= prof[:, 1:]
        e[:, :, 1:] &= prof[:, :, :-1]
        e[:, :, :-1] &= prof[:, :, 1:]
        e[0], e[-1], e[:, 0], e[:, -1], e[:, :, 0], e[:, :, -1] = False, False, False, False, False, False
        if not e.any():
            break
        ultimo, prof = e, e
    ks, js, is_ = np.nonzero(ultimo)
    c = np.array([ks.mean(), js.mean(), is_.mean()])
    n = int(np.argmin((ks - c[0]) ** 2 + (js - c[1]) ** 2 + (is_ - c[2]) ** 2))
    return int(ks[n]), int(js[n]), int(is_[n])


def mascara_na_grade(mv, vol) -> np.ndarray:
    """Uma MaskVolume (máscara em mm, de qualquer série do exame) levada para a grade do volume `vol` (PET),
    pelo vizinho mais próximo, corte a corte."""
    nz, ny, nx = vol.data.shape
    mz, my, mx = mv.mascara.shape
    jj, ii = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    out = np.zeros((nz, ny, nx), bool)
    inv = np.linalg.inv(np.asarray(mv.matriz, float))
    M = vol.matrix()
    base = np.stack([ii.ravel(), jj.ravel(), np.zeros(ii.size)]).astype(float)
    for k in range(nz):
        base[2] = k
        p = np.asarray(vol.origin, float)[:, None] + M @ base
        q = np.rint(inv @ (p - np.asarray(mv.origem, float)[:, None])).astype(int)
        qi, qj, qk = q[0], q[1], q[2]
        ok = (qi >= 0) & (qi < mx) & (qj >= 0) & (qj < my) & (qk >= 0) & (qk < mz)
        if not ok.any():
            continue
        f = np.zeros(ny * nx, bool)
        f[ok] = mv.mascara[qk[ok], qj[ok], qi[ok]]
        out[k] = f.reshape(ny, nx)
    return out


def e_figado(rotulo: str) -> bool:
    t = (rotulo or "").lower()
    return ("liver" in t or "fígado" in t or "figado" in t) and "segment" not in t and "vessel" not in t


def em_sul(r: dict | None) -> dict | None:
    """A referência (guardada em SUV) em SUL, quando o exame tem a razão da massa magra; senão, em SUV."""
    if not r:
        return r
    k = r.get("sul_razao")
    if not k:
        return r
    return {**r, **{c: round(r[c] * k, 3) for c in ("media", "dp", "max") if r.get(c) is not None}, "unidade": "SUL"}


# ------------------------------------------------------------------ PERCIST
def limiar_percist(figado: dict | None, mediastino: dict | None = None) -> tuple[float | None, str]:
    """Limiar de lesão mensurável: 1,5 × média do fígado + 2 × DP; sem o fígado, 2 × média do pool + 2 × DP."""
    if figado and figado.get("media") is not None:
        return 1.5 * figado["media"] + 2.0 * (figado.get("dp") or 0.0), "1,5 × fígado + 2 DP"
    if mediastino and mediastino.get("media") is not None:
        return 2.0 * mediastino["media"] + 2.0 * (mediastino.get("dp") or 0.0), "2 × mediastino + 2 DP"
    return None, ""


def comparar_figado(a: dict | None, b: dict | None) -> tuple[str, str] | None:
    """PERCIST: o SULmédio do fígado não deve variar mais de 20% nem 0,3 entre os exames."""
    if not a or not b or not a.get("media") or b.get("media") is None:
        return None
    d = b["media"] - a["media"]
    pct = 100.0 * d / a["media"]
    if abs(pct) > 20.0 or abs(d) > 0.3:
        return "aviso", f"fígado {a['media']:.2f} → {b['media']:.2f} ({pct:+.0f}%): acima de 20% ou 0,3 — " \
                        "os exames não são comparáveis pelo PERCIST"
    return "ok", f"fígado {a['media']:.2f} → {b['media']:.2f} ({pct:+.0f}%)"


# ------------------------------------------------------------------ Deauville
def deauville(suvmax: float | None, figado: dict | None, mediastino: dict | None, nova: bool = False,
              ausente: bool = False, fator5: float = FATOR_DEAUVILLE_5) -> str:
    """Proposta do escore (texto "1".."5" ou "" sem referência)."""
    if ausente:
        return "1"
    if nova:
        return "5"
    if suvmax is None or not figado or figado.get("media") is None:
        return ""
    fmax = figado.get("max") or figado["media"]
    if suvmax > fator5 * fmax:
        return "5"
    if suvmax > figado["media"]:
        return "4"
    if mediastino and mediastino.get("media") is not None and suvmax <= mediastino["media"]:
        return "2"
    return "3"


def resposta_lugano(escores: list[str], max_base: float | None, max_atual: float | None, nova: bool) -> str:
    """Resposta metabólica (Lugano 2014) pelo maior escore do exame: 1–3 resposta completa; 4–5 com captação
    menor que na base resposta parcial, igual sem resposta, maior (ou lesão nova) progressão."""
    if nova:
        return "DMP"
    nums = [int(e) for e in escores if e and e.isdigit()]
    if not nums:
        return "NA"
    if max(nums) <= 3:
        return "RMC"
    if max_base is None or max_atual is None:
        return "NA"
    if max_atual < max_base * 0.95:
        return "RMP"
    if max_atual > max_base * 1.05:
        return "DMP"
    return "DME"


# ------------------------------------------------------------------ Q.Check
def _f(v) -> float | None:
    try:
        x = float(v)
        return x if not math.isnan(x) else None
    except (TypeError, ValueError):
        return None


def cabecalho(ds) -> dict:
    """Os dados do PET que mudam o SUV ou a comparação, de um arquivo da série."""
    seq = ds.get("RadiopharmaceuticalInformationSequence")
    rp = seq[0] if seq else {}
    g = (lambda k: rp.get(k) if hasattr(rp, "get") else None)
    inj = None
    if g("RadiopharmaceuticalStartDateTime"):
        v = str(g("RadiopharmaceuticalStartDateTime"))
        inj = _dt(v[:8], v[8:])
    if inj is None:
        inj = _dt(str(ds.get("SeriesDate", "") or ds.get("StudyDate", "")), str(g("RadiopharmaceuticalStartTime") or ""))
    aq = _dt(str(ds.get("AcquisitionDate", "") or ds.get("SeriesDate", "")),
             str(ds.get("AcquisitionTime", "") or ds.get("SeriesTime", "")))
    serie = _dt(str(ds.get("SeriesDate", "") or ""), str(ds.get("SeriesTime", "") or ""))
    ini = min([t for t in (aq, serie) if t is not None], default=None)
    captacao = None
    if inj is not None and ini is not None:
        s = (ini - inj).total_seconds()
        if s < -12 * 3600:
            s += 24 * 3600
        captacao = s / 60.0
    radio = ""
    try:
        cs = g("RadiopharmaceuticalCodeSequence") or g("RadionuclideCodeSequence")
        radio = str(g("Radiopharmaceutical") or (cs[0].get("CodeMeaning") if cs else "") or "")
    except Exception:  # noqa: BLE001
        radio = str(g("Radiopharmaceutical") or "")
    sp = ds.get("PixelSpacing") or [None, None]
    corr = ds.get("CorrectedImage") or []
    if isinstance(corr, str):
        corr = [corr]
    return {
        "captacao_min": captacao, "peso": _f(ds.get("PatientWeight")), "altura": _f(ds.get("PatientSize")),
        "sexo": str(ds.get("PatientSex", "") or ""), "dose_mbq": (_f(g("RadionuclideTotalDose")) or 0) / 1e6 or None,
        "meia_vida": _f(g("RadionuclideHalfLife")), "radiofarmaco": radio,
        "unidade": str(ds.get("Units", "") or "").upper(), "decaimento": str(ds.get("DecayCorrection", "") or "").upper(),
        "correcoes": [str(c).upper() for c in corr], "matriz": f"{ds.get('Rows', '')} × {ds.get('Columns', '')}",
        "pixel": _f(sp[0]) if sp else None, "espessura": _f(ds.get("SliceThickness")),
        "reconstrucao": str(ds.get("ReconstructionMethod", "") or ds.get("ConvolutionKernel", "") or ""),
        "fabricante": str(ds.get("Manufacturer", "") or ""), "modelo": str(ds.get("ManufacturerModelName", "") or ""),
        "software": "/".join(str(x) for x in (ds.get("SoftwareVersions") or [])) if not isinstance(
            ds.get("SoftwareVersions"), str) else str(ds.get("SoftwareVersions")),
        "data": str(ds.get("StudyDate", "") or ""),
    }


def conferir(h: dict) -> list[tuple[str, str, str]]:
    """[(nível, item, texto)] de um exame."""
    out = []
    c = h.get("captacao_min")
    if c is None:
        out.append(("erro", "Tempo de captação", "sem o horário da injeção ou da aquisição"))
    elif CAPTACAO_MIN[0] <= c <= CAPTACAO_MIN[1]:
        out.append(("ok", "Tempo de captação", f"{c:.0f} min"))
    else:
        out.append(("aviso", "Tempo de captação", f"{c:.0f} min (o PERCIST pede 50–70 min)"))
    out.append(("ok", "Peso", f"{h['peso']:.1f} kg") if h.get("peso") else ("erro", "Peso", "sem o peso: sem SUV"))
    if h.get("altura") and (h.get("sexo") or "")[:1].upper() in ("M", "F"):
        out.append(("ok", "Altura e sexo", f"{h['altura']:.2f} m, {h['sexo']}"))
    else:
        out.append(("aviso", "Altura e sexo", "sem a altura ou o sexo: sem SUL (o PERCIST mede em SUL)"))
    out.append(("ok", "Dose", f"{h['dose_mbq']:.0f} MBq") if h.get("dose_mbq") else ("erro", "Dose", "sem a dose"))
    mv = h.get("meia_vida")
    if not mv:
        out.append(("erro", "Meia-vida", "sem a meia-vida"))
    elif "FDG" in (h.get("radiofarmaco") or "").upper() or "FLUORODEOXY" in (h.get("radiofarmaco") or "").upper():
        out.append(("ok", "Meia-vida", f"{mv:.0f} s") if abs(mv - MEIA_VIDA_F18) < 30 else
                   ("aviso", "Meia-vida", f"{mv:.0f} s (flúor-18 tem {MEIA_VIDA_F18:.0f} s)"))
    else:
        out.append(("info", "Meia-vida", f"{mv:.0f} s"))
    u = h.get("unidade") or ""
    out.append(("ok", "Unidade", u) if u in ("BQML", "GML") else
               ("erro", "Unidade", f"{u or 'vazia'}: SUV só com Bq/ml"))
    d = h.get("decaimento") or ""
    out.append(("ok", "Correção do decaimento", d) if d in ("START", "ADMIN") else
               ("aviso", "Correção do decaimento", d or "não informada"))
    corr = h.get("correcoes") or []
    falta = [x for x in ("ATTN", "DECY") if x not in corr]
    out.append(("ok", "Correções", ", ".join(corr)) if not falta else
               ("aviso", "Correções", f"falta {', '.join(falta)}" + (f" (tem {', '.join(corr)})" if corr else "")))
    out.append(("info", "Aquisição", f"matriz {h.get('matriz')}, pixel {h.get('pixel') or 0:.2f} mm, "
                                     f"espessura {h.get('espessura') or 0:.2f} mm, {h.get('reconstrucao') or '—'}"))
    out.append(("info", "Aparelho", f"{h.get('fabricante')} {h.get('modelo')} · {h.get('software') or '—'}"))
    return out


def comparar(a: dict, b: dict) -> list[tuple[str, str, str]]:
    """[(nível, item, texto)] entre o exame anterior `a` e o atual `b`."""
    out = []
    ca, cb = a.get("captacao_min"), b.get("captacao_min")
    if ca is not None and cb is not None:
        dif = abs(cb - ca)
        out.append(("ok" if dif <= DIF_CAPTACAO_MAX_MIN else "aviso", "Tempo de captação",
                    f"{ca:.0f} → {cb:.0f} min (diferença de {dif:.0f} min"
                    + ("" if dif <= DIF_CAPTACAO_MAX_MIN else "; o PERCIST aceita até 15") + ")"))
    for chave, item in (("fabricante", "Fabricante"), ("modelo", "Modelo"), ("reconstrucao", "Reconstrução"),
                        ("matriz", "Matriz"), ("unidade", "Unidade"), ("radiofarmaco", "Radiofármaco")):
        va, vb = a.get(chave) or "", b.get(chave) or ""
        if va != vb:
            out.append(("aviso", item, f"{va or '—'} → {vb or '—'}"))
    if (a.get("software") or "") != (b.get("software") or ""):
        out.append(("info", "Software", f"{a.get('software') or '—'} → {b.get('software') or '—'}"))
    ea, eb = a.get("espessura"), b.get("espessura")
    if ea and eb and abs(ea - eb) > 0.1:
        out.append(("aviso", "Espessura", f"{ea:.2f} → {eb:.2f} mm"))
    pa, pb = a.get("peso"), b.get("peso")
    if pa and pb:
        pct = 100 * (pb - pa) / pa
        out.append(("info" if abs(pct) < 10 else "aviso", "Peso", f"{pa:.1f} → {pb:.1f} kg ({pct:+.0f}%)"))
    da, db = a.get("dose_mbq"), b.get("dose_mbq")
    if da and db:
        out.append(("info", "Dose", f"{da:.0f} → {db:.0f} MBq"))
    if not [x for x in out if x[0] == "aviso"]:
        out.insert(0, ("ok", "Comparáveis", "nada no cabeçalho impede a comparação"))
    return out


def texto(itens: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"{NIVEIS.get(n, n)} {item}: {t}" for n, item, t in itens)
