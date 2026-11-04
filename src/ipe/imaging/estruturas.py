"""Estruturas editáveis: máscaras 3D com nome, cor e volume, e as ferramentas para corrigi-las (0.99.40).

Item F2 do plano da AW (`claude/ideias-aw-server.md`): o Ipê já **cria** máscaras (crescimento de região,
captura da lesão na dinâmica, TotalSegmentator, SynthSeg) e já **lê** SEG e RTSTRUCT, mas não deixava
**corrigir** nem **organizar**. Aqui:

- `Grade`: a grade de referência (a de uma série: cortes, linhas, colunas e a geometria em mm). Todas as
  estruturas de uma sessão de edição vivem nela, então se combinam voxel a voxel.
- `Estrutura`: nome, cor, tipo (lesão / órgão / outro), visível, travada, de onde veio — e a máscara
  guardada **recortada** (só a caixa em volta, com o deslocamento): um órgão de TC de abdome inteiro na
  grade cheia passaria de 70 MB por estrutura.
- Edição: pincel e borracha (disco no plano do quadro, ou esfera em 3D), só dentro de uma faixa de
  intensidade, sem passar por cima das estruturas travadas; crescer e encolher em mm; manter só a
  maior ilha ou tirar as pequenas; preencher buracos; interpolar os cortes entre dois desenhados;
  aparar pela faixa de intensidade; unir, subtrair e cruzar estruturas. Cada operação pode ser desfeita.
- Números: volume (mL), voxels, média, mínimo, máximo, desvio e os três eixos.
- Entrada: qualquer `MaskVolume` (lesão guardada, SEG, contornos de RTSTRUCT), reamostrada na grade.
- Saída: SEG (`seg_writer`) e RTSTRUCT (`rtstruct_writer`).

Só NumPy (sem SciPy): a rotulagem de ilhas usa união por ponteiros vetorizada, a distância para a
interpolação é a de chanfro iterada sobre o recorte de cada corte.

Sem Qt.
"""
from __future__ import annotations

import base64
import logging
import uuid
import zlib
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

TIPOS = ("lesão", "órgão", "outro")
MAX_DESFAZER = 15
#: cores das estruturas novas, em ordem (as mesmas famílias da segmentação)
CORES = [(90, 220, 255), (255, 120, 90), (140, 255, 120), (255, 210, 70), (220, 130, 255),
         (255, 150, 200), (120, 160, 255), (200, 255, 90), (255, 90, 160), (90, 255, 210)]


# ====================================================================== grade
@dataclass
class Grade:
    """A grade de referência: forma (nz, ny, nx), voxel (0,0,0) em mm e a matriz 3 × 3 cujas colunas
    são o passo em i (coluna), j (linha) e k (corte)."""
    forma: tuple
    origem: np.ndarray
    matriz: np.ndarray

    def __post_init__(self) -> None:
        self.forma = tuple(int(x) for x in self.forma)
        self.origem = np.asarray(self.origem, float)
        self.matriz = np.asarray(self.matriz, float).reshape(3, 3)
        self._inv = np.linalg.inv(self.matriz)

    @classmethod
    def do_volume(cls, vol) -> "Grade":
        return cls(vol.data.shape, vol.origin, vol.matrix())

    @property
    def espacamento(self) -> tuple[float, float, float]:
        """(dx, dy, dz) em mm."""
        return tuple(float(np.linalg.norm(self.matriz[:, c])) for c in range(3))

    @property
    def ml_por_voxel(self) -> float:
        return abs(float(np.linalg.det(self.matriz))) / 1000.0

    def para_ijk(self, pontos) -> np.ndarray:
        p = np.atleast_2d(np.asarray(pontos, float))
        return (p - self.origem) @ self._inv.T

    def para_mm(self, ijk) -> np.ndarray:
        return self.origem + np.atleast_2d(np.asarray(ijk, float)) @ self.matriz.T


