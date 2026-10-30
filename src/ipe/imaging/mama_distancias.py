"""Distâncias da lesão à pele, ao mamilo e ao limite posterior (parede torácica/peitoral).

É o que o laudo de RM de mama pede junto do tamanho: lesão a 8 mm da pele, a 42 mm do mamilo, a
15 mm do peitoral. O programa devolve os três números; a interpretação é do médico.

De onde vem cada referência, e o que cada uma vale:

- **Pele**: a superfície do corpo que encosta no **ar de fora**. Buraco interno de gordura ou de
  vaso não é pele — a máscara da mama é por limiar e é cheia de buracos; medir até a borda do
  buraco mais próximo daria 1 mm em qualquer lesão. O ar de fora se acha alastrando desde a borda
  do corte, o mesmo truque que acha o pulmão na máscara da mama (0.55).
- **Limite posterior**: onde a máscara da mama foi cortada, isto é a interface com a parede
  torácica. O músculo peitoral fica **dentro** da máscara (quem marca a parede é o pulmão, e o
  músculo está na frente dele), então este número é a distância até a parede, não até a borda
  anterior do músculo. Por isso existe a marcação à mão, e por isso a tela diz qual das duas foi
  usada.
- **Mamilo**: o ponto mais anterior da pele, do lado da lesão. Serve na maioria dos exames e erra
  quando a mama está cortada no campo ou o mamilo está retraído — então é proposta, não veredito:
  um clique do médico substitui o ponto, e a tela diz de quem é o ponto que está valendo.

Tudo em coordenadas do paciente (mm). Ali o anterior é o menor y e o lado é o x, sem depender do
plano da aquisição: no sagital do acervo dele os eixos da imagem trocam de lugar, e conta feita em
índice de imagem erraria de exame para exame.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

ORCAMENTO = 20000        # pontos na primeira passada da distância (a segunda é exata e local)
FOLGA_MM = 3.0           # margem da segunda passada, para não perder o voxel mais perto


# --------------------------------------------------------------------------- geometria
def eixo_ap_do_volume(orientation, slice_vec) -> tuple[int, int]:
    """Qual eixo do volume `(corte, linha, coluna)` anda de anterior para posterior, e o sentido.

    O y do DICOM cresce para posterior. Devolve (-1, 0) quando nenhum dos três eixos é
    predominantemente A-P (aquisição oblíqua): aí não há limite posterior que se possa afirmar.
    """
    ori = np.asarray(orientation, float).ravel()
    sv = np.asarray(slice_vec, float).ravel()
    if ori.size != 6 or sv.size != 3:
        return (-1, 0)
    col_dir, row_dir = ori[:3], ori[3:]       # direção de i (colunas) e de j (linhas)
    n = float(np.linalg.norm(sv))
    dirs = [sv / n if n > 1e-6 else sv, row_dir, col_dir]      # eixos 0, 1, 2 do array
    ys = [abs(float(d[1])) for d in dirs]
    a = int(np.argmax(ys))
    # 0,8 ≈ até 37° fora do eixo. Um sagital inclinado de mama fica em 0,94 ou mais; a 45° (0,707)
    # o "mais posterior da linha" já não é a parede torácica, e aí é melhor não dar número nenhum.
    if ys[a] < 0.8:
        return (-1, 0)
    return (a, 1 if float(dirs[a][1]) > 0 else -1)


def afim_do_volume(origem, orientation, dx: float, dy: float, slice_vec) -> tuple:
    """(origem, passo de i, passo de j, passo de k) em mm — leva índice do array a mm."""
    ori = np.asarray(orientation, float).ravel()
    return (np.asarray(origem, float), ori[:3] * float(dx), ori[3:] * float(dy),
            np.asarray(slice_vec, float))


def afim_do_objeto(vol) -> tuple:
    """O mesmo, a partir de um `imaging.volume.Volume`.

    Ali `row_dir` é a direção de **i** (colunas) e `col_dir` a de **j** (linhas) — nomes que
    enganam, e trocá-los põe a lesão no lugar errado do paciente. Esta função existe para o erro
    não ter onde acontecer duas vezes.
    """
    return (np.asarray(vol.origin, float), np.asarray(vol.row_dir, float) * float(vol.dx),
            np.asarray(vol.col_dir, float) * float(vol.dy), np.asarray(vol.slice_vec, float))


def para_mm(indices: np.ndarray, afim) -> np.ndarray:
    """Índices `(k, j, i)` -> mm no paciente. `indices` é (N, 3)."""
    origem, ei, ej, ek = afim
    idx = np.asarray(indices, np.float64)
    return (origem[None, :] + idx[:, 2:3] * ei[None, :] + idx[:, 1:2] * ej[None, :]
            + idx[:, 0:1] * ek[None, :])


# --------------------------------------------------------------------------- superfícies
def ar_e_pulmao(corpo: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(ar de fora, pulmão) — o escuro que encosta na borda do corte, e o escuro que o corpo fecha.

    Em duas etapas, e a ordem importa:

    1. **Grade reduzida** (a mesma da máscara da mama): ali a traqueia e os brônquios, que têm um
       ou dois voxels de largura, somem na subamostragem, e o pulmão fica fechado como tem de
       ficar. Esta etapa decide *quem é quem*.
    2. **Grade cheia**, com o pulmão da etapa 1 como **barreira**: refina a posição da pele até o
       voxel certo, sem deixar o ar de fora entrar no pulmão pela traqueia.

    Sem a barreira, o refinamento enchia o pulmão de "ar de fora": no acervo o pulmão caía para
    0,23% do volume, a parede torácica ia parar nas costas (mediana 104 mm atrás do mamilo, quando
    a parede está a 42-58 mm) e as distâncias à pele e ao peitoral saíam erradas.
    """
    from ipe.imaging.mama_mascara import LADO_MAX, _propagar
    escuro = ~corpo
    _nz, ny, nx = escuro.shape
    f = max(1, int(np.ceil(max(ny, nx) / float(LADO_MAX))))
    reduzido = escuro[:, ::f, ::f]
    semente = np.zeros_like(reduzido)
    # só as bordas dentro do corte, como em `_pulmoes`: as faces da pilha podem ser tecido
    semente[:, 0] = semente[:, -1] = True
    semente[:, :, 0] = semente[:, :, -1] = True
    fora_r = _propagar(semente & reduzido, reduzido)
    if f > 1:
        fora_r = np.repeat(np.repeat(fora_r, f, axis=1), f, axis=2)[:, :ny, :nx]
    fechado = escuro & ~fora_r               # grosseiro, mas com a topologia certa
    pulmao_aprox = regioes_espessas(fechado)
    fora = _propagar(fora_r & escuro, escuro & ~pulmao_aprox, voltas=2)
    return fora, (escuro & ~fora) & _expandir(pulmao_aprox, 2)


