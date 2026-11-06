"""Composição corporal em L3 e atenuação hepática (esteatose) na TC (0.99.47).

Não usa o repositório BodyComposition (Python 3.11 exato, 25–52 GB de RAM): usa o que o Ipê já roda —
o TotalSegmentator com tarefas **abertas** — e os limiares de HU clássicos.

**Onde mede.** O corte axial no meio craniocaudal da vértebra L3 (`vertebrae_L3`, tarefa `total`).
A série tem de ser axial; se não for, a composição não sai (a esteatose sai assim mesmo).

**Como separa, no corte de L3** (Mitsiopoulos et al., 1998; o mesmo do Slice-O-Matic):

| compartimento | regra |
|---|---|
| corpo | > −500 HU, a maior região, sem buracos; a pele (3 mm de fora) não conta como músculo |
| músculo (SMA) | −29 a 150 HU, fora da cavidade abdominal (`trunk_cavities`), dos órgãos e da vértebra |
| gordura visceral (VAT) | −190 a −30 HU dentro da cavidade abdominal |
| gordura subcutânea (SAT) | −190 a −30 HU fora da cavidade, nas regiões de gordura que encostam na pele |
| gordura intermuscular (IMAT) | o resto da gordura fora da cavidade |

Saem as áreas (cm²), o HU médio do músculo (densidade muscular) e, com a altura do paciente, o índice
muscular (SMA/altura², cm²/m²); com o peso, o IMC. Altura, peso e sexo vêm do arquivo (PatientSize,
PatientWeight, PatientSex) e o médico confirma ou digita numa janela antes da conta, ou depois em
Achados de IA ▸ Altura e peso… (0.99.80, `ai/biometria.py`). A referência de sarcopenia vai como **texto ao
lado**, nunca como veredito: Prado et al., Lancet Oncol 2008 — índice < 52,4 cm²/m² (homens) e < 38,5
(mulheres), em pacientes com câncer de pulmão e TGI obesos; com o IMC, também Martin et al., J Clin Oncol 2013
(sarcopenia: < 43 cm²/m² em homens com IMC < 25, < 53 com IMC ≥ 25, < 41 em mulheres; mioesteatose:
densidade muscular < 41 HU com IMC < 25, < 33 HU com IMC ≥ 25).

**Esteatose.** Fígado e baço da tarefa `total`, erodidos 2 voxels (a borda tem volume parcial):
média e mediana do HU, fígado − baço e fígado / baço. Com contraste (ContrastBolusAgent ou a descrição)
os limiares de TC sem contraste não valem, e a tela diz. Referências, também como texto, na TC sem contraste
e 100% específicas para esteatose ≥ 30%: fígado − baço < −9 HU ou fígado / baço < 0,8 (Park et al., Radiology
2006;239:105) e fígado < 48 HU (Pickhardt et al., Eur Radiol 2012;22:1075). Desde a 0.99.80 sai também um
**resultado** em texto (`resultado_esteatose`): compatível com esteatose moderada a acentuada quando um
desses critérios bate; fígado menos denso que o baço (fígado / baço < 1,0) sem bater nenhum = esteatose
leve possível; senão, sem sinais de esteatose moderada ou acentuada (a TC não exclui a leve). Na série com
contraste, não classifica.

Saída: SEG "Composição corporal · TotalSegmentator" (série 982), com os compartimentos no corte de L3,
e dois **achados** (`ai/achados.py`) — "Composição corporal (L3)" e "Atenuação hepática" — que
se revisam e vão ao laudo como os outros.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "composicao"
TITULO = "Composição corporal em L3 e esteatose (IA)"
MARCA = "· TotalSegmentator"
DESC_SEG = f"Composição corporal {MARCA}"
SERIE_SEG = 982
MIN_CORTES = 30
MODALIDADES = ("CT",)
MOTIVO_MODALIDADE = "A composição corporal é medida na TC."
MODELO = "TotalSegmentator total + trunk_cavities, limiares de HU"
CHAVE_SAIDA = "composicao"
TIPO_L3 = "Composição corporal (L3)"
TIPO_FIGADO = "Atenuação hepática"

MUSCULO = (-29.0, 150.0)
GORDURA = (-190.0, -30.0)
PELE_MM = 3.0
EROSAO_ORGAO = 2

ORGAOS = ("liver", "spleen", "kidney_left", "kidney_right", "stomach", "pancreas", "duodenum", "small_bowel",
          "colon", "aorta", "inferior_vena_cava", "gallbladder", "urinary_bladder")
VERTEBRAS = ("vertebrae_L2", "vertebrae_L3", "vertebrae_L4")
CORES = {"musculo": (220, 80, 80), "vat": (250, 210, 70), "sat": (90, 200, 250), "imat": (190, 140, 230)}
NOMES = {"musculo": "Músculo esquelético (L3)", "vat": "Gordura visceral (L3)", "sat": "Gordura subcutânea (L3)",
         "imat": "Gordura intermuscular (L3)"}
_CONTRASTE = ("C/C", "COM CONTRASTE", "CONTRASTE", "PORTAL", "VENOSA", "VENOSO", "ARTERIAL", "NEFROGRAFICA",
              "EXCRETORA", "TARDIA", "C+", "POS CONTRASTE", "POS-CONTRASTE", "CONTRAST")

# Configurações ▸ CAD/IA ▸ Composição corporal
CHAVE_AUTO = "composicao.auto"
CHAVE_EXAME_CONTEM = "composicao.exame_contem"
CHAVE_MODALIDADES = "composicao.modalidades"
CHAVE_PRIOR_CT = "composicao.prioridade_ct"
CHAVE_ESPESSURA = "composicao.espessura_max"
CHAVE_MIN_CORTES = "composicao.min_cortes"
CHAVE_DESTINOS = "composicao.destinos"
#: pergunta altura e peso antes de calcular (Configurações ▸ CAD/IA ▸ Composição corporal)
CHAVE_PERGUNTAR = "composicao.perguntar_biometria"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "ABD|ABDOME|ABDOMEN|ABDOMINAL|LOMBAR|PELVE|TORAX E ABDOME|CORPO INTEIRO|ESTADIAMENTO",
    CHAVE_MODALIDADES: ["CT"],
    CHAVE_PRIOR_CT: "SEM CONTRASTE|S/C|PRE|SIMPLES|PORTAL|VENOSA|PARTES MOLES|STD|STANDARD|AX|AXIAL",
    CHAVE_ESPESSURA: 5.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
    CHAVE_PERGUNTAR: True,
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}
NOME_CADIA = "Composição corporal (L3)"
TITULO_CADIA = "Composição corporal em L3 e atenuação hepática na TC (TotalSegmentator + limiares de HU)"
EXPLICACAO_CADIA = ("Na TC de abdome: no corte axial do meio de L3 mede a área de músculo esquelético, de gordura "
                    "visceral, subcutânea e intermuscular e a densidade muscular; com a altura no arquivo, o índice "
                    "muscular. Mede também o HU do fígado e do baço (fígado − baço, fígado / baço). Os resultados "
                    "aparecem em Aplicações ▸ Achados de IA, para conferir antes do laudo.")
CHAVES_L3 = ("sma_cm2", "smi", "musculo_hu", "vat_cm2", "sat_cm2", "imat_cm2", "vat_sat", "imc", "altura_m",
             "peso_kg")
CHAVES_FIGADO = ("figado_hu", "baco_hu", "f_menos_b", "f_sobre_b", "resultado", "figado_mediana")
#: avisos que dependem de altura, peso e sexo: refeitos quando o médico troca esses valores
_AVISOS_BIOMETRIA = ("sem a altura", "sem o peso", "referência de sarcopenia", "referências de Martin")

# resultado da esteatose (0.99.80)
EST_SEM = "Sem sinais tomográficos de esteatose moderada ou acentuada (a TC não exclui esteatose leve)"
EST_LEVE = "Esteatose leve possível: fígado menos denso que o baço"
EST_MOD = "Compatível com esteatose moderada a acentuada (≥ 30%)"
EST_CONTRASTE = "Não classificado: série com contraste (os limiares valem na TC sem contraste)"


def resultado_esteatose(figado_hu, f_menos_b=None, f_sobre_b=None, contraste: bool = False) -> str | None:
    """O resultado em texto pelos critérios de Park (2006) e Pickhardt (2012). None sem o HU do fígado."""
    if figado_hu is None:
        return None
    if contraste:
        return EST_CONTRASTE
    fh = float(figado_hu)
    if fh < 48 or (f_menos_b is not None and float(f_menos_b) < -9) or \
            (f_sobre_b is not None and float(f_sobre_b) < 0.8):
        return EST_MOD
    if f_sobre_b is not None and float(f_sobre_b) < 1.0:
        return EST_LEVE
    return EST_SEM


def numeros_biometria(sma, musculo_hu, altura, peso, sexo) -> tuple[dict, list]:
    """Índice muscular, IMC, altura e peso (números do achado de L3) e os avisos com as referências."""
    from ipe.ai import biometria as B
    imc = B.imc(altura, peso)
    nums = {
        "smi": AC.numero(round(sma / altura ** 2, 1) if (altura and sma is not None) else None, "cm²/m²",
                         "Índice muscular (SMI)"),
        "imc": AC.numero(imc, "kg/m²", "IMC"),
        "altura_m": AC.numero(round(float(altura), 2) if altura else None, "m", "Altura"),
        "peso_kg": AC.numero(round(float(peso), 1) if peso else None, "kg", "Peso"),
    }
    avisos = []
    if not altura:
        avisos.append("sem a altura do paciente (no arquivo ou digitada): o índice muscular não sai")
    if not peso:
        avisos.append("sem o peso do paciente: o IMC e as referências de Martin (2013) não saem")
    ref = {"M": "< 52,4", "F": "< 38,5"}.get(sexo)
    if ref:
        avisos.append(f"referência de sarcopenia ({'homens' if sexo == 'M' else 'mulheres'}): índice "
                      f"{ref} cm²/m² (Prado et al., Lancet Oncol 2008) — texto de referência, não diagnóstico")
    if imc is not None:
        if sexo == "M":
            corte = "< 43" if imc < 25 else "< 53"
        elif sexo == "F":
            corte = "< 41"
        else:
            corte = ""
        dens = "< 41" if imc < 25 else "< 33"
        avisos.append("referências de Martin et al., J Clin Oncol 2013, para IMC "
                      + (f"{imc:.1f}".replace(".", ",")) + " kg/m²: "
                      + (f"sarcopenia com índice {corte} cm²/m²; " if corte else "")
                      + f"mioesteatose com densidade muscular {dens} HU — texto de referência, não diagnóstico")
    return nums, avisos


def atualizar_biometria(achado: dict, altura, peso, sexo) -> tuple[dict, str]:
    """Os números e a elegibilidade do achado de L3 refeitos com outra altura, peso ou sexo (sem rodar a IA)."""
    nums = dict(achado.get("numeros") or {})
    validos = AC.numeros_validos(achado)
    sma = (validos.get("sma_cm2") or {}).get("v")
    musc = (validos.get("musculo_hu") or {}).get("v")
    novos, avisos = numeros_biometria(sma, musc, altura, peso, sexo)
    nums.update(novos)
    eleg = achado.get("elegibilidade") or ""
    base, _sep, resto = eleg.partition(". Atenção: ")
    outros = [x for x in resto.split("; ") if x and not x.startswith(_AVISOS_BIOMETRIA)] if resto else []
    todos = outros + avisos
    return nums, base + (". Atenção: " + "; ".join(todos) if todos else "")
CHAVES = CHAVES_L3 + CHAVES_FIGADO


def config(settings, chave):
    if chave == CHAVE_MODALIDADES:
        return ["CT"]
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


def tarefas(modalidade: str = "CT", settings=None) -> list[dict]:
    return [
        {"nome": "total", "roi": list(VERTEBRAS) + list(ORGAOS), "fast": True,
         "rotulo": "vértebras lombares e órgãos", "composicao": True},
        {"nome": "trunk_cavities", "rotulo": "cavidade abdominal", "composicao": True},
    ]


# ------------------------------------------------------------------ 2D sem SciPy
def _dil2(m: np.ndarray, n: int) -> np.ndarray:
    m = m.copy()
    for _ in range(max(0, n)):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        m = d
    return m


def _ero2(m: np.ndarray, n: int) -> np.ndarray:
    return ~_dil2(~m, n)


def _ero3(m: np.ndarray, n: int) -> np.ndarray:
    m = m.copy()
    for _ in range(max(0, n)):
        e = m.copy()
        for ax in range(3):
            a = [slice(None)] * 3
            b = [slice(None)] * 3
            a[ax], b[ax] = slice(1, None), slice(None, -1)
            e[tuple(a)] &= m[tuple(b)]
            e[tuple(b)] &= m[tuple(a)]
            borda = [slice(None)] * 3
            borda[ax] = 0
            e[tuple(borda)] = False
            borda[ax] = -1
            e[tuple(borda)] = False
        m = e
    return m


def _maior(m: np.ndarray) -> np.ndarray:
    from ipe.imaging import estruturas as E
    rot, n = E.rotular(m)
    if n == 0:
        return m
    contagem = np.bincount(rot.ravel())
    contagem[0] = 0
    return rot == int(np.argmax(contagem))


# ------------------------------------------------------------------ a conta
@dataclass
class Resultado:
    k_l3: int | None = None                 # corte de L3 no volume (k)
    centro_l3: list | None = None
    l3: dict = field(default_factory=dict)  # chave -> número (AC.numero)
    figado: dict = field(default_factory=dict)
    figado_centro: list | None = None
    mascaras: dict = field(default_factory=dict)      # nome -> máscara 2D do corte de L3
    avisos_l3: list = field(default_factory=list)
    avisos_figado: list = field(default_factory=list)
    elegibilidade: str = ""
    contraste: bool = False
    versao: str = ""
    series_uid: str = ""


def _contraste(t) -> bool:
    desc = (t.descricao_serie or "").upper()
    try:
        import pydicom
        ds = pydicom.dcmread(t.frames[0].path, stop_before_pixels=True, force=True,
                             specific_tags=["ContrastBolusAgent", "SeriesDescription", "StudyDescription"])
        if str(ds.get("ContrastBolusAgent", "") or "").strip():
            return True
        desc += " " + str(ds.get("SeriesDescription", "") or "").upper()
    except Exception:  # noqa: BLE001
        pass
    from ipe.ai.totalseg import _sem_acento
    d = _sem_acento(desc)
    if "SEM CONTRASTE" in d or "S/C" in d or " PRE" in f" {d}":
        return False
    return any(p in d for p in _CONTRASTE)


def _biometria(t) -> dict:
    """Altura, peso e sexo: o digitado pelo médico neste exame por cima do arquivo (0.99.80)."""
    from ipe.ai import biometria as B
    path = t.frames[0].path if getattr(t, "frames", None) else None
    return B.ler(getattr(t, "repo", None), getattr(t, "study_uid", ""), path)


def _altura_sexo(t) -> tuple[float | None, str]:
    b = _biometria(t)
    return b.get("altura_m"), b.get("sexo") or ""


def _peso(t) -> float | None:
    return _biometria(t).get("peso_kg")


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import cefalometria as CF
    from ipe.imaging import estruturas as E
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    ms = CF.Mascaras(vol, rotulos)
    res.contraste = _contraste(t)
    passo = float(vol.dz)
    res.elegibilidade = (f"TC, série “{t.descricao_serie or t.series_uid[-8:]}”, {vol.data.shape[0]} cortes, "
                         f"pixel {vol.dy:.2f} × {vol.dx:.2f} mm, intervalo {passo:.2f} mm"
                         + (", com contraste" if res.contraste else ", sem contraste"))
    dados = vol.data
    area_px = float(vol.dx * vol.dy) / 100.0       # cm²
    # ---------------- L3
    l3 = ms.get("vertebrae_L3")
    normal = np.asarray(vol.slice_vec, float)
    axial = abs(normal[2]) / max(float(np.linalg.norm(normal)), 1e-9) > 0.95
    if l3 is None:
        res.avisos_l3.append("a IA não achou a vértebra L3 nesta série")
    elif not axial:
        res.avisos_l3.append("a série não é axial: a área em L3 se mede num corte axial")
    else:
        ks = np.nonzero(l3.any(axis=(1, 2)))[0]
        k = int(round((ks[0] + ks[-1]) / 2))
        res.k_l3 = k
        hu = np.asarray(dados[k], float)
        corpo = _maior(hu > -500)
        corpo = E._sem_buracos(corpo)
        pele = corpo & ~_ero2(corpo, max(1, int(round(PELE_MM / max(vol.dx, 1e-3)))))
        cav = ms.get("abdominal_cavity")
        cav2 = cav[k] if cav is not None else np.zeros(hu.shape, bool)
        if cav is None or not cav2.any():
            res.avisos_l3.append("a IA não achou a cavidade abdominal: a gordura visceral não foi separada")
        orgaos = np.zeros(hu.shape, bool)
        for nome in ORGAOS:
            m = ms.get(nome)
            if m is not None:
                orgaos |= m[k]
        vert = _dil2(l3[k], 1)
        for nome in VERTEBRAS:
            m = ms.get(nome)
            if m is not None:
                vert |= _dil2(m[k], 1)
        dentro = cav2 | orgaos
        gordura = corpo & (hu >= GORDURA[0]) & (hu <= GORDURA[1])
        musculo = corpo & (hu >= MUSCULO[0]) & (hu <= MUSCULO[1]) & ~dentro & ~pele & ~vert
        vat = gordura & cav2
        fora = gordura & ~dentro
        rot, n = E.rotular(fora)
        toca = np.unique(rot[_dil2(pele, 1) & fora])
        sat = np.isin(rot, toca[toca > 0])
        imat = fora & ~sat
        res.mascaras = {"musculo": musculo, "vat": vat, "sat": sat, "imat": imat}
        sma = float(musculo.sum()) * area_px
        altura, sexo = _altura_sexo(t)
        peso = _peso(t)
        musc_hu = round(float(hu[musculo].mean()), 0) if musculo.any() else None
        nums_bio, avisos_bio = numeros_biometria(round(sma, 1), musc_hu, altura, peso, sexo)
        res.centro_l3 = [float(x) for x in CF.pontos(vol, l3[k:k + 1], (k, 0, 0)).mean(axis=0)]
        res.l3 = {
            "sma_cm2": AC.numero(round(sma, 1), "cm²", "Área muscular (SMA)"),
            "smi": nums_bio["smi"],
            "musculo_hu": AC.numero(musc_hu, "HU", "Densidade muscular"),
            "vat_cm2": AC.numero(round(float(vat.sum()) * area_px, 1), "cm²", "Gordura visceral (VAT)"),
            "sat_cm2": AC.numero(round(float(sat.sum()) * area_px, 1), "cm²", "Gordura subcutânea (SAT)"),
            "imat_cm2": AC.numero(round(float(imat.sum()) * area_px, 1), "cm²", "Gordura intermuscular (IMAT)"),
            "vat_sat": AC.numero(round(float(vat.sum()) / float(sat.sum()), 2) if sat.any() else None, "",
                                 "VAT / SAT"),
            "imc": nums_bio["imc"], "altura_m": nums_bio["altura_m"], "peso_kg": nums_bio["peso_kg"],
        }
        res.avisos_l3 += avisos_bio
        if passo > 5.0:
            res.avisos_l3.append(f"cortes de {passo:.1f} mm: o corte de L3 pode cair fora do meio da vértebra")
    # ---------------- fígado e baço
    fig, baco = ms.get("liver"), ms.get("spleen")
    if fig is None:
        res.avisos_figado.append("a IA não achou o fígado nesta série")
    else:
        fe = _ero3(fig, EROSAO_ORGAO)
        fe = fe if fe.sum() > 50 else fig
        vf = np.asarray(dados[fe], float)
        kk, jj, ii = np.argwhere(fe).mean(axis=0)
        res.figado_centro = [float(x) for x in vol.voxel_to_patient(ii, jj, kk)]
        res.figado = {"figado_hu": AC.numero(round(float(vf.mean()), 1), "HU", "Fígado (média)"),
                      "figado_mediana": AC.numero(round(float(np.median(vf)), 1), "HU", "Fígado (mediana)")}
        if baco is not None:
            be = _ero3(baco, EROSAO_ORGAO)
            be = be if be.sum() > 30 else baco
            vb = np.asarray(dados[be], float)
            mb = float(vb.mean())
            res.figado["baco_hu"] = AC.numero(round(mb, 1), "HU", "Baço (média)")
            res.figado["f_menos_b"] = AC.numero(round(float(vf.mean()) - mb, 1), "HU", "Fígado − baço")
            res.figado["f_sobre_b"] = AC.numero(round(float(vf.mean()) / mb, 2) if abs(mb) > 1 else None, "",
                                                "Fígado / baço")
        else:
            res.avisos_figado.append("a IA não achou o baço: sem a comparação fígado − baço")
        txt = resultado_esteatose(res.figado["figado_hu"]["v"], (res.figado.get("f_menos_b") or {}).get("v"),
                                  (res.figado.get("f_sobre_b") or {}).get("v"), res.contraste)
        res.figado["resultado"] = AC.numero(txt, "", "Resultado")
        if res.contraste:
            res.avisos_figado.append("série com contraste: os limiares de esteatose da TC sem contraste não valem")
        else:
            res.avisos_figado.append("referências na TC sem contraste, 100% específicas para esteatose de 30% ou "
                                     "mais: fígado − baço < −9 HU ou fígado / baço < 0,8 (Park et al., Radiology "
                                     "2006) e fígado < 48 HU (Pickhardt et al., Eur Radiol 2012) — texto de "
                                     "referência, não diagnóstico")
    return res


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    out = []
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao}
    if res.l3:
        out.append({**base, "rotulo": "L3", "tipo": TIPO_L3, "local": "corte axial do meio de L3",
                    "posicao": res.centro_l3, "numeros": res.l3,
                    "elegibilidade": res.elegibilidade + (". Atenção: " + "; ".join(res.avisos_l3)
                                                          if res.avisos_l3 else "")})
    if res.figado:
        out.append({**base, "rotulo": "F", "tipo": TIPO_FIGADO, "local": "fígado e baço",
                    "posicao": res.figado_centro, "numeros": res.figado,
                    "elegibilidade": res.elegibilidade + (". Atenção: " + "; ".join(res.avisos_figado)
                                                          if res.avisos_figado else "")})
    return out


def gravar(t, res: Resultado, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    import shutil
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

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
                log.exception("trocar a SEG de composição anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    segs = []
    if res.k_l3 is not None:
        for nome, m2 in res.mascaras.items():
            if m2.any():
                m3 = m2[None, :, :]
                segs.append((SimpleNamespace(mask=m3, offset=(res.k_l3, 0, 0)), NOMES[nome], CORES[nome]))
    if segs:
        vol = t.vol
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"TotalSegmentator {versao} + limiares de HU".strip()),
                       anatomia=True)
        tmp = Path(tempfile.mkdtemp(prefix="dv_comp_"))
        try:
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
            out["series"] += sorted(getattr(r, "new_series", None) or [])
            out["seg_sop"] = str(ds.SOPInstanceUID)
            out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    # um resultado novo troca o sugerido; o que o médico já conferiu fica, e o novo entra ao lado
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens_para_o_banco(res, t, versao))
    return out


def resumo(res: Resultado) -> str:
    partes = []
    if res.l3:
        partes.append(f"L3: músculo {AC._fmt(res.l3['sma_cm2'])}, VAT {AC._fmt(res.l3['vat_cm2'])}, "
                      f"SAT {AC._fmt(res.l3['sat_cm2'])}")
    elif res.avisos_l3:
        partes.append(f"L3: {res.avisos_l3[0]}")
    if res.figado:
        partes.append(f"fígado {AC._fmt(res.figado['figado_hu'])}"
                      + (f", fígado − baço {AC._fmt(res.figado['f_menos_b'])}" if "f_menos_b" in res.figado else ""))
    return "; ".join(partes) or "nada medido"


def n_itens(res: Resultado) -> int:
    return int(bool(res.l3)) + int(bool(res.figado))


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Composição corporal pronta em {minutos:.1f} min — {resumo(res)}. Os números estão em Aplicações ▸ "
           "Achados de IA, para conferir antes do laudo; os compartimentos do corte de L3 estão na série "
           f"“{DESC_SEG}”.")
    avisos = res.avisos_l3 + res.avisos_figado
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else f"{float(x):.{casas}f}".replace(".", ",")
    if a.get("tipo") == TIPO_L3:
        txt = f"Composição corporal em L3: área muscular de {v('sma_cm2')} cm²"
        if v("smi"):
            txt += f" (índice muscular {v('smi')} cm²/m²)"
        if v("musculo_hu", 0):
            txt += f", densidade muscular média de {v('musculo_hu', 0)} HU"
        txt += f"; gordura visceral {v('vat_cm2')} cm² e subcutânea {v('sat_cm2')} cm²."
        return txt
    txt = f"Atenuação hepática média de {v('figado_hu', 0)} HU"
    if v("baco_hu", 0):
        txt += f", esplênica de {v('baco_hu', 0)} HU (fígado − baço {v('f_menos_b', 0)} HU)"
    txt += "."
    resultado = resultado_do_achado(a)
    if resultado:
        txt += f" {resultado}."
    return txt


def resultado_do_achado(a: dict) -> str | None:
    """O resultado da esteatose: o que o médico escreveu, ou refeito pelos números que valem (corrigidos)."""
    if "resultado" in (a.get("corrigidos") or {}):
        return str(a["corrigidos"]["resultado"] or "").strip() or None
    if "resultado" not in (a.get("numeros") or {}):
        return None                     # achados de antes da 0.99.80
    n = AC.numeros_validos(a)
    contraste = (a.get("numeros") or {}).get("resultado", {}).get("v") == EST_CONTRASTE

    def g(k):
        return (n.get(k) or {}).get("v")
    return resultado_esteatose(g("figado_hu"), g("f_menos_b"), g("f_sobre_b"), contraste)
