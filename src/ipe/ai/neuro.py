"""Índices automáticos do crânio com o SynthSeg (0.99.17, etapa 1c da neuro).

O SynthSeg (Billot et al., 2023; Apache-2.0) segmenta o encéfalo em RM de **qualquer contraste e
resolução** e também em TC — inclusive o T1 pós-contraste e os 2D de 5 mm dos protocolos de
Parkinson. Roda no ambiente da segmentação, pela versão em PyTorch da DIPY (BSD-3): sem TensorFlow.

| medida | de onde sai |
|---|---|
| índice de Evans | maior largura dos cornos frontais (ventrículos laterais à frente do 3º ventrículo) ÷ maior diâmetro intracraniano no **mesmo axial** |
| 3º ventrículo | largura transversal máxima a 25%, 50% e 75% do comprimento dele; vale a média (como no MRPI 2.0) |
| ângulo calosal | no coronal da extremidade posterior do 3º ventrículo (comissura posterior): retas pelas paredes súpero-mediais dos ventrículos laterais |
| volumes | hipocampos, amígdalas, ventrículos e volume intracraniano estimado (tudo que o SynthSeg rotula) |

O diâmetro "interno do crânio" sai do contorno do líquor externo do SynthSeg, que encosta na tábua
interna; os planos são os da aquisição (o axial do aparelho, não o AC-PC) — a tela diz isso.
Tudo é proposta: a janela de conferência mostra as linhas em qualquer plano e deixa trocar à mão.
"""
from __future__ import annotations

import logging

import numpy as np

from ipe.ai import cefalometria as CF
from ipe.ai.cefalometria import Cefalometria as Resultado
from ipe.ai.cefalometria import Medida, pontos

log = logging.getLogger(__name__)

MARCA = "· SynthSeg"
DESC_SEG = f"Encéfalo {MARCA}"
DESC_IMAGEM = f"Índices do crânio: conferência {MARCA}"
SERIE_SEG, SERIE_IMAGEM = 978, 979
MIN_CORTES = 15
TITULO = "Índices do crânio"
FONTE_OVERLAY = "Índices do crânio"
GRUPO_PRIVADO, CRIADOR = 0x0071, "IPE NEURO"

#: rótulos do SynthSeg (FreeSurfer) usados aqui
VL_E, VL_D, VLI_E, VLI_D = 4, 43, 5, 44
V3, V4 = 14, 15
HIPO_E, HIPO_D, AMIG_E, AMIG_D = 17, 53, 18, 54
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
#: o que vai para a SEG (para ver e conferir), com nome e cor
ESTRUTURAS = {
    4: ("Ventrículo lateral E", (80, 170, 255)), 43: ("Ventrículo lateral D", (80, 170, 255)),
    5: ("Corno temporal E", (110, 190, 255)), 44: ("Corno temporal D", (110, 190, 255)),
    14: ("3º ventrículo", (60, 220, 230)), 15: ("4º ventrículo", (60, 200, 200)),
    17: ("Hipocampo E", (255, 200, 60)), 53: ("Hipocampo D", (255, 200, 60)),
    18: ("Amígdala E", (240, 130, 90)), 54: ("Amígdala D", (240, 130, 90)),
    16: ("Tronco encefálico", (180, 140, 220)),
}

ORDEM = ("evans", "cornos", "cranio", "v3", "calosal", "hipo_d", "hipo_e", "hipo_assim", "amig_d", "amig_e",
         "vent_lat", "v3_vol", "v4_vol", "vic")
NUMERO = {"evans": "1", "cornos": "1", "cranio": "1", "v3": "2", "calosal": "3", "hipo_d": "4", "hipo_e": "4",
          "hipo_assim": "4", "amig_d": "5", "amig_e": "5", "vent_lat": "6", "v3_vol": "6", "v4_vol": "6", "vic": "7"}
