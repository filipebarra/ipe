"""MPR, volumes e planos no visualizador (mixin do ViewerTab, separado do `viewer_tab.py` na 0.100.41).

Aqui ficam: o modo MPR, o volume de cada série (com a mesa tirada), os mapas da dinâmica como quadro, o plano de cada
quadro (axial, coronal, sagital, oblíquo, curvo, espessura) e a reconstrução da etapa em 3D.

Os métodos continuam sendo do ViewerTab (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QProgressDialog,
)

from ipe.core.sysinfo import auto_volume_mb
from ipe.imaging.series import build_frames
from ipe.imaging.curved import CurvedPlane
from ipe.imaging.volume import SLAB_MODES, MPRPlane, ObliquePlane, VolumeError, build_volume
from ipe.ui.viewer.viewport import Viewport
# LAYOUTS e as tabelas de ferramentas moram na barra (0.100.39); outros módulos ainda os importam daqui
from ipe.ui.viewer.barra import BarraMixin, LAYOUTS, MEASURE_TOOLS, SLAB_CHOICES, TOOL_ICONS, TOOL_SHORT  # noqa: F401

log = logging.getLogger("ipe.ui.viewer.viewer_tab")      # o mesmo registro de antes da separação


class MPRMixin:
    """MPRMixin: métodos do ViewerTab separados (mesmos nomes)."""

    # ================================================================ MPR
    def toggle_mpr(self, on: bool) -> None:
        if on:
            ok = self._enter_mpr()
            if not ok:
                self.mpr_action.blockSignals(True)
                self.mpr_action.setChecked(False)
                self.mpr_action.blockSignals(False)
        else:
            self._exit_mpr()

    def _source_series(self, vp: Viewport | None) -> str | None:
        """Série original do quadro (também quando ele já mostra uma reconstrução)."""
        if vp is None:
            return None
        if vp.mpr_plane is not None and vp.series_uid.startswith("mpr:"):
            return vp.series_uid.split(":")[1]
        if getattr(vp, "render3d", None) is not None:
            return vp.render3d.src_uid or None
        if vp.series_uid.startswith("group:"):
            # Dinâmica: a série da fase que está na tela. Sem isso, abrir sempre como dinâmica
            # (0.69) tiraria o MPR, o oblíquo e a segmentação de toda série que é fase.
            try:
                g = self.groups.get(int(vp.series_uid.split(":")[1]))
            except ValueError:
                g = None
            if g is None or g.get("fases") or not g.get("series_uids"):
                return None
            return g["series_uids"][min(max(int(vp.phase or 0), 0), len(g["series_uids"]) - 1)]
        if not vp.frames or vp.frames[0].is_virtual or vp.series_uid.startswith(("key:", "mg:")):
            return None
        return vp.series_uid

    def _volume_for(self, src: Viewport, uid: str, perguntar: bool = True,
                    frames: list | None = None, chave: str | None = None):
        """Volume da série `uid` (do cache, se já montado). `frames`/`chave`: monta destes quadros
        — a fase de uma dinâmica que o protocolo pede (0.90)."""
        # em série 4D cada fase tem o seu volume: a chave do cache leva a fase junto
        fase4d = src.cardiac_where()[1] if getattr(src, "is_4d", None) and src.is_4d() else 0
        if chave is None:
            chave = uid if not fase4d else f"{uid}#fase{fase4d}"
        vol = self._volumes.get(chave)
        if vol is not None:
            return vol
        if frames is None:
            frames = src.frames
            if src.mpr_plane is not None or src.series_uid != uid:
                frames = build_frames(self.repo.instances_for_series(uid), uid)
        else:
            fase4d = 0
        limit = int(self.settings.get("performance.max_volume_mb", 0) or auto_volume_mb())
        h, w = src._img.pixels.shape[:2] if src._img is not None and src.mpr_plane is None else (512, 512)
        est = len(frames) * h * w * 2 / 1024 / 1024
        if est > limit and not perguntar:
            return None
        if est > limit and QMessageBox.question(
                self, "MPR", f"O volume vai ocupar cerca de {est:,.0f} MB de memória, acima do "
                f"limite de {limit:,.0f} MB (Preferências → Desempenho).\n\nMontar mesmo assim?"
                .replace(",", ".")) != QMessageBox.Yes:
            return None
        if not perguntar:
            # pedido do protocolo ao abrir o exame: sem janela de progresso — ela aparecia e
            # fechava e levava o foco do teclado junto (as setas das etapas paravam de responder)
            class _SemJanela:
                def close(self):
                    pass
            dlg = _SemJanela()

            def progress(done: int, total: int) -> bool:
                return True
        else:
            dlg = QProgressDialog("Montando volume…", "Cancelar", 0, len(frames), self)
            dlg.setWindowTitle("MPR")
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(300)

            def progress(done: int, total: int) -> bool:
                if done % 8 == 0 or done == total:
                    dlg.setValue(done)
                    QApplication.processEvents()
                return not dlg.wasCanceled()
        fase = fase4d
        try:
            vol = build_volume(frames, self.cache, progress, phase=fase)
        except VolumeError as e:
            dlg.close()
            if perguntar:
                QMessageBox.information(self, "MPR", str(e))
            return None
        dlg.close()
        if bool(self.settings.get("viewer.tirar_mesa", False)) and (src.modality or "").upper() == "CT":
            vol = self.tirar_a_mesa(vol)                    # 0.99.31 (onda A5)
        # mantém só o volume atual na memória — o protocolo que pede duas fases guarda as duas,
        # para a etapa de 4 MIPs (2 fases × 2 metades) não montar cada fase duas vezes
        manter = {k: v for k, v in self._volumes.items() if k.startswith("etapa:")} if chave.startswith("etapa:") else {}
        self._volumes = dict(list(manter.items())[-1:]) | {chave: vol}
        return vol

    def tirar_a_mesa(self, vol):
        """O volume do MPR/3D sem a mesa da TC (imaging/mesa.py). A série original não muda."""
        from ipe.imaging import mesa
        try:
            dados, mexeu = mesa.tirar_a_mesa(vol.data, vol.dx, vol.dy, vol.dz)
        except Exception:  # noqa: BLE001
            log.exception("tirar a mesa")
            return vol
        if mexeu:
            vol.data = dados
            vol.warnings.append("mesa da TC retirada (só no MPR e no 3D)")
        return vol

    def apagar_imagem(self, vp) -> bool:
        """0.99.31 (onda A7): apaga só a imagem do quadro (botão direito ▸ Apagar esta imagem…)."""
        from ipe.auth import session as S
        if vp is None or not vp.frames or vp.frames[0].is_virtual:
            return False
        if not S.require("delete", self, "apagar imagens"):
            return False
        f = vp.frames[vp.index]
        n_mesmo = sum(1 for x in vp.frames if x.sop_uid == f.sop_uid)
        extra = f" (o arquivo tem {n_mesmo} quadros; todos saem)" if n_mesmo > 1 else ""
        if self.perguntar_apagar_imagem(f"Apagar esta imagem (nº {f.instance_number}){extra}?\n\n"
                                        "Medidas e imagem-chave dela saem junto. O arquivo só é apagado se "
                                        "estiver no armazenamento do programa; fica no registro de acesso.") is False:
            return False
        try:
            self.repo.delete_instance(f.sop_uid, getattr(self, "storage_root", None))
        except Exception as e:  # noqa: BLE001
            QMessageBox.information(self, "Apagar imagem", str(e).split(": ", 1)[-1] if "Error:" in str(e) else str(e))
            return False
        S.audit(self.repo, "apagou_imagem", f"imagem nº {f.instance_number} — {f.sop_uid}", study_uid=vp.study_uid)
        i = vp.index
        restantes = [x for x in vp.frames if x.sop_uid != f.sop_uid]
        vp.frames[:] = restantes
        vp.index = min(i, len(restantes) - 1)
        vp.go_to(vp.index)
        self.status_message.emit(f"Imagem nº {f.instance_number} apagada.")
        return True

    def perguntar_apagar_imagem(self, texto: str) -> bool:
        return QMessageBox.question(self, "Apagar imagem", texto) == QMessageBox.Yes

    def alternar_mesa(self, on: bool) -> None:
        """Liga/desliga "Tirar a mesa da TC" e remonta os volumes na próxima vez."""
        self.settings.set("viewer.tirar_mesa", bool(on))
        self.settings.save()
        self._volumes = {}
        self.status_message.emit(("Mesa da TC: retirada" if on else "Mesa da TC: mostrada")
                                 + " nos próximos volumes montados — feche e abra o MPR/3D para valer agora.")

    # ------------------------------------------------------------ mapas da dinâmica
    def _mapa_do_quadro(self, vp) -> tuple | None:
        """(sessão, chave do mapa) se o quadro mostra um mapa paramétrico da dinâmica."""
        sess = getattr(self, "dyn", None)
        if sess is None or vp is None:
            return None
        from ipe.imaging.dynamic import MAPS
        chave = getattr(vp, "dyn_key", None)
        if chave not in MAPS:
            return None
        pref = (f"dyn:{id(sess.maps)}:", f"dynmpr:{id(sess.maps)}:")
        return (sess, chave) if vp.series_uid.startswith(pref) else None

    def _volume_do_mapa(self, sess, kind: str):
        """Volume 3D do mapa, para reconstruir em outro plano. Monta uma vez por mapa.

        O mapa é calculado corte a corte, sob demanda. Virar axial/coronal/sagital obriga a
        calcular **todos** os cortes: é demorado, então tem barra e botão de parar.
        """
        from ipe.imaging.dynamic import COMPOSTOS
        if kind in COMPOSTOS:                    # 0.99.64: o mapa em cor fica no plano da aquisição
            self.status_message.emit("O mapa em cor é só no plano da aquisição: reformate um mapa de valores.")
            return None
        cache = getattr(self, "_vol_mapas", None)
        if cache is None:
            cache = self._vol_mapas = {}
        chave = f"{id(sess.maps)}:{kind}"
        if chave in cache:
            return cache[chave]
        from ipe.imaging.dynamic import MAPS
        from ipe.imaging.volume import VolumeError
        # Um mapa de RM de mama do acervo dele dá ~105 MB (100 cortes de 512²) e leva uns 7 s.
        # Com quatro mapas reorientados isso passa de 400 MB, então o cache guarda só os dois
        # últimos e o limite de memória do MPR também vale aqui.
        est = sess.maps.n * sess.maps.shape[0] * sess.maps.shape[1] * 4 / 1024 / 1024
        limite = int(self.settings.get("performance.max_volume_mb", 0) or auto_volume_mb())
        if est > limite and QMessageBox.question(
                self, "Reconstrução do mapa",
                f"O volume do mapa vai ocupar cerca de {est:,.0f} MB, acima do limite de "
                f"{limite:,.0f} MB (Preferências → Desempenho).\n\nMontar mesmo assim?"
                .replace(",", ".")) != QMessageBox.Yes:
            return None
        dlg = QProgressDialog(f"Montando o volume do mapa {MAPS[kind][0]}…", "Cancelar",
                              0, sess.maps.n, self)
        dlg.setWindowTitle("Reconstrução do mapa")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progresso(feitos: int, total: int) -> bool:
            if feitos % 4 == 0 or feitos == total:
                dlg.setValue(feitos)
                QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            vol = sess.maps.volume_do_mapa(kind, progresso)
        except VolumeError as e:
            dlg.close()
            QMessageBox.information(self, "Reconstrução do mapa", str(e))
            return None
        finally:
            dlg.close()
        cache[chave] = vol
        while len(cache) > 2:                   # guarda só os dois mapas mais recentes
            cache.pop(next(iter(cache)))
        return vol

    def _dyn_do_quadro(self, vp) -> tuple | None:
        """(sessão, chave) se o quadro é da dinâmica: mapa, subtração ou fase — no plano da
        aquisição ou já reconstruído."""
        sess = getattr(self, "dyn", None)
        if sess is None or vp is None:
            return None
        chave = str(getattr(vp, "dyn_key", "") or "")
        if not chave:
            return None
        mid = id(sess.maps)
        pref = (f"dyn:{mid}:", f"dynph:{mid}:", f"dynmpr:{mid}:")
        return (sess, chave) if vp.series_uid.startswith(pref) else None

    def _volume_da_fase_dyn(self, sess, i: int):
        """Volume de uma fase da dinâmica, para reconstruir o quadro de fase em outro plano."""
        cache = getattr(self, "_vol_mapas", None)
        if cache is None:
            cache = self._vol_mapas = {}
        chave = f"{id(sess.maps)}:ph{i}"
        if chave in cache:
            return cache[chave]
        from ipe.imaging.volume import VolumeError
        dlg = QProgressDialog(f"Montando a fase {i + 1} em 3D…", "Cancelar", 0, sess.maps.n, self)
        dlg.setWindowTitle("Reconstrução da fase")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progresso(feito, total):
            if feito % 8 == 0 or feito == total:
                dlg.setValue(feito)
                QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            vol = sess.maps.volume_da_fase(i, progresso)
        except VolumeError as e:
            QMessageBox.information(self, "Reconstrução da fase", str(e))
            return None
        finally:
            dlg.close()
        cache[chave] = vol
        while len(cache) > 2:
            cache.pop(next(iter(cache)))
        return vol

    def reformatar_mapa(self, vp, sess, kind: str, nome: str) -> bool:
        """Põe um quadro da dinâmica em axial, coronal, sagital ou oblíquo — ou de volta ao plano
        gravado. Vale para mapa, subtração **e fase** (0.68: pedido dele, *"no dinâmico, permita
        que eu possa mudar o eixo (sagital, axial, coronal e oblíquo)"* — antes só o mapa virava,
        e nunca em oblíquo).

        O quadro reorientado **não entra nas curvas**: ROI e ponto são medidos na grade em que a
        dinâmica foi adquirida, e uma ROI desenhada num corte reconstruído atravessaria vários
        cortes originais. Em vez de devolver número errado, o quadro sai da conta e diz por quê.
        A segmentação da lesão, ao contrário, funciona em qualquer plano: a semente é um ponto do
        paciente.
        """
        from ipe.imaging.dynamic import MAPS
        e_fase = kind.startswith("ph:")
        if nome == "Original":
            # Volta no corte que ele está olhando, não no que o índice do plano novo calhar de ser:
            # o índice de um sagital não quer dizer nada no plano da aquisição.
            idx = None
            centro = vp.ponto_central()
            if centro is not None:
                try:
                    idx = sess.maps.plane("ei" if e_fase else kind).index_for_point(np.asarray(centro, float))
                except Exception:  # noqa: BLE001
                    idx = None
            sess.show_view(vp, kind, index=idx)
            self._update_mpr_bar()
            self.update_reference_lines()
            sess.refresh()
            alvo = f"fase {int(kind[3:]) + 1}" if e_fase else MAPS[kind][0]
            self.status_message.emit(f"De volta ao plano da aquisição: {alvo}.")
            return True
        vol = self._volume_da_fase_dyn(sess, int(kind[3:])) if e_fase else self._volume_do_mapa(sess, kind)
        if vol is None:
            return False
        centro = vp.ponto_central()
        if centro is None:
            centro = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        if nome == "Oblíquo":
            pl = vp.plane()
            if pl is None:
                QMessageBox.information(self, "Oblíquo", "Este quadro não tem geometria para virar oblíquo.")
                return False
            try:
                plano = ObliquePlane.do_plano(vol, pl[1], pl[2], centro)
            except VolumeError as e:
                QMessageBox.information(self, "Oblíquo", str(e))
                return False
        else:
            plano = next((MPRPlane(vol, ax) for ax in (0, 1, 2) if MPRPlane(vol, ax).name == nome), None)
        if plano is None:
            QMessageBox.information(self, "Reconstrução da dinâmica",
                                    f"Não dá para montar o plano {nome} com a geometria desta dinâmica.")
            return False
        self._mostrar_plano_dyn(vp, sess, kind, plano, centro)
        return True

    def _mostrar_plano_dyn(self, vp, sess, kind: str, plano, centro) -> None:
        """Põe no quadro um plano reconstruído da dinâmica (mapa, subtração ou fase)."""
        from ipe.imaging.dynamic import MAPS
        info = self.study_infos.get(getattr(sess, "study_uid", self.study_uid), self.study_info)
        largura, nivel, janela_ok = vp.state.width, vp.state.level, vp.state.window_set
        vp.mpr_plane = plano
        vp.key_frames = self.key_set
        if kind.startswith("ph:"):
            i = int(kind[3:])
            vp.modality = "MR"
            rotulo = f"Fase {i + 1} — {sess.maps.dset.labels[i]} — {plano.name}"
        else:
            nome_mapa, _desc, u_rel, u_abs, _cmap = MAPS[kind]
            unidade = u_rel if sess.maps.relative else u_abs
            vp.modality = f"MAP {kind}"
            rotulo = (f"Mapa {nome_mapa} ({unidade}) — {plano.name}" if unidade
                      else f"Mapa {nome_mapa} — {plano.name}")
        vp.set_series(f"dynmpr:{id(sess.maps)}:{kind}:{plano.axis}", plano.frames(), rotulo, info,
                      start_index=plano.index_for_point(centro))
        vp.dyn_key = kind
        if kind.startswith("ph:"):
            if janela_ok:
                vp.set_window(largura, nivel, emit=False)
            vp.set_colormap("")
        else:
            w, l = sess.maps.window(kind)
            vp.set_window(w, l, emit=False)
            vp.set_colormap(vp.cor_padrao() or MAPS[kind][4])
        vp.ghosts = []
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        self._sync_slab_controls(vp)
        self.update_reference_lines()
        sess.refresh()
        self.status_message.emit(f"Reconstrução da dinâmica em {plano.name} ({plano.n} cortes). "
                                 "As curvas saem do plano da aquisição: volte ao original para "
                                 "medir ROI.")

    def reconstruct_plane(self, name: str) -> bool:
        """Reconstrução num único plano (axial, coronal ou sagital) no quadro ativo; os outros
        quadros continuam como estão (dá para comparar com a série original ao lado)."""
        src = self.active
        mapa = self._mapa_do_quadro(src)
        if mapa is not None:
            return self.reformatar_mapa(src, mapa[0], mapa[1], name)
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "Reconstrução", "Selecione um quadro com uma série (TC, RM, PET…).")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        plane = next((MPRPlane(vol, ax) for ax in (0, 1, 2) if MPRPlane(vol, ax).name == name), None)
        if plane is None:
            QMessageBox.information(self, "Reconstrução", f"Não foi possível montar o plano {name} desta série.")
            return False
        width, level, win_set = src.state.width, src.state.level, src.state.window_set
        center = None
        if src._img is not None:
            h, w = src._img.pixels.shape[:2]
            center = src.pixel_to_patient(w / 2, h / 2)
        if center is None:
            center = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        for_uid = src.for_uid
        vp = src
        vp.mpr_plane = plane
        vp.for_uid = for_uid
        vp.study_uid = study_uid
        vp.modality = s.modality if s else ""
        vp.key_frames = self.key_set
        vp.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"{plane.name} (reconstrução)",
                      self.study_infos.get(study_uid, self.study_info), start_index=plane.index_for_point(center))
        if win_set:
            vp.set_window(width, level, emit=False)
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        self._sync_slab_controls(vp)
        self.update_reference_lines()
        self.status_message.emit(f"{plane.name} reconstruído no quadro ativo ({plane.n} cortes). "
                                 "Espessura (slab) na barra MPR.")
        return True

    # --------------------------------------------------------------- plano do quadro
    PLANOS = ("Axial", "Coronal", "Sagital", "Oblíquo")

    def menu_de_plano(self, vp: Viewport, global_pos) -> None:
        """Menu da linha de orientação, no canto do quadro."""
        atual = vp.plano_nome()
        m = QMenu(self)
        cab = QAction("Plano do quadro", m)
        cab.setEnabled(False)
        m.addAction(cab)
        for nome in self.PLANOS:
            a = QAction(nome, m, checkable=True, checked=(nome == atual))
            a.triggered.connect(lambda _=False, n=nome, q=vp: self.reformatar(q, n))
            m.addAction(a)
        if isinstance(getattr(vp, "mpr_plane", None), ObliquePlane):
            m.addSeparator()
            g = QAction("Girar plano (arrastar)", m, checkable=True,
                        checked=(self.left_tool == "rotplane"))
            g.triggered.connect(lambda: self.set_left_tool("rotplane"))
            m.addAction(g)
        ehmapa = self._dyn_do_quadro(vp) is not None
        if getattr(vp, "mpr_plane", None) is not None:
            m.addSeparator()
            back = QAction("Voltar ao plano da aquisição" if ehmapa else "Voltar à série original", m)
            back.triggered.connect(lambda _=False, q=vp: self.reformatar(q, "Original"))
            m.addAction(back)
        m.exec(global_pos)

    def reformatar(self, vp: Viewport, nome: str) -> bool:
        """Troca o plano do quadro: axial, coronal, sagital, oblíquo — ou volta à série original."""
        anterior, self.active = self.active, vp
        try:
            dyn = self._dyn_do_quadro(vp)
            if dyn is not None:
                return self.reformatar_mapa(vp, dyn[0], dyn[1], nome)
            if nome == "Original":
                self._plane_back()
                return True
            if nome == "Oblíquo":
                return self.obliquo_do_plano_atual(vp)
            return self.reconstruct_plane(nome)
        finally:
            if anterior is not None and anterior is not vp:
                self.active = anterior

    def obliquo_do_plano_atual(self, vp: Viewport) -> bool:
        """Vira o quadro para oblíquo **sem mudar a imagem**: mesmo plano, agora girável.

        Era o pedido: "se estiver em axial, mude para oblíquo mantendo a mesma posição e imagem,
        e agora permita que eu possa girar". O oblíquo que já existia nascia de uma linha
        desenhada, e por isso saía sempre perpendicular ao que estava na tela.
        """
        uid = self._source_series(vp)
        pl = vp.plane()
        if uid is None or pl is None:
            QMessageBox.information(self, "Oblíquo", "Escolha um quadro com uma série de cortes "
                                    "(TC, RM, PET…).")
            return False
        vol = self._volume_for(vp, uid)
        if vol is None:
            return False
        _pos, row, col, _n = pl
        centro = vp.ponto_central()
        if centro is None:
            centro = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        try:
            plano = ObliquePlane.do_plano(vol, row, col, centro)
        except VolumeError as e:
            QMessageBox.information(self, "Oblíquo", str(e))
            return False
        antigo = vp.mpr_plane
        if antigo is not None:
            plano.set_slab(antigo.slab_mm, antigo.mode)
        self._mostrar_plano(vp, uid, plano, centro)
        self.status_message.emit("Oblíquo a partir do plano atual: a imagem é a mesma. Use "
                                 "“Girar plano” na barra de MPR para inclinar.")
        return True

    def girar_plano(self, vp: Viewport, graus_h: float, graus_v: float) -> bool:
        """Gira o plano oblíquo do quadro em torno dos eixos da tela."""
        plano = getattr(vp, "mpr_plane", None)
        if not isinstance(plano, ObliquePlane):
            return False
        dyn = self._dyn_do_quadro(vp)
        if dyn is not None:
            try:
                novo = plano.girar(graus_h, graus_v, vp.ponto_central())
            except VolumeError:
                return False
            self._mostrar_plano_dyn(vp, dyn[0], dyn[1], novo, vp.ponto_central())
            return True
        uid = self._source_series(vp)
        if uid is None:
            return False
        centro = vp.ponto_central()
        try:
            novo = plano.girar(graus_h, graus_v, centro)
        except VolumeError:
            return False
        novo.set_slab(plano.slab_mm, plano.mode)
        self._mostrar_plano(vp, uid, novo, centro)
        return True

    def _mostrar_plano(self, vp: Viewport, uid: str, plano, centro) -> None:
        """Põe o plano reconstruído no quadro, mantendo janela, cor e o ponto que estava à vista."""
        width, level, win_set = vp.state.width, vp.state.level, vp.state.window_set
        zoom, pan, cmap = vp.state.zoom, vp.state.pan, vp.state.cmap
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        vp.mpr_plane = plano
        vp.study_uid = study_uid
        vp.modality = s.modality if s else ""
        vp.key_frames = self.key_set
        idx = plano.index_for_point(centro) if centro is not None else plano.idx0
        sufixo = f"  {SLAB_MODES[plano.mode]} {plano.slab_mm:.0f} mm" if plano.slab_mm else ""
        rotulo = f"{plano.name} (reconstrução)" + sufixo
        vp.set_series(f"mpr:{uid}:{plano.axis}", plano.frames(), rotulo,
                      self.study_infos.get(study_uid, self.study_info), start_index=idx)
        if win_set:
            vp.set_window(width, level, emit=False)
        vp.state.zoom, vp.state.pan, vp.state.cmap = zoom, pan, cmap
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        self._sync_slab_controls(vp)
        self.update_reference_lines()

    def _oblique_target(self, src: Viewport) -> Viewport:
        """Quadro que vai mostrar o oblíquo: o mesmo de antes; senão, no layout 1×1 abre 1×2;
        senão o quadro seguinte ao de origem."""
        if self._maximized is not None:
            self.toggle_maximize(self._maximized)
        shown = self._shown()
        for t in src.oblique_targets:
            if t in shown and t is not src:
                return t
        if len(shown) == 1:
            self.set_layout(1, 2)
            shown = self._shown()
        i = shown.index(src) if src in shown else 0
        return shown[(i + 1) % len(shown)]

    def create_oblique(self, src: Viewport, p0, p1) -> bool:
        """MPR oblíquo: plano que contém a linha desenhada em `src` e a normal de `src`."""
        uid = self._source_series(src)
        pl = src.plane()
        if uid is None or pl is None:
            QMessageBox.information(self, "MPR oblíquo",
                                    "Desenhe a linha num quadro com uma série de cortes (TC, RM, PET…).")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        try:
            plane = ObliquePlane(vol, p0, p1, pl[3])
        except VolumeError as e:
            QMessageBox.information(self, "MPR oblíquo", str(e))
            return False
        target = self._oblique_target(src)
        if target is src:
            QMessageBox.information(self, "MPR oblíquo", "Não há outro quadro para mostrar o oblíquo.")
            return False
        old = target.mpr_plane
        if old is not None:
            plane.set_slab(old.slab_mm, old.mode)
        width, level, win_set = src.state.width, src.state.level, src.state.window_set
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        target.mpr_plane = plane
        target.for_uid = src.for_uid
        target.study_uid = study_uid
        target.modality = s.modality if s else ""
        target.key_frames = self.key_set
        suffix = f"  {SLAB_MODES[plane.mode]} {plane.slab_mm:.0f} mm" if plane.slab_mm else ""
        target.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"MPR Oblíquo{suffix}",
                          self.study_infos.get(study_uid, self.study_info), start_index=plane.idx0)
        if win_set:
            target.set_window(width, level, emit=False)
        target.anonymize = self.anonymize
        target.state.cmap = src.state.cmap
        for v in self.viewports:
            if target in v.oblique_targets and v is not src:
                v.oblique_targets.remove(target)
        src.oblique_targets = [target]
        self._update_mpr_bar()
        self._sync_slab_controls(target)
        self.update_reference_lines()
        src.update()
        self.status_message.emit("Oblíquo criado: role no quadro para mover o plano; desenhe outra linha "
                                 "para mudar o ângulo. Espessura (MIP) na barra MPR.")
        return True

    def create_curved(self, src: Viewport, pts) -> bool:
        """MPR curvo pelo caminho marcado em `src` (pontos 3D); gira com a rolagem."""
        uid = self._source_series(src)
        pl = src.plane()
        if uid is None or pl is None:
            QMessageBox.information(self, "MPR curvo", "Marque os pontos num quadro com uma série de cortes.")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        try:
            plane = CurvedPlane(vol, pts, pl[3])
        except VolumeError as e:
            QMessageBox.information(self, "MPR curvo", str(e))
            return False
        target = self._oblique_target(src)
        if target is src:
            QMessageBox.information(self, "MPR curvo", "Não há outro quadro para mostrar o MPR curvo.")
            return False
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        target.mpr_plane = plane
        target.for_uid = ""
        target.study_uid = study_uid
        target.modality = s.modality if s else ""
        target.key_frames = self.key_set
        target.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"MPR curvo ({plane.length_mm:.0f} mm)",
                          self.study_infos.get(study_uid, self.study_info), start_index=0)
        if src.state.window_set:
            target.set_window(src.state.width, src.state.level, emit=False)
        target.state.cmap = src.state.cmap
        target.anonymize = self.anonymize
        src.oblique_targets = [target]
        self._update_mpr_bar()
        self.update_reference_lines()
        self.status_message.emit(f"MPR curvo: {plane.length_mm:.0f} mm de caminho; role no quadro para girar "
                                 "o corte em volta do caminho (0–180°).")
        return True

    def compare_phases(self, fase_a: int = 0, fase_b: int | None = None) -> bool:
        """Mesma série em dois quadros, em duas fases do ciclo, rolando os cortes juntos."""
        vp = self.active or (self.viewports[0] if self.viewports else None)
        if vp is None or not vp.is_4d():
            QMessageBox.information(self, "Cardíaco 4D",
                                    "Abra uma série com fases (cine, cardíaca 4D) antes.")
            return False
        uid, info = vp.series_uid, vp.cardiac
        fase_b = info.n_phases // 2 if fase_b is None else fase_b
        self.set_layout(1, 2)
        for alvo, fase in zip(self.viewports[:2], (fase_a, fase_b)):
            self.load_series_into(alvo, uid)
            alvo.set_cardiac_phase(fase, wrap=False)
        self.hub.sync_scroll = True
        self.status_message.emit(
            f"Comparando a fase {fase_a + 1} com a fase {fase_b + 1} — a rolagem anda nos dois.")
        if self.viewports:
            self._activate(self.viewports[0])
        return True

    def open_surface(self):
        """Superfície por faixa de densidade (osso, pele, metal) e arquivo STL."""
        src = self.active
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "Superfície",
                                    "Selecione um quadro com uma série de cortes (TC, RM…).")
            return None
        vol = self._volume_for(src, uid)
        if vol is None:
            return None
        s = self._series_row(uid)
        from ipe.ui.surface_dialog import SurfaceDialog
        dlg = SurfaceDialog(vol, None, (0, 0, 0),
                            f"Se {s.series_number} {s.description}" if s else "Superfície", self)
        dlg.exec()
        return dlg

    def open_3d(self, mode: str = "vr"):
        """Põe o volume da série do quadro ativo em 3D, no próprio quadro."""
        src = self.active
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "3D", "Selecione um quadro com uma série de cortes (TC, RM, PET…).")
            return None
        return self.abrir_3d_no_quadro(src, uid, mode, perguntar=True)

    def abrir_3d_no_quadro(self, src: Viewport, uid: str, mode: str = "vr", perguntar: bool = False,
                           frames: list | None = None, chave: str | None = None):
        """3D da série `uid` no quadro `src` — o mesmo do botão 3D, com todas as ferramentas da barra.
        Sem `perguntar` (o protocolo de exibição, 0.91) não abre janela nenhuma; `frames`/`chave`:
        de uma fase da dinâmica."""
        from ipe.imaging.render3d import Renderer3D
        from ipe.ui.viewer.render3d_view import View3D
        vol = self._volume_for(src, uid, perguntar=perguntar, frames=frames, chave=chave)
        if vol is None:
            return None
        if perguntar:
            dlg = QProgressDialog("Preparando o volume 3D…", "Cancelar", 0, 100, self)
            dlg.setWindowTitle("3D")
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(300)

            def progress(done: int, total: int) -> bool:
                dlg.setValue(int(done * 100 / max(total, 1)))
                QApplication.processEvents()
                return not dlg.wasCanceled()
        else:
            dlg = None

            def progress(done: int, total: int) -> bool:
                return True
        try:
            r = Renderer3D(vol, max_dim=int(self.settings.get("viewer.render3d_size", 256)), progress=progress)
        except InterruptedError:
            if dlg is not None:
                dlg.close()
            return None
        if dlg is not None:
            dlg.close()
        s = self._series_row(uid)
        window = (src.state.width, src.state.level) if src.state.window_set else vol.window
        title = f"Se {s.series_number} {s.description}" if s else ""
        v = View3D(self, r, title, s.modality if s else "", mode, window, src_uid=uid,
                   study_uid=s.study_uid if s else self.study_uid, source_path=vol.source_path)
        src.mpr_plane = None
        v.attach(src, self.study_infos.get(s.study_uid, self.study_info) if s else self.study_info)
        self._activate(src)
        self.update_render3d_bar()
        self._update_mpr_bar()
        self.status_message.emit(
            "3D no quadro: esquerdo gira, roda aproxima, clique leva os cortes ao ponto.")
        return v

    # ------------------------------------------------------------ reconstrução da etapa como 3D (0.93)
    def registrar_recon(self, vp: Viewport, uid: str, frames: list | None, chave: str | None) -> None:
        """O protocolo montou uma reconstrução neste quadro: guarda de onde ela veio, para a barra do
        3D poder transformá-la num volume 3D."""
        if not hasattr(self, "_recon_etapa"):
            self._recon_etapa = {}
        self._recon_etapa[id(vp)] = {"series_uid": vp.series_uid, "uid": uid, "frames": frames, "chave": chave}

    def recon_da_etapa(self, vp: Viewport | None) -> dict | None:
        """{modo, cmap, texto, …} se o quadro mostra uma reconstrução que o protocolo montou."""
        reg = getattr(self, "_recon_etapa", {}).get(id(vp)) if vp is not None else None
        pl = getattr(vp, "mpr_plane", None)
        if reg is None or pl is None or not isinstance(pl, MPRPlane) or reg["series_uid"] != vp.series_uid:
            return None
        mm = float(pl.slab_mm or 0)
        modo = pl.mode if mm > 0 else "mip"
        texto = (f"Corte {pl.name}, {SLAB_MODES[pl.mode]} {mm:.0f} mm — mexa na barra e o quadro vira 3D"
                 if mm > 0 else f"Corte {pl.name} — mexa na barra e o quadro vira 3D")
        return dict(reg, modo=modo, cmap=vp.state.cmap, texto=texto)

    def recon_para_3d(self, vp: Viewport):
        """Transforma a reconstrução da etapa num 3D, como o botão 3D: mesmo volume (a fase da
        dinâmica, se for o caso), a espessura vira a caixa do corte e a câmera olha do mesmo lado
        de onde o corte era visto."""
        from ipe.ui.viewer.render3d_view import VISTAS
        rec = self.recon_da_etapa(vp)
        if rec is None:
            return None
        pl = vp.mpr_plane
        mm = float(pl.slab_mm or 0)
        centro = np.asarray(pl.position(vp.index), float)
        tela = vp.display_orientation()
        cmap, rotulo, janela_feita = vp.state.cmap, vp.series_label, vp.state.window_set
        v = self.abrir_3d_no_quadro(vp, rec["uid"], rec["modo"], frames=rec["frames"], chave=rec["chave"])
        if v is None:
            self.status_message.emit("Não deu para montar o 3D desta reconstrução: memória ou volume.")
            return None
        n = np.asarray(pl.normal, float)
        eixo = int(np.argmax(np.abs(n)))
        if mm > 0:
            # a caixa do corte no eixo da espessura: do começo ao fim da fatia
            un = np.zeros(3)
            un[eixo] = 1.0
            menor, maior = centro - un * mm / 2, centro + un * mm / 2
            lado_min, lado_max = {0: ("left", "right"), 1: ("posterior", "anterior"), 2: ("head", "feet")}[eixo]
            v.r.cut_at(menor, lado_min)
            v.r.cut_at(maior, lado_max)
        if tela is not None:
            from ipe.imaging.render3d import rotation
            t = np.asarray(tela, float)

            def nota(az, el):
                u, w, _d = rotation(az, el)
                return float(np.dot(u, t[:3]) + np.dot(w, t[3:]))
            _n, az, el = max(VISTAS, key=lambda x: nota(x[1], x[2]))
            v.az, v.el = az, el
        if cmap and v.mode not in ("vr", "surf"):
            vp.set_colormap(cmap)
        if v.mode == "mip" and not janela_feita:
            from ipe.ui.viewer.etapas import _janela_do_mip
            _janela_do_mip(v)
        v.title = rotulo
        vp.series_label = rotulo.replace("MPR ", "3D ")
        v.refresh(fast=False)
        return v

    def close_3d(self, vp: Viewport | None = None) -> None:
        """Desfaz o 3D do quadro e volta a mostrar a série de cortes."""
        vp = vp or self.active
        v = getattr(vp, "render3d", None)
        if vp is None or v is None:
            return
        uid = v.src_uid
        v.cine(False)
        vp.render3d = None
        if uid:
            self.load_series_into(vp, uid)
        else:
            vp.clear()
        self.update_render3d_bar()

    def update_render3d_bar(self) -> None:
        if getattr(self, "render3d_bar", None) is not None:
            self.render3d_bar.sync()

    def cursor_from_3d(self, origem: Viewport, ponto: np.ndarray) -> None:
        """Clique no 3D: leva o cursor e os cortes dos outros quadros até o ponto."""
        for w in self._shown():
            if w is origem or not w.frames:
                continue
            if getattr(w, "render3d", None) is not None:
                w.cursor_point = ponto
                w.update()
                continue
            w.cursor_point = ponto
            w.go_to_point(ponto)
            w.update()
        self.update_reference_lines()

    def _plane_back(self) -> None:
        vp = self.active
        uid = self._source_series(vp)
        if vp is None or vp.mpr_plane is None or uid is None:
            return
        self.load_series_into(vp, uid)
        self._update_mpr_bar()

    def _update_mpr_bar(self) -> None:
        if not hasattr(self, "mpr_bar"):
            return
        self.mpr_bar.setVisible(self.mpr_active or any(
            v.mpr_plane is not None and getattr(v.mpr_plane, "supports_slab", True) for v in self._shown()))

    def _enter_mpr(self) -> bool:
        src = self.active
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "MPR", "Selecione um quadro com uma série (TC, RM, PET…).")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        planes = [MPRPlane(vol, ax) for ax in (0, 1, 2)]
        order = {"Axial": 0, "Coronal": 1, "Sagital": 2}
        if len({p.name for p in planes}) == 3:
            planes.sort(key=lambda p: order[p.name])
        # guarda o estado para voltar
        self._mpr_saved = (self._layout, [(v.series_uid, v.index) for v in self.viewports])
        width, level, cmap = src.state.width, src.state.level, src.state.cmap
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        for_uid = src.for_uid
        center = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        center = src.pixel_to_patient(*[x / 2 for x in src._img.pixels.shape[:2][::-1]]) \
            if src._img is not None else center
        # só desfaz os grupos: desligar a sincronização aqui gravaria a automática da modalidade desligada
        self.hub.unlink(self.viewports)
        self.set_layout(1, 3)
        for vp, plane in zip(self.viewports[:3], planes):
            vp.mpr_plane = plane
            vp.for_uid = for_uid
            vp.study_uid = study_uid
            vp.modality = s.modality if s else ""
            vp.key_frames = self.key_set
            vp.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"MPR {plane.name}",
                          self.study_infos.get(study_uid, self.study_info),
                          start_index=plane.index_for_point(center))
            vp.set_window(width, level, emit=False)
            vp.state.cmap = cmap
            vp.cursor_point = center
            vp.anonymize = self.anonymize
        self.mpr_active = True
        # Os três planos do MPR andam juntos sozinhos (sync._sempre_juntos): ligar aqui a automática
        # gravava a escolha para a modalidade inteira — abrir um MPR religava a RM toda (0.99.9).
        self.refs_action.setChecked(True)
        self.set_left_tool("cross")
        self.mpr_bar.setVisible(True)
        self._activate(self.viewports[0])
        self._sync_slab_controls(self.viewports[0])
        self.mpr_info.setText(f"   volume {vol.shape[2]}×{vol.shape[1]}×{vol.shape[0]}, "
                              f"{vol.nbytes_mb:.0f} MB" + ("   ⚠ " + " ".join(vol.warnings) if vol.warnings else ""))
        self.update_reference_lines()
        return True

    def _exit_mpr(self) -> None:
        self.mpr_active = False
        saved = self._mpr_saved
        self._mpr_saved = None
        for v in self.viewports:
            v.mpr_plane = None
            v.cursor_point = None
        if saved:
            layout, contents = saved
            for vp, (uid, idx) in zip(self.viewports, contents):
                if uid and not uid.startswith("mpr:"):
                    self.load_series_into(vp, uid)
                    vp.set_index_silently(idx)
                else:
                    vp.clear()
            self.set_layout(*layout)
        self.set_left_tool("wl")
        self._update_mpr_bar()
        self.update_reference_lines()

    def _sync_slab_controls(self, vp: Viewport) -> None:
        pl = vp.mpr_plane
        if pl is None:
            return
        for combo, value in ((self.slab_combo, pl.slab_mm), (self.mode_combo, pl.mode)):
            combo.blockSignals(True)
            i = combo.findData(value)
            if i < 0 and combo is self.slab_combo and value:
                # espessura fora da lista (a da etapa: 62 mm, 165 mm): entra na lista, para a barra
                # dizer o que está na tela em vez de "fino"
                combo.addItem(f"{float(value):.0f} mm", value)
                i = combo.count() - 1
            if i >= 0:
                combo.setCurrentIndex(i)
            combo.blockSignals(False)

    def _apply_slab(self) -> None:
        mm = float(self.slab_combo.currentData())
        mode = self.mode_combo.currentData()
        targets = [v for v in self._shown() if v.mpr_plane is not None] if self.slab_all.isChecked() \
            else [self.active] if self.active is not None and self.active.mpr_plane is not None else []
        targets = [v for v in targets if getattr(v.mpr_plane, "supports_slab", True)]
        for v in targets:
            v.mpr_plane.set_slab(mm, mode)
            suffix = f"  {SLAB_MODES[mode]} {mm:.0f} mm" if mm else ""
            v.series_label = f"MPR {v.mpr_plane.name}{suffix}"
            v._qimage_key = None
            v._load_current()
            v.update()
