"""0.100.72: esquemas-guia do laudo no Ipê de mesa — escolher o modelo, desenhar (ponto numerado, elipse, seta,
traço livre, texto; na próstata, o clique pinta o setor) e a faixa "Esquemas-guia" da janela do laudo.

Os dados e as regras são os de `reporting/esquemas.py` (os mesmos do Ipê Web). A tela é desenhada com o QPainter;
a figura que vai para o PDF, para o exame e para o SR é sempre a de `esquemas.desenhar` (Pillow).
"""
from __future__ import annotations

import copy
import json
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QTableWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from ipe.reporting import esquemas as E

TINTA = {"forte": QColor(40, 40, 40), "leve": QColor(150, 150, 150)}
FERRAMENTAS = [
    ("mover", "Mover", "Arraste uma marca para mudar de lugar; um clique escolhe a marca na lista"),
    ("ponto", "Ponto", "Um clique marca um ponto numerado"),
    ("elipse", "Elipse", "Arraste para desenhar uma elipse"),
    ("seta", "Seta", "Arraste do começo até a ponta da seta"),
    ("traco", "Traço livre", "Desenhe à mão livre"),
    ("texto", "Texto", "Um clique põe um texto na figura"),
    ("setor", "Setor", "Um clique pinta o setor com a categoria escolhida; outro clique limpa"),
    ("apagar", "Apagar", "Um clique numa marca apaga"),
]


def _fundo(mod: dict) -> QImage | None:
    if not mod.get("png"):
        return None
    import base64
    im = QImage.fromData(base64.b64decode(mod["png"]))
    return None if im.isNull() else im


def pintar(p: QPainter, mod: dict, e: dict | None, W: float, H: float, fundo: QImage | None = None,
           escolhida: int = -1) -> None:
    """O esquema inteiro num retângulo de W × H (a mesma figura do navegador e do PDF)."""
    esc = W / mod["w"]
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.fillRect(QRectF(0, 0, W, H), QColor(255, 255, 255))
    if fundo is not None:
        p.drawImage(QRectF(0, 0, W, H), fundo)
    cores = {c["k"]: c["cor"] for c in mod.get("categorias") or []}
    pintados = (e or {}).get("setores") or {}
    for s in mod.get("setores") or []:
        cor = cores.get(pintados.get(s["id"], ""))
        if cor:
            c = QColor(cor)
            c.setAlpha(205)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            p.drawPolygon(QPolygonF([QPointF(x * esc, y * esc) for x, y in s["p"]]))
    p.setBrush(Qt.NoBrush)
    for t in mod.get("tracos") or []:
        p.setPen(QPen(TINTA.get(t.get("c"), TINTA["forte"]), max(1.0, t.get("l", 3) * esc), Qt.SolidLine, Qt.RoundCap,
                      Qt.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(x * esc, y * esc) for x, y in t["p"]]))

    def texto(x, y, s, tam, cor):
        f = QFont()
        f.setPixelSize(max(7, int(round(tam))))
        p.setFont(f)
        p.setPen(cor)
        p.drawText(QRectF(x - 400, y - 60, 800, 120), Qt.AlignCenter, s)
    for s in mod.get("setores") or []:
        cat = pintados.get(s["id"])
        if s.get("curto"):
            texto(s["cx"] * esc, s["cy"] * esc - (9 * esc if cat else 0), s["curto"], 15 * esc, QColor(90, 90, 90))
        if cat in cores:
            texto(s["cx"] * esc, s["cy"] * esc + 10 * esc, cat, 24 * esc, QColor(0, 0, 0))
    for r in mod.get("rotulos") or []:
        texto(r["x"] * esc, r["y"] * esc, r["t"], r.get("s", 20) * esc, TINTA.get(r.get("c"), TINTA["leve"]))
    base = W / 1000.0
    for m in mod.get("base") or []:                      # o desenho do próprio modelo, por baixo
        _marca(p, m, W, H, base, False)
    for i, m in enumerate((e or {}).get("marcas") or []):
        _marca(p, m, W, H, base, i == escolhida)


def _marca(p: QPainter, m: dict, W: float, H: float, base: float, escolhida: bool) -> None:
    pts = [QPointF(x * W, y * H) for x, y in m.get("p") or []]
    if not pts:
        return
    cor = QColor(m.get("cor") or E.CORES[0])
    larg = max(2.0, float(m.get("l", 3)) * base)
    tipo, n = m.get("tipo"), int(m.get("n") or 0)

    def numero(c: QPointF, r: float, tam: float):
        p.setPen(QPen(QColor(255, 255, 255), max(1.0, 2 * base)))
        p.setBrush(QBrush(cor))
        p.drawEllipse(c, r, r)
        if n:
            f = QFont()
            f.setPixelSize(max(7, int(round(tam))))
            p.setFont(f)
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, str(n))
    onde = pts[0]
    if tipo == "ponto":
        numero(pts[0], 15 * base, 18 * base)
    elif tipo == "texto":
        f = QFont()
        f.setPixelSize(max(8, int(round(20 * base))))
        p.setFont(f)
        r = p.fontMetrics().boundingRect(m.get("texto", ""))
        caixa = QRectF(pts[0].x() - 4 * base, pts[0].y() - 14 * base, r.width() + 8 * base, 28 * base)
        p.fillRect(caixa, QColor(255, 255, 255, 215))
        p.setPen(cor)
        p.drawText(caixa.adjusted(4 * base, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, m.get("texto", ""))
    else:
        p.setPen(QPen(cor, larg, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if tipo == "elipse" and len(pts) >= 2:
            c = QColor(cor)
            c.setAlpha(46)
            p.setBrush(QBrush(c))
            p.drawEllipse(QRectF(pts[0], pts[1]).normalized())
            onde = QPointF(max(pts[0].x(), pts[1].x()), min(pts[0].y(), pts[1].y()))
        elif tipo == "seta" and len(pts) >= 2:
            a, b = pts[0], pts[1]
            p.drawLine(a, b)
            ang = math.atan2(b.y() - a.y(), b.x() - a.x())
            t = 16 * base + larg * 1.5
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(cor))
            p.drawPolygon(QPolygonF([b, QPointF(b.x() - t * math.cos(ang - 0.42), b.y() - t * math.sin(ang - 0.42)),
                                     QPointF(b.x() - t * math.cos(ang + 0.42), b.y() - t * math.sin(ang + 0.42))]))
        else:
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(QPolygonF(pts))
        p.setBrush(Qt.NoBrush)
        if n:
            numero(onde, 12 * base, 15 * base)
    if escolhida:
        xs, ys = [q.x() for q in pts], [q.y() for q in pts]
        f = 22 * base
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(11, 99, 206), max(1.0, 1.5 * base), Qt.DashLine))
        p.drawRect(QRectF(min(xs) - f, min(ys) - f, max(xs) - min(xs) + 2 * f, max(ys) - min(ys) + 2 * f))