NOMES = {
    "evans": "Índice de Evans",
    "cornos": "Largura dos cornos frontais",
    "cranio": "Diâmetro interno do crânio (mesmo axial)",
    "v3": "Largura do 3º ventrículo (média de três)",
    "calosal": "Ângulo calosal",
    "hipo_d": "Volume do hipocampo direito",
    "hipo_e": "Volume do hipocampo esquerdo",
    "hipo_assim": "Assimetria dos hipocampos",
    "amig_d": "Volume da amígdala direita",
    "amig_e": "Volume da amígdala esquerda",
    "vent_lat": "Volume dos ventrículos laterais",
    "v3_vol": "Volume do 3º ventrículo",
    "v4_vol": "Volume do 4º ventrículo",
    "vic": "Volume intracraniano estimado",
}
UNIDADE = {"evans": "", "cornos": "mm", "cranio": "mm", "v3": "mm", "calosal": "°", "hipo_assim": "%"}
CASAS = {"evans": 2, "calosal": 0, "hipo_assim": 0, "vic": 0}
DERIVADAS = ("evans", "hipo_assim")
CHAVE_REFERENCIAS = "neuro.referencias"
REFERENCIAS = {
    "evans": "acima de 0,30 indica ventriculomegalia",
    "v3": "",
    "calosal": "abaixo de 90° favorece hidrocefalia de pressão normal",
}
for _k in ORDEM:
    REFERENCIAS.setdefault(_k, "")
CORES = {"evans": (255, 220, 70), "cornos": (255, 220, 70), "cranio": (120, 200, 255), "v3": (60, 220, 230),
         "calosal": (255, 120, 170)}
#: medir à mão: régua para larguras, ângulo para o calosal; volumes só digitando
FERRAMENTA = {"cornos": "measure", "cranio": "measure", "v3": "measure", "calosal": "angle"}
INSTRUCAO = {
    "evans": "Calculado: cornos frontais ÷ diâmetro interno do crânio. Troque uma das duas medidas para refazer.",
    "cornos": "No axial, a maior largura entre as paredes laterais dos cornos frontais.",
    "cranio": "No mesmo axial dos cornos, o maior diâmetro interno do crânio (tábua interna a tábua interna).",
    "v3": "No axial (plano AC-PC), a largura do 3º ventrículo; a automática é a média de três pontos.",
    "calosal": "No coronal perpendicular ao AC-PC, na comissura posterior: ângulo entre as paredes mediais "
               "dos ventrículos laterais, com o vértice no meio, abaixo do corpo caloso.",
    "hipo_d": "Volume do SynthSeg. Para trocar, digite o valor (mL).",
    "hipo_e": "Volume do SynthSeg. Para trocar, digite o valor (mL).",
    "hipo_assim": "Calculado: |D − E| ÷ média dos dois.",
}

# Preferências ▸ CAD/IA ▸ Índices do crânio (automático na chegada)
CHAVE_AUTO = "neuro.auto"
CHAVE_EXAME_CONTEM = "neuro.exame_contem"
CHAVE_MODALIDADES = "neuro.modalidades"
CHAVE_PRIOR_CT = "neuro.prioridade_ct"
CHAVE_PRIOR_MR = "neuro.prioridade_mr"
CHAVE_ESPESSURA = "neuro.espessura_max"
CHAVE_MIN_CORTES = "neuro.min_cortes"
CHAVE_DESTINOS = "neuro.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "CRANIO|ENCEFALO|CEREBRO|HEAD|BRAIN|PARKINSON|HIDROCEFALIA|DEMENCIA|HIPOCAMPO",
    CHAVE_MODALIDADES: ["MR", "CT"],
    CHAVE_PRIOR_CT: "PARTES MOLES|CEREBRO|BRAIN|STD|AX",
    CHAVE_PRIOR_MR: "3D T1|T1 3D|FSPGR|MPRAGE|BRAVO|TFE|3D|T1|FLAIR|T2",
    CHAVE_ESPESSURA: 0.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_MR, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}


def config(settings, chave):
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
    return TS.ja_segmentado(repo, study_uid, DESC_IMAGEM)


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    return [{"nome": "synthseg", "rotulo": "encéfalo (SynthSeg)", "neuro": True}]


def referencias(settings=None) -> dict:
    r = dict(REFERENCIAS)
    try:
        extra = settings.get(CHAVE_REFERENCIAS, None) if settings is not None else None
    except Exception:  # noqa: BLE001
        extra = None
    if isinstance(extra, dict):
        r.update({k: str(v) for k, v in extra.items() if k in r})
    return r


def vazio() -> Resultado:
    res = Resultado()
    for k in ORDEM:
        res.medidas[k] = Medida(k, NOMES[k], unidade=UNIDADE.get(k, "mL"), casas=CASAS.get(k, 2 if k not in UNIDADE
                                                                                         else 1), origem="")
    return res


# ------------------------------------------------------------------ a conta
def _lab(rotulos: dict, shape) -> np.ndarray | None:
    for _t, (lab, classes) in (rotulos or {}).items():
        if lab.shape != shape:
            raise ValueError(f"grade {lab.shape} diferente do volume {shape}")
        if any("ventricle" in str(v) for v in classes.values()):
            return lab
    return None


