"""Diâmetro da aorta perpendicular ao eixo, por segmento (0.99.90; backlog IA 8).

A aorta vem do TotalSegmentator (tarefa `total`, que é aberta; o relatório oficial de aorta deles é pago). Daí:

1. **Linha central**: a máscara vira uma grade de 2 mm; cada ponto ganha a profundidade (quantas erosões até
   sumir). A ponta distal é o ponto mais baixo (bifurcação ou o fim da série); a proximal, o ponto mais longe dela
   por dentro da aorta (a raiz, quando a série pega o coração). O caminho entre as duas é o de menor custo, com
   custo maior perto da parede, e depois é suavizado e reamostrado a cada 2 mm.
2. **Plano perpendicular** em cada ponto (a tangente da linha central): a máscara é amostrada num plano de 0,5 mm
   e fica o pedaço que contém o centro. Mede-se o **diâmetro máximo** (o maior calibre entre 36 direções), o
   **perpendicular a ele** e o diâmetro do círculo de mesma área.
3. **Segmentos** pelos marcos do TotalSegmentator: **raiz** (os primeiros 15 mm, quando a série começa no
   coração); **ascendente** até a origem do tronco braquiocefálico; **arco** até 10 mm depois da subclávia
   esquerda; **descendente torácica** até o hiato (borda de baixo de T12); **abdominal suprarrenal** até a altura
   do meio dos rins; **infrarrenal** até o fim. Sem os ramos do arco, o arco é o trecho de 30 mm de cada lado do
   ponto mais alto. Em cada segmento sai o maior diâmetro (com o perpendicular e a posição).

A medida é **da parede externa à externa** (a máscara do TotalSegmentator pega a parede e o trombo), em plano
perpendicular ao eixo. A ACC/AHA (2022) pede a raiz e a ascendente de borda interna a interna em TC
sincronizada com o ECG; sem ECG, a raiz não vale. Referências como texto, nunca veredito:

- ascendente e arco: ≥ 40 mm costuma ser relatado como dilatação; ≥ 55 mm (≥ 50 mm em centro experiente) é o
  limiar de cirurgia da ACC/AHA 2022; descendente: ≥ 55 mm;
- infrarrenal: aneurisma ≥ 30 mm (ou 1,5 × o normal); o ACR (Khosa et al., JACR 2013) sugere controle em 5 anos
  para 25–29 mm, 3 anos para 30–34, 2 anos para 35–39, 1 ano para 40–44, 6 meses para 45–49 e 3–6 meses para
  50–55 mm.

Saída: SEG "Aorta por segmento · Ipê" (série 978, um segmento por trecho) e os achados: o resumo A e um por
segmento (RZ, AA, AR, DT, AS, AI). O texto do laudo leva os confirmados ou corrigidos.
"""
from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "aorta"
TITULO = "Diâmetro da aorta perpendicular ao eixo, por segmento"
MARCA = "· Ipê"
DESC_SEG = f"Aorta por segmento {MARCA}"
SERIE_SEG = 978
MIN_CORTES = 30
MODALIDADES = ("CT",)
MOTIVO_MODALIDADE = "O diâmetro da aorta é medido na TC."
MODELO = "TotalSegmentator (aorta e marcos) + linha central e planos perpendiculares"
CHAVE_SAIDA = "aorta"
TIPO_RESUMO = "Aorta: diâmetros"
TIPO_SEG = "Aorta: segmento"

GRADE_MM = 2.0
PASSO_MM = 2.0
PIXEL_PLANO = 0.5
RAIZ_MM = 15.0
ARCO_SEM_RAMOS_MM = 30.0
DEPOIS_SUBCLAVIA_MM = 10.0

SEGMENTOS = {"RZ": "raiz da aorta (seios)", "AA": "aorta ascendente", "AR": "arco aórtico",
             "DT": "aorta descendente torácica", "AS": "aorta abdominal suprarrenal",
             "AI": "aorta abdominal infrarrenal"}
ORDEM = tuple(SEGMENTOS)
CODIGO = {s: i for i, s in enumerate(ORDEM, start=1)}
CORES = {"RZ": (250, 200, 60), "AA": (240, 90, 80), "AR": (240, 150, 60), "DT": (80, 160, 250),
         "AS": (80, 210, 150), "AI": (190, 110, 250)}