def miniatura(mod: dict, e: dict | None, largura: int = 150) -> QPixmap:
    alt = max(1, int(round(largura * mod["h"] / mod["w"])))
    pm = QPixmap(largura, alt)
    p = QPainter(pm)
    pintar(p, mod, e, largura, alt, _fundo(mod))
    p.end()
    return pm


def _dentro(poli, x, y) -> bool:
    d, j = False, len(poli) - 1
    for i in range(len(poli)):
        if (poli[i][1] > y) != (poli[j][1] > y) and \
                x < (poli[j][0] - poli[i][0]) * (y - poli[i][1]) / (poli[j][1] - poli[i][1]) + poli[i][0]:
            d = not d
        j = i
    return d


def _dist_segmento(px, py, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
    return math.hypot(px - a[0] - t * dx, py - a[1] - t * dy)


class Tela(QWidget):
    """O desenho, com as ferramentas do mouse. `mudou` avisa a janela para refazer a lista."""
    mudou = Signal(int)                                  # o índice da marca nova (para pôr o cursor na descrição) ou -1

    def __init__(self, mod: dict, esquema: dict, pode: bool, parent=None):
        super().__init__(parent)
        self.mod, self.e, self.pode = mod, esquema, pode
        self.fundo = _fundo(mod)
        self.ferramenta = "ponto" if pode else "mover"
        self.cor, self.categoria, self.numerar = E.CORES[0], "", True
        self.escolhida = -1
        self.rascunho: dict | None = None
        self._arrasto = None
        self.desfazer: list[str] = []
        self.setMinimumSize(280, 280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)

    # geometria: a figura cabe inteira, centrada
    def quadro(self) -> QRectF:
        k = min(self.width() / self.mod["w"], self.height() / self.mod["h"])
        w, h = self.mod["w"] * k, self.mod["h"] * k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _ponto(self, pos) -> tuple[float, float]:
        q = self.quadro()
        return (max(0.0, min(1.0, (pos.x() - q.x()) / q.width())), max(0.0, min(1.0, (pos.y() - q.y()) / q.height())))

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        q = self.quadro()
        p.translate(q.topLeft())
        e = {**self.e, "marcas": self.e["marcas"] + ([self.rascunho] if self.rascunho else [])}
        pintar(p, self.mod, e, q.width(), q.height(), self.fundo, self.escolhida)
        p.end()

    def guardar(self) -> None:
        self.desfazer.append(json.dumps({"marcas": self.e["marcas"], "setores": self.e["setores"]}))
        del self.desfazer[:-60]

    def voltar(self) -> None:
        if not self.desfazer:
            return
        v = json.loads(self.desfazer.pop())
        self.e["marcas"], self.e["setores"] = v["marcas"], v["setores"]
        self.escolhida = -1
        self.update()
        self.mudou.emit(-1)

    def marca_em(self, x: float, y: float) -> int:
        """A marca debaixo do ponto (0 a 1), a de cima primeiro; -1 se nenhuma."""
        q = self.quadro()
        W, H = q.width(), q.height()
        px, py = x * W, y * H
        tol = max(12.0, W * 0.022)
        for i in range(len(self.e["marcas"]) - 1, -1, -1):
            m = self.e["marcas"][i]
            pts = [(a * W, b * H) for a, b in m["p"]]
            t = m["tipo"]
            if t == "ponto" and math.hypot(px - pts[0][0], py - pts[0][1]) <= tol + W * 0.012:
                return i
            if t == "texto" and pts[0][0] - tol <= px <= pts[0][0] + max(60.0, len(m.get("texto", "")) * W * 0.011) \
                    and abs(py - pts[0][1]) <= tol:
                return i
            if t == "elipse" and len(pts) >= 2 and min(pts[0][0], pts[1][0]) - tol <= px <= max(pts[0][0], pts[1][0]) + tol \
                    and min(pts[0][1], pts[1][1]) - tol <= py <= max(pts[0][1], pts[1][1]) + tol:
                return i
            if t in ("seta", "traco") and any(_dist_segmento(px, py, pts[k - 1], pts[k]) <= tol for k in range(1, len(pts))):
                return i
        return -1

    def nova(self, tipo: str, pts: list, numerar: bool) -> dict:
        return {"tipo": tipo, "n": E.proximo_numero(self.e) if numerar and self.numerar else 0, "p": pts, "cor": self.cor,
                "l": 4 if tipo == "traco" else 3, "texto": ""}

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() != Qt.LeftButton or (not self.pode and self.ferramenta != "mover"):
            return
        x, y = self._ponto(ev.position())
        em = self.marca_em(x, y)
        f = self.ferramenta
        if f == "mover":
            self.escolhida = em
            if em >= 0 and self.pode:
                self._arrasto = {"i": em, "x": x, "y": y, "orig": copy.deepcopy(self.e["marcas"][em]["p"]), "mexeu": False}
            self.mudou.emit(-1)
        elif f == "apagar":
            if em >= 0:
                self.guardar()
                del self.e["marcas"][em]
                self.escolhida = -1
                self.mudou.emit(-1)
        elif f == "setor":
            s = next((z for z in self.mod.get("setores") or [] if _dentro(z["p"], x * self.mod["w"], y * self.mod["h"])), None)
            if s is not None and self.categoria:
                self.guardar()
                if self.e["setores"].get(s["id"]) == self.categoria:
                    del self.e["setores"][s["id"]]
                else:
                    self.e["setores"][s["id"]] = self.categoria
                self.mudou.emit(-1)
        elif f == "ponto":
            self.guardar()
            self.e["marcas"].append(self.nova("ponto", [[x, y]], True))
            self.escolhida = len(self.e["marcas"]) - 1
            self.mudou.emit(self.escolhida)
        elif f == "texto":
            t, ok = QInputDialog.getText(self, "Texto", "Texto na figura:")
            if ok and t.strip():
                self.guardar()
                self.e["marcas"].append({**self.nova("texto", [[x, y]], False), "texto": t.strip()[:E.MAX_TEXTO]})
                self.mudou.emit(-1)
        else:
            self.rascunho = self.nova(f, [[x, y], [x, y]], f != "traco")
        self.update()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        x, y = self._ponto(ev.position())
        a = self._arrasto
        if a is not None:
            dx, dy = x - a["x"], y - a["y"]
            if not a["mexeu"] and math.hypot(dx, dy) < 0.006:
                return
            if not a["mexeu"]:
                self.guardar()
                a["mexeu"] = True
            self.e["marcas"][a["i"]]["p"] = [[max(0.0, min(1.0, u + dx)), max(0.0, min(1.0, v + dy))] for u, v in a["orig"]]
            self.update()
        elif self.rascunho is not None:
            r = self.rascunho
            if r["tipo"] == "traco":
                u = r["p"][-1]
                if math.hypot(x - u[0], y - u[1]) > 0.004 and len(r["p"]) < E.MAX_PONTOS - 10:
                    r["p"].append([x, y])
            else:
                r["p"][1] = [x, y]
            self.update()

    def mouseReleaseEvent(self, _ev) -> None:  # noqa: N802
        self._arrasto = None
        r, self.rascunho = self.rascunho, None
        if r is None:
            return
        tam = math.hypot(r["p"][-1][0] - r["p"][0][0], r["p"][-1][1] - r["p"][0][1])
        if (len(r["p"]) > 2) if r["tipo"] == "traco" else tam > 0.012:      # um clique sem arrastar não vira marca
            self.guardar()
            self.e["marcas"].append(r)
            self.escolhida = len(self.e["marcas"]) - 1
            self.mudou.emit(self.escolhida if r["n"] else -1)
        self.update()


class EsquemaDialog(QDialog):
    """Desenhar um esquema. `imagem_aberta()` devolve (series_uid, sop_uid, frame) da imagem do visualizador."""

    def __init__(self, repo, study_uid: str, esquema: dict, pode: bool = True, imagem_aberta=None, parent=None):
        super().__init__(parent)
        self.repo, self.study_uid, self.pode, self.imagem_aberta = repo, study_uid, pode, imagem_aberta
        self.mod = E.modelo(esquema.get("modelo", ""), repo)
        if self.mod is None:
            raise LookupError("O modelo deste esquema não existe mais.")
        self.e = {"id": esquema.get("id", ""), "modelo": self.mod["id"], "titulo": esquema.get("titulo", ""),
                  "marcas": copy.deepcopy(esquema.get("marcas") or []), "setores": dict(esquema.get("setores") or {})}
        self.excluir = False
        self.setWindowTitle(f"Esquema — {self.mod['nome']}")
        self.resize(1180, 820)
        self.tela = Tela(self.mod, self.e, pode)
        self.tela.mudou.connect(self._lista)
        # ferramentas
        barra = QHBoxLayout()
        self.grupo = QButtonGroup(self)
        self.dica = QLabel()
        self.dica.setStyleSheet("color:#777;font-size:11px")
        for k, nome, ajuda in FERRAMENTAS:
            if k == "setor" and not self.mod.get("setores"):
                continue
            b = QToolButton()
            b.setText(nome)
            b.setCheckable(True)
            b.setToolTip(ajuda)
            b.setProperty("ferramenta", k)
            b.setChecked(k == self.tela.ferramenta)
            b.clicked.connect(lambda _=False, f=k: self._ferramenta(f))
            self.grupo.addButton(b)
            barra.addWidget(b)
        barra.addSpacing(10)
        self.cores = QButtonGroup(self)
        for c in E.CORES:
            b = QToolButton()
            b.setCheckable(True)
            b.setChecked(c == self.tela.cor)
            b.setFixedSize(26, 26)
            b.setToolTip(c)
            b.setStyleSheet(f"QToolButton{{background:{c};border:2px solid transparent;border-radius:13px}}"
                            f"QToolButton:checked{{border:2px solid palette(text)}}")
            b.clicked.connect(lambda _=False, cor=c: setattr(self.tela, "cor", cor))
            self.cores.addButton(b)
            barra.addWidget(b)
        self.categoria = QComboBox()
        self.categoria.setToolTip("A categoria com que o clique pinta o setor")
        for c in self.mod.get("categorias") or []:
            self.categoria.addItem(c["nome"], c["k"])
        if self.categoria.count():
            self.categoria.setCurrentIndex(max(0, self.categoria.count() - 2))
            self.tela.categoria = self.categoria.currentData()
            self.categoria.currentIndexChanged.connect(lambda _i: setattr(self.tela, "categoria", self.categoria.currentData()))
            barra.addWidget(self.categoria)
        self.numerar = QCheckBox("Numerar")
        self.numerar.setChecked(True)
        self.numerar.setToolTip("Cada ponto, elipse ou seta nova ganha o próximo número (e uma linha na legenda)")
        self.numerar.toggled.connect(lambda on: setattr(self.tela, "numerar", on))
        barra.addWidget(self.numerar)
        b_desfazer = QPushButton("Desfazer")
        b_desfazer.setShortcut("Ctrl+Z")
        b_desfazer.clicked.connect(self.tela.voltar)
        barra.addWidget(b_desfazer)
        barra.addStretch(1)
        # lado: título e a lista das marcas
        self.titulo = QLineEdit(self.e["titulo"])
        self.titulo.setPlaceholderText(self.mod["nome"])
        self.titulo.setMaxLength(80)
        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["Nº", "Descrição", "Imagem", ""])
        self.tabela.setToolTip("Cada marca numerada: a descrição vai para a legenda do laudo")
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setColumnWidth(0, 52)
        self.tabela.setColumnWidth(1, 200)
        self.tabela.setColumnWidth(2, 150)
        self.tabela.setColumnWidth(3, 34)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela, estica_ultima=False)
        from PySide6.QtWidgets import QHeaderView
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)   # a descrição fica com a sobra
        self.setores = QLabel()
        self.setores.setStyleSheet("color:#777")
        lado = QVBoxLayout()
        lado.addWidget(QLabel("Título:"))
        lado.addWidget(self.titulo)
        lado.addWidget(self.tabela, 1)
        lado.addWidget(self.setores)
        lw = QWidget()
        lw.setLayout(lado)
        lw.setMinimumWidth(460)
        lw.setMaximumWidth(560)
        meio = QHBoxLayout()
        meio.addWidget(self.tela, 1)
        meio.addWidget(lw)
        bb = QDialogButtonBox()
        if pode:
            b_exc = bb.addButton("Excluir o esquema", QDialogButtonBox.DestructiveRole)
            b_exc.clicked.connect(self._excluir)
            bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
            b_ok = bb.addButton("Salvar", QDialogButtonBox.AcceptRole)
            b_ok.setDefault(False)
            b_ok.setAutoDefault(False)
        else:
            bb.addButton("Fechar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        if pode:
            lay.addLayout(barra)
            lay.addWidget(self.dica)
        lay.addLayout(meio, 1)
        lay.addWidget(bb)
        self.titulo.setEnabled(pode)
        self._ferramenta(self.tela.ferramenta)
        self._lista(-1)

    def _ferramenta(self, f: str) -> None:
        self.tela.ferramenta = f
        for b in self.grupo.buttons():
            b.setChecked(b.property("ferramenta") == f)
        self.dica.setText(next((a for k, _n, a in FERRAMENTAS if k == f), ""))
        self.categoria.setVisible(f == "setor")

    def _lista(self, focar: int = -1) -> None:
        t = self.tabela
        t.setRowCount(0)
        campo = None
        for i, m in enumerate(self.e["marcas"]):
            if m["tipo"] == "traco" and not m.get("n") and not m.get("texto"):
                continue                                  # traço solto: só desenho
            r = t.rowCount()
            t.insertRow(r)
            n = QLineEdit(str(m["n"]) if m.get("n") else "")
            n.setMaxLength(3)
            n.setEnabled(self.pode and m["tipo"] != "texto")
            n.setStyleSheet(f"border-left:6px solid {m.get('cor', E.CORES[0])}")
            n.editingFinished.connect(lambda m=m, w=n: self._numero(m, w.text()))
            d = QLineEdit(m.get("texto", ""))
            d.setMaxLength(E.MAX_TEXTO)
            d.setEnabled(self.pode)
            d.setProperty("marca", i)
            d.textEdited.connect(lambda txt, m=m: self._texto(m, txt))
            t.setCellWidget(r, 0, n)
            t.setCellWidget(r, 1, d)
            if m["tipo"] != "texto":
                im = m.get("imagem")
                b = QPushButton(im["rotulo"] + " ×" if im else "Ligar à imagem aberta")
                b.setToolTip("Tirar a ligação com a imagem" if im else
                             "Liga esta marca à imagem que está no quadro ativo do visualizador; a imagem passa a ser "
                             "imagem-chave")
                b.setEnabled(self.pode and (bool(im) or self.imagem_aberta is not None))
                b.clicked.connect(lambda _=False, m=m: self._ligar(m))
                t.setCellWidget(r, 2, b)
            if self.pode:
                x = QToolButton()
                x.setText("×")
                x.setToolTip("Apagar a marca")
                x.clicked.connect(lambda _=False, m=m: self._apagar(m))
                t.setCellWidget(r, 3, x)
            if i == focar:
                campo = d
        n = len(self.e["setores"])
        self.setores.setText(f"Setores pintados: {n}" if n else "")
        self.tela.update()
        if campo is not None:
            campo.setFocus()

    def _numero(self, m: dict, txt: str) -> None:
        novo = max(0, min(999, int(txt))) if txt.strip().isdigit() else 0
        if novo != int(m.get("n") or 0):
            self.tela.guardar()
            m["n"] = novo
            self.tela.update()

    def _texto(self, m: dict, txt: str) -> None:
        m["texto"] = txt
        if m["tipo"] == "texto":
            self.tela.update()

    def _apagar(self, m: dict) -> None:
        self.tela.guardar()
        self.e["marcas"] = [x for x in self.e["marcas"] if x is not m]
        self.tela.e = self.e
        self.tela.escolhida = -1
        self._lista(-1)

    def _ligar(self, m: dict) -> None:
        if m.get("imagem"):
            self.tela.guardar()
            del m["imagem"]
            return self._lista(-1)
        im = self.imagem_aberta() if self.imagem_aberta else None
        r = E.ligar_imagem(self.repo, self.study_uid, *im) if im else None
        if r is None:
            QMessageBox.information(self, "Esquema", "Abra no visualizador (no quadro ativo) a imagem deste exame que "
                                                     "quer ligar a esta marca.")
            return
        self.tela.guardar()
        m["imagem"] = r
        self._lista(-1)

    def _excluir(self) -> None:
        if QMessageBox.question(self, "Excluir o esquema", "Excluir este esquema do exame?") == QMessageBox.Yes:
            self.excluir = True
            self.accept()

    def esquema(self) -> dict:
        self.e["titulo"] = self.titulo.text().strip()
        return self.e


class ModeloDialog(QDialog):
    """0.100.73: desenhar o próprio modelo (o que se desenha aqui aparece em todos os exames), mudar o nome e o
    grupo, ocultar um modelo do Ipê, salvar como cópia, excluir ou restaurar o original."""

    def __init__(self, repo, mod: dict, parent=None):
        super().__init__(parent)
        self.repo, self.completo = repo, mod
        self.acao = ""
        self.e = {"id": "", "modelo": mod["id"], "titulo": "", "marcas": copy.deepcopy(mod.get("base") or []), "setores": {}}
        self.setWindowTitle(f"Modelo de esquema — {mod['nome']}")
        self.resize(1100, 800)
        # o desenho do modelo é o que se edita: não entra como fundo, e os setores não se pintam aqui
        self.tela = Tela({**mod, "base": [], "setores": [], "categorias": []}, self.e, True)
        self.tela.ferramenta, self.tela.numerar = "traco", False
        barra = QHBoxLayout()
        self.grupo_f = QButtonGroup(self)
        self.dica = QLabel()
        self.dica.setStyleSheet("color:#777;font-size:11px")
        for k, nome, ajuda in FERRAMENTAS:
            if k == "setor":
                continue
            b = QToolButton()
            b.setText(nome)
            b.setCheckable(True)
            b.setToolTip(ajuda)
            b.setProperty("ferramenta", k)
            b.clicked.connect(lambda _=False, f=k: self._ferramenta(f))
            self.grupo_f.addButton(b)
            barra.addWidget(b)
        barra.addSpacing(10)
        self.cores = QButtonGroup(self)
        for c in E.CORES:
            b = QToolButton()
            b.setCheckable(True)
            b.setChecked(c == E.CORES[-1])
            b.setFixedSize(26, 26)
            b.setStyleSheet(f"QToolButton{{background:{c};border:2px solid transparent;border-radius:13px}}"
                            f"QToolButton:checked{{border:2px solid palette(text)}}")
            b.clicked.connect(lambda _=False, cor=c: setattr(self.tela, "cor", cor))
            self.cores.addButton(b)
            barra.addWidget(b)
        self.tela.cor = E.CORES[-1]                       # o desenho de um modelo começa em preto
        b_desfazer = QPushButton("Desfazer")
        b_desfazer.setShortcut("Ctrl+Z")
        b_desfazer.clicked.connect(self.tela.voltar)
        barra.addWidget(b_desfazer)
        barra.addStretch(1)
        self.nome = QLineEdit(mod["nome"])
        self.nome.setMaxLength(60)
        self.grupo = QLineEdit(mod.get("grupo", ""))
        self.grupo.setMaxLength(30)
        do_ipe = not mod.get("meu")
        self.oculto = QCheckBox("Ocultar da lista de modelos")
        self.oculto.setChecked(bool(mod.get("oculto")))
        self.oculto.setVisible(do_ipe)
        aviso = QLabel("O que você desenhar aqui passa a fazer parte do modelo, em todos os exames. Os esquemas já "
                       "feitos com ele também mudam. Este é um modelo do Ipê: o desenho original fica guardado e volta "
                       "com “Restaurar o original”." if do_ipe else
                       "O que você desenhar aqui passa a fazer parte do modelo, em todos os exames. Os esquemas já "
                       "feitos com ele também mudam.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color:#777")
        campos = QHBoxLayout()
        campos.addWidget(QLabel("Nome do modelo:"))
        campos.addWidget(self.nome, 2)
        campos.addWidget(QLabel("Grupo:"))
        campos.addWidget(self.grupo, 1)
        campos.addWidget(self.oculto)
        bb = QDialogButtonBox()
        self.b_tirar = bb.addButton("Restaurar o original" if do_ipe else "Excluir o modelo", QDialogButtonBox.DestructiveRole)
        self.b_tirar.setVisible(not do_ipe or bool(mod.get("alterado")))
        self.b_tirar.clicked.connect(self._tirar)
        b_copia = bb.addButton("Salvar como cópia", QDialogButtonBox.ActionRole)
        b_copia.clicked.connect(lambda: self._fechar("copia"))
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        b_ok = bb.addButton("Salvar o modelo", QDialogButtonBox.ActionRole)
        b_ok.clicked.connect(lambda: self._fechar("salvar"))
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(campos)
        lay.addLayout(barra)
        lay.addWidget(self.dica)
        lay.addWidget(self.tela, 1)
        lay.addWidget(aviso)
        lay.addWidget(bb)
        self._ferramenta("traco")

    def _ferramenta(self, f: str) -> None:
        self.tela.ferramenta = f
        for b in self.grupo_f.buttons():
            b.setChecked(b.property("ferramenta") == f)
        self.dica.setText(next((a for k, _n, a in FERRAMENTAS if k == f), ""))

    def _fechar(self, acao: str) -> None:
        if not self.nome.text().strip():
            QMessageBox.information(self, "Modelo", "Dê um nome ao modelo.")
            return
        self.acao = acao
        self.accept()

    def _tirar(self) -> None:
        do_ipe = not self.completo.get("meu")
        if QMessageBox.question(self, "Modelo", "Desfazer tudo o que foi mudado neste modelo?" if do_ipe else
                                "Excluir este modelo? Os esquemas já feitos com ele deixam de aparecer.") == QMessageBox.Yes:
            self.acao = "excluir"
            self.accept()

    def gravar(self) -> None:
        """Faz no banco o que a pessoa decidiu (salvar, salvar como cópia, excluir/restaurar)."""
        m = self.completo
        if self.acao == "excluir":
            E.excluir_modelo(self.repo, m["id"])
        elif self.acao == "salvar":
            E.salvar_modelo(self.repo, {"id": m["id"], "nome": self.nome.text(), "grupo": self.grupo.text(),
                                        "oculto": self.oculto.isChecked(), "base": self.e["marcas"]})
        elif self.acao == "copia":
            E.salvar_modelo(self.repo, {"nome": self.nome.text(), "grupo": self.grupo.text(), "origem": m["id"],
                                        "base": self.e["marcas"]})


class PainelDeModelos(QWidget):
    """Os modelos (do Ipê e os próprios), em miniaturas. Com `pode_cadastrar`, também o cadastro: de uma imagem, em
    branco, desenhando por cima de um que existe, copiando, ocultando ou excluindo."""
    escolheu = Signal()                                  # duplo clique num modelo

    def __init__(self, repo, pode_cadastrar: bool = False, parent=None):
        super().__init__(parent)
        self.repo, self.pode_cadastrar = repo, pode_cadastrar
        self.lista = QListWidget()
        self.lista.setViewMode(QListWidget.IconMode)
        self.lista.setIconSize(QSize(150, 190))
        self.lista.setResizeMode(QListWidget.Adjust)
        self.lista.setMovement(QListWidget.Static)
        self.lista.setSpacing(8)
        self.lista.itemDoubleClicked.connect(lambda _i: self._editar() if pode_cadastrar else self.escolheu.emit())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if pode_cadastrar:
            nota = QLabel("Os modelos de esquema desta instalação, para todos os usuários. O que se desenha num modelo "
                          "aparece em todos os exames; nos modelos do Ipê o desenho original fica guardado.")
            nota.setWordWrap(True)
            nota.setStyleSheet("color:#777")
            lay.addWidget(nota)
        lay.addWidget(self.lista, 1)
        if pode_cadastrar:
            b_img = QPushButton("Novo modelo de uma imagem…")
            b_img.setToolTip("Um desenho seu (PNG ou JPG) vira um modelo desta instalação, para todos os usuários")
            b_img.clicked.connect(self._novo)
            b_branco = QPushButton("Novo modelo em branco…")
            b_branco.clicked.connect(self._em_branco)
            self.b_editar = QPushButton("Editar o modelo…")
            self.b_editar.setToolTip("Desenhar no modelo, mudar o nome ou o grupo, ocultar, copiar ou excluir")
            self.b_editar.clicked.connect(self._editar)
            linha = QHBoxLayout()
            for b in (b_img, b_branco, self.b_editar):
                linha.addWidget(b)
            linha.addStretch(1)
            lay.addLayout(linha)
        self._encher()

    def _encher(self, escolher: str = "") -> None:
        self.lista.clear()
        for m in E.modelos(self.repo, ocultos=self.pode_cadastrar):
            nome = m["nome"] + (" (oculto)" if m.get("oculto") else "")
            it = QListWidgetItem(QIcon(miniatura(m, None, 150)), f"{nome}\n{m.get('grupo', '')}")
            it.setData(Qt.UserRole, m["id"])
            self.lista.addItem(it)
            if m["id"] == escolher:
                self.lista.setCurrentItem(it)
        if self.lista.count() and self.lista.currentRow() < 0:
            self.lista.setCurrentRow(0)

    def _novo(self) -> None:
        arq, _f = QFileDialog.getOpenFileName(self, "Imagem do modelo", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not arq:
            return
        nome, ok = QInputDialog.getText(self, "Novo modelo", "Nome do modelo:")
        if not ok:
            return
        try:
            with open(arq, "rb") as f:
                m = E.novo_modelo_de_imagem(self.repo, nome, f.read())
        except (ValueError, OSError, PermissionError) as e:
            QMessageBox.warning(self, "Novo modelo", str(e))
            return
        self._encher(m["id"])

    def _em_branco(self) -> None:
        nome, ok = QInputDialog.getText(self, "Novo modelo", "Nome do modelo:")
        if not ok:
            return
        try:
            m = E.salvar_modelo(self.repo, {"nome": nome})
        except (ValueError, PermissionError) as e:
            QMessageBox.warning(self, "Novo modelo", str(e))
            return
        self._encher(m["id"])
        self._editar()

    def _editar(self) -> None:
        m = E.modelo(self.escolhido(), self.repo)
        if m is None:
            return
        d = ModeloDialog(self.repo, m, self)
        if d.exec() != QDialog.Accepted or not d.acao:
            return
        try:
            d.gravar()
        except (ValueError, LookupError, PermissionError) as e:
            QMessageBox.warning(self, "Modelo", str(e))
        self._encher(m["id"])

    def escolhido(self) -> str:
        it = self.lista.currentItem()
        return it.data(Qt.UserRole) if it is not None else ""


class EscolherModelo(QDialog):
    """Escolher o modelo de um esquema novo. (0.100.74: o cadastro dos modelos mudou-se para Configurações ▸
    Esquemas; `pode_cadastrar` continua valendo para quem quiser as duas coisas na mesma janela.)"""

    def __init__(self, repo, pode_cadastrar: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo esquema")
        self.resize(860, 640)
        self.painel = PainelDeModelos(repo, pode_cadastrar, self)
        self.painel.escolheu.connect(self.accept)
        self.lista = self.painel.lista
        if pode_cadastrar:
            self.b_editar = self.painel.b_editar
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.painel, 1)
        lay.addWidget(bb)

    def _em_branco(self) -> None:
        self.painel._em_branco()

    def escolhido(self) -> str:
        return self.painel.escolhido()


class ModelosDialog(QDialog):
    """0.100.74: Configurações ▸ Esquemas ▸ Modelos de esquema — o cadastro dos modelos, num lugar só."""

    def __init__(self, repo, pode_cadastrar: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações — Modelos de esquema")
        self.resize(900, 680)
        self.painel = PainelDeModelos(repo, pode_cadastrar, self)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.painel, 1)
        lay.addWidget(bb)


def imagem_do_quadro(tab, study_uid: str):
    """(série, SOP, quadro) da imagem no quadro ativo do visualizador, para ligar a uma marca do esquema; ela
    passa a ser imagem-chave (o visualizador fica sabendo). None se não é uma imagem deste exame."""
    vp = getattr(tab, "active", None) or next(iter(getattr(tab, "viewports", []) or []), None)
    f = vp.current_frame() if vp is not None else None
    if f is None or getattr(f, "is_virtual", False) or not f.sop_uid:
        return None
    if (getattr(vp, "study_uid", "") or study_uid) != study_uid:
        return None                                      # é um exame anterior aberto ao lado: não é deste exame
    serie = f.series_uid or getattr(vp, "series_uid", "")
    try:
        tab.key_set.add((f.sop_uid, int(f.frame_index or 0)))
        vp.update()
    except Exception:  # noqa: BLE001
        pass
    return serie, f.sop_uid, int(f.frame_index or 0)


class FaixaDeEsquemas(QWidget):
    """A faixa "Esquemas-guia" da janela do laudo: as miniaturas do exame, novo, editar e a legenda."""
    inserir = Signal(str)                                # a legenda, para o texto do laudo
    gravado = Signal(str)                                # gravou no exame: quem mostra as séries atualiza

    def __init__(self, repo, study_uid: str, usuario: str = "", pode: bool = True, pode_cadastrar: bool = False,
                 imagem_aberta=None, parent=None, storage_root=None, janela: bool = False):
        super().__init__(parent)
        self.repo, self.study_uid, self.usuario, self.storage_root = repo, study_uid, usuario, storage_root
        self.pode, self.pode_cadastrar, self.imagem_aberta = pode, pode_cadastrar, imagem_aberta
        self.esquemas: list[dict] = []
        self.lista = QListWidget()
        self.lista.setViewMode(QListWidget.IconMode)
        self.lista.setFlow(QListWidget.LeftToRight)
        self.lista.setWrapping(False)
        if janela:                                        # 0.100.74: a janela "Esquemas do exame" do visualizador
            self.lista.setWrapping(True)
            self.lista.setResizeMode(QListWidget.Adjust)
            self.lista.setIconSize(QSize(170, 200))
            self.lista.setSpacing(8)
            self.lista.setMinimumHeight(260)
        else:
            self.lista.setIconSize(QSize(74, 74))
            self.lista.setFixedHeight(124)
        self.lista.setMovement(QListWidget.Static)
        self.lista.setToolTip("Esquemas-guia deste exame: duplo clique para desenhar")
        self.lista.itemDoubleClicked.connect(lambda it: self.editar(self.lista.row(it)))
        self.b_novo = QPushButton("Novo esquema…")
        self.b_novo.setToolTip("Um desenho de base (face, corpo, tireoide, mamas, próstata…) para marcar os achados; vai "
                               "para o PDF e, ao assinar, para o exame (imagem e SR)")
        self.b_novo.clicked.connect(self.novo)
        self.b_editar = QPushButton("Desenhar…")
        self.b_editar.clicked.connect(lambda: self.editar(self.lista.currentRow()))
        self.b_legenda = QPushButton("Inserir a legenda no laudo")
        self.b_legenda.setToolTip("Põe no texto, onde está o cursor, as marcas numeradas e os setores pintados")
        self.b_legenda.clicked.connect(self._legenda)
        self.b_gravar = QPushButton("Gravar no exame")
        self.b_gravar.setToolTip("Grava as figuras e um SR dos esquemas no exame agora, sem precisar assinar o laudo. "
                                 "Gravar de novo troca o que havia.")
        self.b_gravar.clicked.connect(self.gravar_no_exame)
        self.b_excluir = QPushButton("Excluir")
        self.b_excluir.setToolTip("Tira o esquema escolhido do exame")
        self.b_excluir.clicked.connect(self.excluir)
        self.b_legenda.setVisible(not janela)             # a legenda entra pelo laudo ("Esquemas no laudo")
        self.b_excluir.setVisible(janela)
        col = QVBoxLayout()
        col.setSpacing(3)
        for b in (self.b_novo, self.b_editar, self.b_excluir, self.b_legenda, self.b_gravar):
            col.addWidget(b)
        col.addStretch(1)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if not janela:
            rot = QLabel("Esquemas-guia:")
            rot.setAlignment(Qt.AlignTop)
            lay.addWidget(rot)
        lay.addWidget(self.lista, 1)
        lay.addLayout(col)
        self.recarregar()

    def set_pode(self, pode: bool) -> None:
        self.pode = pode
        self._estado()

    def _estado(self) -> None:
        self.b_novo.setEnabled(self.pode)
        self.b_legenda.setEnabled(self.pode and bool(self.esquemas))
        self.b_gravar.setEnabled(self.pode and bool(self.esquemas) and self.storage_root is not None)
        self.b_editar.setEnabled(bool(self.esquemas))
        self.b_excluir.setEnabled(self.pode and bool(self.esquemas))
        self.b_editar.setText("Desenhar…" if self.pode else "Ver…")

    def recarregar(self) -> None:
        self.esquemas = E.ler(self.repo, self.study_uid)
        self.lista.clear()
        for e in self.esquemas:
            mod = E.modelo(e.get("modelo", ""), self.repo)
            if mod is None:
                it = QListWidgetItem("(modelo excluído)")
            else:
                it = QListWidgetItem(QIcon(miniatura(mod, e, 148)), E.titulo(e, self.repo))
            self.lista.addItem(it)
        if self.esquemas:
            self.lista.setCurrentRow(0)
        self._estado()

    def _gravar(self, lista: list) -> None:
        try:
            E.gravar(self.repo, self.study_uid, lista, self.usuario)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Esquemas", f"Não foi possível gravar: {e}")
        self.recarregar()

    def novo(self) -> None:
        d = EscolherModelo(self.repo, self.pode_cadastrar, self)
        if d.exec() != QDialog.Accepted or not d.escolhido():
            return
        self._abrir({"id": "", "modelo": d.escolhido(), "titulo": "", "marcas": [], "setores": {}}, -1)

    def editar(self, i: int) -> None:
        if 0 <= i < len(self.esquemas):
            self._abrir(self.esquemas[i], i)

    def _abrir(self, e: dict, i: int) -> None:
        try:
            d = EsquemaDialog(self.repo, self.study_uid, e, self.pode, self.imagem_aberta, self)
        except LookupError as x:
            QMessageBox.information(self, "Esquema", str(x))
            return
        if d.exec() != QDialog.Accepted or not self.pode:
            return
        lista = list(self.esquemas)
        if d.excluir:
            if i >= 0:
                del lista[i]
                self._gravar(lista)
            return
        if i >= 0:
            lista[i] = d.esquema()
        else:
            lista.append(d.esquema())
        self._gravar(lista)

    def excluir(self) -> None:
        i = self.lista.currentRow()
        if not (0 <= i < len(self.esquemas)):
            return
        if QMessageBox.question(self, "Excluir o esquema", "Excluir este esquema do exame?") != QMessageBox.Yes:
            return
        lista = list(self.esquemas)
        del lista[i]
        self._gravar(lista)

    def gravar_no_exame(self) -> None:
        """0.100.73: as figuras e o SR dos esquemas vão para o exame agora (sem laudo assinado)."""
        from ipe.reporting import esquemas_saida as ES
        try:
            r = ES.gravar_no_exame(self.repo, self.storage_root, self.study_uid, self.usuario)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Esquemas", f"Não foi possível gravar: {e}")
            return
        self.gravado.emit(self.study_uid)
        QMessageBox.information(self, "Esquemas", f"Gravado no exame (figuras e SR): {r['imagens']}")

    def _legenda(self) -> None:
        t = E.texto_para_o_laudo(self.esquemas, self.repo)
        if not t:
            QMessageBox.information(self, "Esquemas", "Nenhuma marca numerada nem setor pintado para pôr na legenda.")
            return
        self.inserir.emit(t)


class EsquemasDoExame(QDialog):
    """0.100.74: a janela do botão **Esquema** do visualizador — os esquemas do exame, fora do laudo: novo, desenhar,
    excluir e gravar no exame (gravar de novo troca o que havia)."""

    def __init__(self, repo, study_uid: str, usuario: str = "", pode: bool = True, imagem_aberta=None,
                 storage_root=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Esquemas do exame")
        self.resize(760, 420)
        self.faixa = FaixaDeEsquemas(repo, study_uid, usuario, pode, False, imagem_aberta, self, storage_root, janela=True)
        nota = QLabel("Desenhe os achados num modelo (face, corpo, tireoide, mamas, próstata…). “Gravar no exame” guarda "
                      "as figuras e um SR no exame; gravar de novo troca o que havia. Para o esquema sair no laudo, "
                      "marque “Esquemas no laudo” na janela do laudo. Os modelos ficam em Configurações ▸ Esquemas.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#777")
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.faixa, 1)
        lay.addWidget(nota)
        lay.addWidget(bb)
