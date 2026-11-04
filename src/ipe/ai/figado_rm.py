"""Gordura e ferro hepáticos na RM (0.99.49) — pedido dele em 04/11/2026: *"quero também medir o ferro e
a gordura hepática na ressonância"*.

**O que o acervo mostrou** (RM ABDOME TOTAL de 04/11, GE Optima MR450w, 1,5 T):
- **IDEAL IQ**: o aparelho já grava os mapas — "FatFrac: IDEAL IQ (R2*)" (ImageType DERIVED\\PRIMARY\\
  DIXON\\FAT_FRACTION) e "R2*: IDEAL IQ (R2*)" (…\\R2_STAR_MAP), 32 cortes de 16 mm a cada 8 mm, pixel
  1,56 mm. O mapa de gordura vem **em porcentagem** (a gordura subcutânea dá 91–100; o ar, ruído de −100 a
  200); o de R2* em **s⁻¹** (tecido magro ≈ 47 s⁻¹).
- **Dupla eco** "3D Ax IN/OUT": as duas ecos na **mesma série**, TE 2,08 ms (fora de fase) e 4,17 ms (em
  fase); e o LAVA Flex com "InPhase:" e "OutPhase:" em séries separadas.

**O que o programa faz** — o fígado vem do TotalSegmentator (`total_mr`, fígado e baço, e
`liver_segments_mr` para os segmentos de Couinaud), rodado numa série anatômica axial do exame; a máscara é
levada, ponto a ponto pela posição no paciente, para a grade de cada mapa:

| medida | de onde | conta |
|---|---|---|
| **PDFF** (fração de gordura pela densidade de prótons) | mapa de fração de gordura do aparelho (IDEAL IQ, mDIXON Quant, LiverLab) | mediana, média e p25–p75 no fígado (a borda, 1 voxel, fica de fora); por segmento |
| **R2\\*** e T2\\* | mapa de R2\\* (ou de T2\\*, convertido: R2\\* = 1000/T2\\*) | mediana no fígado e no baço |
| **ferro estimado** | R2\\* a 1,5 T | LIC ≈ 0,0254 · R2\\* + 0,202 mg Fe/g (Wood et al., Blood 2005) |
| **ferro a 3 T** (0.99.50) | R2\\* a 3 T | R2\\* ÷ 2,05 = equivalente a 1,5 T (fígado, Alam et al., JCMR 2016), depois Wood |
| **grau** (0.99.50) | LIC | 3,2–7 leve, 7–15 moderada, > 15 grave (mg Fe/g) — texto de referência |
| **fração de sinal de gordura** | dupla eco em fase / fora de fase | (EF − FF) / (2 · EF) com as médias do fígado; **não é PDFF** |

Referências, como texto ao lado do número (nunca veredito): PDFF ≥ 6,4% grau ≥ 1, ≥ 17,4% grau ≥ 2,
≥ 22,1% grau 3 — limiares de alta especificidade em DHGNA (Tang et al., Radiology 2015). Na dupla eco,
em fase com sinal **menor** que fora de fase sugere ferro (a queda de T2\\* entre 2 e 4 ms) — e o ferro
faz a fração de sinal de gordura sair menor que a real.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "figado_rm"
TITULO = "Gordura e ferro hepáticos na RM (IA)"
MARCA = "· TotalSegmentator"
DESC_SEG = f"Fígado na RM {MARCA}"
SERIE_SEG = 983
MIN_CORTES = 20
MODALIDADES = ("MR",)
MOTIVO_MODALIDADE = "A gordura e o ferro hepáticos por esta ferramenta são medidos na RM."
MODELO = "TotalSegmentator total_mr + liver_segments_mr; mapas do aparelho"
CHAVE_SAIDA = "figado_rm"
TIPO_GORDURA = "Gordura hepática (PDFF)"
TIPO_FERRO = "Ferro hepático (R2*)"
TIPO_DIXON = "Gordura hepática (dupla eco)"

#: Wood et al., Blood 2005;106:1460 — R2* (s⁻¹) a 1,5 T → concentração hepática de ferro (mg Fe/g de peso seco)
WOOD_A, WOOD_B = 0.0254, 0.202
#: Alam et al., J Cardiovasc Magn Reson 2016;18:40 — no fígado o R2* a 3 T foi 105% maior que a 1,5 T (ajuste
#: linear, R² 0,993); os autores sugerem dividir o R2* de 3 T por ~2 para chegar ao equivalente a 1,5 T.
ALAM_FATOR = 2.05
#: faixas de sobrecarga pelo LIC (mg Fe/g de peso seco) — Abdom Radiol 2022 (doi 10.1007/s00261-022-03762-4)
LIC_GRAUS = ((15.0, "sobrecarga grave (> 15)"), (7.0, "sobrecarga moderada (7–15)"),
             (3.2, "sobrecarga leve (3,2–7)"))
LIC_REF = "LIC 3,2–7 leve, 7–15 moderada, > 15 mg Fe/g grave"
PDFF_REF = "PDFF ≥ 6,4% grau ≥ 1, ≥ 17,4% grau ≥ 2, ≥ 22,1% grau 3 (Tang et al., Radiology 2015)"

_FF_DESC = ("FATFRAC", "FAT FRAC", "FAT FRACTION", "FAT_FRACTION", "PDFF", "FF MAP", "FATFRACTION", "FAT%")
_R2_DESC = ("R2*", "R2STAR", "R2 STAR", "R2_STAR")
_T2_DESC = ("T2*", "T2STAR", "T2 STAR", "T2_STAR")

SEGMENTOS = {f"liver_segment_{k}": f"S{k}" for k in range(1, 9)}

# Configurações ▸ CAD/IA
CHAVE_AUTO = "figado_rm.auto"
CHAVE_EXAME_CONTEM = "figado_rm.exame_contem"
CHAVE_MODALIDADES = "figado_rm.modalidades"
CHAVE_PRIOR_CT = "figado_rm.prioridade"
CHAVE_ESPESSURA = "figado_rm.espessura_max"
CHAVE_MIN_CORTES = "figado_rm.min_cortes"
CHAVE_DESTINOS = "figado_rm.destinos"
CHAVE_SEGMENTOS = "figado_rm.segmentos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "ABD|ABDOME|ABDOMEN|ABDOMINAL|FIGADO|HEPAT|FERRO|LIVER|COLANGIO",
    CHAVE_MODALIDADES: ["MR"],
    CHAVE_PRIOR_CT: "WATER: 3D AX|WATER|LAVA|VIBE|MDIXON|DIXON|IN PHASE|INPHASE|T1|AX",
    CHAVE_ESPESSURA: 6.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
    CHAVE_SEGMENTOS: 1.0,
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("FATFRAC", "FAT FRAC", "R2*", "T2*", "ADC", "DWI", "DIFUS", "FAT:", "ORIG ", "PELVE", "PELVIS")}
NOME_CADIA = "Gordura e ferro hepáticos (RM)"
TITULO_CADIA = "Gordura (PDFF) e ferro (R2*) do fígado na RM — TotalSegmentator + mapas do aparelho"
EXPLICACAO_CADIA = ("Na RM de abdome: acha o fígado e o baço (e os segmentos de Couinaud) numa série axial e mede "
                    "nos mapas do aparelho — fração de gordura (IDEAL IQ, mDIXON Quant, LiverLab) e R2* —, com a "
                    "estimativa de ferro a 1,5 T; com a dupla eco em fase / fora de fase, a fração de sinal de "
                    "gordura. Os números aparecem em Aplicações ▸ Achados de IA, para conferir antes do laudo.")
OPCOES = ((CHAVE_SEGMENTOS, "Por segmento de Couinaud (1 = sim, 0 = não):", 0.0, 1.0, "",
           "Roda também a tarefa liver_segments_mr e dá a gordura de cada segmento (uns minutos a mais)."),)
CHAVES_GORDURA = ("pdff_mediana", "pdff_media", "pdff_p25", "pdff_p75", "pdff_segmentos", "voxels")
CHAVES_FERRO = ("r2_mediana", "t2_ms", "r2_15", "lic", "lic_grau", "baco_r2", "r2_p25", "r2_p75")
CHAVES_DIXON = ("ff_sinal", "ef", "ff", "razao_ef_ff")
CHAVES = CHAVES_GORDURA + CHAVES_FERRO + CHAVES_DIXON


def config(settings, chave):
    if chave == CHAVE_MODALIDADES:
        return ["MR"]
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v


def exame_serve(info: dict, settings=None) -> bool:
    from ipe.ai import totalseg as TS
    return TS.exame_serve(info, settings, PERFIL, config)


def escolher_serie(repo, study_uid: str, settings=None):
    from ipe.ai import totalseg as TS
    return TS.escolher_serie(repo, study_uid, settings, PERFIL, config, min_absoluto=MIN_CORTES)


def ja_feita(repo, study_uid: str) -> bool:
    from ipe.ai import totalseg as TS
    return TS.ja_segmentado(repo, study_uid, DESC_SEG)


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    out = [{"nome": "total_mr", "roi": ["liver", "spleen"], "rotulo": "fígado e baço", "figado_rm": True}]
    if float(config(settings, CHAVE_SEGMENTOS) or 0) >= 0.5:
        out.append({"nome": "liver_segments_mr", "rotulo": "segmentos do fígado (Couinaud)", "figado_rm": True})
    return out


# ------------------------------------------------------------------ achar as séries
def _sem_acento(t: str) -> str:
    from ipe.ai.totalseg import _sem_acento as f
    return f(t)


def _cabecalho(repo, series_uid: str):
    import pydicom
    inst = repo.instances_for_series(series_uid)
    if not inst:
        return None
    try:
        return pydicom.dcmread(inst[len(inst) // 2]["path"], stop_before_pixels=True, force=True)
    except Exception:  # noqa: BLE001
        return None


def tipo_do_mapa(descricao: str, image_type) -> str:
    """"ff", "r2", "t2" ou "" — pela ImageType (o arquivo manda) e, sem ela, pela descrição."""
    it = " ".join(str(x) for x in (image_type or [])).upper()
    if "FAT_FRACTION" in it or "FATFRACTION" in it or "PDFF" in it:
        return "ff"
    if "R2_STAR" in it or "R2STAR" in it:
        return "r2"
    if "T2_STAR" in it or "T2STAR" in it:
        return "t2"
    d = _sem_acento(descricao or "")
    if any(p in d for p in _FF_DESC):
        return "ff"
    if any(p in d for p in _R2_DESC):
        return "r2"
    if any(p in d for p in _T2_DESC) and "MAP" in d:
        return "t2"
    return ""


def mapas_do_exame(repo, study_uid: str) -> dict:
    """{"ff": series_uid, "r2"/"t2": series_uid} — o mais recente de cada tipo."""
    out = {}
    for s in repo.series_for_study(study_uid):
        if (s.modality or "").upper() != "MR":
            continue
        ds = _cabecalho(repo, s.series_uid)
        tipo = tipo_do_mapa(s.description or "", ds.get("ImageType") if ds is not None else None)
        if tipo:
            out[tipo] = s.series_uid
    if "r2" in out:
        out.pop("t2", None)
    return out


def dupla_eco(repo, study_uid: str):
    """(frames fora de fase, frames em fase, descrição) ou None.

    Preferência: a série com as **duas ecos juntas** (dupla eco verdadeira); senão o par "InPhase:" /
    "OutPhase:" da mesma aquisição. Fora de fase é a eco mais curta."""
    import pydicom

    from ipe.imaging.series import build_frames
    series = [s for s in repo.series_for_study(study_uid) if (s.modality or "").upper() == "MR"]
    for s in series:
        d = _sem_acento(s.description or "")
        if not ("IN/OUT" in d or "IN-OUT" in d or "DUAL ECHO" in d or "DUALECHO" in d or "IN OUT" in d):
            continue
        inst = repo.instances_for_series(s.series_uid)
        tes: dict[float, list] = {}
        for i in inst:
            try:
                te = float(pydicom.dcmread(i["path"], stop_before_pixels=True, force=True,
                                           specific_tags=["EchoTime"]).EchoTime)
            except Exception:  # noqa: BLE001
                continue
            tes.setdefault(round(te, 2), []).append(i)
        if len(tes) == 2:
            curta, longa = sorted(tes)
            return (build_frames(tes[curta], s.series_uid), build_frames(tes[longa], s.series_uid),
                    f"{s.description} (TE {curta:g} e {longa:g} ms)")
    pares = {}
    for s in series:
        d = _sem_acento(s.description or "")
        if d.startswith("ORIG "):
            continue
        for chave, papel in (("INPHASE:", "ef"), ("IN PHASE:", "ef"), ("OUTPHASE:", "ff"), ("OUT PHASE:", "ff"),
                             ("OPPOSED", "ff")):
            if d.startswith(chave) or (chave == "OPPOSED" and chave in d):
                resto = d.split(":", 1)[-1].strip()
                pares.setdefault(resto, {})[papel] = s
    for resto, par in pares.items():
        if "ef" in par and "ff" in par:
            ef = build_frames(repo.instances_for_series(par["ef"].series_uid), par["ef"].series_uid)
            ff = build_frames(repo.instances_for_series(par["ff"].series_uid), par["ff"].series_uid)
            return ff, ef, f"{par['ff'].description} / {par['ef'].description}"
    return None


# ------------------------------------------------------------------ amostrar a máscara noutra grade
def _amostrar(vol_mascara, mascara: np.ndarray, vol_alvo) -> np.ndarray:
    """A máscara (grade de `vol_mascara`) levada para a grade de `vol_alvo`, pelo vizinho mais próximo,
    ponto a ponto na posição do paciente. Corte a corte: o LAVA do acervo tem 126 × 512 × 512."""
    nz, ny, nx = vol_alvo.data.shape
    mz, my, mx = mascara.shape
    jj, ii = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    base = np.stack([ii.ravel(), jj.ravel(), np.zeros(ii.size)]).astype(float)
    inv = np.linalg.inv(vol_mascara.matrix())
    M = vol_alvo.matrix()
    o_alvo, o_masc = np.asarray(vol_alvo.origin, float), np.asarray(vol_mascara.origin, float)
    out = np.zeros((nz, ny, nx), bool)
    zs = np.nonzero(mascara.any(axis=(1, 2)))[0]
    if not len(zs):
        return out
    for k in range(nz):
        base[2] = k
        q = inv @ (o_alvo[:, None] + M @ base - o_masc[:, None])
        qk = np.rint(q[2]).astype(int)
        if qk.max() < zs[0] or qk.min() > zs[-1]:
            continue
        qi, qj = np.rint(q[0]).astype(int), np.rint(q[1]).astype(int)
        ok = (qi >= 0) & (qi < mx) & (qj >= 0) & (qj < my) & (qk >= 0) & (qk < mz)
        fatia = np.zeros(ny * nx, bool)
        fatia[ok] = mascara[qk[ok], qj[ok], qi[ok]]
        out[k] = fatia.reshape(ny, nx)
    return out


def _ero2(m: np.ndarray, n: int = 1) -> np.ndarray:
    """Erosão só no plano de cada corte: os mapas têm cortes grossos (16 mm no IDEAL IQ do acervo) e
    erodir na direção do corte apagaria o fígado inteiro."""
    from ipe.ai.composicao import _ero2 as e
    return np.stack([e(s, n) for s in m]) if m.ndim == 3 else e(m, n)


def grau_do_ferro(lic: float | None) -> str:
    """Faixa de referência do LIC (texto ao lado do número, nunca veredito)."""
    if lic is None:
        return ""
    for limite, txt in LIC_GRAUS:
        if lic >= limite:
            return txt
    return "abaixo de 3,2 (fora das faixas de sobrecarga)"


def r2_para_15t(r2: float, campo: float | None) -> tuple[float | None, str]:
    """(R2* equivalente a 1,5 T, ou None; de onde veio). 1,5 T: o próprio; 3 T: ÷ ALAM_FATOR."""
    if campo is None:
        return None, "sem a intensidade do campo no arquivo"
    if abs(campo - 1.5) < 0.2:
        return r2, "1,5 T"
    if abs(campo - 3.0) < 0.3:
        return r2 / ALAM_FATOR, "3 T"
    return None, f"campo de {campo:g} T".replace(".", ",")


def _stats(v: np.ndarray) -> dict:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return {}
    return {"mediana": float(np.median(v)), "media": float(v.mean()), "p25": float(np.percentile(v, 25)),
            "p75": float(np.percentile(v, 75)), "n": int(len(v))}


# ------------------------------------------------------------------ a conta
@dataclass
class Resultado:
    gordura: dict = field(default_factory=dict)
    ferro: dict = field(default_factory=dict)
    dixon: dict = field(default_factory=dict)
    centro: list | None = None
    avisos_gordura: list = field(default_factory=list)
    avisos_ferro: list = field(default_factory=list)
    avisos_dixon: list = field(default_factory=list)
    elegibilidade: str = ""
    campo: float | None = None
    versao: str = ""
    series_uid: str = ""
    series_mapas: dict = field(default_factory=dict)
    mascaras: dict = field(default_factory=dict)


def _volume(t, frames):
    from ipe.imaging.volume import build_volume
    return build_volume(frames, t.cache)


def _frames(t, series_uid):
    from ipe.imaging.series import build_frames
    return build_frames(t.repo.instances_for_series(series_uid), series_uid)


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import cefalometria as CF
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    ms = CF.Mascaras(vol, rotulos)
    figado, baco = ms.get("liver"), ms.get("spleen")
    res.elegibilidade = (f"RM, fígado achado na série “{t.descricao_serie or t.series_uid[-8:]}” "
                         f"({vol.data.shape[0]} cortes)")
    ds0 = _cabecalho(t.repo, t.series_uid)
    try:
        res.campo = float(ds0.get("MagneticFieldStrength")) if ds0 is not None else None
    except (TypeError, ValueError):
        res.campo = None
    if figado is None:
        res.avisos_gordura.append("a IA não achou o fígado nesta série")
        return res
    kk, jj, ii = np.argwhere(figado).mean(axis=0)
    res.centro = [float(x) for x in vol.voxel_to_patient(ii, jj, kk)]
    res.mascaras = {"liver": figado}
    if baco is not None:
        res.mascaras["spleen"] = baco
    segs = {SEGMENTOS[n]: ms.get(n) for n in SEGMENTOS if ms.get(n) is not None}
    for nome, m in segs.items():
        res.mascaras[nome] = m
    mapas = mapas_do_exame(t.repo, t.study_uid)
    res.series_mapas = dict(mapas)
    # ---------------- gordura
    if "ff" in mapas:
        try:
            vff = _volume(t, _frames(t, mapas["ff"]))
            dados = np.asarray(vff.data, float)
            escala = 1.0
            if float(np.percentile(dados, 99.5)) > 300:          # 0–1000 (por mil): Siemens/Philips
                escala = 0.1
                res.avisos_gordura.append("mapa em 0–1000: lido como décimos de porcento")
            m = _ero2(_amostrar(vol, figado, vff), 1)
            if m.sum() < 20:
                m = _amostrar(vol, figado, vff)
            st = _stats(dados[m] * escala)
            if st:
                res.gordura = {
                    "pdff_mediana": AC.numero(round(st["mediana"], 1), "%", "PDFF (mediana)"),
                    "pdff_media": AC.numero(round(st["media"], 1), "%", "PDFF (média)"),
                    "pdff_p25": AC.numero(round(st["p25"], 1), "%", "PDFF p25"),
                    "pdff_p75": AC.numero(round(st["p75"], 1), "%", "PDFF p75"),
                    "voxels": AC.numero(st["n"], "", "Voxels medidos"),
                }
                por_seg = []
                for nome, mk in segs.items():
                    ms_ = _ero2(_amostrar(vol, mk, vff), 1)
                    s2 = _stats(dados[ms_] * escala) if ms_.sum() >= 5 else {}
                    if s2:
                        por_seg.append(f"{nome} {s2['mediana']:.1f}".replace(".", ","))
                if por_seg:
                    res.gordura["pdff_segmentos"] = AC.numero(" · ".join(por_seg), "%", "PDFF por segmento")
                res.avisos_gordura.append(f"referência: {PDFF_REF} — texto de referência, não diagnóstico")
        except Exception as e:  # noqa: BLE001
            log.exception("PDFF")
            res.avisos_gordura.append(f"não deu para ler o mapa de gordura: {e}")
    # ---------------- ferro
    chave_r = "r2" if "r2" in mapas else ("t2" if "t2" in mapas else "")
    if chave_r:
        try:
            vr = _volume(t, _frames(t, mapas[chave_r]))
            dados = np.asarray(vr.data, float)
            if chave_r == "t2":
                with np.errstate(divide="ignore"):
                    dados = np.where(dados > 0, 1000.0 / dados, np.nan)
                res.avisos_ferro.append("mapa de T2* convertido: R2* = 1000 / T2*")
            m = _ero2(_amostrar(vol, figado, vr), 1)
            if m.sum() < 20:
                m = _amostrar(vol, figado, vr)
            st = _stats(dados[m])
            if st:
                r2 = st["mediana"]
                res.ferro = {
                    "r2_mediana": AC.numero(round(r2, 1), "s⁻¹", "R2* (mediana)"),
                    "t2_ms": AC.numero(round(1000.0 / r2, 1) if r2 > 0 else None, "ms", "T2*"),
                    "r2_p25": AC.numero(round(st["p25"], 1), "s⁻¹", "R2* p25"),
                    "r2_p75": AC.numero(round(st["p75"], 1), "s⁻¹", "R2* p75"),
                }
                r15, como = r2_para_15t(r2, res.campo)
                if r15 is not None:
                    lic = round(WOOD_A * r15 + WOOD_B, 2)
                    if como == "3 T":
                        res.ferro["r2_15"] = AC.numero(round(r15, 1), "s⁻¹", "R2* equivalente a 1,5 T")
                        fator = f"{ALAM_FATOR:.2f}".replace(".", ",")
                        res.avisos_ferro.append(f"exame a 3 T: R2* ÷ {fator} para o equivalente a 1,5 T (Alam et "
                                                "al., JCMR 2016) antes da calibração de Wood — a 3 T o T2* curto "
                                                "mede pior")
                    res.ferro["lic"] = AC.numero(lic, "mg Fe/g", "Ferro estimado (LIC)")
                    res.ferro["lic_grau"] = AC.numero(grau_do_ferro(lic), "", "Faixa do LIC")
                    res.avisos_ferro.append("ferro estimado pela calibração de Wood et al. (Blood 2005): "
                                            "LIC = 0,0254 · R2* (1,5 T) + 0,202 mg Fe/g de peso seco — estimativa, "
                                            f"não diagnóstico; referência: {LIC_REF}")
                else:
                    res.avisos_ferro.append(f"sem ferro estimado (LIC): {como} — a calibração vale a 1,5 T, e a "
                                            "3 T com a conversão de Alam")
                if baco is not None:
                    mb = _ero2(_amostrar(vol, baco, vr), 1)
                    sb = _stats(dados[mb]) if mb.sum() >= 5 else {}
                    if sb:
                        res.ferro["baco_r2"] = AC.numero(round(sb["mediana"], 1), "s⁻¹", "R2* do baço")
        except Exception as e:  # noqa: BLE001
            log.exception("R2*")
            res.avisos_ferro.append(f"não deu para ler o mapa de R2*: {e}")
    # ---------------- dupla eco
    try:
        par = dupla_eco(t.repo, t.study_uid)
    except Exception:  # noqa: BLE001
        log.exception("dupla eco")
        par = None
    if par is not None:
        try:
            f_ff, f_ef, desc = par
            vff_, vef_ = _volume(t, f_ff), _volume(t, f_ef)
            m = _ero2(_amostrar(vol, figado, vef_), 1)
            if m.sum() >= 20 and vff_.data.shape == vef_.data.shape:
                ef = float(np.asarray(vef_.data, float)[m].mean())
                fo = float(np.asarray(vff_.data, float)[m].mean())
                fs = (ef - fo) / (2 * ef) * 100.0 if ef > 0 else None
                res.dixon = {
                    "ff_sinal": AC.numero(round(fs, 1) if fs is not None else None, "%",
                                          "Fração de sinal de gordura (dupla eco)"),
                    "ef": AC.numero(round(ef, 0), "", "Sinal em fase"),
                    "ff": AC.numero(round(fo, 0), "", "Sinal fora de fase"),
                    "razao_ef_ff": AC.numero(round(ef / fo, 2) if fo > 0 else None, "", "Em fase / fora de fase"),
                }
                res.avisos_dixon.append(f"da série {desc}: fração de sinal, não PDFF — não corrige T1 nem T2*")
                if fs is not None and fs < 0:
                    res.avisos_dixon.append("em fase com sinal menor que fora de fase: sugere ferro (e o ferro "
                                            "esconde a gordura nesta conta)")
        except Exception as e:  # noqa: BLE001
            log.exception("dupla eco")
            res.avisos_dixon.append(f"não deu para ler a dupla eco: {e}")
    if not (res.gordura or res.ferro or res.dixon):
        res.avisos_gordura.append("o exame não tem mapa de fração de gordura, mapa de R2*/T2* nem dupla eco em "
                                  "fase / fora de fase")
    return res


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "posicao": res.centro,
            "local": "fígado"}
    out = []
    for rot, tipo, nums, avisos in (("PDFF", TIPO_GORDURA, res.gordura, res.avisos_gordura),
                                    ("R2*", TIPO_FERRO, res.ferro, res.avisos_ferro),
                                    ("Dixon", TIPO_DIXON, res.dixon, res.avisos_dixon)):
        if nums:
            out.append({**base, "rotulo": rot, "tipo": tipo, "numeros": nums,
                        "elegibilidade": res.elegibilidade + (". Atenção: " + "; ".join(avisos) if avisos else "")})
    return out


def gravar(t, res: Resultado, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    import shutil
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from ipe.ai import cefalometria as CF
    from ipe.ai.totalseg_saida import _caminho_do_sop
    from ipe.db.repository import Repository
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    repo = repo or Repository(db)
    for se in repo.series_for_study(t.study_uid):
        if (se.description or "") == DESC_SEG:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
            except Exception:  # noqa: BLE001
                log.exception("trocar a SEG do fígado na RM anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    cores = {"liver": (170, 90, 60), "spleen": (140, 80, 200)}
    nomes = {"liver": "Fígado", "spleen": "Baço"}
    segs = []
    for nome, mk in res.mascaras.items():
        if mk is None or not mk.any():
            continue
        fat, off = CF._recorte(mk)
        cor = cores.get(nome, (230, 200, 90))
        segs.append((SimpleNamespace(mask=mk[fat], offset=off), nomes.get(nome, f"Segmento {nome}"), cor))
    if segs:
        vol = t.vol
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"TotalSegmentator {versao} total_mr".strip()), anatomia=True)
        tmp = Path(tempfile.mkdtemp(prefix="dv_figrm_"))
        try:
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
            out["series"] += sorted(getattr(r, "new_series", None) or [])
            out["seg_sop"] = str(ds.SOPInstanceUID)
            out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens_para_o_banco(res, t, versao))
    return out


def resumo(res: Resultado) -> str:
    partes = []
    if res.gordura:
        partes.append(f"PDFF {AC._fmt(res.gordura['pdff_mediana'])}")
    if res.ferro:
        partes.append(f"R2* {AC._fmt(res.ferro['r2_mediana'])}"
                      + (f" (ferro ≈ {AC._fmt(res.ferro['lic'])})" if "lic" in res.ferro else ""))
    if res.dixon and res.dixon["ff_sinal"]["v"] is not None:
        partes.append(f"fração de sinal (dupla eco) {AC._fmt(res.dixon['ff_sinal'])}")
    return "; ".join(partes) or "nada medido"


def n_itens(res: Resultado) -> int:
    return int(bool(res.gordura)) + int(bool(res.ferro)) + int(bool(res.dixon))


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Fígado na RM pronto em {minutos:.1f} min — {resumo(res)}. Os números estão em Aplicações ▸ Achados "
           f"de IA, para conferir antes do laudo; a máscara do fígado está na série “{DESC_SEG}”.")
    avisos = res.avisos_gordura + res.avisos_ferro + res.avisos_dixon
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        if x is None:
            return None
        return f"{float(x):.{casas}f}".replace(".", ",") if isinstance(x, (int, float)) else str(x)
    if a.get("tipo") == TIPO_GORDURA:
        txt = f"Fração de gordura hepática (PDFF) mediana de {v('pdff_mediana')}%"
        if v("pdff_p25") and v("pdff_p75"):
            txt += f" (intervalo interquartil {v('pdff_p25')}–{v('pdff_p75')}%)"
        return txt + "."
    if a.get("tipo") == TIPO_FERRO:
        txt = f"R2* hepático mediano de {v('r2_mediana', 0)} s⁻¹ (T2* {v('t2_ms')} ms)"
        if v("r2_15", 0):
            txt += f", equivalente a {v('r2_15', 0)} s⁻¹ a 1,5 T"
        if v("lic", 2):
            txt += f", concentração de ferro estimada em {v('lic', 2)} mg Fe/g"
            if v("lic_grau"):
                txt += f" ({v('lic_grau')})"
        if v("baco_r2", 0):
            txt += f"; R2* do baço {v('baco_r2', 0)} s⁻¹"
        return txt + "."
    return (f"Fração de sinal de gordura hepática na dupla eco (em fase / fora de fase) de {v('ff_sinal')}%, "
            "sem correção de T2*.")