#: diâmetro (mm) a partir do qual a referência é lembrada, e o texto
REFERENCIA = {
    "RZ": (40.0, "≥ 40 mm costuma ser relatado como dilatação; a raiz se mede seio a seio, com ECG"),
    "AA": (40.0, "≥ 40 mm costuma ser relatado como dilatação; ≥ 55 mm (≥ 50 mm em centro experiente) é o limiar "
                 "de cirurgia (ACC/AHA 2022)"),
    "AR": (40.0, "≥ 40 mm costuma ser relatado como dilatação; ≥ 55 mm, cirurgia (ACC/AHA 2022)"),
    "DT": (40.0, "≥ 40 mm costuma ser relatado como dilatação; ≥ 55 mm, reparo (ACC/AHA 2022)"),
    "AS": (30.0, "o normal da suprarrenal vai até ~30 mm (ACR 2013)"),
    "AI": (30.0, "aneurisma ≥ 30 mm (ACR 2013)"),
}
_CONTROLE_ACR = ((25, 30, "5 anos"), (30, 35, "3 anos"), (35, 40, "2 anos"), (40, 45, "1 ano"), (45, 50, "6 meses"),
                 (50, 55.5, "3 a 6 meses"))

ORGAOS = (["aorta", "heart", "brachiocephalic_trunk", "common_carotid_artery_left", "subclavian_artery_left",
           "kidney_left", "kidney_right", "iliac_artery_left", "iliac_artery_right", "vertebrae_T12"])

CHAVE_AUTO = "aorta.auto"
CHAVE_EXAME_CONTEM = "aorta.exame_contem"
CHAVE_MODALIDADES = "aorta.modalidades"
CHAVE_PRIOR_CT = "aorta.prioridade"
CHAVE_ESPESSURA = "aorta.espessura_max"
CHAVE_MIN_CORTES = "aorta.min_cortes"
CHAVE_DESTINOS = "aorta.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "AORTA|ANGIO|TORAX|TÓRAX|CHEST|THORAX|ABD|ABDOM|TAP|CORPO",
    CHAVE_MODALIDADES: ["CT"],
    CHAVE_PRIOR_CT: "AORTA|ANGIO|ARTERIAL|CTA|PORTAL|VENOSA|STANDARD|STD|PARTES MOLES|MEDIASTINO|SOFT|B30|BR40",
    CHAVE_ESPESSURA: 3.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("TOPO", "SCOUT", "LOCALIZER", "MIP", "DOSE", "SURVIEW", "PATIENT PROTOCOL", "PULMAO",
                      "LUNG", "OSSO", "BONE")}
NOME_CADIA = "Aorta: diâmetro por segmento"
TITULO_CADIA = "Diâmetro da aorta perpendicular ao eixo, da raiz à bifurcação, por segmento"
EXPLICACAO_CADIA = ("Na TC de tórax ou de abdome (com ou sem contraste): o TotalSegmentator acha a aorta e os marcos "
                    "(tronco braquiocefálico, subclávia esquerda, T12, rins); o programa traça a linha central e "
                    "mede, em planos perpendiculares a ela, o diâmetro máximo e o perpendicular de cada segmento "
                    "(raiz, ascendente, arco, descendente, abdominal suprarrenal e infrarrenal), da parede externa à "
                    "externa. Cada segmento está em Achados de IA, com a referência como texto.")
CHAVES_RESUMO = ("dmax", "segmento_max", "comprimento")
CHAVES_SEG = ("dmax", "dperp", "deq", "s_mm")
CHAVES = tuple(dict.fromkeys(CHAVES_RESUMO + CHAVES_SEG))


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
    return [{"nome": "total", "roi": list(ORGAOS), "fast": False, "rotulo": "aorta e marcos", "aorta": True}]


def controle_acr(d_mm: float) -> str:
    """O intervalo de controle do ACR (2013) para a aorta abdominal ectásica ou com aneurisma."""
    for a, b, txt in _CONTROLE_ACR:
        if a <= d_mm < b:
            return txt
    return ""


