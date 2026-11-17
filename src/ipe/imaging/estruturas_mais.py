"""Estruturas: as ferramentas que faltavam (0.100.67) — tesoura, oco, suavização, limiar automático (Otsu),
dividir ilhas em estruturas, contorno por nível (level tracing), crescer de sementes (o "grow from seeds" do
3D Slicer) e a segmentação a partir do maior diâmetro (AW: desenhar o diâmetro e receber o contorno 3D).

Complemento de `imaging/estruturas.py` (0.99.40/44), no mesmo espírito: máscaras recortadas na grade da série
de referência, cada operação devolve o quanto mudou e pode ser desfeita por quem chama. Só NumPy. Sem Qt.
"""
from __future__ import annotations

import logging

import numpy as np

from ipe.imaging import estruturas as ES
from ipe.imaging.estruturas import Estrutura, Grade

log = logging.getLogger(__name__)

ACOES_TESOURA = {"apagar_dentro": "Apagar dentro", "apagar_fora": "Apagar fora", "preencher": "Preencher dentro"}
ALCANCES = {"corte": "Só este corte", "volume": "Todos os cortes"}
ONDE_OCO = {"dentro": "para dentro da borda", "fora": "para fora da borda", "meio": "metade para cada lado"}
SUAVIZACOES = {"mediana": "Mediana (tira pontas e fecha furos pequenos)", "abertura": "Abertura (tira pontas e pontes finas)",
               "fechamento": "Fechamento (fecha furos e reentrâncias)"}
#: o crescer de sementes trabalha, no máximo, neste número de voxels (acima disso, a caixa é amostrada)
MAX_VOXELS_SEMENTES = 900_000


# ====================================================================== geometria
def _base_do_plano(normal) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = np.asarray(normal, float)
    n = n / (np.linalg.norm(n) or 1.0)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(n, a)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(n, e1), n


def dentro_do_poligono(px: np.ndarray, py: np.ndarray, poli: np.ndarray) -> np.ndarray:
    """Quais pontos (px, py) estão dentro do polígono (N × 2), pela regra par-ímpar. Vetorizado."""
    dentro = np.zeros(np.shape(px), bool)
    n = len(poli)
    xj, yj = poli[-1]
    for t in range(n):
        xi, yi = poli[t]
        if yi != yj:
            cruza = ((yi > py) != (yj > py)) & (px < (xj - xi) * (py - yi) / (yj - yi) + xi)
            dentro ^= cruza
        xj, yj = xi, yi
    return dentro


def _simplificar(pts: np.ndarray, maximo: int = 160) -> np.ndarray:
    if len(pts) <= maximo:
        return pts
    return pts[np.linspace(0, len(pts) - 1, maximo).round().astype(int)]


def _eixo_da_grade(grade: Grade, normal) -> tuple[int, float]:
    """O eixo da grade (0 = i/coluna, 1 = j/linha, 2 = k/corte) mais alinhado com a normal, e o cosseno."""
    n = np.asarray(normal, float)
    n = n / (np.linalg.norm(n) or 1.0)
    cos = [abs(float(grade.matriz[:, c] @ n)) / (float(np.linalg.norm(grade.matriz[:, c])) or 1.0) for c in range(3)]
    c = int(np.argmax(cos))
    return c, cos[c]


