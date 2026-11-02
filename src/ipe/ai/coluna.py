"""Níveis da coluna: vértebras e discos com nome, visíveis em qualquer corte (0.99.2).

Pedido dele: identificar automaticamente os discos intervertebrais em TC e RM — "ler e laudar: ver o
nível em qualquer corte é o principal".

**Os modelos** (TotalSegmentator, tarefas abertas):

| | vértebras com nome | discos (todos numa classe só) |
|---|---|---|
| TC | `total` (C1…L5, S1, sacro) | `vertebrae_body` |
| RM | `vertebrae_mr` (C1…L5, sacro) | `total_mr` (`intervertebral_discs`) |

**Nenhum modelo dá o disco já com nome.** O disco fica entre duas vértebras que o modelo nomeia: cada
voxel de disco olha os dois centros de vértebra mais próximos; se forem vizinhos na coluna (L4 e L5),
o voxel é do disco L4-L5. Sem componente conexo, sem scipy: só distância aos ~25 centros.

**A numeração é o ponto frágil** — vértebra de transição (L6, sacralização), 13 pares de costelas, série
só torácica sem onde ancorar a contagem. O programa avisa quando a contagem lombar não é 5 e deixa
**renumerar ±1** com um clique (todos os rótulos andam um nível).

Na tela vai **só o rótulo**, não a máscara pintada: a máscara cobriria justamente o disco que se está
lendo. O rótulo aparece onde o plano do quadro corta o disco/vértebra — em qualquer série e plano do
exame (é a `MaskVolume`, a mesma das lesões).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

MARCA = "Níveis da coluna · TotalSegmentator"
SERIE = 972
ORDEM = [f"C{i}" for i in range(1, 8)] + [f"T{i}" for i in range(1, 13)] + [f"L{i}" for i in range(1, 6)] + \
    ["S1", "S2"]                   # S2: o sacro abaixo de uma S1 lombarizada (0.99.23)
POS = {n: i for i, n in enumerate(ORDEM)}
COR_DISCO = (255, 210, 60)
COR_VERTEBRA = (120, 200, 255)
MIN_ML_DISCO = 0.15            # pedaço menor que isso não é disco (ruído na borda)
MIN_CORTES = 8                 # RM sagital lombar costuma ter 13–17 cortes

# Preferências ▸ CAD/IA ▸ Níveis da coluna (0.99.2)
CHAVE_AUTO = "coluna.auto"
CHAVE_EXAME_CONTEM = "coluna.exame_contem"
CHAVE_MODALIDADES = "coluna.modalidades"
CHAVE_PRIOR_CT = "coluna.prioridade_ct"
CHAVE_PRIOR_MR = "coluna.prioridade_mr"
CHAVE_ESPESSURA = "coluna.espessura_max"
CHAVE_MIN_CORTES = "coluna.min_cortes"
CHAVE_DESTINOS = "coluna.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "COLUNA|SPINE|LOMBAR|LOMBO|CERVICAL|TORACICA|TORÁCICA|DORSAL|SACR|VERTEBR|CIFO|ESCOLIO",
    CHAVE_MODALIDADES: ["CT", "MR"],
    CHAVE_PRIOR_CT: "OSSO|BONE|COLUNA|SPINE|SAG|AX",
    CHAVE_PRIOR_MR: "SAG T2|T2 SAG|SAGITAL T2|T2 SAGITAL|SAG STIR|STIR SAG|SAG T1|T1 SAG|SAG",
    CHAVE_ESPESSURA: 4.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_MR, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}


# 0.99.7: *"sobre a IA na coluna, apenas nomeie as vértebras. desconsidere a altura do disco e da
# vértebra"*. As medidas (0.99.3–0.99.5) ficam no código, desligadas: sem tabelas, sem a segunda
# sagital, sem o 📏 na lista, e a RM volta ao modelo de discos de 3 mm (mais rápido). Os testes das
# medidas ligam isto de propósito.
MEDIR_DISPONIVEL = False
_SO_COM_MEDIR = ("coluna.medir", "coluna.sequencias")


def config(settings, chave):
    if chave in _SO_COM_MEDIR and not MEDIR_DISPONIVEL:
        return False if chave == "coluna.medir" else 1
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


def ja_identificado(repo, study_uid: str) -> bool:
    from ipe.ai import totalseg as TS
    return TS.ja_segmentado(repo, study_uid, MARCA)


def tarefas(modalidade: str, settings=None) -> list[dict]:
    """O que pedir ao trabalhador. Na TC, o `total` rápido basta para dar nome às vértebras; os discos
    vêm do `vertebrae_body` (1,5 mm). Na RM, para **medir** (0.99.3) os discos vêm do `total_mr`
    completo (1,5 mm): o de `roi_subset` usa 3 mm, grosso demais para uma altura de ~10 mm."""
    if (modalidade or "").upper() == "MR":
        medir = bool(config(settings, CHAVE_MEDIR))
        discos = ({"nome": "total_mr", "rotulo": "discos (1,5 mm)"} if medir
                  else {"nome": "total_mr", "roi": ["intervertebral_discs"], "rotulo": "discos"})
        return [{"nome": "vertebrae_mr", "rotulo": "vértebras"}, discos]
    vertebras = [f"vertebrae_{n}" for n in ORDEM if n != "S2"] + ["sacrum"]
    # 0.99.23: as costelas dão a T12 (a da costela mais baixa) quando a série não pega a C2
    vertebras += [f"rib_{lado}_{i}" for lado in ("left", "right") for i in range(1, 13)]
    return [{"nome": "total", "roi": vertebras, "fast": True, "rotulo": "vértebras"},
            {"nome": "vertebrae_body", "rotulo": "discos"}]


def nome_da_vertebra(classe: str) -> str | None:
    """'vertebrae_L4' → 'L4'; 'sacrum' → 'S1' (o sacro faz o papel de S1 no disco L5-S1)."""
    if classe == "sacrum":
        return "S1"
    m = re.fullmatch(r"vertebrae_([CTL]\d{1,2}|S1)", classe or "")
    return m.group(1) if m and m.group(1) in POS else None


class ForaDaColuna(ValueError):
    """Renumerar empurraria um nível para antes de C1 ou depois de S2."""


def deslocar(nome: str, passo: int) -> str:
    """Renumerar: 'L4' + 1 → 'L5'; disco 'L4-L5' + 1 → 'L5-S1'; 'S1' + 1 → 'S2'. Fora da coluna
    (nome que não é nível), mantém. Passar de C1 ou de S2 é recusado (`ForaDaColuna`): até a 0.99.22
    o nome parava no fim da lista, e subir um nível dava duas S1."""
    if "-" in nome:
        a, b = nome.split("-", 1)
        return f"{deslocar(a, passo)}-{deslocar(b, passo)}"
    i = POS.get(nome)
    if i is None:
        return nome
    j = i + passo
    if j < 0 or j >= len(ORDEM):
        raise ForaDaColuna(f"{nome} {'+' if passo > 0 else '−'} {abs(passo)} sai da coluna "
                           f"({ORDEM[0]} a {ORDEM[-1]})")
    return ORDEM[j]


@dataclass
class Nivel:
    nome: str                  # o nível: "L4" ou "L4-L5" (o que conta para renumerar e para os discos)
    tipo: str                  # "vertebra" | "disco"
    mascara: np.ndarray        # bool (k, j, i) do recorte
    offset: tuple              # (k0, j0, i0)
    voxels: int
    cor: tuple = COR_VERTEBRA
    sacro: bool = False        # o sacro (a peça inteira): o nome dele é o do segmento de cima
    rotulo: str = ""           # o que aparece na tela ("S1 lombarizada"); vazio = o nome
    centro: object = None      # mm do paciente (centro dos voxels)


# ------------------------------------------------------------------ vértebra de transição (0.99.23)
# Pedido dele: *"a maior mudança que quero é com relação às vértebras de transição"*. Escolhas dele:
# nomes **lombarizada / sacralizada** (não L6, não "4 lombares"); contar **pela C2 e pela última
# costela**; Castellvi como **sugestão** que ele confirma.
LOMBOSSACRAL = {
    "": "sem transição lombossacral",
    "lombarizada": "S1 lombarizada (seis vértebras de tipo lombar)",
    "sacralizada": "L5 sacralizada (parcial: L5 ainda separada do sacro)",
    "fundida": "L5 sacralizada, fundida ao sacro (quatro vértebras lombares livres)",
    "possivel": "L5 com sinais de transição",
}
TORACOLOMBAR = {
    "": "",
    "costela_l1": "L1 com costela (transição toracolombar)",
    "t12_sem_costela": "T12 sem costela (transição toracolombar)",
}
CASTELLVI = ("", "Ia", "Ib", "IIa", "IIb", "IIIa", "IIIb", "IV")
ANCORAS = {
    "c2": "contando a partir de C2",
    "costela": "pela última costela (T12)",
    "c2_costela": "contando a partir de C2, conferida pela última costela",
    "outra_serie": "contando a partir de C2 em outra série do exame",
    "medico": "numeração ajustada pelo médico",
    "modelo": "pelos nomes da IA, sem C2 nem a última costela na série",
    "": "",
}
# o que mede o disco rudimentar e a apófise (Castellvi): números da definição, não do acervo dele
# (ele não tem exames com transição; marcar quando chegarem)
RUDIMENTAR = 0.5               # disco acima do sacro < metade da mediana dos dois de cima
APOFISE_LATERAL_MM = 28.0      # o que está a mais de 28 mm da linha média é apófise transversa
APOFISE_ALTA_MM = 19.0         # Castellvi I: apófise com 19 mm ou mais no crânio-caudal
CONTATO_MM = 2.0               # apófise a até 2 mm da asa sacral: pseudoarticulação ou fusão
ALCANCE_MM = 45.0              # a série precisa pegar ±45 mm da linha média para avaliar
VAO_CORPOS_MM = 3.0            # dois corpos com o mesmo nome: vão maior que isso os separa


@dataclass
class Numeracao:
    """De onde veio a numeração e o que se achou de transição. Vai no SEG (ImageComments, JSON) e na
    conferência do exame (`revisao_ia`, módulo "coluna")."""
    ancora: str = ""
    lombossacral: str = ""                 # derivado dos nomes; "sacralizada"/"possivel" vêm de indício
    lombossacral_medico: str = ""          # o que ele escolheu na janela (manda sobre o derivado)
    castellvi: str = ""
    castellvi_lado: str = ""               # "à direita" | "à esquerda" (tipo a)
    castellvi_fonte: str = ""              # "sugestão" | "médico"
    castellvi_motivo: str = ""
    ultima_costela: str = ""               # nível da vértebra que tem a costela mais baixa
    toracolombar: str = ""
    costelas_pares: int = 0                # 0 = a série não pega da C7 à última costela
    evidencias: list = field(default_factory=list)
    aviso_anterior: str = ""               # não bate com a confirmada num exame anterior do paciente
    confirmado_por: str = ""
    confirmado_em: str = ""

    def para_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict | None) -> "Numeracao":
        d = dict(d or {})
        campos = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in campos})

    @property
    def tipo_lombossacral(self) -> str:
        """O que vale: a escolha dele ("nenhuma" = ele disse que não há) ou o derivado."""
        if self.lombossacral_medico == "nenhuma":
            return ""
        return self.lombossacral_medico or self.lombossacral


@dataclass
class Niveis:
    itens: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    numeracao: Numeracao = field(default_factory=Numeracao)

    def nomes(self, tipo: str | None = None) -> list[str]:
        return [n.nome for n in self.itens if tipo is None or n.tipo == tipo]


def _mascara_de(idx: np.ndarray):
    """Recorte bool (k, j, i) e canto a partir dos índices dos voxels (n × 3)."""
    lo, hi = idx.min(axis=0), idx.max(axis=0) + 1
    m = np.zeros(tuple(int(x) for x in hi - lo), bool)
    rel = idx - lo
    m[rel[:, 0], rel[:, 1], rel[:, 2]] = True
    return m, (int(lo[0]), int(lo[1]), int(lo[2]))


def _mm(vol, idx: np.ndarray) -> np.ndarray:
    """Índices (k, j, i) → mm do paciente."""
    return vol.origin + idx[:, ::-1].astype(float) @ vol.matrix().T


def _dilatar(m: np.ndarray, r: int) -> np.ndarray:
    """Dilatação cúbica de `r` voxels, sem scipy (deslocamentos do numpy)."""
    out = m.copy()
    for _ in range(max(int(r), 0)):
        d = out.copy()
        for eixo in range(3):
            d[(slice(None),) * eixo + (slice(1, None),)] |= out[(slice(None),) * eixo + (slice(None, -1),)]
            d[(slice(None),) * eixo + (slice(None, -1),)] |= out[(slice(None),) * eixo + (slice(1, None),)]
        out = d
    return out


def _perto(idx_a: np.ndarray, idx_b: np.ndarray, r: int) -> bool:
    """Algum voxel de A a até `r` voxels de algum de B (mesma grade)?"""
    if not len(idx_a) or not len(idx_b):
        return False
    lo = np.minimum(idx_a.min(0), idx_b.min(0)) - r - 1
    hi = np.maximum(idx_a.max(0), idx_b.max(0)) + r + 2
    forma = tuple(int(x) for x in hi - lo)
    if np.prod(forma) > 60_000_000:
        return False
    mb = np.zeros(forma, bool)
    rb = idx_b - lo
    mb[rb[:, 0], rb[:, 1], rb[:, 2]] = True
    mb = _dilatar(mb, r)
    ra = idx_a - lo
    return bool(mb[ra[:, 0], ra[:, 1], ra[:, 2]].any())


@dataclass
class _Corpo:
    modelo: str                # o nome que a IA deu
    idx: np.ndarray            # (n × 3) voxels
    sacro: bool
    centro: np.ndarray         # mm
    nome: str = ""


def _corpos(vol, rotulos: dict, disco: np.ndarray) -> list[_Corpo]:
    """As vértebras da IA como **corpos físicos**, de cima para baixo.

    - Na TC o `total` tem `vertebrae_S1` e `sacrum`: encostados, são o sacro; separados (um disco no
      meio), a "S1" é uma vértebra livre — é assim que uma S1 lombarizada aparece.
    - Um nome que pegou dois corpos (vão > 3 mm no crânio-caudal, cada pedaço com ≥ 25% e ≥ 8 mm) vira
      dois: com vértebra de transição a IA costuma pôr o mesmo nome em duas."""
    por_nome: dict[str, list] = {}
    for _tarefa, (lab, classes) in rotulos.items():
        for cid, classe in classes.items():
            nome = nome_da_vertebra(classe)
            if nome is None:
                continue
            idx = np.argwhere(lab == int(cid))
            if not len(idx):
                continue
            idx = idx[~disco[idx[:, 0], idx[:, 1], idx[:, 2]]]
            if len(idx):
                por_nome.setdefault((nome, classe), []).append(idx)
    juntos = {k: np.concatenate(v) for k, v in por_nome.items()}
    s1 = juntos.pop(("S1", "vertebrae_S1"), None)
    sac = juntos.pop(("S1", "sacrum"), None)
    corpos: list[_Corpo] = []
    if s1 is not None and sac is not None:
        if _perto(s1, sac, 1):
            corpos.append(_Corpo("S1", np.concatenate([s1, sac]), True, np.zeros(3)))
        else:
            corpos.append(_Corpo("S1", s1, False, np.zeros(3)))
            corpos.append(_Corpo("S1", sac, True, np.zeros(3)))
    elif s1 is not None or sac is not None:
        corpos.append(_Corpo("S1", s1 if s1 is not None else sac, True, np.zeros(3)))
    for (nome, _classe), idx in juntos.items():
        corpos.append(_Corpo(nome, idx, False, np.zeros(3)))
    # dois corpos num nome
    sep = []
    for c in corpos:
        if c.sacro or len(c.idx) < 20:
            sep.append(c)
            continue
        z = _mm(vol, c.idx)[:, 2]
        gs = [g for g in _grupos(z, VAO_CORPOS_MM)
              if len(g) >= 0.25 * len(c.idx) and float(np.ptp(z[g])) >= 8.0]
        if len(gs) >= 2:
            for g in gs:
                sep.append(_Corpo(c.modelo, c.idx[g], False, np.zeros(3)))
        else:
            sep.append(c)
    for c in sep:
        c.centro = _mm(vol, c.idx).mean(axis=0)
    sep.sort(key=lambda c: -float(c.centro[2]))          # LPS: +z é para cima
    # o sacro fica embaixo de tudo, mesmo que o centro dele (que é grande e inclinado) suba
    sep.sort(key=lambda c: c.sacro)
    return sep


def _cadeia_continua(corpos: list[_Corpo], de: int) -> bool:
    """Da vértebra `de` até o fim, não falta vértebra: nenhum vão entre centros vizinhos maior que
    1,7× o maior dos dois vãos ao lado (o espaçamento cresce da cervical para a lombar)."""
    c = [k.centro for k in corpos[de:] if not k.sacro]      # o centro do sacro fica longe: não conta
    if len(c) < 2:
        return True
    d = [float(np.linalg.norm(b - a)) for a, b in zip(c, c[1:])]
    for i, g in enumerate(d):
        viz = [d[j] for j in (i - 1, i + 1) if 0 <= j < len(d)]
        if viz and g > 1.7 * max(viz) and g > 25.0:
            return False
    return True


def _nomes_a_partir(corpos: list[_Corpo], i_ancora: int, nome_ancora: str) -> bool:
    base = POS[nome_ancora] - i_ancora
    if base < 0 or base + len(corpos) - 1 >= len(ORDEM):
        return False
    for i, c in enumerate(corpos):
        c.nome = ORDEM[base + i]
    return True


def _nomes_do_modelo(corpos: list[_Corpo]) -> None:
    """Sem âncora: o deslocamento que a maioria dos nomes da IA concorda, aplicado em sequência —
    nunca dois corpos com o mesmo nome (era o caso das duas S1)."""
    from collections import Counter
    votos = Counter(POS[c.modelo] - i for i, c in enumerate(corpos) if c.modelo in POS)
    base = votos.most_common(1)[0][0] if votos else 0
    base = min(max(base, 0), len(ORDEM) - len(corpos)) if len(corpos) <= len(ORDEM) else 0
    for i, c in enumerate(corpos):
        c.nome = ORDEM[min(base + i, len(ORDEM) - 1)]


def _costelas(vol, rotulos: dict, corpos: list[_Corpo]) -> dict:
    """Qual corpo leva cada costela (TC: `rib_left_N`/`rib_right_N` do `total`). A cabeça da costela é a
    parte dela mais perto de um centro de vértebra; a costela é daquele corpo."""
    if not corpos:
        return {}
    centros = np.array([c.centro for c in corpos])
    livres = [i for i, c in enumerate(corpos) if not c.sacro]
    por_lado: dict[str, set] = {"right": set(), "left": set()}
    for _tarefa, (lab, classes) in rotulos.items():
        for cid, classe in classes.items():
            m = re.fullmatch(r"rib_(left|right)_(\d+)", classe or "")
            if not m:
                continue
            idx = np.argwhere(lab == int(cid))
            if len(idx) < 10:
                continue
            if len(idx) > 4000:
                idx = idx[:: len(idx) // 4000 + 1]
            p = _mm(vol, idx)
            d = np.linalg.norm(p[:, None, :] - centros[None, livres, :], axis=2)
            perto = d.min(axis=1)
            cabeca = p[perto <= perto.min() + 5.0].mean(axis=0)
            dc = np.linalg.norm(centros[livres] - cabeca, axis=1)
            if float(dc.min()) > 60.0:
                continue                                   # costela solta, longe da coluna
            por_lado[m.group(1)].add(livres[int(np.argmin(dc))])
    todos = por_lado["right"] | por_lado["left"]
    if not todos:
        return {}
    return {"corpos": sorted(todos), "ultima": max(todos),
            "ultima_dir": max(por_lado["right"]) if por_lado["right"] else None,
            "ultima_esq": max(por_lado["left"]) if por_lado["left"] else None}


def _castellvi(vol, livre: _Corpo, sacro: _Corpo) -> tuple[str, str, str]:
    """Sugestão de Castellvi na última vértebra livre: (grau, lado, motivo). Grau "" = sem achado;
    None no motivo quando não dá para avaliar. II e III só se separam olhando a imagem (pseudoartrose ×
    fusão): a sugestão diz "II", e ele troca para III na janela se for fusão."""
    m = vol.matrix()
    # alcance da série no direita-esquerda (x do paciente)
    nz, ny, nx = vol.data.shape
    cantos = np.array([[i, j, k] for i in (0, nx - 1) for j in (0, ny - 1) for k in (0, nz - 1)], float)
    xs = (vol.origin + cantos @ m.T)[:, 0]
    x0 = float(np.median(_mm(vol, livre.idx)[:, 0]))      # mediana: a apófise de um lado não puxa
    if float(xs.min()) > x0 - ALCANCE_MM or float(xs.max()) < x0 + ALCANCE_MM:
        return "", "", (f"Castellvi não avaliável: a série não pega ±{ALCANCE_MM:.0f} mm da linha média "
                        "(as apófises transversas ficam de fora) — veja na coronal ou na TC")
    p = _mm(vol, livre.idx)
    r = max(1, int(np.ceil(CONTATO_MM / max(min(vol.dx, vol.dy, abs(float(np.linalg.norm(m[:, 2])))), 0.3))))
    lados = {}
    ps = _mm(vol, sacro.idx)
    for lado, sinal in (("direita", -1.0), ("esquerda", 1.0)):          # LPS: x cresce para a esquerda
        sel = sinal * (p[:, 0] - x0) >= APOFISE_LATERAL_MM
        if int(sel.sum()) < 5:
            lados[lado] = None
            continue
        alta = float(np.ptp(p[sel, 2])) >= APOFISE_ALTA_MM
        sel_s = sinal * (ps[:, 0] - x0) >= APOFISE_LATERAL_MM - 10.0
        contato = _perto(livre.idx[sel], sacro.idx[sel_s], r)
        lados[lado] = "contato" if contato else ("alta" if alta else "")
    if all(v is None for v in lados.values()):
        return "", "", "Castellvi não avaliável: a IA não marcou as apófises transversas desta vértebra"
    contato = [k for k, v in lados.items() if v == "contato"]
    alta = [k for k, v in lados.items() if v == "alta"]
    if contato:
        grau = "IIb" if len(contato) == 2 else "IIa"
        lado = "" if len(contato) == 2 else f"à {contato[0]}"
        motivo = ("apófise transversa encostada na asa sacral " + ("dos dois lados" if len(contato) == 2
                                                                   else lado)
                  + " (II = pseudoarticulação; se for fusão óssea, é III)")
        return grau, lado, motivo
    if alta:
        grau = "Ib" if len(alta) == 2 else "Ia"
        lado = "" if len(alta) == 2 else f"à {alta[0]}"
        return grau, lado, (f"apófise transversa com {APOFISE_ALTA_MM:.0f} mm ou mais de altura "
                            + ("dos dois lados" if len(alta) == 2 else lado))
    falta = [k for k, v in lados.items() if v is None]
    return "", "", ("apófises sem sinal de transição" + (f" (a da {falta[0]} não foi marcada)" if falta else ""))


def nomear(vol, rotulos: dict, ancora_externa: dict | None = None) -> Niveis:
    """`rotulos`: {tarefa: (uint8 (k,j,i), {id: classe})} — vértebras, discos e (TC) costelas.

    0.99.23: o nome sai da **sequência física** dos corpos, contada de uma âncora — C2 na série, a
    última costela (T12), ou `ancora_externa` ({índice do corpo: nome}, de outra série do exame) —, e
    só sem âncora dos nomes da IA. O sacro recebe o nome do segmento de cima: S1 normalmente, S2 com
    S1 lombarizada, L5 com L5 fundida a ele.

    Guarda só os voxels de cada vértebra (índices), não um volume inteiro por vértebra: numa TC da
    coluna toda (400 × 512 × 512) eram ~25 máscaras de 100 MB."""
    shape = vol.data.shape
    disco = np.zeros(shape, bool)
    for _tarefa, (lab, classes) in rotulos.items():
        if lab.shape != shape:
            raise ValueError(f"grade {lab.shape} diferente do volume {shape}")
        for cid, classe in classes.items():
            if classe == "intervertebral_discs":
                disco |= lab == int(cid)
    corpos = _corpos(vol, rotulos, disco)
    num = Numeracao()
    out = Niveis(numeracao=num)
    if not corpos:
        return out
    cost = _costelas(vol, rotulos, corpos)
    i_c2 = next((i for i, c in enumerate(corpos) if c.modelo == "C2"), None)
    if i_c2 is None:
        i_c1 = next((i for i, c in enumerate(corpos) if c.modelo == "C1"), None)
        i_c2 = i_c1 + 1 if i_c1 is not None and i_c1 + 1 < len(corpos) else None
    feito = False
    if i_c2 is not None and _cadeia_continua(corpos, i_c2) and _nomes_a_partir(corpos, i_c2, "C2"):
        num.ancora, feito = ("c2_costela" if cost else "c2"), True
    elif i_c2 is not None:
        num.evidencias.append("há C2 na série, mas falta vértebra no caminho até o sacro: não contei a partir dela")
    if not feito and cost and _cadeia_continua(corpos, 0) and _nomes_a_partir(corpos, cost["ultima"], "T12"):
        num.ancora, feito = "costela", True
        num.evidencias.append("T12 = a vértebra da costela mais baixa (supõe 12 pares)")
    if not feito and ancora_externa:
        ok = False
        for i, nome in sorted(ancora_externa.items()):
            if 0 <= int(i) < len(corpos) and nome in POS and _nomes_a_partir(corpos, int(i), nome):
                ok = True
                break
        if ok:
            num.ancora, feito = "outra_serie", True
    if not feito:
        _nomes_do_modelo(corpos)
        num.ancora = "modelo"
    # ---- costelas: a última e a contagem
    if cost:
        num.ultima_costela = corpos[cost["ultima"]].nome
        if cost["ultima_dir"] is not None and cost["ultima_esq"] is not None and \
                cost["ultima_dir"] != cost["ultima_esq"]:
            lado = "direita" if cost["ultima_dir"] > cost["ultima_esq"] else "esquerda"
            num.evidencias.append(f"a costela mais baixa só existe à {lado} ({num.ultima_costela})")
        prim = min(cost["corpos"])
        if prim > 0 and not corpos[prim - 1].sacro:
            num.costelas_pares = cost["ultima"] - prim + 1
    # ---- itens
    mat = vol.matrix()
    ml_voxel = abs(float(np.linalg.det(mat))) / 1000.0
    for c in corpos:
        masc, off = _mascara_de(c.idx)
        out.itens.append(Nivel(c.nome, "vertebra", masc, off, int(len(c.idx)), COR_VERTEBRA, sacro=c.sacro,
                               centro=c.centro))
    # ---- discos: cada voxel vai para o par de corpos vizinhos mais próximo
    volumes_disco: dict[int, float] = {}
    if len(corpos) >= 2 and disco.any():
        centros_mm = np.array([c.centro for c in corpos])
        idx = np.argwhere(disco)                                                          # (k, j, i)
        del disco
        a = np.empty(len(idx), np.int32)
        b = np.empty(len(idx), np.int32)
        for c0 in range(0, len(idx), 200_000):                                            # em blocos: memória
            pts = _mm(vol, idx[c0:c0 + 200_000])
            d = np.linalg.norm(pts[:, None, :] - centros_mm[None, :, :], axis=2)
            dois = np.argsort(d, axis=1)[:, :2]
            a[c0:c0 + 200_000] = dois.min(axis=1)
            b[c0:c0 + 200_000] = dois.max(axis=1)
        for ia in range(len(corpos) - 1):
            sel = (a == ia) & (b == ia + 1)
            n = int(sel.sum())
            if not n or n * ml_voxel < MIN_ML_DISCO:
                continue
            masc, off = _mascara_de(idx[sel])
            volumes_disco[ia] = n * ml_voxel
            out.itens.append(Nivel(f"{corpos[ia].nome}-{corpos[ia + 1].nome}", "disco", masc, off, n, COR_DISCO))
    # ---- transição lombossacral: disco rudimentar e Castellvi na última vértebra livre
    i_sac = next((i for i, c in enumerate(corpos) if c.sacro), None)
    if i_sac is not None and i_sac > 0 and not corpos[i_sac - 1].sacro:
        ia = i_sac - 1
        acima = [volumes_disco[j] for j in (ia - 1, ia - 2) if j in volumes_disco]
        if ia in volumes_disco and acima and volumes_disco[ia] < RUDIMENTAR * float(np.median(acima)):
            num.evidencias.append(f"disco {corpos[ia].nome}-{corpos[i_sac].nome} rudimentar "
                                  f"({volumes_disco[ia]:.1f} mL; os de cima, {float(np.median(acima)):.1f} mL)")
        try:
            g, lado, motivo = _castellvi(vol, corpos[ia], corpos[i_sac])
        except Exception:  # noqa: BLE001
            log.exception("Castellvi")
            g, lado, motivo = "", "", ""
        num.castellvi, num.castellvi_lado, num.castellvi_motivo = g, lado, motivo
        num.castellvi_fonte = "sugestão" if g else ""
    derivar(out.itens, num)
    rotular(out.itens, num)
    out.itens.sort(key=lambda n: (_ordem_do_item(n), n.tipo == "disco"))
    out.avisos = avisos_da_numeracao(out.itens, num)
    return out


def _ordem_do_item(n) -> int:
    return POS.get(str(n.nome).split("-")[0], 99)


def _vertebras(itens) -> list:
    """As vértebras (Nivel ou MaskVolume), de cima para baixo, com o sacro no fim."""
    vs = [n for n in itens if _tipo(n) == "vertebra"]
    return sorted(vs, key=lambda n: (bool(getattr(n, "sacro", False)), POS.get(nivel_de(n), 99)))


def _tipo(n) -> str:
    t = getattr(n, "tipo", None)
    if t:
        return t
    return "disco" if "-" in nivel_de(n) else "vertebra"


def nivel_de(n) -> str:
    """O nível (o que renumera e dá nome ao disco), seja de um `Nivel` ou de um `MaskVolume`."""
    v = getattr(n, "nivel", None) or getattr(n, "nome", None)
    if v:
        return str(v)
    return str(getattr(n, "label", "") or "").split(" ")[0]


def derivar(itens, num: Numeracao) -> None:
    """Transições que os **nomes** já dizem: a última vértebra livre é S1 → lombarizada; é L4 e o sacro
    é L5 → L5 fundida ao sacro; é L5 com indício (disco rudimentar, Castellvi) → possível. E a última
    costela fora da T12 → transição toracolombar."""
    vs = _vertebras(itens)
    sacro = next((v for v in vs if getattr(v, "sacro", False)), None)
    livres = [v for v in vs if not getattr(v, "sacro", False)]
    num.lombossacral = ""
    if sacro is not None and livres:
        ultima = nivel_de(livres[-1])
        if ultima == "S1":
            num.lombossacral = "lombarizada"
        elif ultima == "L4" and nivel_de(sacro) == "L5":
            num.lombossacral = "fundida"
        elif ultima == "L5" and (num.castellvi or any("rudimentar" in e for e in num.evidencias)):
            num.lombossacral = "possivel"
    num.toracolombar = ""
    if num.ultima_costela == "L1":
        num.toracolombar = "costela_l1"
    elif num.ultima_costela == "T11":
        num.toracolombar = "t12_sem_costela"


def rotular(itens, num: Numeracao) -> None:
    """O texto na tela de cada vértebra (o nível continua o mesmo)."""
    vs = _vertebras(itens)
    sacro = next((v for v in vs if getattr(v, "sacro", False)), None)
    livres = [v for v in vs if not getattr(v, "sacro", False)]
    tipo = num.tipo_lombossacral
    for v in vs:
        _por_rotulo(v, nivel_de(v))
    if sacro is not None:
        n = nivel_de(sacro)
        _por_rotulo(sacro, "S1" if n == "S1" else ("Sacro (L5 sacralizada)" if n == "L5" else f"Sacro ({n})"))
    if livres and sacro is not None:
        u = livres[-1]
        txt = {"lombarizada": "lombarizada", "sacralizada": "sacralizada", "possivel": "transição?"}.get(tipo)
        if txt and not (tipo == "lombarizada" and nivel_de(u) != "S1"):
            _por_rotulo(u, f"{nivel_de(u)} {txt}")
    tl = {"costela_l1": ("L1", "L1 com costela"), "t12_sem_costela": ("T12", "T12 sem costela")}.get(num.toracolombar)
    if tl:
        for v in livres:
            if nivel_de(v) == tl[0]:
                _por_rotulo(v, tl[1])


def _por_rotulo(n, texto: str) -> None:
    if hasattr(n, "rotulo") and not hasattr(n, "fatia"):
        n.rotulo = texto if texto != n.nome else ""
    else:
        if getattr(n, "label", None) != texto:
            n.label = texto
            if hasattr(n, "_cache"):
                n._cache.clear()


def avisos_da_numeracao(itens, num: Numeracao) -> list[str]:
    out = []
    nomes = [nivel_de(v) for v in _vertebras(itens)]
    tipo = num.tipo_lombossacral
    tem_sacro = any(getattr(v, "sacro", False) for v in _vertebras(itens))
    if num.ancora == "modelo" and not tem_sacro and not set(nomes) & {"C1", "C2"}:
        out.append("a série não pega C2, a última costela nem o sacro: a contagem não tem onde se "
                   "ancorar — confira (botão direito ▸ Ajustar a numeração)")
    elif num.ancora == "modelo" and tipo:
        out.append("sem C2 nem a última costela na série, a transição abaixo é só pela IA")
    if tipo and tipo != "possivel":
        out.append(LOMBOSSACRAL[tipo] + (" — confira" if num.ancora == "modelo" else ""))
    elif tipo == "possivel":
        out.append("L5 com sinais de transição (" + "; ".join(
            [e for e in num.evidencias if "rudimentar" in e]
            + ([f"Castellvi {num.castellvi} sugerido"] if num.castellvi else [])) + ") — confira")
    if num.toracolombar:
        out.append(TORACOLOMBAR[num.toracolombar])
    if num.aviso_anterior:
        out.append(num.aviso_anterior)
    if num.costelas_pares and num.costelas_pares != 12:
        out.append(f"{num.costelas_pares} pares de costelas")
    posicoes = sorted(POS[n] for n in nomes if n in POS)
    if len(set(posicoes)) != len(posicoes):
        out.append("dois corpos com o mesmo nome — confira a numeração")
    return out


def avisos(vertebras: list[str]) -> list[str]:
    """Contagem que pede conferência: lombar ≠ 5 quando a série pega de T12 ao sacro; buraco no meio."""
    out = []
    tem = set(vertebras)
    lombares = [n for n in vertebras if n.startswith("L")]
    if "T12" in tem and "S1" in tem and len(lombares) != 5:
        out.append(f"{len(lombares)} vértebras lombares entre T12 e o sacro — confira (vértebra de transição?)")
    posicoes = sorted(POS[n] for n in tem if n in POS)
    faltam = [ORDEM[i] for i in range(posicoes[0], posicoes[-1]) if i not in posicoes] if posicoes else []
    if faltam:
        out.append("faltou " + ", ".join(faltam) + " no meio da coluna — confira a numeração")
    if tem and not tem & {"C1", "C2", "S1"}:
        out.append("a série não pega C1/C2 nem o sacro: a contagem não tem onde se ancorar — confira")
    return out


def resumo(niveis: Niveis) -> str:
    vert, discos = niveis.nomes("vertebra"), niveis.nomes("disco")
    txt = f"{vert[0]} a {vert[-1]}" if vert else "nenhuma vértebra"
    txt += f", {len(discos)} discos ({discos[0]} a {discos[-1]})" if discos else ", nenhum disco"
    if niveis.avisos:
        txt += " — confira: " + "; ".join(niveis.avisos)
    return txt


def frase_do_laudo(num: Numeracao) -> str:
    """O parágrafo para o laudo."""
    partes = []
    tipo = num.tipo_lombossacral
    if tipo in ("lombarizada", "sacralizada", "fundida"):
        txt = "Vértebra de transição lombossacral: " + LOMBOSSACRAL[tipo]
    elif tipo == "possivel":
        txt = "Possível vértebra de transição lombossacral (L5)"
    else:
        txt = ""
    if txt and num.castellvi:
        txt += f", Castellvi {num.castellvi}" + (f" {num.castellvi_lado}" if num.castellvi_lado else "")
    if txt:
        partes.append(txt + ".")
    if num.toracolombar:
        partes.append(TORACOLOMBAR[num.toracolombar][0].upper() + TORACOLOMBAR[num.toracolombar][1:] + ".")
    if num.costelas_pares and num.costelas_pares != 12:
        partes.append(f"{num.costelas_pares} pares de costelas.")
    anc = ANCORAS.get(num.ancora, "")
    if anc:
        partes.append(f"Numeração vertebral {anc}.")
    return " ".join(partes)


# ------------------------------------------------------------------ outra série do exame como âncora
def tarefas_ancora(modalidade: str, settings=None) -> list[dict]:
    """Na série âncora só as vértebras: os discos dela não entram em nada."""
    if (modalidade or "").upper() == "MR":
        return [{"nome": "vertebrae_mr", "rotulo": "vértebras (contagem a partir de C2)"}]
    return [{"nome": "total", "roi": [f"vertebrae_{n}" for n in ORDEM if n != "S2"] + ["sacrum"], "fast": True,
             "rotulo": "vértebras (contagem a partir de C2)"}]


def com_ancora(vol, rotulos: dict, niveis: Niveis, ancora: Niveis, desc_ancora: str = "") -> Niveis:
    """Refaz a numeração da principal pela âncora (outra série contada de C2). Sem par, devolve a
    principal com o motivo nas evidências."""
    mapa = ancora_de_outra(niveis, ancora)
    if not mapa:
        motivo = ("a série âncora não chegou a contar a partir de C2" if ancora.numeracao.ancora not in
                  ("c2", "c2_costela") else "nenhuma vértebra da série bate com a da série âncora")
        niveis.numeracao.evidencias.append(f"tentei contar pela C2 em {desc_ancora or 'outra série'}, mas {motivo}")
        return niveis
    novo = nomear(vol, rotulos, ancora_externa=mapa)
    if novo.numeracao.ancora == "outra_serie":
        novo.numeracao.evidencias.insert(0, f"contada a partir de C2 na série “{desc_ancora}”" if desc_ancora
                                         else "contada a partir de C2 em outra série")
    return novo


def corpos_em_mm(niveis: Niveis) -> list[tuple[str, np.ndarray]]:
    """(nível, centro em mm) das vértebras livres, de cima para baixo."""
    return [(n.nome, np.asarray(n.centro, float)) for n in _vertebras(niveis.itens)
            if n.centro is not None and not n.sacro]


def ancora_de_outra(principal: Niveis, ancora: Niveis, raio_mm: float = 15.0) -> dict | None:
    """Os corpos da série principal que batem (centros a até `raio_mm`) com um corpo da série âncora,
    contada a partir de C2. Devolve {índice do corpo na principal: nome}, para `nomear` refazer, ou
    None se a âncora não conta de C2 ou se nada bate. Precisa do mesmo Frame of Reference."""
    if ancora.numeracao.ancora not in ("c2", "c2_costela"):
        return None
    alvo = corpos_em_mm(ancora)
    vs = _vertebras(principal.itens)
    pares = {}
    for i, v in enumerate(vs):
        if v.centro is None or v.sacro:
            continue
        d = [(float(np.linalg.norm(np.asarray(v.centro) - c)), nome) for nome, c in alvo]
        if d and min(d)[0] <= raio_mm:
            pares[i] = min(d)[1]
    if not pares:
        return None
    # fica o deslocamento em que a maioria concorda (um par errado não vira a numeração)
    from collections import Counter
    votos = Counter(POS[n] - i for i, n in pares.items())
    base = votos.most_common(1)[0][0]
    return {i: n for i, n in pares.items() if POS[n] - i == base}


def serie_ancora(repo, study_uid: str, primeira: str, settings=None) -> str | None:
    try:
        return _serie_ancora(repo, study_uid, primeira, settings)
    except Exception:  # noqa: BLE001
        log.exception("procurar a série com a C2")
        return None


def _serie_ancora(repo, study_uid: str, primeira: str, settings=None) -> str | None:
    """Outra série do exame que pegue da C2 à região da principal (coluna inteira, composta): extensão
    crânio-caudal ≥ 450 mm, mesmo Frame of Reference, cobrindo a principal."""
    from ipe.ai import totalseg as TS
    meta1 = repo.series_meta(primeira) or {}
    for_ = meta1.get("frame_of_reference", "")
    faixa1 = _faixa_z(repo, primeira)
    if faixa1 is None:
        return None
    cands = []
    for s in repo.series_for_study(study_uid):
        if s.series_uid == primeira or (s.modality or "").upper() != (meta1.get("modality") or "").upper():
            continue
        desc = TS._sem_acento(s.description or "")
        if "TOTALSEGMENTATOR" in desc or any(x in desc for x in TS._NUNCA):
            continue
        if for_ and ((repo.series_meta(s.series_uid) or {}).get("frame_of_reference") or "") != for_:
            continue
        f = _faixa_z(repo, s.series_uid)
        if f is None or f[1] - f[0] < 450.0:
            continue
        if f[0] > faixa1[0] + 20 or f[1] < faixa1[1] - 20:
            continue                            # não cobre a principal
        cands.append((-(f[1] - f[0]), s.series_uid))
    return min(cands)[1] if cands else None


def _faixa_z(repo, series_uid: str) -> tuple[float, float] | None:
    """(z mínimo, z máximo) em mm que a série cobre, pela posição e pela orientação das imagens."""
    inst = repo.instances_for_series(series_uid)
    if not inst:
        return None
    zs = []
    for it in (inst[0], inst[len(inst) // 2], inst[-1]):
        pos, ori = _numeros(it.get("position")), _numeros(it.get("orientation"))
        if len(pos) < 3:
            continue
        zs.append(pos[2])
        if len(ori) >= 6:
            try:
                import pydicom
                ds = pydicom.dcmread(it["path"], stop_before_pixels=True)
                dy, dx = (float(v) for v in ds.PixelSpacing)
                zs.append(pos[2] + ori[2] * dx * (int(ds.Columns) - 1) + ori[5] * dy * (int(ds.Rows) - 1))
            except Exception:  # noqa: BLE001
                pass
    if not zs:
        return None
    return float(min(zs)), float(max(zs))


# ------------------------------------------------------------------ na tela
def _cortada(forma_total, offset, forma, matriz) -> bool:
    """O nível encosta na borda da série no sentido crânio-caudal (a série cortou a vértebra no meio)?
    `forma_total`/`offset`/`forma` em (k, j, i); `matriz`: colunas = passo em i, j, k (mm)."""
    m = np.asarray(matriz, float)
    for eixo_kji, col in ((0, 2), (1, 1), (2, 0)):
        d = m[:, col]
        if np.linalg.norm(d) < 1e-9 or abs(d[2]) / np.linalg.norm(d) < 0.7:
            continue                                  # este eixo da grade não é o crânio-caudal
        a, b = int(offset[eixo_kji]), int(offset[eixo_kji]) + int(forma[eixo_kji])
        if a <= 0 or b >= int(forma_total[eixo_kji]):
            return True
    return False


def objeto(vol, niveis: Niveis, study_uid: str = "", chave: str = "coluna"):
    """O objeto de sobreposição: um volume por nível, **só o rótulo** (sem pintar a máscara)."""
    from ipe.imaging import overlays as O
    obj = O.OverlayObject(chave, "Coluna", "Níveis da coluna", COR_DISCO, True, study_uid)
    for n in niveis.itens:
        mv = O.MaskVolume.do_volume(vol, n.mascara, n.offset, n.cor, n.rotulo or n.nome)
        mv.so_rotulo = True
        mv.nivel, mv.sacro = n.nome, n.sacro
        mv.cortada = _cortada(vol.data.shape, n.offset, n.mascara.shape, mv.matriz)
        obj.volumes.append(mv)
    obj.numeracao = niveis.numeracao
    atualizar_lista(obj)
    return obj


def atualizar_lista(obj) -> None:
    """A lista do objeto: os níveis, a linha da numeração e os avisos."""
    num = getattr(obj, "numeracao", None) or Numeracao()
    medidas = [f for f in (obj.findings or []) if str(f).startswith("📏")]
    obj.findings = [mv.label for mv in obj.volumes]
    anc = ANCORAS.get(num.ancora, "")
    if anc:
        obj.findings.append(f"Numeração: {anc}")
    obj.findings += [f"⚠ {a}" for a in avisos_da_numeracao(obj.volumes, num)]
    obj.findings += medidas


def renumerar(obj, passo: int) -> None:
    """Todos os níveis andam `passo` (vértebra de transição, contagem errada). Recusa
    (`ForaDaColuna`) antes de mexer em qualquer coisa se algum nível sairia da coluna."""
    novos = [deslocar(nivel_de(mv), passo) for mv in obj.volumes]
    num = getattr(obj, "numeracao", None)
    if num is None:
        num = obj.numeracao = Numeracao()
    costela = deslocar(num.ultima_costela, passo) if num.ultima_costela else ""
    for mv, n in zip(obj.volumes, novos):
        mv.nivel = n
        mv.label = n
        mv._cache.clear()
    num.ultima_costela = costela
    num.ancora = "medico"
    num.lombossacral_medico = ""
    derivar(obj.volumes, num)
    rotular(obj.volumes, num)
    atualizar_lista(obj)
    anexar_medidas(obj)
    obj.version += 1


def ultima_livre(obj) -> str:
    vs = [v for v in _vertebras(obj.volumes) if not getattr(v, "sacro", False)]
    return nivel_de(vs[-1]) if vs else ""


def tem_sacro(obj) -> bool:
    return any(getattr(v, "sacro", False) for v in obj.volumes)


def passo_para(obj, tipo: str) -> int:
    """Quanto renumerar para que a última vértebra livre fique como `tipo` pede: lombarizada → S1;
    sacralizada (parcial) ou nenhuma → L5; fundida → L4 (o sacro vira L5)."""
    u = ultima_livre(obj)
    alvo = {"lombarizada": "S1", "fundida": "L4"}.get(tipo, "L5")
    if u not in POS:
        return 0
    return POS[alvo] - POS[u]


def ajustar(obj, *, passo: int = 0, lombossacral: str | None = None, castellvi: str | None = None,
            castellvi_lado: str = "", quem: str = "") -> None:
    """O que ele decide na janela Ajustar a numeração. `lombossacral`: "" (nenhuma), "sacralizada",
    "lombarizada", "fundida" — renumera para ficar coerente e guarda a escolha."""
    from datetime import datetime
    if lombossacral is not None and tem_sacro(obj):
        passo = passo_para(obj, lombossacral) if not passo else passo
    if passo:
        renumerar(obj, passo)
    num = obj.numeracao
    if lombossacral is not None:
        num.lombossacral_medico = lombossacral or "nenhuma"
        derivar(obj.volumes, num)
    if castellvi is not None:
        num.castellvi = castellvi
        num.castellvi_lado = castellvi_lado if castellvi.endswith("a") else ""
        num.castellvi_fonte = "médico" if castellvi else ""
    num.confirmado_por = quem
    num.aviso_anterior = ""                       # ele acabou de conferir
    num.confirmado_em = datetime.now().strftime("%d/%m/%Y %H:%M")
    if num.ancora == "":
        num.ancora = "medico"
    rotular(obj.volumes, num)
    atualizar_lista(obj)
    obj.version += 1


# ------------------------------------------------------------------ memória por paciente (0.99.23)
MODULO_REVISAO = "coluna"


def _resumo_para_comparar(num: Numeracao) -> tuple[str, str]:
    return num.tipo_lombossacral if num.tipo_lombossacral != "possivel" else "", num.toracolombar


def descrever(num: Numeracao) -> str:
    """'S1 lombarizada, Castellvi IIa à direita' — ou 'sem vértebra de transição'."""
    tipo = num.tipo_lombossacral
    partes = []
    if tipo and tipo != "possivel":
        partes.append({"lombarizada": "S1 lombarizada", "sacralizada": "L5 sacralizada",
                       "fundida": "L5 sacralizada fundida ao sacro"}[tipo])
    if num.castellvi:
        partes.append(f"Castellvi {num.castellvi}" + (f" {num.castellvi_lado}" if num.castellvi_lado else ""))
    if num.toracolombar:
        partes.append(TORACOLOMBAR[num.toracolombar])
    return ", ".join(partes) or "sem vértebra de transição"


def guardar_conferencia(repo, study_uid: str, num: Numeracao, quem: str = "") -> None:
    """A numeração que ele confirmou neste exame (Ajustar a numeração ▸ Aplicar)."""
    import json
    if repo is None or not study_uid:
        return
    try:
        repo.salvar_revisao_ia(study_uid, MODULO_REVISAO, "aceito", True, quem,
                               json.dumps(num.para_dict(), ensure_ascii=False))
    except Exception:  # noqa: BLE001
        log.exception("guardar a numeração da coluna")


def anterior_confirmada(repo, study_uid: str) -> dict | None:
    """A numeração confirmada no exame anterior mais recente do paciente: {data, numeracao, descricao}."""
    import json
    if repo is None or not study_uid:
        return None
    try:
        lista = repo.revisoes_ia_do_paciente(study_uid, MODULO_REVISAO)
    except Exception:  # noqa: BLE001
        log.exception("numeração confirmada nos exames anteriores")
        return None
    for r in lista:
        try:
            num = Numeracao.de_dict(json.loads(r["dados"] or "{}"))
        except Exception:  # noqa: BLE001
            continue
        return {"data": r["data"], "numeracao": num, "descricao": r.get("descricao", ""),
                "usuario": r.get("usuario", "")}
    return None


def _data_br(d: str) -> str:
    d = str(d or "")
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 and d.isdigit() else d


def conferir_anteriores(repo, study_uid: str, niveis: Niveis) -> None:
    """Põe o aviso das anteriores na numeração e nos avisos (depois de `nomear`, antes de gravar)."""
    txt = aviso_das_anteriores(repo, study_uid, niveis.numeracao)
    if txt:
        niveis.numeracao.aviso_anterior = txt
        niveis.avisos = avisos_da_numeracao(niveis.itens, niveis.numeracao)


def aviso_das_anteriores(repo, study_uid: str, num: Numeracao) -> str:
    """Aviso quando a numeração deste exame não bate com a que ele confirmou num exame anterior do
    mesmo paciente: cirurgia no nível errado nasce de dois exames numerados de jeitos diferentes."""
    ant = anterior_confirmada(repo, study_uid)
    if ant is None:
        return ""
    if _resumo_para_comparar(ant["numeracao"]) == _resumo_para_comparar(num):
        return ""
    return (f"no exame de {_data_br(ant['data'])} a numeração confirmada foi “{descrever(ant['numeracao'])}”; "
            f"aqui saiu “{descrever(num)}” — confira")


# ------------------------------------------------------------------ no exame
def gravar(trabalho, niveis: Niveis, versao: str, db, storage_root, conferencia: bool = False,
           repo=None) -> dict:
    """SEG "Níveis da coluna · TotalSegmentator" no exame (só local, como as outras do CAD/IA).
    `conferencia`: a da segunda sagital (0.99.5), que só serve para as medidas e não aparece na tela.
    Com `repo`, a anterior da mesma espécie sai: repetir não deixa duas colunas no exame."""
    desc, numero = (DESC_CONF, SERIE_CONF) if conferencia else (MARCA, SERIE)
    if repo is not None:
        from pathlib import Path as _P
        for se in repo.series_for_study(trabalho.study_uid):
            if (se.description or "") == desc:
                try:
                    repo.delete_series(se.series_uid, _P(storage_root))
                except Exception:  # noqa: BLE001
                    log.exception("trocar a SEG da coluna")
    import shutil
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    vol = trabalho.vol
    segs = [(SimpleNamespace(mask=n.mascara, offset=n.offset), n.rotulo or n.nome, n.cor) for n in niveis.itens]
    if not segs:
        from ipe.ai.totalseg import Falhou
        raise Falhou("O TotalSegmentator não achou vértebras nesta série.")
    ds = build_seg(vol, segs, vol.source_path, frames=trabalho.frames, series_number=numero, description=desc,
                   algoritmo=("AUTOMATIC", f"TotalSegmentator {versao}".strip()), anatomia=True)
    _escrever_niveis(ds, [(n.nome, n.sacro) for n in niveis.itens], niveis.numeracao)
    tmp = Path(tempfile.mkdtemp(prefix="dv_coluna_"))
    try:
        ds.save_as(tmp / "coluna.dcm", enforce_file_format=True)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    from ipe.ai.totalseg_saida import _caminho_do_sop
    return {"series": sorted(getattr(r, "new_series", None) or []), "seg_sop": str(ds.SOPInstanceUID),
            "seg_path": _caminho_do_sop(db, trabalho.study_uid, str(ds.SOPInstanceUID))}


def _escrever_niveis(ds, niveis: list[tuple[str, bool]], num: Numeracao | None) -> None:
    """O nível de cada segmento vai na SegmentDescription ("nivel=L5;sacro=1") — o rótulo da tela pode
    ser "S1 lombarizada" —, e a numeração no ImageComments, em JSON."""
    import json
    for s, (nivel, sacro) in zip(ds.SegmentSequence, niveis):
        s.SegmentDescription = f"nivel={nivel};sacro={int(bool(sacro))}"
    if num is not None:
        # ASCII: o conjunto de caracteres do SEG é latin-1, e o motivo tem travessão e "≥"
        ds.ImageComments = "ipe-coluna " + json.dumps(num.para_dict(), ensure_ascii=True)[:10000]


def _ler_niveis(ds) -> tuple[dict, Numeracao | None]:
    import json
    niveis = {}
    for s in ds.SegmentSequence:
        d = str(s.get("SegmentDescription", "") or "")
        m = re.search(r"nivel=([^;]+);sacro=(\d)", d)
        if m:
            niveis[int(s.SegmentNumber)] = (m.group(1), m.group(2) == "1")
    num = None
    txt = str(ds.get("ImageComments", "") or "")
    if txt.startswith("ipe-coluna "):
        try:
            num = Numeracao.de_dict(json.loads(txt[len("ipe-coluna "):]))
        except Exception:  # noqa: BLE001
            log.exception("ler a numeração da coluna no SEG")
    return niveis, num


def salvar_no_seg(caminho: str, obj) -> None:
    """Guarda no próprio SEG o que mudou na tela (renumerar, ajustar): reabrir o exame já vem certo."""
    import pydicom
    ds = pydicom.dcmread(caminho)
    por_num = {getattr(mv, "segmento", None): mv for mv in obj.volumes}
    niveis = []
    for s in ds.SegmentSequence:
        mv = por_num.get(int(s.SegmentNumber))
        if mv is None:
            niveis.append((str(s.SegmentLabel), False))
            continue
        s.SegmentLabel = str(mv.label)[:64]
        niveis.append((nivel_de(mv), bool(getattr(mv, "sacro", False))))
    _escrever_niveis(ds, niveis, getattr(obj, "numeracao", None))
    ds.save_as(caminho, enforce_file_format=True)


def renumerar_seg(caminho: str, passo: int) -> None:
    """Compatível com a 0.99.2: renumera o SEG sem o objeto na mão."""
    obj = objeto_do_seg(caminho)
    renumerar(obj, passo)
    salvar_no_seg(caminho, obj)


def eh_seg_da_coluna(ds_ou_desc) -> bool:
    d = ds_ou_desc if isinstance(ds_ou_desc, str) else str(ds_ou_desc.get("SeriesDescription", "") or "")
    return d == MARCA


def objeto_do_seg(caminho: str, study_uid: str = ""):
    """Relê a SEG da coluna como volumes em mm (aparecem em qualquer série e plano), cada um com o
    nome do nível. A grade sai do próprio SEG: o índice do corte (DimensionIndexValues) e a posição."""
    import pydicom

    from ipe.imaging import overlays as O
    ds = pydicom.dcmread(caminho)
    arr = ds.pixel_array
    if arr.ndim == 2:
        arr = arr[None]
    shared = ds.SharedFunctionalGroupsSequence[0]
    ori = np.array([float(v) for v in shared.PlaneOrientationSequence[0].ImageOrientationPatient])
    dy, dx = (float(v) for v in shared.PixelMeasuresSequence[0].PixelSpacing)
    row, col = ori[:3], ori[3:]
    nomes = {int(s.SegmentNumber): (str(s.SegmentLabel), O.lab_to_rgb(s.RecommendedDisplayCIELabValue)
                                     if "RecommendedDisplayCIELabValue" in s else COR_DISCO)
             for s in ds.SegmentSequence}
    niveis, num = _ler_niveis(ds)
    quadros: dict[int, list] = {}
    pos_k: dict[int, np.ndarray] = {}
    for f, fg in enumerate(ds.PerFrameFunctionalGroupsSequence):
        nseg = int(fg.SegmentIdentificationSequence[0].ReferencedSegmentNumber)
        k = int(fg.FrameContentSequence[0].DimensionIndexValues[1]) - 1
        pos_k[k] = np.array([float(v) for v in fg.PlanePositionSequence[0].ImagePositionPatient])
        quadros.setdefault(nseg, []).append((k, arr[f] > 0))
    ks = sorted(pos_k)
    if len(ks) >= 2:
        passo = (pos_k[ks[-1]] - pos_k[ks[0]]) / (ks[-1] - ks[0])
    else:
        passo = np.cross(row, col) * float(shared.PixelMeasuresSequence[0].get("SpacingBetweenSlices", 1) or 1)
    k_ref = ks[0]
    matriz = np.column_stack([row * dx, col * dy, passo])
    obj = O.OverlayObject(f"coluna:{ds.SOPInstanceUID}", "Coluna", "Níveis da coluna", COR_DISCO, True,
                          study_uid or str(ds.get("StudyInstanceUID", "")))
    ordem = []
    for nseg, lista in quadros.items():
        rot, cor = nomes.get(nseg, (f"Nível {nseg}", COR_DISCO))
        kmin, kmax = min(k for k, _m in lista), max(k for k, _m in lista)
        h, w = lista[0][1].shape
        vol = np.zeros((kmax - kmin + 1, h, w), bool)
        for k, m in lista:
            vol[k - kmin] |= m
        js, is_ = np.flatnonzero(vol.any(axis=(0, 2))), np.flatnonzero(vol.any(axis=(0, 1)))
        if not len(js):
            continue
        j0, i0 = int(js[0]), int(is_[0])
        masc = vol[:, j0:int(js[-1]) + 1, i0:int(is_[-1]) + 1].copy()
        origem = pos_k[ks[0]] + passo * (kmin - k_ref) + row * dx * i0 + col * dy * j0
        mv = O.MaskVolume(masc, origem, matriz, tuple(cor), rot)
        mv.so_rotulo = True
        mv.segmento = nseg
        if nseg in niveis:
            mv.nivel, mv.sacro = niveis[nseg]
        else:                                   # SEG de antes da 0.99.23: o rótulo é o nível
            mv.nivel, mv.sacro = rot.split(" ")[0], False
        mv.cortada = _cortada((ks[-1] - ks[0] + 1, h, w), (kmin - ks[0], j0, i0), masc.shape, matriz)
        ordem.append((POS.get(mv.nivel.split("-")[0], 99), "-" in mv.nivel, mv))
    if not niveis:                               # antes da 0.99.23: o sacro era a "S1" mais de baixo
        vs = [mv for _p, d, mv in ordem if not d]
        if vs:
            baixo = max(vs, key=lambda mv: POS.get(mv.nivel, -1))
            if baixo.nivel == "S1":
                baixo.sacro = True
    for _p, _d, mv in sorted(ordem, key=lambda t: (t[0], t[1])):
        obj.volumes.append(mv)
    obj.numeracao = num or Numeracao(ancora="")
    if num is None:
        derivar(obj.volumes, obj.numeracao)
    rotular(obj.volumes, obj.numeracao)
    atualizar_lista(obj)
    obj.caminho = caminho
    return obj


# ------------------------------------------------------------------ medidas (0.99.3 discos, 0.99.4 vértebras, 0.99.5)
CHAVE_MEDIR = "coluna.medir"                 # altura e volume dos discos e dos corpos, com as tabelas no exame
PADROES[CHAVE_MEDIR] = False
CHAVE_SEQUENCIAS = "coluna.sequencias"       # 0.99.5: na RM, medir em quantas sagitais (1 ou 2)
PADROES[CHAVE_SEQUENCIAS] = 2
DESC_TABELA = "Discos: medidas · TotalSegmentator"   # sem travessão: o conjunto de caracteres da imagem não tem
SERIE_TABELA = 973
DESC_TABELA_VERT = "Vértebras: medidas · TotalSegmentator"
SERIE_TABELA_VERT = 974
DESC_CONF = "Níveis da coluna (conferência) · TotalSegmentator"   # a segunda sagital (0.99.5)
SERIE_CONF = 975
FAIXA_SAGITAL_MM = 4.0                       # metade da faixa central (direita-esquerda) onde se mede
POS_BORDA = 0.10                             # anterior/posterior: a 10% da profundidade, a partir da borda
MAX_PASSO_AP_MM = 3.0                        # série com cortes mais grossos no ântero-posterior (coronal): não mede
DUVIDOSA_DISCO = 1.8
ALTURA_POR_FUNDO = 1.25                      # corpo vertebral mais alto que 1,25× o próprio fundo: não é um corpo
CONCORDA_MM, CONCORDA_REL = 2.0, 0.10        # duas sequências concordam: diferença até 2 mm ou 10%
RAIO_PAR_MM = 12.0                           # mesma vértebra nas duas sequências: centros a até 12 mm
SEM_CORPO = {"C1", "C2", "S1"}               # C1 não tem corpo; C2 tem o dente; S1 é o sacro
GENANT = ((40.0, 3, "acentuada"), (25.0, 2, "moderada"), (20.0, 1, "leve"))
GRADUA = (POS["T4"], POS["L5"])              # Genant foi validado na torácica e lombar (T4–L4); L5 junto
FORMAS = {"cunha": "cunha", "biconcava": "bicôncava", "esmagamento": "esmagamento"}
CAMPOS = ("anterior", "media", "posterior")


def _num(v, casas=1):
    return "—" if v is None else f"{v:.{casas}f}".replace(".", ",")


def _pontos_mm(mv) -> np.ndarray:
    """Centros dos voxels do volume (MaskVolume) em mm, LPS."""
    idx = np.argwhere(mv.mascara)                                    # (k, j, i)
    return mv.origem + idx[:, ::-1].astype(float) @ mv.matriz.T


def _extensao(matriz: np.ndarray, u: np.ndarray) -> float:
    """Quanto um voxel mede na direção u (a "espessura" que um voxel soma à medida)."""
    return float(np.abs(matriz.T @ u).sum())


def passo_ap(mv) -> float:
    """Quanto um voxel da série mede no sentido ântero-posterior (na coronal, a espessura do corte)."""
    return _extensao(mv.matriz, np.array([0.0, 1.0, 0.0]))


def aviso_da_serie(obj) -> str:
    for mv in getattr(obj, "volumes", []) or []:
        p = passo_ap(mv)
        if p > MAX_PASSO_AP_MM:
            return (f"a série tem {_num(p)} mm por voxel no sentido ântero-posterior (coronal?): as alturas "
                    "anterior e posterior precisam da sagital — identifique os níveis na série sagital")
        return ""
    return ""


def _grupos(v: np.ndarray, vao: float) -> list[np.ndarray]:
    """Índices de `v` em grupos contínuos: um vão maior que `vao` (mm) separa um grupo do outro."""
    if not len(v):
        return []
    ordem = np.argsort(v)
    vs = v[ordem]
    cortes = np.flatnonzero(np.diff(vs) > vao) + 1
    return np.split(ordem, cortes)


def _principal(v: np.ndarray, vao: float) -> np.ndarray:
    """Máscara do grupo contínuo com mais pontos (tira pedaço solto que a IA marcou longe do osso)."""
    gs = _grupos(v, vao)
    out = np.zeros(len(v), bool)
    if gs:
        out[max(gs, key=len)] = True
    return out


def _altura(t: np.ndarray, s: np.ndarray, s0: float, largura: float, passo_u: float) -> float | None:
    """Altura na coluna de voxels em s0: do voxel mais de cima ao mais de baixo, mais um voxel. Os
    pedaços soltos já saíram antes (`_principal` no eixo da coluna); um buraco **dentro** do corpo não
    encurta a altura (0.99.5: numa RM real do acervo, L3 tinha um buraco de 15 mm na frente)."""
    j = np.abs(s - s0) <= largura
    if j.sum() < 2:
        return None
    return float(t[j].max() - t[j].min()) + passo_u


def _altura_em(t: np.ndarray, s: np.ndarray, smin: float, smax: float, frac: float, largura: float,
               passo_u: float) -> float | None:
    """Altura em `frac` da profundidade (0 = atrás, 1 = na frente): a mediana de cinco colunas entre
    frac − 5% e frac + 5%. Uma coluna só caía num buraco da segmentação e dava 7–9 mm numa vértebra de
    25 mm (0.99.5)."""
    prof = smax - smin
    vals = [_altura(t, s, smin + f * prof, largura, passo_u) for f in np.linspace(frac - 0.05, frac + 0.05, 5)]
    vals = [v for v in vals if v is not None]
    return float(np.median(vals)) if len(vals) >= 2 else None


@dataclass
class MedidaDisco:
    nome: str
    volume_ml: float
    anterior: float | None = None            # mm
    media: float | None = None               # mm, no meio da profundidade (ântero-posterior)
    posterior: float | None = None           # mm
    profundidade: float | None = None        # mm, ântero-posterior na faixa central
    vs_acima: float | None = None            # % da altura média do disco de cima
    nota: str = ""
    centro: np.ndarray | None = None         # mm (para achar o mesmo disco na outra sequência)
    duvidosa: bool = False
    seq: int = 1                             # em quantas sequências saiu
    concorda: bool = False                   # 0.99.5: as duas sequências deram o mesmo (dentro da tolerância)
    alt: dict = field(default_factory=dict)  # campo → valor da outra sequência, quando discordam


@dataclass
class MedidaVertebra:
    nome: str
    anterior: float | None = None            # mm, altura do corpo a 10% da profundidade, na frente
    media: float | None = None               # mm, no meio
    posterior: float | None = None           # mm, a 10% da profundidade, atrás
    profundidade: float | None = None        # mm, ântero-posterior do corpo na faixa central
    ant_post: float | None = None            # Ha / Hp
    perda: float | None = None               # %, a maior das três (cunha, bicôncava, esmagamento)
    forma: str = ""                          # "cunha" | "biconcava" | "esmagamento"
    grau: int = 0                            # Genant 0–3 (pela perda de altura)
    nota: str = ""
    centro: np.ndarray | None = None
    duvidosa: bool = False
    seq: int = 1
    concorda: bool = False
    alt: dict = field(default_factory=dict)

    @property
    def grau_txt(self) -> str:
        return next((t for lim, g, t in GENANT if g == self.grau), "")


def _referencial(u: np.ndarray):
    """(u, anterior, lateral) a partir do eixo da coluna; None se o eixo for ântero-posterior."""
    if np.linalg.norm(u) < 1e-6:
        return None
    u = u / np.linalg.norm(u)
    ant = np.array([0.0, -1.0, 0.0])                                 # LPS: anterior é −y
    a = ant - (ant @ u) * u
    if np.linalg.norm(a) < 1e-3:
        return None
    a /= np.linalg.norm(a)
    return u, a, np.cross(u, a)


# ---------------------------------------------------------------- discos, uma sequência
def _discos_crus(obj) -> list[MedidaDisco]:
    vols = {nivel_de(mv): mv for mv in getattr(obj, "volumes", []) or []}
    out: list[MedidaDisco] = []
    for nome, mv in vols.items():
        if "-" not in nome:
            continue
        a_nome, b_nome = nome.split("-", 1)
        pts = _pontos_mm(mv)
        ml = len(pts) * abs(float(np.linalg.det(mv.matriz))) / 1000.0
        m = MedidaDisco(nome, ml, centro=pts.mean(axis=0) if len(pts) else None)
        out.append(m)
        if a_nome not in vols or b_nome not in vols or len(pts) < 20:
            m.nota = "sem as duas vértebras vizinhas: só o volume"
            continue
        if passo_ap(mv) > MAX_PASSO_AP_MM:
            m.nota = "série sem resolução ântero-posterior: só o volume"
            continue
        ref = _referencial(_pontos_mm(vols[b_nome]).mean(axis=0) - _pontos_mm(vols[a_nome]).mean(axis=0))
        if ref is None:
            m.nota = "eixo da coluna na direção ântero-posterior: altura não medida"
            continue
        u, a, lat = ref
        passo_u = _extensao(mv.matriz, u)
        t = (pts - pts.mean(axis=0)) @ u
        pts = pts[_principal(t, max(3.0, 2 * passo_u))]          # pedaço solto fora do disco: sai
        d = pts - pts.mean(axis=0)
        t, s, r = d @ u, d @ a, d @ lat
        centro = np.abs(r) <= max(FAIXA_SAGITAL_MM, 0.6 * _extensao(mv.matriz, lat))
        if centro.sum() < 10:
            m.nota = "faixa central sem disco suficiente"
            continue
        t, s = t[centro], s[centro]
        largura = max(1.0, 0.6 * _extensao(mv.matriz, a))
        s = s.copy()
        sel = _principal(s, max(3.0, 3 * largura))
        t, s = t[sel], s[sel]
        smin, smax = float(s.min()), float(s.max())
        m.profundidade = smax - smin + _extensao(mv.matriz, a)
        m.anterior = _altura_em(t, s, smin, smax, 1 - POS_BORDA, largura, passo_u)
        m.media = _altura_em(t, s, smin, smax, 0.5, largura, passo_u)
        m.posterior = _altura_em(t, s, smin, smax, POS_BORDA, largura, passo_u)
    out.sort(key=lambda x: POS.get(x.nome.split("-")[0], 99))
    _marcar_duvidosas(out, DUVIDOSA_DISCO, lambda m: POS.get(m.nome.split("-")[0], 0))
    return out


# ---------------------------------------------------------------- vértebras, uma sequência
def _corpo(s: np.ndarray, passo: float) -> tuple[float, float] | None:
    """Na faixa sagital central, a vértebra é o corpo, um vão (o canal) e o arco posterior. O corpo é o
    grupo **mais anterior que tenha tamanho de corpo** (≥ 8 mm de fundo e ≥ 15% dos pontos): um
    pedacinho solto na frente não passa por corpo."""
    if len(s) < 10:
        return None
    gs = _grupos(s, max(2.5, 1.5 * passo))
    if len(gs) < 2:
        return None                               # sem canal à vista: não dá para separar o corpo
    bons = [g for g in gs if (s[g].max() - s[g].min()) >= 8.0 and len(g) >= 0.15 * len(s)]
    if not bons:
        return None
    g = max(bons, key=lambda g: float(s[g].max()))                   # o mais anterior (s cresce para a frente)
    if g is gs[-1] and len(gs) == 1:
        return None
    return float(s[g].min()), float(s[g].max())


def _vertebras_cruas(obj) -> list[MedidaVertebra]:
    vols = {nivel_de(mv): mv for mv in getattr(obj, "volumes", []) or []}
    centros = {n: _pontos_mm(mv).mean(axis=0) for n, mv in vols.items()}
    out: list[MedidaVertebra] = []
    for nome, mv in vols.items():
        if "-" in nome or nome not in POS or nome in SEM_CORPO:
            continue
        m = MedidaVertebra(nome, centro=centros[nome])
        out.append(m)
        if getattr(mv, "cortada", False):
            m.nota = "cortada na borda da série"
            continue
        if passo_ap(mv) > MAX_PASSO_AP_MM:
            m.nota = "série sem resolução ântero-posterior (use a sagital)"
            continue
        i = POS[nome]
        cima = ORDEM[i - 1] if i > 0 else ""
        baixo = ORDEM[i + 1] if i + 1 < len(ORDEM) else ""
        da, db = f"{cima}-{nome}", f"{nome}-{baixo}"
        if da in centros and db in centros:
            u = centros[db] - centros[da]
        elif cima in centros and baixo in centros:
            u = centros[baixo] - centros[cima]
        elif baixo in centros:
            u = centros[baixo] - centros[nome]
        elif cima in centros:
            u = centros[nome] - centros[cima]
        else:
            m.nota = "sem vizinhas para achar o eixo"
            continue
        ref = _referencial(u)
        if ref is None:
            m.nota = "eixo na direção ântero-posterior"
            continue
        u, a, lat = ref
        passo_u = _extensao(mv.matriz, u)
        pts = _pontos_mm(mv)
        t = (pts - pts.mean(axis=0)) @ u
        pts = pts[_principal(t, max(3.0, 2 * passo_u))]            # pedaço solto acima/abaixo: sai
        d = pts - pts.mean(axis=0)
        t, sa, r = d @ u, d @ a, d @ lat
        centro = np.abs(r) <= max(FAIXA_SAGITAL_MM, 0.6 * _extensao(mv.matriz, lat))
        t, sa = t[centro], sa[centro]
        passo_a = max(1.0, 0.6 * _extensao(mv.matriz, a))
        corpo = _corpo(sa, passo_a)
        if corpo is None:
            m.nota = "corpo não separado do arco posterior"
            continue
        smin, smax = corpo
        sel = (sa >= smin - 1e-6) & (sa <= smax + 1e-6)
        t, sa = t[sel], sa[sel]
        m.profundidade = smax - smin + _extensao(mv.matriz, a)
        m.anterior = _altura_em(t, sa, smin, smax, 1 - POS_BORDA, passo_a, passo_u)
        m.media = _altura_em(t, sa, smin, smax, 0.5, passo_a, passo_u)
        m.posterior = _altura_em(t, sa, smin, smax, POS_BORDA, passo_a, passo_u)
    out.sort(key=lambda x: POS[x.nome])
    _marcar_duvidosas(out, None, lambda m: POS[m.nome], prof_max=ALTURA_POR_FUNDO)
    return out


def _marcar_duvidosas(lista: list, fator: float | None, pos, prof_max: float | None = None) -> None:
    """Altura que não pode ser osso (ou disco): a segmentação vazou ou juntou dois níveis num nome só.
    Duas regras, qualquer uma marca:
    - (discos) mais alta que `fator` × a mediana dos vizinhos (até dois níveis para cada lado);
    - (vértebras) mais alta que `prof_max` × a própria profundidade do corpo: um corpo vertebral é mais
      fundo que alto; um nome que pegou duas vértebras dá 55–60 mm de altura para 35 mm de fundo. Nas
      vértebras não se compara com as vizinhas: uma vizinha fraturada (vértebra plana) faria as normais
      parecerem "altas demais".
    A marcada não entra na graduação nem na referência das outras; a conta repete até parar de mudar."""
    for m in lista:
        if prof_max and m.profundidade:
            altas = [v for v in (m.anterior, m.media, m.posterior) if v is not None and v > prof_max * m.profundidade]
            if altas:
                m.duvidosa = True
                m.nota = f"medida duvidosa ({_num(max(altas))} mm de altura para {_num(m.profundidade)} mm de fundo)"
    for _volta in range(len(lista) if fator else 0):
        base = {pos(m): m.media for m in lista if m.media and not m.duvidosa}
        mudou = False
        for m in lista:
            if m.duvidosa:
                continue
            p = pos(m)
            viz = [base[q] for q in (p - 2, p - 1, p + 1, p + 2) if q in base]
            if len(viz) < 2:
                continue
            ref = float(np.median(viz))
            altas = [v for v in (m.anterior, m.media, m.posterior) if v is not None and v > fator * ref]
            if altas:
                m.duvidosa, mudou = True, True
                m.nota = f"medida duvidosa ({_num(max(altas))} mm; vizinhas ~{_num(ref)} mm)"
        if not mudou:
            break


# ---------------------------------------------------------------- duas sequências (0.99.5)
def _combinar(prim: list, outras: list[list]) -> None:
    """Junta, em `prim`, as medidas da(s) outra(s) sagital(is). O par é pela **posição** (centro a até
    12 mm), não pelo nome: as duas contagens podem estar deslocadas. Concordam (até 2 mm ou 10%): fica a
    média. Discordam: fica a da primeira, a outra vai em `alt`, e o nível não é graduado."""
    for m in prim:
        if m.centro is None:
            continue
        for lista in outras:
            cands = [c for c in lista if c.centro is not None]
            if not cands:
                continue
            c = min(cands, key=lambda c: float(np.linalg.norm(c.centro - m.centro)))
            tem_m = any(getattr(m, k) is not None for k in CAMPOS) and not m.duvidosa
            if float(np.linalg.norm(c.centro - m.centro)) > RAIO_PAR_MM:
                if tem_m and not m.nota:
                    m.nota = "não saiu na outra sagital"
                continue
            tem_c = any(getattr(c, k) is not None for k in CAMPOS) and not c.duvidosa
            if not tem_c:
                if tem_m and not m.nota:
                    m.nota = "na outra sagital: duvidosa" if c.duvidosa else "na outra sagital: sem medida"
                continue
            if not tem_m:                       # a primeira não mediu (ou vazou): vale a outra, sem grau
                for k in CAMPOS + ("profundidade",):
                    setattr(m, k, getattr(c, k))
                m.duvidosa, m.seq, m.concorda = False, 1, False
                m.nota = "medida só na outra sagital"
                continue
            m.seq += 1
            discordam = []
            for k in CAMPOS:
                a, b = getattr(m, k), getattr(c, k)
                if a is None or b is None:
                    discordam.append(k)
                    if a is None:
                        m.alt[k] = b
                    continue
                if abs(a - b) <= max(CONCORDA_MM, CONCORDA_REL * (a + b) / 2):
                    setattr(m, k, (a + b) / 2)
                else:
                    m.alt[k] = b
                    discordam.append(k)
            m.concorda = not discordam
            if discordam:
                nomes = {"anterior": "anterior", "media": "média", "posterior": "posterior"}
                m.nota = "discordam (" + ", ".join(nomes[k] for k in discordam) + "): conferir"
            if hasattr(m, "volume_ml") and hasattr(c, "volume_ml") and m.volume_ml and c.volume_ml:
                m.volume_ml = (m.volume_ml + c.volume_ml) / 2


def contagem_difere(obj, conferencias: tuple) -> str:
    """As duas sagitais deram nomes diferentes ao mesmo osso? (Numa RM real do acervo, o que a Sag T2 chamou de
    T11 a outra chamou de T12.) O par é pela posição; vale o deslocamento da maioria dos pares."""
    def centros(o):
        return {nivel_de(mv): _pontos_mm(mv).mean(axis=0) for mv in getattr(o, "volumes", []) or []
                if "-" not in nivel_de(mv) and nivel_de(mv) in POS}
    a = centros(obj)
    for conf in conferencias:
        b = centros(conf)
        if not a or not b:
            continue
        desl = []
        for n, c in a.items():
            m, d = min(((k, float(np.linalg.norm(v - c))) for k, v in b.items()), key=lambda kv: kv[1])
            if d <= RAIO_PAR_MM:
                desl.append((POS[m] - POS[n], n, m))
        if not desl:
            continue
        vals = [d for d, _n, _m in desl]
        moda = max(set(vals), key=vals.count)
        if moda != 0 and vals.count(moda) >= max(2, len(vals) // 2):
            _d, n, m = next(x for x in desl if x[0] == moda)
            return (f"as duas sagitais contaram diferente (o que nesta é {n}, na outra é {m}) — confira a "
                    "numeração; as medidas foram pareadas pela posição")
    return ""


def _graduar(vert: list, exigir_duas: bool) -> None:
    """Perda de altura de Genant: a maior entre cunha (1 − Ha/Hp), bicôncava (1 − Hm/Hp) e esmagamento
    (Hp contra a média das **duas** vizinhas). Grau só de T4 a L5, só em medida não duvidosa e — com
    duas sagitais — só onde as duas concordam."""
    validas = [x for x in vert if not x.duvidosa and not x.alt]
    hp = {x.nome: x.posterior for x in validas if x.posterior}
    for x in vert:
        x.ant_post = x.anterior / x.posterior if (x.anterior and x.posterior) else None
        x.perda, x.forma, x.grau = None, "", 0
        if x.duvidosa or not x.posterior:
            continue
        perdas = {}
        if x.anterior:
            perdas["cunha"] = 100.0 * (1 - x.anterior / x.posterior)
        if x.media:
            perdas["biconcava"] = 100.0 * (1 - x.media / x.posterior)
        i = POS[x.nome]
        viz = [hp[n] for n in (ORDEM[i - 1] if i else "", ORDEM[i + 1] if i + 1 < len(ORDEM) else "") if n in hp]
        if len(viz) == 2:          # só com as duas: a altura cresce de cima para baixo, uma vizinha só engana
            perdas["esmagamento"] = 100.0 * (1 - x.posterior / float(np.mean(viz)))
        if not perdas:
            continue
        x.forma, perda = max(perdas.items(), key=lambda kv: kv[1])
        x.perda = max(0.0, perda)
        if exigir_duas and not x.concorda:
            if x.perda >= GENANT[-1][0] and not x.nota:
                x.nota = "uma sagital só: sem grau"
            continue
        if GRADUA[0] <= i <= GRADUA[1]:
            x.grau = next((g for lim, g, _t in GENANT if x.perda >= lim), 0)
        elif x.perda >= GENANT[-1][0] and not x.nota:
            x.nota = "fora de T4–L5: sem grau de Genant"


def medir_discos(obj, conferencias: tuple = ()) -> list[MedidaDisco]:
    """Altura (anterior, média, posterior) e volume de cada disco, a partir dos volumes com nome.

    O eixo do disco é a linha entre os centros das duas vértebras vizinhas; a faixa central tem ±4 mm.
    A altura num ponto é o trecho **contínuo** de disco naquela coluna de voxels (0.99.5), mais um voxel.
    `conferencias`: objetos da(s) outra(s) sagital(is) do mesmo exame."""
    out = _discos_crus(obj)
    if conferencias:
        _combinar(out, [_discos_crus(c) for c in conferencias])
    for acima, este in zip(out, out[1:]):
        este.vs_acima = None
        ok = acima.media and este.media and not acima.duvidosa and not este.duvidosa
        if ok and POS.get(este.nome.split("-")[0], 0) - POS.get(acima.nome.split("-")[0], 0) == 1:
            este.vs_acima = 100.0 * este.media / acima.media
    return out


def medir_vertebras(obj, conferencias: tuple = ()) -> list[MedidaVertebra]:
    """Altura do **corpo** vertebral (anterior, média, posterior) e a perda de altura de Genant.

    O corpo sai da faixa sagital central: o grupo de osso mais anterior com tamanho de corpo, antes do
    vão do canal. Pedaço solto que a IA marcou com o nome da vértebra sai (0.99.5); altura muito acima das
    vizinhas fica "duvidosa". Com `conferencias` (a outra sagital), só gradua onde as duas concordam."""
    out = _vertebras_cruas(obj)
    if conferencias:
        _combinar(out, [_vertebras_cruas(c) for c in conferencias])
    _graduar(out, exigir_duas=bool(conferencias))
    return out


RES_MODELO_MM = 1.5          # os modelos usados para medir trabalham em 1,5 mm


def resolucao_mm(obj) -> float | None:
    """Incerteza de cada borda de uma altura: o voxel na direção crânio-caudal ou a grade do modelo,
    o que for maior."""
    for mv in getattr(obj, "volumes", []) or []:
        return max(RES_MODELO_MM, _extensao(mv.matriz, np.array([0.0, 0.0, 1.0])))
    return None


def _valor(m, k: str, casas: int = 1) -> str:
    v = _num(getattr(m, k), casas)
    return f"{v} | {_num(m.alt[k], casas)}" if k in m.alt else v


def texto_da_medida(m: MedidaDisco) -> str:
    base = (f"{m.nome}: altura {_valor(m, 'media')} mm (ant {_valor(m, 'anterior')} / post {_valor(m, 'posterior')}), "
            f"{_num(m.volume_ml, 2)} mL")
    return base + (f" — {m.nota}" if m.nota else "")


def texto_da_vertebra(m: MedidaVertebra) -> str:
    base = (f"{m.nome}: corpo {_valor(m, 'anterior')} / {_valor(m, 'media')} / {_valor(m, 'posterior')} mm "
            "(ant/média/post)")
    if m.perda is not None:
        base += f", perda {m.perda:.0f}%"
        if m.grau:
            base += f" ({FORMAS.get(m.forma, m.forma)}, {m.grau_txt})"
    if m.seq > 1:
        base += f" [{m.seq} sagitais]"
    return base + (f" — {m.nota}" if m.nota else "")


def anexar_medidas(obj, conferencias: tuple | None = None) -> list:
    """As medidas dos discos e das vértebras na lista do objeto (o que o menu de sobreposições mostra).
    Devolve as dos discos (as das vértebras ficam em `obj.medidas_vertebras`). Sem `conferencias`, usa as
    que o objeto já guardou (`obj.conferencias`, posto ao abrir o exame)."""
    if not MEDIR_DISPONIVEL:
        obj.findings = [f for f in obj.findings if not str(f).startswith("📏")]
        try:
            obj.medidas_vertebras = []
        except Exception:  # noqa: BLE001
            pass
        return []
    conf = tuple(conferencias if conferencias is not None else (getattr(obj, "conferencias", None) or ()))
    try:
        medidas = medir_discos(obj, conf)
    except Exception:  # noqa: BLE001
        log.exception("medir os discos")
        medidas = []
    try:
        vert = medir_vertebras(obj, conf)
    except Exception:  # noqa: BLE001
        log.exception("medir as vértebras")
        vert = []
    try:
        obj.medidas_vertebras = vert
        if conferencias is not None:
            obj.conferencias = conf
    except Exception:  # noqa: BLE001
        pass
    aviso = "; ".join(x for x in (aviso_da_serie(obj), contagem_difere(obj, conf)) if x)
    obj.findings = [f for f in obj.findings if not str(f).startswith("📏")] + \
        ([f"📏 ⚠ {aviso}"] if aviso else []) + \
        [f"📏 {texto_da_vertebra(v)}" for v in vert] + [f"📏 {texto_da_medida(md)}" for md in medidas]
    return medidas


def resumo_medidas(medidas: list) -> str:
    alturas = [m for m in medidas if m.media is not None and not m.duvidosa]
    if not alturas:
        return ""
    menor = min(alturas, key=lambda m: m.media)
    return (f"{len(alturas)} discos medidos; o mais baixo é {menor.nome} ({_num(menor.media)} mm"
            + (f", {menor.vs_acima:.0f}% do de cima" if menor.vs_acima is not None else "") + ")")


def resumo_vertebras(medidas: list) -> str:
    feitas = [m for m in medidas if m.perda is not None]
    if not feitas:
        return ""
    txt = f"{len(feitas)} vértebras medidas"
    alteradas = [m for m in feitas if m.grau]
    txt += ("; perda de altura ≥ 20% em " + ", ".join(
        f"{m.nome} ({m.perda:.0f}%, {FORMAS.get(m.forma, m.forma)})" for m in alteradas)) if alteradas \
        else ", nenhuma com perda de altura de 20% ou mais"
    conferir = [m.nome for m in medidas if m.alt or m.duvidosa]
    if conferir:
        txt += "; conferir " + ", ".join(conferir)
    return txt


# ------------------------------------------------------------------ a segunda sagital (0.99.5)
def _numeros(texto) -> list[float]:
    import re as _re
    return [float(x) for x in _re.findall(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", str(texto or ""))]


def eh_sagital(repo, series_uid: str) -> bool:
    inst = repo.instances_for_series(series_uid)
    if not inst:
        return False
    v = _numeros(inst[len(inst) // 2].get("orientation"))
    if len(v) < 6:
        return False
    n = np.cross(np.array(v[:3]), np.array(v[3:6]))
    return float(np.linalg.norm(n)) > 0 and abs(n[0]) / float(np.linalg.norm(n)) >= 0.8


def segunda_serie(repo, study_uid: str, primeira: str, settings=None) -> str | None:
    """A outra sagital do exame para conferir as medidas: RM, sagital, ≥ mínimo de cortes, sem
    localizador/MIP; a de cima na lista de prioridade da RM (Sag T2, T1, STIR…), depois a de mais cortes."""
    from ipe.ai import totalseg as TS
    minimo = max(int(config(settings, CHAVE_MIN_CORTES) or MIN_CORTES), MIN_CORTES)
    limite = float(config(settings, CHAVE_ESPESSURA) or 0)
    pads = TS._padroes(config(settings, CHAVE_PRIOR_MR))
    cands = []
    for s in repo.series_for_study(study_uid):
        if s.series_uid == primeira or (s.modality or "").upper() != "MR":
            continue
        desc = TS._sem_acento(s.description or "")
        if "TOTALSEGMENTATOR" in desc or any(x in desc for x in TS._NUNCA):
            continue
        n = len(repo.instances_for_series(s.series_uid))
        if n < minimo or not eh_sagital(repo, s.series_uid):
            continue
        esp = TS._espessura(repo, s.series_uid)
        if limite and esp is not None and esp > limite + 1e-6:
            continue
        nivel = next((k for k, p in enumerate(pads) if p in desc), len(pads))
        cands.append((nivel, -n, s.series_uid))
    return min(cands)[2] if cands else None


def quer_conferencia(settings, modalidade: str) -> bool:
    return ((modalidade or "").upper() == "MR" and bool(config(settings, CHAVE_MEDIR))
            and int(config(settings, CHAVE_SEQUENCIAS) or 1) >= 2)


def conferencias_do_exame(repo, study_uid: str) -> list:
    """Os objetos da segunda sagital guardada no exame (a mais recente)."""
    out = []
    for s in repo.series_for_study(study_uid):
        if (s.description or "") != DESC_CONF:
            continue
        for inst in repo.instances_for_series(s.series_uid)[:1]:
            try:
                out.append((str(inst.get("path")), objeto_do_seg(inst["path"], study_uid)))
            except Exception:  # noqa: BLE001
                log.exception("ler a SEG de conferência da coluna")
    return [o for _p, o in out[-1:]]


# ------------------------------------------------------------------ a tabela dos discos (OT)
def cabecalho_do_seg(repo, seg_path: str) -> dict:
    """Paciente, aparelho, data e a série de onde saiu, lidos da série que a SEG referencia."""
    import pydicom
    ds = pydicom.dcmread(seg_path, stop_before_pixels=True, force=True)
    fonte, serie_desc = None, ""
    try:
        uid = str(ds.ReferencedSeriesSequence[0].SeriesInstanceUID)
        inst = repo.instances_for_series(uid)
        fonte = inst[0]["path"] if inst else None
        serie_desc = next((s.description or "" for s in repo.series_for_study(str(ds.StudyInstanceUID))
                           if s.series_uid == uid), "")
    except Exception:  # noqa: BLE001
        pass
    src = pydicom.dcmread(fonte, stop_before_pixels=True, force=True) if fonte else ds
    data = str(src.get("StudyDate", "") or "")
    if len(data) == 8:
        data = f"{data[6:]}/{data[4:6]}/{data[:4]}"
    esp = src.get("SliceThickness")
    if esp:
        serie_desc += f" ({float(esp):g} mm)".replace(".", ",")
    return {"paciente": str(src.get("PatientName", "") or "").replace("^", " ").strip(),
            "id": str(src.get("PatientID", "") or ""), "data": data, "serie": serie_desc,
            "modalidade": str(src.get("Modality", "") or ""), "fonte": fonte or seg_path,
            "versao": str(ds.SegmentSequence[0].get("SegmentAlgorithmName", "")) if "SegmentSequence" in ds else ""}


def _desenhar(titulo: str, cols: list, linhas: list, vermelhas: set, cab: dict, notas: list) -> np.ndarray:
    """Tabela branca de 1600 px: título, paciente, série, cabeçalho azul, linhas zebradas e notas.
    `cols`: [(nome, fração da largura)] — a última fica com o resto; `linhas`: listas de textos;
    `vermelhas`: {(linha, coluna)} que saem em vermelho."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

    largura, m = 1600, 30
    alt_l, topo = 44, 190
    notas = [n for n in notas if n]
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QFontMetrics
    fn = QFont("DejaVu Sans")
    fn.setPixelSize(19)
    fm = QFontMetrics(fn)
    util0 = largura - 2 * m
    alturas_notas = [fm.boundingRect(QRect(0, 0, util0, 2000), int(Qt.TextWordWrap), n).height() + 10
                     for n in notas]                          # nota comprida quebra a linha, não corta
    altura = topo + alt_l * (len(linhas) + 1) + 40 + sum(alturas_notas) + 30
    img = QImage(largura, altura, QImage.Format_RGB888)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    def fonte(px, neg=False):
        f = QFont("DejaVu Sans")
        f.setPixelSize(px)
        f.setBold(neg)
        p.setFont(f)

    def texto(x, y, w, h, s_, cor=(30, 30, 30), al=Qt.AlignLeft | Qt.AlignVCenter):
        p.setPen(QColor(*cor))
        p.drawText(QRectF(x, y, w, h), int(al), s_)

    fonte(40, True)
    mod = "TC" if cab.get("modalidade") == "CT" else "RM" if cab.get("modalidade") == "MR" else ""
    texto(m, 18, largura, 56, f"{titulo}{(' — ' + mod) if mod else ''}")
    fonte(21)
    sub = "  |  ".join(x for x in (f"Paciente {cab.get('id', '')}".strip(), cab.get("paciente", ""),
                                   f"Estudo {cab.get('data', '')}".strip()) if x.strip())
    texto(m, 76, largura - 2 * m, 30, sub, (70, 70, 70))
    texto(m, 106, largura - 2 * m, 30, f"Série: {cab.get('serie', '')}  ·  {cab.get('versao', '')}", (70, 70, 70))
    util = largura - 2 * m
    xs, x = [], m
    for _n, fr in cols:
        xs.append(x)
        x += fr * util
    xs.append(largura - m)
    y = topo
    p.fillRect(QRectF(m, y, util, alt_l), QColor(38, 54, 89))
    fonte(20, True)
    for k, (n, _f) in enumerate(cols):
        texto(xs[k] + 12, y, xs[k + 1] - xs[k] - 16, alt_l, n, (255, 255, 255),
              (Qt.AlignLeft if k in (0, len(cols) - 1) else Qt.AlignHCenter) | Qt.AlignVCenter)
    y += alt_l
    for i, linha in enumerate(linhas):
        p.fillRect(QRectF(m, y, util, alt_l), QColor(247, 247, 247) if i % 2 else QColor(255, 255, 255))
        for k, v in enumerate(linha):
            fonte(20, k == 0)
            cor = (180, 60, 30) if (i, k) in vermelhas else (30, 30, 30)
            texto(xs[k] + 12, y, xs[k + 1] - xs[k] - 16, alt_l, v, cor,
                  (Qt.AlignLeft if k in (0, len(linha) - 1) else Qt.AlignHCenter) | Qt.AlignVCenter)
        p.setPen(QPen(QColor(215, 215, 215), 1))
        p.drawLine(m, int(y + alt_l), largura - m, int(y + alt_l))
        y += alt_l
    p.setPen(QPen(QColor(200, 200, 200), 1))
    p.drawRect(QRectF(m, topo, util, y - topo))
    p.setFont(fn)
    p.setPen(QColor(90, 90, 90))
    yy = y + 24
    for n, h in zip(notas, alturas_notas):
        p.drawText(QRectF(m, yy, util, h), int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap), n)
        yy += h
    p.end()
    buf = img.constBits()
    arr = np.frombuffer(buf, np.uint8, count=img.sizeInBytes()).reshape(altura, img.bytesPerLine())
    return arr[:, : largura * 3].reshape(altura, largura, 3).copy()