# ====================================================================== estrutura
@dataclass
class Estrutura:
    nome: str
    cor: tuple
    mascara: np.ndarray = field(default_factory=lambda: np.zeros((0, 0, 0), bool))   # recorte (k, j, i)
    offset: tuple = (0, 0, 0)                                                     # (k0, j0, i0) do recorte
    tipo: str = "lesão"
    visivel: bool = True
    travada: bool = False
    fonte: str = "manual"                 # manual, lesão guardada, SEG, RTSTRUCT, IA…
    chave_origem: str = ""                # a chave do objeto de onde veio (para atualizar a lesão guardada)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    alterada: bool = False
    _desfazer: list = field(default_factory=list, repr=False)
    _refazer: list = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.mascara = np.asarray(self.mascara, bool)
        self.offset = tuple(int(x) for x in self.offset)
        self.cor = tuple(int(c) for c in self.cor[:3])

    # ------------------------------------------------------------ números
    @property
    def voxels(self) -> int:
        return int(self.mascara.sum())

    def ml(self, grade: Grade) -> float:
        return self.voxels * grade.ml_por_voxel

    def vazia(self) -> bool:
        return self.mascara.size == 0 or not self.mascara.any()

    def caixa(self) -> tuple[slice, slice, slice]:
        k0, j0, i0 = self.offset
        nz, ny, nx = self.mascara.shape
        return slice(k0, k0 + nz), slice(j0, j0 + ny), slice(i0, i0 + nx)

    def cheia(self, grade: Grade) -> np.ndarray:
        """A máscara na grade inteira (cuidado com a memória: só para conferência e testes)."""
        out = np.zeros(grade.forma, bool)
        if self.mascara.size:
            out[self.caixa()] = self.mascara
        return out

    def pontos_mm(self, grade: Grade) -> np.ndarray:
        k, j, i = np.nonzero(self.mascara)
        k0, j0, i0 = self.offset
        return grade.para_mm(np.stack([i + i0, j + j0, k + k0], axis=1)) if len(k) else np.zeros((0, 3))

    # ------------------------------------------------------------ recorte
    def expandir(self, grade: Grade, k0, k1, j0, j1, i0, i1) -> None:
        """Garante que o recorte cobre [k0, k1) × [j0, j1) × [i0, i1) (limitado à grade)."""
        nz, ny, nx = grade.forma
        k0, j0, i0 = max(0, int(k0)), max(0, int(j0)), max(0, int(i0))
        k1, j1, i1 = min(nz, int(k1)), min(ny, int(j1)), min(nx, int(i1))
        if self.mascara.size == 0:
            self.mascara = np.zeros((max(k1 - k0, 1), max(j1 - j0, 1), max(i1 - i0, 1)), bool)
            self.offset = (k0, j0, i0)
            return
        a0, b0, c0 = self.offset
        a1, b1, c1 = a0 + self.mascara.shape[0], b0 + self.mascara.shape[1], c0 + self.mascara.shape[2]
        n0, m0, l0 = min(a0, k0), min(b0, j0), min(c0, i0)
        n1, m1, l1 = max(a1, k1), max(b1, j1), max(c1, i1)
        if (n0, m0, l0, n1, m1, l1) == (a0, b0, c0, a1, b1, c1):
            return
        nova = np.zeros((n1 - n0, m1 - m0, l1 - l0), bool)
        nova[a0 - n0:a1 - n0, b0 - m0:b1 - m0, c0 - l0:c1 - l0] = self.mascara
        self.mascara, self.offset = nova, (n0, m0, l0)

    def aparar(self) -> None:
        """Recorte justo em volta do que está marcado."""
        m = self.mascara
        if m.size == 0:
            return
        if not m.any():
            self.mascara = np.zeros((0, 0, 0), bool)
            return
        ks, js, is_ = (np.flatnonzero(m.any(axis=ax)) for ax in ((1, 2), (0, 2), (0, 1)))
        k0, k1, j0, j1, i0, i1 = ks[0], ks[-1] + 1, js[0], js[-1] + 1, is_[0], is_[-1] + 1
        if (k0, j0, i0) == (0, 0, 0) and (k1, j1, i1) == m.shape:
            return
        self.mascara = m[k0:k1, j0:j1, i0:i1].copy()
        o = self.offset
        self.offset = (o[0] + int(k0), o[1] + int(j0), o[2] + int(i0))

    def definir(self, cheia_ou_recorte: np.ndarray, offset=(0, 0, 0)) -> None:
        self.mascara = np.asarray(cheia_ou_recorte, bool)
        self.offset = tuple(int(x) for x in offset)
        self.aparar()

    # ------------------------------------------------------------ desfazer
    def _foto(self) -> tuple:
        m = self.mascara
        return (m.shape, self.offset, zlib.compress(np.packbits(m.ravel()).tobytes(), 1))

    @staticmethod
    def _de_foto(f) -> tuple[np.ndarray, tuple]:
        forma, off, dados = f
        n = int(np.prod(forma))
        m = np.unpackbits(np.frombuffer(zlib.decompress(dados), np.uint8))[:n].reshape(forma).astype(bool)
        return m, off

    def guardar_para_desfazer(self) -> None:
        self._desfazer.append(self._foto())
        del self._desfazer[:-MAX_DESFAZER]
        self._refazer.clear()

    def pode_desfazer(self) -> bool:
        return bool(self._desfazer)

    def pode_refazer(self) -> bool:
        return bool(self._refazer)

    def desfazer(self) -> bool:
        if not self._desfazer:
            return False
        self._refazer.append(self._foto())
        self.mascara, self.offset = self._de_foto(self._desfazer.pop())
        self.alterada = True
        return True

    def refazer(self) -> bool:
        if not self._refazer:
            return False
        self._desfazer.append(self._foto())
        self.mascara, self.offset = self._de_foto(self._refazer.pop())
        self.alterada = True
        return True

    # ------------------------------------------------------------ guardar
    def para_meta(self) -> dict:
        """A máscara compacta (para a lesão guardada e para reabrir)."""
        return {"forma": list(self.mascara.shape), "offset": list(self.offset),
                "bits": base64.b64encode(zlib.compress(np.packbits(self.mascara.ravel()).tobytes(), 9)).decode()}

    def mask_volume(self, grade: Grade):
        """A `MaskVolume` (desenho em qualquer plano de qualquer série do exame)."""
        from ipe.imaging.overlays import MaskVolume
        k0, j0, i0 = self.offset
        m = self.mascara if self.mascara.size else np.zeros((1, 1, 1), bool)
        return MaskVolume(m, grade.para_mm([i0, j0, k0])[0], grade.matriz, self.cor, self.nome)