# ------------------------------------------------------------------ geometria
def _profundidade(oc: np.ndarray) -> np.ndarray:
    """Quantas erosões (6 vizinhos) cada ponto aguenta: a distância à parede, em passos da grade."""
    prof = np.zeros(oc.shape, np.int16)
    cur = oc.copy()
    n = 0
    while cur.any() and n < 200:
        n += 1
        prof[cur] = n
        e = cur.copy()
        for ax in range(3):
            a = [slice(None)] * 3
            b = [slice(None)] * 3
            a[ax], b[ax] = slice(1, None), slice(None, -1)
            e[tuple(a)] &= cur[tuple(b)]
            e[tuple(b)] &= cur[tuple(a)]
            for borda in (0, -1):
                s = [slice(None)] * 3
                s[ax] = borda
                e[tuple(s)] = False
        cur = e
    return prof


_VIZ = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) != (0, 0, 0)])


def _grafo(pts: np.ndarray, forma):
    """Vizinhos (26) de cada ponto da grade. Devolve (vizinhos (n, 26) com −1, comprimentos (26,))."""
    chave = np.ravel_multi_index(pts.T, forma)
    ordem = np.argsort(chave)
    ch_ord = chave[ordem]
    viz = np.full((len(pts), len(_VIZ)), -1, np.int64)
    for c, d in enumerate(_VIZ):
        q = pts + d
        ok = np.all((q >= 0) & (q < np.array(forma)), axis=1)
        kq = np.full(len(pts), -1, np.int64)
        kq[ok] = np.ravel_multi_index(q[ok].T, forma)
        pos = np.searchsorted(ch_ord, kq)
        pos = np.clip(pos, 0, len(ch_ord) - 1)
        achou = ok & (ch_ord[pos] == kq)
        viz[achou, c] = ordem[pos[achou]]
    return viz, np.linalg.norm(_VIZ, axis=1)


def _dijkstra(viz, comp, peso_no, origem: int):
    n = len(viz)
    dist = np.full(n, np.inf)
    pai = np.full(n, -1, np.int64)
    dist[origem] = 0.0
    fila = [(0.0, origem)]
    while fila:
        d, u = heapq.heappop(fila)
        if d > dist[u]:
            continue
        for c in range(viz.shape[1]):
            v = viz[u, c]
            if v < 0:
                continue
            nd = d + comp[c] * 0.5 * (peso_no[u] + peso_no[v])
            if nd < dist[v]:
                dist[v] = nd
                pai[v] = u
                heapq.heappush(fila, (nd, v))
    return dist, pai


def _suavizar(p: np.ndarray, janela: int = 7) -> np.ndarray:
    if len(p) <= janela:
        return p
    h = janela // 2
    q = p.copy()
    for i in range(h, len(p) - h):
        q[i] = p[i - h:i + h + 1].mean(axis=0)
    return q


def _reamostrar(p: np.ndarray, passo: float) -> tuple[np.ndarray, np.ndarray]:
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] <= 0:
        return p[:1], np.zeros(1)
    alvo = np.arange(0.0, s[-1] + 1e-6, passo)
    out = np.column_stack([np.interp(alvo, s, p[:, d]) for d in range(3)])
    return out, alvo


