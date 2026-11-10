"""Avaliação dinâmica de RM de mama no visualizador: escolha das fases, mapas MSI/PEI/SER
e painel com as curvas tempo-intensidade dos pontos e ROIs desenhados nos quadros."""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.core.i18n import tr
from ipe.imaging import measure as M
from ipe.imaging import phases as PH
from ipe.imaging.dynamic import MAPS, DynamicMaps, DynamicSet, split_single_series
from ipe.imaging.series import build_frames
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

CURVE_COLORS = [QColor(255, 90, 90), QColor(80, 200, 255), QColor(120, 255, 120), QColor(255, 200, 60),
                QColor(220, 120, 255), QColor(255, 140, 200), QColor(160, 255, 230), QColor(255, 255, 255)]
ROI_KINDS = ("ellipse", "rect", "polygon", "tic")
# Os layouts de fábrica, na forma antiga (rótulo, vistas). Desde a 0.99.9 os layouts são dele
# (Preferências ▸ Dinâmica da mama, `dinamica_config`); esta lista fica para quem ainda a lê.
from ipe.ui.viewer import dinamica_config as DC  # noqa: E402

LAYOUTS = [(lay["nome"], [q["vista"] for q in lay["quadros"]]) for lay in DC.FABRICA]


def fmt_time(s: float) -> str:
    s = max(0.0, float(s))
    return f"{int(s // 60)}:{int(round(s % 60)):02d}"


