"""Densidade mamária: quanto da mama é tecido fibroglandular.

**O que este módulo devolve é um número**: a porcentagem da área da mama ocupada por tecido
fibroglandular (PD%, *percent density*), com as áreas em cm². As faixas a/b/c/d aparecem ao lado,
como **referência**, nunca como veredito — a categoria do BI-RADS 5ª edição é um julgamento do
radiologista, que leva em conta mascaramento e distribuição, não só a fração de área.

A segmentação do tecido denso pode vir de duas fontes, e a tela sempre diz qual foi usada:

* **limiar** (padrão, sempre disponível): limiar de Otsu dentro da mama, depois de tirar fundo,
  pele, músculo peitoral e prótese. É medida clássica, não é rede neural.
* **modelo**: uma rede em ONNX, quando houver uma instalada (`ai/models.py`). Troca só a etapa de
  segmentação; tudo o mais — áreas, faixas, avisos — continua igual.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.imaging.mammo import (
    _dilate, _erode, _maior_componente, chest_wall_side, display_values,
)

log = logging.getLogger(__name__)

LIMIAR = "limiar"
FCM = "fcm"
MODELO = "modelo"

#: como cada método aparece na tela, e a frase de uma linha que diz o que ele é
METODOS = {
    LIMIAR: "Limiar de Otsu",
    FCM: "Agrupamento nebuloso",
    MODELO: "Rede neural",
}

#: faixas clássicas de fração de área, usadas como **referência ao lado do número**
FAIXAS = ((25.0, "a"), (50.0, "b"), (75.0, "c"), (float("inf"), "d"))

#: margem da pele descartada, em mm: a linha da pele é clara e inflaria a densidade
PELE_MM = 3.0


def faixa_de(pd: float) -> str:
    for teto, letra in FAIXAS:
        if pd < teto:
            return letra
    return "d"


@dataclass
class Medida:
    """O resultado de **um** método de segmentação do tecido denso, na mesma mama."""
    metodo: str = LIMIAR
    pd: float = 0.0
    densa_cm2: float = 0.0
    limiar: float = 0.0
    grupos: int = 0                              # quantos grupos o FCM usou nesta imagem
    mascara: object = None

    @property
    def faixa(self) -> str:
        return faixa_de(self.pd)


@dataclass
class Densidade:
    lado: str = ""
    incidencia: str = ""
    pd: float = 0.0
    mama_cm2: float = 0.0
    densa_cm2: float = 0.0
    espessura_mm: float = 0.0
    metodo: str = LIMIAR
    limiar: float = 0.0
    avisos: list = field(default_factory=list)
    sop_uid: str = ""
    serie_uid: str = ""
    caminho: str = ""
    quadro: int = 0                              # o quadro do layout de onde a imagem veio
    forma: tuple = ()                            # (linhas, colunas) da imagem inteira
    #: máscaras na grade reduzida em que a conta foi feita (só quando pedidas) — é o que a tela
    #: desenha por cima da imagem para o médico julgar se o número está errado por causa delas
    mascara_mama: object = None
    mascara_densa: object = None
    #: o resultado de cada método pedido, pelo nome. O `pd`/`densa_cm2` acima são os do primeiro —
    #: a tela compara os outros com ele, e é a discordância entre eles que interessa.
    medidas: dict = field(default_factory=dict)

    @property
    def faixa(self) -> str:
        return faixa_de(self.pd)

    def rotulo(self) -> str:
        return f"{self.lado}{self.incidencia}" if self.lado or self.incidencia else "?"


# --------------------------------------------------------------------- preparo
def espacamento(ds) -> float:
    """Tamanho do pixel em mm.

    Em mamografia 2D costuma vir só em `ImagerPixelSpacing`. Mas a **2D sintética da tomossíntese**
    (a "V-Preview" do GE) é gravada na classe de tomossíntese, e aí o tamanho do pixel está nos
    grupos funcionais compartilhados, não no nível de cima — foi o que fez as áreas saírem zeradas
    nos exames reais do IMEB.
    """
    for chave in ("PixelSpacing", "ImagerPixelSpacing"):
        v = getattr(ds, chave, None)
        try:
            if v is not None and float(v[0]) > 0:
                return float(v[0])
        except Exception:  # noqa: BLE001
            continue
    try:
        medidas = ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
        for chave in ("PixelSpacing", "ImagerPixelSpacing"):
            v = getattr(medidas, chave, None)
            if v is not None and float(v[0]) > 0:
                return float(v[0])
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def _otsu(valores: np.ndarray) -> float:
    """Limiar de Otsu — o que separa em duas classes com a menor variância interna."""
    v = valores[np.isfinite(valores)]
    if v.size < 16:
        return float("inf")
    hist, bordas = np.histogram(v, bins=256)
    p = hist.astype(np.float64) / max(1, hist.sum())
    meio = (bordas[:-1] + bordas[1:]) / 2.0
    w0 = np.cumsum(p)
    w1 = 1.0 - w0
    soma = np.cumsum(p * meio)
    total = soma[-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        m0 = soma / w0
        m1 = (total - soma) / w1
        entre = w0 * w1 * (m0 - m1) ** 2
    entre[~np.isfinite(entre)] = -1.0
    return float(meio[int(np.argmax(entre))])


def _na_janela(ds, bruto: np.ndarray) -> np.ndarray:
    """Valores **como a tela mostra**, aplicando a LUT/janela do próprio arquivo.

    Nos 71 exames reais a `WindowWidth` varia de 165 a 4095 e 67 deles trazem VOI LUT própria:
    são imagens FOR PRESENTATION, cujo mapeamento é decidido **por imagem**. Medir direto no valor
    gravado compara escalas diferentes — e foi o que fez a mesma mama dar números distintos na CC
    e na MLO.
    """
    try:
        from pydicom.pixels import apply_voi_lut
        return np.asarray(apply_voi_lut(bruto, ds), dtype=np.float32)
    except Exception:  # noqa: BLE001 - sem LUT utilizável, vale o valor gravado
        log.debug("densidade: sem VOI LUT utilizável", exc_info=True)
        return bruto.astype(np.float32)


def _tapa_furos(mask: np.ndarray) -> np.ndarray:
    """Tapa os buracos internos: em cada linha, preenche do primeiro ao último pixel da máscara.

    A mama é cheia por linha — do bordo da pele à parede torácica não há vão de verdade. Os vãos
    que aparecem são do limiar, que deixa de fora o tecido adiposo mais escuro.
    """
    cheia = mask.copy()
    for y in np.nonzero(mask.any(axis=1))[0]:
        xs = np.nonzero(mask[y])[0]
        cheia[y, xs[0]:xs[-1] + 1] = True
    return cheia


def mama(arr: np.ndarray, passo_mm: float) -> np.ndarray:
    """Máscara da mama: o tecido, sem fundo, sem a linha da pele e sem letreiro solto.

    O fechamento e o tapa-furos não são enfeite. Nas 2D processadas do GE ("2D_PROC") a mama não
    é um bloco claro: a gordura chega perto do fundo, o limiar recorta a mama em centenas de
    pedaços (525 numa das imagens do acervo) e a erosão da pele, de 3 mm, come o que sobrou — a
    mesma mama dava 108,8 cm² na 2D sintética e 38,4 cm² na 2D processada. Fechar vãos de 2 mm,
    pegar a maior região e encher cada linha resolve, e **não muda** a 2D sintética, onde a mama
    já saía inteira (104,4 cm² antes e depois).
    """
    lo, hi = np.percentile(arr, 1), np.percentile(arr, 99.5)
    if hi <= lo:
        return np.zeros(arr.shape, bool)
    bruta = arr > lo + 0.10 * (hi - lo)
    k2 = max(1, int(round(2.0 / max(passo_mm, 1e-6))))       # fecha vãos de até 2 mm
    bruta = _erode(_dilate(bruta, k2), k2)
    bruta = _maior_componente(bruta, atalho=np.unravel_index(int(np.argmax(arr)), arr.shape))
    bruta = _tapa_furos(bruta)
    k = max(1, int(round(PELE_MM / max(passo_mm, 1e-6))))
    return _erode(bruta, k)


def peitoral(arr: np.ndarray, breast: np.ndarray, lado_tela: str) -> tuple[np.ndarray, str]:
    """Músculo peitoral da MLO, por crescimento a partir do canto da parede torácica.

    Medido nas mamografias reais do IMEB: ajustar uma reta à borda do músculo falha quase sempre
    (a queda de intensidade mais forte de cada linha cai no ruído, não na borda). Crescer a partir
    do canto, acima do percentil **75** dos pixels da mama, deu 9% a 22% da área nas oito MLO
    testadas — que é a faixa anatômica. Os percentis vizinhos entram como segunda e terceira
    tentativa; 85 chega a colapsar para 0,1%, e 60 vaza para 34%.

    **Não reconheceu, não corta** — e diz que não reconheceu, porque peitoral dentro da conta
    infla a densidade e o usuário precisa saber.
    """
    vazio = np.zeros(arr.shape, bool)
    if lado_tela not in ("left", "right") or not breast.any():
        return vazio, "Lado da parede torácica não reconhecido: o peitoral não foi separado."
    from ipe.imaging.segment import _grow
    a = arr if lado_tela == "left" else arr[:, ::-1]         # parede torácica sempre à esquerda
    m = breast if lado_tela == "left" else breast[:, ::-1]
    dentro = a[m]
    # O topo é o da **mama**, não o da imagem: mama que não encosta na borda de cima existe, e
    # procurar a semente na linha 0 simplesmente não acha nada.
    linhas_mama = np.nonzero(m.any(axis=1))[0]
    y0 = int(linhas_mama[0])
    topo = y0 + max(2, int(a.shape[0] * 0.03))
    for q in (75, 70, 80):
        cand = m & (a > np.percentile(dentro, q))
        ys, xs = np.nonzero(cand[y0:topo + 1])
        ys = ys + y0
        if ys.size == 0:
            continue
        i = int(np.argmin(xs))                               # o mais colado na parede torácica
        reg = _grow(cand[None], (0, int(ys[i]), int(xs[i])))[0]
        fr = reg.sum() / max(1, m.sum())
        linhas = np.nonzero(reg.any(axis=1))[0]
        altura = (linhas[-1] - linhas[0]) / a.shape[0] if linhas.size else 0.0
        if 0.02 <= fr <= 0.35 and altura >= 0.15:
            return (reg if lado_tela == "left" else reg[:, ::-1]), ""
    return vazio, "Músculo peitoral não reconhecido: o valor pode estar superestimado."


def denso(arr: np.ndarray, regiao: np.ndarray) -> tuple[np.ndarray, float]:
    """Tecido fibroglandular dentro da região: limiar de Otsu sobre os pixels dela."""
    if not regiao.any():
        return np.zeros(arr.shape, bool), 0.0
    t = _otsu(arr[regiao])
    return (regiao & (arr > t)), float(t)


# ------------------------------------------------- segundo método: FCM adaptativo
def _fcm(centros: np.ndarray, pesos: np.ndarray, k: int, m: float = 2.0,
         voltas: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """Fuzzy c-means em uma dimensão, sobre o **histograma** (não sobre cada pixel).

    Agrupar 2 milhões de pixels custaria segundos; agrupar 256 valores com o peso de cada um dá o
    mesmo resultado, porque a conta só olha a intensidade. `m` é o expoente de nebulosidade — 2,0 é
    o valor clássico, o mesmo que o LIBRA usa.
    """
    c = np.linspace(centros.min(), centros.max(), k) if k > 1 else centros.mean(keepdims=True)
    c = np.asarray(c, dtype=np.float64)
    u = np.zeros((k, centros.size))
    for _ in range(voltas):
        d = np.abs(centros[None, :] - c[:, None])
        d = np.maximum(d, 1e-9)
        inv = d ** (-2.0 / (m - 1.0))
        u = inv / inv.sum(axis=0, keepdims=True)
        w = (u ** m) * pesos[None, :]
        novo_c = (w * centros[None, :]).sum(axis=1) / np.maximum(w.sum(axis=1), 1e-12)
        if np.max(np.abs(novo_c - c)) < 1e-6:
            c = novo_c
            break
        c = novo_c
    ordem = np.argsort(c)
    return c[ordem], u[ordem]


def _xie_beni(centros: np.ndarray, pesos: np.ndarray, c: np.ndarray, u: np.ndarray,
              m: float = 2.0) -> float:
    """Índice de Xie-Beni: quanto menor, melhor o agrupamento. Serve para escolher o `k`."""
    if c.size < 2:
        return float("inf")
    d2 = (centros[None, :] - c[:, None]) ** 2
    compacidade = float(((u ** m) * pesos[None, :] * d2).sum())
    separacao = float(np.min(np.diff(c) ** 2))
    n = float(pesos.sum())
    if separacao <= 0 or n <= 0:
        return float("inf")
    return compacidade / (n * separacao)


def denso_fcm(arr: np.ndarray, regiao: np.ndarray,
              grupos: tuple = (2,)) -> tuple[np.ndarray, float, int]:
    """Tecido denso por **agrupamento nebuloso** (fuzzy c-means), no espírito do LIBRA.

    Separa as intensidades da mama em `k` grupos e chama de denso o **grupo mais claro**. Com
    `k = 2` é a mesma pergunta que o limiar de Otsu, por um critério diferente: Otsu maximiza a
    variância *entre* as duas classes, com cada pixel inteiro de um lado; o FCM minimiza a
    distância *dentro* das classes, com o pixel pertencendo às duas em graus.

    **Medido no acervo, os dois quase não se distinguem**: nas 60 mamografias do IMEB em que o
    FCM usou 2 grupos, r = 0,994, diferença média de 0,7 ponto percentual, e só **1 imagem em 60**
    passou de 5 pontos. Ou seja: *não* é uma segunda opinião de verdade — é a mesma medida por
    outro caminho. O que ele entrega é **precisão, não acerto**: onde os dois batem, a segmentação
    está estável; onde se afastam (a tal imagem em 60), a imagem é difícil e o número é frágil.
    Opinião de outra natureza só vem de fora da área clara — a rede da NYU, em `ai/densidade_nyu.py`.

    **Não é o LIBRA.** O original escolhe quais grupos são densos com uma máquina de vetores de
    suporte treinada; aqui a regra é fixa e escrita: o grupo mais claro.

    **Por que `k` fixo em 2, e não adaptativo.** Escolher `k` por imagem pelo índice de Xie-Beni
    (`grupos=(2, 3, 4, 5)`) foi medido no acervo e **reprovado**: em 74 das 91 imagens ele escolhia
    2, e nas outras saltava para 4 ou 5, onde só o grupo mais claro sobra e o PD% cai de 30 a 40
    pontos percentuais. O método passava a alternar entre **duas definições diferentes de denso**,
    e a reprodutibilidade CC × MLO caía de 0,91 para 0,78. Medida que muda de definição no meio do
    caminho não é medida.

    Devolve (máscara, limiar em valor de pixel, k usado).
    """
    if not regiao.any():
        return np.zeros(arr.shape, bool), 0.0, 0
    dentro = arr[regiao]
    dentro = dentro[np.isfinite(dentro)]
    if dentro.size < 64:
        return np.zeros(arr.shape, bool), 0.0, 0
    pesos, bordas = np.histogram(dentro, bins=256)
    centros = (bordas[:-1] + bordas[1:]) / 2.0
    usa = pesos > 0
    centros, pesos = centros[usa], pesos[usa].astype(np.float64)
    if centros.size < 4:
        return denso(arr, regiao) + (1,)

    melhor = None
    for k in grupos:
        if k > centros.size:
            break
        c, u = _fcm(centros, pesos, k)
        if np.min(np.diff(c)) <= 0:                      # grupos colados: k alto demais
            continue
        v = _xie_beni(centros, pesos, c, u)
        if melhor is None or v < melhor[0]:
            melhor = (v, c, u, k)
    if melhor is None:
        return denso(arr, regiao) + (1,)
    _v, c, u, k = melhor

    # a fronteira é onde a pertinência ao grupo mais claro passa a mandar
    mais_claro = u[-1] >= u.max(axis=0) - 1e-12
    if not mais_claro.any():
        return denso(arr, regiao) + (k,)
    t = float(centros[np.argmax(mais_claro)])
    return (regiao & (arr > t)), t, k


# --------------------------------------------------------------------- medida
def medir(ds, modelo=None, passo: int = 0, mascaras: bool = False,
          metodos: tuple = (LIMIAR,)) -> Densidade:
    """Mede uma imagem. `modelo` (opcional) substitui só a segmentação do tecido denso.

    Com `mascaras`, guarda a máscara da mama e a do tecido denso na grade reduzida em que a
    conta foi feita. Elas custam memória, então só saem quando alguém vai desenhá-las.
    """
    # lado e incidência saem da mesma leitura que a seleção usa (`atributos`), e não das tags de
    # cima: na 2D sintética da tomossíntese elas não existem lá, e a medida saía sem lado — o que
    # impedia até de juntar as incidências por mama.
    a = atributos(ds)
    r = Densidade(lado=a["lado"], incidencia=a["vista"],
                  sop_uid=str(getattr(ds, "SOPInstanceUID", "") or ""))
    # A conta roda em qualquer imagem 2D, mas só quer dizer alguma coisa em mamografia. Recusar
    # seria adivinhar pelo usuário; medir calado seria pior. Então mede e diz o que está medindo.
    if a["modalidade"].upper() != "MG":
        r.avisos.append("Esta imagem não é mamografia: o número não é densidade mamária.")
    try:
        bruto = ds.pixel_array
    except Exception as e:  # noqa: BLE001
        r.avisos.append("Imagem ilegível.")
        log.debug("densidade: %s", e)
        return r
    if bruto.ndim != 2:
        r.avisos.append("Só vale para imagem 2D: tomossíntese não entra nesta conta.")
        return r
    mm = espacamento(ds)
    if mm <= 0:
        r.avisos.append("Sem tamanho de pixel no arquivo: as áreas em cm² não saem.")
    passo = passo or max(1, max(bruto.shape) // 1024)
    arr = display_values(_na_janela(ds, bruto[::passo, ::passo]),
                         str(getattr(ds, "PhotometricInterpretation", "")) == "MONOCHROME1")
    passo_mm = mm * passo
    r.espessura_mm = float(getattr(ds, "BodyPartThickness", 0) or 0)

    regiao = mama(arr, passo_mm or 0.3)
    if not regiao.any():
        r.avisos.append("Não achei a mama na imagem.")
        return r

    # Prótese: **o arquivo diz** (0028,1300). Nos 71 exames reais do IMEB a tag veio preenchida em
    # todos (59 NO, 12 YES), enquanto o detector por textura acusava 16 — ou seja, adivinhava a
    # mais. Adivinhar aqui é grave: prótese falsa tira um pedaço da mama e estraga a conta.
    declarada = str(getattr(ds, "BreastImplantPresent", "") or "").upper()
    prot = None
    if declarada != "NO":
        from ipe.imaging.mammo import implant_mask
        try:
            prot = implant_mask(arr, seed=None)
        except Exception:  # noqa: BLE001
            prot = None
    if declarada == "YES" and (prot is None or not prot.any()):
        r.avisos.append("O arquivo diz que há prótese, mas não achei o contorno dela.")
    if prot is not None and prot.any() and prot.sum() > 0.05 * regiao.sum():
        regiao = regiao & ~_dilate(prot, 2)
        r.avisos.append("Prótese na imagem: densidade medida só no tecido em volta, e com cuidado.")

    if r.incidencia.upper() in ("MLO", "SIO", "LMO"):
        tri, aviso = peitoral(arr, regiao, chest_wall_side(arr))
        if tri.any():
            regiao = regiao & ~tri
        if aviso:
            r.avisos.append(aviso)

    area_px = (passo_mm / 10.0) ** 2 if passo_mm else 0.0
    r.mama_cm2 = float(regiao.sum() * area_px)

    pedidos = tuple(metodos) if modelo is None else (MODELO,) + tuple(
        m for m in metodos if m != MODELO)
    for nome in pedidos:
        med = Medida(metodo=nome)
        if nome == MODELO:
            try:
                med.mascara = modelo(arr, regiao)
            except Exception as e:  # noqa: BLE001
                r.avisos.append("O modelo falhou; medi pelo limiar.")
                log.debug("modelo de densidade: %s", e)
                med = Medida(metodo=LIMIAR)
                med.mascara, med.limiar = denso(arr, regiao)
        elif nome == FCM:
            med.mascara, med.limiar, med.grupos = denso_fcm(arr, regiao)
        else:
            med.metodo = LIMIAR
            med.mascara, med.limiar = denso(arr, regiao)
        dentro = med.mascara & regiao
        med.densa_cm2 = float(dentro.sum() * area_px)
        med.pd = float(100.0 * dentro.sum() / max(1, regiao.sum()))
        if not mascaras:
            med.mascara = None
        r.medidas[med.metodo] = med

    principal = r.medidas.get(pedidos[0]) or next(iter(r.medidas.values()))
    r.metodo, r.pd, r.densa_cm2, r.limiar = (principal.metodo, principal.pd,
                                             principal.densa_cm2, principal.limiar)
    mask = principal.mascara if principal.mascara is not None else np.zeros(arr.shape, bool)
    if mascaras:
        r.mascara_mama, r.mascara_densa = regiao, (mask & regiao)
        # a conta roda numa grade reduzida: quem for desenhar precisa saber sobre que imagem
        r.forma = (int(bruto.shape[0]), int(bruto.shape[1]))
    return r


def atributos(ds) -> dict:
    """O que a seleção precisa saber sobre **esta** imagem, lido do arquivo.

    Fica aqui, e não no motor da seleção, porque é conhecimento de mamografia: a incidência pode
    estar em `ViewPosition`, na `ViewCodeSequence` ou só no texto da descrição, e é `mammo` quem
    sabe ler os três.
    """
    from ipe.imaging import mammo as M
    textos = [str(getattr(ds, c, "") or "") for c in ("ViewPosition", "SeriesDescription",
                                                      "ProtocolName", "ImageComments")]
    codigo = ds.get("ViewCodeSequence", None)
    if codigo:
        try:
            textos.append(str(codigo[0].CodeMeaning))
        except Exception:  # noqa: BLE001
            pass
    vista = M._view_of([t.upper() for t in textos if t])
    # a 2D sintética da tomo guarda o lado na Frame Anatomy Sequence, como os volumes (0.29)
    lat = str(getattr(ds, "ImageLaterality", "") or "")
    if not lat:
        try:
            lat = str(ds.SharedFunctionalGroupsSequence[0].FrameAnatomySequence[0].FrameLaterality)
        except Exception:  # noqa: BLE001
            lat = ""
    lado = M._side_of(lat, [t.upper() for t in textos if t])
    apresentacao = str(getattr(ds, "PresentationIntentType", "") or "")
    return {
        "modalidade": str(getattr(ds, "Modality", "") or ""),
        "descricao": str(getattr(ds, "SeriesDescription", "") or ""),
        "vista": vista,
        "lado": lado,
        "parte": str(getattr(ds, "BodyPartExamined", "") or ""),
        "aparelho": " ".join(x for x in (str(getattr(ds, "Manufacturer", "") or ""),
                                         str(getattr(ds, "ManufacturerModelName", "") or "")) if x),
        "estacao": str(getattr(ds, "StationName", "") or ""),
        "classe": str(getattr(ds, "SOPClassUID", "") or ""),
        "quadros": str(int(getattr(ds, "NumberOfFrames", 1) or 1)),
        "apresentacao": apresentacao,
    }


def por_mama(medidas: list) -> dict:
    """Um valor por mama: a média das incidências que deram certo."""
    saida: dict[str, float] = {}
    for lado in ("R", "L"):
        vals = [m.pd for m in medidas if m.lado == lado and m.mama_cm2 > 0]
        if vals:
            saida[lado] = float(sum(vals) / len(vals))
    return saida


def do_exame(medidas: list) -> float:
    """O valor do exame: a **mama mais densa** — é ela que governa o laudo."""
    m = por_mama(medidas)
    return max(m.values()) if m else 0.0


def contorno(mask, k: int = 2):
    """Só a borda da máscara, com `k` pixels de espessura.

    A borda da mama se desenha como linha; preenchida, ela esconderia justamente o tecido que o
    médico precisa ver para julgar se a máscara está certa.
    """
    m = np.asarray(mask, bool)
    return m & ~_erode(m, k)


# ---------------------------------------------------------------- várias imagens
def medir_imagens(caminhos, modelo=None, stop=None, progresso=None,
                  mascaras: bool = False, metodos: tuple = (LIMIAR,)) -> list:
    """Mede **as imagens que lhe derem** — quem escolhe é quem chama.

    A escolha por regra saiu de propósito: na tela, o que vale é o que o médico pôs no quadro.
    A imagem que não abre entra na lista **com aviso**, porque sumir em silêncio seria pior.
    """
    import pydicom

    saida: list = []
    total = len(caminhos)
    for i, caminho in enumerate(caminhos):
        if stop is not None and stop.is_set():
            break
        if progresso is not None:
            progresso(i, total)
        try:
            ds = pydicom.dcmread(str(caminho), force=True)
        except Exception:  # noqa: BLE001
            log.debug("densidade: não li %s", caminho, exc_info=True)
            r = Densidade(caminho=str(caminho))
            r.avisos.append("Imagem ilegível.")
            saida.append(r)
            continue
        r = medir(ds, modelo=modelo, mascaras=mascaras, metodos=metodos)
        r.caminho = str(caminho)
        saida.append(r)
    if progresso is not None:
        progresso(total, total)
    return saida