def linha_central(mascara: np.ndarray, vol) -> tuple[np.ndarray, np.ndarray]:
    """(pontos em mm do paciente, distância ao longo da linha a partir da ponta proximal). Vazio sem caminho."""
    M = np.asarray(vol.matrix(), float)
    esp = np.linalg.norm(M, axis=0)                      # mm por passo em i, j, k
    idx = np.argwhere(mascara)                           # (k, j, i)
    if len(idx) < 20:
        return np.zeros((0, 3)), np.zeros(0)
    mm = idx[:, ::-1] * esp                              # (i, j, k) em mm, nos eixos da série
    cel = np.floor(mm / GRADE_MM).astype(np.int64)
    cel -= cel.min(axis=0)
    forma = tuple(int(x) + 3 for x in cel.max(axis=0))
    cel += 1
    oc = np.zeros(forma, bool)
    oc[tuple(cel.T)] = True
    pts = np.argwhere(oc)
    prof = _profundidade(oc)[tuple(pts.T)].astype(float)
    viz, comp = _grafo(pts, forma)
    # o centro de cada célula, de volta a mm do paciente
    base = np.floor(mm.min(axis=0) / GRADE_MM) * GRADE_MM - GRADE_MM
    centro_mm = base + (pts + 0.5) * GRADE_MM                    # (i, j, k) mm
    ijk = centro_mm / esp
    pac = vol.origin + ijk @ M.T
    z = pac[:, 2]
    # o maior pedaço conexo (a máscara pode ter ilhas soltas)
    um = np.ones(len(pts))
    d0, _ = _dijkstra(viz, comp, um, int(np.argmax(prof)))
    vivos = np.isfinite(d0)
    zv = np.where(vivos, z, np.inf)
    distal = int(np.argmin(zv))
    d1, _ = _dijkstra(viz, comp, um, distal)
    d1[~vivos] = -1
    proximal = int(np.argmax(d1))
    peso_no = 1.0 / (prof + 0.5) ** 2
    _d, pai = _dijkstra(viz, comp, peso_no, proximal)
    cam = [distal]
    while cam[-1] != proximal and pai[cam[-1]] >= 0:
        cam.append(int(pai[cam[-1]]))
    cam = cam[::-1]
    # as pontas caem na borda da tampa (o ponto mais longe é na parede): corta até o caminho chegar ao meio
    pc = prof[cam]

    def corte(seq):
        for n_p in range(len(seq)):
            if seq[n_p] >= 0.7 * max(seq[n_p:n_p + 6].max(), 1):
                return n_p
        return 0
    a = corte(pc)
    b = len(cam) - corte(pc[::-1])
    cam = cam[a:b] if b - a >= 5 else cam
    if len(cam) < 5:
        return np.zeros((0, 3)), np.zeros(0)
    return _reamostrar(_suavizar(pac[cam], 7), PASSO_MM)


