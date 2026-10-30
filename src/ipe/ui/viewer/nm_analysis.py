"""Janela de análise de medicina nuclear: ROIs sobre a série dinâmica, curvas e números.

A janela é própria, como a da avaliação dinâmica: à esquerda a imagem com as regiões, à
direita a lista de ROIs, o gráfico e a tabela de resultados. Sai de lá um CSV, uma imagem do
gráfico ou um texto pronto para o laudo — **nada vai para o laudo sozinho**, é sempre botão.

A imagem mostrada é a **soma dos quadros** por padrão, não um quadro só: numa série de 2 s por
quadro, um quadro sozinho é ruído demais para desenhar um rim em cima. Dá para ver quadro a
quadro com o controle embaixo.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QSlider, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.imaging import nm, nm_exams, nm_roi
from ipe.imaging.windowing import auto_window, to_display
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

CORES = [QColor(255, 110, 110), QColor(110, 190, 255), QColor(160, 230, 140),
         QColor(255, 205, 100), QColor(210, 160, 255), QColor(120, 230, 225)]

# os nomes prontos de cada exame vivem no protocolo (imaging/nm_exams.py)


def cor(i: int) -> QColor:
    return CORES[i % len(CORES)]


# ------------------------------------------------------------------ imagem com ROIs
class RoiCanvas(QWidget):
    """Imagem da série com as regiões desenhadas por cima."""

    rois_changed = Signal()
    selected_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self.pixels: np.ndarray | None = None
        self.rois: list[nm_roi.Roi] = []
        self.selected = -1
        self.kind = "ellipse"
        self._draft: tuple[float, float] | None = None
        self._draft_to: tuple[float, float] | None = None
        self._drag: tuple[float, float] | None = None
        self._livre: list | None = None
        self.preset_names: list | None = None      # nomes prontos vindos de fora (análise entre séries)
        self._qimg: QImage | None = None

    # ---------------------------------------------------------- imagem
    def set_image(self, pixels: np.ndarray) -> None:
        self.pixels = np.asarray(pixels, np.float32)
        w, l = auto_window(self.pixels)
        from ipe.imaging.series import FrameImage
        disp = to_display(FrameImage(self.pixels, False, None, None, "", "MONOCHROME2", {}),
                          w, l, invert=True)
        h, wd = disp.shape
        self._qimg = QImage(bytes(np.ascontiguousarray(disp).data), wd, h, wd,
                            QImage.Format_Grayscale8).copy()
        self.update()

    def _rect(self) -> QRectF:
        """Onde a imagem é desenhada, mantendo a proporção."""
        if self._qimg is None:
            return QRectF(self.rect())
        iw, ih = self._qimg.width(), self._qimg.height()
        esc = min(self.width() / iw, self.height() / ih)
        w, h = iw * esc, ih * esc
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _to_img(self, x: float, y: float) -> tuple[float, float]:
        r = self._rect()
        if self._qimg is None or r.width() <= 0:
            return 0.0, 0.0
        return ((x - r.left()) / r.width() * self._qimg.width(),
                (y - r.top()) / r.height() * self._qimg.height())

    def _to_tela(self, x: float, y: float) -> QPointF:
        r = self._rect()
        if self._qimg is None:
            return QPointF(x, y)
        return QPointF(r.left() + x / self._qimg.width() * r.width(),
                       r.top() + y / self._qimg.height() * r.height())

    # ---------------------------------------------------------- mouse
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self._qimg is None:
            return
        p = self._to_img(e.position().x(), e.position().y())
        alvo = self._roi_em(p)
        if alvo >= 0 and e.button() == Qt.LeftButton and self.selected == alvo:
            self._drag = p                       # segunda vez na mesma ROI: arrasta
            return
        if alvo >= 0:
            self.selected = alvo
            self.selected_changed.emit(alvo)
            self.update()
            return
        self._draft = self._draft_to = p
        self._livre = [p] if self.kind == "freehand" else None

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._qimg is None:
            return
        p = self._to_img(e.position().x(), e.position().y())
        if self._drag is not None and 0 <= self.selected < len(self.rois):
            dx, dy = p[0] - self._drag[0], p[1] - self._drag[1]
            r = self.rois[self.selected]
            r.points = [(x + dx, y + dy) for x, y in r.points]
            self._drag = p
            self.update()
        elif self._draft is not None:
            self._draft_to = p
            if self._livre is not None:
                ult = self._livre[-1]
                if abs(p[0] - ult[0]) + abs(p[1] - ult[1]) >= 1.0:   # 1 px basta; evita milhares de pontos
                    self._livre.append(p)
            self.update()

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self.rois_changed.emit()
            return
        if self._draft is None or self._draft_to is None:
            self._draft = self._draft_to = None
            return
        livre = self._livre
        (x0, y0), (x1, y1) = self._draft, self._draft_to
        self._draft = self._draft_to = None
        self._livre = None
        if livre is not None:
            if len(livre) < 6:
                return                                   # risco curto demais: não é uma região
            self.add_roi(livre, kind="polygon")          # o traçado fecha sozinho no polígono
            return
        if abs(x1 - x0) < 3 or abs(y1 - y0) < 3:
            return
        self.add_roi([(x0, y0), (x1, y1)])

    def _roi_em(self, p: tuple[float, float]) -> int:
        if self.pixels is None:
            return -1
        for i in range(len(self.rois) - 1, -1, -1):
            res = self.rois[i].mask(self.pixels.shape[:2])
            if res is None:
                continue
            sl, m = res
            x, y = int(p[0]), int(p[1])
            if (sl[0].start <= y < sl[0].stop and sl[1].start <= x < sl[1].stop
                    and m[y - sl[0].start, x - sl[1].start]):
                return i
        return -1

    # ---------------------------------------------------------- ROIs
    def add_roi(self, pontos: list, nome: str = "", kind: str = "") -> nm_roi.Roi:
        r = nm_roi.Roi(name=nome or self._proximo_nome(), kind=kind or self.kind,
                       points=list(pontos))
        self.rois.append(r)
        self.selected = len(self.rois) - 1
        self.rois_changed.emit()
        self.selected_changed.emit(self.selected)
        self.update()
        return r

    def _proximo_nome(self) -> str:
        usados = {r.name for r in self.rois}
        prontos = getattr(self, "preset_names", None)
        if prontos is None:
            prontos = nm_exams.protocol(getattr(self, "preset", "livre")).rois
        for nome in prontos:
            if nome not in usados:
                return nome
        return f"ROI {len(self.rois) + 1}"

    def mirror_selected(self) -> nm_roi.Roi | None:
        """Espelha a ROI escolhida no eixo vertical da imagem — rim direito vira esquerdo."""
        if not (0 <= self.selected < len(self.rois)) or self.pixels is None:
            return None
        r = self.rois[self.selected]
        novo = r.mirrored(self.pixels.shape[1])
        novo.name = self._proximo_nome()
        self.rois.append(novo)
        self.selected = len(self.rois) - 1
        self.rois_changed.emit()
        self.selected_changed.emit(self.selected)
        self.update()
        return novo

    def auto_contour(self, pct: float = 40.0) -> str:
        """Troca a região escolhida por um contorno por limiar dentro dela. "" se deu certo."""
        if self.pixels is None:
            return "Sem imagem."
        if not (0 <= self.selected < len(self.rois)):
            return "Desenhe uma região grosseira em volta do alvo e escolha-a antes."
        r = self.rois[self.selected]
        if r.auto_box is not None:
            y0, y1, x0, x1 = r.auto_box       # refaz sempre na caixa original: mexer no limiar
            sl = (slice(y0, y1), slice(x0, x1))   # para baixo precisa poder crescer de novo
            dentro = np.zeros(self.pixels.shape[:2], bool)
            dentro[sl] = True
        else:
            caixa = r.mask(self.pixels.shape[:2])
            if caixa is None:
                return "Esta região está fora da imagem."
            sl, m = caixa
            dentro = np.zeros(self.pixels.shape[:2], bool)
            dentro[sl] = m
            r.auto_box = (sl[0].start, sl[0].stop, sl[1].start, sl[1].stop)
        sub = np.where(dentro, self.pixels, -np.inf)
        yy, xx = np.unravel_index(int(np.argmax(sub)), sub.shape)
        mascara = nm_roi.grow_from(self.pixels, (xx, yy), pct, box=sl)
        if mascara is None:
            return "Não achei nada acima do limiar dentro desta região."
        mascara = mascara & dentro                     # não escapa da caixa que você desenhou
        r.auto_mask = mascara
        r.kind = "auto"
        r.auto_pct = pct
        self.rois_changed.emit()
        self.update()
        return ""

    def remove_selected(self) -> None:
        if 0 <= self.selected < len(self.rois):
            del self.rois[self.selected]
            self.selected = min(self.selected, len(self.rois) - 1)
            self.rois_changed.emit()
            self.selected_changed.emit(self.selected)
            self.update()

    # ---------------------------------------------------------- desenho
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(18, 18, 20))
        if self._qimg is None:
            p.setPen(QColor(170, 170, 170))
            p.drawText(self.rect(), Qt.AlignCenter, "Sem imagem")
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(self._rect(), QPixmap.fromImage(self._qimg), QRectF(self._qimg.rect()))
        f = QFont()
        f.setPointSize(9)
        p.setFont(f)
        for i, r in enumerate(self.rois):
            c = cor(i)
            p.setPen(QPen(c, 3 if i == self.selected else 2))
            if r.is_auto:
                self._desenha_mascara(p, r.auto_mask, c, i == self.selected)
                ys, xs = np.nonzero(r.auto_mask)
                if xs.size:
                    q = self._to_tela(float(xs.min()), float(ys.min()))
                    p.setPen(c)
                    p.drawText(QPointF(q.x(), q.y() - 4), f"{r.name} · limiar {r.auto_pct:.0f}%")
                continue
            self._desenha(p, r.kind, r.points)
            if r.points:
                q = self._to_tela(min(x for x, _ in r.points), min(y for _, y in r.points))
                p.setPen(c)
                p.drawText(QPointF(q.x(), q.y() - 4), r.name)
        if self._livre and len(self._livre) > 1:
            p.setPen(QPen(QColor(255, 255, 255), 1.5))
            p.drawPolyline(QPolygonF([self._to_tela(*q) for q in self._livre]))
        elif self._draft and self._draft_to:
            p.setPen(QPen(QColor(255, 255, 255), 1, Qt.DashLine))
            self._desenha(p, self.kind, [self._draft, self._draft_to])

    def _desenha_mascara(self, p: QPainter, mask, c: QColor, ativa: bool) -> None:
        """Borda da máscara, pixel a pixel — um contorno por limiar não é uma figura."""
        borda = nm_roi.mask_outline(mask)
        ys, xs = np.nonzero(borda)
        if not xs.size:
            return
        r = self._rect()
        lado = max(1.0, r.width() / max(1, mask.shape[1]))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 255 if ativa else 190))
        for x, y in zip(xs.tolist(), ys.tolist()):
            q = self._to_tela(x, y)
            p.drawRect(QRectF(q.x(), q.y(), lado, lado))
        p.setBrush(Qt.NoBrush)

    def _desenha(self, p: QPainter, kind: str, pontos: list) -> None:
        if len(pontos) < 2:
            return
        a, b = self._to_tela(*pontos[0]), self._to_tela(*pontos[1])
        r = QRectF(a, b).normalized()
        if kind == "rect":
            p.drawRect(r)
        elif kind == "ellipse":
            p.drawEllipse(r)
        else:
            p.drawPolygon(QPolygonF([self._to_tela(*q) for q in pontos]))


# ------------------------------------------------------------------ gráfico
class CurveChart(QWidget):
    """Curvas atividade-tempo, uma linha por ROI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 240)
        self.curves: list[nm_roi.Curve] = []
        self.cps = True
        self.marks: list[tuple[float, str]] = []

    def set_curves(self, curves: list[nm_roi.Curve], cps: bool = True,
                   marks: list[tuple[float, str]] | None = None) -> None:
        self.curves, self.cps, self.marks = curves, cps, marks or []
        self.update()

    def _valores(self, c: nm_roi.Curve) -> np.ndarray:
        return c.cps if self.cps else c.counts

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(24, 24, 26))
        if not self.curves or not any(c.counts.size for c in self.curves):
            p.setPen(QColor(170, 170, 170))
            p.drawText(self.rect(), Qt.AlignCenter, "Desenhe uma região para ver a curva")
            return
        m = QRectF(62, 14, self.width() - 78, self.height() - 54)
        tmax = max((float(c.times_s[-1]) for c in self.curves if c.times_s.size), default=1.0) or 1.0
        ymax = max((float(self._valores(c).max()) for c in self.curves if c.counts.size), default=1.0)
        ymax = ymax * 1.12 or 1.0

        def pt(t, y) -> QPointF:
            return QPointF(m.left() + t / tmax * m.width(), m.bottom() - y / ymax * m.height())
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        for k in range(6):
            y = ymax * k / 5
            yy = pt(0, y).y()
            p.setPen(QColor(64, 64, 68))
            p.drawLine(QPointF(m.left(), yy), QPointF(m.right(), yy))
            p.setPen(QColor(170, 170, 170))
            p.drawText(QRectF(0, yy - 8, 56, 16), Qt.AlignRight | Qt.AlignVCenter, f"{y:,.0f}".replace(",", " "))
        for k in range(6):
            t = tmax * k / 5
            p.setPen(QColor(170, 170, 170))
            p.drawText(QRectF(pt(t, 0).x() - 30, m.bottom() + 4, 60, 16), Qt.AlignCenter,
                       f"{t / 60:.1f} min")
        p.setPen(QPen(QColor(120, 120, 120)))
        p.drawRect(m)
        for t, texto in self.marks:
            if 0 <= t <= tmax:
                x = pt(t, 0).x()
                p.setPen(QPen(QColor(200, 200, 120), 1, Qt.DashLine))
                p.drawLine(QPointF(x, m.top()), QPointF(x, m.bottom()))
                p.setPen(QColor(200, 200, 120))
                p.drawText(QPointF(x + 3, m.top() + 12), texto)
        for i, c in enumerate(self.curves):
            if not c.counts.size:
                continue
            v = self._valores(c)
            p.setPen(QPen(cor(i), 2.2))
            p.drawPolyline(QPolygonF([pt(float(t), float(y)) for t, y in zip(c.times_s, v)]))
        leg = m.top() + 4
        for i, c in enumerate(self.curves):
            p.setPen(cor(i))
            p.drawText(QPointF(m.right() - 150, leg), c.name)
            leg += 14
        p.setPen(QColor(190, 190, 190))
        p.drawText(QRectF(m.left(), m.bottom() + 22, m.width(), 16), Qt.AlignCenter,
                   "contagens por segundo" if self.cps else "contagens por quadro")