def _ml(vol, n: int) -> float:
    return n * vol.dx * vol.dy * vol.dz / 1000.0


def _h(vol) -> float:
    return float(min(vol.dx, vol.dy))


def calcular(vol, rotulos: dict, settings=None) -> Resultado:
    res = vazio()
    for m in res.medidas.values():
        m.origem = "automático"
    lab = _lab(rotulos, vol.data.shape)
    if lab is None:
        res.avisos.append("o SynthSeg não devolveu a segmentação do encéfalo")
        for m in res.medidas.values():
            m.motivo = "sem segmentação"
        return res
    h = _h(vol)
    contagem = np.bincount(lab.ravel(), minlength=256)
    vol_ml = {k: _ml(vol, int(contagem[k])) for k in range(256)}

    # --- volumes ---------------------------------------------------------------------------
    for k, ids in (("hipo_d", (HIPO_D,)), ("hipo_e", (HIPO_E,)), ("amig_d", (AMIG_D,)), ("amig_e", (AMIG_E,)),
                   ("vent_lat", (VL_E, VL_D, VLI_E, VLI_D)), ("v3_vol", (V3,)), ("v4_vol", (V4,))):
        v = sum(vol_ml[i] for i in ids)
        if v > 0:
            res.medidas[k].valor = v
        else:
            res.medidas[k].motivo = "estrutura não segmentada"
    vic = sum(vol_ml[i] for i in range(1, 256))
    res.medidas["vic"].valor = vic if vic > 0 else None

    p3 = pontos(vol, lab == V3)
    pv = pontos(vol, (lab == VL_E) | (lab == VL_D))
    xm = float(np.median(p3[:, 0])) if len(p3) else (float(np.median(pv[:, 0])) if len(pv) else None)
    res.x_meio = xm

    # --- Evans: cornos frontais e diâmetro intracraniano no mesmo axial ------------------------
    mc, mk = res.medidas["cornos"], res.medidas["cranio"]
    if len(pv) < 20 or not len(p3):
        mc.motivo = mk.motivo = "ventrículos laterais ou 3º ventrículo não segmentados"
    else:
        y_monro = float(p3[:, 1].min())                     # extremidade anterior do 3º ventrículo
        fr = pv[pv[:, 1] <= y_monro]
        # só tiras com os dois lados (corno direito e esquerdo)
        melhor, onde = 0.0, None
        for z in np.arange(fr[:, 2].min(), fr[:, 2].max() + 1e-6, 1.0) if len(fr) else []:
            sz = np.abs(fr[:, 2] - z) <= 0.5
            q = fr[sz]
            for y in np.arange(q[:, 1].min(), q[:, 1].max() + 1e-6, 1.0) if len(q) else []:
                s2 = np.abs(q[:, 1] - y) <= 0.5
                xs = q[s2, 0]
                if not len(xs) or xs.min() > xm or xs.max() < xm:
                    continue
                larg = float(xs.max() - xs.min()) + h
                if larg > melhor:
                    melhor, onde = larg, (np.array([xs.min(), y, z]), np.array([xs.max(), y, z]))
        if onde is None:
            mc.motivo = mk.motivo = "não achei os dois cornos frontais no mesmo corte"
        else:
            mc.valor, mc.linhas = melhor, [onde]
            z = float(onde[0][2])
            pic = _pontos_intracranianos_na_altura(vol, lab, z)
            if len(pic) < 20:
                mk.motivo = "o encéfalo não aparece inteiro neste axial"
            else:
                larg, extremos = 0.0, None
                for y in np.arange(pic[:, 1].min(), pic[:, 1].max() + 1e-6, 1.0):
                    s2 = np.abs(pic[:, 1] - y) <= 0.5
                    xs = pic[s2, 0]
                    if len(xs) < 2:
                        continue
                    lw = float(xs.max() - xs.min()) + h
                    if lw > larg:
                        larg, extremos = lw, (np.array([xs.min(), y, z]), np.array([xs.max(), y, z]))
                mk.valor, mk.linhas = larg, [extremos]

    # --- 3º ventrículo: média de três larguras ----------------------------------------------------
    m3 = res.medidas["v3"]
    if len(p3) < 10:
        m3.motivo = "3º ventrículo não segmentado"
    else:
        y0, y1 = float(p3[:, 1].min()), float(p3[:, 1].max())
        larguras, linhas = [], []
        for f in (0.25, 0.5, 0.75):
            yc = y0 + f * (y1 - y0)
            q = p3[np.abs(p3[:, 1] - yc) <= 0.75]
            melhor, onde = 0.0, None
            for z in np.arange(q[:, 2].min(), q[:, 2].max() + 1e-6, 1.0) if len(q) else []:
                xs = q[np.abs(q[:, 2] - z) <= 0.5, 0]
                if not len(xs):
                    continue
                lw = float(xs.max() - xs.min()) + h
                if lw > melhor:
                    melhor, onde = lw, (np.array([xs.min(), yc, z]), np.array([xs.max(), yc, z]))
            if onde is not None:
                larguras.append(melhor)
                linhas.append(onde)
        if larguras:
            m3.valor, m3.linhas = float(np.mean(larguras)), linhas
            m3.texto = " / ".join(f"{x:.1f}".replace(".", ",") for x in larguras) + " mm"
        else:
            m3.motivo = "3º ventrículo fino demais para medir"

    # --- ângulo calosal --------------------------------------------------------------------------
    ma = res.medidas["calosal"]
    if len(pv) < 20 or not len(p3):
        ma.motivo = "ventrículos laterais ou 3º ventrículo não segmentados"
    else:
        y_cp = float(p3[:, 1].max())                       # extremidade posterior: comissura posterior
        r = angulo_calosal(pv, y_cp, xm)
        if r is None:
            ma.motivo = "os ventrículos não aparecem dos dois lados no coronal da comissura posterior"
        else:
            ma.valor, ma.linhas = r
    if res.medidas["calosal"].valor is not None or res.medidas["cornos"].valor is not None:
        res.avisos.append("planos da aquisição (não reorientados ao AC-PC): confira nos planos certos se "
                          "a cabeça estiver inclinada")
    recalcular(res)
    for k in DERIVADAS:
        res.medidas[k].origem = "automático"
    for cid in ESTRUTURAS:
        if contagem[cid]:
            m = lab == cid
            fat, off = CF._recorte(m)
            res.estruturas[cid] = (m[fat], off)
    return res


