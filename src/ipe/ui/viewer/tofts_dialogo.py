"""A janela da farmacocinética da dinâmica (0.100.67): modelo de Tofts, a entrada arterial e o que se supõe.

Os avisos ficam à vista antes do OK e mudam com as escolhas: com uma fase por minuto, o Ktrans é indicativo, e a
janela diz isso com os números do exame (ver `imaging.tofts.avisos`).
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QVBoxLayout,
)

from ipe.core.i18n import tr
from ipe.imaging import tofts as TF

log = logging.getLogger(__name__)


def parametros_do_exame(caminho: str) -> dict:
    """TR (ms), ângulo (graus) e campo (T) lidos do cabeçalho da primeira imagem da dinâmica; 0 = não tem."""
    out = {"tr_ms": 0.0, "angulo": 0.0, "campo_t": 0.0}
    try:
        import pydicom
        ds = pydicom.dcmread(caminho, stop_before_pixels=True, specific_tags=[
            "RepetitionTime", "FlipAngle", "MagneticFieldStrength", "SharedFunctionalGroupsSequence"])
        for chave, tag in (("tr_ms", "RepetitionTime"), ("angulo", "FlipAngle"), ("campo_t", "MagneticFieldStrength")):
            try:
                out[chave] = float(ds.get(tag) or 0)
            except (TypeError, ValueError):
                pass
        if not (out["tr_ms"] and out["angulo"]):                 # RM "enhanced": dentro dos grupos funcionais
            for g in ds.get("SharedFunctionalGroupsSequence", []) or []:
                for t in g.get("MRTimingAndRelatedParametersSequence", []) or []:
                    out["tr_ms"] = out["tr_ms"] or float(t.get("RepetitionTime") or 0)
                    out["angulo"] = out["angulo"] or float(t.get("FlipAngle") or 0)
    except Exception:  # noqa: BLE001
        log.exception("TR e ângulo da dinâmica")
    if out["campo_t"] > 100:                                     # alguns aparelhos gravam em gauss
        out["campo_t"] /= 10000.0
    return out


class ToftsDialog(QDialog):
    def __init__(self, sessao, parent=None):
        super().__init__(parent or sessao.tab)
        self.s = sessao
        mp = sessao.maps
        self.setWindowTitle("Farmacocinética (Tofts)")
        self.setMinimumWidth(520)
        cfg = mp.tofts
        novo = cfg is None
        if novo:
            ex = parametros_do_exame(mp.dset.phases[mp.pre][0].path)
            t10, t10s = TF.t1_padrao(ex["campo_t"])
            res = TF.resolucao_temporal(mp.dset.times)
            # o contraste costuma entrar quando a pré acaba, e a imagem "vale" pelo meio da aquisição: meia fase
            cfg = TF.Config(tr_ms=ex["tr_ms"], angulo=ex["angulo"], campo_t=ex["campo_t"], t10_ms=t10,
                            t10_sangue_ms=t10s, inicio_s=round(res / 2.0) if res > TF.RESOLUCAO_BOA else 0.0)
        lay = QVBoxLayout(self)
        intro = QLabel("Ktrans, ve e kep de cada voxel, pelo modelo de Tofts: o sinal vira concentração de contraste "
                       "e a curva de cada voxel é comparada com a do plasma. Os mapas entram na lista do quadro "
                       "ativo, e as ROIs ganham os números na tabela.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        f = QFormLayout()
        self.c_modelo = QComboBox()
        for k, txt in TF.MODELOS.items():
            self.c_modelo.addItem(txt, k)
        self.c_modelo.setCurrentIndex(max(0, self.c_modelo.findData(cfg.modelo)))
        f.addRow("Modelo:", self.c_modelo)
        self.c_aif = QComboBox()
        self.c_aif.addItem(TF.AIFS["parker"], ("parker", None))
        self._rois = [(rot, vals) for rot, _st, vals in getattr(sessao.panel, "rows", []) if len(vals) == len(mp.dset.phases)]
        for i, (rot, vals) in enumerate(self._rois):
            self.c_aif.addItem(f"ROI numa artéria: curva {i + 1} ({rot})", ("roi", i))
        if cfg.aif == "roi" and cfg.aif_sinal:
            self.c_aif.addItem("ROI numa artéria: a que já está em uso", ("roi", -1))
            self.c_aif.setCurrentIndex(self.c_aif.count() - 1)
        self.c_aif.setToolTip("A curva do contraste no sangue. Populacional: a média medida em pacientes (Parker). "
                              "ROI: desenhe antes uma ROI dentro de uma artéria (aorta, mamária interna) num quadro "
                              "da dinâmica, e ela aparece aqui.")
        f.addRow("Entrada arterial:", self.c_aif)
        self.s_inicio = QDoubleSpinBox(minimum=-120, maximum=600, value=cfg.inicio_s, decimals=0, suffix=" s")
        self.s_inicio.setToolTip("Quando a injeção começou, contado a partir do horário da fase pré. Em geral o "
                                 "contraste entra quando a pré acaba e a imagem vale pelo meio da aquisição: meia "
                                 "fase. Só vale para a entrada populacional.")
        f.addRow("Início da injeção (depois da pré):", self.s_inicio)
        self.s_t10 = QDoubleSpinBox(minimum=100, maximum=5000, value=cfg.t10_ms, decimals=0, suffix=" ms", singleStep=50)
        self.s_t10.setToolTip("O T1 do tecido antes do contraste. Não há mapa de T1 no exame de rotina: é um valor "
                              "de literatura (fibroglandular: cerca de 1250 ms a 1,5 T e 1450 ms a 3 T).")
        f.addRow("T1 do tecido antes do contraste:", self.s_t10)
        self.s_t10s = QDoubleSpinBox(minimum=100, maximum=5000, value=cfg.t10_sangue_ms, decimals=0, suffix=" ms",
                                     singleStep=50)
        f.addRow("T1 do sangue (para a ROI arterial):", self.s_t10s)
        self.s_tr = QDoubleSpinBox(minimum=0, maximum=10000, value=cfg.tr_ms, decimals=2, suffix=" ms")
        self.s_ang = QDoubleSpinBox(minimum=0, maximum=89, value=cfg.angulo, decimals=1, suffix=" °")
        for w in (self.s_tr, self.s_ang):
            w.setToolTip("Lido do exame. Zero: não veio no cabeçalho, e a concentração sai pela aproximação linear.")
        f.addRow("TR:", self.s_tr)
        f.addRow("Ângulo de inclinação:", self.s_ang)
        self.s_r1 = QDoubleSpinBox(minimum=1, maximum=20, value=cfg.r1, decimals=1, suffix=" /(mM·s)", singleStep=0.1)
        self.s_r1.setToolTip("Relaxividade do contraste: cerca de 4,5 para os agentes de gadolínio comuns a 1,5 T, "
                             "um pouco menos a 3 T; mais para os de alta relaxividade.")
        f.addRow("Relaxividade do contraste:", self.s_r1)
        self.s_hct = QDoubleSpinBox(minimum=0.2, maximum=0.6, value=cfg.hematocrito, decimals=2, singleStep=0.01)
        f.addRow("Hematócrito:", self.s_hct)
        lay.addLayout(f)
        self.l_avisos = QLabel()
        self.l_avisos.setWordWrap(True)
        self.l_avisos.setStyleSheet("color:#c08a1a")
        lay.addWidget(self.l_avisos)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.b_desligar = QPushButton("Desligar")
        self.b_desligar.setToolTip("Tira os mapas de Tofts e as colunas da tabela.")
        self.b_desligar.setEnabled(not novo)
        bb.addButton(self.b_desligar, QDialogButtonBox.DestructiveRole)
        self.desligar = False
        self.b_desligar.clicked.connect(self._desligar)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._campo = cfg.campo_t
        self._aif_antiga = list(cfg.aif_sinal)
        for w in (self.c_modelo, self.c_aif):
            w.currentIndexChanged.connect(lambda _i: self._avisar())
        for w in (self.s_tr, self.s_ang, self.s_t10):
            w.valueChanged.connect(lambda _v: self._avisar())
        self._avisar()

    def _desligar(self) -> None:
        self.desligar = True
        self.accept()

    def config(self) -> TF.Config:
        aif, i = self.c_aif.currentData()
        sinal = []
        if aif == "roi":
            sinal = self._aif_antiga if i == -1 else [float(x) for x in self._rois[i][1]]
        return TF.Config(modelo=self.c_modelo.currentData(), aif=aif if sinal or aif == "parker" else "parker",
                         tr_ms=self.s_tr.value(), angulo=self.s_ang.value(), t10_ms=self.s_t10.value(),
                         t10_sangue_ms=self.s_t10s.value(), r1=self.s_r1.value(), hematocrito=self.s_hct.value(),
                         inicio_s=self.s_inicio.value(), aif_sinal=sinal, campo_t=self._campo)

    def _avisar(self) -> None:
        mp = self.s.maps
        n_pos = len([i for i in mp.ativas() if i > mp.pre])
        self.s_inicio.setEnabled(self.c_aif.currentData()[0] == "parker")
        self.s_t10s.setEnabled(self.c_aif.currentData()[0] == "roi")
        self.l_avisos.setText("<br>".join("• " + tr(a) for a in TF.avisos(self.config(), mp.dset.times, n_pos)))