# ====================================================================== diálogo
class DynamicDialog(QDialog):
    """Escolhe as séries (fases) e os parâmetros dos mapas."""

    def __init__(self, tab, preselect: list[str] | None = None, previous: dict | None = None):
        super().__init__(tab)
        self.tab = tab
        self.setWindowTitle("Avaliação dinâmica — MSI, PEI e SER")
        self.resize(640, 640)
        self._frames: dict[str, list] = {}
        self.dset: DynamicSet | None = None
        prev = previous or {}
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Marque as séries da dinâmica (pré-contraste e pós-contraste). Uma série só com "
                             "todas as fases também serve. A ordem segue o horário de aquisição."))
        self.list = QListWidget()
        mr = [s for s in tab.series if s.modality == "MR"] or list(tab.series)
        for s in mr:
            it = QListWidgetItem(f"Se {s.series_number}  {s.description}  ({s.num_images} im)")
            it.setData(Qt.UserRole, s.series_uid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if preselect and s.series_uid in preselect else Qt.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        b_auto = QPushButton("Detectar automaticamente")
        b_auto.clicked.connect(self.autodetect)
        row.addWidget(b_auto)
        row.addStretch(1)
        lay.addLayout(row)
        self.phase_info = QLabel("")
        self.phase_info.setWordWrap(True)
        self.phase_info.setTextFormat(Qt.RichText)
        lay.addWidget(self.phase_info)

        g = QGroupBox("Parâmetros")
        f = QFormLayout(g)
        self.c_pre, self.c_early, self.c_late = QComboBox(), QComboBox(), QComboBox()
        f.addRow("Pré-contraste:", self.c_pre)
        f.addRow("Fase inicial (SER, realce inicial):", self.c_early)
        f.addRow("Fase tardia (SER):", self.c_late)
        # 0.99.48 (plano AW M4): linha de base pela média das fases pré e fases fora da conta
        self.c_base_media = QCheckBox("Linha de base: média de todas as fases até a pré-contraste escolhida")
        self.c_base_media.setChecked(bool(prev.get("base_media", False)))
        self.c_base_media.setToolTip("Com duas fases pré-contraste ou mais, a média delas tem menos ruído que uma "
                                     "fase só. Com uma fase pré, o painel avisa.")
        f.addRow(self.c_base_media)
        self.e_excluir = QLineEdit(", ".join(str(i + 1) for i in prev.get("excluidas", []) or []))
        self.e_excluir.setPlaceholderText("ex.: 4  ou  4, 7")
        self.e_excluir.setToolTip("Fases com movimento que saem da conta dos mapas e das curvas (o número da "
                                  "fase, como na lista). Não pode ser a inicial, a tardia, nem duas seguidas.")
        f.addRow("Fases fora da conta (movimento):", self.e_excluir)
        self.s_thr = QDoubleSpinBox(minimum=0, maximum=500, value=float(prev.get("threshold_pct", 50)),
                                    suffix=" %", decimals=0, singleStep=10)
        self.s_thr.setToolTip("Realce inicial mínimo para calcular o SER (fora disso o mapa fica preto).")
        f.addRow("Limiar de realce inicial:", self.s_thr)
        self.c_thr_all = QCheckBox("Aplicar o limiar também em MSI, PEI, realce inicial e TTP")
        self.c_thr_all.setChecked(bool(prev.get("threshold_all", False)))
        f.addRow(self.c_thr_all)
        self.s_noise = QDoubleSpinBox(minimum=0, maximum=50, value=float(prev.get("noise_pct", 5)),
                                      suffix=" % do máximo", decimals=1)
        self.s_noise.setToolTip("Pixels com sinal abaixo disso (ar, fundo) ficam de fora dos mapas.")
        f.addRow("Ignorar sinal abaixo de:", self.s_noise)
        self.s_rapido = QDoubleSpinBox(minimum=50, maximum=1000, value=float(prev.get("rapido_pct", 100)),
                                       suffix=" %", decimals=0, singleStep=10)
        self.s_rapido.setToolTip("Acima disso o realce é “rápido”; entre o limiar de realce inicial e este "
                                 "valor é “médio”. Convenção do CADstream: 50–100% médio, acima de 100% rápido.")
        f.addRow("Mapa cinético — realce rápido acima de:", self.s_rapido)
        self.s_tardio = QDoubleSpinBox(minimum=1, maximum=50, value=float(prev.get("tardio_pct", 10)),
                                       suffix=" %", decimals=0)
        self.s_tardio.setToolTip("Variação do sinal da fase tardia em relação à de pico: acima disso "
                                 "persistente, abaixo do negativo washout, no meio platô.")
        f.addRow("Mapa cinético — faixa do platô:", self.s_tardio)
        self.s_sinal = QDoubleSpinBox(minimum=0, maximum=60, value=float(prev.get("sinal_min_pct", 10)),
                                      suffix=" % da referência", decimals=0)
        self.s_sinal.setToolTip("Máscara de tecido do mapa cinético: só entram voxels cujo pré-contraste "
                                "chegue a esta fração do sinal de referência do exame. Sem máscara, a "
                                "classificação em porcentagem acende o ar e o pulmão.")
        f.addRow("Mapa cinético — tecido com pré ≥:", self.s_sinal)
        self.c_units = QComboBox()
        self.c_units.addItem("Relativos ao pré-contraste (%)", True)
        self.c_units.addItem("Absolutos (sinal)", False)
        self.c_units.setCurrentIndex(0 if prev.get("relative", True) else 1)
        f.addRow("Mapas MSI/PEI:", self.c_units)
        self.c_motion = QCheckBox("Corrigir movimento entre as fases (translação 3D)")
        self.c_motion.setChecked(bool(prev.get("motion", False)))
        self.c_motion.setToolTip("Estima o deslocamento de cada fase em relação à pré-contraste e alinha "
                                 "antes de calcular mapas e curvas. A rotação entra com a opção abaixo; "
                                 "deformação não é corrigida.")
        f.addRow(self.c_motion)
        self.c_rigido = QCheckBox("Incluir rotação (registro rígido, mais lento)")
        self.c_rigido.setChecked(bool(prev.get("motion_rigido", False)))
        self.c_rigido.setToolTip("Além da translação, procura a rotação de cada fase (até uns 40 s por "
                                 "fase). Só reamostra em 3D a fase que girou 0,75° ou mais; nas RM de "
                                 "mama medidas a rotação entre as fases não passou de 0,5°.")
        self.c_rigido.setEnabled(self.c_motion.isChecked())
        self.c_motion.toggled.connect(self.c_rigido.setEnabled)
        f.addRow(self.c_rigido)
        self.c_layout = QComboBox()
        lista = DC.nomes(tab.settings)
        for label in lista:
            self.c_layout.addItem(label)
        i_lay = lista.index(prev["layout_nome"]) if prev.get("layout_nome") in lista else \
            int(prev.get("layout", DC.indice_padrao(tab.settings)))
        self.c_layout.setCurrentIndex(max(0, min(i_lay, len(lista) - 1)))
        self.c_layout.setToolTip("Os layouts (quadros, mapas, séries e cores) se montam em "
                                 "Preferências ▸ Dinâmica da mama.")
        f.addRow("Layout:", self.c_layout)
        lay.addWidget(g)
        note = QLabel("<small>Mapa cinético: a cor diz o comportamento tardio (azul persistente, verde "
                      "platô, vermelho washout) e o brilho diz a intensidade do realce (escuro médio, "
                      "vivo rápido). MSI = maior inclinação de subida; PEI = integral do realce positivo; "
                      "SER = (inicial − pré)/(tardia − pré): &lt; 0,9 persistente, 0,9–1,1 platô, "
                      "&gt; 1,1 washout. Pesquisa e ensino — não destinado a uso diagnóstico.</small>")
        note.setWordWrap(True)
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Gerar mapas")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._prev = prev
        self.list.itemChanged.connect(lambda _it: self.rebuild())
        if not preselect:
            self.autodetect()
        else:
            self.rebuild()

    # ------------------------------------------------------------------
    def _frames_of(self, uid: str) -> list:
        if uid not in self._frames:
            self._frames[uid] = build_frames(self.tab.repo.instances_for_series(uid), uid)
        return self._frames[uid]

    def checked(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def autodetect(self) -> None:
        cands = []
        for i in range(self.list.count()):
            uid = self.list.item(i).data(Qt.UserRole)
            s = self.tab._series_row(uid)
            cands.append((uid, self._frames_of(uid), s.series_number if s else 0, s.modality if s else "",
                          s.description if s else ""))
        groups = PH.detect(cands)
        pick: list[str] = max(groups, key=len) if groups else []
        if not pick:        # série única com várias fases
            best = max(((c[0], split_single_series(c[1])) for c in cands),
                       key=lambda x: len(x[1]) if x[1] else 0, default=(None, None))
            if best[1]:
                pick = [best[0]]
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setCheckState(Qt.Checked if it.data(Qt.UserRole) in pick else Qt.Unchecked)
        self.list.blockSignals(False)
        self.rebuild()

    def rebuild(self) -> None:
        uids = self.checked()
        self.dset = None
        for c in (self.c_pre, self.c_early, self.c_late):
            c.clear()
        if not uids:
            self.phase_info.setText("<i>Nenhuma série marcada.</i>")
            return
        if len(uids) == 1:
            ph = split_single_series(self._frames_of(uids[0]))
            if not ph:
                self.phase_info.setText("<span style='color:#f88'>Esta série não tem fases repetidas; "
                                        "marque as outras séries da dinâmica.</span>")
                return
            s = self.tab._series_row(uids[0])
            labels = [f"Fase {i + 1}" + (f" (Se {s.series_number})" if s else "") for i in range(len(ph))]
            dset = DynamicSet(ph, labels)
        else:
            phases, labels = [], []
            for uid in uids:
                s = self.tab._series_row(uid)
                phases.append(self._frames_of(uid))
                labels.append(f"Se {s.series_number} {s.description}".strip() if s else uid[-8:])
            dset = DynamicSet(phases, labels)
        why = dset.check()
        if why:
            self.phase_info.setText(f"<span style='color:#f88'>{why}</span>")
            return
        self.dset = dset
        items = [f"{i + 1} — {lab}  ({fmt_time(t)})" for i, (lab, t) in enumerate(zip(dset.labels, dset.times))]
        for c in (self.c_pre, self.c_early, self.c_late):
            c.addItems(items)
        pre = min(int(self._prev.get("pre", 0)), len(items) - 1)
        self.c_pre.setCurrentIndex(pre)
        self.c_early.setCurrentIndex(dset.default_early(pre))
        self.c_late.setCurrentIndex(len(items) - 1)
        warn = "" if dset.timed else ("<br><span style='color:#fc6'>Sem horário de aquisição distinto: "
                                     "fases a cada 1 min, na ordem das séries.</span>")
        self.phase_info.setText(f"<b>{len(items)} fases</b>, {dset.n_slices} cortes cada; duração "
                                f"{fmt_time(dset.times[-1])}.{warn}")

    def _ok(self) -> None:
        if self.dset is None:
            QMessageBox.information(self, "Dinâmica", self.phase_info.text() or "Escolha as séries.")
            return
        pre, early, late = self.c_pre.currentIndex(), self.c_early.currentIndex(), self.c_late.currentIndex()
        if not pre < early <= late:
            QMessageBox.information(self, "Dinâmica", "A fase inicial deve vir depois do pré-contraste, "
                                    "e a tardia não pode vir antes da inicial.")
            return
        ex = self.excluidas()
        if ex is None:
            QMessageBox.information(self, "Dinâmica", "Fases fora da conta: escreva os números das fases, "
                                    "separados por vírgula.")
            return
        motivo = validar_exclusao(len(self.dset.phases), pre, early, late, self.fases_pre(), ex)
        if motivo:
            QMessageBox.information(self, "Dinâmica", motivo)
            return
        self.accept()

    def excluidas(self) -> list[int] | None:
        txt = self.e_excluir.text().replace(";", ",").replace(" ", ",")
        try:
            return sorted({int(x) - 1 for x in txt.split(",") if x.strip()})
        except ValueError:
            return None

    def fases_pre(self) -> list[int]:
        pre = self.c_pre.currentIndex()
        return list(range(pre + 1)) if self.c_base_media.isChecked() else [pre]

    def params(self) -> dict:
        return {"pre": self.c_pre.currentIndex(), "early": self.c_early.currentIndex(),
                "late": self.c_late.currentIndex(), "threshold_pct": self.s_thr.value(),
                "noise_pct": self.s_noise.value(), "relative": bool(self.c_units.currentData()),
                "threshold_all": self.c_thr_all.isChecked(), "layout": self.c_layout.currentIndex(),
                "layout_nome": self.c_layout.currentText(),
                "motion": self.c_motion.isChecked(),
                "motion_rigido": self.c_motion.isChecked() and self.c_rigido.isChecked(),
                "rapido_pct": self.s_rapido.value(),
                "tardio_pct": self.s_tardio.value(), "sinal_min_pct": self.s_sinal.value(),
                "base_media": self.c_base_media.isChecked(), "fases_pre": self.fases_pre(),
                "excluidas": self.excluidas() or [],
                "uids": self.checked()}


def validar_exclusao(n: int, pre: int, early: int, late: int, fases_pre, excluidas) -> str:
    """A mesma regra de `DynamicMaps.validar_exclusao`, antes de montar os mapas."""
    from types import SimpleNamespace
    falso = SimpleNamespace(dset=SimpleNamespace(phases=[None] * n), pre=pre, early=early, late=late,
                            fases_pre=list(fases_pre))
    return DynamicMaps.validar_exclusao(falso, excluidas)


# ====================================================================== gráfico
class TicChart(QWidget):
    """Curvas tempo-intensidade (várias), em realce relativo (%) ou sinal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.times: list[float] = []
        self.curves: list[tuple[QColor, str, np.ndarray, bool]] = []    # cor, rótulo, valores, tracejada
        self.relative = True
        self.marks: list[tuple[float, str]] = []

    def set_data(self, times, curves, relative: bool, marks) -> None:
        self.times, self.curves, self.relative, self.marks = list(times), curves, relative, marks
        self.update()

    def _ys(self, v: np.ndarray) -> np.ndarray:
        if not self.relative:
            return v
        base = v[0] if abs(v[0]) > 1e-6 else 1e-6
        return (v - v[0]) / abs(base) * 100.0

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        f = QFont()
        f.setPointSizeF(8.5)
        p.setFont(f)
        m = QRectF(58, 14, max(10, self.width() - 74), max(10, self.height() - 48))
        if not self.times:
            p.setPen(QColor(150, 150, 150))
            p.drawText(self.rect(), Qt.AlignCenter, "Sem fases")
            return
        ys = [self._ys(np.asarray(v, float)) for _c, _l, v, _d in self.curves]
        if ys:
            lo = min(float(y.min()) for y in ys)
            hi = max(float(y.max()) for y in ys)
        else:
            lo, hi = 0.0, 100.0
        if self.relative:
            lo = min(lo, 0.0)
            hi = max(hi, 20.0)
        pad = (hi - lo) * 0.08 or 1.0
        lo, hi = lo - pad, hi + pad
        tmax = max(self.times[-1], 1.0)

        def pt(t, y) -> QPointF:
            return QPointF(m.left() + t / tmax * m.width(), m.bottom() - (y - lo) / (hi - lo) * m.height())
        axis = QColor(210, 190, 60)
        p.setPen(QPen(QColor(55, 55, 55)))
        for k in range(6):
            y = lo + (hi - lo) * k / 5
            q = pt(0, y)
            p.setPen(QPen(QColor(50, 50, 50)))
            p.drawLine(QPointF(m.left(), q.y()), QPointF(m.right(), q.y()))
            p.setPen(axis)
            txt = f"{y:.0f}%" if self.relative else f"{y:.0f}"
            p.drawText(QRectF(0, q.y() - 8, 54, 16), Qt.AlignRight | Qt.AlignVCenter, txt)
        for t in self.times:
            x = pt(t, lo).x()
            p.setPen(QPen(QColor(45, 45, 45)))
            p.drawLine(QPointF(x, m.top()), QPointF(x, m.bottom()))
        for k in range(5):
            t = tmax * k / 4
            x = pt(t, lo).x()
            p.setPen(axis)
            p.drawText(QRectF(x - 30, m.bottom() + 3, 60, 14), Qt.AlignCenter, fmt_time(t))
        for t, lab in self.marks:
            x = pt(t, lo).x()
            pen = QPen(QColor(140, 140, 140))
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(x, m.top()), QPointF(x, m.bottom()))
            tw = p.fontMetrics().horizontalAdvance(lab)
            p.drawText(QPointF(x + 3 if x + tw + 4 < m.right() else x - tw - 3, m.bottom() - 4), lab)
        p.setPen(QPen(axis))
        p.drawRect(m)
        p.drawText(QRectF(m.left(), m.bottom() + 17, m.width(), 14), Qt.AlignCenter,
                   "tempo (min:s) · " + ("realce relativo ao pré-contraste (%)" if self.relative else "sinal"))
        for (color, label, _v, dashed), y in zip(self.curves, ys):
            pts = [pt(t, yy) for t, yy in zip(self.times, y)]
            pen = QPen(color, 2.2)
            if dashed:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawPolyline(QPolygonF(pts))
            p.setBrush(color)
            for q in pts:
                p.drawEllipse(q, 3, 3)
            p.setBrush(Qt.NoBrush)
        # legenda
        y0 = m.top() + 4
        for color, label, _v, _d in self.curves[:8]:
            p.setPen(color)
            p.drawText(QPointF(m.left() + 6, y0 + 10), label)
            y0 += 14


# ====================================================================== painel
class DynamicPanel(QWidget):
    COLS = ["#", "Origem", "Inicial", "Pico", "SER", "Curva", "Cinética", "MSI", "PEI", "BAT", "Lavagem",
            "iAUC90", "MRT"]

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.s = session
        self.setMinimumWidth(320)
        self.setStyleSheet("QWidget{background:#111;color:#ddd} QComboBox,QPushButton{background:#222}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        self.title = QLabel("")
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.RichText)
        lay.addWidget(self.title)
        row = QHBoxLayout()
        row.addWidget(QLabel("Quadro ativo:"))
        self.c_view = QComboBox()
        self.c_view.activated.connect(self._view_chosen)
        row.addWidget(self.c_view, 1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Plano:"))
        self.c_plano = QComboBox()
        for nome in ("Aquisição", "Axial", "Coronal", "Sagital", "Oblíquo"):
            self.c_plano.addItem(nome)
        self.c_plano.setToolTip("Reconstrói o mapa do quadro ativo em outro plano. As curvas e as "
                                "ROIs continuam valendo no plano da aquisição.")
        self.c_plano.activated.connect(self._plano_escolhido)
        row2.addWidget(self.c_plano, 1)
        lay.addLayout(row2)
        self.chart = TicChart()
        lay.addWidget(self.chart, 3)
        opts = QHBoxLayout()
        self.c_hover = QCheckBox("Curva sob o cursor")
        self.c_hover.setChecked(True)
        self.c_hover.toggled.connect(lambda _on: self.s.refresh())
        opts.addWidget(self.c_hover)
        self.c_rel = QCheckBox("Realce relativo (%)")
        self.c_rel.setChecked(True)
        self.c_rel.toggled.connect(lambda _on: self.s.refresh())
        opts.addWidget(self.c_rel)
        self.c_worst = QCheckBox("Pior pixel das ROIs")
        self.c_worst.setChecked(True)
        self.c_worst.setToolTip("Em cada ROI, acha o pixel (média 3×3) mais suspeito: maior SER entre os que "
                                "passam do limiar de realce; mostra a curva dele tracejada e marca ✳ na imagem.")
        self.c_worst.toggled.connect(lambda _on: self.s.refresh())
        opts.addWidget(self.c_worst)
        opts.addStretch(1)
        lay.addLayout(opts)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.table, 1)
        colunas_ajustaveis(self.table)
        hint = QLabel("<small>Clique com a ferramenta <b>Intensidade</b> (V) para pontos ou desenhe ROIs "
                      "(elipse E, retângulo, polígono G) em qualquer quadro da dinâmica.<br>"
                      "SER: <span style='color:#48f'>■</span> &lt; 0,9 persistente "
                      "<span style='color:#fd0'>■</span> 0,9–1,1 platô "
                      "<span style='color:#e22'>■</span> &gt; 1,1 washout<br>"
                      "Cinética — realce médio: <span style='color:#1a5fa0'>■</span> persistente "
                      "<span style='color:#1a7a44'>■</span> platô <span style='color:#8c3030'>■</span> washout "
                      "· rápido: <span style='color:#4a96ff'>■</span> persistente "
                      "<span style='color:#3ce65a'>■</span> platô "
                      "<span style='color:#ff3737'>■</span> washout</small>")
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.RichText)
        lay.addWidget(hint)
        # Oito botões em duas colunas, e não quatro por linha: o painel tem ~340 px, e com quatro
        # cada um ficava com 77 px para um texto que precisa de 144. Ficavam todos cortados —
        # inclusive o "Números do exame…", que ele não achou. Botão cortado não é botão.
        grade = QGridLayout()
        grade.setContentsMargins(0, 0, 0, 0)
        botoes = (("Parâmetros…", self.s.reconfigure, "Fases, limiares e disposição dos quadros."),
                  ("Números do exame…", self.s.numeros_do_exame,
                   "Realce de fundo do parênquima e angiovolume da mama inteira."),
                  ("Fibroglandular e realce…", self.s.fgt_do_exame,
                   "Quanto da mama é tecido fibroglandular (no T1 sem saturação, no Dixon ou, sem eles, na "
                   "pré-contraste) e quanto ele realça na primeira fase."),
                  ("Salvar mapas…", self.s.save_maps, "Grava os mapas dos quadros como séries novas."),
                  ("Apagar curvas", self.s.clear_slice, "Apaga as curvas e ROIs deste corte."),
                  ("Gráfico no filme", self.s.chart_to_film, "Põe o gráfico numa folha de filme."),
                  ("Copiar valores", self.copy_values, "Copia a tabela para a área de transferência."),
                  ("Salvar gráfico…", self.save_chart, "Grava o gráfico como imagem."),
                  ("Fechar dinâmica", self.s.close, "Volta os quadros às séries originais."))
        for i, (text, fn, dica) in enumerate(botoes):
            b = QPushButton(text)
            b.setToolTip(dica)
            b.clicked.connect(fn)
            grade.addWidget(b, i // 2, i % 2)
        lay.addLayout(grade)
        self.rows: list[tuple[str, dict, np.ndarray]] = []

    # ------------------------------------------------------------------
    def fill_views(self, current: str) -> None:
        self.c_view.clear()
        for key, (name, desc, *_r) in MAPS.items():
            self.c_view.addItem(f"{name} — {desc}", key)
        mp = self.s.maps
        for i, (lab, t) in enumerate(zip(mp.dset.labels, mp.dset.times)):
            tag = " (pré)" if i == mp.pre else " (inicial)" if i == mp.early else " (tardia)" if i == mp.late else ""
            if i in getattr(mp, "excluidas", ()):
                tag += " (fora da conta)"
            self.c_view.addItem(f"Fase {i + 1}{tag} — {fmt_time(t)} — {lab}", f"ph:{i}")
        i = self.c_view.findData(current)
        if i >= 0:
            self.c_view.setCurrentIndex(i)

    def _view_chosen(self, _i: int) -> None:
        self.s.set_active_view(self.c_view.currentData())
        self.mostrar_plano()

    def _plano_escolhido(self, _i: int) -> None:
        nome = self.c_plano.currentText()
        self.s.reorientar(nome if nome != "Aquisição" else "Original")
        self.mostrar_plano()

    def mostrar_plano(self) -> None:
        """A caixa do plano mostra o que o quadro ativo está mostrando de verdade."""
        nome = self.s.plano_do_quadro_ativo()
        i = self.c_plano.findText(nome)
        self.c_plano.setCurrentIndex(i if i >= 0 else 0)
        self.c_plano.setEnabled(nome != "")

    def set_rows(self, rows: list[tuple[QColor, str, dict]]) -> None:
        mp = self.s.maps
        unit_msi = MAPS["msi"][2] if mp.relative else MAPS["msi"][3]
        unit_pei = MAPS["pei"][2] if mp.relative else MAPS["pei"][3]
        self.table.setRowCount(len(rows))
        self.rows = []
        for r, (color, label, st) in enumerate(rows):
            vals = [str(r + 1), label, f"{st['initial']:+.0f}%", f"{st['peak']:+.0f}%",
                    "—" if st["ser"] is None else f"{st['ser']:.2f}", st["type"] or "—",
                    st.get("cinetica", "—"), f"{st['msi']:.0f} {unit_msi}", f"{st['pei']:.0f} {unit_pei}",
                    f"{st.get('bat', 0):.0f} s", f"{st.get('wash', 0):.0f} {unit_msi}",
                    f"{st.get('iauc', 0):.0f} {unit_pei}", f"{st.get('mrt', 0):.0f} s"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setForeground(color)
                    it.setBackground(QColor(35, 35, 35))
                self.table.setItem(r, c, it)
            self.rows.append((label, st, np.asarray(st.get("values", []))))

    def copy_values(self) -> None:
        mp = self.s.maps
        head = ["curva"] + [f"{lab} ({fmt_time(t)})" for lab, t in zip(mp.dset.labels, mp.dset.times)] + \
            ["inicial %", "pico %", "SER", "tipo", "cinética", "MSI", "PEI", "BAT s", "lavagem", "iAUC90", "MRT s"]
        lines = ["\t".join(head)]
        for label, st, vals in self.rows:
            ser = "" if st["ser"] is None else f"{st['ser']:.3f}"
            lines.append("\t".join([label] + [f"{v:.2f}" for v in vals] +
                                   [f"{st['initial']:.1f}", f"{st['peak']:.1f}", ser, st["type"],
                                    st.get("cinetica", ""), f"{st['msi']:.2f}", f"{st['pei']:.2f}",
                                    f"{st.get('bat', 0):.1f}", f"{st.get('wash', 0):.2f}", f"{st.get('iauc', 0):.2f}",
                                    f"{st.get('mrt', 0):.1f}"]))
        QApplication.clipboard().setText("\n".join(lines))
        self.s.tab.status_message.emit("Valores das curvas copiados (cole numa planilha).")

    def save_chart(self) -> None:
        path, _f = QFileDialog.getSaveFileName(self, "Salvar gráfico", "curva_dinamica.png", "PNG (*.png)")
        if path:
            self.report_image().save(path)

    def report_image(self, width: int = 1200):
        """Gráfico grande + tabela das curvas, numa imagem só (para filme/arquivo)."""
        from PySide6.QtGui import QImage
        chart = TicChart()
        chart.resize(width, int(width * 0.55))
        chart.set_data(self.chart.times, self.chart.curves, self.chart.relative, self.chart.marks)
        cp = chart.grab()
        f = QFont()
        f.setPointSizeF(13)
        lh = 26
        lines = [self.s.summary_line()] + ["   ".join(
            [f"{r + 1}. {label}", f"inicial {st['initial']:+.0f}%", f"pico {st['peak']:+.0f}%",
             "SER —" if st["ser"] is None else f"SER {st['ser']:.2f}", st["type"] or ""])
            for r, (label, st, _v) in enumerate(self.rows)]
        img = QImage(width, cp.height() + lh * (len(lines) + 1), QImage.Format_RGB888)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        p.drawPixmap(0, 0, cp)
        p.setFont(f)
        colors = [QColor(230, 230, 230)] + [self.s.row_colors[i] if i < len(self.s.row_colors) else
                                           QColor(230, 230, 230) for i in range(len(self.rows))]
        for i, (t, c) in enumerate(zip(lines, colors)):
            p.setPen(c)
            p.drawText(QPointF(16, cp.height() + lh * (i + 1)), t)
        p.end()
        return img


# ====================================================================== sessão
class DynamicSession:
    """Liga os quadros da aba aos mapas e ao painel de curvas."""

    def __init__(self, tab, maps: DynamicMaps, params: dict):
        self._cad = None
        self.tab, self.maps, self.params = tab, maps, params
        self.vps: list = []
        self.hover: tuple[int, float, float] | None = None
        self.row_colors: list = []
        self.panel = DynamicPanel(self)
        self._refreshing = False
        self.avisos: list[str] = []

    # ------------------------------------------------------------------ quadros
    def resolve(self, key: str) -> str:
        if key == "ph:early":
            return f"ph:{self.maps.early}"
        return key

    def show_view(self, vp, key: str, index: int | None = None) -> None:
        tab, mp = self.tab, self.maps
        key = self.resolve(key)
        idx = vp.index if index is None else index
        idx = max(0, min(idx, mp.n - 1))
        info = tab.study_infos.get(tab.study_uid, tab.study_info)
        vp.for_uid = self.for_uid
        vp.study_uid = self.study_uid
        vp.key_frames = tab.key_set
        if key.startswith("ph:"):
            i = int(key[3:])
            vp.mpr_plane = None
            vp.modality = "MR"
            # O quadro recebe **todas** as fases, não só esta: assim a linha de fase aparece no canto
            # e dá para andar pelas fases (clique, setas, menu) com o dinâmico ligado.
            vp.set_phases(f"dynph:{id(mp)}:fases", [mp.phase_frames(j) for j in range(len(mp.dset.phases))],
                          list(mp.dset.labels), f"Fase {i + 1} — {mp.dset.labels[i]}", info,
                          phase=i, start_index=idx)
            vp.set_colormap("")
        else:
            pl = mp.plane(key)
            vp.mpr_plane = pl
            vp.modality = f"MAP {key}"          # não sincroniza janela/cor com os outros mapas
            name, desc, u_rel, u_abs, cmap = MAPS[key]
            unit = u_rel if mp.relative else u_abs
            vp.set_series(f"dyn:{id(mp)}:{key}", pl.frames(), f"{name} ({unit})" if unit else name,
                          info, start_index=idx)
            w, l = mp.window(key)
            vp.set_window(w, l, emit=False)
            # a última cor que ele usou **neste mapa** manda; a de fábrica é só o ponto de partida
            vp.set_colormap(vp.cor_padrao() or cmap)
        vp.dyn_key = key
        vp.anonymize = tab.anonymize
        vp.update()

    def start(self) -> None:
        tab, mp = self.tab, self.maps
        uid0 = mp.dset.phases[0][0].series_uid
        meta = tab.repo.series_meta(uid0) or {}
        s = tab._series_row(uid0)
        self.study_uid = s.study_uid if s else tab.study_uid
        self.for_uid = meta.get("frame_of_reference", "") or f"study:{self.study_uid}"
        start = mp.n // 2
        src = tab.active
        if src is not None and src.frames and src.frames[0].position is not None:
            start = PH.map_index(src.frames, src.index, mp.phase_frames(0))
        # O número manda (quem chama já o tirou do nome: a janela e a etapa do protocolo); o nome é a
        # reserva para quando o número não vale mais na lista dele.
        lista = DC.layouts(tab.settings)
        try:
            i_lay = int(self.params.get("layout", -1))
        except (TypeError, ValueError):
            i_lay = -1
        lay = lista[i_lay] if 0 <= i_lay < len(lista) else \
            DC.escolher(tab.settings, None, self.params.get("layout_nome", ""))
        rows, cols = lay["rows"], lay["cols"]
        tab.set_layout(rows, cols)
        self.vps = []
        self.avisos: list[str] = []
        ponto = None
        outras: list[tuple] = []
        for vp, q in zip(tab.viewports[: rows * cols], lay["quadros"]):
            chave = self.chave_da_vista(q["vista"])
            if q["vista"] == "serie":
                outras.append((vp, q))
                continue
            if chave is None:
                vp.clear()
                vp.dyn_key = None
                vp.empty_note = "" if not q["vista"] else f"{DC.VISTAS[q['vista']]}: a dinâmica não tem esta fase"
                continue
            self.vps.append(vp)
            self.show_view(vp, chave, start)
            if q["cor"]:
                vp.set_colormap("" if q["cor"] == DC.COR_CINZA else q["cor"])
            if ponto is None:
                try:
                    ponto = vp.ponto_central()
                except Exception:  # noqa: BLE001
                    ponto = None
        for vp, q in outras:            # outra série do exame (T2, difusão…) no mesmo lugar do mapa
            self._mostrar_serie(vp, q, ponto)
        if not self.vps:                 # layout sem nenhum mapa nem fase: a curva precisa de um
            self.vps = [tab.viewports[0]]
            self.show_view(tab.viewports[0], "cin", start)
        tab._activate(self.vps[0])
        tab.set_left_tool("probe")
        self.panel.fill_views(self.vps[0].dyn_key)
        self.update_title()
        tab.update_reference_lines()
        self.refresh()

    def chave_da_vista(self, vista: str) -> str | None:
        """A chave de `show_view` para a vista do layout (None = não há como mostrar)."""
        mp = self.maps
        n = len(mp.dset.phases)
        if vista in DC.MAPAS:
            return vista
        if vista == "ph:pre":
            return f"ph:{mp.pre}"
        if vista == "ph:early":
            return f"ph:{mp.early}"
        if vista == "ph:late":
            return f"ph:{mp.late}"
        if vista == "ph:ult":
            return f"ph:{n - 1}"
        if vista.startswith("ph:pos"):
            k = mp.pre + int(vista[6:])
            return f"ph:{k}" if 0 <= k < n else None
        return None

    def _mostrar_serie(self, vp, q: dict, ponto) -> None:
        """Quadro do layout com outra série do exame (palavras da descrição, | = alternativas)."""
        from ipe.ui.viewer import hanging as H
        tab = self.tab
        fases = {f.series_uid for ph in self.maps.dset.phases for f in ph[:1]}
        cand = [(s.series_uid, *H.series_words(tab.repo, s)) for s in tab.series
                if s.study_uid == self.study_uid and s.num_images and s.series_uid not in fases]
        uid = H.escolher_serie(q["serie"], cand, set()) if q["serie"].strip() else None
        vp.dyn_key = None
        if uid is None:
            vp.clear()
            vp.empty_note = (f"Série não encontrada neste exame:\n{q['serie'].replace('|', ' ou ')}"
                             if q["serie"].strip() else "Quadro de série sem série escolhida")
            self.avisos.append(vp.empty_note.replace("\n", " "))
            return
        try:
            tab.load_series_into(vp, uid)
            if ponto is not None:
                vp.go_to_point(ponto)
            if q["cor"]:
                vp.set_colormap("" if q["cor"] == DC.COR_CINZA else q["cor"])
        except Exception:  # noqa: BLE001
            log.exception("série do layout da dinâmica")
            vp.clear()
            vp.empty_note = "Não foi possível abrir a série deste quadro"

    def update_title(self) -> None:
        mp = self.maps
        d = mp.dset
        self.panel.title.setText(
            f"<b>Avaliação dinâmica</b> — {len(d.phases)} fases, {d.n_slices} cortes<br>"
            f"<small>pré: fase {mp.pre + 1} · inicial: fase {mp.early + 1} ({fmt_time(d.times[mp.early])}) · "
            f"tardia: fase {mp.late + 1} ({fmt_time(d.times[mp.late])}) · limiar {mp.threshold_pct:.0f}%"
            + ("" if d.timed else " · <span style='color:#fc6'>sem horários (1 min/fase)</span>")
            + (self._motion_text() if mp.motion_corrected else "")
            + "".join(f"<br><span style='color:#fc6'>{tr(a)}</span>" for a in mp.avisos_das_fases())
            + (f"<br>{mp.legenda_cinetica()}" if self._mostra_cinetica() else "") + "</small>")

    def _mostra_cinetica(self) -> bool:
        """Mapa colorido sem os limiares à vista é imagem bonita sem medida."""
        return any(getattr(vp, "dyn_key", None) == "cin" for vp in self.vps)

    def _motion_text(self) -> str:
        mp = self.maps
        rs, cs = mp.pixel_spacing or (1.0, 1.0)
        pl = mp.plane("msi")
        worst = max(np.linalg.norm([dz * pl.step_mm, dy * rs, dx * cs]) for dz, dy, dx in mp.shifts)
        rot = mp.rotacao_maxima
        if rot:
            return f"<br>movimento corrigido (máx. {worst:.1f} mm e {rot:.1f}°)"
        return f"<br>movimento corrigido (máx. {worst:.1f} mm)"

    def is_dyn(self, vp) -> bool:
        return vp in self.vps and getattr(vp, "dyn_key", None) is not None and \
            vp.series_uid.startswith((f"dyn:{id(self.maps)}:", f"dynph:{id(self.maps)}:"))

    def set_active_view(self, key: str) -> None:
        vp = self.tab.active
        if vp is None:
            return
        if vp not in self.vps:
            self.vps.append(vp)
        self.show_view(vp, key)
        self.tab.update_reference_lines()
        self.refresh()

    # ------------------------------------------------------------------ plano
    def quadro_de_mapa(self):
        """O quadro ativo, se ele mostra um mapa (no plano da aquisição ou reconstruído)."""
        vp = self.tab.active
        return vp if self.tab._dyn_do_quadro(vp) is not None else None

    def plano_do_quadro_ativo(self) -> str:
        """"Aquisição", "Axial"… para a caixa do painel; "" quando o quadro não é um mapa."""
        vp = self.quadro_de_mapa()
        if vp is None:
            return ""
        if not vp.series_uid.startswith(f"dynmpr:{id(self.maps)}:"):
            return "Aquisição"
        return getattr(vp.mpr_plane, "name", "") or "Aquisição"

    def reorientar(self, nome: str) -> bool:
        """Põe o mapa do quadro ativo em outro plano (ou de volta ao da aquisição)."""
        vp = self.quadro_de_mapa()
        if vp is None:
            self.tab.status_message.emit("Escolha primeiro um quadro com um mapa da dinâmica.")
            return False
        chave = self.tab._dyn_do_quadro(vp)[1]
        return self.tab.reformatar_mapa(vp, self, chave, nome)

    def fase_mudou(self, vp) -> None:
        """Trocou de fase num quadro de fase: o rótulo, a chave do quadro e o painel acompanham."""
        if not self.is_dyn(vp) or not str(getattr(vp, "dyn_key", "") or "").startswith("ph:"):
            return
        i = int(vp.phase)
        vp.dyn_key = f"ph:{i}"
        vp.series_label = f"Fase {i + 1} — {self.maps.dset.labels[i]}"
        if self.tab.active is vp:
            self.activated(vp)
        vp.update()
        self.refresh()

    def activated(self, vp) -> None:
        if self.is_dyn(vp):
            i = self.panel.c_view.findData(vp.dyn_key)
            if i >= 0:
                self.panel.c_view.setCurrentIndex(i)
        self.panel.mostrar_plano()

    # ------------------------------------------------------------------ curvas
    def on_hover(self, vp, u: float, v: float) -> None:
        if not self.panel.c_hover.isChecked() or not self.is_dyn(vp):
            return
        self.hover = (vp.index, u, v)
        self.refresh()

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._refresh()
        except Exception:  # noqa: BLE001
            log.exception("curvas da dinâmica")
        finally:
            self._refreshing = False

    def _refresh(self) -> None:
        mp = self.maps
        curves, rows = [], []
        self.row_colors = []
        n = 0
        dyn = [vp for vp in self.vps if self.is_dyn(vp)]
        drawn: list[tuple[object, int, str, list, QColor]] = []      # (vp, corte, tipo, pontos, cor)
        worst = self.panel.c_worst.isChecked()
        for vp in dyn:
            vp.ann_colors = {}
            k = vp.index
            for a in vp.frame_annotations():
                vals = None
                if a.kind == "probe" and a.points:
                    vals = mp.curve(k, point=a.points[0], radius=1)
                    label = f"ponto 3×3 · corte {k + 1}"
                elif a.kind in ROI_KINDS:
                    r = M.roi_mask(a.kind, a.points, mp.shape)
                    if r is not None:
                        vals = mp.curve(k, r[0], r[1])
                        label = f"{M.KINDS.get(a.kind, 'ROI')} ({int(r[1].sum())} px) · corte {k + 1}"
                if vals is None:
                    continue
                color = CURVE_COLORS[n % len(CURVE_COLORS)]
                n += 1
                vp.ann_colors[id(a)] = color
                drawn.append((vp, k, a.kind, list(a.points), color))
                st = mp.curve_stats(vals)
                st["values"] = vals
                curves.append((color, f"{n}: {label}", vals, False))
                rows.append((color, label, st))
                self.row_colors.append(color)
                if worst and a.kind in ROI_KINDS and r is not None:
                    w = mp.worst_pixel(k, r[0], r[1])
                    if w is not None:
                        (x, y), wv = w
                        drawn.append((None, k, "star", [(x, y)], color))
                        wst = mp.curve_stats(wv)
                        wst["values"] = wv
                        curves.append((color, f"{n}✳: pior pixel ({int(x)}, {int(y)})", wv, True))
                        rows.append((color, f"✳ pior pixel da ROI {n} ({int(x)}, {int(y)})", wst))
                        self.row_colors.append(color)
        # contornos repetidos nos outros quadros da dinâmica (mesma grade de pixels)
        for vp in dyn:
            vp.ghosts = [(kind, pts, color) for owner, k, kind, pts, color in drawn
                         if k == vp.index and owner is not vp]
            vp.update()
        if self.hover is not None and self.panel.c_hover.isChecked():
            k, u, v = self.hover
            vals = mp.curve(k, point=(u, v), radius=0)
            if vals is not None:
                curves.append((QColor(200, 200, 200), f"cursor ({int(u)}, {int(v)})", vals, True))
        marks = [(mp.dset.times[mp.early], "inicial"), (mp.dset.times[mp.late], "tardia")]
        marks += [(mp.dset.times[i], "fora") for i in sorted(getattr(mp, "excluidas", ()))]
        self.panel.chart.set_data(mp.dset.times, curves, self.panel.c_rel.isChecked(), marks)
        self.panel.set_rows(rows)

    def volumes_cad(self, progresso=None):
        """(volume do realce no pico, volume das classes cinéticas) — montados uma vez só.

        Os dois juntos são o que permite medir a lesão: o realce diz **onde ela está** e a classe
        diz **que tipo de realce** é cada voxel dela.
        """
        if getattr(self, "_cad", None) is None:
            realce = self.maps.volume_do_mapa("ei", progresso, so_tecido=True)
            classes = self.maps.volume_do_mapa("cin", progresso).data.astype(np.uint8)
            self._cad = (realce, classes)
        return self._cad

    def summary_line(self) -> str:
        mp = self.maps
        d = mp.dset
        mov = " · movimento corrigido" if mp.motion_corrected else ""
        cin = f" · {mp.legenda_cinetica()}" if self._mostra_cinetica() else ""
        fora = (" · fora da conta: fase " + ", ".join(str(i + 1) for i in sorted(mp.excluidas))) if mp.excluidas else ""
        base = f" · linha de base: média das fases 1 a {mp.pre + 1}" if len(mp.fases_pre) > 1 else ""
        return (f"Dinâmica: {len(d.phases)} fases · pré fase {mp.pre + 1} · inicial {fmt_time(d.times[mp.early])} · "
                f"tardia {fmt_time(d.times[mp.late])} · limiar {mp.threshold_pct:.0f}%{base}{fora}{mov}{cin}")

    def chart_to_film(self) -> None:
        """Grava o gráfico (com a tabela) como imagem DICOM (captura secundária) no estudo e manda ao filme."""
        from ipe.imaging.derived import qimage_to_rgb, save_secondary_capture
        tab = self.tab
        storage = getattr(tab, "storage_root", None)
        if storage is None:
            return None
        try:
            uid, _sops = save_secondary_capture(qimage_to_rgb(self.panel.report_image()), self.maps.source_path,
                                                tab.repo.db, storage, "Curvas tempo-intensidade")
        except Exception as e:  # noqa: BLE001
            log.exception("gráfico no filme")
            QMessageBox.warning(self.panel, "Dinâmica", f"Não foi possível gravar o gráfico:\n{e}")
            return None
        from ipe.central.client_repo import upload_if_client
        upload_if_client(tab.repo, self.study_uid)
        tab.film_requested.emit({"kind": "images", "items": [
            {"study_uid": self.study_uid, "series_uid": uid, "index": 0, "label": "Curvas tempo-intensidade"}]})
        tab.status_message.emit("Gráfico enviado ao filme (também salvo como imagem no exame).")
        return uid

    def clear_slice(self) -> None:
        for vp in self.vps:
            if self.is_dyn(vp):
                vp.delete_frame_annotations()
        self.refresh()

    # ------------------------------------------------------------------ ações
    def reconfigure(self) -> None:
        self.tab.open_dynamic(previous=self.params)

    def numeros_do_exame(self) -> None:
        """Realce de fundo do parênquima e angiovolume da mama inteira, numa janela própria."""
        from PySide6.QtWidgets import QApplication, QProgressDialog
        from ipe.imaging.volume import VolumeError
        tab = self.tab
        dlg = QProgressDialog("Medindo a mama inteira…", "Cancelar", 0, 2 * self.maps.n, tab)
        dlg.setWindowTitle("Números do exame")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progresso(feitos: int, total: int) -> bool:
            if feitos % 4 == 0 or feitos == total:
                dlg.setMaximum(total)
                dlg.setValue(feitos)
                QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            e = self.maps.numeros_do_exame(progresso)
        except VolumeError as erro:
            dlg.close()
            QMessageBox.information(tab, "Números do exame", str(erro))
            return
        except Exception:  # noqa: BLE001
            dlg.close()
            log.exception("falhou a conta da mama inteira")
            QMessageBox.warning(tab, "Números do exame", "Não consegui medir a mama inteira; "
                                "o registro do erro está no log.")
            return
        finally:
            dlg.close()
        linhas = "".join("<tr><td>" + nome + "</td><td align='right'><b>" + valor
                         + "</b></td></tr>" for nome, valor in e.linhas())
        avisos = "<br>".join(e.avisos)
        cx = QMessageBox(QMessageBox.NoIcon, "Números do exame",
                         "<table cellpadding=3>" + linhas + "</table>", parent=tab)
        cx.setInformativeText(f"<small>{e.mascara}<br><br>{e.formula}<br><br>{avisos}</small>")
        cx.setTextFormat(Qt.RichText)
        cx.exec()

    def fgt_do_exame(self) -> None:
        """Fibroglandular × gordura e realce de fundo do FGT (0.100.7), com a máscara para conferir."""
        from PySide6.QtWidgets import QApplication, QProgressDialog
        from ipe.imaging import mama_fgt as F
        from ipe.imaging import mama_fgt_exame as FE
        tab = self.tab
        dlg = QProgressDialog("Separando gordura e glândula…", "Cancelar", 0, 0, tab)
        dlg.setWindowTitle("Fibroglandular e realce")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progresso(feitos: int, total: int) -> bool:
            if feitos % 4 == 0 or feitos == total:
                dlg.setMaximum(total)
                dlg.setValue(feitos)
                QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            r, esc, vol, frames = FE.medir(tab.repo, tab.cache, tab.study_uid, self.maps, progresso)
        except Exception as erro:  # noqa: BLE001
            dlg.close()
            log.exception("fibroglandular do exame")
            QMessageBox.information(tab, "Fibroglandular e realce", str(erro) or "Não consegui medir; o registro "
                                    "do erro está no log.")
            return
        finally:
            dlg.close()
        self.ultimo_fgt = r
        frases = F.frases(r)
        tabela = "".join("<tr><td>" + nome + "</td><td><b>" + valor + "</b></td></tr>" for nome, valor in FE.linhas(r))
        cx = QMessageBox(QMessageBox.NoIcon, "Fibroglandular e realce", "<table cellpadding=3>" + tabela + "</table>",
                         parent=tab)
        avisos = "<br>".join(r.avisos)
        cx.setInformativeText("<small>" + r.texto_metodo + "<br><br>"
                              + "<br>".join(frases) + ("<br><br>" + avisos if avisos else "") + "</small>")
        cx.setTextFormat(Qt.RichText)
        copiar = cx.addButton("Copiar frases", QMessageBox.ActionRole)
        gravar = cx.addButton("Gravar a máscara (SEG)", QMessageBox.ActionRole) if vol is not None else None
        cx.addButton(QMessageBox.Close)
        cx.exec()
        if cx.clickedButton() is copiar:
            QApplication.clipboard().setText("\n".join(frases))
            tab.status_message.emit("Frases do fibroglandular copiadas.")
        elif gravar is not None and cx.clickedButton() is gravar:
            db = getattr(tab.repo, "db", None)
            storage = getattr(tab, "storage_root", None)
            if db is None or storage is None:
                QMessageBox.information(tab, "Fibroglandular e realce", "Este banco não aceita série nova daqui.")
                return
            try:
                novas = FE.gravar_seg(r, vol, frames, db, storage, tab.repo, tab.study_uid)
            except Exception:  # noqa: BLE001
                log.exception("gravar a SEG do fibroglandular")
                QMessageBox.warning(tab, "Fibroglandular e realce", "Não consegui gravar a máscara; o registro do "
                                    "erro está no log.")
                return
            if hasattr(tab, "recarregar_series"):
                tab.recarregar_series()
            tab.status_message.emit(f"Máscara gravada: {FE.DESC_SEG} ({len(novas)} série).")

    @staticmethod
    def resumo_do_salvamento(feitos: list[str], faltaram: list[str]) -> str:
        """O texto do aviso, montado longe de quem o exibe — assim dá para testar sem janela."""
        texto = ""
        if feitos:
            texto = ("<b>Séries novas no banco</b><br>" + "<br>".join(feitos)
                     + "<br><br>Elas já aparecem na tira de séries e no banco de dados.")
        if faltaram:
            texto += ("<br><br>" if texto else "") + "<b>Não salvos</b><br>" + "<br>".join(faltaram)
        return texto or "Nenhum mapa foi salvo."

    def save_maps(self) -> None:
        """Grava como séries novas os mapas que estão nos quadros. Um a um, com aviso no fim.

        Cada mapa é calculado corte a corte na hora de gravar: com três mapas de uma RM de mama
        são centenas de contas, e sem janela de progresso o programa parecia travado — foi o que
        ele relatou. Agora cada mapa tem barra e botão de parar, e no fim sai um aviso dizendo o
        que entrou no banco (e o que não entrou).
        """
        keys = [vp.dyn_key for vp in self.vps if self.is_dyn(vp) and vp.dyn_key in MAPS] or ["msi", "pei", "ser"]
        keys = list(dict.fromkeys(keys))
        feitos, faltaram = [], []
        for key in keys:
            vp = next((v for v in self.vps if self.is_dyn(v) and v.dyn_key == key), None)
            if vp is None:
                faltaram.append(MAPS[key][0] + " (não está em nenhum quadro)")
                continue
            res = self.tab.save_reconstruction(vp)
            if res:
                feitos.append(MAPS[key][0] + f": {len(res[1])}" + " imagens")
            else:
                faltaram.append(MAPS[key][0])
        QMessageBox.information(self.tab, "Salvar mapas", self.resumo_do_salvamento(feitos, faltaram))
        if feitos:
            self.tab.status_message.emit("Mapas salvos como séries novas: "
                                         + ", ".join(f.split(":")[0] for f in feitos))

    def close(self) -> None:
        self.tab.close_dynamic()