# ====================================================================== entrada
def de_mask_volume(mv, grade: Grade, nome: str = "", cor=None, tipo: str = "lesão", fonte: str = "",
                   chave: str = "") -> Estrutura:
    """Uma `MaskVolume` (em qualquer grade, em mm) reamostrada na grade de referência — cada voxel da
    referência olha o voxel da máscara mais próximo do seu centro."""
    e = Estrutura(nome or getattr(mv, "label", "") or "Estrutura", tuple(cor or mv.color), tipo=tipo,
                  fonte=fonte, chave_origem=chave)
    ijk = grade.para_ijk(mv.cantos())
    nz, ny, nx = grade.forma
    lo = np.floor(ijk.min(axis=0)).astype(int) - 1
    hi = np.ceil(ijk.max(axis=0)).astype(int) + 2
    i0, j0, k0 = max(0, lo[0]), max(0, lo[1]), max(0, lo[2])
    i1, j1, k1 = min(nx, hi[0]), min(ny, hi[1]), min(nz, hi[2])
    if i0 >= i1 or j0 >= j1 or k0 >= k1:
        return e
    rec = np.zeros((k1 - k0, j1 - j0, i1 - i0), bool)
    J, I = np.meshgrid(np.arange(j0, j1, dtype=float), np.arange(i0, i1, dtype=float), indexing="ij")
    inv = mv._inv
    mz, my, mx = mv.mascara.shape
    for k in range(k0, k1):
        pts = grade.para_mm(np.stack([I.ravel(), J.ravel(), np.full(I.size, float(k))], axis=1))
        q = np.rint((pts - mv.origem) @ inv.T).astype(np.int64)
        ok = (q[:, 0] >= 0) & (q[:, 0] < mx) & (q[:, 1] >= 0) & (q[:, 1] < my) & (q[:, 2] >= 0) & (q[:, 2] < mz)
        v = np.zeros(len(q), bool)
        v[ok] = mv.mascara[q[ok, 2], q[ok, 1], q[ok, 0]]
        rec[k - k0] = v.reshape(I.shape)
    e.definir(rec, (k0, j0, i0))
    return e


def de_meta(d: dict, grade: Grade, nome: str, cor, **kw) -> Estrutura:
    forma = tuple(int(x) for x in d["forma"])
    n = int(np.prod(forma))
    m = np.unpackbits(np.frombuffer(zlib.decompress(base64.b64decode(d["bits"])), np.uint8))[:n]
    e = Estrutura(nome, cor, **kw)
    e.definir(m.reshape(forma).astype(bool), d.get("offset", (0, 0, 0)))
    return e


# ====================================================================== limites da edição (0.99.44)
@dataclass
class Limites:
    """Onde a edição pode pôr voxel (como as opções de máscara do Segment Editor do 3D Slicer).

    - `area`: "tudo"; "dentro" (só dentro da estrutura `alvo`); "fora" (só fora das `outras` visíveis).
    - `faixa` (mín, máx) com `dados`: só voxels com intensidade na faixa — vale para todas as ferramentas.
    - `sobrescrever`: o que a estrutura ganha sai das outras (não travadas); sem isso, sobrepõem.
    Valem para o que **entra** (pincel, crescer, buracos, interpolação); apagar não é limitado.
    """
    area: str = "tudo"
    alvo: "Estrutura | None" = None
    outras: list = field(default_factory=list)
    faixa: tuple | None = None
    dados: np.ndarray | None = None
    sobrescrever: bool = False

    def ativo(self) -> bool:
        return self.area != "tudo" or self.faixa is not None

    def permitido(self, caixa, e: "Estrutura") -> np.ndarray:
        k0, k1, j0, j1, i0, i1 = caixa
        m = np.ones((k1 - k0, j1 - j0, i1 - i0), bool)
        if self.faixa is not None and self.dados is not None:
            v = self.dados[k0:k1, j0:j1, i0:i1]
            m &= (v >= self.faixa[0]) & (v <= self.faixa[1])
        if self.area == "dentro" and self.alvo is not None and self.alvo is not e:
            m &= _recorte_de(self.alvo, caixa)
        elif self.area == "fora":
            for o in self.outras:
                if o is not e and o.visivel and not o.vazia():
                    m &= ~_recorte_de(o, caixa)
        return m


def _de_foto(foto) -> "Estrutura":
    m, off = Estrutura._de_foto(foto)
    return Estrutura("antes", (0, 0, 0), m, off)