def _pontos_intracranianos_na_altura(vol, lab: np.ndarray, z: float) -> np.ndarray:
    """Pontos (mm) de tudo o que o SynthSeg rotula (encéfalo + líquor) a até meio corte da altura z."""
    M = np.asarray(vol.matrix(), float)
    o = np.asarray(vol.origin, float)
    eixo = int(np.argmax(np.abs(M[2, :])))                 # 0 = i, 1 = j, 2 = k: o mais perto do z
    nk, nj, ni = lab.shape
    passo = float(M[2, eixo])
    n = (ni, nj, nk)[eixo]
    centro = int(round((z - o[2]) / passo)) if abs(passo) > 1e-6 else 0
    tol = max(0.5, abs(passo) / 2 + 0.01)
    pts = []
    for k in (centro - 1, centro, centro + 1):
        if not 0 <= k < n:
            continue
        if eixo == 2:
            jj, ii = np.nonzero(lab[k] > 0)
            ijk = np.stack([ii, jj, np.full_like(ii, k)])
        elif eixo == 1:
            kk, ii = np.nonzero(lab[:, k, :] > 0)
            ijk = np.stack([ii, np.full_like(ii, k), kk])
        else:
            kk, jj = np.nonzero(lab[:, :, k] > 0)
            ijk = np.stack([np.full_like(jj, k), jj, kk])
        p = (o[:, None] + M @ ijk.astype(float)).T
        pts.append(p[np.abs(p[:, 2] - z) <= tol])
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def angulo_calosal(pv: np.ndarray, y_cp: float, xm: float, meia: float = 1.0):
    """(ângulo em graus, [linha esquerda, linha direita]) no coronal y = y_cp, ou None.

    Em cada ventrículo, na metade de cima do corte, a parede medial (o x mais perto do meio em cada
    altura); uma reta por esses pontos; o ângulo entre as duas retas, abrindo para baixo."""
    c = pv[np.abs(pv[:, 1] - y_cp) <= meia]
    lados = []
    for sinal in (+1, -1):                                 # +x: esquerda do paciente (LPS)
        q = c[(c[:, 0] - xm) * sinal > 0]
        if len(q) < 6:
            return None
        zmed = float(np.median(q[:, 2]))
        topo = float(q[:, 2].max())
        pts = []
        for z in np.arange(zmed, topo + 1e-6, 1.0):
            s = q[np.abs(q[:, 2] - z) <= 0.5]
            if len(s):
                i = int(np.argmin(np.abs(s[:, 0] - xm)))
                pts.append((s[i, 0], z))
        if len(pts) < 3:
            return None
        pts = np.array(pts)
        a, b = np.polyfit(pts[:, 1], pts[:, 0], 1)          # x = a·z + b
        lados.append((a, b, topo, float(pts[:, 1].min())))
    (aE, bE, tE, lE), (aD, bD, tD, lD) = lados
    vE = np.array([-aE, -1.0])                             # descendo pela parede: Δz = −1
    vD = np.array([-aD, -1.0])
    cosang = float(vE @ vD / (np.linalg.norm(vE) * np.linalg.norm(vD)))
    ang = float(np.degrees(np.arccos(np.clip(cosang, -1, 1))))
    linhas = []
    for a, b, topo, baixo in ((aE, bE, tE, lE), (aD, bD, tD, lD)):
        z0, z1 = topo, topo - 25.0
        linhas.append((np.array([a * z0 + b, y_cp, z0]), np.array([a * z1 + b, y_cp, z1])))
    return ang, linhas