def _nota_resolucao(resolucao: float | None) -> str:
    if not resolucao:
        return ""
    return (f"Resolução da segmentação na altura: {_num(resolucao)} mm por borda; diferenças menores que "
            "isso entre níveis não são diferença.")


def _nota_seq(cab: dict) -> str:
    if cab.get("serie2"):
        return ("Medido em duas sagitais: com as duas concordando (até 2 mm ou 10%), vale a média; quando "
                "discordam, as duas aparecem (primeira | segunda) e o nível não é graduado.")
    return "Medido numa sagital só."


def desenhar_tabela(medidas: list[MedidaDisco], cab: dict, resolucao: float | None, avisos_: list,
                    extra: tuple = ()) -> np.ndarray:
    cols = [("Disco", 0.11), ("Anterior (mm)", 0.14), ("Média (mm)", 0.14), ("Posterior (mm)", 0.14),
            ("Volume (mL)", 0.11), ("vs. acima", 0.10), ("Seq.", 0.06), ("Observação", 0.0)]
    linhas, vermelhas = [], set()
    for i, md in enumerate(medidas):
        linhas.append([md.nome, _valor(md, "anterior"), _valor(md, "media"), _valor(md, "posterior"),
                       _num(md.volume_ml, 2), f"{_num(md.vs_acima, 0)}%" if md.vs_acima is not None else "—",
                       str(md.seq), md.nota])
        if md.vs_acima is not None and md.vs_acima < 75:
            vermelhas.add((i, 5))
        for k, col in (("anterior", 1), ("media", 2), ("posterior", 3)):
            if k in md.alt:
                vermelhas.add((i, col))
        if md.duvidosa or md.alt:
            vermelhas.add((i, 7))
    notas = ["Alturas no eixo entre os centros das vértebras vizinhas, na faixa sagital central (±4 mm); "
             "anterior e posterior a 10% da profundidade.",
             _nota_seq(cab), _nota_resolucao(resolucao),
             "Segmentação automática (TotalSegmentator). Confira os níveis (botão direito ▸ Renumerar) antes de "
             "usar os números. Não destinado a uso diagnóstico."]
    notas += [f"Confira a numeração: {a}." for a in avisos_] + [f"Atenção: {e}." for e in extra if e]
    return _desenhar("Discos intervertebrais — altura e volume", cols, linhas, vermelhas, cab, notas)