def restringir(e: "Estrutura", antes, limites: "Limites | None") -> int:
    """Depois de uma operação: o que entrou fora dos limites sai. `antes`: a foto do desfazer (ou uma
    Estrutura). Devolve os voxels tirados."""
    if limites is None or not limites.ativo() or e.vazia():
        return 0
    velha = antes if isinstance(antes, Estrutura) else _de_foto(antes)
    cx = _caixa_de(e)
    novos = e.mascara & ~_recorte_de(velha, cx)
    if not novos.any():
        return 0
    tirar = novos & ~limites.permitido(cx, e)
    n = int(tirar.sum())
    if n:
        e.mascara = e.mascara & ~tirar
        e.aparar()
    return n


def sobrescrever(e: "Estrutura", antes, outras) -> list:
    """O que `e` ganhou sai das outras estruturas (não travadas). Cada uma que mudou guarda o seu
    desfazer. Devolve as que mudaram."""
    if e.vazia():
        return []
    velha = antes if isinstance(antes, Estrutura) else _de_foto(antes)
    cx = _caixa_de(e)
    novos = Estrutura("novos", (0, 0, 0), e.mascara & ~_recorte_de(velha, cx), cx[0::2])
    if novos.vazia():
        return []
    mudaram = []
    for o in outras:
        if o is e or o.travada or o.vazia():
            continue
        co = _caixa_de(o)
        tira = o.mascara & _recorte_de(novos, co)
        if tira.any():
            o.guardar_para_desfazer()
            o.mascara = o.mascara & ~tira
            o.aparar()
            o.alterada = True
            mudaram.append(o)
    return mudaram


# ====================================================================== pincel
def pintar(e: Estrutura, grade: Grade, centro_mm, raio_mm: float, normal=None, apagar: bool = False,
           dados: np.ndarray | None = None, faixa: tuple | None = None, proibidas=(),
           limites: "Limites | None" = None) -> int:
    """Pincel (ou borracha) em volta de `centro_mm`.

    Com `normal` (a do plano do quadro): um **disco** de raio `raio_mm` no plano, da espessura de um
    voxel — pinta só o corte que se vê, em qualquer plano (inclusive reformatado). Sem `normal`: uma
    **esfera**. `faixa` (mín, máx) com `dados` (o volume da grade): só voxels com valor na faixa (o pincel
    "inteligente", que não sai da lesão). `proibidas`: estruturas travadas — o pincel não pinta por
    cima delas. Devolve quantos voxels mudaram (não guarda o desfazer: quem chama guarda uma vez por traço).
    """
    if e.travada:
        return 0
    c = np.asarray(centro_mm, float)
    dx, dy, dz = grade.espacamento
    r = float(raio_mm)
    ci = grade.para_ijk(c)[0]
    ri = np.array([r / dx, r / dy, r / dz]) + 1
    lo = np.floor(ci - ri).astype(int)
    hi = np.ceil(ci + ri).astype(int) + 1
    nz, ny, nx = grade.forma
    i0, j0, k0 = max(0, lo[0]), max(0, lo[1]), max(0, lo[2])
    i1, j1, k1 = min(nx, hi[0]), min(ny, hi[1]), min(nz, hi[2])
    if i0 >= i1 or j0 >= j1 or k0 >= k1:
        return 0
    K, J, I = np.meshgrid(np.arange(k0, k1), np.arange(j0, j1), np.arange(i0, i1), indexing="ij")
    d = grade.para_mm(np.stack([I.ravel(), J.ravel(), K.ravel()], axis=1)) - c
    if normal is not None:
        n = np.asarray(normal, float)
        n = n / max(float(np.linalg.norm(n)), 1e-9)
        alt = d @ n
        meia = 0.5 * float(np.abs(grade.matriz.T @ n).max())    # meio voxel na direção do plano
        sel = (np.abs(alt) <= meia + 1e-6) & (np.linalg.norm(d - np.outer(alt, n), axis=1) <= r)
    else:
        sel = np.linalg.norm(d, axis=1) <= r
    sel = sel.reshape(K.shape)
    if not apagar and dados is not None and faixa is not None:
        v = dados[k0:k1, j0:j1, i0:i1]
        sel &= (v >= faixa[0]) & (v <= faixa[1])
    for p in proibidas:
        if p is e or p.vazia():
            continue
        sel &= ~_recorte_de(p, (k0, k1, j0, j1, i0, i1))
    if not apagar and limites is not None and limites.ativo():
        sel &= limites.permitido((k0, k1, j0, j1, i0, i1), e)
    if not sel.any():
        return 0
    if apagar:
        if e.vazia():
            return 0
        sub = _recorte_de(e, (k0, k1, j0, j1, i0, i1))
        mudou = int((sub & sel).sum())
        if mudou:
            _escrever(e, (k0, k1, j0, j1, i0, i1), sub & ~sel)
            e.alterada = True
        return mudou
    e.expandir(grade, k0, k1, j0, j1, i0, i1)
    a0, b0, c0 = e.offset
    alvo = e.mascara[k0 - a0:k1 - a0, j0 - b0:j1 - b0, i0 - c0:i1 - c0]
    mudou = int((sel & ~alvo).sum())
    alvo |= sel
    if mudou:
        e.alterada = True
    return mudou


