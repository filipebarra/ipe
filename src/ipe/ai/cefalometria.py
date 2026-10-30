"""Cefalometria do cavum na TC, automática (0.99.15, etapa 1b da neuro).

Pedido dele: as medidas dos laudos de cefalometria (apneia do sono), feitas pela IA e conferidas
por ele. O TotalSegmentator (tarefas abertas, só TC) dá as estruturas; a geometria é feita aqui,
sem scipy, toda em coordenadas do paciente (mm, LPS: +x esquerda, +y posterior, +z superior):

| medida | de onde sai |
|---|---|
| área mínima da via aérea | ar (< −400 HU) dentro de naso/oro/hipofaringe (`head_glands_cavities`); eixo pela linha central; área **perpendicular ao eixo**, onde ela é menor (o pedido dele) |
| palato mole: comprimento e espessura | `soft_palate` no sagital mediano: ENP (junto do `hard_palate`) → ponta da úvula; espessura perpendicular a essa linha |
| espaço aéreo posterior | menor diâmetro AP da luz no sagital mediano: retropalatal (na altura do palato mole) e retrolingual (abaixo da úvula) |
| hioide ao plano mandibular | `mandible` (`craniofacial_structures`) projetada no sagital: Go–Me; distância **perpendicular** da linha à borda superior do `hyoid` (`headneck_bones_vessels`) |
| língua: transversal e AP | `tongue` (`head_muscles`) |
| nível do hioide na coluna | linha **horizontal** (axial) pelo corpo do hioide × corpos de C1–C7 (`total`) |

Nada aqui classifica o paciente além do que ele pediu (as três faixas da área mínima); o resto é
número com a referência entre parênteses, como no laudo dele. Tudo é proposta: a tela mostra de onde
cada número saiu e deixa trocar por uma medida feita à mão.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

MARCA = "· TotalSegmentator"
DESC_SEG = f"Cefalometria {MARCA}"
DESC_IMAGEM = f"Cefalometria: conferência {MARCA}"
SERIE_SEG, SERIE_IMAGEM = 976, 977
MIN_CORTES = 40

LIMIAR_AR = -400.0                     # HU: luz da via aérea
FAIXAS_AREA = (50.0, 100.0)            # mm²: < 50 acentuadamente reduzida; 50–100 moderadamente; > 100 normal

#: referências que vão entre parênteses no texto (Preferências podem trocar: `cefalo.referencias`)
CHAVE_REFERENCIAS = "cefalo.referencias"
REFERENCIAS = {
    "area": "> 100 mm²: normal; 50–100 mm²: moderadamente reduzida; < 50 mm²: acentuadamente reduzida",
    "palato_comprimento": "34 ± 6 mm",
    "palato_espessura": "10 ± 3 mm",
    "pas_retropalatal": "",
    "pas_retrolingual": "11 ± 2 mm",
    "hioide_mp": "17 ± 8 mm",
    "lingua_transversal": "até 50 mm",
    "lingua_ap": "até 75 mm",
    "hioide_nivel": "",
}

#: o que cada estrutura usa do TotalSegmentator (tarefa, classe)
ESTRUTURAS = {
    "soft_palate": ("head_glands_cavities", "Palato mole", (240, 140, 160)),
    "hard_palate": ("head_glands_cavities", "Palato duro", (250, 230, 200)),
    "nasopharynx": ("head_glands_cavities", "Nasofaringe", (90, 170, 250)),
    "oropharynx": ("head_glands_cavities", "Orofaringe", (60, 200, 240)),
    "hypopharynx": ("head_glands_cavities", "Hipofaringe", (60, 140, 220)),
    "hyoid": ("headneck_bones_vessels", "Hioide", (255, 220, 80)),
    "mandible": ("craniofacial_structures", "Mandíbula", (230, 230, 230)),
    "tongue": ("head_muscles", "Língua", (230, 120, 110)),
}
VERTEBRAS = [f"C{i}" for i in range(1, 8)]
FARINGE = ("nasopharynx", "oropharynx", "hypopharynx")


def tarefas(modalidade: str = "CT", settings=None) -> list[dict]:
    """As tarefas do TotalSegmentator, todas abertas e de TC. `cefalo` marca para o modo simulado."""
    return [
        {"nome": "head_glands_cavities", "rotulo": "palato e faringe", "cefalo": True},
        {"nome": "headneck_bones_vessels", "rotulo": "hioide", "cefalo": True},
        {"nome": "craniofacial_structures", "rotulo": "mandíbula", "cefalo": True},
        {"nome": "head_muscles", "rotulo": "língua", "cefalo": True},
        {"nome": "total", "roi": [f"vertebrae_{v}" for v in VERTEBRAS], "fast": True,
         "rotulo": "vértebras cervicais", "cefalo": True},
    ]


def referencias(settings=None) -> dict:
    r = dict(REFERENCIAS)
    try:
        extra = settings.get(CHAVE_REFERENCIAS, None) if settings is not None else None
    except Exception:  # noqa: BLE001
        extra = None
    if isinstance(extra, dict):
        r.update({k: str(v) for k, v in extra.items() if k in r})
    return r


# ------------------------------------------------------------------ resultado
@dataclass
class Medida:
    id: str
    nome: str
    valor: float | None = None
    unidade: str = "mm"
    texto: str = ""                     # o que não é número (nível do hioide, local da área mínima)
    motivo: str = ""                    # por que não saiu
    linhas: list = field(default_factory=list)      # [(p0, p1)] em mm (paciente) para a conferência
    origem: str = "automático"          # "automático" | "editado"
    casas: int = 1

    def texto_valor(self) -> str:
        if self.valor is None:
            return self.texto or "—"
        v = f"{self.valor:.{self.casas}f}".replace(".", ",")
        return f"{v} {self.unidade}".strip()


@dataclass
class Cefalometria:
    medidas: dict = field(default_factory=dict)     # id -> Medida, na ordem do laudo
    perfil: list = field(default_factory=list)      # [(z mm, área mm²)] ao longo do eixo
    avisos: list = field(default_factory=list)
    x_meio: float | None = None                     # sagital mediano (mm, x do paciente)
    estruturas: dict = field(default_factory=dict)  # nome -> (máscara recortada, offset) para a SEG

    def __getitem__(self, k: str) -> Medida:
        return self.medidas[k]


ORDEM = ("area", "palato_comprimento", "palato_espessura", "pas_retropalatal", "pas_retrolingual",
         "hioide_mp", "lingua_transversal", "lingua_ap", "hioide_nivel")
#: o número de cada medida no laudo dele (a área vem antes, sem número; o espaço aéreo é um item só)
NUMERO = {"area": "", "palato_comprimento": "1", "palato_espessura": "2", "pas_retropalatal": "3",
          "pas_retrolingual": "3", "hioide_mp": "4", "lingua_transversal": "5", "lingua_ap": "6",
          "hioide_nivel": "7"}
NOMES = {
    "area": "Área de secção transversal mínima da via aérea",
    "palato_comprimento": "Comprimento do palato mole",
    "palato_espessura": "Espessura do palato mole",
    "pas_retropalatal": "Espaço aéreo posterior retropalatal",
    "pas_retrolingual": "Espaço aéreo posterior retrolingual",
    "hioide_mp": "Distância do hioide ao plano mandibular",
    "lingua_transversal": "Espessura transversal da língua",
    "lingua_ap": "Comprimento anteroposterior da língua",
    "hioide_nivel": "Nível do hioide em relação à coluna",
}


def classe_da_area(area: float) -> str:
    baixo, alto = FAIXAS_AREA
    if area < baixo:
        return "acentuadamente reduzida"
    if area <= alto:
        return "moderadamente reduzida"
    return "normal"


# ------------------------------------------------------------------ máscaras e pontos
class Mascaras:
    """{nome da classe: máscara bool (k, j, i)} a partir do que o trabalhador devolveu."""

    def __init__(self, vol, rotulos: dict):
        self.vol = vol
        self._onde = {}
        for tarefa, (lab, classes) in (rotulos or {}).items():
            if lab.shape != vol.data.shape:
                raise ValueError(f"{tarefa}: grade {lab.shape} diferente do volume {vol.data.shape}")
            for cid, nome in classes.items():
                self._onde.setdefault(nome, (lab, int(cid)))

    def tem(self, nome: str) -> bool:
        return nome in self._onde and bool((self._onde[nome][0] == self._onde[nome][1]).any())

    def get(self, nome: str):
        if nome not in self._onde:
            return None
        lab, cid = self._onde[nome]
        m = lab == cid
        return m if m.any() else None

    def vertebra(self, v: str):
        return self.get(f"vertebrae_{v}")


def _M(vol) -> np.ndarray:
    return np.asarray(vol.matrix(), float)


def pontos(vol, mascara, offset=(0, 0, 0)) -> np.ndarray:
    """N×3, mm do paciente, dos voxels da máscara (k, j, i) — `offset` de um recorte."""
    k, j, i = np.nonzero(mascara)
    if not len(k):
        return np.zeros((0, 3))
    ijk = np.stack([i + offset[2], j + offset[1], k + offset[0]]).astype(float)
    return (np.asarray(vol.origin, float)[:, None] + _M(vol) @ ijk).T


def _recorte(m: np.ndarray, margem: int = 0):
    idx = np.nonzero(m.any(axis=(1, 2)))[0], np.nonzero(m.any(axis=(0, 2)))[0], np.nonzero(m.any(axis=(0, 1)))[0]
    lo = [max(0, int(a[0]) - margem) for a in idx]
    hi = [min(s, int(a[-1]) + 1 + margem) for a, s in zip(idx, m.shape)]
    return tuple(slice(a, b) for a, b in zip(lo, hi)), tuple(lo)


def _dilatar(m: np.ndarray, n: int) -> np.ndarray:
    m = m.copy()
    for _ in range(n):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        d[:, :, 1:] |= m[:, :, :-1]
        d[:, :, :-1] |= m[:, :, 1:]
        m = d
    return m


def _alastrar_2d(m: np.ndarray, semente: tuple[int, int]) -> np.ndarray:
    """O pedaço conexo (4 vizinhos) de `m` que contém a semente."""
    out = np.zeros_like(m)
    out[semente] = True
    while True:
        d = out.copy()
        d[1:] |= out[:-1]
        d[:-1] |= out[1:]
        d[:, 1:] |= out[:, :-1]
        d[:, :-1] |= out[:, 1:]
        d &= m
        if d.sum() == out.sum():
            return out
        out = d


def _passo_no_plano(vol) -> float:
    return float(min(vol.dx, vol.dy))


def _passo_z(vol) -> float:
    """O tamanho do voxel no eixo crânio-caudal do paciente (para somar à extensão medida)."""
    M = _M(vol)
    return float(max(abs(M[2, 0]), abs(M[2, 1]), abs(M[2, 2])))


# ------------------------------------------------------------------ geometria 2D (sagital: y, z)
def _casco(p: np.ndarray) -> np.ndarray:
    """Casco convexo (cadeia monótona) de pontos 2D; devolve o casco inferior e o superior juntos
    em ordem anti-horária, começando no de menor y."""
    pts = np.unique(np.round(p, 2), axis=0)
    if len(pts) < 3:
        return pts

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    inf, sup = [], []
    for q in pts:
        while len(inf) >= 2 and cruz(inf[-2], inf[-1], q) <= 0:
            inf.pop()
        inf.append(tuple(q))
    for q in pts[::-1]:
        while len(sup) >= 2 and cruz(sup[-2], sup[-1], q) <= 0:
            sup.pop()
        sup.append(tuple(q))
    return np.array(inf), np.array(sup)


def _casco_inferior(p: np.ndarray) -> np.ndarray:
    r = _casco(p)
    return r[0] if isinstance(r, tuple) else r


def plano_mandibular(mand_yz: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """(Go, Me) no sagital (y, z). Me: o ponto mais baixo da sínfise (o terço anterior). Go: onde a
    borda inferior vira o ramo — andando pelo casco inferior a partir do Me para trás, o último
    vértice antes de a borda subir mais de 45°."""
    if len(mand_yz) < 50:
        return None
    y, z = mand_yz[:, 0], mand_yz[:, 1]
    inf = _casco_inferior(mand_yz)                  # de y menor (anterior) para y maior (posterior)
    if len(inf) < 3:
        return None
    y0, y1 = float(y.min()), float(y.max())
    anteriores = [n for n, v in enumerate(inf) if v[0] <= y0 + 0.25 * (y1 - y0)]
    if not anteriores:
        return None
    i_me = min(anteriores, key=lambda n: inf[n][1])
    me = inf[i_me]
    i_go = i_me
    for n in range(i_me, len(inf) - 1):
        dy, dz = inf[n + 1][0] - inf[n][0], inf[n + 1][1] - inf[n][1]
        if dy <= 0 or np.degrees(np.arctan2(dz, dy)) > 45.0:
            break
        i_go = n + 1
    if i_go == i_me:
        return None
    return np.asarray(inf[i_go], float), np.asarray(me, float)


# ------------------------------------------------------------------ a conta
def _meio(ms: Mascaras, vol) -> float | None:
    for nomes in (("soft_palate", "hard_palate", "tongue"), FARINGE, ("mandible",)):
        ps = [pontos(vol, m) for m in (ms.get(n) for n in nomes) if m is not None]
        ps = [p for p in ps if len(p)]
        if ps:
            return float(np.median(np.concatenate(ps)[:, 0]))
    return None


def _fatia_sagital(p: np.ndarray, x: float, meia: float) -> np.ndarray:
    s = p[np.abs(p[:, 0] - x) <= meia]
    return s if len(s) >= 20 else p


def _faixas(valores: np.ndarray, vao: float) -> list[tuple[float, float]]:
    """Pedaços contínuos de uma lista de coordenadas (y numa altura): [(início, fim)]."""
    v = np.sort(valores)
    quebras = np.nonzero(np.diff(v) > vao)[0]
    ini = np.concatenate([[0], quebras + 1])
    fim = np.concatenate([quebras, [len(v) - 1]])
    return [(float(v[a]), float(v[b])) for a, b in zip(ini, fim)]


def calcular(vol, rotulos: dict, settings=None) -> Cefalometria:
    ms = Mascaras(vol, rotulos)
    res = Cefalometria()
    for k in ORDEM:
        res.medidas[k] = Medida(k, NOMES[k], unidade="mm²" if k == "area" else "mm",
                                casas=0 if k == "area" else 1)
    res.medidas["hioide_nivel"].unidade = ""
    res.x_meio = xm = _meio(ms, vol)
    if xm is None:
        res.avisos.append("o modelo não achou palato, faringe nem mandíbula nesta série")
        for m in res.medidas.values():
            m.motivo = "estruturas não encontradas"
        return res
    h = _passo_no_plano(vol)
    hz = _passo_z(vol)

    # --- palato mole: ENP → úvula, espessura -------------------------------------------------
    palato = ms.get("soft_palate")
    zp = None                                         # (z da ENP, z da ponta da úvula)
    if palato is None:
        for k in ("palato_comprimento", "palato_espessura"):
            res.medidas[k].motivo = "palato mole não segmentado"
    else:
        pp = _fatia_sagital(pontos(vol, palato), xm, 2.5)
        yz = pp[:, 1:]
        duro = ms.get("hard_palate")
        if duro is not None:
            dd = _fatia_sagital(pontos(vol, duro), xm, 2.5)
            enp_ref = dd[np.argmax(dd[:, 1])][1:]             # o ponto mais posterior do palato duro
            ini = yz[np.argmin(np.linalg.norm(yz - enp_ref, axis=1))]
        else:
            ini = yz[np.argmax(yz[:, 1] - yz[:, 0])]          # o mais alto e anterior
            res.avisos.append("palato duro não segmentado: a ENP foi estimada pela ponta do palato mole")
        fim = yz[np.argmax(np.linalg.norm(yz - ini, axis=1))]
        L = float(np.linalg.norm(fim - ini))
        mc = res.medidas["palato_comprimento"]
        mc.valor = L
        mc.linhas = [(np.r_[xm, ini], np.r_[xm, fim])]
        zp = (float(max(ini[1], fim[1])), float(min(ini[1], fim[1])))
        if L > 5:
            a = (fim - ini) / L
            n = np.array([-a[1], a[0]])
            s, w = (yz - ini) @ a, (yz - ini) @ n
            melhor, onde = 0.0, None
            for s0 in np.arange(0.1 * L, 0.9 * L, 1.0):
                sel = np.abs(s - s0) <= 0.5
                if sel.sum() < 2:
                    continue
                larg = float(w[sel].max() - w[sel].min()) + h
                if larg > melhor:
                    melhor, onde = larg, (s0, float(w[sel].min()), float(w[sel].max()))
            me = res.medidas["palato_espessura"]
            if onde is not None:
                me.valor = melhor
                p0 = ini + a * onde[0] + n * onde[1]
                p1 = ini + a * onde[0] + n * onde[2]
                me.linhas = [(np.r_[xm, p0], np.r_[xm, p1])]
            else:
                me.motivo = "palato mole fino demais para medir"

    # --- via aérea: luz, eixo, área perpendicular mínima -------------------------------------
    regiao = None
    for n in FARINGE:
        m = ms.get(n)
        if m is not None:
            regiao = m if regiao is None else (regiao | m)
    hioide = ms.get("hyoid")
    p_hi = _fatia_sagital(pontos(vol, hioide), xm, 8.0) if hioide is not None else None
    oro = ms.get("oropharynx")
    z_baixo = None
    if oro is not None:
        z_baixo = float(pontos(vol, oro)[:, 2].min())
    elif p_hi is not None and len(p_hi):
        z_baixo = float(p_hi[:, 2].max())
    if regiao is None:
        for k in ("area", "pas_retropalatal", "pas_retrolingual"):
            res.medidas[k].motivo = "faringe não segmentada"
    else:
        fat, off = _recorte(regiao, margem=4)
        ar = _dilatar(regiao[fat], 2) & (np.asarray(vol.data[fat]) < LIMIAR_AR)
        pa = pontos(vol, ar, off)
        if len(pa) < 50:
            for k in ("area", "pas_retropalatal", "pas_retrolingual"):
                res.medidas[k].motivo = "sem ar na faringe (via aérea colabada ou fora da série)"
        else:
            _via_aerea(vol, ar, off, pa, zp, z_baixo, res, h, hz)

    # --- hioide ao plano mandibular -----------------------------------------------------------
    mand = ms.get("mandible")
    mh = res.medidas["hioide_mp"]
    if mand is None:
        mh.motivo = "mandíbula não segmentada"
    elif p_hi is None or not len(p_hi):
        mh.motivo = "hioide não segmentado"
    else:
        pm = pontos(vol, mand)
        if len(pm) > 200000:
            pm = pm[:: len(pm) // 200000 + 1]
        gm = plano_mandibular(pm[:, 1:])
        if gm is None:
            mh.motivo = "não deu para traçar o plano mandibular (mandíbula incompleta?)"
        else:
            go, me = gm
            d = go - me
            d = d / np.linalg.norm(d)
            nrm = np.array([-d[1], d[0]])
            if nrm[1] > 0:                               # a normal aponta para baixo (caudal)
                nrm = -nrm
            yz = p_hi[:, 1:]
            dist = (yz - me) @ nrm
            i = int(np.argmin(dist))
            mh.valor = float(dist[i])
            pe = yz[i] - nrm * dist[i]
            mh.linhas = [(np.r_[xm, go], np.r_[xm, me]), (np.r_[xm, yz[i]], np.r_[xm, pe])]
            if mh.valor < 0:
                mh.texto = "hioide acima do plano mandibular"

    # --- nível do hioide na coluna ------------------------------------------------------------
    nv = res.medidas["hioide_nivel"]
    if p_hi is None or not len(p_hi):
        nv.motivo = "hioide não segmentado"
    else:
        z_h = float(np.median(p_hi[:, 2]))
        corpos = {}
        for v in VERTEBRAS:
            m = ms.vertebra(v)
            if m is None:
                continue
            pv = pontos(vol, m)
            corpo = pv[pv[:, 1] <= np.median(pv[:, 1])]      # o corpo é a metade anterior
            corpos[v] = (float(np.percentile(corpo[:, 2], 2)), float(np.percentile(corpo[:, 2], 98)))
        nv.texto = nivel_na_coluna(z_h, corpos)
        if not nv.texto:
            nv.motivo = "vértebras cervicais não segmentadas na altura do hioide"
        else:
            yh = float(np.median(p_hi[:, 1]))
            nv.linhas = [(np.r_[xm, yh - 15, z_h], np.r_[xm, yh + 60, z_h])]

    # --- língua -------------------------------------------------------------------------------
    lingua = ms.get("tongue")
    if lingua is None:
        for k in ("lingua_transversal", "lingua_ap"):
            res.medidas[k].motivo = "língua não segmentada"
    else:
        pl = pontos(vol, lingua)
        melhor, onde = 0.0, None
        for z0 in np.arange(pl[:, 2].min(), pl[:, 2].max() + 0.01, 1.0):
            sel = np.abs(pl[:, 2] - z0) <= 0.5
            if sel.sum() < 2:
                continue
            xs = pl[sel, 0]
            larg = float(xs.max() - xs.min()) + h
            if larg > melhor:
                melhor = larg
                y0 = float(np.median(pl[sel, 1]))
                onde = (np.array([xs.min(), y0, z0]), np.array([xs.max(), y0, z0]))
        mt = res.medidas["lingua_transversal"]
        mt.valor, mt.linhas = (melhor, [onde]) if onde is not None else (None, [])
        sl = _fatia_sagital(pl, xm, 3.0)
        ia, ib = int(np.argmin(sl[:, 1])), int(np.argmax(sl[:, 1]))
        ma = res.medidas["lingua_ap"]
        ma.valor = float(sl[ib, 1] - sl[ia, 1]) + h
        za = float(np.median(sl[:, 2]))
        ma.linhas = [(np.array([xm, sl[ia, 1], za]), np.array([xm, sl[ib, 1], za]))]

    # --- máscaras para a SEG de conferência -------------------------------------------------
    for nome in ESTRUTURAS:
        m = ms.get(nome)
        if m is not None:
            fat, off = _recorte(m)
            res.estruturas[nome] = (m[fat], off)
    for v in VERTEBRAS:
        m = ms.vertebra(v)
        if m is not None:
            fat, off = _recorte(m)
            res.estruturas[f"vertebrae_{v}"] = (m[fat], off)
    return res


def nivel_na_coluna(z: float, corpos: dict) -> str:
    """"platô inferior de C3", "corpo de C3", "disco C3-C4"… — a altura z (mm) contra os corpos
    vertebrais {C3: (z de baixo, z de cima)}."""
    nomes = [v for v in VERTEBRAS if v in corpos]
    for v in nomes:
        lo, hi = corpos[v]
        if lo <= z <= hi:
            f = (hi - z) / max(hi - lo, 1e-6)
            if f < 0.25:
                return f"platô superior de {v}"
            if f > 0.75:
                return f"platô inferior de {v}"
            return f"corpo de {v}"
    for a, b in zip(nomes, nomes[1:]):
        if VERTEBRAS.index(b) == VERTEBRAS.index(a) + 1 and corpos[b][1] < z < corpos[a][0]:
            return f"disco {a}-{b}"
    if nomes:
        if z > corpos[nomes[0]][1]:
            return f"acima de {nomes[0]}"
        if z < corpos[nomes[-1]][0]:
            return f"abaixo de {nomes[-1]}"
    return ""


def _base_ortonormal(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.array([1.0, 0.0, 0.0]) if abs(t[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = a - (a @ t) * t
    u /= np.linalg.norm(u)
    return u, np.cross(t, u)


def secao(vol, ar: np.ndarray, off, c: np.ndarray, t: np.ndarray, raio: float = 30.0, passo: float = 0.4):
    """Área (mm²) do pedaço de luz que o plano perpendicular a `t` em `c` corta, e as duas maiores
    extensões (lateral ≈ u, outra ≈ v) — ou (0, 0, 0) se o plano não acha luz perto do eixo."""
    u, v = _base_ortonormal(t)
    g = np.arange(-raio, raio + 1e-6, passo)
    A, B = np.meshgrid(g, g, indexing="ij")
    P = c[None, None, :] + A[..., None] * u + B[..., None] * v
    Minv = np.linalg.inv(_M(vol))
    ijk = (P.reshape(-1, 3) - np.asarray(vol.origin, float)) @ Minv.T
    idx = np.rint(ijk).astype(int) - np.array([off[2], off[1], off[0]])
    nk, nj, ni = ar.shape
    dentro = (idx[:, 0] >= 0) & (idx[:, 0] < ni) & (idx[:, 1] >= 0) & (idx[:, 1] < nj) & \
             (idx[:, 2] >= 0) & (idx[:, 2] < nk)
    m = np.zeros(len(idx), bool)
    q = idx[dentro]
    m[dentro] = ar[q[:, 2], q[:, 1], q[:, 0]]
    m = m.reshape(A.shape)
    if not m.any():
        return 0.0, 0.0, 0.0
    d = np.hypot(A, B)
    d[~m] = np.inf
    s = np.unravel_index(int(np.argmin(d)), d.shape)
    if d[s] > 6.0:
        return 0.0, 0.0, 0.0
    peca = _alastrar_2d(m, s)
    area = float(peca.sum()) * passo * passo
    ea = float(np.ptp(A[peca])) + passo
    eb = float(np.ptp(B[peca])) + passo
    return area, ea, eb


def _via_aerea(vol, ar, off, pa, zp, z_baixo, res: Cefalometria, h: float, hz: float) -> None:
    # linha central: centroide da luz em cada milímetro de altura, suavizada
    z0, z1 = float(pa[:, 2].min()), float(pa[:, 2].max())
    cent = []
    for z in np.arange(z1, z0 - 0.01, -1.0):
        sel = np.abs(pa[:, 2] - z) <= 0.5
        if sel.sum() * h * h >= 2.0:
            cent.append(pa[sel].mean(axis=0))
    if len(cent) < 5:
        for k in ("area", "pas_retropalatal", "pas_retrolingual"):
            res.medidas[k].motivo = "luz da via aérea curta demais"
        return
    cent = np.array(cent)
    jan = 7
    pad = np.pad(cent, ((jan // 2, jan // 2), (0, 0)), mode="edge")
    liso = np.array([pad[i:i + jan].mean(axis=0) for i in range(len(cent))])
    tang = np.gradient(liso, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1)[:, None], 1e-9)

    z_cima = zp[0] if zp is not None else z1
    z_fim = z_baixo if z_baixo is not None else z0
    melhor = None
    for c, t in zip(liso, tang):
        a, ea, eb = secao(vol, ar, off, c, t)
        res.perfil.append((float(c[2]), a))
        if z_fim - 0.5 <= c[2] <= z_cima + 0.5 and a > 0 and (melhor is None or a < melhor[0]):
            melhor = (a, c, t, ea, eb)
    ma = res.medidas["area"]
    if melhor is None:
        ma.motivo = "não achei a luz entre o palato e a base da língua"
    else:
        a, c, t, ea, eb = melhor
        ma.valor = a
        ma.texto = local_da_area(float(c[2]), zp)
        u, v = _base_ortonormal(t)
        ma.linhas = [(c - u * ea / 2, c + u * ea / 2), (c - v * eb / 2, c + v * eb / 2)]

    # espaço aéreo posterior: menor AP da luz no sagital mediano (perto do eixo), por altura
    ap = []
    for c in liso:
        sel = (np.abs(pa[:, 2] - c[2]) <= 0.5) & (np.abs(pa[:, 0] - c[0]) <= 2.0)
        if sel.sum() < 2:
            continue
        faixas = _faixas(pa[sel, 1], 1.6 * h)
        f = min(faixas, key=lambda ab: 0 if ab[0] <= c[1] <= ab[1] else min(abs(ab[0] - c[1]), abs(ab[1] - c[1])))
        ap.append((float(c[2]), f[1] - f[0] + h, float(c[0]), f))
    for k, faixa_z in (("pas_retropalatal", (zp[1], zp[0]) if zp else None),
                       ("pas_retrolingual", (z_baixo, zp[1]) if zp and z_baixo is not None else None)):
        m = res.medidas[k]
        if faixa_z is None:
            m.motivo = "sem o palato mole não dá para separar retropalatal de retrolingual" if zp is None \
                else "sem a orofaringe nem o hioide não dá para saber até onde vai a base da língua"
            continue
        lo, hi = min(faixa_z), max(faixa_z)
        cand = [x for x in ap if lo - 0.5 <= x[0] <= hi + 0.5]
        if not cand:
            m.motivo = "a luz não aparece nesta altura"
            continue
        z, d, x, f = min(cand, key=lambda q: q[1])
        m.valor = d
        m.linhas = [(np.array([x, f[0], z]), np.array([x, f[1], z]))]


def local_da_area(z: float, zp) -> str:
    """Onde está a área mínima: terço do palato mole (retropalatal) ou retrolingual."""
    if zp is None:
        return ""
    cima, baixo = zp
    if z > cima:
        return "na nasofaringe, acima do palato mole"
    if z < baixo:
        return "retrolingual"
    f = (cima - z) / max(cima - baixo, 1e-6)
    if f < 1 / 3:
        return "no terço superior do palato mole (retropalatal)"
    if f < 2 / 3:
        return "no terço médio do palato mole (retropalatal)"
    return "no terço inferior do palato mole (retropalatal)"


# ------------------------------------------------------------------ o texto do laudo
def _ref(refs: dict, k: str) -> str:
    r = refs.get(k, "")
    return f" ({r})" if r else ""


def texto_do_laudo(res: Cefalometria, settings=None, automatica: bool = True) -> str:
    """No formato dos laudos dele: a área mínima com o local e a faixa, depois a lista numerada com
    a referência entre parênteses."""
    refs = referencias(settings)
    m = res.medidas
    linhas = ["Cefalometria por TC:"]
    a = m["area"]
    if a.valor is not None:
        local = f", {a.texto}" if a.texto else ""
        linhas.append(f"Área de secção transversal mínima da via aérea: {a.texto_valor()}{local} — "
                      f"{classe_da_area(a.valor)}{_ref(refs, 'area')}.")
    itens = []
    for k in ("palato_comprimento", "palato_espessura"):
        if m[k].valor is not None:
            itens.append(f"{m[k].nome}: {m[k].texto_valor()}{_ref(refs, k)}.")
    rp, rl = m["pas_retropalatal"], m["pas_retrolingual"]
    if rp.valor is not None or rl.valor is not None:
        partes = []
        if rp.valor is not None:
            partes.append(f"retropalatal {rp.texto_valor()}{_ref(refs, 'pas_retropalatal')}")
        if rl.valor is not None:
            partes.append(f"retrolingual {rl.texto_valor()}{_ref(refs, 'pas_retrolingual')}")
        itens.append("Espaço aéreo posterior: " + "; ".join(partes) + ".")
    for k in ("hioide_mp", "lingua_transversal", "lingua_ap"):
        if m[k].valor is not None:
            extra = f" ({m[k].texto})" if k == "hioide_mp" and m[k].texto else ""
            itens.append(f"{m[k].nome}: {m[k].texto_valor()}{extra}{_ref(refs, k)}.")
    if m["hioide_nivel"].texto:
        itens.append(f"{m['hioide_nivel'].nome}: {m['hioide_nivel'].texto}{_ref(refs, 'hioide_nivel')}.")
    linhas += [f"{n}. {t}" for n, t in enumerate(itens, start=1)]
    editadas = [x.nome.lower() for x in m.values() if x.origem == "editado"]
    if editadas and automatica:
        linhas.append("Medidas conferidas e corrigidas à mão: " + ", ".join(editadas) + ".")
    return "\n".join(linhas)


def resumo(res: Cefalometria) -> str:
    feitas = [x for x in res.medidas.values() if x.valor is not None or (x.texto and not x.motivo)]
    a = res.medidas["area"]
    txt = f"medidas feitas: {len(feitas)} de {len(res.medidas)}"
    if a.valor is not None:
        txt += f"; área mínima {a.texto_valor()} ({classe_da_area(a.valor)})"
    return txt