def ar_de_fora(corpo: np.ndarray) -> np.ndarray:
    """Só o ar do ambiente (ver `ar_e_pulmao`)."""
    return ar_e_pulmao(corpo)[0]


def _expandir(mask: np.ndarray, voltas: int = 1) -> np.ndarray:
    """Dilata a máscara em `voltas` voxels (6-conectividade)."""
    saida = mask.copy()
    for _ in range(max(0, int(voltas))):
        anterior = saida
        for eixo in range(3):
            for passo in (1, -1):
                saida = saida | np.roll(anterior, passo, axis=eixo)
    return saida


def regioes_espessas(fechado: np.ndarray, voltas: int = 3) -> np.ndarray:
    """Só as regiões fechadas **espessas**: o pulmão, e não cada bolsa de ar do exame.

    Medido no acervo: a 15 mm do mamilo a "parede torácica" saltava 49 mm para a frente, porque
    ali a primeira região escura fechada da linha era uma bolsa de ar ao lado da mama, não o
    pulmão. Pulmão é espesso em todas as direções (bem mais de 1 cm); bolsa de ar, não.

    Erodir e devolver por alastramento é o que separa os dois: sobrevive à erosão só o que tem
    miolo, e o alastramento devolve a região inteira a partir do miolo — sem precisar separar
    componente por componente, que num volume de 29 milhões de voxels não termina.
    """
    from ipe.imaging.mama_mascara import _propagar
    nucleo = fechado
    for _ in range(max(1, int(voltas))):
        anterior = nucleo
        for eixo in range(3):
            for passo in (1, -1):
                nucleo = nucleo & np.roll(anterior, passo, axis=eixo)
    if not nucleo.any():
        return np.zeros_like(fechado)
    return _propagar(nucleo, fechado)