def _recorte_de(e: Estrutura, caixa) -> np.ndarray:
    """A máscara de `e` na caixa (k0, k1, j0, j1, i0, i1) da grade (zeros fora do recorte dela)."""
    k0, k1, j0, j1, i0, i1 = caixa
    out = np.zeros((k1 - k0, j1 - j0, i1 - i0), bool)
    if e.mascara.size == 0:
        return out
    a0, b0, c0 = e.offset
    a1, b1, c1 = a0 + e.mascara.shape[0], b0 + e.mascara.shape[1], c0 + e.mascara.shape[2]
    ka, kb = max(k0, a0), min(k1, a1)
    ja, jb = max(j0, b0), min(j1, b1)
    ia, ib = max(i0, c0), min(i1, c1)
    if ka < kb and ja < jb and ia < ib:
        out[ka - k0:kb - k0, ja - j0:jb - j0, ia - i0:ib - i0] = \
            e.mascara[ka - a0:kb - a0, ja - b0:jb - b0, ia - c0:ib - c0]
    return out


def _escrever(e: Estrutura, caixa, valores: np.ndarray) -> None:
    k0, k1, j0, j1, i0, i1 = caixa
    a0, b0, c0 = e.offset
    a1, b1, c1 = a0 + e.mascara.shape[0], b0 + e.mascara.shape[1], c0 + e.mascara.shape[2]
    ka, kb = max(k0, a0), min(k1, a1)
    ja, jb = max(j0, b0), min(j1, b1)
    ia, ib = max(i0, c0), min(i1, c1)
    if ka < kb and ja < jb and ia < ib:
        e.mascara[ka - a0:kb - a0, ja - b0:jb - b0, ia - c0:ib - c0] = \
            valores[ka - k0:kb - k0, ja - j0:jb - j0, ia - i0:ib - i0]


# ====================================================================== morfologia
def _bola(grade: Grade, mm: float, so_no_plano: bool = False) -> list[tuple[int, int, int]]:
    dx, dy, dz = grade.espacamento
    rk = 0 if so_no_plano else int(np.floor(mm / dz))
    rj, ri = int(np.floor(mm / dy)), int(np.floor(mm / dx))
    out = []
    for a in range(-rk, rk + 1):
        for b in range(-rj, rj + 1):
            for c in range(-ri, ri + 1):
                if (a * dz) ** 2 + (b * dy) ** 2 + (c * dx) ** 2 <= mm * mm + 1e-9:
                    out.append((a, b, c))
    return out


def _dilatar(m: np.ndarray, bola) -> np.ndarray:
    out = np.zeros_like(m)
    nz, ny, nx = m.shape
    for a, b, c in bola:
        src = m[max(0, -a):nz - max(0, a), max(0, -b):ny - max(0, b), max(0, -c):nx - max(0, c)]
        out[max(0, a):nz - max(0, -a), max(0, b):ny - max(0, -b), max(0, c):nx - max(0, -c)] |= src
    return out


def crescer(e: Estrutura, grade: Grade, mm: float, so_no_plano: bool = False, proibidas=()) -> int:
    """Margem de `mm` (negativo encolhe), numa bola anisotrópica com o espaçamento da grade.
    `so_no_plano`: só nos cortes (sem passar para o corte de cima e o de baixo). Devolve a variação
    em voxels."""
    if e.travada or e.vazia() or abs(mm) < 1e-6:
        return 0
    antes = e.voxels
    bola = _bola(grade, abs(mm), so_no_plano)
    if len(bola) <= 1:
        return 0
    rk = max(abs(a) for a, _b, _c in bola)
    rj = max(abs(b) for _a, b, _c in bola)
    ri = max(abs(c) for _a, _b, c in bola)
    k0, j0, i0 = e.offset
    nz, ny, nx = e.mascara.shape
    e.expandir(grade, k0 - rk - 1, k0 + nz + rk + 1, j0 - rj - 1, j0 + ny + rj + 1, i0 - ri - 1, i0 + nx + ri + 1)
    m = e.mascara
    if mm > 0:
        novo = _dilatar(m, bola)
        for p in proibidas:
            if p is not e and not p.vazia():
                novo &= ~_recorte_de(p, _caixa_de(e)) | m
    else:
        # erosão: o complemento dilatado; a borda da grade conta como fora
        pad = np.pad(~m, 1, constant_values=True)
        novo = ~_dilatar(pad, bola)[1:-1, 1:-1, 1:-1]
    e.mascara = novo
    e.aparar()
    e.alterada = True
    return e.voxels - antes


def _caixa_de(e: Estrutura):
    k0, j0, i0 = e.offset
    nz, ny, nx = e.mascara.shape
    return (k0, k0 + nz, j0, j0 + ny, i0, i0 + nx)


