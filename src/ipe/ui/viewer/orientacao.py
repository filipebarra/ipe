"""Orientação na tela (0.91): o que fica à esquerda e o que fica no alto do quadro.

Pedido dele: trocar o "Frente (mamilo): esquerda ou direita da tela" do protocolo por uma
orientação de verdade — Direita, Esquerda, Superior, Inferior, Anterior, Posterior — e ter a mesma
escolha nas barras do MPR e do 3D, para trabalhar nos MIPs que o protocolo da mama monta.

Escolhe-se a direção do paciente que fica no **lado esquerdo** da tela e a que fica no **alto**.
Num corte (MPR, MIP de espessura, série original) isso vira giro + espelho do quadro; no 3D vira
posição da câmera e giro, **sem espelho** — um 3D espelhado é um paciente que não existe.

Direções em LPS: +x = esquerda do paciente, +y = posterior, +z = cabeça.
"""
from __future__ import annotations

import itertools

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QTransform

DIRECOES = {"direita": (-1.0, 0.0, 0.0), "esquerda": (1.0, 0.0, 0.0),
            "anterior": (0.0, -1.0, 0.0), "posterior": (0.0, 1.0, 0.0),
            "superior": (0.0, 0.0, 1.0), "inferior": (0.0, 0.0, -1.0)}
NOMES = {"": "Como vier", "direita": "Direita", "esquerda": "Esquerda", "superior": "Superior",
         "inferior": "Inferior", "anterior": "Anterior", "posterior": "Posterior"}
OPOSTA = {"direita": "esquerda", "esquerda": "direita", "anterior": "posterior",
          "posterior": "anterior", "superior": "inferior", "inferior": "superior"}


def _t(rot: int, fh: bool, fv: bool) -> QTransform:
    t = QTransform()
    t.rotate(rot)
    t.scale(-1 if fh else 1, -1 if fv else 1)
    return t


def na_tela(direita_img, baixo_img, rot: int, fh: bool, fv: bool) -> tuple[np.ndarray, np.ndarray]:
    """(direita da tela, baixo da tela) em mm do paciente, depois do giro/espelho do quadro."""
    r, c = np.asarray(direita_img, float), np.asarray(baixo_img, float)
    inv, _ok = _t(rot, fh, fv).inverted()
    a, b = inv.map(QPointF(1, 0)), inv.map(QPointF(0, 1))
    return r * a.x() + c * a.y(), r * b.x() + c * b.y()


def nome_da_direcao(v) -> str:
    """A direção anatômica dominante de um vetor ("anterior", "superior"…), ou "" se oblíqua."""
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return ""
    v = v / n
    melhor = max(DIRECOES, key=lambda k: float(np.dot(v, DIRECOES[k])))
    return melhor if float(np.dot(v, DIRECOES[melhor])) > 0.7 else ""


def _nota(direita, baixo, esq: str, alto: str) -> float:
    nota = 0.0
    if esq:
        nota += float(np.dot(-direita, DIRECOES[esq]))
    if alto:
        nota += float(np.dot(-baixo, DIRECOES[alto]))
    return nota


def escolher_giro(direita_img, baixo_img, esq: str, alto: str,
                  espelhar: bool = True) -> tuple[int, bool, bool] | None:
    """(giro, espelho horizontal, espelho vertical) que põe `esq` à esquerda e `alto` no alto.

    Só o que está no plano da imagem pode ir para a tela: pedir "anterior" num corte axial dá
    certo; num coronal, não — aí devolve None. Pedir só um dos dois mantém o outro o mais perto
    possível de como está. Empate fica com a solução de menos mexida."""
    if not esq and not alto:
        return 0, False, False
    if esq and alto and (esq == alto or OPOSTA[esq] == alto):
        return None
    combos = [(rot, fh, fv) for rot in (0, 90, 180, 270) for fh, fv in itertools.product((False, True), repeat=2)
              if espelhar or not (fh or fv)]
    pedido = (1 if esq else 0) + (1 if alto else 0)
    melhor, nota_m = None, -9.0
    for rot, fh, fv in combos:
        d, b = na_tela(direita_img, baixo_img, rot, fh, fv)
        nota = _nota(d, b, esq, alto)
        # quem só pediu um lado: o outro eixo fica como estava (cabeça para cima, se der)
        if pedido == 1:
            livre = b if esq else d
            original = np.asarray(baixo_img if esq else direita_img, float)
            nota += 0.01 * float(np.dot(livre, original))
        nota -= 0.001 * (rot / 90 + fh + fv)
        if nota > nota_m:
            melhor, nota_m = (rot, fh, fv), nota
    return melhor if nota_m > pedido * 0.7 else None


# ---------------------------------------------------------------- no quadro
def eixos_do_quadro(vp):
    """(direita, baixo) da imagem **sem** o giro do quadro, em mm do paciente; None se não há."""
    v3 = getattr(vp, "render3d", None)
    if v3 is not None:
        from ipe.imaging.render3d import rotation
        u, v, _d = rotation(v3.az, v3.el)
        return np.asarray(u, float), np.asarray(v, float)
    f = vp.current_frame() if vp is not None else None
    if f is None or f.orientation is None:
        return None
    o = np.asarray(f.orientation, float)
    return o[:3], o[3:]


