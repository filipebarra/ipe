"""Captura da lesão de mama (Secondary Capture 2×2): o que a segmentação achou, numa imagem só.

Pedido dele: *"depois que eu segmentei, quero ter a opção de salvar a lesão em uma screencapture
2x2 (linha superior — sagital e coronal, linha inferior — axial e curva de realce). no rodapé ou
na parte inferior da SC informações da lesão como medidas, distâncias, percentual de realce e o
que você gerou."*

Como cada parte é feita:

* **As três imagens** são a fase inicial (pico) **na grade da própria segmentação** — o volume sai
  de `DynamicMaps.volume_da_fase`, que já aplica a correção de movimento, e a máscara é a mesma
  do crescimento de região. Por isso a borda colorida cai sobre a lesão nas três direções sem
  registro nenhum. Os planos são reconstruídos com `MPRPlane` (a mesma convenção de leitura do
  MPR: axial com anterior em cima, sagital com posterior à direita) e cortam pelo **centro** da
  lesão.
* **Campo**: o plano **inteiro** (0.68, pedido dele: *"não aplique zoom na lesão no SC. mantenha
  o zoom no objeto todo"*) — a mama no sagital, as duas mamas no coronal e no axial — cada um na
  proporção física dele (um coronal de 33,6 × 25 cm não vira quadrado), com régua de 10 mm. Com
  corte de 3 mm o axial e o coronal reconstruídos ficam em degraus; isso é a aquisição.
* **Fase**: a 2ª fase da dinâmica (a primeira pós-contraste do VIBRANT), também a pedido dele.
* **A curva** é o sinal médio **da lesão inteira** em cada fase, em % sobre a pré-contraste, com
  as fases inicial e tardia marcadas e o tipo (persistente/platô/washout) pela mesma régua do
  mapa cinético.
* **O rodapé** traz o que a janela da lesão mostra: volume, angiovolume, eixos, realce de pico e
  médio, distância ao mamilo, os seis padrões em cor e o limiar usado. Medida semiautomática vai
  dita como tal.

A montagem é uma função só (`montar`), sem janela: dá para testar e para olhar a imagem.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF

from ipe.imaging.volume import MPRPlane, Volume

LARG, ALT = 640, 480     # px de cada quadro (4:3, a proporção do coronal e do axial da mama)
VAO = 12                # px entre quadros
FUNDO = QColor(0, 0, 0)
TEXTO = QColor(235, 235, 235)
APAGADO = QColor(160, 160, 160)


@dataclass
class DadosCaptura:
    fase: Volume                         # imagem anatômica (2ª fase), na grade da máscara
    mascara: np.ndarray                  # bool, recortada (como no SegResult)
    offset: tuple                        # (k0, j0, i0) do recorte
    cor: tuple                           # cor da lesão (r, g, b)
    nome: str
    cabecalho: str = ""                  # paciente · ID · data · exame
    rotulo_fase: str = "Fase inicial"
    linhas: list = field(default_factory=list)        # (rótulo, valor)
    padroes: list = field(default_factory=list)       # (nome, %, (r, g, b))
    tempos_s: list = field(default_factory=list)
    curva: np.ndarray | None = None                   # sinal médio da lesão por fase
    pre: int = 0
    inicial: int = 1
    tardia: int = -1
    tipo_curva: str = ""
    rodape: str = ""                                  # observação final (limiar, aviso)
    maior_eixo_mm: float = 0.0


# ------------------------------------------------------------------ geometria
def centro_mm(vol: Volume, mascara: np.ndarray, offset) -> np.ndarray:
    kk, jj, ii = np.nonzero(mascara)
    k0, j0, i0 = (int(v) for v in offset)
    ijk = np.stack([ii + i0, jj + j0, kk + k0], axis=1).astype(float)
    return vol.origin + (ijk @ vol.matrix().T).mean(axis=0)


def planos(vol: Volume) -> dict:
    """{"Sagital": MPRPlane, "Coronal": …, "Axial": …} do volume, pelo nome do plano."""
    todos = [MPRPlane(vol, a, cache_slices=2) for a in (0, 1, 2)]
    out: dict = {}
    for p in todos:
        out.setdefault(p.name, p)
    sobra = [p for p in todos if p not in out.values()]
    for nome in ("Sagital", "Coronal", "Axial"):      # aquisição oblíqua: dois com o mesmo nome
        if nome not in out and sobra:
            out[nome] = sobra.pop(0)
    return out


def quadro_do_plano(plano: MPRPlane, plano_mask: MPRPlane, centro: np.ndarray):
    """(imagem, máscara) do plano **inteiro** que passa pelo centro da lesão."""
    idx = plano.index_for_point(centro)
    return plano._extract(idx), plano_mask._extract(idx) > 0.5


def encaixe(plano: MPRPlane, forma) -> tuple[float, float, float]:
    """(largura, altura, px por mm) do plano desenhado no quadro, na proporção física."""
    h, w = forma[:2]
    larg_mm, alt_mm = w * plano.col_spacing, h * plano.row_spacing
    escala = min(LARG / max(larg_mm, 1e-6), ALT / max(alt_mm, 1e-6))
    return larg_mm * escala, alt_mm * escala, escala


def letra(u: np.ndarray) -> str:
    """Para onde o vetor aponta no paciente: D/E, A/P, S/I (x do DICOM cresce para a esquerda)."""
    ax = int(np.argmax(np.abs(u)))
    pos = u[ax] > 0
    return (("E", "D"), ("P", "A"), ("S", "I"))[ax][0 if pos else 1]


# ------------------------------------------------------------------ desenho
def _para_tela(arr: np.ndarray, alt: int, larg: int) -> np.ndarray:
    """Reamostra (vizinho mais próximo) para alt × larg."""
    h, w = arr.shape[:2]
    li = np.minimum((np.arange(alt) * h / alt).astype(int), h - 1)
    ci = np.minimum((np.arange(larg) * w / larg).astype(int), w - 1)
    return arr[li][:, ci]


def _cinza(img: np.ndarray, lo: float, hi: float, larg: int, alt: int) -> QImage:
    a = np.clip((img.astype(np.float32) - lo) / max(hi - lo, 1e-6) * 255.0, 0, 255).astype(np.uint8)
    a = np.ascontiguousarray(a)
    q = QImage(a.data, a.shape[1], a.shape[0], a.strides[0], QImage.Format_Grayscale8).copy()
    return q.scaled(larg, alt, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def _contorno(msk: np.ndarray, cor: tuple, larg: int, alt: int) -> QImage:
    """Preenchimento leve e borda nítida, já na resolução da tela (a borda não sai em escada)."""
    m = _para_tela(msk.astype(bool), alt, larg)
    dentro = m.copy()
    for eixo in (0, 1):
        for passo in (1, -1):
            dentro &= np.roll(m, passo, axis=eixo)
    borda = m & ~dentro
    grossa = borda.copy()
    for eixo in (0, 1):
        for passo in (1, -1):
            grossa |= np.roll(borda, passo, axis=eixo)
    rgba = np.zeros((alt, larg, 4), np.uint8)
    rgba[..., :3] = cor
    rgba[..., 3] = np.where(grossa, 255, np.where(m, 70, 0))
    rgba = np.ascontiguousarray(rgba)
    return QImage(rgba.data, larg, alt, larg * 4, QImage.Format_RGBA8888).copy()


def _fonte(px: int, negrito: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(negrito)
    return f


def _quadro_imagem(p: QPainter, x: int, y: int, nome: str, rotulo_fase: str, img, msk, lo, hi,
                   cor, plano: MPRPlane) -> None:
    larg, alt, escala = encaixe(plano, img.shape)
    li, ai = max(1, int(round(larg))), max(1, int(round(alt)))
    xi, yi = x + (LARG - li) // 2, y + (ALT - ai) // 2
    p.drawImage(xi, yi, _cinza(img, lo, hi, li, ai))
    p.drawImage(xi, yi, _contorno(msk, cor, li, ai))
    p.setPen(QPen(QColor(70, 70, 70), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRect(x, y, LARG - 1, ALT - 1)
    p.setPen(TEXTO)
    p.setFont(_fonte(20, True))
    p.drawText(x + 10, y + 26, nome)
    p.setFont(_fonte(14))
    p.setPen(APAGADO)
    p.drawText(x + 10, y + 46, rotulo_fase)
    # letras de orientação: o que fica à direita, à esquerda e embaixo do quadro
    h, v = plano.orientation[:3], plano.orientation[3:]
    p.setFont(_fonte(16, True))
    p.setPen(QColor(255, 220, 120))
    p.drawText(x + LARG - 22, y + ALT // 2, letra(h))
    p.drawText(x + LARG // 2 - 5, y + ALT - 10, letra(v))
    p.drawText(x + 8, y + ALT // 2, letra(-h))
    # régua de 10 mm
    r = 10.0 * escala
    p.setPen(QPen(TEXTO, 2))
    x0, y0 = x + LARG - 24 - r, y + ALT - 34
    p.drawLine(QPointF(x0, y0), QPointF(x0 + r, y0))
    p.drawLine(QPointF(x0, y0 - 5), QPointF(x0, y0 + 5))
    p.drawLine(QPointF(x0 + r, y0 - 5), QPointF(x0 + r, y0 + 5))
    p.setFont(_fonte(13))
    p.drawText(QRectF(x0 - 20, y0 + 4, r + 40, 18), Qt.AlignCenter, "10 mm")


def _quadro_curva(p: QPainter, x: int, y: int, d: DadosCaptura) -> None:
    p.setPen(QPen(QColor(70, 70, 70), 1))
    p.setBrush(QColor(12, 12, 12))
    p.drawRect(x, y, LARG - 1, ALT - 1)
    p.setPen(TEXTO)
    p.setFont(_fonte(20, True))
    p.drawText(x + 10, y + 26, "Curva de realce")
    p.setFont(_fonte(14))
    p.setPen(APAGADO)
    p.drawText(x + 10, y + 46, "média da lesão inteira, % sobre a pré-contraste")
    if d.curva is None or len(d.curva) < 2 or not d.tempos_s:
        p.drawText(QRectF(x, y, LARG, ALT), Qt.AlignCenter, "Sem curva")
        return
    v = np.asarray(d.curva, float)
    base = v[d.pre] if abs(v[d.pre]) > 1e-6 else 1e-6
    e = (v - v[d.pre]) / abs(base) * 100.0
    t = np.asarray(d.tempos_s, float) / 60.0
    esq, dir_, topo, baixo = x + 70, x + LARG - 24, y + 72, y + ALT - 104
    ymin = min(0.0, float(np.floor(e.min() / 50.0) * 50))
    ymax = max(100.0, float(np.ceil(e.max() / 50.0) * 50))
    tmax = max(float(t.max()), 1e-6)

    def px(ti, ei):
        return QPointF(esq + (ti / tmax) * (dir_ - esq), baixo - (ei - ymin) / (ymax - ymin) * (baixo - topo))
    p.setFont(_fonte(13))
    passo = 50.0 if ymax - ymin <= 300 else 100.0
    val = ymin
    while val <= ymax + 1e-6:
        a = px(0, val)
        p.setPen(QPen(QColor(55, 55, 55), 1))
        p.drawLine(QPointF(esq, a.y()), QPointF(dir_, a.y()))
        p.setPen(APAGADO)
        p.drawText(QRectF(x + 4, a.y() - 9, esq - x - 10, 18), Qt.AlignRight | Qt.AlignVCenter, f"{val:.0f}%")
        val += passo
    for ti in range(0, int(np.ceil(tmax)) + 1):
        a = px(min(ti, tmax), ymin)
        p.setPen(APAGADO)
        p.drawText(QRectF(a.x() - 20, baixo + 6, 40, 18), Qt.AlignCenter, f"{ti}")
    p.drawText(QRectF(esq, baixo + 24, dir_ - esq, 18), Qt.AlignCenter, "minutos")
    p.setPen(QPen(QColor(120, 120, 120), 1))
    p.drawLine(QPointF(esq, baixo), QPointF(dir_, baixo))
    p.drawLine(QPointF(esq, topo), QPointF(esq, baixo))
    for i, nome in ((d.inicial, "inicial"), (d.tardia, "tardia")):
        if -len(t) <= i < len(t):
            a = px(t[i], ymin)
            p.setPen(QPen(QColor(150, 150, 150), 1, Qt.DashLine))
            p.drawLine(QPointF(a.x(), topo), QPointF(a.x(), baixo))
            p.setPen(APAGADO)
            larg = p.fontMetrics().horizontalAdvance(nome)
            xt = a.x() + 4 if a.x() + 4 + larg < x + LARG - 6 else a.x() - 4 - larg
            p.drawText(QPointF(xt, topo + 14), nome)
    cor = QColor(*d.cor)
    p.setPen(QPen(cor, 3))
    p.drawPolyline(QPolygonF([px(ti, ei) for ti, ei in zip(t, e)]))
    p.setBrush(cor)
    for ti, ei in zip(t, e):
        p.drawEllipse(px(ti, ei), 5, 5)
    p.setBrush(Qt.NoBrush)
    p.setPen(TEXTO)
    p.setFont(_fonte(16, True))
    p.drawText(QRectF(x + 12, baixo + 44, LARG - 24, 22), Qt.AlignLeft, d.tipo_curva or "")
    p.setFont(_fonte(14))
    ini = e[d.inicial] if -len(e) <= d.inicial < len(e) else float("nan")
    p.drawText(QRectF(x + 12, baixo + 68, LARG - 24, 20), Qt.AlignLeft,
               f"Realce inicial {ini:.0f}% · pico {float(e.max()):.0f}%")


def montar(d: DadosCaptura) -> QImage:
    """A captura inteira: cabeçalho, 2 × 2 e rodapé."""
    largura = 2 * LARG + 3 * VAO
    cab_h = 64
    n_linhas = len(d.linhas) + (1 if d.padroes else 0)
    rodape_h = 24 + 26 * ((n_linhas + 1) // 2) + (34 if d.padroes else 0) + 40
    altura = cab_h + 2 * ALT + 3 * VAO + rodape_h
    img = QImage(largura, altura, QImage.Format_RGB888)
    img.fill(FUNDO)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    # cabeçalho
    p.setPen(TEXTO)
    p.setFont(_fonte(24, True))
    p.drawText(QRectF(VAO, 6, largura - 2 * VAO, 30), Qt.AlignLeft | Qt.AlignVCenter, d.nome)
    p.setFont(_fonte(15))
    p.setPen(APAGADO)
    p.drawText(QRectF(VAO, 36, largura - 2 * VAO, 22), Qt.AlignLeft | Qt.AlignVCenter, d.cabecalho)
    p.setPen(QColor(*d.cor))
    p.setBrush(QColor(*d.cor))
    p.drawRect(largura - VAO - 22, 14, 18, 18)
    # as três imagens
    vol = d.fase
    cheio = np.zeros(vol.data.shape, np.uint8)
    k0, j0, i0 = (int(v) for v in d.offset)
    nz, ny, nx = d.mascara.shape
    cheio[k0:k0 + nz, j0:j0 + ny, i0:i0 + nx] = d.mascara.astype(np.uint8)
    vol_m = Volume(data=cheio, origin=vol.origin, row_dir=vol.row_dir, col_dir=vol.col_dir,
                   slice_vec=vol.slice_vec, dx=vol.dx, dy=vol.dy, window=None, source_path="")
    centro = centro_mm(vol, d.mascara, d.offset)
    pl, pm = planos(vol), planos(vol_m)
    quadros = {}
    for nome in ("Sagital", "Coronal", "Axial"):
        if nome in pl and nome in pm:
            quadros[nome] = quadro_do_plano(pl[nome], pm[nome], centro)
    tudo = np.concatenate([q[0].ravel() for q in quadros.values()]) if quadros else np.zeros(1)
    lo, hi = (float(np.percentile(tudo, 1.0)), float(np.percentile(tudo, 99.7))) if tudo.size else (0, 1)
    pos = {"Sagital": (VAO, cab_h + VAO), "Coronal": (2 * VAO + LARG, cab_h + VAO),
           "Axial": (VAO, cab_h + 2 * VAO + ALT)}
    for nome, (x, y) in pos.items():
        if nome in quadros:
            im, mk = quadros[nome]
            _quadro_imagem(p, x, y, nome, d.rotulo_fase, im, mk, lo, hi, d.cor, pl[nome])
    _quadro_curva(p, 2 * VAO + LARG, cab_h + 2 * VAO + ALT, d)
    # rodapé
    y = cab_h + 2 * ALT + 3 * VAO + 18
    col_w = (largura - 3 * VAO) // 2
    for n, (rot, val) in enumerate(d.linhas):
        x = VAO + (n % 2) * (col_w + VAO)
        yy = y + (n // 2) * 26
        p.setFont(_fonte(15, True))
        p.setPen(APAGADO)
        larg_rot = p.fontMetrics().horizontalAdvance(rot + ": ")
        p.drawText(QPointF(x, yy + 16), rot + ": ")
        p.setFont(_fonte(15))
        p.setPen(TEXTO)
        p.drawText(QRectF(x + larg_rot, yy, col_w - larg_rot, 22), Qt.AlignLeft | Qt.AlignVCenter, val)
    y += 26 * ((len(d.linhas) + 1) // 2) + 6
    if d.padroes:
        x = VAO
        p.setFont(_fonte(15, True))
        p.setPen(APAGADO)
        p.drawText(QPointF(x, y + 16), "Padrões: ")
        x += p.fontMetrics().horizontalAdvance("Padrões: ")
        p.setFont(_fonte(15))
        for nome, pct, cor in d.padroes:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*cor))
            p.drawRect(QRectF(x, y + 4, 14, 14))
            p.setBrush(Qt.NoBrush)
            p.setPen(TEXTO)
            txt = f"{nome} {pct:.0f}%"
            p.drawText(QPointF(x + 18, y + 16), txt)
            x += 18 + p.fontMetrics().horizontalAdvance(txt) + 18
        y += 34
    p.setFont(_fonte(13))
    p.setPen(APAGADO)
    p.drawText(QRectF(VAO, y, largura - 2 * VAO, 36), Qt.AlignLeft | Qt.TextWordWrap, d.rodape)
    p.end()
    return img
