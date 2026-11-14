"""Fusão e leitura PET no visualizador (mixin do ViewerTab, separado do `viewer_tab.py` na 0.100.41).

Aqui ficam: a fusão de duas séries, o layout de leitura PET (fusão, PET e MIP girando) e a fusão por arrastar uma série
sobre outra.

Os métodos continuam sendo do ViewerTab (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QProgressDialog,
)

from ipe.imaging.series import build_frames
from ipe.imaging.volume import VolumeError, build_volume
from ipe.ui.viewer.viewport import Viewport
# LAYOUTS e as tabelas de ferramentas moram na barra (0.100.39); outros módulos ainda os importam daqui
from ipe.ui.viewer.barra import BarraMixin, LAYOUTS, MEASURE_TOOLS, SLAB_CHOICES, TOOL_ICONS, TOOL_SHORT  # noqa: F401

log = logging.getLogger("ipe.ui.viewer.viewer_tab")      # o mesmo registro de antes da separação


class FusaoMixin:
    """FusaoMixin: métodos do ViewerTab separados (mesmos nomes)."""

    # ================================================================ fusão
    def _fill_fusion_menu(self) -> None:
        m = self.fusion_menu
        m.clear()
        vp = self.active
        src = self._source_series(vp) if vp is not None else None
        head = QAction("Sobrepor ao quadro ativo:", m)
        head.setEnabled(False)
        m.addAction(head)
        rows = [s for s in self.series if s.series_uid != src and s.num_images >= 3]
        rows.sort(key=lambda s: (s.modality not in ("PT", "NM"), s.study_uid != self.study_uid, s.series_number))
        for s in rows:
            a = QAction(f"{s.modality}  Se {s.series_number}  {s.description}  ({s.num_images} im)", m)
            a.triggered.connect(lambda _=False, u=s.series_uid: self.set_fusion(self.active, u))
            m.addAction(a)
        m.addSeparator()
        if any((x.modality or "").upper() == "PT" for x in self.series):     # 0.99.88
            a = QAction("Leitura PET: fusão, PET e MIP girando (clique no MIP leva aos cortes)", m)
            a.triggered.connect(self.leitura_pet)
            m.addAction(a)
            a = self._act("pet.maximo", "Ir ao SUV máximo perto do cursor (3 cm)", self.ir_ao_maximo)
            m.addAction(a)
            m.addSeparator()
        for text, fn, ok in (("Aplicar a fusão do quadro ativo a todos os quadros", self.fusion_to_all,
                              vp is not None and vp.fusion is not None),
                             ("Remover a fusão do quadro ativo", lambda: self.remove_fusion(self.active),
                              vp is not None and vp.fusion is not None)):
            a = QAction(text, m)
            a.setEnabled(ok)
            a.triggered.connect(fn)
            m.addAction(a)

    # ------------------------------------------------------------ leitura PET (0.99.88)
    def series_da_leitura_pet(self) -> tuple[str | None, str | None]:
        """(TC, PET corrigido) do exame: a TC de mais cortes (sem topograma) e o PET AC (não o NAC)."""
        pts = [x for x in self.series if (x.modality or "").upper() == "PT" and x.study_uid == self.study_uid
               and (x.num_images or 0) >= 10]
        cts = [x for x in self.series if (x.modality or "").upper() == "CT" and x.study_uid == self.study_uid
               and (x.num_images or 0) >= 10]

        def nac(x):
            d = (x.description or "").upper()
            return "NAC" in d.split() or "NAC" in d.replace("-", " ").split() or "NON AC" in d or "UNCORR" in d
        pts.sort(key=lambda x: (nac(x), -(x.num_images or 0)))
        cts.sort(key=lambda x: -(x.num_images or 0))
        return (cts[0].series_uid if cts else None), (pts[0].series_uid if pts else None)

    def leitura_pet(self) -> bool:
        """Três quadros: TC com o PET fundido, o PET e o MIP do PET girando. Clicar num foco do MIP leva os
        outros dois ao voxel mais quente daquela linha (o 3D já faz isso pelo mapa de profundidade do MIP)."""
        ct, pt = self.series_da_leitura_pet()
        if pt is None:
            self.status_message.emit("Este exame não tem série PET para a leitura.")
            return False
        uids = [u for u in (ct, pt, pt) if u]
        self.show_series(uids)
        QApplication.processEvents()
        vps = [v for v in self._shown() if v.frames]
        if ct and len(vps) >= 3:
            self.set_fusion(vps[0], pt)
        alvo = vps[-1] if vps else None
        if alvo is None:
            return False
        v3 = self.abrir_3d_no_quadro(alvo, pt, "mip", perguntar=False)
        if v3 is not None:
            try:
                alvo.state.invert = True       # MIP do PET como se lê: captação escura em fundo claro
                v3.cine(True)
            except Exception:  # noqa: BLE001
                log.debug("cine do MIP", exc_info=True)
        self.status_message.emit("Leitura PET: clique num foco do MIP para levar os cortes até ele; "
                                 "Fusão ▸ Ir ao SUV máximo procura o máximo perto do cursor.")
        return True

    def abrir_sessao_preparada(self) -> bool:
        """0.100.33: o PET/CT com a carga tumoral feita (a sessão preparada) abre direto na Leitura PET — se foi ele
        que montou o exame (sem protocolo de exibição, escolha de séries ou divisão entre monitores)."""
        from ipe.ai import pet_preparo as PP
        if not PP.config(self.settings, PP.CHAVE_ABRIR) or not self.estado_pode():
            return False
        if getattr(self, "_arranjo_de_protocolo", False):
            return False
        mods = {(s.modality or "").upper() for s in self.series}
        if "PT" not in mods or not PP.preparado(self.repo, self.study_uid):
            return False
        QTimer.singleShot(0, self.leitura_pet)
        return True

    def ir_ao_maximo(self, raio_mm: float = 15.0) -> np.ndarray | None:
        """Leva o cursor 3D e os cortes ao voxel de maior SUV numa esfera em volta do cursor (ou do centro do
        corte do quadro PET, sem cursor). É o "K" da AW — sem atalho de fábrica; o atalho fica a critério dele."""
        vp = next((v for v in [self.active] + self._shown()
                   if v is not None and v.frames and getattr(v, "suv_factor", None)
                   and getattr(v, "render3d", None) is None), None)
        if vp is None:
            self.status_message.emit("Abra o PET num quadro para procurar o máximo.")
            return None
        uid = self._source_series(vp)
        vol = self._volume_for(vp, uid, perguntar=False) if uid else None
        if vol is None:
            return None
        centro = next((w.cursor_point for w in self._shown() if getattr(w, "cursor_point", None) is not None), None)
        if centro is None:
            img = vp._img
            if img is None:
                return None
            centro = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vp.index)
        from ipe.imaging import pet_onco as PO
        p = PO.maximo_perto(vol, np.asarray(centro, float), raio_mm)
        if p is None:
            return None
        vp.cursor_point = p
        self.cursor_from_3d(vp, p)
        vp.go_to_point(p)
        vp.update()
        i, j, k = (int(round(v)) for v in vol.patient_to_voxel(p))
        suv = float(vol.data[k, j, i]) * float(vp.suv_factor)
        self.status_message.emit(f"SUV máximo perto do cursor: {suv:.2f}.")
        return p

    def _fusion_volume(self, uid: str):
        cache = self.__dict__.setdefault("_fusion_vols", {})
        if uid in cache:
            return cache[uid]
        frames = build_frames(self.repo.instances_for_series(uid), uid)
        dlg = QProgressDialog("Montando o volume da fusão…", "Cancelar", 0, len(frames), self)
        dlg.setWindowTitle("Fusão")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progress(done: int, total: int) -> bool:
            if done % 8 == 0 or done == total:
                dlg.setValue(done)
                QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            vol = build_volume(frames, self.cache, progress)
        except VolumeError as e:
            dlg.close()
            QMessageBox.information(self, "Fusão", str(e))
            return None
        dlg.close()
        while len(cache) >= 2:
            cache.pop(next(iter(cache)))
        cache[uid] = vol
        return vol

    def set_fusion(self, vp: Viewport | None, uid: str):
        """Sobrepõe a série `uid` (ex.: PET) ao quadro, colorida e com transparência."""
        from ipe.imaging.fusion import Fusion
        if vp is None or not vp.frames:
            return None
        vol = self._fusion_volume(uid)
        if vol is None:
            return None
        s = self._series_row(uid)
        suv = None
        if s is not None and s.modality == "PT":
            from ipe.imaging.suv import suv_factor_for_file
            suv = suv_factor_for_file(vol.source_path)[0]
        label = f"{s.modality} Se {s.series_number}" if s else "fusão"
        fu = Fusion(vol, label, suv, cmap="hot" if (s and s.modality in ("PT", "NM")) else "rainbow",
                    series_uid=uid)
        vp.fusion = fu
        vp._fusion_cache = None
        vp.update()
        meta = self.repo.series_meta(uid) or {}
        if vp.for_uid and meta.get("frame_of_reference") and meta["frame_of_reference"] != vp.for_uid:
            self.status_message.emit("Atenção: as séries têm referenciais espaciais diferentes — a fusão usa "
                                     "as coordenadas do paciente; confira o alinhamento.")
        else:
            self.status_message.emit(f"Fusão: {label} sobre o quadro. Ajuste opacidade, cor e janela na barra.")
        self._sync_fusion_bar()
        return fu

    # ------------------------------------------------------------ fusão por arrastar (0.99.64, plano AW M6)
    def fundir_por_arrastar(self, vp: Viewport, uid: str):
        """Série solta no canto "Fundir por cima": vai por cima do quadro, em cores."""
        if not uid or uid.startswith(("key:", "group:", "mg:", "mpr:", "dyn")):
            self.status_message.emit("Para fundir um mapa ou uma reconstrução, use o botão direito no quadro dele ▸ "
                                     "Fundir este quadro sobre…")
            return None
        return self.set_fusion(vp, uid)

    def fundir_quadro(self, origem: Viewport, alvo: Viewport):
        """O que o quadro `origem` mostra (série, ou mapa da dinâmica: ADC, SER, cinético…) por cima do `alvo`."""
        from ipe.imaging.fusion import Fusion
        dq = self._dyn_do_quadro(origem)
        if dq is not None:
            from ipe.imaging.dynamic import COMPOSTOS, MAPS
            sess, chave = dq
            if chave in COMPOSTOS:
                self.status_message.emit("O mapa em cor já é colorido: funda um mapa de valores (SER, realce, "
                                         "cinético…).")
                return None
            if chave.startswith("ph:") or chave.startswith("ph"):
                try:
                    vol = self._volume_da_fase_dyn(sess, int(chave.split(":")[-1].lstrip("ph")))
                except ValueError:
                    vol = None
                rotulo, cmap = f"fase {chave}", "rainbow"
            else:
                vol = self._volume_do_mapa(sess, chave)
                rotulo, cmap = MAPS.get(chave, (chave,) * 5)[0], (MAPS.get(chave, ("",) * 5)[4] or "rainbow")
            if vol is None:
                return None
            fu = Fusion(vol, rotulo, None, cmap=cmap)
            alvo.fusion = fu
            alvo._fusion_cache = None
            alvo.update()
            self._activate(alvo)
            self.status_message.emit(f"Fusão: {rotulo} sobre o quadro. Ajuste opacidade, cor e janela na barra.")
            self._sync_fusion_bar()
            return fu
        uid = self._source_series(origem)
        if uid is None or uid.startswith(("key:", "group:", "mg:")):
            self.status_message.emit("Este quadro não tem uma série que dê para fundir.")
            return None
        self._activate(alvo)
        return self.set_fusion(alvo, uid)

    def remove_fusion(self, vp: Viewport | None) -> None:
        if vp is None:
            return
        vp.fusion = None
        vp._fusion_cache = None
        vp.fusion_value = None
        vp.update()
        self._sync_fusion_bar()

    def fusion_to_all(self) -> None:
        vp = self.active
        if vp is None or vp.fusion is None:
            return
        for v in self._shown():
            if v is not vp and v.frames:
                v.fusion = vp.fusion
                v._fusion_cache = None
                v.update()

    def _sync_fusion_bar(self) -> None:
        if not hasattr(self, "fusion_bar"):
            return
        vp = self.active
        fu = vp.fusion if vp is not None else None
        self.fusion_bar.setVisible(fu is not None or any(v.fusion is not None for v in self._shown()))
        if fu is None:
            self.fusion_label.setText("  Fusão (quadro ativo sem fusão)")
            return
        widgets = (self.fusion_alpha, self.fusion_cmap, self.fusion_lo, self.fusion_hi, self.fusion_hide)
        for wdg in widgets:
            wdg.blockSignals(True)
        self.fusion_label.setText(f"  Fusão: {fu.label}" + (f" ({fu.unit})" if fu.unit else ""))
        self.fusion_alpha.setValue(int(round(fu.alpha * 100)))
        i = self.fusion_cmap.findData(fu.cmap)
        if i >= 0:
            self.fusion_cmap.setCurrentIndex(i)
        self.fusion_lo.setValue(fu.lo)
        self.fusion_hi.setValue(fu.hi)
        self.fusion_hide.setChecked(fu.hide_below)
        for wdg in widgets:
            wdg.blockSignals(False)

    def _fusion_set(self, **kw) -> None:
        vp = self.active
        fu = vp.fusion if vp is not None else None
        if fu is None:
            return
        for k, v in kw.items():
            setattr(fu, k, v)
        if fu.hi <= fu.lo:
            fu.hi = fu.lo + 1e-3
        fu.changed()
        for v in self.viewports:
            if v.fusion is fu:
                v.update()