# ------------------------------------------------------------------ imagem condensada
class CondensedDialog(QDialog):
    """Cada quadro vira uma coluna: o tempo passa a ser o eixo horizontal.

    É como se lê refluxo esofágico e trânsito — o bolo subindo e descendo aparece numa figura
    só, sem precisar rodar o cine quadro a quadro.
    """

    def __init__(self, img, info: nm.NMInfo, frames: list, roi_nome: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Imagem condensada")
        self.resize(760, 520)
        self.img = np.asarray(img, np.float32)
        lay = QVBoxLayout(self)
        fonte = f"Região: {roi_nome}." if roi_nome else "Imagem inteira (escolha uma região para limitar)."
        dur = info.mid_times_s([f.frame_index for f in frames])
        total = f"{dur[-1] / 60:.1f} min" if dur else "?"
        cab = QLabel(f"{len(frames)} quadros em {total}. {fonte}")
        cab.setWordWrap(True)
        lay.addWidget(cab)
        self.tela = _CondensedView(self.img)
        lay.addWidget(self.tela, 1)
        pe = QLabel("Horizontal: tempo, um quadro por coluna. Vertical: a anatomia, somada no "
                    "outro eixo. Escala de cinza invertida, como o resto da medicina nuclear.")
        pe.setWordWrap(True)
        lay.addWidget(pe)
        bb = QDialogButtonBox()
        b = bb.addButton("Salvar imagem…", QDialogButtonBox.ActionRole)
        b.clicked.connect(self.salvar)
        bb.addButton(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def salvar(self) -> None:
        caminho, _f = QFileDialog.getSaveFileName(self, "Salvar imagem condensada",
                                                  "condensada.png", "Imagem (*.png)")
        if not caminho:
            return
        from ipe.imaging.windowing import encode_png
        with open(caminho, "wb") as fh:
            fh.write(encode_png(_oito_bits(self.img)))


def _oito_bits(img) -> np.ndarray:
    """Imagem em 8 bits, invertida (captação escura), para desenhar e salvar."""
    from ipe.imaging.series import FrameImage
    w, l = auto_window(np.asarray(img, np.float32))
    return to_display(FrameImage(np.asarray(img, np.float32), False, None, None, "",
                                 "MONOCHROME2", {}), w, l, invert=True)


class _CondensedView(QWidget):
    def __init__(self, img, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 260)
        disp = _oito_bits(img)
        h, w = disp.shape
        self._q = QImage(bytes(np.ascontiguousarray(disp).data), w, h, w,
                         QImage.Format_Grayscale8).copy()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(18, 18, 20))
        if self._q.isNull():
            return
        # poucos quadros: sem suavizar, para cada coluna aparecer como o quadro que ela é
        p.setRenderHint(QPainter.SmoothPixmapTransform, self._q.width() >= 60)
        p.drawPixmap(QRectF(self.rect()), QPixmap.fromImage(self._q), QRectF(self._q.rect()))


# ------------------------------------------------------------------ janela
class NMAnalysisDialog(QDialog):
    """Análise de uma série dinâmica de medicina nuclear."""

    def __init__(self, frames: list, cache, titulo: str, info: nm.NMInfo | None = None,
                 preset: str = "livre", parent=None, tab=None):
        super().__init__(parent)
        self.tab = tab if tab is not None else parent
        self.setWindowTitle(f"Medicina nuclear — {titulo}")
        self.resize(1180, 720)
        self.frames, self.cache = frames, cache
        self.info = info or (nm.info_for_file(frames[0].path) if frames else nm.NMInfo())
        self.preset = preset
        self.curvas: list[nm_roi.Curve] = []
        self.resultado: renogram.RenogramResult | None = None

        self.canvas = RoiCanvas()
        self.canvas.preset = preset
        self.chart = CurveChart()
        self.tabela = QTableWidget(0, 1)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.setMaximumHeight(150)
        colunas_ajustaveis(self.tabela)
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color:#e0c070;")
        self.referencia = QLabel()
        self.referencia.setWordWrap(True)
        self.referencia.setStyleSheet("color:#9fb8cc;")

        self._monta()
        self._soma_quadros()
        self.canvas.rois_changed.connect(self.recalcular)
        self.canvas.selected_changed.connect(self._mostra_roi)
        self._exame_mudou()      # já esconde o que este exame não pergunta, e calcula

    # ---------------------------------------------------------- layout
    def _monta(self) -> None:
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)

        esq = QWidget()
        ve = QVBoxLayout(esq)
        ve.setContentsMargins(0, 0, 0, 0)
        ve.addWidget(self.canvas, 1)
        barra = QHBoxLayout()
        self.forma = QComboBox()
        self.forma.addItem("Elipse", "ellipse")
        self.forma.addItem("Retângulo", "rect")
        self.forma.addItem("Mão livre", "freehand")
        self.forma.currentIndexChanged.connect(
            lambda: setattr(self.canvas, "kind", self.forma.currentData()))
        barra.addWidget(QLabel("Forma:"))
        barra.addWidget(self.forma)
        b = QPushButton("Contorno automático")
        b.setToolTip("Desenhe uma região grosseira em volta do alvo e clique aqui: o contorno "
                     "segue o limiar em % do máximo daquela região, sem escapar dela.")
        b.clicked.connect(self._contorno)
        barra.addWidget(b)
        self.limiar = QSpinBox()
        self.limiar.setRange(5, 95)
        self.limiar.setValue(40)
        self.limiar.setSuffix("% do máximo")
        self.limiar.setToolTip("40% do máximo é o limiar mais usado em medicina nuclear.")
        self.limiar.valueChanged.connect(self._limiar_mudou)
        barra.addWidget(self.limiar)
        b = QPushButton("Espelhar D/E")
        b.setToolTip("Cria a região do outro lado, espelhada no eixo vertical da imagem.")
        b.clicked.connect(self._espelhar)
        barra.addWidget(b)
        b = QPushButton("Apagar região")
        b.clicked.connect(self.canvas.remove_selected)
        barra.addWidget(b)
        b = QPushButton("Imagem condensada…")
        b.setToolTip("Cada quadro vira uma coluna: o tempo passa a ser o eixo horizontal. "
                     "É como se lê refluxo e trânsito sem rodar o cine.")
        b.clicked.connect(self.mostrar_condensada)
        barra.addWidget(b)
        barra.addStretch(1)
        ve.addLayout(barra)
        quadro = QHBoxLayout()
        self.somar = QCheckBox("Somar todos os quadros")
        self.somar.setChecked(True)
        self.somar.setToolTip("Um quadro de 2 s sozinho é ruído demais para desenhar em cima.")
        self.somar.toggled.connect(self._soma_quadros)
        quadro.addWidget(self.somar)
        self.desliza = QSlider(Qt.Horizontal)
        self.desliza.setRange(0, max(0, len(self.frames) - 1))
        self.desliza.valueChanged.connect(self._quadro_mudou)
        quadro.addWidget(self.desliza, 1)
        self.rotulo_quadro = QLabel()
        quadro.addWidget(self.rotulo_quadro)
        ve.addLayout(quadro)
        split.addWidget(esq)

        dir_ = QWidget()
        vd = QVBoxLayout(dir_)
        vd.setContentsMargins(0, 0, 0, 0)
        exame = QHBoxLayout()
        exame.addWidget(QLabel("Exame:"))
        self.exame = QComboBox()
        for chave in nm_exams.ORDER:
            self.exame.addItem(nm_exams.PROTOCOLS[chave].name, chave)
        i = self.exame.findData(self.preset)
        self.exame.setCurrentIndex(max(0, i))
        self.exame.currentIndexChanged.connect(self._exame_mudou)
        exame.addWidget(self.exame, 1)
        self.rotulo_estimulo = QLabel()
        exame.addWidget(self.rotulo_estimulo)
        self.estimulo = QDoubleSpinBox()
        self.estimulo.setRange(0.0, 600.0)
        self.estimulo.setDecimals(1)
        self.estimulo.setSuffix(" min")
        self.estimulo.setToolTip("Instante do estímulo, contado do começo da série.")
        self.estimulo.valueChanged.connect(self.recalcular)
        exame.addWidget(self.estimulo)
        vd.addLayout(exame)
        fundo = QHBoxLayout()
        fundo.addWidget(QLabel("Fundo da região:"))
        self.metodo = QComboBox()
        for chave, (nome, _precisa) in nm_roi.BACKGROUND_METHODS.items():
            self.metodo.addItem(nome, chave)
        self.metodo.currentIndexChanged.connect(self._fundo_mudou)
        fundo.addWidget(self.metodo, 1)
        self.roi_fundo = QComboBox()
        self.roi_fundo.currentIndexChanged.connect(self._fundo_mudou)
        fundo.addWidget(self.roi_fundo, 1)
        self.anel = QSpinBox()
        self.anel.setRange(1, 20)
        self.anel.setValue(3)
        self.anel.setSuffix(" px")
        self.anel.valueChanged.connect(self._fundo_mudou)
        fundo.addWidget(self.anel)
        self.fracao = QDoubleSpinBox()
        self.fracao.setRange(0.0, 0.95)
        self.fracao.setSingleStep(0.05)
        self.fracao.setDecimals(2)
        self.fracao.valueChanged.connect(self._fundo_mudou)
        fundo.addWidget(self.fracao)
        vd.addLayout(fundo)
        opcoes = QHBoxLayout()
        self.em_cps = QCheckBox("Contagens por segundo")
        self.em_cps.setChecked(True)
        self.em_cps.setToolTip("Sem isso, a mudança de duração entre as fases vira um degrau falso.")
        self.em_cps.toggled.connect(self.recalcular)
        opcoes.addWidget(self.em_cps)
        self.decaimento = QCheckBox("Corrigir decaimento")
        self.decaimento.toggled.connect(self.recalcular)
        opcoes.addWidget(self.decaimento)
        opcoes.addStretch(1)
        vd.addLayout(opcoes)
        vd.addWidget(self.chart, 1)
        vd.addWidget(self.tabela)
        vd.addWidget(self.aviso)
        vd.addWidget(self.referencia)
        split.addWidget(dir_)
        split.setSizes([520, 660])
        lay.addWidget(split, 1)

        bb = QDialogButtonBox()
        self.b_csv = bb.addButton("Exportar CSV…", QDialogButtonBox.ActionRole)
        self.b_csv.clicked.connect(self.exportar_csv)
        self.b_laudo = bb.addButton("Mandar para o laudo", QDialogButtonBox.ActionRole)
        self.b_laudo.clicked.connect(self.para_o_laudo)
        bb.addButton(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        nota = QLabel("Os números saem das regiões desenhadas aqui. Valores de referência dependem "
                      "do protocolo do serviço e não estão no programa. "
                      "Ferramenta de pesquisa e ensino, não destinada a uso diagnóstico.")
        nota.setWordWrap(True)
        lay.addWidget(nota)

    # ---------------------------------------------------------- imagem
    def _soma_quadros(self) -> None:
        if not self.frames:
            return
        if self.somar.isChecked() if hasattr(self, "somar") else True:
            acc = None
            for f in self.frames:
                px = self.cache.get(f).pixels
                if px.ndim != 2:
                    px = px.astype(np.float32).mean(axis=2)
                acc = px.astype(np.float32) if acc is None else acc + px
            self.canvas.set_image(acc)
            self.rotulo_quadro.setText(f"{len(self.frames)} quadros somados")
        else:
            self._quadro_mudou(self.desliza.value())

    def _quadro_mudou(self, i: int) -> None:
        if not self.frames or (hasattr(self, "somar") and self.somar.isChecked()):
            return
        i = max(0, min(i, len(self.frames) - 1))
        px = self.cache.get(self.frames[i]).pixels
        if px.ndim != 2:
            px = px.astype(np.float32).mean(axis=2)
        self.canvas.set_image(px)
        t = self.info.mid_times_s([f.frame_index for f in self.frames])
        if i < len(t):
            self.rotulo_quadro.setText(f"Quadro {i + 1}/{len(self.frames)} · {t[i]:.0f} s")
        else:
            self.rotulo_quadro.setText(f"Quadro {i + 1}/{len(self.frames)}")

    # ---------------------------------------------------------- ROIs
    def _contorno(self) -> None:
        erro = self.canvas.auto_contour(float(self.limiar.value()))
        if erro:
            QMessageBox.information(self, "Contorno automático", erro)

    def _limiar_mudou(self, v: int) -> None:
        """Mexer no limiar refaz o contorno da região escolhida, se ela já for automática."""
        i = self.canvas.selected
        if 0 <= i < len(self.canvas.rois) and self.canvas.rois[i].is_auto:
            self.canvas.auto_contour(float(v))

    def _espelhar(self) -> None:
        if self.canvas.mirror_selected() is None:
            QMessageBox.information(self, "Espelhar", "Escolha uma região antes de espelhar.")

    def _mostra_roi(self, i: int) -> None:
        self.roi_fundo.blockSignals(True)
        self.roi_fundo.clear()
        for r in self.canvas.rois:
            self.roi_fundo.addItem(r.name)
        self.roi_fundo.blockSignals(False)
        if not (0 <= i < len(self.canvas.rois)):
            return
        r = self.canvas.rois[i]
        self.metodo.blockSignals(True)
        idx = self.metodo.findData(r.background)
        self.metodo.setCurrentIndex(max(0, idx))
        self.metodo.blockSignals(False)
        self.anel.setValue(r.ring_px)
        self.fracao.setValue(r.fraction)
        j = self.roi_fundo.findText(r.background_roi)
        if j >= 0:
            self.roi_fundo.setCurrentIndex(j)
        self._ajusta_campos()

    def _ajusta_campos(self) -> None:
        metodo = self.metodo.currentData()
        self.roi_fundo.setVisible(metodo == "roi")
        self.anel.setVisible(metodo == "ring")
        self.fracao.setVisible(metodo == "fraction")

    def _fundo_mudou(self) -> None:
        i = self.canvas.selected
        if 0 <= i < len(self.canvas.rois):
            r = self.canvas.rois[i]
            r.background = self.metodo.currentData() or "none"
            r.background_roi = self.roi_fundo.currentText()
            r.ring_px = self.anel.value()
            r.fraction = self.fracao.value()
        self._ajusta_campos()
        self.recalcular()

    # ---------------------------------------------------------- contas
    def _exame_mudou(self) -> None:
        """Trocar o exame troca os nomes prontos, a conta e o que a janela pergunta."""
        self.preset = self.exame.currentData() or "livre"
        self.canvas.preset = self.preset
        p = nm_exams.protocol(self.preset)
        self.estimulo.setVisible(p.needs_stimulus)
        self.rotulo_estimulo.setVisible(p.needs_stimulus)
        self.rotulo_estimulo.setText(p.stimulus_label)
        self.recalcular()

    def recalcular(self) -> None:
        if not self.canvas.rois:
            self.curvas = []
            self.chart.set_curves([])
            self.tabela.setRowCount(0)
            self.aviso.setText("")
            self.referencia.setText("")
            return
        self.curvas = nm_roi.curves(self.frames, self.cache, self.canvas.rois, self.info,
                                    decay=self.decaimento.isChecked())
        mostrar = [c for c in self.curvas if any(r.name == c.name and r.role != "fundo"
                                                 for r in self.canvas.rois)]
        marcas = []
        p = nm_exams.protocol(self.preset)
        if p.needs_stimulus and self.estimulo.value() > 0:
            marcas = [(self.estimulo.value() * 60.0, p.stimulus_label or "Estímulo")]
        self.chart.set_curves(mostrar, self.em_cps.isChecked(), marcas)
        self.resultado = nm_exams.run(self.preset, mostrar, self.estimulo.value() * 60.0)
        self._preenche_tabela()
        self._mostra_roi(self.canvas.selected)   # a caixa nunca diz um fundo diferente do usado

    def _preenche_tabela(self) -> None:
        res = self.resultado
        if res is None:
            self.tabela.setRowCount(0)
            return
        self.tabela.setColumnCount(max(1, len(res.headers)))
        self.tabela.setHorizontalHeaderLabels(res.headers)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.setRowCount(len(res.rows))
        for i, linha in enumerate(res.rows):
            for j, v in enumerate(linha):
                self.tabela.setItem(i, j, QTableWidgetItem(v))
        avisos = [a for a in res.notes if a]
        avisos += [c.note for c in self.curvas if c.note]
        self.aviso.setText(" ".join(dict.fromkeys(avisos)))
        self.referencia.setText(res.reference)

    def mostrar_condensada(self) -> None:
        """Imagem condensada da série (tempo no eixo horizontal)."""
        roi = None
        i = self.canvas.selected
        if 0 <= i < len(self.canvas.rois):
            roi = self.canvas.rois[i]
        img = nm_roi.condensed(self.frames, self.cache, roi=roi)
        if img.size <= 1:
            QMessageBox.information(self, "Imagem condensada", "Não deu para montar a imagem.")
            return
        dlg = CondensedDialog(img, self.info, self.frames,
                              roi.name if roi is not None else "", self)
        dlg.exec()

    # ---------------------------------------------------------- saídas
    def exportar_csv(self) -> None:
        if not self.curvas:
            QMessageBox.information(self, "Exportar", "Não há curva para exportar.")
            return
        caminho, _f = QFileDialog.getSaveFileName(self, "Salvar tabela", "curvas.csv",
                                                  "Planilha (*.csv)")
        if not caminho:
            return
        texto = nm_roi.to_csv(self.curvas, self.em_cps.isChecked())
        with open(caminho, "w", encoding="utf-8-sig") as fh:
            fh.write(texto)

    def report_text(self) -> str:
        return self.resultado.text if self.resultado else ""

    def para_o_laudo(self) -> None:
        texto = self.report_text()
        if not texto:
            QMessageBox.information(self, "Laudo", "Não há números para mandar ao laudo.")
            return
        alvo = getattr(self.tab, "append_to_report", None)
        enviado = bool(callable(alvo) and alvo(texto))
        if not enviado:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(texto)
            QMessageBox.information(self, "Laudo",
                                    "O texto foi copiado; cole no laudo onde quiser.")
        else:
            QMessageBox.information(self, "Laudo", "Os números foram para o laudo.")
