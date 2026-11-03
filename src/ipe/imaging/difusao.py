"""Difusão na RM (0.99.37): mapa ADC, DWI sintética e medidas por ROI, em qualquer RM.

Pedido dele: *"crie a difusão de RM para todas as RM, não apenas as mama"* (itens M1, M2, M5 e M12 do
plano da AW, em `claude/ideias-aw-server.md`).

**O que o acervo dele mostrou antes de escrever o cálculo** (16 séries de difusão, cinco aparelhos
GE: Signa HDxt, SIGNA Pioneer, Creator, Voyager e Optima MR450w):

- cada série traz **dois valores de b** — b0 e b1000 (crânio e mama no HDxt) ou b0 e b750 (mama no
  Pioneer e no Creator) — com uma imagem de cada b por posição;
- o valor de b está no privado da GE **(0043,1039)** (primeiro número, módulo 10⁹) em todas as
  imagens; o padrão **(0018,9087)** só nas imagens com b > 0. Numa série anonimizada só sobrou o
  (0018,9087): a imagem sem nenhum dos dois, numa série em que as outras têm b > 0, é o b0;
- o aparelho grava o próprio ADC ("ADC (10^-6 mm²/s)", com intercept −1). No **crânio** o ADC daqui
  bate com o dele: razão mediana 1,0002, diferença mediana 0,4 × 10⁻⁶ mm²/s, nos 24 cortes. Na
  **mama** a diferença é de ruído (mediana 120 a 330; cai para 48 suavizando 5 × 5; nenhum
  deslocamento): o aparelho calcula a mama a partir das médias/direções que não grava na série DWI, e
  no Pioneer mascara 94% da imagem. Por isso o painel mostra, na mesma ROI, o ADC daqui **e** o do
  aparelho quando ele existe.

O cálculo: regressão log-linear de ln(S) contra b em todos os b escolhidos (com dois b, é a fórmula
de sempre ln(S0/Sb)/b); unidade 10⁻⁶ mm²/s, a mesma do aparelho. Pixel com sinal de b0 abaixo do
limiar de ruído (padrão: 5% do percentil 99 do b0) fica 0. Com três b ou mais, o ajuste tem R², e o
pixel com R² abaixo do mínimo (padrão 0,25 — o "nível de confiança" da AW) fica 0.

A DWI sintética é S(b) = S0·e^(−ADC·b): **marcada como sintética** na descrição e no ImageType, e
nunca é usada para calcular ADC (a AW proíbe o mesmo).

Sem Qt.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

#: descrição da série que sugere difusão (a confirmação é ter mais de um b no arquivo)
PALAVRAS = re.compile(r"(?<![A-Z])(DWI|DIFUS[A-Z]*|DIFF[A-Z]*|TRACE[A-Z]*|DTI|B\s*\d{3,4})(?![A-Z])", re.I)
#: séries que são mapa, não aquisição (o ADC do aparelho, o eADC, o FA)
MAPAS = re.compile(r"(?<![A-Z])(E?ADC|FA|EXP|SINT[EÉ]TICA)(?![A-Z])", re.I)
LIMIAR_SINAL = 0.05          # fração do percentil 99 do b0 abaixo da qual o pixel é ruído
R2_MINIMO = 0.25             # com 3 b ou mais
ADC_MAX = 5000.0             # ×10⁻⁶ mm²/s — acima disso é ruído (água livre a 37 °C ≈ 3000)
UNIDADE = "×10⁻⁶ mm²/s"
B_MIN_CONFIAVEL = 500


# ------------------------------------------------------------------ o valor de b no arquivo
def valor_b(ds) -> float | None:
    """O b da imagem, pelos lugares em que os fabricantes gravam. None = o arquivo não diz."""
    def num(v):
        try:
            if isinstance(v, (list, tuple)) or type(v).__name__ == "MultiValue":
                v = v[0]
            return float(str(v).split("\\")[0])
        except (TypeError, ValueError, IndexError):
            return None
    if (0x0018, 0x9087) in ds:                         # padrão (Enhanced, e as GE nas imagens b > 0)
        b = num(ds[0x0018, 0x9087].value)
        if b is not None:
            return b
    if (0x0043, 0x1039) in ds:                         # GE: primeiro valor, módulo 10⁹
        b = num(ds[0x0043, 0x1039].value)
        if b is not None:
            return float(int(b) % 1_000_000_000)
    if (0x0019, 0x100C) in ds:                         # Siemens
        b = num(ds[0x0019, 0x100C].value)
        if b is not None:
            return b
    if (0x2001, 0x1003) in ds:                         # Philips
        b = num(ds[0x2001, 0x1003].value)
        if b is not None:
            return b
    for kw in ("SequenceName", "ImageComments"):       # Siemens antigo: "ep_b1000t", "b=1000"
        m = re.search(r"b\s*=?\s*(\d{2,4})", str(getattr(ds, kw, "") or ""), re.I)
        if m:
            return float(m.group(1))
    return None


def parece_difusao(descricao: str) -> bool:
    d = descricao or ""
    return bool(PALAVRAS.search(d)) and not MAPAS.search(d)


def e_mapa_adc(descricao: str, image_type=None) -> bool:
    it = "\\".join(image_type or []).upper() if not isinstance(image_type, str) else image_type.upper()
    return "ADC" in it.split("\\") or bool(re.match(r"\s*ADC\b", descricao or "", re.I))


# ------------------------------------------------------------------ a série de difusão
@dataclass
class Corte:
    posicao: tuple                                  # (x, y, z) do b0 (ou do primeiro) neste corte
    imagens: dict = field(default_factory=dict)     # b -> caminho do arquivo (o primeiro)
    extras: dict = field(default_factory=dict)      # b -> nº de imagens a mais (direções não combinadas)


@dataclass
class SerieDifusao:
    series_uid: str
    descricao: str
    cortes: list[Corte]
    bs: list[float]
    deduzido: bool = False          # o b0 saiu da regra "imagem sem b numa série com b > 0"
    sem_b: bool = False             # nenhum b no arquivo: precisa digitar
    avisos: list[str] = field(default_factory=list)
    te_tr: dict = field(default_factory=dict)       # b -> (TE, TR)

    @property
    def n(self) -> int:
        return len(self.cortes)


def _pos(ds) -> tuple:
    p = getattr(ds, "ImagePositionPatient", None)
    if p is None:
        return (0.0, 0.0, float(getattr(ds, "InstanceNumber", 0) or 0))
    return tuple(round(float(x), 1) for x in p)


def ler_serie(repo, series_uid: str, bs_digitados: list[float] | None = None) -> SerieDifusao:
    """Lê os cabeçalhos da série e agrupa as imagens por posição e por b.

    `bs_digitados`: quando o arquivo não diz o b, os b na ordem em que se repetem em cada posição
    (ex.: [0, 1000]), como no painel da AW para digitar os b."""
    import pydicom
    meta = repo.series_meta(series_uid) or {}
    insts = sorted(repo.instances_for_series(series_uid), key=lambda i: (i.get("instance_number") or 0))
    lidos = []
    for it in insts:
        try:
            ds = pydicom.dcmread(it["path"], stop_before_pixels=True, force=True)
        except Exception as e:  # noqa: BLE001
            log.warning("difusão: não li %s: %s", it.get("path"), e)
            continue
        lidos.append((it["path"], ds, valor_b(ds)))
    s = SerieDifusao(series_uid, meta.get("description", "") or "", [], [])
    if not lidos:
        s.avisos.append("A série não tem imagens legíveis.")
        return s
    com_b = [b for _p, _d, b in lidos if b is not None]
    por_pos: dict[tuple, list] = {}
    for p, ds, b in lidos:
        por_pos.setdefault(_pos(ds), []).append((p, ds, b))
    if not com_b:
        if bs_digitados:
            for grupo in por_pos.values():
                for k, (p, ds, _b) in enumerate(grupo):
                    grupo[k] = (p, ds, float(bs_digitados[k % len(bs_digitados)]))
        else:
            s.sem_b = True
            s.avisos.append("O arquivo não diz o valor de b: digite os b na ordem em que se repetem em cada "
                            "corte (ex.: 0, 1000).")
    elif len(com_b) < len(lidos) and max(com_b) > 0:
        s.deduzido = True                     # GE anonimizada: o b0 perdeu o (0043,1039)
        for grupo in por_pos.values():
            for k, (p, ds, b) in enumerate(grupo):
                if b is None:
                    grupo[k] = (p, ds, 0.0)
    for pos in sorted(por_pos, key=lambda q: q[2]):
        c = Corte(pos)
        for p, ds, b in por_pos[pos]:
            if b is None:
                continue
            if b in c.imagens:
                c.extras[b] = c.extras.get(b, 0) + 1
                continue
            c.imagens[b] = p
            s.te_tr.setdefault(b, (getattr(ds, "EchoTime", None), getattr(ds, "RepetitionTime", None)))
        if c.imagens:
            s.cortes.append(c)
    s.bs = sorted({b for c in s.cortes for b in c.imagens})
    s.avisos += avisos_de_qualidade(s)
    return s


def avisos_de_qualidade(s: SerieDifusao) -> list[str]:
    """O semáforo antes do mapa (M12): o que pode estragar o ADC, dito antes de calcular."""
    av = []
    if s.sem_b:
        return av
    if len(s.bs) < 2:
        av.append(f"Só há um valor de b ({_b(s.bs[0]) if s.bs else '?'}): não dá para calcular o ADC.")
        return av
    if 0 not in s.bs and min(s.bs) > 100:
        av.append(f"Sem b0: o menor b é {_b(min(s.bs))}; o ADC sai do ajuste entre os b que existem.")
    if max(s.bs) < B_MIN_CONFIAVEL:
        av.append(f"O maior b é {_b(max(s.bs))} (< {B_MIN_CONFIAVEL}): o ADC fica pouco confiável.")
    faltam = [c for c in s.cortes if len(c.imagens) < len(s.bs)]
    if faltam:
        av.append(f"{len(faltam)} corte(s) sem todos os b: ficam de fora do mapa.")
    if any(c.extras for c in s.cortes):
        av.append("Há mais de uma imagem por b no mesmo corte (direções não combinadas?): vale a primeira.")
    tes = {te for te, _tr in s.te_tr.values() if te not in (None, "")}
    if len(tes) > 1:
        av.append("O TE muda entre os b: o ADC mistura difusão com T2.")
    if s.deduzido:
        av.append("O b0 foi deduzido: as imagens sem b, numa série em que as outras têm b > 0.")
    return av


def _b(b: float) -> str:
    return f"b{int(b) if float(b).is_integer() else b}"


# ------------------------------------------------------------------ o cálculo
def _pixels(caminho: str) -> np.ndarray:
    from ipe.imaging.series import Frame, read_frame
    return np.asarray(read_frame(Frame(caminho, 0, "", 0)).pixels, dtype=np.float64)


@dataclass
class Mapa:
    adc: np.ndarray                 # (n, h, w) float32, ×10⁻⁶ mm²/s; 0 = fora (ruído, ajuste ruim)
    s0: np.ndarray                  # (n, h, w) o b0 ajustado (o sinal extrapolado para b = 0)
    bs: list[float]
    cortes: list[Corte]
    r2: np.ndarray | None = None
    limiar: float = 0.0

    def em(self, posicao, tol: float = 1.0) -> int | None:
        """O índice do corte nesta posição do paciente (mm), ou None."""
        alvo = np.asarray(posicao, dtype=float)
        melhor, k = None, None
        for i, c in enumerate(self.cortes):
            d = float(np.linalg.norm(np.asarray(c.posicao, dtype=float) - alvo))
            if melhor is None or d < melhor:
                melhor, k = d, i
        return k if melhor is not None and melhor <= tol else None


def calcular(s: SerieDifusao, bs: list[float] | None = None, limiar: float = LIMIAR_SINAL,
             r2_minimo: float = R2_MINIMO, progresso=None) -> Mapa:
    """ADC por regressão log-linear nos b escolhidos. `progresso(feitos, total)` devolve False para
    parar (levanta InterruptedError)."""
    usar = sorted(float(b) for b in (bs or s.bs))
    if len(usar) < 2:
        raise ValueError("O ADC precisa de pelo menos dois valores de b.")
    cortes = [c for c in s.cortes if all(b in c.imagens for b in usar)]
    if not cortes:
        raise ValueError("Nenhum corte tem todos os b escolhidos.")
    b = np.asarray(usar, dtype=np.float64)
    bm = b - b.mean()
    sxx = float((bm ** 2).sum())
    adcs, s0s, r2s = [], [], []
    # limiar de ruído: do b mais baixo da série inteira (amostra de cortes)
    amostra = [_pixels(c.imagens[usar[0]]) for c in cortes[:: max(1, len(cortes) // 8)]]
    p99 = float(np.percentile(np.concatenate([a.ravel() for a in amostra]), 99)) if amostra else 0.0
    corte_ruido = limiar * p99
    for i, c in enumerate(cortes):
        if progresso is not None and progresso(i, len(cortes)) is False:
            raise InterruptedError("Cálculo interrompido.")
        pilha = np.stack([_pixels(c.imagens[x]) for x in usar])          # (nb, h, w)
        valido = (pilha[0] > corte_ruido) & np.all(pilha > 0, axis=0)
        ln = np.log(np.where(pilha > 0, pilha, 1.0))
        lm = ln.mean(axis=0)
        inclinacao = np.tensordot(bm, ln - lm, axes=(0, 0)) / sxx         # d ln S / d b
        adc = -inclinacao * 1e6
        s0 = np.exp(lm - inclinacao * b.mean())
        r2 = None
        if len(usar) >= 3:
            prev = lm + inclinacao * bm[:, None, None]
            ss_res = ((ln - prev) ** 2).sum(axis=0)
            ss_tot = ((ln - lm) ** 2).sum(axis=0)
            r2 = np.where(ss_tot > 0, 1 - ss_res / np.maximum(ss_tot, 1e-12), 1.0)
            valido &= r2 >= r2_minimo
        adc = np.where(valido, np.clip(adc, 0, ADC_MAX), 0.0)
        adcs.append(adc.astype(np.float32))
        s0s.append(np.where(valido, s0, pilha[0]).astype(np.float32))
        if r2 is not None:
            r2s.append(r2.astype(np.float32))
    if progresso is not None:
        progresso(len(cortes), len(cortes))
    return Mapa(np.stack(adcs), np.stack(s0s), usar, cortes, np.stack(r2s) if r2s else None, corte_ruido)


def dwi_sintetica(m: Mapa, b: float) -> np.ndarray:
    """S(b) = S0·e^(−ADC·b) — só onde há ADC; fora, 0. Não serve para calcular ADC."""
    return np.where(m.adc > 0, m.s0 * np.exp(-m.adc * 1e-6 * float(b)), 0.0).astype(np.float32)


# ------------------------------------------------------------------ medir numa ROI
def estatistica(valores: np.ndarray) -> dict | None:
    v = np.asarray(valores, dtype=np.float64).ravel()
    v = v[np.isfinite(v)]
    if v.size == 0:
        return None
    return {"n": int(v.size), "media": float(v.mean()), "dp": float(v.std()), "mediana": float(np.median(v)),
            "min": float(v.min()), "max": float(v.max())}


def tabela_da_roi(m: Mapa, k: int, mascara: np.ndarray, adc_aparelho: np.ndarray | None = None) -> list[dict]:
    """Uma linha por mapa, para a ROI no corte k: ADC daqui (só pixels válidos), ADC do aparelho e o
    sinal em cada b (M5, "tabela multi-mapa por ROI")."""
    linhas = []
    adc = m.adc[k][mascara]
    st = estatistica(adc[adc > 0])
    validos = int((adc > 0).sum())
    linhas.append({"mapa": f"ADC (Ipê) {UNIDADE}", **(st or {}),
                   "obs": f"{validos} de {int(mascara.sum())} pixels válidos" if st else "nenhum pixel válido"})
    if adc_aparelho is not None and adc_aparelho.shape == mascara.shape:
        a = adc_aparelho[mascara]
        st = estatistica(a[a > 0])
        linhas.append({"mapa": f"ADC do aparelho {UNIDADE}", **(st or {}), "obs": "" if st else "zerado pelo aparelho"})
    c = m.cortes[k]
    for b in m.bs:
        try:
            px = _pixels(c.imagens[b])
        except Exception:  # noqa: BLE001
            continue
        if px.shape == mascara.shape:
            linhas.append({"mapa": f"Sinal {_b(b)}", **(estatistica(px[mascara]) or {}), "obs": ""})
    return linhas