# ====================================================================== tesoura
def tesoura(e: Estrutura, grade: Grade, poligono_mm, normal, acao: str = "apagar_dentro", alcance: str = "corte",
            limites: "ES.Limites | None" = None, proibidas=()) -> int:
    """Corta ou preenche pela forma desenhada no plano da tela (os pontos em mm): apaga o que está dentro, apaga o
    que está fora ou preenche dentro; só no corte em que foi desenhada ou atravessando todos os cortes (a forma é
    estendida ao longo da normal do plano). Devolve a variação em voxels (negativa ao apagar)."""
    pts = _simplificar(np.asarray(poligono_mm, float).reshape(-1, 3))
    if e.travada or len(pts) < 3 or acao not in ACOES_TESOURA:
        return 0
    if acao != "preencher" and e.vazia():
        return 0
    e1, e2, n = _base_do_plano(normal)
    o = pts[0]
    poli = np.stack([(pts - o) @ e1, (pts - o) @ e2], axis=1)
    nz, ny, nx = grade.forma
    eixo, cos = _eixo_da_grade(grade, n)
    passo = float(np.linalg.norm(grade.matriz[:, eixo]))
    meia = 0.5 * passo * max(cos, 0.5) + 1e-6           # meia espessura do "corte" ao longo da normal
    # a caixa (em voxels) onde a operação pode mexer
    if acao == "preencher":
        cantos = pts if alcance == "corte" else np.concatenate([pts - n * 1e5, pts + n * 1e5])
        if alcance == "corte":
            cantos = np.concatenate([pts - n * meia, pts + n * meia])
        ijk = grade.para_ijk(cantos)
        lo = np.clip(np.floor(ijk.min(0)).astype(int) - 1, 0, [nx - 1, ny - 1, nz - 1])
        hi = np.clip(np.ceil(ijk.max(0)).astype(int) + 2, 1, [nx, ny, nz])
        caixa = (int(lo[2]), int(hi[2]), int(lo[1]), int(hi[1]), int(lo[0]), int(hi[0]))
    else:
        caixa = ES._caixa_de(e)
    k0, k1, j0, j1, i0, i1 = caixa
    if k1 <= k0 or j1 <= j0 or i1 <= i0:
        return 0
    antes = e.voxels
    dentro = np.zeros((k1 - k0, j1 - j0, i1 - i0), bool)
    no_corte = np.ones_like(dentro)
    jj, ii = np.meshgrid(np.arange(j0, j1), np.arange(i0, i1), indexing="ij")
    for k in range(k0, k1):                               # um corte da grade por vez (memória)
        mm = grade.origem + ii[..., None] * grade.matriz[:, 0] + jj[..., None] * grade.matriz[:, 1] + k * grade.matriz[:, 2]
        d = mm - o
        if alcance == "corte":
            perto = np.abs(d @ n) <= meia
            no_corte[k - k0] = perto
            if not perto.any():
                continue
        dentro[k - k0] = dentro_do_poligono(d @ e1, d @ e2, poli)
    if alcance == "corte":
        dentro &= no_corte
    if acao == "preencher":
        novo = dentro
        if limites is not None and limites.ativo():
            novo = novo & limites.permitido(caixa, e)
        for p in proibidas:
            if p is not e and not p.vazia():
                novo = novo & ~ES._recorte_de(p, caixa)
        if not novo.any():
            return 0
        e.expandir(grade, k0, k1, j0, j1, i0, i1)
        atual = ES._recorte_de(e, caixa)
        ES._escrever(e, caixa, atual | novo)
    elif acao == "apagar_dentro":
        e.mascara = e.mascara & ~dentro
    else:                                                 # apagar fora: no corte (ou em todos), só fica o de dentro
        fora = ~dentro & no_corte if alcance == "corte" else ~dentro
        e.mascara = e.mascara & ~fora
    e.aparar()
    dif = e.voxels - antes
    if dif:
        e.alterada = True
    return dif