def rotular(m: np.ndarray) -> tuple[np.ndarray, int]:
    """Componentes conexos (6-vizinhos em 3D, 4 em 2D) sem SciPy: união por ponteiros, vetorizada.
    Devolve (rótulos int32 com 0 no fundo e 1..n nas ilhas, n)."""
    m = np.asarray(m, bool)
    idx = np.full(m.shape, -1, np.int64)
    n = int(m.sum())
    if n == 0:
        return np.zeros(m.shape, np.int32), 0
    idx[m] = np.arange(n)
    pares_a, pares_b = [], []
    for ax in range(m.ndim):
        sl_a = [slice(None)] * m.ndim
        sl_b = [slice(None)] * m.ndim
        sl_a[ax], sl_b[ax] = slice(None, -1), slice(1, None)
        a, b = idx[tuple(sl_a)], idx[tuple(sl_b)]
        ok = (a >= 0) & (b >= 0)
        pares_a.append(a[ok])
        pares_b.append(b[ok])
    ea, eb = np.concatenate(pares_a), np.concatenate(pares_b)
    pai = np.arange(n)
    for _ in range(200):
        pa, pb = pai[ea], pai[eb]
        dif = pa != pb
        if not dif.any():
            break
        lo, hi = np.minimum(pa[dif], pb[dif]), np.maximum(pa[dif], pb[dif])
        np.minimum.at(pai, hi, lo)
        while True:
            pp = pai[pai]
            if np.array_equal(pp, pai):
                break
            pai = pp
    raizes, rot = np.unique(pai, return_inverse=True)
    out = np.zeros(m.shape, np.int32)
    out[m] = rot.astype(np.int32) + 1
    return out, len(raizes)


def ilhas(e: Estrutura, grade: Grade) -> list[float]:
    """Volume (mL) de cada ilha, da maior para a menor."""
    if e.vazia():
        return []
    rot, n = rotular(e.mascara)
    tam = np.bincount(rot.ravel(), minlength=n + 1)[1:]
    return sorted((float(t) * grade.ml_por_voxel for t in tam), reverse=True)


def limpar_ilhas(e: Estrutura, grade: Grade, so_a_maior: bool = True, min_ml: float = 0.0) -> int:
    """Mantém só a maior ilha, ou tira as menores que `min_ml`. Devolve quantas ilhas saíram."""
    if e.travada or e.vazia():
        return 0
    rot, n = rotular(e.mascara)
    if n <= 1 and (so_a_maior or n == 0):
        return 0
    tam = np.bincount(rot.ravel(), minlength=n + 1)
    tam[0] = 0
    if so_a_maior:
        manter = np.zeros(n + 1, bool)
        manter[int(np.argmax(tam))] = True
    else:
        manter = tam * grade.ml_por_voxel >= min_ml
        manter[0] = False
    saem = int(n - manter[1:].sum())
    if saem:
        e.mascara = manter[rot]
        e.aparar()
        e.alterada = True
    return saem


def preencher_buracos(e: Estrutura, por_corte: bool = True) -> int:
    """Fecha os buracos (fundo que não encosta na borda do recorte): corte a corte (o padrão — uma
    lesão em anel aberta para cima e para baixo também é fechada) ou em 3D. Devolve os voxels ganhos."""
    if e.travada or e.vazia():
        return 0
    m = e.mascara
    antes = int(m.sum())
    if por_corte:
        novo = m.copy()
        for k in range(m.shape[0]):
            if m[k].any():
                novo[k] = _sem_buracos(m[k])
    else:
        novo = _sem_buracos(m)
    e.mascara = novo
    ganho = int(novo.sum()) - antes
    if ganho:
        e.alterada = True
    return ganho


def _sem_buracos(m: np.ndarray) -> np.ndarray:
    pad = np.pad(~m, 1, constant_values=True)
    rot, _n = rotular(pad)
    borda = rot.flat[0]                    # o canto é fundo e encosta na borda
    fora = rot == borda
    sl = tuple(slice(1, -1) for _ in range(m.ndim))
    return ~fora[sl]


def aplicar_faixa(e: Estrutura, dados: np.ndarray, lo: float, hi: float) -> int:
    """Tira os voxels fora da faixa de intensidade (gordura, ar, osso). Devolve os voxels tirados."""
    if e.travada or e.vazia():
        return 0
    v = dados[e.caixa()]
    fora = e.mascara & ~((v >= lo) & (v <= hi))
    n = int(fora.sum())
    if n:
        e.mascara = e.mascara & ~fora
        e.aparar()
        e.alterada = True
    return n


# ====================================================================== interpolação entre cortes
def _distancia_2d(m: np.ndarray, sx: float, sy: float, maximo: float) -> np.ndarray:
    """Distância (mm) de cada pixel ao conjunto `m` (0 dentro), por chanfro iterado até `maximo`."""
    INF = 1e9
    d = np.where(m, 0.0, INF)
    sd = float(np.hypot(sx, sy))
    passos = ((0, 1, sx), (0, -1, sx), (1, 0, sy), (-1, 0, sy), (1, 1, sd), (1, -1, sd), (-1, 1, sd), (-1, -1, sd))
    h, w = m.shape
    for _ in range(int(maximo / min(sx, sy)) + 2):
        novo = d.copy()
        for a, b, c in passos:
            src = d[max(0, -a):h - max(0, a), max(0, -b):w - max(0, b)]
            dst = novo[max(0, a):h - max(0, -a), max(0, b):w - max(0, -b)]
            np.minimum(dst, src + c, out=dst)
        if np.array_equal(novo, d):
            break
        d = novo
    return np.minimum(d, maximo)


