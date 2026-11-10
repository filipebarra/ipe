"""Tecido fibroglandular (FGT) e realce de fundo (BPE) da RM de mama (0.100.7).

O que faltava na linha da dinâmica (`claude/rm-mama-dinamica.md`, item 1): a máscara da mama (0.55) corta a
parede torácica, mas mantém gordura, pele, vasos e o músculo peitoral — o realce de fundo medido nela servia para
comparar o mesmo serviço ao longo do tempo, não para virar categoria. Aqui a gordura sai.

De onde vem o contraste entre gordura e glândula, em ordem de preferência:

1. **Dixon** (VIBRANT FLEX, IDEAL: séries "WATER:" e "FAT:" da mesma aquisição): fração de gordura
   F/(F+W) < 0,5 é glândula. Não depende de bobina nem de limiar.
2. **T1 sem saturação de gordura** ("A T1", "Axi T1", "Ax T1 FSE" do protocolo dele): a gordura é clara e a
   glândula escura. É o padrão das medidas de FGT na literatura.
3. **Pré-contraste da dinâmica com saturação de gordura** (VIBRANT): a gordura é escura e a glândula
   intermediária — o contraste é pequeno; o resultado vem marcado como menos confiável.

Passos (T1 sem saturação):
- máscara da mama de `mama_mascara.mascara_da_mama` (até a parede, pelo pulmão);
- tira a **pele**: 3 mm a partir do ar de fora, no plano;
- **campo da bobina**: a gordura é o tecido de referência — a intensidade dela, suavizada (σ 20 mm), é o campo;
  divide-se a imagem por ele (duas voltas), o que tira o degradê das bobinas de mama;
- **limiar de Otsu** em cada mama (direita e esquerda separadas, pela linha média do corpo);
- tira o **peitoral**: em cada linha, indo da parede para a frente, a faixa de "glândula" encostada na parede
  até a primeira gordura (até 25 mm) é músculo (e costela), não mama;
- abre (1 voxel) para tirar ruído solto.

O FGT é o volume de glândula sobre o volume da mama (a máscara sem pele e sem peitoral), por lado. As faixas
a/b/c/d (< 25, 25–50, 50–75, ≥ 75%) vêm **como referência**: a categoria do BI-RADS de RM é visual.

O realce de fundo (BPE) é medido **só dentro do FGT**, na 1ª pós-contraste: o realce relativo
(pós − pré)/pré, e a fração do FGT que realça mais que 20%. A categoria sugerida segue a definição do BI-RADS
(proporção do FGT que realça: < 25% mínimo, 25–50% leve, 50–75% moderado, > 75% acentuado) e também é
**sugestão**: o médico decide.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

PELE_MM = 3.0
CAMPO_SIGMA_MM = 20.0
PEITORAL_MAX_MM = 25.0
IMPLANTE_ML = 40.0           # bloco escuro, liso e homogêneo maior que isso é implante, não glândula
IMPLANTE_CV = 0.12           # variação do sinal no miolo do bloco (desvio / média) abaixo disso
IMPLANTE_MIOLO_MM = 5.0
IMPLANTE_RAIO_MM = 18.0      # e grosso: o peitoral (e o serrátil), também lisos, são lâminas — no acervo, até 16 mm aqui
REALCE_LIMIAR = 20.0         # % de realce para "realça" no BPE
FAIXAS_FGT = ((25.0, "a"), (50.0, "b"), (75.0, "c"), (101.0, "d"))
FAIXAS_BPE = ((25.0, "minimo"), (50.0, "leve"), (75.0, "moderado"), (101.0, "acentuado"))
NOMES_FGT = {"a": "quase toda gordura", "b": "tecido fibroglandular esparso",
             "c": "tecido fibroglandular heterogêneo", "d": "tecido fibroglandular extremo"}
NOMES_BPE = {"minimo": "mínimo", "leve": "leve", "moderado": "moderado", "acentuado": "acentuado"}

FONTE_DIXON, FONTE_T1, FONTE_FS = "dixon", "t1", "fs"


def faixa(pct: float, faixas) -> str:
    for lim, nome in faixas:
        if pct < lim:
            return nome
    return faixas[-1][1]


def otsu(valores: np.ndarray, bins: int = 256) -> float:
    v = np.asarray(valores, np.float64)
    v = v[np.isfinite(v)]
    if v.size < 10:
        return float(np.median(v)) if v.size else 0.0
    lo, hi = np.percentile(v, [0.5, 99.5])
    if hi <= lo:
        return float(lo)
    h, b = np.histogram(np.clip(v, lo, hi), bins=bins, range=(lo, hi))
    c = (b[:-1] + b[1:]) / 2
    w0 = np.cumsum(h)
    w1 = w0[-1] - w0
    m0 = np.cumsum(h * c)
    mu0 = m0 / np.maximum(w0, 1)
    mu1 = (m0[-1] - m0) / np.maximum(w1, 1)
    var = w0 * w1 * (mu0 - mu1) ** 2
    return float(c[int(np.argmax(var[:-1]))])


def _gauss(img: np.ndarray, sigma_px: tuple) -> np.ndarray:
    from ipe.imaging.morfologia import suavizar_reduzido
    return suavizar_reduzido(img, sigma_px)


def corrigir_campo(img: np.ndarray, mascara: np.ndarray, referencia: np.ndarray, voxel_mm: tuple,
                   sigma_mm: float = CAMPO_SIGMA_MM) -> np.ndarray:
    """Divide a imagem pelo campo da bobina, estimado pela intensidade suavizada do tecido de referência (a
    gordura no T1). Convolução normalizada: só o tecido de referência entra na média."""
    sig = tuple(max(0.5, sigma_mm / max(float(v), 1e-3)) for v in voxel_mm)
    sig = (min(sig[0], 3.0),) + sig[1:]          # entre cortes o campo muda pouco e os cortes são grossos
    w = (referencia & mascara).astype(np.float32)
    num = _gauss(img.astype(np.float32) * w, sig)
    den = _gauss(w, sig)
    campo = np.where(den > 1e-3, num / np.maximum(den, 1e-6), np.nan)
    ref = np.nanmedian(campo[mascara]) if np.any(mascara) else 1.0
    campo = np.where(np.isfinite(campo), campo, ref)
    return img / np.maximum(campo / max(ref, 1e-6), 0.05)


def tirar_pele(mascara: np.ndarray, corpo: np.ndarray, pixel_mm: tuple, pele_mm: float = PELE_MM) -> np.ndarray:
    """Tira a faixa de `pele_mm` a partir do ar de fora, corte a corte."""
    from ipe.imaging.morfologia import distancia
    return mascara & (distancia(~np.asarray(corpo, bool), pixel_mm, pele_mm + 1.0) > pele_mm)


def eixo_esquerda(orientation, slice_vec) -> tuple[int, int]:
    """Qual eixo do volume `(corte, linha, coluna)` anda para a esquerda da paciente (+x no DICOM) e em que
    sentido: (eixo, +1 quando o índice cresce para a esquerda)."""
    o = np.asarray(orientation, float).ravel()
    s = np.asarray(slice_vec, float).ravel() if slice_vec is not None else np.cross(o[:3], o[3:])
    cand = [(abs(o[0]), 2, o[0]), (abs(o[3]), 1, o[3]), (abs(s[0]), 0, s[0])]
    _, eixo, v = max(cand)
    return eixo, (1 if v > 0 else -1)


def linha_media(perfil: np.ndarray) -> int:
    """A linha média num perfil esquerda-direita (quantos voxels de mama em cada posição): o vale entre as mamas,
    procurado no miolo da extensão ocupada. A mediana dos voxels cairia dentro da mama maior quando as duas têm
    tamanhos diferentes (um implante tirado, uma mastectomia)."""
    idx = np.flatnonzero(perfil)
    if not idx.size:
        return perfil.size // 2
    lo, hi = int(idx[0]), int(idx[-1])
    a, b = lo + int(0.3 * (hi - lo)), lo + int(0.7 * (hi - lo)) + 1
    janela = perfil[a:b].astype(float)
    centro = (lo + hi) / 2.0
    custo = janela + 1e-3 * np.abs(np.arange(a, b) - centro)     # empate: o mais perto do centro
    return int(a + np.argmin(custo))


def lados(mascara: np.ndarray, eixo_lr: int, sentido: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """(direita, esquerda) da paciente, pela linha média do corpo: a mediana da posição esquerda-direita da
    máscara (corte a corte; no sagital, a mediana dos cortes)."""
    dire, esq = np.zeros_like(mascara), np.zeros_like(mascara)
    if eixo_lr == 0:
        ks = np.nonzero(mascara.any(axis=(1, 2)))[0]
        if ks.size:
            meio = int(np.median(ks))
            baixo, alto = mascara.copy(), mascara.copy()
            baixo[meio:] = False
            alto[:meio] = False
            return (baixo, alto) if sentido > 0 else (alto, baixo)
        return dire, esq
    for k in range(mascara.shape[0]):
        sl = mascara[k]
        if not sl.any():
            continue
        meio = linha_media(sl.sum(axis=0 if eixo_lr == 2 else 1))
        b, a = np.zeros_like(sl), np.zeros_like(sl)
        if eixo_lr == 2:
            b[:, :meio], a[:, meio:] = sl[:, :meio], sl[:, meio:]
        else:
            b[:meio, :], a[meio:, :] = sl[:meio, :], sl[meio:, :]
        # índice baixo = direita quando o índice cresce para a esquerda
        if sentido > 0:
            dire[k], esq[k] = b, a
        else:
            dire[k], esq[k] = a, b
    return dire, esq


def _vista(a: np.ndarray, eixo: int, sentido: int) -> np.ndarray:
    """O volume com as colunas crescendo para trás (a convenção de `mama_mascara`)."""
    v = np.swapaxes(a, 1, 2) if eixo == 0 else a
    return v[:, :, ::-1] if sentido < 0 else v


def _da_vista(v: np.ndarray, eixo: int, sentido: int) -> np.ndarray:
    if sentido < 0:
        v = v[:, :, ::-1]
    return np.swapaxes(v, 1, 2) if eixo == 0 else v


def corte_coronal(limites: np.ndarray, mama_vista: np.ndarray) -> np.ndarray:
    """Na vista (cortes, linhas, colunas para trás): em cada corte e lado (metades pelo centro da mama), tudo atrás da
    coluna mais anterior do pulmão sai. O pulmão encurva para trás nos lados, e a máscara que o segue levaria a
    parede lateral do tórax junto."""
    nk, nl, nc = mama_vista.shape
    plano = np.zeros_like(mama_vista, dtype=bool)
    cols = np.arange(nc)[None, :]
    for k in range(nk):
        lim = limites[k]
        if (lim < 0).all():
            plano[k] = True
            continue
        meio = linha_media(mama_vista[k].sum(axis=1))
        corte = np.empty(nl, np.int32)
        for a, b in ((0, meio), (meio, nl)):
            validos = lim[a:b][lim[a:b] >= 0]
            corte[a:b] = int(validos.min()) if validos.size else nc
        plano[k] = cols < corte[:, None]
    return plano


def musculo_no_fundo(escuro: np.ndarray, mama: np.ndarray, eixo_ap: int, sentido: int, pixel_mm=(1.0, 1.0),
                     max_mm: float = PEITORAL_MAX_MM, pontes: int = 2) -> np.ndarray:
    """Os pedaços de "escuro" que encostam no fundo da mama (o último voxel de cada linha anterior-posterior), até
    `max_mm` do fundo. Antes de ligar os pedaços, uma erosão de `pontes` voxels no plano corta as pontes finas entre
    a glândula e o músculo; e o limite de distância segura a glândula que ainda assim ficou ligada: só a parte dela
    encostada na parede sai."""
    from ipe.imaging.estruturas import rotular
    from ipe.imaging.morfologia import dilatar, distancia, erodir
    # só o último voxel de cada linha: a borda de trás de um buraco dentro da mama (vaso, cisto) não é fundo
    m = np.moveaxis(mama, eixo_ap, -1)
    if sentido < 0:
        m = m[..., ::-1]
    n = m.shape[-1]
    tem = m.any(axis=-1)
    ultimo = n - 1 - np.argmax(m[..., ::-1], axis=-1)
    f = np.zeros_like(m)
    idx = np.nonzero(tem)
    f[idx + (ultimo[idx],)] = True
    if sentido < 0:
        f = f[..., ::-1]
    fundo = np.moveaxis(f, -1, eixo_ap)
    nucleo = erodir(escuro, pontes) if pontes else escuro
    toca_fundo = dilatar(fundo, pontes + 1)
    rot, n = rotular(nucleo)
    if not n:
        return np.zeros_like(escuro)
    ids = np.unique(rot[toca_fundo & nucleo])
    ids = ids[ids > 0]
    musc = np.isin(rot, ids)
    if pontes:
        musc = dilatar(musc, pontes) & escuro
    musc &= distancia(fundo, pixel_mm, max_mm + 1.0) <= max_mm
    # o escuro fino encostado no fundo (a erosão apagou) também é parede
    return musc | (escuro & dilatar(fundo, 1))


def achar_implante(escuro: np.ndarray, img: np.ndarray, voxel_mm: tuple, min_ml: float = IMPLANTE_ML,
                   max_cv: float = IMPLANTE_CV, miolo_mm: float = IMPLANTE_MIOLO_MM) -> tuple[np.ndarray, list]:
    """O implante é um bloco escuro grande e homogêneo; a glândula, mesmo densa, tem gordura entremeada. Erode
    `miolo_mm` no plano (o que sobra de uma glândula são ilhas pequenas), liga em 3D e fica com os blocos de mais de
    `min_ml` cujo sinal no miolo varia pouco e que são grossos (cabe um círculo de `IMPLANTE_RAIO_MM` dentro, num
    corte) — o músculo também é liso, mas é lâmina. Devolve (máscara do implante, [(mL, cv) de cada bloco grande])."""
    from ipe.imaging.estruturas import rotular
    from ipe.imaging.morfologia import dilatar, distancia, erodir
    it = max(1, int(round(miolo_mm / max(min(voxel_mm[1:]), 1e-3))))
    miolo = erodir(escuro, it)
    rot, n = rotular(miolo)
    out = np.zeros_like(escuro)
    diag = []
    if not n:
        return out, diag
    voxel_ml = float(np.prod(voxel_mm)) / 1000.0
    tam = np.bincount(rot.ravel())
    for i in np.flatnonzero(tam * voxel_ml >= min_ml / 4):
        if i == 0:
            continue
        sel = rot == i
        v = img[sel]
        cv = float(np.std(v) / max(float(np.mean(v)), 1e-6))
        cheio = dilatar(sel, it + 1) & escuro
        ml = float(cheio.sum()) * voxel_ml
        ks, js, is_ = (np.flatnonzero(cheio.any(axis=ax)) for ax in ((1, 2), (0, 2), (0, 1)))
        caixa = np.pad(cheio[ks[0]:ks[-1] + 1, js[0]:js[-1] + 1, is_[0]:is_[-1] + 1], ((0, 0), (1, 1), (1, 1)))
        raio = float(distancia(~caixa, voxel_mm[1:], IMPLANTE_RAIO_MM + 1.0).max())
        diag.append((round(ml), round(cv, 3), round(raio)))
        if ml >= min_ml and cv <= max_cv and raio >= IMPLANTE_RAIO_MM:
            out |= cheio
    return out, diag


def cortar_atras(mama: np.ndarray, musc: np.ndarray, eixo_ap: int, sentido: int) -> np.ndarray:
    """Em cada linha anterior-posterior, o que fica na frente do primeiro voxel de músculo (a linha inteira, se
    não há músculo nela)."""
    m = np.moveaxis(musc, eixo_ap, -1)
    if sentido < 0:
        m = m[..., ::-1]
    n = m.shape[-1]
    tem = m.any(axis=-1)
    primeiro = np.where(tem, np.argmax(m, axis=-1), n)
    frente = np.arange(n)[None, None, :] < primeiro[..., None]
    if sentido < 0:
        frente = frente[..., ::-1]
    return np.moveaxis(frente, -1, eixo_ap)


@dataclass
class Lado:
    nome: str
    mama_ml: float = 0.0
    fgt_ml: float = 0.0
    fgt_pct: float = 0.0
    faixa: str = ""
    bpe_realce_medio: float | None = None
    bpe_realce_mediana: float | None = None
    bpe_pct: float | None = None             # % do FGT que realça > REALCE_LIMIAR
    bpe_faixa: str = ""


@dataclass
class ResultadoFGT:
    fonte: str = ""
    serie: str = ""
    lados: list[Lado] = field(default_factory=list)
    total: Lado = field(default_factory=lambda: Lado("total"))
    limiar: float = 0.0
    peitoral_cheio: float = 0.0
    implante_ml: float = 0.0
    diag: list = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    texto_metodo: str = ""
    fgt: np.ndarray | None = None
    mama: np.ndarray | None = None
    eixo_lr: int = 2
    sentido_lr: int = 1


def _medir_lado(nome: str, mama: np.ndarray, fgt: np.ndarray, voxel_ml: float) -> Lado:
    lado = Lado(nome)
    nm, nf = int(mama.sum()), int((fgt & mama).sum())
    lado.mama_ml, lado.fgt_ml = nm * voxel_ml, nf * voxel_ml
    lado.fgt_pct = 100.0 * nf / nm if nm else 0.0
    lado.faixa = faixa(lado.fgt_pct, FAIXAS_FGT) if nm else ""
    return lado


def segmentar(vol: np.ndarray, orientation, voxel_mm: tuple, fonte: str = FONTE_T1, gordura: np.ndarray | None = None,
              agua: np.ndarray | None = None, slice_vec=None) -> ResultadoFGT:
    """FGT no volume `(cortes, linhas, colunas)`. `voxel_mm` = (entre cortes, linha, coluna).
    `fonte`: FONTE_T1 (gordura clara), FONTE_FS (gordura escura) ou FONTE_DIXON (passar `gordura` e `agua`)."""
    from ipe.imaging import mama_mascara as MM
    r = ResultadoFGT(fonte=fonte)
    eixo_lr, sentido_lr = eixo_esquerda(orientation, slice_vec)
    base = (np.asarray(agua, np.float32) + np.asarray(gordura, np.float32)) if fonte == FONTE_DIXON else np.asarray(vol, np.float32)
    ref = float(np.percentile(base, 99.5)) if base.size else 1.0
    mama, info = MM.mascara_da_mama(base, ref, orientation, voxel_mm[1:])
    # o que a mama cerca é mama: glândula muito escura (do lado fraco da bobina) cairia abaixo do limiar do corpo
    from ipe.imaging.morfologia import abrir, preencher_buracos
    mama = preencher_buracos(mama) if mama.any() else mama
    mama_inteira = mama.copy()
    if info.get("modo") != MM.MODO_PAREDE:
        r.avisos.append("Não achei a parede torácica (pulmão): a máscara pode ter tórax.")
    corpo = base >= ref * 0.10
    mama = tirar_pele(mama, corpo, voxel_mm[1:])
    if fonte == FONTE_DIXON:
        ff = np.asarray(gordura, np.float32) / np.maximum(np.asarray(gordura, np.float32) + np.asarray(agua, np.float32), 1e-6)
        glandula = mama & (ff < 0.5)
        r.limiar = 0.5
    else:
        img = base
        # 1ª volta: Otsu na mama inteira dá a gordura para o campo; 2ª volta já no corrigido
        for _ in range(2):
            t = otsu(img[mama])
            ref_tecido = (img > t) if fonte == FONTE_T1 else (img < t)
            img = corrigir_campo(img, mama, ref_tecido & mama, voxel_mm)
        glandula = np.zeros_like(mama)
        limiares = []
        for parte in lados(mama, eixo_lr, sentido_lr):
            if parte.sum() < 100:
                continue
            t = otsu(img[parte])
            limiares.append(t)
            glandula |= parte & ((img < t) if fonte == FONTE_T1 else (img > t))
        r.limiar = float(np.mean(limiares)) if limiares else 0.0
        if fonte == FONTE_FS:
            r.avisos.append("Sem T1 sem saturação nem Dixon: separado no pré-contraste com saturação de gordura, "
                            "onde o contraste entre gordura e glândula é pequeno — número menos confiável.")
    if fonte != FONTE_DIXON:
        implante, r.diag = achar_implante(glandula, img, voxel_mm)
        if implante.any():
            r.implante_ml = float(implante.sum()) * float(np.prod(voxel_mm)) / 1000.0
            mama &= ~implante
            glandula &= ~implante
            r.avisos.append(f"Implante achado ({r.implante_ml:.0f} mL): fora da conta — a porcentagem é do tecido "
                            "da mama sem o implante.")
    eixo, sentido = MM.eixo_anterior_posterior(orientation)
    if eixo >= 0 and info.get("limites") is not None:
        eixo_vol = 2 if eixo == 1 else 1
        # 1) atrás do ponto mais anterior do pulmão de cada lado é parede lateral (serrátil, grande dorsal, costelas),
        #    não mama; 2) o "escuro" que encosta no fundo do que sobrou é músculo (peitoral, intercostal) — e em cada
        #    linha a mama acaba na frente dele. A glândula fica cercada de gordura e não encosta no fundo.
        plano = corte_coronal(info["limites"], _vista(mama_inteira, eixo, sentido))
        mama &= _da_vista(plano, eixo, sentido)
        musc = musculo_no_fundo(glandula & mama, mama, eixo_vol, sentido, voxel_mm[1:])
        frente = cortar_atras(mama, musc, eixo_vol, sentido)
        r.peitoral_cheio = float((glandula & musc).sum() / max(int((glandula & mama).sum()), 1))
        mama &= frente & ~musc
        glandula &= mama
    # abertura só no plano: entre cortes de 2–3 mm os fios de glândula não se alinham, e a cruz 3D os apagava
    glandula = abrir(glandula, quadrado=False) & mama
    voxel_ml = float(np.prod(voxel_mm)) / 1000.0
    r.lados = [_medir_lado(n, p, glandula, voxel_ml) for n, p in zip(("direita", "esquerda"), lados(mama, eixo_lr, sentido_lr))]
    r.eixo_lr, r.sentido_lr = eixo_lr, sentido_lr
    r.total = _medir_lado("total", mama, glandula, voxel_ml)
    r.fgt, r.mama = glandula, mama
    r.texto_metodo = {
        FONTE_DIXON: "Dixon: glândula = fração de gordura < 50% na mama (sem pele e sem peitoral).",
        FONTE_T1: "T1 sem saturação: campo da bobina corrigido pela gordura, limiar de Otsu em cada mama, sem pele "
                  f"({PELE_MM:.0f} mm) e sem o peitoral.",
        FONTE_FS: "Pré-contraste com saturação de gordura: limiar de Otsu em cada mama (menos confiável).",
    }[fonte]
    return r


def medir_bpe(r: ResultadoFGT, fgt_dyn: np.ndarray, lados_dyn: list[np.ndarray], pre: np.ndarray,
              pos: np.ndarray, limiar: float = REALCE_LIMIAR) -> None:
    """Realce de fundo dentro do FGT (já na grade da dinâmica): realce relativo na 1ª pós e a fração do FGT que
    realça mais que `limiar` %. Preenche os lados e o total de `r`."""
    from ipe.imaging.morfologia import erodir
    pre = np.asarray(pre, np.float32)
    pos = np.asarray(pos, np.float32)
    nucleo = erodir(fgt_dyn, 1, quadrado=False) if fgt_dyn.sum() > 2000 else fgt_dyn
    re = (pos - pre) / np.maximum(pre, 1e-3) * 100.0
    # fora o que quase não tem sinal no pré (a conta em % explode ali)
    valido = pre > 0.2 * float(np.median(pre[nucleo])) if nucleo.any() else pre > 0

    def medir(lado: Lado, sel: np.ndarray) -> None:
        v = re[sel & nucleo & valido]
        if v.size < 50:
            return
        lado.bpe_realce_medio = float(np.mean(v))
        lado.bpe_realce_mediana = float(np.median(v))
        lado.bpe_pct = float(np.mean(v > limiar) * 100.0)
        lado.bpe_faixa = faixa(lado.bpe_pct, FAIXAS_BPE)

    for lado, sel in zip(r.lados, lados_dyn):
        medir(lado, sel)
    medir(r.total, np.ones_like(nucleo))


def reamostrar(mask: np.ndarray, afim_origem: np.ndarray, forma_destino: tuple, afim_destino: np.ndarray) -> np.ndarray:
    """Leva uma máscara de uma grade a outra pela posição no paciente (vizinho mais próximo). As afins são 4×4,
    índice (corte, linha, coluna) → mm."""
    inv = np.linalg.inv(afim_origem)
    out = np.zeros(forma_destino, bool)
    nz, ny, nx = forma_destino
    jj, ii = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    for k in range(nz):
        idx = np.stack([np.full(jj.size, k), jj.ravel(), ii.ravel(), np.ones(jj.size)])
        src = inv @ (afim_destino @ idx)
        a, b, c = (np.rint(src[i]).astype(np.int64) for i in range(3))
        ok = (a >= 0) & (a < mask.shape[0]) & (b >= 0) & (b < mask.shape[1]) & (c >= 0) & (c < mask.shape[2])
        fat = np.zeros(jj.size, bool)
        fat[ok] = mask[a[ok], b[ok], c[ok]]
        out[k] = fat.reshape(ny, nx)
    return out


def frases(r: ResultadoFGT) -> list[str]:
    """As frases para o laudo (sugestão). Só os números: a categoria BI-RADS fica com o médico — a porcentagem em
    volume sai bem abaixo da impressão visual (num exame do acervo, 10% medidos para "esparsas" no laudo), e o realce
    medido voxel a voxel, sem registro, ainda não foi aferido contra os laudos."""
    out = []
    t = r.total
    if t.mama_ml:
        partes = "; ".join(f"{l.nome} {l.fgt_pct:.0f}% ({l.fgt_ml:.0f} de {l.mama_ml:.0f} mL)" for l in r.lados if l.mama_ml)
        out.append(f"Tecido fibroglandular estimado em {t.fgt_pct:.0f}% do volume mamário ({partes}) — medida "
                   "automática em volume; a categoria de quantidade fica a critério do médico.")
    if r.implante_ml:
        out.append(f"Implante identificado ({r.implante_ml:.0f} mL), fora da conta.")
    if t.bpe_pct is not None:
        partes = "; ".join(f"{l.nome} {l.bpe_realce_mediana:.0f}%" for l in r.lados if l.bpe_realce_mediana is not None)
        out.append(f"Realce do tecido fibroglandular na primeira fase: mediana {t.bpe_realce_mediana:.0f}% ({partes}); "
                   f"{t.bpe_pct:.0f}% do tecido realça mais de {REALCE_LIMIAR:.0f}% — medida automática, para apoiar "
                   "a graduação do realce de fundo.")
    return out