def desenhar_tabela_vertebras(medidas: list[MedidaVertebra], cab: dict, resolucao: float | None,
                              avisos_: list, extra: tuple = ()) -> np.ndarray:
    cols = [("Vértebra", 0.10), ("Anterior (mm)", 0.14), ("Média (mm)", 0.14), ("Posterior (mm)", 0.14),
            ("Ant/Post", 0.08), ("Perda", 0.08), ("Seq.", 0.06), ("Observação", 0.0)]
    linhas, vermelhas = [], set()
    for i, md in enumerate(medidas):
        obs = md.nota or (f"{FORMAS.get(md.forma, md.forma)}, grau {md.grau} ({md.grau_txt})" if md.grau else "")
        if md.grau and md.nota:
            obs = f"{FORMAS.get(md.forma, md.forma)}, grau {md.grau}; {md.nota}"
        linhas.append([md.nome, _valor(md, "anterior"), _valor(md, "media"), _valor(md, "posterior"),
                       _num(md.ant_post, 2), f"{md.perda:.0f}%" if md.perda is not None else "—", str(md.seq), obs])
        if md.grau:
            vermelhas |= {(i, 5), (i, 7)}
        for k, col in (("anterior", 1), ("media", 2), ("posterior", 3)):
            if k in md.alt:
                vermelhas.add((i, col))
        if md.duvidosa or md.alt:
            vermelhas.add((i, 7))
    notas = ["Altura do corpo no eixo da coluna naquele nível, na faixa sagital central (±4 mm); "
             "anterior e posterior a 10% da profundidade do corpo.",
             "Perda de altura (Genant): a maior entre cunha (1 − Ha/Hp), bicôncava (1 − Hm/Hp) e esmagamento "
             "(Hp contra as vizinhas). Grau 1: 20–25%; 2: 25–40%; 3: 40% ou mais (T4 a L5).",
             _nota_seq(cab), _nota_resolucao(resolucao),
             "Segmentação automática (TotalSegmentator). Confira os níveis antes de usar os números. Não destinado "
             "a uso diagnóstico."]
    notas += [f"Confira a numeração: {a}." for a in avisos_] + [f"Atenção: {e}." for e in extra if e]
    return _desenhar("Corpos vertebrais — altura e perda de altura", cols, linhas, vermelhas, cab, notas)


