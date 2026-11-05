"""Nódulo pulmonar por clique (0.99.62, plano AW O10): botão direito na TC ▸ Nódulo pulmonar aqui.

A janela mostra a máscara por cima da imagem (em qualquer plano), os números — os mesmos dos candidatos da IA — e,
quando o mesmo nódulo já foi revisado num exame anterior, o crescimento. Guardar cria um achado **confirmado**
(ferramenta "nodulos", modelo "Ipê: segmentação por clique") na lista de Achados de IA; Guardar e acompanhar já o
põe no acompanhamento de lesões (na lesão do anterior, quando o anterior já era acompanhado)."""
from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from ipe.ai import achados as AC
from ipe.ai import nodulos as ND
from ipe.imaging import nodulo_clique as NC

log = logging.getLogger(__name__)

MODELO = "Ipê: segmentação por clique"


def lobo_no_ponto(tab, p) -> str:
    """O lobo pulmonar no ponto (mm), pelas máscaras de lobo que o exame mostra (TotalSegmentator), ou ""."""
    p = np.asarray(p, float)
    nomes = {**{k: k for k in ND.LOBOS}, **{v: k for k, v in ND.LOBOS.items()}}
    for o in getattr(tab, "overlay_objects", []):
        for mv in (o.volumes or []):
            rot = (mv.label or "").strip().lower()
            chave = next((nomes[n] for n in nomes if n.lower() == rot or n.lower() in rot), None)
            if chave is None:
                continue
            try:
                q = np.rint(np.linalg.inv(np.asarray(mv.matriz, float)) @ (p - np.asarray(mv.origem, float))).astype(int)
            except Exception:  # noqa: BLE001
                continue
            m = mv.mascara
            if 0 <= q[2] < m.shape[0] and 0 <= q[1] < m.shape[1] and 0 <= q[0] < m.shape[2] and m[q[2], q[1], q[0]]:
                return ND.LOBOS[chave]
    return ""