def _sinalizada(m: np.ndarray, sx: float, sy: float, maximo: float) -> np.ndarray:
    """Distância com sinal: positiva fora, negativa dentro (borda ≈ 0)."""
    return _distancia_2d(m, sx, sy, maximo) - _distancia_2d(~m, sx, sy, maximo)


def interpolar(e: Estrutura, grade: Grade, max_lacuna: int = 12) -> int:
    """Preenche os cortes vazios entre dois cortes desenhados (no eixo dos cortes da grade), pela
    interpolação das formas (distância com sinal) — desenha-se a lesão a cada 3 ou 4 cortes e o meio
    sai sozinho. Lacunas maiores que `max_lacuna` cortes ficam como estão. Devolve os cortes preenchidos."""
    if e.travada or e.vazia():
        return 0
    m = e.mascara
    cheios = [k for k in range(m.shape[0]) if m[k].any()]
    dx, dy, _dz = grade.espacamento
    feitos = 0
    for a, b in zip(cheios, cheios[1:]):
        if b - a <= 1 or b - a > max_lacuna + 1:
            continue
        uniao = m[a] | m[b]
        js, is_ = np.flatnonzero(uniao.any(axis=1)), np.flatnonzero(uniao.any(axis=0))
        j0, j1, i0, i1 = js[0], js[-1] + 1, is_[0], is_[-1] + 1
        pad = 3
        j0, i0 = max(0, j0 - pad), max(0, i0 - pad)
        j1, i1 = min(m.shape[1], j1 + pad), min(m.shape[2], i1 + pad)
        ma, mb = m[a, j0:j1, i0:i1], m[b, j0:j1, i0:i1]
        maximo = float(np.hypot((j1 - j0) * dy, (i1 - i0) * dx))
        da, db = _sinalizada(ma, dx, dy, maximo), _sinalizada(mb, dx, dy, maximo)
        for k in range(a + 1, b):
            t = (k - a) / (b - a)
            m[k, j0:j1, i0:i1] |= ((1 - t) * da + t * db) <= 0
            feitos += 1
    if feitos:
        e.alterada = True
    return feitos


# ====================================================================== combinar
def combinar(a: Estrutura, b: Estrutura, grade: Grade, op: str, nome: str = "", cor=None) -> Estrutura:
    """Nova estrutura: 'uniao', 'subtracao' (a − b) ou 'intersecao'."""
    caixas = [c for c in (_caixa_de(a) if not a.vazia() else None, _caixa_de(b) if not b.vazia() else None) if c]
    simbolo = {"uniao": "∪", "subtracao": "−", "intersecao": "∩"}[op]
    out = Estrutura(nome or f"{a.nome} {simbolo} {b.nome}", tuple(cor or a.cor), tipo=a.tipo, fonte="combinação")
    if not caixas:
        return out
    k0 = min(c[0] for c in caixas); k1 = max(c[1] for c in caixas)   # noqa: E702
    j0 = min(c[2] for c in caixas); j1 = max(c[3] for c in caixas)   # noqa: E702
    i0 = min(c[4] for c in caixas); i1 = max(c[5] for c in caixas)   # noqa: E702
    cx = (k0, k1, j0, j1, i0, i1)
    ma, mb = _recorte_de(a, cx), _recorte_de(b, cx)
    m = ma | mb if op == "uniao" else (ma & ~mb if op == "subtracao" else ma & mb)
    out.definir(m, (k0, j0, i0))
    return out


# ====================================================================== números
def estatisticas(e: Estrutura, grade: Grade, dados: np.ndarray | None = None) -> dict:
    """Volume, voxels, ilhas, eixos e (com `dados`) média, desvio, mínimo e máximo."""
    from ipe.imaging.segment import tres_eixos
    out = {"ml": e.ml(grade), "voxels": e.voxels}
    if e.vazia():
        return out
    if dados is not None:
        v = dados[e.caixa()][e.mascara].astype(np.float64)
        out.update(media=float(v.mean()), dp=float(v.std()), minimo=float(v.min()), maximo=float(v.max()))
        out.update(primeira_ordem(v))
    out.update(forma(e, grade))
    pts = e.pontos_mm(grade)
    if len(pts) > 60000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 60000, replace=False)]
    try:
        out["eixos_mm"] = tuple(float(x) for x in tres_eixos(pts, grade.espacamento))
    except Exception:  # noqa: BLE001
        pass
    k = np.flatnonzero(e.mascara.any(axis=(1, 2)))
    out["cortes"] = int(len(k))
    return out