def recalcular(res: Resultado) -> None:
    """As medidas que saem de outras: Evans (cornos ÷ crânio) e a assimetria dos hipocampos."""
    m = res.medidas
    c, k = m["cornos"].valor, m["cranio"].valor
    ev = m["evans"]
    if c is not None and k:
        ev.valor, ev.motivo = c / k, ""
        if "editado" in (m["cornos"].origem, m["cranio"].origem):
            ev.origem = "calculado"
    else:
        ev.valor = None
        ev.motivo = ev.motivo or "faltam os cornos ou o diâmetro do crânio"
    d, e = m["hipo_d"].valor, m["hipo_e"].valor
    a = m["hipo_assim"]
    if d and e:
        a.valor, a.motivo = abs(d - e) / ((d + e) / 2) * 100.0, ""
        if "editado" in (m["hipo_d"].origem, m["hipo_e"].origem):
            a.origem = "calculado"
    else:
        a.valor = None
        a.motivo = a.motivo or "faltam os dois hipocampos"


# ------------------------------------------------------------------ texto
def _ref(refs: dict, k: str) -> str:
    r = refs.get(k, "")
    return f" (referência: {r})" if r else ""


def _v(m: Medida) -> str:
    return m.texto_valor()


def texto_do_laudo(res: Resultado, settings=None, automatica: bool = True, modalidade: str = "") -> str:
    refs = referencias(settings)
    modalidade = modalidade or res.modalidade
    m = res.medidas
    mod = {"MR": "RM", "CT": "TC"}.get(modalidade, "")
    cab = f"Índices do crânio{(' por ' + mod) if mod else ''}" + (" (segmentação automática SynthSeg):" if automatica
                                                                   else ":")
    linhas = [cab]
    if m["evans"].valor is not None:
        linhas.append(f"- Índice de Evans: {_v(m['evans'])} (cornos frontais {_v(m['cornos'])}; diâmetro interno "
                      f"do crânio {_v(m['cranio'])}){_ref(refs, 'evans')}.")
    if m["v3"].valor is not None:
        linhas.append(f"- Largura do 3º ventrículo: {_v(m['v3'])} (média de três medidas){_ref(refs, 'v3')}.")
    if m["calosal"].valor is not None:
        linhas.append(f"- Ângulo calosal: {_v(m['calosal'])}{_ref(refs, 'calosal')}.")
    if m["hipo_d"].valor is not None and m["hipo_e"].valor is not None:
        extra = f" (assimetria {_v(m['hipo_assim'])})" if m["hipo_assim"].valor is not None else ""
        linhas.append(f"- Volume dos hipocampos: direito {_v(m['hipo_d'])}; esquerdo {_v(m['hipo_e'])}{extra}"
                      f"{_ref(refs, 'hipo_d')}.")
    if m["amig_d"].valor is not None and m["amig_e"].valor is not None:
        linhas.append(f"- Volume das amígdalas: direita {_v(m['amig_d'])}; esquerda {_v(m['amig_e'])}"
                      f"{_ref(refs, 'amig_d')}.")
    partes = [f"{n} {_v(m[k])}" for k, n in (("vent_lat", "laterais"), ("v3_vol", "3º"), ("v4_vol", "4º"))
              if m[k].valor is not None]
    if partes:
        linhas.append("- Volume dos ventrículos: " + "; ".join(partes) + f"{_ref(refs, 'vent_lat')}.")
    if m["vic"].valor is not None:
        linhas.append(f"- Volume intracraniano estimado: {_v(m['vic'])}{_ref(refs, 'vic')}.")
    editadas = [x.nome.lower() for x in m.values() if x.origem == "editado"]
    if editadas and automatica:
        linhas.append("Medidas conferidas e corrigidas à mão: " + ", ".join(editadas) + ".")
    return "\n".join(linhas)