def _base_do_plano(t: np.ndarray):
    t = t / max(np.linalg.norm(t), 1e-9)
    ref = np.array([1.0, 0, 0]) if abs(t[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(t, ref)
    u /= np.linalg.norm(u)
    v = np.cross(t, u)
    return u, v


def _secao(mascara_f, vol, centro, tangente, raio_mm, off, pixel):
    """O corte da máscara no plano perpendicular a `tangente` em `centro`: (pedaço que contém o centro, A, B,
    u, v), com A e B as coordenadas (mm) no plano; None se o plano não pega a máscara."""
    from ipe.imaging.estruturas import rotular
    from ipe.imaging.volume import sample_trilinear
    u, v = _base_do_plano(np.asarray(tangente, float))
    n = int(raio_mm / pixel)
    a = np.arange(-n, n + 1) * pixel
    A, B = np.meshgrid(a, a, indexing="ij")
    P = np.asarray(centro, float)[None, None] + A[..., None] * u + B[..., None] * v
    Minv = np.linalg.inv(np.asarray(vol.matrix(), float))
    ijk = (P - vol.origin) @ Minv.T - np.array([off[2], off[1], off[0]], float)
    m = np.nan_to_num(sample_trilinear(mascara_f, ijk)) >= 0.5
    if not m.any():
        return None
    r, _nr = rotular(m)
    c = r[n, n]
    if c == 0:                                            # o centro caiu fora: o pedaço mais perto
        idx = np.argwhere(r > 0)
        c = r[tuple(idx[np.argmin(((idx - n) ** 2).sum(axis=1))])]
    return r == c, A, B, u, v


def _tangentes(p: np.ndarray, h: int = 3) -> np.ndarray:
    t = np.zeros_like(p)
    for n_p in range(len(p)):
        a, b = max(0, n_p - h), min(len(p) - 1, n_p + h)
        t[n_p] = p[b] - p[a]
    return t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)


def recentrar(p: np.ndarray, mascara_f, vol, off, voltas: int = 3) -> np.ndarray:
    """Leva cada ponto ao centroide do corte perpendicular (a linha do caminho mínimo foge do meio perto das
    pontas, onde a profundidade não distingue o centro), e suaviza."""
    for _ in range(voltas):
        tg = _tangentes(p)
        q = p.copy()
        for n_p in range(len(p)):
            sec = _secao(mascara_f, vol, p[n_p], tg[n_p], 45.0, off, 1.0)
            if sec is None:
                continue
            pe, A, B, u, v = sec
            q[n_p] = p[n_p] + A[pe].mean() * u + B[pe].mean() * v
        p = _suavizar(q, 5)
    return p


def estender(p: np.ndarray, mascara: np.ndarray, vol, off=(0, 0, 0)) -> np.ndarray:
    """Continua as duas pontas em linha reta, pela tangente, até sair da máscara."""
    Minv = np.linalg.inv(np.asarray(vol.matrix(), float))

    def dentro(q):
        i, j, k = np.rint((q - vol.origin) @ Minv.T).astype(int) - np.array([off[2], off[1], off[0]])
        return (0 <= k < mascara.shape[0] and 0 <= j < mascara.shape[1] and 0 <= i < mascara.shape[2]
                and bool(mascara[k, j, i]))

    def um_lado(pts):
        if len(pts) < 4:
            return pts
        tg = pts[-1] - pts[-4]
        tg = tg / max(np.linalg.norm(tg), 1e-9)
        novos, q = [], pts[-1].copy()
        for _ in range(int(60 / PASSO_MM)):
            q = q + tg * PASSO_MM
            if not dentro(q):
                break
            novos.append(q.copy())
        return np.vstack([pts] + ([np.array(novos)] if novos else []))
    return um_lado(um_lado(p)[::-1])[::-1]


def medir_plano(mascara_f: np.ndarray, vol, centro, tangente, raio_mm: float, off=(0, 0, 0)) -> dict | None:
    """Diâmetros da máscara no plano perpendicular a `tangente` em `centro` (mm do paciente)."""
    sec = _secao(mascara_f, vol, centro, tangente, raio_mm, off, PIXEL_PLANO)
    if sec is None:
        return None
    pe, A, B, _u, _v = sec
    borda = bool(pe[0, :].any() or pe[-1, :].any() or pe[:, 0].any() or pe[:, -1].any())
    xa, xb = A[pe], B[pe]
    larg = []
    for th in np.radians(np.arange(0, 180, 5)):
        pr = xa * np.cos(th) + xb * np.sin(th)
        larg.append(float(pr.max() - pr.min() + PIXEL_PLANO))
    larg = np.array(larg)
    k = int(np.argmax(larg))
    perp = larg[(k + 18) % 36]
    area = float(pe.sum() * PIXEL_PLANO ** 2)
    return {"dmax": float(larg[k]), "dperp": float(perp), "dmin": float(larg.min()),
            "deq": float(2 * np.sqrt(area / np.pi)), "area": area, "borda": borda}


# ------------------------------------------------------------------ a conta
@dataclass
class Segmento:
    sigla: str
    dmax: float
    dperp: float
    deq: float
    s_mm: float
    centro: list
    inicio_mm: float
    fim_mm: float


@dataclass
class Resultado:
    segmentos: dict = field(default_factory=dict)       # sigla -> Segmento
    perfil: list = field(default_factory=list)          # [(s, dmax, dperp, deq)]
    linha: np.ndarray | None = None
    s: np.ndarray | None = None
    comprimento: float = 0.0
    calculado: bool = False
    mascara: np.ndarray | None = None
    offset: tuple = (0, 0, 0)
    centro: list | None = None
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""

    @property
    def maior(self):
        return max(self.segmentos.values(), key=lambda g: g.dmax) if self.segmentos else None


def _s_do_ramo(linha: np.ndarray, ramo_pts: np.ndarray, s: np.ndarray):
    """O ponto da linha central mais perto do ramo (a origem dele)."""
    if ramo_pts is None or len(ramo_pts) == 0:
        return None
    sub = ramo_pts[:: max(1, len(ramo_pts) // 4000)]
    d = np.sqrt(((linha[:, None, :] - sub[None, :, :]) ** 2).sum(-1)).min(axis=1)
    i = int(np.argmin(d))
    return float(s[i]) if d[i] < 25.0 else None


def _pontos_mm(m, vol):
    if m is None or not m.any():
        return None
    idx = np.argwhere(m)[:, ::-1].astype(float)
    return vol.origin + idx @ np.asarray(vol.matrix(), float).T


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import cefalometria as CF
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    ms = CF.Mascaras(vol, rotulos)
    nz = vol.data.shape[0]
    desc = t.descricao_serie or t.series_uid[-8:]
    res.elegibilidade = (f"TC, série “{desc}”, {nz} cortes de {vol.dz:.2f} mm, pixel {vol.dy:.2f} × {vol.dx:.2f} mm")
    aorta = ms.get("aorta")
    if aorta is None or aorta.sum() < 200:
        res.avisos.append("a IA não achou a aorta nesta série")
        return res
    # o recorte da aorta (com folga para os planos)
    ks, js, is_ = (np.nonzero(aorta.any(axis=a))[0] for a in ((1, 2), (0, 2), (0, 1)))
    folga = [int(np.ceil(50.0 / e)) for e in (vol.dz, vol.dy, vol.dx)]
    k0, k1 = max(0, ks[0] - folga[0]), min(nz, ks[-1] + 1 + folga[0])
    j0, j1 = max(0, js[0] - folga[1]), min(vol.data.shape[1], js[-1] + 1 + folga[1])
    i0, i1 = max(0, is_[0] - folga[2]), min(vol.data.shape[2], is_[-1] + 1 + folga[2])
    sub = aorta[k0:k1, j0:j1, i0:i1]
    sub_f = sub.astype(np.float32)
    linha, s = linha_central(aorta, vol)
    if len(linha) >= 10:
        bruta, _s = _reamostrar(linha, 4.0)
        linha, s = _reamostrar(estender(recentrar(bruta, sub_f, vol, (k0, j0, i0)), sub, vol, (k0, j0, i0)),
                               PASSO_MM)
    if len(linha) < 10:
        res.avisos.append("não deu para traçar a linha central da aorta")
        return res
    res.linha, res.s, res.comprimento = linha, s, float(s[-1])
    # medidas perpendiculares
    perfil = []
    raio = 45.0
    for n_p in range(len(linha)):
        if s[n_p] < 4.0 or s[n_p] > s[-1] - 4.0:
            perfil.append(None)
            continue
        a, b = max(0, n_p - 3), min(len(linha) - 1, n_p + 3)
        tg = linha[b] - linha[a]
        m = medir_plano(sub_f, vol, linha[n_p], tg, raio, (k0, j0, i0))
        perfil.append(m)
    vals = np.array([m["dmax"] if m else np.nan for m in perfil])
    # mediana de 3 (tira o pico de um plano só)
    med = vals.copy()
    for n_p in range(1, len(vals) - 1):
        w = vals[n_p - 1:n_p + 2]
        if np.isfinite(w).sum() >= 2:
            med[n_p] = float(np.nanmedian(w))
    res.perfil = [(float(s[n_p]), m["dmax"], m["dperp"], m["deq"]) for n_p, m in enumerate(perfil) if m]
    # marcos
    z = linha[:, 2]
    apice = int(np.argmax(z))
    tem_arco = 5 < apice < len(linha) - 5
    cor = ms.get("heart")
    comeca_no_coracao = False
    if cor is not None and cor.any():
        pc = _pontos_mm(cor, vol)
        sub_c = pc[:: max(1, len(pc) // 4000)]
        comeca_no_coracao = float(np.sqrt(((sub_c - linha[0]) ** 2).sum(-1)).min()) < 20.0
    s_bct = _s_do_ramo(linha, _pontos_mm(ms.get("brachiocephalic_trunk"), vol), s)
    s_lsa = _s_do_ramo(linha, _pontos_mm(ms.get("subclavian_artery_left"), vol), s)
    if not tem_arco:
        s_bct = s_lsa = None
    s_apice = float(s[apice]) if tem_arco else None
    if tem_arco and (s_bct is None or s_lsa is None or s_lsa <= s_bct):
        s_bct, s_lsa = max(0.0, s_apice - ARCO_SEM_RAMOS_MM), s_apice + ARCO_SEM_RAMOS_MM - DEPOIS_SUBCLAVIA_MM
        res.avisos.append("sem os ramos do arco: o arco é o trecho de 30 mm de cada lado do ponto mais alto")
    # níveis em z (depois do arco)
    inicio_desc = apice if tem_arco else 0

    def s_no_nivel(z_nivel):
        if z_nivel is None:
            return None
        for n_p in range(inicio_desc, len(linha)):
            if z[n_p] <= z_nivel:
                return float(s[n_p])
        return None
    t12 = ms.get("vertebrae_T12")
    z_hiato = float(_pontos_mm(t12, vol)[:, 2].min()) if t12 is not None else None
    rins = [_pontos_mm(ms.get(k), vol) for k in ("kidney_left", "kidney_right")]
    rins = [r for r in rins if r is not None]
    z_renal = float(np.mean([r[:, 2].mean() for r in rins])) if rins else None
    s_hiato, s_renal = s_no_nivel(z_hiato), s_no_nivel(z_renal)
    if z_hiato is None:
        res.avisos.append("sem T12: o fim da aorta torácica não foi marcado")
    if z_renal is None:
        res.avisos.append("sem os rins: a aorta abdominal não foi dividida em suprarrenal e infrarrenal")
    # o segmento de cada ponto
    sig = []
    for n_p in range(len(linha)):
        sv = s[n_p]
        if tem_arco and n_p < apice and comeca_no_coracao and sv < RAIZ_MM:
            sig.append("RZ")
        elif tem_arco and sv < s_bct:
            sig.append("AA")
        elif tem_arco and sv < s_lsa + DEPOIS_SUBCLAVIA_MM:
            sig.append("AR")
        elif s_hiato is not None and sv < s_hiato:
            sig.append("DT")
        elif s_hiato is None and z_renal is None:
            sig.append("DT")
        elif s_renal is not None and sv < s_renal:
            sig.append("AS")
        elif s_renal is None:
            sig.append("AS" if s_hiato is not None else "DT")
        else:
            sig.append("AI")
    for g in ORDEM:
        idx = [n_p for n_p in range(len(linha)) if sig[n_p] == g and perfil[n_p] is not None and np.isfinite(med[n_p])]
        if not idx:
            continue
        n_m = max(idx, key=lambda n_p: med[n_p])
        m = perfil[n_m]
        res.segmentos[g] = Segmento(g, float(med[n_m]), float(m["dperp"]), float(m["deq"]), float(s[n_m]),
                                    [float(x) for x in linha[n_m]], float(s[idx[0]]), float(s[idx[-1]]))
    if not res.segmentos:
        res.avisos.append("nenhum plano perpendicular deu medida")
        return res
    res.calculado = True
    res.centro = res.maior.centro
    # a máscara por segmento: cada voxel da aorta vai para o ponto da linha central mais perto
    idx = np.argwhere(sub)
    pac = vol.origin + (idx[:, ::-1] + np.array([i0, j0, k0], float)) @ np.asarray(vol.matrix(), float).T
    cod = np.array([CODIGO[g] for g in sig], np.uint8)
    mais_perto = np.empty(len(idx), np.int64)
    for c0 in range(0, len(idx), 20000):
        d = ((pac[c0:c0 + 20000, None, :] - linha[None, :, :]) ** 2).sum(-1)
        mais_perto[c0:c0 + 20000] = np.argmin(d, axis=1)
    mascara = np.zeros(sub.shape, np.uint8)
    mascara[tuple(idx.T)] = cod[mais_perto]
    res.mascara, res.offset = mascara, (int(k0), int(j0), int(i0))
    # avisos
    if "RZ" in res.segmentos:
        res.avisos.append("raiz: sem ECG, a medida dos seios não vale (a ACC/AHA mede seio a seio, com ECG)")
    if not tem_arco:
        res.avisos.append("a série não pega o arco: sem raiz, ascendente e arco")
    if float(vol.dz) > 3.0:
        res.avisos.append(f"cortes a cada {vol.dz:.1f} mm: o plano perpendicular perde nitidez; prefira ≤ 3 mm")
    res.avisos.append("da parede externa à externa (a máscara pega a parede e o trombo), em plano perpendicular à "
                      "linha central; a ACC/AHA pede a raiz e a ascendente de borda interna a interna, com ECG")
    return res


# ------------------------------------------------------------------ saída
def _n(v, u, n, casas=0):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def _referencia(g: str, d: float) -> str:
    lim, txt = REFERENCIA[g]
    out = txt if d >= lim else ""
    if g == "AI" and controle_acr(d):
        out += f"; controle sugerido pelo ACR (2013) para {d:.0f} mm: {controle_acr(d)}"
    return out.strip("; ")


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado:
        return []
    eleg = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "elegibilidade": eleg}
    m = res.maior
    itens = [{**base, "rotulo": "A", "tipo": TIPO_RESUMO, "local": f"maior: {SEGMENTOS[m.sigla]}",
              "posicao": m.centro,
              "numeros": {"dmax": _n(m.dmax, "mm", "Maior diâmetro"),
                          "comprimento": _n(res.comprimento, "mm", "Comprimento da linha central")}}]
    for g in ORDEM:
        x = res.segmentos.get(g)
        if x is None:
            continue
        ref = _referencia(g, x.dmax)
        itens.append({**base, "rotulo": g, "tipo": TIPO_SEG, "local": SEGMENTOS[g], "posicao": x.centro,
                      "segmento": CODIGO[g],
                      "elegibilidade": eleg + (f". Referência: {ref}" if ref else ""),
                      "numeros": {"dmax": _n(x.dmax, "mm", "Diâmetro máximo"),
                                  "dperp": _n(x.dperp, "mm", "Perpendicular"),
                                  "deq": _n(x.deq, "mm", "Diâmetro pela área"),
                                  "s_mm": _n(x.s_mm, "mm", "Distância na linha central")}})
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
                log.exception("trocar a SEG da aorta anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.mascara is not None and res.mascara.any():
        segs = []
        for g in ORDEM:
            m = res.mascara == CODIGO[g]
            if m.any():
                segs.append((SimpleNamespace(mask=m, offset=res.offset), f"Aorta: {SEGMENTOS[g]}", CORES[g]))
        vol = t.vol
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"TotalSegmentator {versao} + linha central".strip()), anatomia=True)
        tmp = Path(tempfile.mkdtemp(prefix="dv_aorta_"))
        try:
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
            out["series"] += sorted(getattr(r, "new_series", None) or [])
            out["seg_sop"] = str(ds.SOPInstanceUID)
            out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    revisados = {a.get("rotulo") for a in repo.achados(t.study_uid, FERRAMENTA) if a.get("estado") != "sugerido"}
    itens = [x for x in itens_para_o_banco(res, t, versao) if x["rotulo"] not in revisados]
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens)
    return out


def _f(v, casas=0) -> str:
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",")


def resumo(res: Resultado) -> str:
    if not res.calculado:
        return res.avisos[0] if res.avisos else "não medido"
    partes = [f"{g} {_f(res.segmentos[g].dmax)} mm" for g in ORDEM if g in res.segmentos]
    return "diâmetro máximo por segmento: " + ", ".join(partes)


def n_itens(res: Resultado) -> int:
    return (1 + len(res.segmentos)) if res.calculado else 0


def mensagem(res: Resultado, minutos: float) -> str:
    if not res.calculado:
        return f"Aorta: {resumo(res)}."
    msg = (f"Aorta pronta em {minutos:.1f} min — {resumo(res)}. Cada segmento está em Aplicações ▸ Achados de IA "
           f"(clicar leva ao ponto do maior diâmetro); os segmentos estão na série “{DESC_SEG}”, uma cor por trecho.")
    avisos = [a for a in res.avisos if not a.startswith("da parede externa")]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x)
    if a.get("tipo") == TIPO_RESUMO:
        return ""
    txt = f"{(a.get('local') or a.get('rotulo', '')).capitalize()}: diâmetro máximo {v('dmax')}"
    txt += f" × {v('dperp')} mm" if v("dperp") else " mm"
    return txt + " (perpendicular ao eixo, parede externa)."


def laudo(achados: list[dict]) -> str:
    valem = [a for a in achados if a.get("estado") in AC.VALEM and a.get("tipo") == TIPO_SEG]
    if not valem:
        return ""
    valem.sort(key=lambda a: ORDEM.index(a["rotulo"]) if a.get("rotulo") in ORDEM else 99)
    return "\n".join(f"- {frase(a)}" for a in valem)