def pele(corpo: np.ndarray) -> np.ndarray:
    """Voxels de corpo que encostam no ar de fora."""
    return pele_de(corpo, ar_de_fora(corpo))


def pele_de(corpo: np.ndarray, fora: np.ndarray) -> np.ndarray:
    """O mesmo, com o ar de fora já calculado (ele e o pulmão saem do mesmo alastramento)."""
    vizinho = np.zeros_like(fora)
    for eixo in range(3):
        for passo in (1, -1):
            vizinho |= np.roll(fora, passo, axis=eixo)
    return corpo & vizinho


ESCURO_MIN_MM = 20.0     # trecho escuro que conta como pulmão (medido: o pulmão dá 90 mm)


def _primeiro_escuro_longo(corpo: np.ndarray, eixo_ap: int, sentido: int,
                           mm_por_passo: float, minimo_mm: float = ESCURO_MIN_MM) -> np.ndarray:
    """Para cada linha, o índice em que começa o primeiro trecho escuro **longo** (ou -1).

    É esta a regra que acha o pulmão numa RM de mama, e não "o escuro que o corpo fecha": no
    acervo dele a imagem sagital **acaba dentro do pulmão** (o FOV não pega as costas), então o
    pulmão encosta na borda e a regra do fechamento o classifica como ar de fora. O que sobrava
    eram bolsas de ar de poucos milímetros, e a parede torácica saltava 49 mm de um corte para o
    outro. O pulmão mede 90 mm de trecho escuro no perfil; bolsa de ar, uns poucos.
    """
    v = np.moveaxis(~corpo, eixo_ap, 0)
    if sentido < 0:
        v = v[::-1]
    n = v.shape[0]
    passos = max(1, int(round(float(minimo_mm) / max(mm_por_passo, 1e-3))))
    if passos >= n:
        return np.full(v.shape[1:], -1, np.int32)
    soma = np.cumsum(v.astype(np.int32), axis=0)
    # trecho escuro de `passos` voxels começando em i: soma[i+passos-1] - soma[i-1] == passos
    base = np.concatenate([np.zeros((1, *v.shape[1:]), np.int32), soma[:-1]], axis=0)
    cheio = (soma[passos - 1:] - base[:n - passos + 1]) == passos
    faixa = np.arange(cheio.shape[0])[:, None, None]
    # A busca começa **na pele**, não na borda da imagem: na frente da mama o que há é ar, que é
    # o trecho escuro mais longo de todos. Sem isto a linha inteira cai fora e não sobra parede.
    tecido = ~v
    primeiro = np.where(tecido.any(axis=0), np.where(tecido, np.arange(n)[:, None, None], n).min(axis=0), n)
    cheio = cheio & (faixa > primeiro[None][:1])
    tem = cheio.any(axis=0)
    return np.where(tem, np.where(cheio, faixa, n).min(axis=0), -1).astype(np.int32)


def parede_e_pele(corpo: np.ndarray, pele_mask: np.ndarray, eixo_ap: int, sentido: int,
                  mm_por_passo: float) -> tuple[np.ndarray, np.ndarray]:
    """(parede torácica, pele da mama): o tecido que encosta no pulmão, e a pele na frente dele.

    Por linha: acha onde começa o primeiro trecho escuro longo (o pulmão), toma o último voxel de
    tecido antes dele — essa é a parede — e fica com a pele que está na frente dessa parede.
    Linha sem trecho escuro longo não entra: ali não há como afirmar onde a mama acaba.
    """
    vazio = np.zeros_like(corpo)
    if eixo_ap < 0:
        return vazio, pele_mask
    inicio = _primeiro_escuro_longo(corpo, eixo_ap, sentido, mm_por_passo)
    corpo_v = np.moveaxis(corpo, eixo_ap, 0)
    pele_v = np.moveaxis(pele_mask, eixo_ap, 0)
    if sentido < 0:
        corpo_v, pele_v = corpo_v[::-1], pele_v[::-1]
    n = corpo_v.shape[0]
    faixa = np.arange(n)[:, None, None]
    tem = inicio[None] >= 0
    antes = faixa < inicio[None]
    idx = np.where(corpo_v & antes & tem, faixa, -1)
    ultimo = idx.max(axis=0)
    parede = corpo_v & tem & (ultimo[None] >= 0) & (faixa >= ultimo[None]) & antes
    pele = pele_v & tem & antes
    if sentido < 0:
        parede, pele = parede[::-1], pele[::-1]
    return np.moveaxis(parede, 0, eixo_ap), np.moveaxis(pele, 0, eixo_ap)


