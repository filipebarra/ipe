"""Carga tumoral total no PET, sem IA de lesão, e o fluxo do PSMA (0.99.88; backlog PET/CT itens 2 e 3).

A ideia é a do LesionID (MIM): tudo o que passa de um **limiar** vira foco; a captação **fisiológica** sai pelas
máscaras dos órgãos que o TotalSegmentator acha na **TC** do PET/CT; cada foco que sobra é uma lesão revisável
(descartar nos Achados de IA tira ela do total do laudo). Serve para FDG, PSMA e análogos de somatostatina (DOTA),
porque não depende de um modelo treinado num traçador — e roda em segundos depois dos órgãos.

**Limiar** (Configurações ▸ CAD/IA ou o padrão do traçador):
- FDG: PERCIST — 1,5 × média do fígado + 2 DP (esfera de 3 cm no lobo direito); sem fígado, SUV 2,5;
- PSMA: SUV 3 (o corte do qPSMA, Seifert/Gafita 2021);
- DOTA/SSTR: a média do fígado (Krenning ≥ 3 = acima do fígado).

**Fisiológico** (tirado, com 1 voxel de margem):
- FDG: cérebro, coração, rins, bexiga;
- PSMA: glândulas salivares (parótidas, submandibulares), rins, bexiga, fígado, baço, intestino delgado,
  duodeno e cólon;
- DOTA: baço, rins, fígado, adrenais, bexiga, intestino delgado e duodeno.
O que se tira não é medido — metástase hepática no PSMA/DOTA, por exemplo, fica de fora (aviso no resultado).

**Região de cada foco** (pela TC): osso (vértebra, costela, bacia, fêmur, crânio…), víscera (pulmão, fígado,
adrenal…), próstata e, no resto, linfonodo/partes moles — pélvico se abaixo da crista ilíaca, extrapélvico acima.

**PSMA (PROMISE v2)**: miTNM pela região (T próstata; N1 linfonodo pélvico; M1a extrapélvico; M1b osso — uni,
oligo ≤ 3, dissem.; M1c víscera) e o **escore miPSMA** de cada lesão pelo SUVmáx contra as médias do pool
sanguíneo (aorta), do fígado e da parótida: 0 abaixo do pool, 1 até o fígado, 2 até a parótida, 3 acima.
O PSMA-RADS fica com o médico (pede o contexto clínico e a morfologia de cada lesão).

Saída: SEG "Carga tumoral PET · Ipê" (série 987, na grade do PET) e os achados (resumo T e lesões L1…L30).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "carga_pet"
TITULO = "Carga tumoral no PET (FDG, PSMA, DOTA)"
MARCA = "· Ipê"
DESC_SEG = f"Carga tumoral PET {MARCA}"
SERIE_SEG = 987
MIN_CORTES = 40
MODALIDADES = ("CT",)                    # o TotalSegmentator roda na TC do PET/CT; a conta é no PET
MOTIVO_MODALIDADE = "A carga tumoral usa a TC do PET/CT para achar os órgãos (e o PET do mesmo exame)."
MODELO = "limiar + órgãos do TotalSegmentator"
CHAVE_SAIDA = "carga_pet"
TIPO_RESUMO = "Carga tumoral PET"
TIPO_LESAO = "Foco PET"
MIN_ML = 0.3
MAX_ACHADOS = 30
_FORA_CT = ("TOPO", "SCOUT", "LOCALIZER", "MIP", "DOSE", "SURVIEW", "PATIENT PROTOCOL")

TRACADORES = {"fdg": "FDG", "psma": "PSMA", "sstr": "análogo de somatostatina (DOTA)"}
_PADROES_TRACADOR = (
    ("psma", r"PSMA|PYL|DCFPYL|GOZETOTID|PSMA.?11|PSMA.?1007|RH.?PSMA|PIFLUFOLASTAT|ILUCCIX|LOCAMETZ"),
    ("sstr", r"DOTA|TATE|TOC\b|NOC\b|SSTR|SOMATOST|NETSPOT|DETECTNET|EDOTREOTID|OCTREO"),
    ("fdg", r"FDG|FLUORODEOX|FLUDEOX|DEOXYGLUC|GLICOSE|GLUCOSE"),
)

FISIOLOGICO = {
    "fdg": ("brain", "heart", "kidney_left", "kidney_right", "urinary_bladder"),
    "psma": ("parotid_gland_left", "parotid_gland_right", "submandibular_gland_left", "submandibular_gland_right",
             "kidney_left", "kidney_right", "urinary_bladder", "liver", "spleen", "small_bowel", "duodenum",
             "colon"),
    "sstr": ("spleen", "kidney_left", "kidney_right", "liver", "adrenal_gland_left", "adrenal_gland_right",
             "urinary_bladder", "small_bowel", "duodenum"),
}
_OSSO = re.compile(r"^(vertebrae_|rib_|hip_|femur_|humerus_|scapula_|clavicula_|sacrum|skull|sternum|costal_cartil)")
_VISCERA = {"liver": "fígado", "spleen": "baço", "pancreas": "pâncreas", "stomach": "estômago",
            "adrenal_gland_left": "adrenal esquerda", "adrenal_gland_right": "adrenal direita",
            "kidney_left": "rim esquerdo", "kidney_right": "rim direito", "brain": "encéfalo",
            "thyroid_gland": "tireoide", "esophagus": "esôfago", "gallbladder": "vesícula",
            "small_bowel": "intestino delgado", "colon": "cólon", "duodenum": "duodeno",
            "urinary_bladder": "bexiga"}
_PULMAO = "lung_"
REGIOES = {"osso": "osso", "visc": "víscera", "prost": "próstata", "lnp": "linfonodo pélvico",
           "lne": "linfonodo/partes moles extrapélvico"}
CORES = {"osso": (240, 200, 60), "visc": (230, 80, 80), "prost": (90, 150, 240), "lnp": (90, 210, 120),
         "lne": (60, 190, 200)}

CHAVE_AUTO = "carga_pet.auto"
CHAVE_EXAME_CONTEM = "carga_pet.exame_contem"
CHAVE_MODALIDADES = "carga_pet.modalidades"
CHAVE_PRIOR_CT = "carga_pet.prioridade"
CHAVE_ESPESSURA = "carga_pet.espessura_max"
CHAVE_MIN_CORTES = "carga_pet.min_cortes"
CHAVE_DESTINOS = "carga_pet.destinos"
CHAVE_SUV_FDG = "carga_pet.suv_fdg"
CHAVE_SUV_PSMA = "carga_pet.suv_psma"
CHAVE_MIN_ML = "carga_pet.min_ml"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "PET|PET-CT|PET/CT|PETCT|PSMA|FDG|DOTA|GALIO|GALLIUM",
    CHAVE_MODALIDADES: ["CT"],
    CHAVE_PRIOR_CT: "STD|STANDARD|AC|WB|CORPO|BODY",
    CHAVE_ESPESSURA: 6.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
    CHAVE_SUV_FDG: 0.0,                  # 0 = PERCIST pelo fígado
    CHAVE_SUV_PSMA: 3.0,
    CHAVE_MIN_ML: MIN_ML,
}
OPCOES = ((CHAVE_SUV_FDG, "Limiar no FDG:", 0, 20, " SUV", "0 = PERCIST (1,5 × fígado + 2 DP); outro valor = SUV fixo"),
          (CHAVE_SUV_PSMA, "Limiar no PSMA:", 0, 20, " SUV", "O qPSMA usa SUV 3"),
          (CHAVE_MIN_ML, "Menor foco:", 0.05, 10, " mL", "Focos menores ficam de fora (ruído)"))
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": _FORA_CT}
NOME_CADIA = "Carga tumoral no PET (FDG/PSMA/DOTA)"
TITULO_CADIA = "Carga tumoral no PET: focos acima do limiar sem a captação fisiológica, MTV, TLG, miTNM e miPSMA"
EXPLICACAO_CADIA = ("No PET/CT: o TotalSegmentator acha os órgãos na TC; no PET, tudo acima do limiar do traçador "
                    "(FDG: PERCIST; PSMA: SUV 3; DOTA: fígado) que não está num órgão de captação fisiológica vira "
                    "um foco, com volume, SUV e região (osso, linfonodo, víscera). No PSMA sai também o miTNM e o "
                    "escore miPSMA. Cada foco está em Achados de IA: descartar tira do total do laudo.")
CHAVES_RESUMO = ("n_lesoes", "mtv", "tlg", "suvmax", "limiar", "n_osso", "n_lnp", "n_lne", "n_visc")
CHAVES_LESAO = ("vol_ml", "suvmax", "suvmean", "suvpeak", "tlg", "mipsma")
CHAVES = CHAVES_RESUMO + CHAVES_LESAO


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


def _sem_acento(s):
    from ipe.ai.totalseg import _sem_acento as f
    return f(s)


def exame_serve(info: dict, settings=None) -> bool:
    mods = (info.get("modalities") or "").upper()
    if "PT" not in mods or "CT" not in mods:
        return False
    from ipe.ai import totalseg as TS
    pads = TS._padroes(config(settings, CHAVE_EXAME_CONTEM))
    return not pads or any(p in _sem_acento(info.get("description", "")) for p in pads)


def serie_pet(repo, study_uid: str):
    """O PET corrigido por atenuação com mais cortes (não o NAC)."""
    pets = [s for s in repo.series_for_study(study_uid) if (s.modality or "").upper() == "PT"]

    def fora(s) -> bool:
        d = _sem_acento(s.description or "").upper().replace("-", " ")
        return any(w in d.split() for w in ("NAC", "NOAC", "UNCORR", "MIP")) or "NON AC" in d or "SEM CORRECAO" in d
    bons = [s for s in pets if not fora(s)] or pets
    bons = [s for s in bons if (s.num_images or 0) >= 10]
    return max(bons, key=lambda s: s.num_images or 0) if bons else None


def escolher_serie(repo, study_uid: str, settings=None):
    """A TC do PET/CT (o TotalSegmentator roda nela)."""
    from ipe.ai import autopet as AP
    if serie_pet(repo, study_uid) is None:
        return None, "este exame não tem PET"
    se = AP.serie_ct(repo, study_uid)
    if se is None or (se.num_images or 0) < MIN_CORTES:
        return None, "não há TC do PET/CT com cortes suficientes"
    return se.series_uid, ""


def ja_feita(repo, study_uid: str) -> bool:
    from ipe.ai import totalseg as TS
    return TS.ja_segmentado(repo, study_uid, DESC_SEG)


def tarefas(modalidade: str = "CT", settings=None) -> list[dict]:
    # as glândulas salivares (só o PSMA precisa) entram em `canais_extras`, que conhece o traçador
    return [{"nome": "total", "rotulo": "órgãos e ossos (corpo inteiro)", "fast": True, "carga": True}]


def tracador_do_cabecalho(ds) -> str:
    """fdg / psma / sstr / "" pelo radiofármaco e pelas descrições do exame e da série."""
    textos = []
    try:
        for it in ds.get("RadiopharmaceuticalInformationSequence", []) or []:
            textos.append(str(it.get("Radiopharmaceutical", "") or ""))
            for c in it.get("RadiopharmaceuticalCodeSequence", []) or []:
                textos.append(str(c.get("CodeMeaning", "") or ""))
    except Exception:  # noqa: BLE001
        pass
    textos += [str(ds.get("StudyDescription", "") or ""), str(ds.get("SeriesDescription", "") or "")]
    t = _sem_acento(" ".join(textos)).upper()
    for nome, pad in _PADROES_TRACADOR:
        if re.search(pad, t):
            return nome
    return ""


def canais_extras(t) -> dict:
    """Antes do trabalhador: acha o PET do exame e o traçador; no PSMA, pede também as glândulas salivares."""
    import pydicom

    from ipe.ai.totalseg import Falhou
    se = serie_pet(t.repo, t.study_uid)
    if se is None:
        raise Falhou("Este exame não tem PET para medir a carga tumoral.")
    inst = t.repo.instances_for_series(se.series_uid)
    if not inst:
        raise Falhou("O PET deste exame não tem imagens.")
    ds = pydicom.dcmread(str(inst[0]["path"]), stop_before_pixels=True, force=True)
    t.pet_series_uid = se.series_uid
    t.tracador = tracador_do_cabecalho(ds)
    if t.tracador == "psma" and not any(x.get("nome") == "head_glands_cavities" for x in t.lista_tarefas):
        t.lista_tarefas = list(t.lista_tarefas) + [
            {"nome": "head_glands_cavities", "rotulo": "glândulas salivares (referência e fisiológico do PSMA)",
             "carga": True}]
    return {}


# ------------------------------------------------------------------ geometria
def rotulos_na_grade(alvo, fonte, rot: np.ndarray) -> np.ndarray:
    """Rótulos (k, j, i) da grade `fonte` levados à grade `alvo` pelo vizinho mais próximo (mesmo Frame of
    Reference, o caso do PET/CT)."""
    nz, ny, nx = alvo.shape
    fz, fy, fx = rot.shape
    jj, ii = np.mgrid[0:ny, 0:nx].astype(np.float64)
    ma, mf_inv = alvo.matrix(), np.linalg.inv(fonte.matrix())
    out = np.zeros(alvo.shape, rot.dtype)
    for k in range(nz):
        pts = np.stack([ii.ravel(), jj.ravel(), np.full(ii.size, float(k))], 1) @ ma.T + alvo.origin
        ijk = np.rint((pts - fonte.origin) @ mf_inv.T).astype(np.int64)
        ok = ((ijk[:, 0] >= 0) & (ijk[:, 0] < fx) & (ijk[:, 1] >= 0) & (ijk[:, 1] < fy)
              & (ijk[:, 2] >= 0) & (ijk[:, 2] < fz))
        v = np.zeros(ii.size, rot.dtype)
        v[ok] = rot[ijk[ok, 2], ijk[ok, 1], ijk[ok, 0]]
        out[k] = v.reshape(ny, nx)
    return out


def _dilatar(m: np.ndarray, n: int = 1) -> np.ndarray:
    out = m.copy()
    for _ in range(n):
        d = out.copy()
        for ax in range(3):
            d |= np.roll(out, 1, ax) | np.roll(out, -1, ax)
        out = d
    return out


def _erodir(m: np.ndarray, n: int = 1) -> np.ndarray:
    return ~_dilatar(~m, n)


# ------------------------------------------------------------------ a conta
@dataclass
class Lesao:
    n: int
    vol_ml: float
    suvmax: float
    suvmean: float
    suvpeak: float | None
    tlg: float
    centro: list
    regiao: str                          # osso / visc / prost / lnp / lne
    local: str                           # "osso (vértebra L3)", "fígado", "linfonodo pélvico"…
    mipsma: int | None = None


@dataclass
class Resultado:
    tracador: str = ""
    limiar: float | None = None
    limiar_como: str = ""
    refs: dict = field(default_factory=dict)            # pool, figado, parotida: SUV médio
    lesoes: list = field(default_factory=list)
    mtv: float = 0.0
    tlg: float = 0.0
    suvmax: float | None = None
    fator: float | None = None
    rotulo_mask: np.ndarray | None = None               # uint8: código da região de cada voxel de lesão
    offset: tuple = (0, 0, 0)
    centro: list | None = None
    pet_vol: object = None
    pet_frames: list = field(default_factory=list)
    pet_series_uid: str = ""
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    calculado: bool = False

    @property
    def mitnm(self) -> str:
        return mitnm(self.lesoes) if self.tracador == "psma" else ""


_CODIGO = {"osso": 1, "visc": 2, "prost": 3, "lnp": 4, "lne": 5}


def mitnm(lesoes: list) -> str:
    """miTNM (PROMISE v2) pela região das lesões: T, N, M1a/b/c."""
    reg = [x.regiao for x in lesoes]
    t = "miT+" if "prost" in reg else "miT0"
    n_lnp = reg.count("lnp")
    n = "miN1" if n_lnp else "miN0"
    m = []
    if reg.count("lne"):
        m.append("M1a")
    no = reg.count("osso")
    if no:
        m.append("M1b " + ("(uni)" if no == 1 else "(oligo)" if no <= 3 else "(dissem.)"))
    if reg.count("visc"):
        m.append("M1c")
    return f"{t} {n} " + ("mi" + ", ".join(m) if m else "miM0")


def escore_mipsma(suvmax: float, refs: dict) -> int | None:
    pool, fig, par = refs.get("pool"), refs.get("figado"), refs.get("parotida")
    if pool is None or fig is None:
        return None
    if suvmax < pool:
        return 0
    if suvmax < fig:
        return 1
    if par is None or suvmax < par:
        return 2
    return 3


def _limiar(tracador: str, refs: dict, settings) -> tuple[float, str]:
    if tracador == "psma":
        v = float(config(settings, CHAVE_SUV_PSMA) or 3.0)
        return v, f"SUV {v:.1f} (qPSMA)"
    if tracador == "sstr":
        if refs.get("figado") is not None:
            return refs["figado"], "média do fígado (Krenning)"
        return 4.0, "SUV 4 (sem o fígado)"
    v = float(config(settings, CHAVE_SUV_FDG) or 0)
    if v > 0:
        return v, f"SUV {v:.1f} (fixo)"
    f = refs.get("figado_ref")
    if f:
        return 1.5 * f["media"] + 2 * f["dp"], "PERCIST: 1,5 × fígado + 2 DP"
    return 2.5, "SUV 2,5 (sem o fígado)"


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    import pydicom

    from ipe.imaging import pet_onco as PO
    from ipe.imaging.estruturas import rotular
    from ipe.imaging.segment import suv_peak
    from ipe.imaging.series import build_frames
    from ipe.imaging.suv import suv_factor_for_file
    from ipe.imaging.volume import build_volume
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid, calculado=True)
    uid_pet = getattr(t, "pet_series_uid", "") or (serie_pet(t.repo, t.study_uid).series_uid
                                                   if serie_pet(t.repo, t.study_uid) else "")
    if not uid_pet:
        res.avisos.append("o exame não tem PET")
        return res
    res.pet_series_uid = uid_pet
    res.pet_frames = build_frames(t.repo.instances_for_series(uid_pet), uid_pet)
    pet = build_volume(res.pet_frames, t.cache)
    res.pet_vol = pet
    fator, motivo = suv_factor_for_file(res.pet_frames[0].path)
    res.fator = fator
    if not fator:
        res.avisos.append(f"sem o fator de SUV ({motivo})")
        return res
    ds = pydicom.dcmread(res.pet_frames[0].path, stop_before_pixels=True, force=True)
    res.tracador = getattr(t, "tracador", "") or tracador_do_cabecalho(ds) or "fdg"
    if not (getattr(t, "tracador", "") or tracador_do_cabecalho(ds)):
        res.avisos.append("o traçador não está no cabeçalho do PET: contas de FDG")
    suv = np.asarray(pet.data, np.float32) * float(fator)
    voxel_ml = float(pet.dx * pet.dy * abs(pet.dz)) / 1000.0
    res.elegibilidade = (f"PET ({TRACADORES.get(res.tracador, res.tracador)}), {pet.data.shape[0]} cortes de "
                         f"{abs(pet.dz):.1f} mm; órgãos da TC “{t.descricao_serie or t.series_uid[-8:]}” levados à "
                         f"grade do PET")
    # órgãos na grade do PET
    org: dict[str, np.ndarray] = {}
    for _tarefa, (lab, classes) in rotulos.items():
        if lab is None:
            continue
        na = rotulos_na_grade(pet, t.vol, np.asarray(lab, np.uint8))
        for cid, nome in classes.items():
            m = na == int(cid)
            if m.any():
                org[nome] = org[nome] | m if nome in org else m
    if not org:
        res.avisos.append("o TotalSegmentator não achou órgãos na TC")
    # referências: fígado (esfera de 3 cm no lobo direito), pool (aorta, erodida), parótida
    if "liver" in org:
        centro = PO.centro_da_mascara(org["liver"])
        if centro is not None:
            r = PO.referencia(suv, (abs(pet.dz), pet.dy, pet.dx), centro, PO.DIAM_FIGADO_MM, mascara=org["liver"],
                              busca_mm=40.0)
            if r:
                res.refs["figado_ref"] = r
                res.refs["figado"] = float(r["media"])
            else:                                   # fígado pequeno ou cortes grossos: a esfera de 3 cm não cabe
                m = _erodir(org["liver"], 1)
                m = m if m.sum() >= 10 else org["liver"]
                v = suv[m].astype(np.float64)
                med = float(np.median(v))
                dp = float(1.4826 * np.median(np.abs(v - med)))       # DP robusto: a lesão hepática não pesa
                res.refs["figado_ref"] = {"media": med, "dp": dp, "max": float(v.max()), "n": int(v.size)}
                res.refs["figado"] = med
                res.avisos.append("a esfera de 3 cm não coube no fígado: referência pela mediana do fígado")
    if "aorta" in org:
        a = _erodir(org["aorta"], 1)
        a = a if a.sum() >= 3 else org["aorta"]
        res.refs["pool"] = float(suv[a].mean())
    par = np.zeros(pet.shape, bool)
    for k in ("parotid_gland_left", "parotid_gland_right"):
        if k in org:
            par |= org[k]
    if par.any():
        res.refs["parotida"] = float(suv[par].mean())
    res.limiar, res.limiar_como = _limiar(res.tracador, res.refs, settings)
    # fisiológico
    fora = np.zeros(pet.shape, bool)
    tirados = []
    for nome in FISIOLOGICO.get(res.tracador, ()):
        if nome in org:
            fora |= org[nome]
            tirados.append(nome)
    fora = _dilatar(fora, 1)
    focos = (suv >= float(res.limiar)) & ~fora
    min_ml = float(config(settings, CHAVE_MIN_ML) or MIN_ML)
    # região: osso, víscera, próstata, linfonodo (pélvico abaixo da crista ilíaca)
    osso = np.zeros(pet.shape, bool)
    nome_osso = {}
    for nome, m in org.items():
        if _OSSO.match(nome):
            osso |= m
            nome_osso[nome] = m
    visc = {n: m for n, m in org.items() if n in _VISCERA or n.startswith(_PULMAO)}
    crista = None
    for k in ("hip_left", "hip_right"):
        if k in org:
            zs = np.nonzero(org[k].any(axis=(1, 2)))[0]
            if len(zs):
                topo = float(pet.voxel_to_patient(0, 0, int(zs.max()))[2])
                fundo = float(pet.voxel_to_patient(0, 0, int(zs.min()))[2])
                crista = max(topo, fundo) if crista is None else max(crista, topo, fundo)
    lesoes = []
    if focos.any():
        rot, n = rotular(focos)
        cont = np.bincount(rot.ravel(), minlength=n + 1)
        manter = [x for x in range(1, n + 1) if cont[x] * voxel_ml >= min_ml]
        if n - len(manter):
            res.avisos.append(f"{n - len(manter)} foco(s) menor(es) que {min_ml:.2f} mL ficaram de fora"
                              .replace(".", ","))
        mapa = np.zeros(pet.shape, np.uint8)
        for x in manter:
            idx = np.argwhere(rot == x)
            (k0, j0, i0), (k1, j1, i1) = idx.min(0), idx.max(0) + 1
            mk = rot[k0:k1, j0:j1, i0:i1] == x
            sub = suv[k0:k1, j0:j1, i0:i1]
            v = sub[mk]
            vol_ml = float(mk.sum() * voxel_ml)
            kk, jj, ii = idx.mean(0)
            centro = [float(c) for c in pet.voxel_to_patient(ii, jj, kk)]
            regiao, local = _regiao(mk, (k0, k1, j0, j1, i0, i1), osso, nome_osso, visc, org, centro, crista)
            pk = suv_peak(pet, sub / float(fator), mk, float(fator))
            les = Lesao(0, vol_ml, float(v.max()), float(v.mean()), pk, float(v.mean() * vol_ml), centro, regiao,
                        local)
            if res.tracador == "psma":
                les.mipsma = escore_mipsma(les.suvmax, res.refs)
            lesoes.append(les)
            mapa[k0:k1, j0:j1, i0:i1][mk] = _CODIGO[regiao]
        lesoes.sort(key=lambda x: -x.tlg)
        for i, x in enumerate(lesoes, start=1):
            x.n = i
        if mapa.any():
            kk, jj, ii = np.nonzero(mapa)
            a, b, c = kk.min(), jj.min(), ii.min()
            res.rotulo_mask = mapa[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
            res.offset = (int(a), int(b), int(c))
            res.centro = [float(x) for x in pet.voxel_to_patient(ii.mean(), jj.mean(), kk.mean())]
    res.lesoes = lesoes
    if lesoes:
        res.mtv = float(sum(x.vol_ml for x in lesoes))
        res.tlg = float(sum(x.tlg for x in lesoes))
        res.suvmax = float(max(x.suvmax for x in lesoes))
    # avisos
    if tirados:
        res.avisos.append("captação fisiológica tirada: " + ", ".join(_nome_org(x) for x in tirados))
    if res.tracador in ("psma", "sstr") and "liver" in tirados:
        res.avisos.append("o fígado está entre os órgãos tirados: lesão hepática não entra na conta — conferir")
    if res.tracador == "psma" and "parotida" not in res.refs:
        res.avisos.append("sem a parótida: o escore miPSMA vai no máximo até 2")
    if res.tracador == "fdg" and "figado_ref" not in res.refs and not float(config(settings, CHAVE_SUV_FDG) or 0):
        res.avisos.append("sem o fígado para o PERCIST: limiar SUV 2,5")
    res.avisos.append("limiar e máscaras automáticos: conferir cada foco — inflamação, músculo, gordura marrom e "
                      "intestino podem entrar; descartar nos Achados tira o foco do total do laudo")
    return res


def _nome_org(nome: str) -> str:
    return (_VISCERA.get(nome) or {"parotid_gland_left": "parótida esquerda", "parotid_gland_right": "parótida direita",
                                    "submandibular_gland_left": "submandibular esquerda",
                                    "submandibular_gland_right": "submandibular direita",
                                    "heart": "coração", "aorta": "aorta"}.get(nome) or nome.replace("_", " "))


def _nome_osso(nome: str) -> str:
    if nome.startswith("vertebrae_"):
        return "vértebra " + nome.split("_", 1)[1]
    if nome.startswith("rib_"):
        p = nome.split("_")
        return f"{p[2]}º arco costal {'direito' if p[1] == 'right' else 'esquerdo'}" if len(p) == 3 else "costela"
    return {"hip_left": "ilíaco esquerdo", "hip_right": "ilíaco direito", "sacrum": "sacro", "skull": "crânio",
            "sternum": "esterno", "femur_left": "fêmur esquerdo", "femur_right": "fêmur direito",
            "humerus_left": "úmero esquerdo", "humerus_right": "úmero direito", "scapula_left": "escápula esquerda",
            "scapula_right": "escápula direita", "clavicula_left": "clavícula esquerda",
            "clavicula_right": "clavícula direita"}.get(nome, nome.replace("_", " "))


def _regiao(mk, caixa, osso, nome_osso, visc, org, centro, crista):
    k0, k1, j0, j1, i0, i1 = caixa
    n = max(int(mk.sum()), 1)

    def fracao(m):
        return float(m[k0:k1, j0:j1, i0:i1][mk].sum()) / n
    if "prostate" in org and fracao(_dilatar(org["prostate"], 1)) >= 0.3:
        return "prost", "próstata"
    if fracao(_dilatar(osso, 1)) >= 0.3:
        melhor = max(nome_osso, key=lambda x: fracao(nome_osso[x]), default=None)
        return "osso", "osso" + (f" ({_nome_osso(melhor)})" if melhor else "")
    melhor, fr = None, 0.0
    for nome, m in visc.items():
        f = fracao(m)
        if f > fr:
            melhor, fr = nome, f
    if melhor is not None and fr >= 0.3:
        return "visc", ("pulmão " + ("direito" if "right" in melhor else "esquerdo")) if melhor.startswith(_PULMAO) \
            else _VISCERA[melhor]
    if crista is not None and centro[2] < crista:
        return "lnp", "linfonodo pélvico"
    return "lne", "linfonodo/partes moles extrapélvico" if crista is not None else "linfonodo/partes moles"


# ------------------------------------------------------------------ banco e laudo
def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def _nome_tlg(tracador: str) -> str:
    return "TLG" if tracador == "fdg" else "TL-PSMA" if tracador == "psma" else "TLA"


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado or not res.fator:
        return []
    eleg = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    base = {"series_uid": res.pet_series_uid or t.series_uid, "modelo": MODELO,
            "versao": versao or res.versao, "elegibilidade": eleg}
    tl = _nome_tlg(res.tracador)
    cont = {r: sum(1 for x in res.lesoes if x.regiao == r) for r in _CODIGO}
    num = {"n_lesoes": _n(len(res.lesoes), "", "Focos", 0), "mtv": _n(res.mtv, "mL", "Volume tumoral (MTV)"),
           "tlg": _n(res.tlg, "g" if res.tracador == "fdg" else "", tl), "suvmax": _n(res.suvmax, "", "SUVmáx"),
           "limiar": _n(res.limiar, "", "Limiar (SUV)", 2),
           "n_osso": _n(cont["osso"], "", "No osso", 0), "n_lnp": _n(cont["lnp"], "", "Linfonodos pélvicos", 0),
           "n_lne": _n(cont["lne"], "", "Linfonodos/partes moles extrapélvicos", 0),
           "n_visc": _n(cont["visc"], "", "Vísceras", 0)}
    for k, nome in (("figado", "Fígado (SUV médio)"), ("pool", "Pool sanguíneo (SUV médio)"),
                    ("parotida", "Parótida (SUV médio)")):
        if res.refs.get(k) is not None:
            num["ref_" + k] = _n(res.refs[k], "", nome, 2)
    local = TRACADORES.get(res.tracador, res.tracador) + (f" · {res.mitnm}" if res.mitnm else "") + \
        f" · limiar {res.limiar_como}"
    itens = [{**base, "rotulo": "T", "tipo": TIPO_RESUMO, "local": local, "posicao": res.centro, "numeros": num}]
    for x in res.lesoes[:MAX_ACHADOS]:
        nl = {"vol_ml": _n(x.vol_ml, "mL", "Volume", 2), "suvmax": _n(x.suvmax, "", "SUVmáx"),
              "suvmean": _n(x.suvmean, "", "SUVmédio"), "suvpeak": _n(x.suvpeak, "", "SUVpeak"),
              "tlg": _n(x.tlg, "", tl)}
        if x.mipsma is not None:
            nl["mipsma"] = _n(x.mipsma, "", "miPSMA", 0)
        itens.append({**base, "rotulo": f"L{x.n}", "tipo": TIPO_LESAO, "local": x.local, "posicao": x.centro,
                      "numeros": nl})
    if len(res.lesoes) > MAX_ACHADOS:
        itens[0]["elegibilidade"] += f"; {len(res.lesoes) - MAX_ACHADOS} focos menores não viraram achado"
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
                log.exception("trocar a SEG da carga tumoral anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.rotulo_mask is not None and res.rotulo_mask.any() and res.pet_vol is not None:
        segs = []
        for reg, cod in _CODIGO.items():
            m = res.rotulo_mask == cod
            if m.any():
                segs.append((SimpleNamespace(mask=m, offset=res.offset), f"Focos: {REGIOES[reg]}", CORES[reg]))
        ds = build_seg(res.pet_vol, segs, res.pet_vol.source_path, frames=res.pet_frames, series_number=SERIE_SEG,
                       description=DESC_SEG, algoritmo=("SEMIAUTOMATIC", f"limiar {res.limiar_como}"))
        tmp = Path(tempfile.mkdtemp(prefix="dv_carga_"))
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


def _f(v, casas=1) -> str:
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",")


def resumo(res: Resultado) -> str:
    if not res.fator:
        return res.avisos[0] if res.avisos else "sem SUV"
    tr_ = TRACADORES.get(res.tracador, res.tracador)
    if not res.lesoes:
        return f"{tr_}: nenhum foco acima do limiar ({res.limiar_como}) fora da captação fisiológica"
    s = (f"{tr_}: {len(res.lesoes)} foco(s), MTV {_f(res.mtv)} mL, {_nome_tlg(res.tracador)} {_f(res.tlg)}, "
         f"SUVmáx {_f(res.suvmax)}")
    return s + (f"; {res.mitnm}" if res.mitnm else "")


def n_itens(res: Resultado) -> int:
    return (1 + min(len(res.lesoes), MAX_ACHADOS)) if res.fator else 0


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Carga tumoral pronta em {minutos:.1f} min — {resumo(res)}. Cada foco está em Aplicações ▸ Achados de "
           f"IA: descarte a captação fisiológica que sobrou e o total do laudo acompanha; a máscara está na série "
           f"“{DESC_SEG}”.")
    avisos = [a for a in res.avisos if not a.startswith("limiar e máscaras")]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x, casas)
    partes = [f"SUVmáx {v('suvmax')}" if v("suvmax") else "", f"volume {v('vol_ml', 2)} mL" if v("vol_ml", 2) else "",
              f"miPSMA {v('mipsma', 0)}" if v("mipsma", 0) is not None else ""]
    partes = [p for p in partes if p]
    return "Foco captante" + (f" ({a['local']})" if a.get("local") else "") + \
        (", " + ", ".join(partes) if partes else "") + "."


def _regiao_do_local(local: str) -> str:
    s = _sem_acento(local or "").lower()
    if s.startswith("osso"):
        return "osso"
    if s.startswith("prostata"):
        return "prost"
    if s.startswith("linfonodo pelvico"):
        return "lnp"
    if s.startswith("linfonodo"):
        return "lne"
    return "visc"


def laudo(achados: list[dict]) -> str:
    """O texto do laudo pelos focos **confirmados** (descartar um foco tira ele do total): MTV, TLG, regiões e,
    no PSMA, o miTNM e os escores miPSMA."""
    valem = [a for a in achados if a.get("estado") in AC.VALEM and a.get("tipo") == TIPO_LESAO]
    resumo_a = next((a for a in achados if a.get("tipo") == TIPO_RESUMO), None)
    local_r = (resumo_a or {}).get("local", "")
    tracador = "psma" if local_r.startswith("PSMA") else "sstr" if local_r.startswith("análogo") else "fdg"
    tl = _nome_tlg(tracador)
    if not valem:
        return ""
    vols, tlgs, maxs, regioes, scores = [], [], [], [], []
    for a in valem:
        n = AC.numeros_validos(a)
        vols.append(float((n.get("vol_ml") or {}).get("v") or 0))
        tlgs.append(float((n.get("tlg") or {}).get("v") or 0))
        maxs.append(float((n.get("suvmax") or {}).get("v") or 0))
        regioes.append(_regiao_do_local(a.get("local", "")))
        if (n.get("mipsma") or {}).get("v") is not None:
            scores.append(int(float(n["mipsma"]["v"])))
    partes = [f"{regioes.count(r)} {REGIOES[r]}" for r in ("prost", "lnp", "lne", "osso", "visc") if regioes.count(r)]
    txt = (f"- Carga tumoral ({TRACADORES.get(tracador, tracador)}): {len(valem)} foco(s) confirmado(s) — "
           + ", ".join(partes) + f"; volume tumoral total {_f(sum(vols))} mL, {tl} {_f(sum(tlgs))}, "
           f"SUVmáx {_f(max(maxs))}.")
    if tracador == "psma":
        from types import SimpleNamespace
        txt += f"\n- Estadiamento molecular (PROMISE v2): {mitnm([SimpleNamespace(regiao=r) for r in regioes])}."
        if scores:
            txt += f" Escore miPSMA máximo {max(scores)}."
    linhas = [txt] + [f"- {frase(a)}" for a in valem]
    return "\n".join(linhas)