def gravar_tabela(repo, db, storage_root, study_uid: str, seg_path: str, obj=None) -> dict:
    """Mede discos e vértebras (com a segunda sagital, se o exame tiver) e grava as duas tabelas no exame
    (séries locais). Troca as anteriores: depois de renumerar, os nomes mudam."""
    from pathlib import Path

    from ipe.imaging.derived import save_secondary_capture
    obj = obj if obj is not None else objeto_do_seg(seg_path, study_uid)
    confs = tuple(conferencias_do_exame(repo, study_uid))
    medidas = anexar_medidas(obj, confs)
    vert = list(getattr(obj, "medidas_vertebras", []) or [])
    for se in repo.series_for_study(study_uid):
        if (se.description or "") in (DESC_TABELA, DESC_TABELA_VERT):
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
            except Exception:  # noqa: BLE001
                log.exception("trocar a tabela da coluna")
    series = []
    if medidas or vert:
        cab = cabecalho_do_seg(repo, seg_path)
        if confs:
            for s in repo.series_for_study(study_uid):
                if (s.description or "") == DESC_CONF:
                    inst = repo.instances_for_series(s.series_uid)[:1]
                    if inst:
                        cab["serie2"] = cabecalho_do_seg(repo, inst[0]["path"]).get("serie", "")
            if cab.get("serie2"):
                cab["serie"] = f"{cab.get('serie', '')} + {cab['serie2']}"
        avisos_ = [f[2:] for f in getattr(obj, "findings", []) if str(f).startswith("⚠")]
        res = resolucao_mm(obj)
        extra = (aviso_da_serie(obj), contagem_difere(obj, confs))
        if vert:
            rgb = desenhar_tabela_vertebras(vert, cab, res, avisos_, extra)
            uid, _s = save_secondary_capture(rgb, cab["fonte"], db, storage_root, description=DESC_TABELA_VERT,
                                             series_number=SERIE_TABELA_VERT,
                                             extra={"BurnedInAnnotation": "YES",
                                                    "ImageComments": "Corpos vertebrais — altura e perda de altura"})
            series.append(uid)
        if medidas:
            rgb = desenhar_tabela(medidas, cab, res, avisos_, extra)
            uid, _s = save_secondary_capture(rgb, cab["fonte"], db, storage_root, description=DESC_TABELA,
                                             series_number=SERIE_TABELA,
                                             extra={"BurnedInAnnotation": "YES",
                                                    "ImageComments": "Discos intervertebrais — altura e volume"})
            series.append(uid)
    aviso = "; ".join(x for x in (aviso_da_serie(obj), contagem_difere(obj, confs)) if x)
    return {"medidas": medidas, "vertebras": vert, "series": series, "aviso": aviso,
            "sequencias": 1 + len(confs)}


def tem_tabela(repo, study_uid: str) -> bool:
    return any((s.description or "") in (DESC_TABELA, DESC_TABELA_VERT) for s in repo.series_for_study(study_uid))


def resumo_tabelas(tab: dict) -> str:
    seq = int(tab.get("sequencias") or 1)
    return "; ".join(x for x in (resumo_vertebras(tab.get("vertebras") or []),
                                 resumo_medidas(tab.get("medidas") or []),
                                 "conferido em duas sagitais" if seq > 1 else "", tab.get("aviso", "")) if x)