class NoduloDialog(QDialog):
    def __init__(self, tab, vp, vol, semente_kji, series_uid: str):
        super().__init__(tab, Qt.Tool)
        self.tab, self.vp, self.vol, self.semente = tab, vp, vol, tuple(int(x) for x in semente_kji)
        self.series_uid = series_uid
        self.study_uid = vp.study_uid or tab.study_uid
        self.setWindowTitle("Nódulo pulmonar (segmentação por clique)")
        self.resize(460, 420)
        self.mascara, self.offset, self.avisos, self.numeros, self.centro = None, (0, 0, 0), [], {}, None
        self.achado: dict | None = None
        from ipe.imaging import overlays as O
        self.obj = O.OverlayObject(f"nodulo-{id(self)}", "Segmentação", "Nódulo (clique)", ND.COR,
                                   study_uid=self.study_uid)
        tab.overlay_objects.append(self.obj)
        self.c_vidro = QCheckBox("Incluir o vidro fosco (limiar −750 HU)")
        self.c_vidro.toggled.connect(self._vidro)
        self.s_limiar = QDoubleSpinBox()
        self.s_limiar.setRange(-950, 200)
        self.s_limiar.setSuffix(" HU")
        self.s_limiar.setValue(NC.LIMIAR_SOLIDO)
        self.s_limiar.editingFinished.connect(self.rodar)
        self.c_abrir = QCheckBox("Separar dos vasos e da pleura (abertura de 1 voxel)")
        self.c_abrir.setChecked(True)
        self.c_abrir.toggled.connect(lambda _on: self.rodar())
        self.l_nums = QLabel()
        self.l_nums.setWordWrap(True)
        self.l_ant = QLabel()
        self.l_ant.setWordWrap(True)
        self.l_avisos = QLabel()
        self.l_avisos.setWordWrap(True)
        self.l_avisos.setStyleSheet("color:#e3b341")
        f = QFormLayout()
        f.addRow("Limiar:", self.s_limiar)
        f.addRow(self.c_vidro)
        f.addRow(self.c_abrir)
        self.b_guardar = QPushButton("Guardar como achado")
        self.b_guardar.clicked.connect(self.guardar)
        self.b_acomp = QPushButton("Guardar e acompanhar como lesão")
        self.b_acomp.clicked.connect(self.guardar_e_acompanhar)
        b_fechar = QPushButton("Fechar")
        b_fechar.clicked.connect(self.close)
        h = QHBoxLayout()
        h.addWidget(self.b_guardar)
        h.addWidget(self.b_acomp)
        h.addStretch(1)
        h.addWidget(b_fechar)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(self.l_nums)
        lay.addWidget(self.l_ant)
        lay.addWidget(self.l_avisos)
        lay.addStretch(1)
        lay.addLayout(h)
        self.rodar()

    def _vidro(self, on: bool) -> None:
        self.s_limiar.setValue(NC.LIMIAR_VIDRO if on else NC.LIMIAR_SOLIDO)
        self.rodar()

    # ------------------------------------------------------------ a conta
    def rodar(self) -> None:
        from ipe.imaging import overlays as O
        try:
            m, off, av = NC.segmentar(self.vol, self.semente, float(self.s_limiar.value()), NC.RAIO_MM,
                                      self.c_abrir.isChecked())
        except Exception as e:  # noqa: BLE001
            log.exception("nódulo por clique")
            m, off, av = None, (0, 0, 0), [str(e)]
        self.mascara, self.offset, self.avisos = m, off, av
        self.obj.volumes = [O.MaskVolume.do_volume(self.vol, m, off, ND.COR, "Nódulo")] if m is not None else []
        self.obj.version += 1
        for v in self.tab.viewports:
            v.update()
        ok = m is not None
        self.b_guardar.setEnabled(ok and self.achado is None)
        self.b_acomp.setEnabled(ok and self.achado is None)
        self.l_avisos.setText("\n".join(av))
        if not ok:
            self.numeros, self.centro = {}, None
            self.l_nums.setText("Nada segmentado: clique no meio do nódulo, ou baixe o limiar.")
            self.l_ant.setText("")
            return
        self.numeros, centro = ND.numeros_do_nodulo(self.vol, m, off)
        self.centro = [float(x) for x in centro]
        self.lobo = lobo_no_ponto(self.tab, self.centro)
        prov = {"numeros": self.numeros, "posicao": self.centro, "study_uid": self.study_uid,
                "local": self.lobo, "ferramenta": "nodulos", "id": -1}
        self.l_nums.setText(AC.texto_dos_numeros(prov) + (f"\nLobo: {self.lobo}" if self.lobo else ""))
        self.l_ant.setText(self._texto_anterior(prov))

    def _texto_anterior(self, prov: dict) -> str:
        from ipe.ui.viewer import achados_painel as AP
        try:
            exames = list(getattr(self.tab, "study_order", None) or [self.tab.study_uid])
            datas, outros = AP.carregar_outros(self.tab, self.tab.repo, exames)
            c = AP.correspondencia(self.tab.repo, prov, outros, datas)
        except Exception:  # noqa: BLE001
            log.exception("nódulo no anterior")
            return ""
        if c is None:
            return "Nenhum nódulo revisado num exame anterior neste lugar."
        from ipe.core.i18n import tr
        b, cr = c["achado"], c["crescimento"]
        partes = "; ".join(tr(x) for x in cr.get("lista") or []) or tr(cr["partes"])
        return tr(f"Mesmo nódulo que {b['rotulo']} de {cr['quando']} ({tr(c['como'])}): {partes}.")

    # ------------------------------------------------------------ guardar
    def guardar(self) -> dict | None:
        if self.mascara is None or self.achado is not None:
            return self.achado
        from ipe.ui.viewer.achados_painel import _usuario
        lim = float(self.s_limiar.value())
        item = {"series_uid": self.series_uid, "tipo": ND.TIPO, "local": self.lobo, "posicao": self.centro,
                "numeros": self.numeros, "modelo": MODELO, "versao": "",
                "elegibilidade": f"clique no ponto, limiar {lim:.0f} HU"
                                 + (", separado dos vasos" if self.c_abrir.isChecked() else "")
                                 + (". Atenção: " + "; ".join(self.avisos) if self.avisos else "")}
        self.achado = self.tab.repo.adicionar_achado(self.study_uid, ND.FERRAMENTA, item, "confirmado", _usuario())
        self.b_guardar.setEnabled(False)
        self.b_acomp.setEnabled(False)
        self.tab.status_message.emit(f"Nódulo {self.achado['rotulo']} guardado nos Achados de IA, confirmado.")
        return self.achado

    def guardar_e_acompanhar(self) -> int | None:
        a = self.guardar()
        if a is None:
            return None
        from ipe.ui.viewer import achados_painel as AP
        p = AP.abrir(self.tab, a["id"])
        lid = p.acompanhar()
        if lid is not None and self.mascara is not None:
            self._mascara_na_medida(lid)
        return lid

    def _mascara_na_medida(self, lid: int) -> None:
        """A medida da lesão leva o volume da segmentação."""
        for v in self.tab.viewports:
            for ann in v.annotations:
                if (ann.meta or {}).get("lesion") == lid and (ann.meta or {}).get("achado_ia") == self.achado["id"]:
                    vol = (self.numeros.get("volume_mm3") or {}).get("v")
                    if vol is not None:
                        ann.meta["ml"] = round(float(vol) / 1000.0, 4)
                        v._store("save", ann)
                    return

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.achado is None and self.obj in self.tab.overlay_objects:
            self.tab.overlay_objects.remove(self.obj)
            for v in self.tab.viewports:
                v.update()
        super().closeEvent(e)
