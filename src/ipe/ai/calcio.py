"""Escore de cálcio coronariano (Agatston) na TC sem contraste (0.99.89; backlog IA 2 / AW B1).

Sem um modelo de coronária: a tarefa `coronary_arteries` do TotalSegmentator exige licença, e o AI-CAC (VA) tem
pesos de 1,2 GB num PyTorch antigo. O caminho é o do SmartScore, com a IA só para tirar o que não é coronária:

1. **Órgãos** (TotalSegmentator `total`, rápido): coração, aorta, esterno, cartilagens costais, costelas e
   vértebras torácicas.
2. **Região de busca**: o coração com 8 mm de margem (as coronárias correm na gordura epicárdica, por fora da
   máscara do coração), sem o osso (1 voxel de margem). A aorta (com 2 voxels de margem), da altura do coração
   para cima, entra à parte.
3. **Agatston** (Agatston et al., J Am Coll Cardiol 1990), corte a corte: pixel ≥ 130 HU, lesão 2D (4 vizinhos)
   com área ≥ 1 mm², peso pelo HU máximo da lesão (130–199 = 1, 200–299 = 2, 300–399 = 3, ≥ 400 = 4),
   escore = área × peso × espessura ÷ 3 mm (o escore clássico é de cortes de 3 mm; a espessura que vale é a
   distância entre os cortes, como no SmartScore). **Volume** = área × espessura (limiar de 130 HU).
   Cortes finos (≤ 2 mm) são **somados em fatias de ~3 mm** (média dos HU), como a reconstrução de 3 mm em que o
   escore foi definido: corte fino aumenta o escore.
4. **Lesões 3D** (as 2D que se tocam entre cortes) e **o vaso de cada uma**, pela posição:
   - encostada na aorta → **aorta** (inclui a raiz e a valva aórtica; não entra no escore coronariano);
   - mais de 5 mm para dentro do coração → **intracardíaca** (valva ou anel mitral, provavelmente; fora do escore);
   - até 20 mm da raiz da aorta, à esquerda dela e no máximo 8 mm abaixo → **TCE** (tronco da coronária esquerda);
   - no resto, o ângulo em volta do centro do coração naquele corte: anterior e à esquerda → **DA**; à esquerda e
     posterior → **CX**; à direita e posteroinferior → **CD**.
   É uma **sugestão** (sem a árvore coronária não há como ter certeza): o médico confere e corrige.
5. **Categorias**: CAC-DRS (Hecht et al., J Cardiovasc Comput Tomogr 2018) A0 = 0, A1 = 1–99, A2 = 100–299,
   A3 ≥ 300, com N = número de vasos com cálcio (TCE, DA, CX, CD); e a escala da SCCT/STR para TC de tórax sem
   sincronização (Hecht et al. 2017): nenhum, leve, moderado, grave.

Avisos: contraste (o escore **não** vale: o sangue passa do limiar), TC sem sincronização com o ECG (o movimento
subestima), kV diferente de 120, corte fino ou grosso, anel mitral perto da CX. O percentil por idade e sexo (MESA)
não é calculado.

Saída: SEG "Cálcio coronariano (Agatston) · Ipê" (série 979, um segmento por vaso) e os achados: o resumo T e um
por vaso (TCE, DA, CX, CD) e por calcificação não coronária (AO, IC). O texto do laudo refaz o total pelos vasos
confirmados ou corrigidos: descartar um vaso tira ele do total.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "calcio"
TITULO = "Escore de cálcio coronariano (Agatston) na TC"
MARCA = "· Ipê"
DESC_SEG = f"Calcio coronariano (Agatston) {MARCA}"        # sem acento: o DICOM é Latin-1
SERIE_SEG = 979
MIN_CORTES = 20
MODALIDADES = ("CT",)
MOTIVO_MODALIDADE = "O escore de cálcio é medido na TC."
MODELO = "Agatston (130 HU) + órgãos do TotalSegmentator"
CHAVE_SAIDA = "calcio"
TIPO_RESUMO = "Cálcio coronariano (Agatston)"
TIPO_VASO = "Cálcio coronariano por vaso"
TIPO_OUTRO = "Calcificação não coronária"

LIMIAR_HU = 130.0
LIMIAR_MIN = 90.0                         # o SmartScore não deixa abaixo de 90
AREA_MIN_MM2 = 1.0
ALVO_MM = 3.0                              # a espessura do escore clássico
MARGEM_CORACAO_MM = 8.0
DENTRO_MM = 5.0                            # mais fundo que isto, dentro do coração: valva/anel
RAIZ_TCE_MM = 20.0
CONTRASTE_HU = 100.0                       # sangue (aorta, coração) acima disto: contraste

VASOS = {"TCE": "tronco da coronária esquerda", "DA": "descendente anterior", "CX": "circunflexa",
         "CD": "coronária direita"}
OUTROS = {"AO": "aorta torácica (inclui a raiz e a valva aórtica)",
          "IC": "dentro do coração (valva ou anel mitral?)"}
ORDEM = ("TCE", "DA", "CX", "CD", "AO", "IC")
CODIGO = {s: i for i, s in enumerate(ORDEM, start=1)}
CORES = {"TCE": (250, 220, 40), "DA": (240, 80, 80), "CX": (70, 150, 255), "CD": (70, 210, 110),
         "AO": (190, 190, 190), "IC": (190, 110, 250)}
_OSSO = re.compile(r"^(vertebrae_[TC]\d+|rib_|sternum|costal_cartilages|clavicula_|scapula_)")
_GATED = ("CALCIO", "CALCIUM", "ESCORE", "SCORE", "CAC", "CARDIAC", "CARDIACA", "CORONAR", "CORACAO", "HEART",
          "SMARTSCORE", "ECG", "GATED", "SINCRONIZ")

CHAVE_AUTO = "calcio.auto"
CHAVE_EXAME_CONTEM = "calcio.exame_contem"
CHAVE_MODALIDADES = "calcio.modalidades"
CHAVE_PRIOR_CT = "calcio.prioridade"
CHAVE_ESPESSURA = "calcio.espessura_max"
CHAVE_MIN_CORTES = "calcio.min_cortes"
CHAVE_DESTINOS = "calcio.destinos"
CHAVE_LIMIAR = "calcio.limiar_hu"
CHAVE_AREA = "calcio.area_min"
CHAVE_SOMAR = "calcio.somar_3mm"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "CALCIO|CALCIUM|ESCORE|SCORE|CORONAR|CARDIAC|CORACAO|TORAX|TÓRAX|CHEST|THORAX",
    CHAVE_MODALIDADES: ["CT"],
    CHAVE_PRIOR_CT: "CALCIO|CALCIUM|ESCORE|SCORE|CAC|SMARTSCORE|SEM CONTRASTE|S/C|STANDARD|STD|MEDIASTINO|"
                    "PARTES MOLES|SOFT|B30|BR40",
    CHAVE_ESPESSURA: 5.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
    CHAVE_LIMIAR: LIMIAR_HU,
    CHAVE_AREA: AREA_MIN_MM2,
    CHAVE_SOMAR: 1,
}
OPCOES = ((CHAVE_LIMIAR, "Limiar:", LIMIAR_MIN, 400, " HU", "O Agatston usa 130 HU (o SmartScore não deixa abaixo de 90)"),
          (CHAVE_AREA, "Menor lesão:", 0.1, 10, " mm²", "Lesões menores num corte não pontuam (ruído); o padrão é 1 mm²"),
          (CHAVE_SOMAR, "Somar cortes finos em 3 mm:", 0, 1, "",
           "1 = cortes de até 2 mm viram fatias de ~3 mm (média), como o escore clássico; 0 = usa os cortes como vêm"))
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("TOPO", "SCOUT", "LOCALIZER", "MIP", "DOSE", "SURVIEW", "PATIENT PROTOCOL", "PULMAO",
                      "LUNG", "ANGIO", "ARTERIAL", "PORTAL", "VENOSA")}
NOME_CADIA = "Cálcio coronariano (Agatston)"
TITULO_CADIA = "Escore de cálcio coronariano (Agatston) na TC sem contraste, por vaso, com o CAC-DRS"
EXPLICACAO_CADIA = ("Na TC sem contraste (escore de cálcio ou TC de tórax): o TotalSegmentator acha o coração, a "
                    "aorta e os ossos; em volta do coração, o cálcio ≥ 130 HU é pontuado pelo Agatston corte a "
                    "corte (cortes finos somados em fatias de 3 mm), com o volume, o vaso sugerido de cada lesão "
                    "(TCE, DA, CX, CD), o CAC-DRS e a categoria da SCCT/STR. A aorta e o que está dentro do coração "
                    "(valva, anel mitral) saem à parte. Cada vaso está em Achados de IA: corrigir ou descartar muda "
                    "o total do laudo. Com contraste o escore não vale.")
CHAVES_RESUMO = ("agatston", "volume", "n_vasos", "n_lesoes")
CHAVES_VASO = ("agatston", "volume", "n_lesoes", "hu_max")
CHAVES = tuple(dict.fromkeys(CHAVES_RESUMO + CHAVES_VASO))


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


ORGAOS = (["heart", "aorta", "sternum", "costal_cartilages"] + [f"vertebrae_T{i}" for i in range(1, 13)]
          + [f"rib_{lado}_{i}" for lado in ("left", "right") for i in range(1, 13)])


def tarefas(modalidade: str = "CT", settings=None) -> list[dict]:
    return [{"nome": "total", "roi": list(ORGAOS), "fast": True, "rotulo": "coração, aorta e ossos do tórax",
             "calcio": True}]


# ------------------------------------------------------------------ peças da conta
def peso(hu_max: float) -> int:
    """O fator de Agatston pelo HU máximo da lesão."""
    if hu_max >= 400:
        return 4
    if hu_max >= 300:
        return 3
    if hu_max >= 200:
        return 2
    return 1 if hu_max >= 130 else 0


def cac_drs(agatston: float, n_vasos: int) -> str:
    a = 0 if agatston <= 0 else 1 if agatston < 100 else 2 if agatston < 300 else 3
    return "CAC-DRS 0" if a == 0 else f"CAC-DRS A{a}/N{max(1, min(4, int(n_vasos)))}"


def categoria(agatston: float) -> str:
    """A escala da SCCT/STR (2017) para a TC de tórax sem sincronização."""
    if agatston <= 0:
        return "nenhum"
    return "leve" if agatston < 100 else "moderado" if agatston < 300 else "grave"


def _box(m: np.ndarray, raios: tuple[int, int, int]) -> np.ndarray:
    """Dilatação por uma caixa de meia-largura `raios` (k, j, i), sem dar a volta na borda."""
    out = m.copy()
    for ax, r in enumerate(raios):
        if r <= 0:
            continue
        cur = out.copy()
        n = out.shape[ax]
        for d in range(1, r + 1):
            if d >= n:
                break
            a = [slice(None)] * 3
            b = [slice(None)] * 3
            a[ax], b[ax] = slice(d, None), slice(None, -d)
            cur[tuple(a)] |= out[tuple(b)]
            cur[tuple(b)] |= out[tuple(a)]
        out = cur
    return out


def _raios(mm: float, esp: tuple[float, float, float]) -> tuple[int, int, int]:
    return tuple(max(0, int(round(mm / max(abs(e), 1e-6)))) for e in esp)


def _dilatar_mm(m, mm, esp):
    return _box(m, _raios(mm, esp))


def _erodir_mm(m, mm, esp):
    return ~_box(~m, _raios(mm, esp))


def _cabecalho(t) -> dict:
    try:
        import pydicom
        ds = pydicom.dcmread(t.frames[0].path, stop_before_pixels=True, force=True,
                             specific_tags=["KVP", "SliceThickness", "ContrastBolusAgent", "SeriesDescription",
                                            "StudyDescription", "TriggerTime", "CardiacSynchronizationTechnique",
                                            "ConvolutionKernel"])
    except Exception:  # noqa: BLE001
        return {}
    from pydicom.multival import MultiValue
    k = ds.get("ConvolutionKernel", "")
    k = " ".join(str(x) for x in k) if isinstance(k, (list, tuple, MultiValue)) else str(k or "")
    return {"kvp": ds.get("KVP"), "espessura": ds.get("SliceThickness"),
            "contraste": str(ds.get("ContrastBolusAgent", "") or "").strip(),
            "descricao": str(ds.get("SeriesDescription", "") or ""),
            "estudo": str(ds.get("StudyDescription", "") or ""),
            "gatilho": ds.get("TriggerTime") is not None or bool(ds.get("CardiacSynchronizationTechnique")),
            "kernel": k.strip()}


@dataclass
class Lesao:
    vaso: str
    agatston: float
    volume: float                 # mm³
    hu_max: float
    centro: list                  # mm, paciente
    n_voxels: int


@dataclass
class Resultado:
    lesoes: list = field(default_factory=list)
    vasos: dict = field(default_factory=dict)      # sigla -> {agatston, volume, n_lesoes, hu_max, centro}
    agatston: float = 0.0
    volume: float = 0.0
    n_vasos: int = 0
    calculado: bool = False                         # False: não deu para medir (sem coração, contraste…)
    mascara: np.ndarray | None = None               # códigos 1..6 (ORDEM), na caixa `offset`
    offset: tuple = (0, 0, 0)
    fatia_mm: float = 0.0
    centro: list | None = None
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""

    @property
    def cac_drs(self) -> str:
        return cac_drs(self.agatston, self.n_vasos)

    @property
    def categoria(self) -> str:
        return categoria(self.agatston)


def _vaso(x, y, z, cx, cy, raiz) -> str:
    """O vaso sugerido pela posição (mm, paciente LPS: x cresce para a esquerda, y para trás)."""
    if raiz is not None:
        rx, ry, rz = raiz
        if math.dist((x, y, z), raiz) <= RAIZ_TCE_MM and x > rx and z >= rz - 8.0:
            return "TCE"
    phi = math.degrees(math.atan2(-(y - cy), x - cx))     # 0 = esquerda, 90 = anterior, ±180 = direita
    if 30.0 <= phi < 120.0:
        return "DA"
    if -100.0 <= phi < 30.0:
        return "CX"
    return "CD"


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import cefalometria as CF
    from ipe.imaging.estruturas import rotular
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    ms = CF.Mascaras(vol, rotulos)
    dados = vol.data
    nz = dados.shape[0]
    zs = np.array([float(vol.voxel_to_patient(0, 0, k)[2]) for k in range(nz)])
    passo = float(np.median(np.abs(np.diff(zs)))) if nz > 1 else abs(float(vol.dz))
    cab = _cabecalho(t)
    esp_nominal = float(cab.get("espessura") or 0) or passo
    desc = t.descricao_serie or cab.get("descricao") or t.series_uid[-8:]
    res.elegibilidade = (f"TC, série “{desc}”, {nz} cortes de {esp_nominal:.2f} mm a cada {passo:.2f} mm, pixel "
                         f"{vol.dy:.2f} × {vol.dx:.2f} mm" + (f", {float(cab['kvp']):.0f} kV" if cab.get("kvp") else ""))
    coracao = ms.get("heart")
    if coracao is None or coracao.sum() < 50:
        res.avisos.append("a IA não achou o coração nesta série")
        return res
    aorta = ms.get("aorta")
    esp = (passo, float(vol.dy), float(vol.dx))
    # contraste: o sangue passa do limiar e o escore não vale
    sangue = []
    for m in (aorta, coracao):
        if m is not None and m.sum() > 50:
            me = _erodir_mm(m, 3.0, esp)
            me = me if me.sum() > 20 else m
            sangue.append(float(np.median(dados[me])))
    if sangue and max(sangue) > CONTRASTE_HU:
        res.avisos.append(f"série com contraste (sangue em {max(sangue):.0f} HU): o escore de cálcio só vale na TC sem "
                          f"contraste — use a série sem contraste")
        return res
    from ipe.ai.totalseg import _sem_acento
    textos = _sem_acento(" ".join((t.descricao_serie or "", cab.get("descricao", ""), cab.get("estudo", ""))).upper())
    if cab.get("contraste"):
        res.avisos.append(f"o cabeçalho diz contraste ({cab['contraste']}): confira se esta é a série sem contraste")
    # região de busca (recortada)
    k_c = np.nonzero(coracao.any(axis=(1, 2)))[0]
    k_base, k_topo = int(k_c.min()), int(k_c.max())
    ao_tor = np.zeros(dados.shape, bool)
    if aorta is not None:
        z_base = min(zs[k_base], zs[k_topo])                   # da altura do coração para cima
        acima = (zs >= z_base - 1e-3)[:, None, None]
        ao_tor = aorta & acima
    # a caixa: o coração com folga (a margem de busca e mais um pouco) e a aorta torácica — recortar antes de
    # dilatar, que a série inteira (512 × 512 × 300) é grande
    folga = _raios(MARGEM_CORACAO_MM + 12.0, esp)
    lim = []
    for ax, (outros, f) in enumerate((((1, 2), folga[0]), ((0, 2), folga[1]), ((0, 1), folga[2]))):
        ic = np.nonzero(coracao.any(axis=outros))[0]
        lo, hi = int(ic[0]) - f, int(ic[-1]) + 1 + f
        if ao_tor.any():
            ia = np.nonzero(ao_tor.any(axis=outros))[0]
            lo, hi = min(lo, int(ia[0]) - 2), max(hi, int(ia[-1]) + 3)
        lim += [max(0, lo), min(dados.shape[ax], hi)]
    k0, k1, j0, j1, i0, i1 = lim
    sl = (slice(k0, k1), slice(j0, j1), slice(i0, i1))
    hu = np.asarray(dados[sl], np.float32)
    cor = coracao[sl]
    busca = _dilatar_mm(cor, MARGEM_CORACAO_MM, esp)
    dentro = _erodir_mm(cor, DENTRO_MM, esp)
    ao = _box(ao_tor[sl], (0, 2, 2)) if ao_tor.any() else np.zeros(hu.shape, bool)
    osso = np.zeros(hu.shape, bool)
    for nome in list(ms._onde):
        if _OSSO.match(nome):
            m = ms.get(nome)
            if m is not None:
                osso |= m[sl]
    osso = _box(osso, (1, 1, 1))
    regiao = (busca | ao) & ~osso
    # fatias de ~3 mm
    somar = int(config(settings, CHAVE_SOMAR) or 0) == 1
    n = max(1, int(round(ALVO_MM / passo))) if (somar and passo <= 2.0 + 1e-6 and esp_nominal <= 2.0 + 1e-6) else 1
    K = hu.shape[0]
    grupos = [(g, min(g + n, K)) for g in range(0, K, n)]
    if n > 1 and grupos[-1][1] - grupos[-1][0] < n:      # o resto vai junto da última fatia cheia
        if len(grupos) > 1:
            grupos.pop()
            grupos[-1] = (grupos[-1][0], K)
    res.fatia_mm = n * passo
    if n > 1:
        res.avisos.append(f"cortes de {esp_nominal:.2f} mm somados em fatias de {n * passo:.1f} mm (média dos HU), "
                          f"como a reconstrução de 3 mm em que o Agatston foi definido")
    limiar = max(LIMIAR_MIN, float(config(settings, CHAVE_LIMIAR) or LIMIAR_HU))
    area_min = float(config(settings, CHAVE_AREA) or AREA_MIN_MM2)
    px_mm2 = float(vol.dx * vol.dy)
    G = len(grupos)
    sh = (G,) + hu.shape[1:]
    fat_hu = np.zeros(sh, np.float32)
    fat_reg = np.zeros(sh, bool)
    fat_ao = np.zeros(sh, bool)
    fat_dentro = np.zeros(sh, bool)
    esp_g = np.zeros(G)
    for g, (a, b) in enumerate(grupos):
        fat_hu[g] = hu[a:b].mean(axis=0)
        fat_reg[g] = regiao[a:b].any(axis=0)
        fat_ao[g] = ao[a:b].any(axis=0)
        fat_dentro[g] = dentro[a:b].all(axis=0)
        esp_g[g] = (b - a) * passo
    manter = np.zeros(sh, bool)
    densidade = np.zeros(sh, np.float32)          # escore de Agatston por pixel (a lesão 2D dividida)
    for g in range(G):
        m2 = (fat_hu[g] >= limiar) & fat_reg[g]
        if not m2.any():
            continue
        rot2, n2 = rotular(m2)
        cont = np.bincount(rot2.ravel(), minlength=n2 + 1)
        hmax = np.full(n2 + 1, -np.inf)
        np.maximum.at(hmax, rot2.ravel(), fat_hu[g].ravel())
        for c in range(1, n2 + 1):
            area = cont[c] * px_mm2
            if area < area_min:
                continue
            w = peso(float(hmax[c]))
            mc = rot2 == c
            manter[g][mc] = True
            densidade[g][mc] = area * w * (esp_g[g] / ALVO_MM) / cont[c]
    # lesões 3D e o vaso de cada uma
    mascara = np.zeros(hu.shape, np.uint8)
    if manter.any():
        rot3, n3 = rotular(manter)
        flat = rot3.ravel()
        soma = np.bincount(flat, weights=densidade.ravel(), minlength=n3 + 1)
        vox_vol = (px_mm2 * esp_g)[:, None, None] * np.ones(sh[1:])[None]
        volume = np.bincount(flat, weights=vox_vol.ravel(), minlength=n3 + 1)
        cnt = np.bincount(flat, minlength=n3 + 1)
        n_ao = np.bincount(flat, weights=fat_ao.ravel().astype(float), minlength=n3 + 1)
        n_dentro = np.bincount(flat, weights=fat_dentro.ravel().astype(float), minlength=n3 + 1)
        hmax3 = np.full(n3 + 1, -np.inf)
        np.maximum.at(hmax3, flat, fat_hu.ravel())
        gg, jj, ii = np.indices(sh)
        sg = np.bincount(flat, weights=gg.ravel(), minlength=n3 + 1)
        sj = np.bincount(flat, weights=jj.ravel(), minlength=n3 + 1)
        si = np.bincount(flat, weights=ii.ravel(), minlength=n3 + 1)
        meio_g = np.array([(a + b - 1) / 2.0 for a, b in grupos])
        # centro do coração por fatia e a raiz da aorta
        centros = {}
        for g, (a, b) in enumerate(grupos):
            c2 = cor[a:b].any(axis=0)
            if c2.sum() > 10:
                cj, ci = np.argwhere(c2).mean(axis=0)
                centros[g] = (cj, ci)
        cj_all, ci_all = np.argwhere(cor.any(axis=0)).mean(axis=0)
        raiz = _raiz_da_aorta(ao_tor[sl], cor, grupos, vol, (k0, j0, i0))
        codigo = np.zeros(n3 + 1, np.uint8)
        for c in range(1, n3 + 1):
            if cnt[c] == 0 or soma[c] <= 0:
                continue
            g_c = sg[c] / cnt[c]
            k_c_ = k0 + float(np.interp(g_c, np.arange(G), meio_g))
            j_c, i_c = j0 + sj[c] / cnt[c], i0 + si[c] / cnt[c]
            x, y, z = (float(v) for v in vol.voxel_to_patient(i_c, j_c, k_c_))
            if n_ao[c] > 0:
                sig = "AO"
            elif n_dentro[c] / cnt[c] > 0.5:
                sig = "IC"
            else:
                g_i = int(round(g_c))
                cj, ci = centros.get(g_i, (cj_all, ci_all))
                cx, cy, _cz = (float(v) for v in vol.voxel_to_patient(i0 + ci, j0 + cj, k_c_))
                sig = _vaso(x, y, z, cx, cy, raiz)
            res.lesoes.append(Lesao(sig, float(soma[c]), float(volume[c]), float(hmax3[c]), [x, y, z], int(cnt[c])))
            codigo[c] = CODIGO[sig]
        # na grade original: os pixels da lesão ≥ limiar em cada corte da fatia
        por_fatia = codigo[rot3]
        for g, (a, b) in enumerate(grupos):
            if por_fatia[g].any():
                mascara[a:b] = np.where(hu[a:b] >= limiar, por_fatia[g][None], 0)
    # por vaso
    for sig in ORDEM:
        ls = [x for x in res.lesoes if x.vaso == sig]
        if not ls:
            continue
        maior = max(ls, key=lambda x: x.agatston)
        res.vasos[sig] = {"agatston": sum(x.agatston for x in ls), "volume": sum(x.volume for x in ls),
                          "n_lesoes": len(ls), "hu_max": max(x.hu_max for x in ls), "centro": maior.centro}
    cor_vasos = [s for s in VASOS if s in res.vasos]
    res.agatston = float(sum(res.vasos[s]["agatston"] for s in cor_vasos))
    res.volume = float(sum(res.vasos[s]["volume"] for s in cor_vasos))
    res.n_vasos = len(cor_vasos)
    res.calculado = True
    if mascara.any():
        res.mascara, res.offset = mascara, (int(k0), int(j0), int(i0))
    kk, jj2, ii2 = np.argwhere(coracao).mean(axis=0)
    res.centro = [float(v) for v in vol.voxel_to_patient(ii2, jj2, kk)]
    # avisos de técnica
    gated = cab.get("gatilho") or any(p in textos for p in _GATED)
    if not gated:
        res.avisos.append("TC sem sincronização com o ECG (pelo cabeçalho e pela descrição): o movimento subestima o "
                          "escore; a SCCT/STR recomenda relatar também a categoria (nenhum, leve, moderado, grave)")
    try:
        kv = float(cab.get("kvp") or 0)
    except (TypeError, ValueError):
        kv = 0.0
    if kv and abs(kv - 120) > 1:
        res.avisos.append(f"{kv:.0f} kV: o limiar de 130 HU e os pesos do Agatston são de 120 kV")
    if n == 1 and passo < 2.5:
        res.avisos.append(f"cortes de {passo:.2f} mm sem somar: corte fino aumenta o escore (o clássico é de 3 mm)")
    if passo > 3.5:
        res.avisos.append(f"cortes a cada {passo:.1f} mm: corte grosso perde lesão pequena e subestima o escore")
    if "IC" in res.vasos and "CX" in res.vasos:
        res.avisos.append("há cálcio dentro do coração (anel mitral?) perto da CX: confira o que é coronária")
    res.avisos.append("o vaso é sugerido pela posição em volta do coração (sem a árvore coronária): confira e "
                      "corrija; o percentil por idade e sexo (MESA) não é calculado")
    return res


def _raiz_da_aorta(ao, cor, grupos, vol, off):
    """A raiz: o centro da aorta ascendente na fatia mais baixa em que ela aparece. Em cada fatia com dois
    pedaços de aorta, o ascendente é o mais anterior; com um só, é ascendente se estiver na frente do meio do
    coração (senão é a descendente)."""
    from ipe.imaging.estruturas import rotular
    if not ao.any():
        return None
    cj_cor = np.argwhere(cor.any(axis=0)).mean(axis=0)[0] if cor.any() else ao.shape[1] / 2
    melhor = None
    for g, (a, b) in enumerate(grupos):
        m2 = ao[a:b].any(axis=0)
        if m2.sum() < 5:
            continue
        r, nr = rotular(m2)
        pedacos = []
        for c in range(1, nr + 1):
            idx = np.argwhere(r == c)
            if len(idx) >= 5:
                pedacos.append(idx.mean(axis=0))
        if not pedacos:
            continue
        asc = min(pedacos, key=lambda p: p[0])                   # j menor = mais anterior
        if len(pedacos) == 1 and asc[0] > cj_cor:
            continue
        k = (a + b - 1) / 2.0
        z = float(vol.voxel_to_patient(0, 0, off[0] + k)[2])
        if melhor is None or z < melhor[0]:
            x, y, zz = (float(v) for v in vol.voxel_to_patient(off[2] + asc[1], off[1] + asc[0], off[0] + k))
            melhor = (z, (x, y, zz))
    return melhor[1] if melhor else None


# ------------------------------------------------------------------ saída
def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado:
        return []
    eleg = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "elegibilidade": eleg}
    num = {"agatston": _n(res.agatston, "", "Agatston", 0), "volume": _n(res.volume, "mm³", "Volume", 0),
           "n_vasos": _n(res.n_vasos, "", "Vasos com cálcio", 0),
           "n_lesoes": _n(sum(1 for x in res.lesoes if x.vaso in VASOS), "", "Lesões", 0)}
    itens = [{**base, "rotulo": "T", "tipo": TIPO_RESUMO, "local": f"{res.cac_drs} · {res.categoria}",
              "posicao": res.centro, "numeros": num}]
    for sig in ORDEM:
        v = res.vasos.get(sig)
        if not v:
            continue
        nv = {"agatston": _n(v["agatston"], "", "Agatston", 0), "volume": _n(v["volume"], "mm³", "Volume", 0),
              "n_lesoes": _n(v["n_lesoes"], "", "Lesões", 0), "hu_max": _n(v["hu_max"], "HU", "HU máximo", 0)}
        itens.append({**base, "rotulo": sig, "tipo": TIPO_VASO if sig in VASOS else TIPO_OUTRO,
                      "local": VASOS.get(sig) or OUTROS[sig], "posicao": v["centro"], "numeros": nv,
                      "segmento": CODIGO[sig]})
    return itens


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
                log.exception("trocar a SEG do cálcio anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.mascara is not None and res.mascara.any():
        segs = []
        for sig in ORDEM:
            m = res.mascara == CODIGO[sig]
            if m.any():
                nome = VASOS.get(sig) or OUTROS[sig]
                segs.append((SimpleNamespace(mask=m, offset=res.offset), f"Cálcio: {sig} ({nome})", CORES[sig]))
        vol = t.vol
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("SEMIAUTOMATIC", f"Agatston 130 HU + TotalSegmentator {versao}".strip()))
        tmp = Path(tempfile.mkdtemp(prefix="dv_calcio_"))
        try:
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
            out["series"] += sorted(getattr(r, "new_series", None) or [])
            out["seg_sop"] = str(ds.SOPInstanceUID)
            out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    # o que o médico já revisou (por vaso) fica: a rodada nova não repete o rótulo
    revisados = {a.get("rotulo") for a in repo.achados(t.study_uid, FERRAMENTA) if a.get("estado") != "sugerido"}
    itens = [x for x in itens_para_o_banco(res, t, versao) if x["rotulo"] not in revisados]
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens)
    return out


def _f(v, casas=0) -> str:
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",")


def resumo(res: Resultado) -> str:
    if not res.calculado:
        return res.avisos[0] if res.avisos else "não medido"
    if res.agatston <= 0:
        return "Agatston 0 (CAC-DRS 0)" + ("; cálcio só fora das coronárias" if res.vasos else "")
    partes = ", ".join(f"{s} {_f(res.vasos[s]['agatston'])}" for s in VASOS if s in res.vasos)
    return f"Agatston {_f(res.agatston)} ({partes}) — {res.cac_drs}, {res.categoria}"


def n_itens(res: Resultado) -> int:
    return (1 + len(res.vasos)) if res.calculado else 0


def mensagem(res: Resultado, minutos: float) -> str:
    if not res.calculado:
        return f"Cálcio coronariano: {resumo(res)}."
    msg = (f"Cálcio coronariano pronto em {minutos:.1f} min — {resumo(res)}. Cada vaso está em Aplicações ▸ Achados "
           f"de IA: confira o vaso sugerido, corrija ou descarte, e o total do laudo acompanha; as lesões estão na "
           f"série “{DESC_SEG}”, uma cor por vaso.")
    avisos = [a for a in res.avisos if not a.startswith("o vaso é sugerido")]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x)
    if a.get("tipo") == TIPO_RESUMO:
        return f"Escore de cálcio coronariano (Agatston): {v('agatston') or '0'} ({a.get('local', '')})."
    nome = a.get("local") or a.get("rotulo", "")
    txt = f"{a.get('rotulo', '')} ({nome}): Agatston {v('agatston') or '0'}"
    if v("volume"):
        txt += f", volume {v('volume')} mm³"
    return ("Calcificação " if a.get("tipo") == TIPO_OUTRO else "Cálcio coronariano, ") + txt + "."


def laudo(achados: list[dict]) -> str:
    """O texto do laudo pelos vasos **confirmados ou corrigidos**: o total, o CAC-DRS e a categoria são refeitos
    (descartar um vaso tira ele do total; corrigir o Agatston de um vaso muda o total)."""
    revis = [a for a in achados if a.get("estado") in AC.VALEM]
    if not revis:
        return ""
    vasos = [a for a in revis if a.get("tipo") == TIPO_VASO and a.get("rotulo") in VASOS]
    outros = [a for a in revis if a.get("tipo") == TIPO_OUTRO]
    total = 0.0
    n_vasos = 0
    for a in vasos:
        x = float((AC.numeros_validos(a).get("agatston") or {}).get("v") or 0)
        total += x
        n_vasos += x > 0
    cat = categoria(total)
    txt = (f"- Escore de cálcio coronariano (Agatston): {_f(total)} — {cac_drs(total, n_vasos)}; "
           + ("sem cálcio coronariano" if cat == "nenhum" else f"cálcio coronariano {cat}") + " (SCCT/STR).")
    linhas = [txt] + [f"- {frase(a)}" for a in sorted(vasos, key=lambda a: ORDEM.index(a["rotulo"]))]
    linhas += [f"- {frase(a)}" for a in outros]
    return "\n".join(linhas)