def primeira_ordem(v: np.ndarray) -> dict:
    """Estatística de primeira ordem (as definições do pyradiomics / IBSI): mediana, percentis 10 e 90,
    assimetria, curtose (excesso, 0 na normal), entropia (bits, histograma de 64 classes), uniformidade."""
    v = np.asarray(v, np.float64).ravel()
    if v.size == 0:
        return {}
    out = {"mediana": float(np.median(v)), "p10": float(np.percentile(v, 10)), "p90": float(np.percentile(v, 90))}
    m, s = float(v.mean()), float(v.std())
    if s > 0 and v.size > 2:
        z = (v - m) / s
        out["assimetria"] = float(np.mean(z ** 3))
        out["curtose"] = float(np.mean(z ** 4) - 3.0)
    else:
        out["assimetria"] = out["curtose"] = 0.0
    lo, hi = float(v.min()), float(v.max())
    h = np.histogram(v, bins=64, range=(lo, hi if hi > lo else lo + 1))[0].astype(np.float64)
    p = h[h > 0] / h.sum()
    out["entropia"] = float(-(p * np.log2(p)).sum())
    out["uniformidade"] = float((p ** 2).sum())
    return out


def forma(e: "Estrutura", grade: Grade) -> dict:
    """Forma 3D: superfície (faces expostas dos voxels), esfericidade, maior diâmetro (Feret, entre os
    voxels da borda), alongamento e achatamento (raízes das razões dos autovalores — pyradiomics)."""
    if e.vazia():
        return {}
    m = e.mascara
    dx, dy, dz = grade.espacamento
    p = np.pad(m, 1)
    borda = np.zeros_like(p)
    for ax in range(3):
        d = np.diff(p.astype(np.int8), axis=ax) != 0
        sl_a = [slice(None)] * 3
        sl_b = [slice(None)] * 3
        sl_a[ax], sl_b[ax] = slice(None, -1), slice(1, None)
        borda[tuple(sl_a)] |= d & p[tuple(sl_a)]
        borda[tuple(sl_b)] |= d & p[tuple(sl_b)]
    vol = e.voxels * dx * dy * dz
    out = {}
    # superfície pela malha (marching cubes sem suavizar, como o pyradiomics); contar faces de voxel
    # superestima ~50% numa esfera. Em objeto pequeno (raio < ~10 voxels) a esfericidade é aproximada.
    area = 0.0
    if m.size <= 30_000_000:
        from ipe.imaging.surface import mesh_from_mask
        v, f = mesh_from_mask(m, (dz, dy, dx), smooth=0)[:2]
        if len(f):
            a, b = v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]
            area = float(0.5 * np.linalg.norm(np.cross(a, b), axis=1).sum())
    if area > 0:
        out["superficie_mm2"] = area
        out["esfericidade"] = float(min(1.0, (np.pi ** (1 / 3)) * ((6 * vol) ** (2 / 3)) / area))
    k, j, i = np.nonzero(borda[1:-1, 1:-1, 1:-1])
    pts = np.stack([i * dx, j * dy, k * dz], axis=1) if len(k) else np.zeros((0, 3))
    if len(pts) > 2500:
        pts = pts[np.random.default_rng(0).choice(len(pts), 2500, replace=False)]
    if len(pts) >= 2:
        best = 0.0
        for a0 in range(0, len(pts), 500):
            d2 = ((pts[a0:a0 + 500, None, :] - pts[None, :, :]) ** 2).sum(-1)
            best = max(best, float(d2.max()))
        out["feret_mm"] = float(np.sqrt(best))
    todos = e.pontos_mm(grade)
    if len(todos) > 60000:
        todos = todos[np.random.default_rng(1).choice(len(todos), 60000, replace=False)]
    if len(todos) >= 4:
        lam = np.sort(np.linalg.eigvalsh(np.cov((todos - todos.mean(0)).T)))[::-1]
        if lam[0] > 0:
            out["alongamento"] = float(np.sqrt(max(lam[1], 0) / lam[0]))
            out["achatamento"] = float(np.sqrt(max(lam[2], 0) / lam[0]))
    return out


def texto_do_laudo(estruturas, grade: Grade, dados=None) -> str:
    """Uma linha por estrutura: nome, volume e eixos."""
    linhas = []
    for e in estruturas:
        if e.vazia():
            continue
        s = estatisticas(e, grade, dados)
        if s.get("eixos_mm"):
            a, b, c = s["eixos_mm"]
            linhas.append(f"{e.nome}: {s['ml']:.2f} mL ({a:.1f} × {b:.1f} × {c:.1f} mm).")
        else:
            linhas.append(f"{e.nome}: {s['ml']:.2f} mL.")
    return "\n".join(linhas)


def nova(estruturas, nome: str = "", tipo: str = "lesão") -> Estrutura:
    usados = {e.cor for e in estruturas}
    cor = next((c for c in CORES if c not in usados), CORES[len(estruturas) % len(CORES)])
    n = len(estruturas) + 1
    return Estrutura(nome or f"Estrutura {n}", cor, tipo=tipo)