def _amostra(mask: np.ndarray, orcamento: int = ORCAMENTO) -> np.ndarray:
    """Índices (N, 3) dos voxels da máscara, no máximo `orcamento` deles."""
    z, y, x = np.nonzero(mask)
    if len(z) > orcamento > 0:
        passo = int(np.ceil(len(z) / orcamento))
        z, y, x = z[::passo], y[::passo], x[::passo]
    return np.stack([z, y, x], 1)


# --------------------------------------------------------------------------- distâncias
def _menor(a: np.ndarray, b: np.ndarray) -> float:
    """Menor distância entre dois conjuntos de pontos em mm, em blocos (sem estourar memória)."""
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    melhor = np.inf
    bloco = max(1, int(4e6 // max(len(b), 1)))
    for i in range(0, len(a), bloco):
        d = a[i:i + bloco, None, :] - b[None, :, :]
        melhor = min(melhor, float(np.sqrt((d * d).sum(axis=2)).min()))
    return melhor


def menor_distancia(pontos: np.ndarray, nuvem: np.ndarray, fina: np.ndarray | None = None) -> float:
    """Menor distância em mm, em duas passadas: a grossa acha a região, a fina é exata ali.

    Sem as duas passadas isto é um produto de milhões por milhares: a pele de uma RM de mama do
    acervo tem 1,3 milhão de voxels.
    """
    if len(pontos) == 0 or len(nuvem) == 0:
        return float("nan")
    d0 = _menor(pontos, nuvem)
    if fina is None or not np.isfinite(d0):
        return d0
    centro = pontos.mean(axis=0)
    raio = d0 + FOLGA_MM + float(np.sqrt(((pontos - centro) ** 2).sum(axis=1)).max())
    perto = fina[(np.abs(fina - centro) <= raio).all(axis=1)]
    if len(perto) == 0:
        return d0
    return min(d0, _menor(pontos, perto))


# Aquisição mais larga que isto (esquerda-direita do paciente) pega as duas mamas: o meio do
# volume separa uma da outra. Mais estreita é unilateral, e tudo é da mesma mama.
LARGURA_BILATERAL_MM = 250.0


@dataclass
class MamilosMarcados:
    """Os mamilos que o médico marcou neste exame, um por mama.

    Marcado uma vez, vale para todas as lesões daquela mama — e a distância sai sem procurar a
    pele (que é o que leva os ~15 s). A mama de um ponto é o lado do meio do volume em que ele
    está, na direção esquerda-direita do paciente (x); aquisição unilateral tem um lado só.
    """
    centro_x: float = 0.0
    bilateral: bool = False
    pontos: dict = field(default_factory=dict)

    def lado(self, ponto) -> int:
        if not self.bilateral:
            return 0
        return 1 if float(np.asarray(ponto, float)[0]) >= self.centro_x else -1

    def marcar(self, ponto) -> None:
        self.pontos[self.lado(ponto)] = np.asarray(ponto, float)

    def do_lado(self, ponto) -> np.ndarray | None:
        return self.pontos.get(self.lado(ponto))


def marcados_do_volume(afim, shape) -> MamilosMarcados:
    """Onde fica o meio do volume em x, e se a aquisição pega as duas mamas."""
    nz, ny, nx = (int(v) for v in shape)
    cantos = np.array([[k, j, i] for k in (0, nz - 1) for j in (0, ny - 1) for i in (0, nx - 1)])
    x = para_mm(cantos, afim)[:, 0]
    largura = float(x.max() - x.min())
    return MamilosMarcados(float((x.max() + x.min()) / 2.0), largura >= LARGURA_BILATERAL_MM)


@dataclass
class Referencias:
    """As referências do exame, em mm no paciente. Monta-se uma vez por exame."""
    pele: np.ndarray                      # (N, 3) amostra da pele
    pele_fina: np.ndarray                 # (M, 3) pele completa, para a segunda passada
    posterior: np.ndarray                 # (P, 3) limite posterior (parede torácica)
    mamilos: np.ndarray                   # (k, 3) um ponto por lado, do automático
    texto: str = ""
    manual: np.ndarray | None = None      # mamilo marcado à mão: manda sobre o automático
    avisos: list = field(default_factory=list)
    marcados: MamilosMarcados | None = None   # os mamilos marcados no exame, um por mama

    @classmethod
    def so_marcados(cls, marcados: MamilosMarcados) -> "Referencias":
        """Sem pele nem parede: só o mamilo que o médico marcou. Não precisa montar nada."""
        vazio = np.zeros((0, 3))
        return cls(vazio, None, vazio, vazio, marcados=marcados)

    def mamilo_do_lado(self, ponto) -> tuple[np.ndarray | None, bool]:
        """O mamilo que vale para uma lesão, e se ele é do médico (True) ou do programa."""
        if self.manual is not None:
            return np.asarray(self.manual, float), True
        if self.marcados is not None:
            m = self.marcados.do_lado(ponto)
            if m is not None:
                return m, True
        if len(self.mamilos) == 0:
            return None, False
        if len(self.mamilos) == 1:
            return self.mamilos[0], False
        # o mamilo do lado da lesão: o de x (esquerda-direita do paciente) mais próximo
        p = np.asarray(ponto, float)
        k = int(np.argmin([abs(float(m[0]) - float(p[0])) for m in self.mamilos]))
        return self.mamilos[k], False


def mamilos_automaticos(pele_mm: np.ndarray, maximo: int = 2) -> np.ndarray:
    """O ponto mais anterior da pele de cada lado do paciente (menor y de cada metade em x)."""
    if len(pele_mm) == 0:
        return np.zeros((0, 3))
    meio = float(np.median(pele_mm[:, 0]))
    saida = []
    for sel in (pele_mm[:, 0] <= meio, pele_mm[:, 0] > meio):
        lado = pele_mm[sel]
        if len(lado):
            saida.append(lado[int(np.argmin(lado[:, 1]))])
    return np.asarray(saida[:maximo]) if saida else np.zeros((0, 3))


def construir(corpo: np.ndarray, afim, orientation, slice_vec, progresso=None) -> Referencias:
    """Monta as referências do exame a partir da máscara do corpo (tecido acima do limiar).

    Não usa a máscara da mama da 0.55 de propósito: ela corta na "primeira região escura fechada
    indo para trás", e numa RM de mama sagital do acervo isso é uma bolsa de ar de poucos
    milímetros — a imagem **acaba dentro do pulmão** (o FOV não pega as costas), então o pulmão
    encosta na borda e deixa de ser "fechado". Aqui a parede sai do perfil da própria linha.
    """
    fora, _pulmao = ar_e_pulmao(corpo)
    pele_toda_mask = pele_de(corpo, fora)
    if progresso is not None and not progresso(1, 2):
        from ipe.imaging.volume import VolumeError
        raise VolumeError("Cancelado.")
    eixo, sentido = eixo_ap_do_volume(orientation, slice_vec)
    passo_ap = float(np.linalg.norm([afim[3], afim[2], afim[1]][eixo])) if eixo >= 0 else 1.0
    post_mask, pele_mask = parede_e_pele(corpo, pele_toda_mask, eixo, sentido, passo_ap)
    if not pele_mask.any():      # nenhuma linha com pulmão: fica a pele toda, e se declara
        pele_mask = pele_toda_mask
    pele_mm = para_mm(_amostra(pele_mask), afim)
    pele_fina = para_mm(_amostra(pele_mask, 0), afim)
    post_mm = para_mm(_amostra(post_mask), afim)
    # o mamilo sai da pele **toda**: é o ponto mais anterior do corpo, e não depende da parede
    mamilos = mamilos_automaticos(para_mm(_amostra(pele_toda_mask, 0), afim))
    avisos = []
    if eixo < 0:
        avisos.append("Plano oblíquo: não dá para dizer onde está a parede torácica, "
                      "então a distância ao peitoral não sai.")
    if not post_mask.any() and eixo >= 0:
        avisos.append("Não achei o pulmão atrás da mama neste exame: sem ele não dá para dizer "
                      "onde a mama acaba, e a distância ao peitoral não sai.")
    if len(mamilos) == 0:
        avisos.append("Não achei a pele neste exame: o mamilo tem de ser marcado à mão.")
    texto = ("Pele: superfície que encosta no ar de fora, na frente da parede. Peitoral: o tecido "
             "que encosta no pulmão, linha por linha (é a parede torácica; o músculo fica na "
             "frente dela). Mamilo: ponto mais anterior da pele do lado da lesão — clique para "
             "corrigir.")
    if progresso is not None:
        progresso(2, 2)
    return Referencias(pele_mm, pele_fina, post_mm, mamilos, texto, None, avisos)


def superficie_da_lesao(mask: np.ndarray, offset, afim) -> np.ndarray:
    """A superfície da lesão em mm, a partir da máscara recortada e do canto do recorte."""
    m = np.asarray(mask, bool)
    if not m.any():
        return np.zeros((0, 3))
    fora = np.zeros_like(m)
    for eixo in range(3):
        for passo in (1, -1):
            viz = np.roll(m, passo, axis=eixo)
            idx = [slice(None)] * 3
            idx[eixo] = 0 if passo == 1 else -1
            viz[tuple(idx)] = False
            fora |= m & ~viz
    z, y, x = np.nonzero(fora)
    k0, j0, i0 = (int(v) for v in offset)
    return para_mm(np.stack([z + k0, y + j0, x + i0], 1), afim)


def distancias(refs: Referencias, pontos_mm: np.ndarray) -> dict:
    """Os três números, em mm, da borda da lesão até cada referência.

    `pontos_mm`: a **superfície** da lesão (em mm). Da borda, e não do centro, porque é a borda
    que encosta: lesão de 3 cm com centro a 2 cm da pele já toca a pele.
    """
    pontos = np.asarray(pontos_mm, float).reshape(-1, 3)
    if len(pontos) == 0:
        return {}
    centro = pontos.mean(axis=0)
    out: dict = {"centro_mm": centro}
    out["pele"] = menor_distancia(pontos, refs.pele, refs.pele_fina) if len(refs.pele) else float("nan")
    out["posterior"] = menor_distancia(pontos, refs.posterior) if len(refs.posterior) else float("nan")
    mamilo, manual = refs.mamilo_do_lado(centro)
    if mamilo is not None:
        out["mamilo"] = _menor(pontos, np.asarray(mamilo, float).reshape(1, 3))
        out["mamilo_centro"] = float(np.linalg.norm(centro - np.asarray(mamilo, float)))
        out["mamilo_manual"] = bool(manual)
        out["mamilo_ponto"] = np.asarray(mamilo, float)
    return out


def linhas(d: dict) -> list:
    """(rótulo, valor) para a tela, só o que foi medido."""
    if not d:
        return []
    out = []
    if np.isfinite(d.get("pele", float("nan"))):
        out.append(("Distância à pele", f"{d['pele']:.0f} mm"))
    if np.isfinite(d.get("mamilo", float("nan"))):
        quem = "marcado" if d.get("mamilo_manual") else "automático"
        # frase começando por palavra: padrão de tradução que começa com {} sequestra outros textos
        out.append(("Distância ao mamilo",
                    f"borda {d['mamilo']:.0f} mm, centro {d['mamilo_centro']:.0f} mm "
                    f"(ponto {quem})"))
    if np.isfinite(d.get("posterior", float("nan"))):
        out.append(("Distância ao peitoral (parede torácica)", f"{d['posterior']:.0f} mm"))
    return out


# Pedido dele (10/10/2026): "retire a distância até o peitoral e pele. mantenha apenas a distância
# do mamilo, como está". As três continuam calculáveis aqui (a pele é de onde sai o mamilo
# automático), mas a tela, a medida guardada e a captura só levam o mamilo.
TEXTO_MAMILO = ("Mamilo: ponto mais anterior da pele do lado da lesão — clique em \"Marcar o "
                "mamilo\" para corrigir.")


def linhas_mamilo(d: dict) -> list:
    """Só a linha do mamilo, para a tela e para a captura."""
    return [(rot, val) for rot, val in linhas(d) if rot == "Distância ao mamilo"]


def avisos_do_mamilo(refs: "Referencias") -> list:
    """Dos avisos do exame, só os que dizem respeito ao mamilo (os do peitoral saíram)."""
    return [a for a in (refs.avisos or []) if "mamilo" in a]