def atual(vp) -> tuple[str, str]:
    """(o que está à esquerda, o que está no alto) do quadro como aparece agora."""
    eixos = eixos_do_quadro(vp)
    if eixos is None:
        return "", ""
    st = vp.state
    d, b = na_tela(*eixos, st.rot, st.flip_h, st.flip_v)
    return nome_da_direcao(-d), nome_da_direcao(-b)


def orientar(vp, esq: str, alto: str) -> str:
    """Põe `esq` à esquerda e `alto` no alto do quadro. Devolve "" ou o motivo de não ter dado."""
    esq, alto = esq or "", alto or ""
    if not esq and not alto:
        return ""
    v3 = getattr(vp, "render3d", None)
    if v3 is not None:
        return _orientar_3d(vp, v3, esq, alto)
    eixos = eixos_do_quadro(vp)
    if eixos is None:
        return "Este quadro não tem orientação no arquivo."
    g = escolher_giro(*eixos, esq, alto)
    if g is None:
        return _fora_do_plano(esq, alto)
    vp.set_orientation(*g)
    return ""


def _fora_do_plano(esq: str, alto: str) -> str:
    pedido = " e ".join(NOMES[x].lower() for x in (esq, alto) if x)
    return f"Neste plano não dá para pôr {pedido} na tela."


#: posições de câmera do 3D: as seis vistas (az, el) da barra
_VISTAS_3D = [(0, 0), (180, 0), (270, 0), (90, 0), (0, -89), (0, 89)]


def _orientar_3d(vp, v3, esq: str, alto: str) -> str:
    """No 3D a orientação vem da câmera (de que lado se olha) e de um giro do quadro, nunca de
    espelho. Quem só pediu um lado continua olhando de onde estava, se der."""
    from ipe.imaging.render3d import rotation
    candidatos = [(v3.az, v3.el)] + [c for c in _VISTAS_3D if c != (v3.az, v3.el)]
    pedido = (1 if esq else 0) + (1 if alto else 0)
    melhor, nota_m = None, -9.0
    for k, (az, el) in enumerate(candidatos):
        u, v, _d = rotation(az, el)
        for rot in (0, 90, 180, 270):
            d, b = na_tela(u, v, rot, False, False)
            nota = _nota(d, b, esq, alto) - 0.001 * (rot / 90) - (0.0005 * k)
            if esq and not alto:            # só o lado: cabeça para cima, se der
                nota += 0.01 * float(np.dot(b, DIRECOES["inferior"]))
            if nota > nota_m:
                melhor, nota_m = (az, el, rot), nota
    if melhor is None or nota_m < pedido * 0.7:
        return _fora_do_plano(esq, alto)
    az, el, rot = melhor
    vp.set_orientation(rot, False, False)
    if (az, el) != (v3.az, v3.el):
        v3.set_view(az, el)
    else:
        vp.update()
    return ""


# ---------------------------------------------------------------- nas barras (MPR e 3D)
class BarraOrientacao:
    """Os dois combos "à esquerda / no alto" numa barra. Aplicam no quadro ativo na hora; ao trocar
    de quadro mostram como ele está."""

    def __init__(self, barra, quadro, avisar=None):
        from PySide6.QtWidgets import QComboBox, QLabel
        self.quadro, self.avisar = quadro, avisar or (lambda _t: None)
        self._mudo = False
        barra.addWidget(QLabel("  orientação — esquerda:"))
        self.c_esq = QComboBox()
        barra.addWidget(self.c_esq)
        barra.addWidget(QLabel(" alto:"))
        self.c_alto = QComboBox()
        barra.addWidget(self.c_alto)
        for c in (self.c_esq, self.c_alto):
            for k, v in NOMES.items():
                c.addItem("—" if not k else v, k)
            c.setFixedWidth(95)
        self.c_esq.activated.connect(lambda *_a: self._escolheu("esq"))
        self.c_alto.activated.connect(lambda *_a: self._escolheu("alto"))
        self.c_esq.setToolTip("Que lado do paciente fica no lado esquerdo do quadro ativo")
        self.c_alto.setToolTip("Que lado do paciente fica no alto do quadro ativo")

    def _escolheu(self, mudou: str) -> None:
        if self._mudo:
            return
        vp = self.quadro()
        if vp is None:
            return
        esq, alto = self.c_esq.currentData() or "", self.c_alto.currentData() or ""
        # o outro combo fica como está — a não ser que esteja no mesmo eixo do que mudou
        if mudou == "esq" and alto and esq and alto in (esq, OPOSTA[esq]):
            alto = ""
        if mudou == "alto" and esq and alto and esq in (alto, OPOSTA[alto]):
            esq = ""
        motivo = orientar(vp, esq, alto)
        if motivo:
            self.avisar(motivo)
        self.sync()

    def sync(self) -> None:
        vp = self.quadro()
        esq, alto = atual(vp) if vp is not None else ("", "")
        self._mudo = True
        try:
            for c, v in ((self.c_esq, esq), (self.c_alto, alto)):
                c.setCurrentIndex(max(0, c.findData(v)))
                c.setEnabled(vp is not None and eixos_do_quadro(vp) is not None)
        finally:
            self._mudo = False