def resumo(res: Resultado) -> str:
    m = res.medidas
    partes = []
    if m["evans"].valor is not None:
        partes.append(f"Evans {_v(m['evans'])}")
    if m["calosal"].valor is not None:
        partes.append(f"ângulo calosal {_v(m['calosal'])}")
    if m["hipo_d"].valor is not None and m["hipo_e"].valor is not None:
        partes.append(f"hipocampos {_v(m['hipo_d'])} / {_v(m['hipo_e'])}")
    return "; ".join(partes) or "nenhuma medida saiu"


# ------------------------------------------------------------------ guardar e ler
def para_json(res: Resultado) -> str:
    return CF.para_json(res)


def de_json(texto: str) -> Resultado:
    import json
    d = json.loads(texto)
    res = vazio()
    res.x_meio, res.avisos = d.get("x_meio"), list(d.get("avisos") or [])
    res.modalidade = d.get("modalidade") or ""
    for mm in d.get("medidas") or []:
        if mm.get("id") in res.medidas:
            alvo = res.medidas[mm["id"]]
            alvo.valor = None if mm.get("valor") is None else float(mm["valor"])
            alvo.texto, alvo.motivo = mm.get("texto") or "", mm.get("motivo") or ""
            alvo.origem = mm.get("origem") or "automático"
            alvo.linhas = [(np.asarray(a, float), np.asarray(b, float)) for a, b in (mm.get("linhas") or [])]
    return res


def ler_do_exame(repo, study_uid: str) -> Resultado | None:
    import pydicom
    try:
        series = [s for s in repo.series_for_study(study_uid) if (s.description or "") == DESC_IMAGEM]
    except Exception:  # noqa: BLE001
        return None
    for s in reversed(series):
        for inst in repo.instances_for_series(s.series_uid):
            try:
                ds = pydicom.dcmread(inst["path"], stop_before_pixels=True, force=True)
                return de_json(str(ds.private_block(GRUPO_PRIVADO, CRIADOR)[0x01].value))
            except Exception:  # noqa: BLE001
                continue
    return None


def rotulo_da_linha(m: Medida) -> str:
    return f"{NUMERO.get(m.id, '')}: {m.texto_valor()}"


def objeto_de_linhas(res: Resultado, study_uid: str = ""):
    from ipe.imaging import overlays as O
    obj = O.OverlayObject(f"neuro:{study_uid}", FONTE_OVERLAY, "linhas das medidas", (255, 220, 70),
                          study_uid=study_uid)
    for k in ORDEM:
        m = res.medidas.get(k)
        if m is None or not m.linhas:
            continue
        for n, (a, b) in enumerate(m.linhas):
            if k == "calosal":
                texto = rotulo_da_linha(m) if n == 0 else ""
            elif k == "v3":
                texto = rotulo_da_linha(m) if n == 1 else ""
            else:
                texto = rotulo_da_linha(m) if n == len(m.linhas) - 1 else ""
            obj.planar.append(O.Graphic("polyline", [], texto, np.array([a, b], float), CORES.get(k)))
        obj.findings.append(f"{m.nome}: {m.texto_valor()}")
    return obj


plano_da_medida = CF.plano_da_medida


def valores_para_roteiro(res: Resultado) -> dict:
    """Os números que preenchem os roteiros manuais (MRPI 2.0, Evans, calosal): passo -> [valores]."""
    m = res.medidas
    out = {}
    tres = [float(x.replace(",", ".")) for x in m["v3"].texto.replace("mm", "").split("/") if x.strip()] \
        if m["v3"].origem != "editado" else []
    if len(tres) == 3:
        out["v3"] = tres
    elif m["v3"].valor is not None:
        out["v3"] = [m["v3"].valor] * 3
    for k, passo in (("cornos", "cornos"), ("cranio", "cranio"), ("calosal", "angulo")):
        if m[k].valor is not None:
            out[passo] = [m[k].valor]
    return out