def forma_da_tesoura(forma: str, a, b, e1, e2, n: int = 72) -> np.ndarray:
    """Os pontos (mm) de um retângulo ou de uma elipse entre os cantos `a` e `b`, no plano de base (e1, e2)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    du, dv = float((b - a) @ e1), float((b - a) @ e2)
    if forma == "elipse":
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        c = a + 0.5 * du * e1 + 0.5 * dv * e2
        return c + np.outer(0.5 * du * np.cos(t), e1) + np.outer(0.5 * dv * np.sin(t), e2)
    return np.array([a, a + du * e1, a + du * e1 + dv * e2, a + dv * e2])


# ====================================================================== oco e suavização
def _erodir(m: np.ndarray, bola) -> np.ndarray:
    pad = np.pad(~m, 1, constant_values=True)
    return ~ES._dilatar(pad, bola)[1:-1, 1:-1, 1:-1]


def _folga(e: Estrutura, grade: Grade, bola) -> None:
    rk = max(abs(a) for a, _b, _c in bola)
    rj = max(abs(b) for _a, b, _c in bola)
    ri = max(abs(c) for _a, _b, c in bola)
    k0, j0, i0 = e.offset
    nz, ny, nx = e.mascara.shape
    e.expandir(grade, k0 - rk - 1, k0 + nz + rk + 1, j0 - rj - 1, j0 + ny + rj + 1, i0 - ri - 1, i0 + nx + ri + 1)


def oco(e: Estrutura, grade: Grade, mm: float, onde: str = "dentro") -> int:
    """Troca a estrutura pela **casca** dela, com `mm` de espessura: para dentro da borda, para fora, ou metade
    para cada lado. Devolve a variação em voxels (0 se a espessura é menor que um voxel)."""
    if e.travada or e.vazia() or mm <= 0 or onde not in ONDE_OCO:
        return 0
    antes = e.voxels
    r = mm / 2.0 if onde == "meio" else mm
    bola = ES._bola(grade, r)
    if len(bola) <= 1:
        return 0
    _folga(e, grade, bola)
    m = e.mascara
    if onde == "dentro":
        novo = m & ~_erodir(m, bola)
    elif onde == "fora":
        novo = ES._dilatar(m, bola) & ~m
    else:
        novo = ES._dilatar(m, bola) & ~_erodir(m, bola)
    if not novo.any():
        e.aparar()
        return 0
    e.mascara = novo
    e.aparar()
    e.alterada = True
    return e.voxels - antes


def suavizar(e: Estrutura, grade: Grade, metodo: str = "mediana", mm: float = 2.0, so_no_plano: bool = False) -> int:
    """Suaviza a borda: **mediana** (cada voxel fica com o que a maioria da vizinhança tem), **abertura** (encolhe e
    cresce: somem pontas e pontes finas) ou **fechamento** (cresce e encolhe: somem furos e reentrâncias). `mm` é o
    raio da vizinhança. Devolve quantos voxels mudaram."""
    if e.travada or e.vazia() or metodo not in SUAVIZACOES:
        return 0
    bola = ES._bola(grade, mm, so_no_plano)
    if len(bola) <= 1:
        return 0
    _folga(e, grade, bola)
    m = e.mascara
    if metodo == "abertura":
        novo = ES._dilatar(_erodir(m, bola), bola)
    elif metodo == "fechamento":
        novo = _erodir(ES._dilatar(m, bola), bola)
    else:
        conta = np.zeros(m.shape, np.int16)
        nz, ny, nx = m.shape
        for a, b, c in bola:
            src = m[max(0, -a):nz - max(0, a), max(0, -b):ny - max(0, b), max(0, -c):nx - max(0, c)]
            conta[max(0, a):nz - max(0, -a), max(0, b):ny - max(0, -b), max(0, c):nx - max(0, -c)] += src
        novo = conta * 2 > len(bola)
    mudou = int((novo != m).sum())
    if mudou:
        e.mascara = novo
        e.alterada = True
    e.aparar()
    return mudou


# ====================================================================== limiar automático e ilhas
def limiar_otsu(valores, bins: int = 256) -> float:
    """O limiar de Otsu (o corte que melhor separa o histograma em duas classes). Os extremos (0,5% de cada lado)
    ficam fora da conta para um pixel estourado não esticar o histograma."""
    v = np.asarray(valores, np.float64).ravel()
    v = v[np.isfinite(v)]
    if v.size < 2:
        return 0.0
    lo, hi = np.percentile(v, [0.5, 99.5])
    if hi <= lo:
        return float(lo)
    h, bordas = np.histogram(np.clip(v, lo, hi), bins=bins, range=(lo, hi))
    centros = 0.5 * (bordas[:-1] + bordas[1:])
    w0 = np.cumsum(h).astype(np.float64)
    w1 = w0[-1] - w0
    s0 = np.cumsum(h * centros)
    m0 = s0 / np.maximum(w0, 1)
    m1 = (s0[-1] - s0) / np.maximum(w1, 1)
    entre = w0 * w1 * (m0 - m1) ** 2
    # empate (histograma com um vão entre as classes): o meio do vão
    melhores = np.flatnonzero(entre >= entre.max() * (1 - 1e-9))
    return float(0.5 * (bordas[melhores[0] + 1] + bordas[melhores[-1] + 1]))


def otsu_da_regiao(dados: np.ndarray, dentro: "Estrutura | None" = None, passo: int = 2) -> float:
    """Otsu sobre a série (amostrada de `passo` em `passo`) ou só dentro de uma estrutura."""
    if dentro is not None and not dentro.vazia():
        return limiar_otsu(dados[dentro.caixa()][dentro.mascara])
    return limiar_otsu(dados[::max(1, passo), ::passo, ::passo])


def preencher_pela_faixa(e: Estrutura, grade: Grade, dados: np.ndarray, lo: float, hi: float,
                         limites: "ES.Limites | None" = None, proibidas=()) -> int:
    """A estrutura passa a ser **tudo** o que tem intensidade entre `lo` e `hi` (dentro dos limites da edição).
    Devolve a variação em voxels."""
    if e.travada:
        return 0
    antes = e.voxels
    nz, ny, nx = grade.forma
    caixa = (0, nz, 0, ny, 0, nx)
    if limites is not None and limites.area == "dentro" and limites.alvo is not None and not limites.alvo.vazia():
        caixa = ES._caixa_de(limites.alvo)
    k0, k1, j0, j1, i0, i1 = caixa
    v = dados[k0:k1, j0:j1, i0:i1]
    novo = (v >= lo) & (v <= hi)
    if limites is not None and limites.area != "tudo":
        so_area = ES.Limites(area=limites.area, alvo=limites.alvo, outras=limites.outras)
        novo &= so_area.permitido(caixa, e)
    for p in proibidas:
        if p is not e and not p.vazia():
            novo &= ~ES._recorte_de(p, caixa)
    e.definir(novo, (k0, j0, i0))
    e.alterada = True
    return e.voxels - antes


def dividir_ilhas(e: Estrutura, grade: Grade, min_ml: float = 0.0, maximo: int = 30) -> list[Estrutura]:
    """Cada ilha (pedaço solto) vira uma estrutura: `e` fica com a maior, e as outras (da maior para a menor,
    até `maximo`, as menores que `min_ml` ficam de fora — são apagadas) vêm numa lista de estruturas novas."""
    if e.travada or e.vazia():
        return []
    rot, n = ES.rotular(e.mascara)
    if n <= 1:
        return []
    tam = np.bincount(rot.ravel(), minlength=n + 1)
    tam[0] = 0
    ordem = [int(r) for r in np.argsort(-tam) if r and tam[r] * grade.ml_por_voxel >= min_ml][:maximo]
    if len(ordem) <= 1:
        return []
    off = e.offset
    novas = []
    for pos, r in enumerate(ordem[1:], start=2):
        x = Estrutura(f"{e.nome} {pos}", ES.CORES[(pos - 1) % len(ES.CORES)], rot == r, off, tipo=e.tipo,
                      fonte=e.fonte or "manual")
        x.aparar()
        x.alterada = True
        novas.append(x)
    e.mascara = rot == ordem[0]
    e.aparar()
    e.alterada = True
    return novas


# ====================================================================== contorno por nível
def _fatia(dados: np.ndarray, eixo: int, indice: int) -> np.ndarray:
    return dados[indice] if eixo == 2 else dados[:, indice, :] if eixo == 1 else dados[:, :, indice]


def _media_3x3(a: np.ndarray) -> np.ndarray:
    p = np.pad(a, 1, mode="edge")
    out = np.zeros_like(a)
    for dj in range(3):
        for di in range(3):
            out += p[dj:dj + a.shape[0], di:di + a.shape[1]]
    return out / 9.0


def contorno_por_nivel(dados: np.ndarray, grade: Grade, ponto_mm, normal, max_fracao: float = 0.5):
    """Level tracing: a região do corte, ligada ao ponto clicado, limitada pela **linha de mesma intensidade** que
    passa por ele — o lado mais claro (lesão clara: clicar perto da borda dá a lesão; mais para dentro, só o miolo
    mais intenso) ou o mais escuro (lesão escura), o que for menor; com os furos fechados. O corte é levemente
    alisado (média 3 × 3) para o ruído não picotar o contorno.
    Devolve (máscara 3D de um corte, caixa) ou None (ponto fora da série, ou os dois lados tomam mais de
    `max_fracao` do corte — o clique foi no fundo)."""
    eixo, _cos = _eixo_da_grade(grade, normal)
    ijk = np.rint(grade.para_ijk(ponto_mm)[0]).astype(int)
    nz, ny, nx = grade.forma
    if not (0 <= ijk[0] < nx and 0 <= ijk[1] < ny and 0 <= ijk[2] < nz):
        return None
    a = _media_3x3(np.asarray(_fatia(dados, eixo, int(ijk[eixo])), np.float32))
    # no corte: (linha, coluna) = os dois eixos que sobram, na ordem do volume (k, j, i)
    resto = [x for x in (2, 1, 0) if x != eixo]
    semente = (int(ijk[resto[0]]), int(ijk[resto[1]]))
    reg = None
    for lado in (a >= a[semente], a <= a[semente]):
        rot, _n = ES.rotular(lado)
        r = rot == rot[semente]
        n = int(r.sum())
        if n <= max_fracao * r.size and (reg is None or n < int(reg.sum())):
            reg = r
    if reg is None:
        return None
    reg = ES._sem_buracos(reg)
    ls, cs = np.flatnonzero(reg.any(1)), np.flatnonzero(reg.any(0))
    l0, l1, c0, c1 = int(ls[0]), int(ls[-1]) + 1, int(cs[0]), int(cs[-1]) + 1
    rec = reg[l0:l1, c0:c1]
    p = int(ijk[eixo])
    if eixo == 2:
        return rec[None, :, :], (p, p + 1, l0, l1, c0, c1)
    if eixo == 1:
        return rec[:, None, :], (l0, l1, p, p + 1, c0, c1)
    return rec[:, :, None], (l0, l1, c0, c1, p, p + 1)


def aplicar_mascara(e: Estrutura, grade: Grade, mascara: np.ndarray, caixa, apagar: bool = False,
                    limites: "ES.Limites | None" = None, proibidas=()) -> int:
    """Soma (ou tira) da estrutura uma máscara dada na `caixa` (k0, k1, j0, j1, i0, i1). Devolve a variação."""
    if e.travada or not np.any(mascara):
        return 0
    antes = e.voxels
    m = np.asarray(mascara, bool)
    if apagar:
        if e.vazia():
            return 0
        e.mascara = e.mascara & ~_na_caixa_de(e, m, caixa)
    else:
        if limites is not None and limites.ativo():
            m = m & limites.permitido(caixa, e)
        for p in proibidas:
            if p is not e and not p.vazia():
                m = m & ~ES._recorte_de(p, caixa)
        if not m.any():
            return 0
        e.expandir(grade, *caixa)
        ES._escrever(e, caixa, ES._recorte_de(e, caixa) | m)
    e.aparar()
    dif = e.voxels - antes
    if dif:
        e.alterada = True
    return dif


def _na_caixa_de(e: Estrutura, m: np.ndarray, caixa) -> np.ndarray:
    tmp = Estrutura("tmp", (0, 0, 0), m, (caixa[0], caixa[2], caixa[4]))
    return ES._recorte_de(tmp, ES._caixa_de(e))


# ====================================================================== crescer de sementes
def crescer_de_sementes(estruturas, grade: Grade, dados: np.ndarray, margem_mm: float = 15.0, cancelar=None) -> dict:
    """"Grow from seeds": cada estrutura é uma **semente** (alguns traços dentro da lesão, outros no que está em
    volta — uma estrutura "Fundo"); cada voxel da caixa em volta das sementes fica com a semente a que se liga pelo
    caminho de **menor mudança de intensidade**. Precisa de duas sementes ou mais. Devolve {id: variação em
    voxels}; as estruturas travadas servem de semente e não mudam. Nada fora da caixa das sementes (mais a margem)
    é tocado."""
    sem = [e for e in estruturas if e.visivel and not e.vazia()]
    if len(sem) < 2:
        raise ValueError("crescer de sementes precisa de duas estruturas ou mais (por exemplo, a lesão e o fundo)")
    nz, ny, nx = grade.forma
    dx, dy, dz = grade.espacamento
    cx = np.array([ES._caixa_de(e) for e in sem])
    mk, mj, mi = (int(np.ceil(margem_mm / s)) for s in (dz, dy, dx))
    k0, k1 = max(0, cx[:, 0].min() - mk), min(nz, cx[:, 1].max() + mk)
    j0, j1 = max(0, cx[:, 2].min() - mj), min(ny, cx[:, 3].max() + mj)
    i0, i1 = max(0, cx[:, 4].min() - mi), min(nx, cx[:, 5].max() + mi)
    caixa = (int(k0), int(k1), int(j0), int(j1), int(i0), int(i1))
    n_vox = (k1 - k0) * (j1 - j0) * (i1 - i0)
    # amostrar no plano (os cortes ficam) até caber
    f = 1
    while n_vox / (f * f) > MAX_VOXELS_SEMENTES and f < 8:
        f += 1
    v = np.asarray(dados[k0:k1, j0:j1:f, i0:i1:f], np.float32)
    lo, hi = np.percentile(v, [1, 99])
    v = np.clip((v - lo) / max(float(hi - lo), 1e-6), 0, 1)
    rot = np.zeros(v.shape, np.int16)
    for n, e in enumerate(sem, start=1):
        m = ES._recorte_de(e, caixa)[:, ::f, ::f]
        rot[m & (rot == 0)] = n
    fixo = rot > 0
    INF = np.float32(1e9)
    dist = np.where(fixo, np.float32(0), INF)
    # o custo de um passo: a mudança de intensidade, mais um quase nada pela distância (desempata no plano liso)
    passo = [np.float32(1e-3 * s / max(dx * f, 1e-6)) for s in (dz, dy * f, dx * f)]
    custos = [np.abs(np.diff(v, axis=ax)) + passo[ax] for ax in range(3)]
    for _it in range(4 * int(max(v.shape)) + 50):
        if cancelar is not None and cancelar():
            raise InterruptedError("cancelado")
        mudou = False
        for ax in range(3):
            c = custos[ax]
            a = [slice(None)] * 3
            b = [slice(None)] * 3
            a[ax], b[ax] = slice(None, -1), slice(1, None)
            a, b = tuple(a), tuple(b)
            for de, para in ((a, b), (b, a)):
                cand = dist[de] + c
                melhor = cand < dist[para]
                if melhor.any():
                    dist[para] = np.where(melhor, cand, dist[para])
                    rot[para] = np.where(melhor, rot[de], rot[para])
                    mudou = True
        if not mudou:
            break
    out = {}
    for n, e in enumerate(sem, start=1):
        if e.travada:
            continue
        novo = rot == n
        if f > 1:
            novo = np.repeat(np.repeat(novo, f, axis=1), f, axis=2)[:, :j1 - j0, :i1 - i0]
        antes = e.voxels
        e.expandir(grade, *caixa)
        ES._escrever(e, caixa, novo | (ES._recorte_de(e, caixa) if f > 1 else False))
        e.aparar()
        e.alterada = True
        out[e.id] = e.voxels - antes
    return out


# ====================================================================== segmentação pelo maior diâmetro
def por_diametro(dados: np.ndarray, grade: Grade, a_mm, b_mm, ajuste: float = 0.0, normal=None) -> dict | None:
    """A lesão a partir do **maior diâmetro** desenhado sobre ela (de `a_mm` a `b_mm`): o contorno 3D.

    1. Dentro: a intensidade ao longo dos 60% centrais da linha. Fora: a casca entre 1,25 e 1,6 raios do centro.
    2. Limiar = o meio entre as duas (o `ajuste`, de −1 a +1, leva o limiar para fora — lesão maior — ou para
       dentro); a lesão pode ser mais clara ou mais escura que o entorno.
    3. Fica o pedaço ligado à linha, dentro de um elipsoide de 1,35 raio (no eixo dos cortes, o mesmo em mm), com os
       furos fechados corte a corte e as pontas tiradas.
    Devolve {"mascara", "caixa", "limiar", "dentro", "fora", "contraste", "clara", "aviso"} ou None (linha curta
    demais ou fora da série)."""
    a, b = np.asarray(a_mm, float), np.asarray(b_mm, float)
    d = float(np.linalg.norm(b - a))
    dx, dy, dz = grade.espacamento
    if d < 2 * min(dx, dy):
        return None
    c, r = 0.5 * (a + b), 0.5 * d
    nz, ny, nx = grade.forma
    alcance = 1.6 * r + max(dx, dy, dz)
    ijk = grade.para_ijk([c])[0]
    lo = np.floor(ijk - alcance / np.array([dx, dy, dz])).astype(int) - 1
    hi = np.ceil(ijk + alcance / np.array([dx, dy, dz])).astype(int) + 2
    i0, j0, k0 = (int(max(0, x)) for x in lo)
    i1, j1, k1 = int(min(nx, hi[0])), int(min(ny, hi[1])), int(min(nz, hi[2]))
    if i1 <= i0 or j1 <= j0 or k1 <= k0:
        return None
    caixa = (k0, k1, j0, j1, i0, i1)
    v = np.asarray(dados[k0:k1, j0:j1, i0:i1], np.float32)
    kk, jj, ii = np.meshgrid(np.arange(k0, k1), np.arange(j0, j1), np.arange(i0, i1), indexing="ij")
    mm = grade.origem + ii[..., None] * grade.matriz[:, 0] + jj[..., None] * grade.matriz[:, 1] + kk[..., None] * grade.matriz[:, 2]
    rel = mm - c
    dist = np.linalg.norm(rel, axis=-1)
    # a linha: os voxels a menos de um voxel dela, nos 60% centrais
    u = (b - a) / d
    ao_longo = rel @ u
    fora_da_linha = np.linalg.norm(rel - ao_longo[..., None] * u, axis=-1)
    linha = (np.abs(ao_longo) <= 0.6 * r) & (fora_da_linha <= max(dx, dy) * 0.9)
    if normal is not None:                                  # só no plano em que foi desenhada
        n = np.asarray(normal, float)
        n = n / (np.linalg.norm(n) or 1.0)
        linha &= np.abs(rel @ n) <= 0.6 * max(dx, dy, dz)
    if linha.sum() < 2:
        linha = dist <= max(dx, dy, dz)
    casca = (dist >= 1.25 * r) & (dist <= 1.6 * r)
    if normal is not None:
        casca &= np.abs(rel @ n) <= max(dz, 0.35 * r)
    if casca.sum() < 8:
        return None
    dentro, fora = float(np.median(v[linha])), float(np.median(v[casca]))
    espalha = float(np.percentile(v[casca], 84) - np.percentile(v[casca], 16)) / 2 or 1e-6
    contraste = abs(dentro - fora) / max(espalha, 1e-6)
    clara = dentro >= fora
    aj = float(np.clip(ajuste, -1, 1))
    # ajuste > 0: o limiar anda para o lado de fora (entra mais); < 0: para dentro
    limiar = 0.5 * (dentro + fora) - aj * 0.45 * (dentro - fora)
    cand = (v >= limiar) if clara else (v <= limiar)
    cand &= dist <= (1.35 + 0.25 * max(aj, 0)) * r
    aviso = ""
    if contraste < 1.0:
        aviso = "pouco contraste entre a lesão e o que está em volta: confira o contorno"
    rot, _n = ES.rotular(cand)
    ids = np.unique(rot[linha & cand])
    ids = ids[ids > 0]
    if len(ids) == 0:
        return {"mascara": None, "caixa": caixa, "limiar": limiar, "dentro": dentro, "fora": fora,
                "contraste": contraste, "clara": clara, "aviso": "a linha não ficou sobre a lesão (ajuste para + ou redesenhe)"}
    m = np.isin(rot, ids)
    for k in range(m.shape[0]):
        if m[k].any():
            m[k] = ES._sem_buracos(m[k])
    # tirar pontas: abertura de um voxel no plano, guardando o pedaço da linha
    tmp = Estrutura("tmp", (0, 0, 0), m, (k0, j0, i0))
    bola = ES._bola(grade, max(dx, dy) * 1.01, so_no_plano=True)
    if len(bola) > 1 and tmp.voxels > 30:
        aberta = ES._dilatar(_erodir(m, bola), bola)
        rot2, _n2 = ES.rotular(aberta)
        ids2 = np.unique(rot2[linha & aberta])
        ids2 = ids2[ids2 > 0]
        if len(ids2):
            m = np.isin(rot2, ids2)
    if m.sum() >= 0.97 * cand.sum() and (dist[m].max() if m.any() else 0) >= 1.3 * r and contraste < 2:
        aviso = aviso or "o contorno encostou no limite da busca: a lesão pode ter vazado para o entorno"
    return {"mascara": m, "caixa": caixa, "limiar": float(limiar), "dentro": dentro, "fora": fora,
            "contraste": float(contraste), "clara": bool(clara), "aviso": aviso}


def diametros_axiais(e: Estrutura, grade: Grade) -> dict:
    """O maior diâmetro num corte (mm), o eixo curto perpendicular a ele no mesmo corte e o corte em que estão —
    como se mede uma lesão no RECIST. {} se vazia."""
    if e.vazia():
        return {}
    dx, dy, _dz = grade.espacamento
    melhor = (0.0, 0.0, -1)
    for k in range(e.mascara.shape[0]):
        m = e.mascara[k]
        if not m.any():
            continue
        p = np.pad(m, 1)
        borda = p & ~(np.roll(p, 1, 0) & np.roll(p, -1, 0) & np.roll(p, 1, 1) & np.roll(p, -1, 1))
        j, i = np.nonzero(borda[1:-1, 1:-1])
        pts = np.stack([i * dx, j * dy], axis=1)
        if len(pts) > 400:
            pts = pts[np.linspace(0, len(pts) - 1, 400).round().astype(int)]
        if len(pts) < 2:
            continue
        d2 = ((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        ia, ib = np.unravel_index(int(np.argmax(d2)), d2.shape)
        longo = float(np.sqrt(d2[ia, ib])) + min(dx, dy)          # de borda a borda do voxel
        if longo > melhor[0]:
            u = (pts[ib] - pts[ia]) / max(float(np.linalg.norm(pts[ib] - pts[ia])), 1e-9)
            perp = np.array([-u[1], u[0]])
            proj = pts @ perp
            # o eixo curto: a maior largura medida perpendicular ao maior diâmetro
            ao_longo = np.round((pts @ u) / max(min(dx, dy), 1e-6)).astype(int)
            curto = 0.0
            for t in np.unique(ao_longo):
                q = proj[ao_longo == t]
                if len(q) >= 2:
                    curto = max(curto, float(q.max() - q.min()))
            melhor = (longo, curto + min(dx, dy) if curto else 0.0, k + e.offset[0])
    if melhor[2] < 0:
        return {}
    return {"maior_mm": melhor[0], "curto_mm": melhor[1], "corte": int(melhor[2])}
