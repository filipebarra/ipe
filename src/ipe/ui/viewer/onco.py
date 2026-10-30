"""Funções do visualizador para oncologia e IA (mixin do ViewerTab):

- acompanhamento de lesões (painel, ligar medidas, ir à imagem, layout das lesões);
- laudo (janela do laudo do exame);
- objetos de CAD/IA e anotações (SR, SEG, RTSTRUCT, GSPS) desenhados sobre as imagens;
- segmentação 3D (crescimento de região): volume, SUV, TMTV e TLG; salvar como DICOM SEG.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMessageBox, QProgressDialog, QPushButton, QSlider, QVBoxLayout,
)

from ipe.imaging import overlays as O
from ipe import MARCAS_NOSSAS

log = logging.getLogger(__name__)
SEG_COLORS = [(90, 220, 255), (255, 120, 90), (140, 255, 120), (255, 210, 70), (220, 130, 255)]


class OncoMixin:
    # ================================================================ lesões
    def _lesion_panel(self, create: bool = True):
        if getattr(self, "lesion_panel", None) is None and create:
            from ipe.ui.viewer.lesion_panel import LesionPanel
            self.lesion_panel = LesionPanel(self)
            self.lesion_panel.hide()
            self._body.addWidget(self.lesion_panel)
        return getattr(self, "lesion_panel", None)

    def toggle_lesion_panel(self, on: bool) -> None:
        panel = self._lesion_panel(create=on)
        if panel is not None:
            panel.setVisible(on)
            if on:
                panel.refresh()

    def refresh_lesions(self) -> None:
        panel = self._lesion_panel(create=False)
        if panel is not None and panel.isVisible():
            QTimer.singleShot(0, panel.refresh)

    def choose_lesion_for(self, vp, ann) -> None:
        """Menu para ligar a medida a uma lesão (ou criar uma nova)."""
        from ipe.ui.viewer.lesion_panel import patient_key
        pid = patient_key(self.study_infos.get(vp.study_uid) or self.study_info)
        if not pid:
            QMessageBox.information(self, "Lesões", "O exame não tem identificação do paciente.")
            return
        lesions = self.repo.lesions(pid)
        cur = (ann.meta or {}).get("lesion")
        m = QMenu(self)
        m.setStyleSheet(self.MENU_STYLE)
        for le in lesions:
            a = QAction(f"{le['name']}  ({le.get('location', '')})", m, checkable=True, checked=(le["id"] == cur))
            a.triggered.connect(lambda _=False, L=le: self._link(vp, ann, L["id"], L["name"]))
            m.addAction(a)
        if lesions:
            m.addSeparator()
        a_new = m.addAction("Nova lesão…")
        a_new.triggered.connect(lambda: self._link_new(vp, ann))
        if cur is not None:
            a_off = m.addAction("Desligar da lesão")
            a_off.triggered.connect(lambda: self._link(vp, ann, None, ""))
        m.exec(QCursor.pos())

    def _link(self, vp, ann, lesion_id, name: str) -> None:
        vp.link_lesion(ann, lesion_id, name)
        panel = self._lesion_panel(create=False)
        if panel is None or not panel.isVisible():
            self.lesions_action.setChecked(True)
        else:
            panel.refresh()
        self.status_message.emit(f"Medida ligada a “{name}”." if lesion_id else "Medida desligada da lesão.")

    def _link_new(self, vp, ann) -> None:
        panel = self._lesion_panel()
        lid = panel.new_lesion()
        if lid is not None:
            le = next((x for x in self.repo.lesions(panel.pid) if x["id"] == lid), {"name": "Lesão"})
            self._link(vp, ann, lid, le["name"])

    def go_to_image(self, study_uid: str, series_uid: str, sop: str, frame: int) -> bool:
        if study_uid not in self.study_order:
            self.add_study_silent(study_uid)
        vp = self.active or (self.viewports[0] if self.viewports else None)
        if vp is None:
            return False
        if vp.series_uid != series_uid or vp.mpr_plane is not None:
            self.load_series_into(vp, series_uid)
        for i, f in enumerate(vp.frames):
            if f.sop_uid == sop and f.frame_index == frame:
                vp.go_to(i)
                return True
        return False

    def lesion_layout(self, study_uid: str | None = None) -> None:
        """Um quadro por lesão, na imagem medida (exame atual; se a lesão não foi medida nele, o último)."""
        panel = self._lesion_panel()
        panel.load()
        study_uid = study_uid or self.study_uid
        order = [u for u, _d in panel.studies]
        items = []
        for le in panel.lesions:
            ref = None
            cands = [study_uid] + list(reversed(order))
            for su in cands:
                c = panel.cells.get((le["id"], su))
                if c is not None and c.refs:
                    ref = (su, c.refs[0])
                    break
            if ref is not None:
                items.append((le, ref))
        if not items:
            QMessageBox.information(self, "Lesões", "Nenhuma lesão com medida ligada.")
            return
        items = items[:16]
        self.set_layout(*self._layout_for(len(items)))
        for vp, (le, (su, (series_uid, sop, frame, _aid))) in zip(self.viewports, items):
            if su not in self.study_order:
                self.add_study_silent(su)
            self.load_series_into(vp, series_uid)
            for i, f in enumerate(vp.frames):
                if f.sop_uid == sop and f.frame_index == frame:
                    vp.go_to(i)
                    break
            vp.lesion_names = {x["id"]: x["name"] for x in panel.lesions}
        self.status_message.emit(f"{len(items)} lesão(ões) no layout. Filme ▸ “Enviar todos os quadros” monta a folha.")

    # ================================================================ laudo
    def open_report(self, study_uid: str | None = None) -> None:
        from ipe.auth import session as auth
        from ipe.ui.report_window import ReportWindow
        study = study_uid or (self.active.study_uid if self.active is not None and self.active.study_uid
                              else self.study_uid)
        w = getattr(self, "_report_windows", {}).get(study)
        if w is not None and w.isVisible():
            w.raise_()
            w.activateWindow()
            return
        if not auth.can("report") and not self.repo.reports(study):
            auth.require("report", self, "escrever laudos")
            return
        w = ReportWindow(self.repo, study, self.settings, self, self)
        w.saved.connect(lambda _u: self.status_message.emit("Laudo salvo."))
        self._report_windows = getattr(self, "_report_windows", {})
        self._report_windows[study] = w
        w.show()

    def append_to_report(self, text: str, study_uid: str | None = None) -> bool:
        """Acrescenta um texto ao laudo aberto (abre a janela se preciso). False se não deu."""
        if not (text or "").strip():
            return False
        study = study_uid or (self.active.study_uid if self.active is not None and self.active.study_uid
                              else self.study_uid)
        self.open_report(study)
        w = getattr(self, "_report_windows", {}).get(study)
        editor = getattr(w, "editor", None)
        if editor is None or editor.isReadOnly():
            return False
        from PySide6.QtGui import QTextCursor
        editor.moveCursor(QTextCursor.End)
        editor.insertPlainText(("\n" if editor.toPlainText().strip() else "") + text.rstrip() + "\n")
        w.raise_()
        return True

    # ================================================================ CAD / IA
    def load_overlay_objects(self) -> int:
        """Lê SR/SEG/RTSTRUCT/GSPS dos estudos da aba (os que ainda não foram lidos)."""
        done = getattr(self, "_overlay_studies", set())
        self._overlay_studies = done
        added = 0
        for study in list(self.study_order):
            if study in done:
                continue
            done.add(study)
            try:
                rows = self.repo.series_for_study(study)
            except Exception:  # noqa: BLE001
                continue
            for s in rows:
                if (s.modality or "").upper() not in O.OVERLAY_MODALITIES:
                    continue
                if s.description == "Níveis da coluna (conferência) · TotalSegmentator":
                    continue                    # a segunda sagital só serve às medidas (0.99.5)
                for inst in self.repo.instances_for_series(s.series_uid)[:50]:
                    if s.description == "Níveis da coluna · TotalSegmentator":
                        # 0.99.2: a coluna volta como volumes com nome — o rótulo em qualquer série e plano
                        from ipe.ai import coluna as COL
                        try:
                            obj = COL.objeto_do_seg(inst["path"], study)
                            COL.anexar_medidas(obj, tuple(COL.conferencias_do_exame(self.repo, study)))
                        except Exception:  # noqa: BLE001
                            log.exception("níveis da coluna")
                            continue
                        self.overlay_objects.append(obj)
                        added += 1
                        continue
                    obj = O.load_object(inst["path"])
                    if obj is None:
                        continue
                    obj.study_uid = obj.study_uid or study
                    if obj.source == "SR" and any(m in (s.description or "") for m in MARCAS_NOSSAS):
                        obj.enabled = False
                    if obj.source in O.tipos_ocultos(self.settings):
                        obj.enabled = False      # escolha do exame anterior: nasce oculto
                    for parte in O.por_segmento(obj):    # SEG de órgãos: um item por órgão (0.98)
                        self.overlay_objects.append(parte)
                        added += 1
        self.carregar_segmentacoes()
        if added:
            self._apply_overlays()
            n = sum(1 for o in self.overlay_objects if o.enabled)
            self.status_message.emit(f"{added} objeto(s) de CAD/IA/anotações encontrados ({n} visíveis) — botão CAD/IA.")
            if n < added:
                self.status_message.emit(
                    f"Ocultos por escolha anterior: {added - n} — botão CAD/IA para mostrar.")
        self._update_overlay_button()
        return added

    def _apply_overlays(self) -> None:
        for vp in self.viewports:
            vp.overlays = self.overlay_objects
            vp.update()
        self._update_overlay_button()

    def _update_overlay_button(self) -> None:
        a = getattr(self, "overlay_action", None)
        if a is None:
            return
        n = len(self.overlay_objects)
        a.setIconText(f"CAD/IA ({n})" if n else "CAD/IA")

    def toggle_overlays(self) -> None:
        """Clique no botão CAD/IA: oculta todos se algum estiver visível; senão mostra todos.

        A escolha fica guardada por tipo (SEG, GSPS, SR…): quem desligou a segmentação da IA
        num exame não quer vê-la no exame seguinte, e não deveria ter de desligar de novo.
        """
        objs = self.overlay_objects
        if not objs:
            self.overlay_menu.exec(QCursor.pos())
            return
        on = not any(o.enabled for o in objs)
        for o in objs:
            o.enabled = on
        self.lembrar_tipos({o.source for o in objs}, on)
        self._apply_overlays()
        self.status_message.emit("CAD/IA visível." if on else "CAD/IA oculto (também nos próximos exames).")

    def lembrar_tipos(self, tipos, visivel: bool) -> None:
        """Guarda, por tipo de objeto, se ele nasce visível nos próximos exames."""
        ocultos = O.tipos_ocultos(self.settings)
        ocultos = (ocultos - set(tipos)) if visivel else (ocultos | set(tipos))
        O.guardar_tipos_ocultos(self.settings, ocultos)

    def mostrar_tipo(self, tipo: str, on: bool) -> None:
        """Liga/desliga todos os objetos de um tipo neste exame e nos próximos."""
        for o in self.overlay_objects:
            if o.source == tipo:
                o.enabled = on
        self.lembrar_tipos({tipo}, on)
        self._apply_overlays()

    def set_overlay_enabled(self, obj, on: bool) -> None:
        obj.enabled = on
        self._apply_overlays()

    def _fill_overlay_menu(self, m: QMenu) -> None:
        m.clear()
        objs = self.overlay_objects
        if not objs:
            a = m.addAction("Nenhum objeto de CAD/IA, SEG, RTSTRUCT ou GSPS neste exame")
            a.setEnabled(False)
        for o in objs:
            a = QAction(o.title, m, checkable=True, checked=o.enabled)
            a.toggled.connect(lambda on, oo=o: self.set_overlay_enabled(oo, on))
            m.addAction(a)
            refs = self._overlay_refs(o)
            if refs:
                sub = m.addMenu(f"   Ir para ({len(refs)} imagem(ns))")
                for k, (series_uid, sop, fr, lab) in enumerate(refs[:30]):
                    b = sub.addAction(f"{k + 1}. {lab}" if lab else f"Imagem {k + 1}")
                    b.triggered.connect(lambda _=False, su=series_uid, s=sop, f=fr, oo=o:
                                        self.go_to_image(oo.study_uid or self.study_uid, su, s, max(0, f)))
        tipos = []
        for o in objs:
            if o.source not in tipos:
                tipos.append(o.source)
        if len(tipos) > 1 or (tipos and len(objs) > 1):
            m.addSeparator()
            cab = m.addAction("Por tipo (a escolha vale para os próximos exames):")
            cab.setEnabled(False)
            for t in tipos:
                vis = any(o.enabled for o in objs if o.source == t)
                a = QAction(O.TIPOS.get(t, t), m, checkable=True, checked=vis)
                a.toggled.connect(lambda on, tt=t: self.mostrar_tipo(tt, on))
                m.addAction(a)
        m.addSeparator()
        on = m.addAction("Mostrar todos")
        on.triggered.connect(lambda: self.mostrar_todos(True))
        off = m.addAction("Ocultar todos")
        off.triggered.connect(lambda: self.mostrar_todos(False))
        m.addSeparator()
        rl = m.addAction("Ler de novo os objetos do exame")
        rl.triggered.connect(self._reload_overlays)
        m.addSeparator()
        m.addAction(self.tool_actions["grow"])
        pet = m.addAction("Resumo das segmentações (TMTV / TLG)…")
        pet.triggered.connect(self.show_tmtv)

    def mostrar_todos(self, on: bool) -> None:
        for o in self.overlay_objects:
            o.enabled = on
        self.lembrar_tipos({o.source for o in self.overlay_objects}, on)
        self._apply_overlays()

    def _reload_overlays(self) -> None:
        # a máscara da densidade foi feita aqui, como a segmentação: reler o exame não a apaga
        self.overlay_objects[:] = [o for o in self.overlay_objects
                                   if o.source in ("Segmentação", "Densidade")]
        self._overlay_studies = set()
        self.load_overlay_objects()
        self._apply_overlays()

    def _overlay_refs(self, o) -> list:
        """Imagens referenciadas pelo objeto: (série, SOP, quadro, rótulo)."""
        sops = {}
        for (sop, fr), gs in o.by_frame.items():
            sops.setdefault((sop, fr), gs[0].text if gs else "")
        for mf in o.masks:
            if mf.ref is not None:
                sops.setdefault(mf.ref, mf.label)
        if not sops:
            return []
        out = []
        with_series = self._series_of_sops([s for s, _f in sops])
        for (sop, fr), lab in sops.items():
            su = with_series.get(sop)
            if su:
                out.append((su, sop, fr, lab))
        return out

    def _series_of_sops(self, sops: list[str]) -> dict[str, str]:
        out = {}
        want = set(sops)
        for s in self.series:
            if not want:
                break
            for inst in self.repo.instances_for_series(s.series_uid):
                if inst["sop_uid"] in want:
                    out[inst["sop_uid"]] = s.series_uid
                    want.discard(inst["sop_uid"])
        return out

    # ================================================================ segmentação 3D
    def segment_at(self, vp, u: float, v: float) -> None:
        # Marcando o mamilo: o próximo clique é o ponto, não uma lesão nova. O médico já está com
        # a ferramenta Segmentar na mão — pedir outra ferramenta só para um clique seria pior.
        pedido = getattr(self, "_mamilo_pendente", None)
        if pedido is not None:
            self._mamilo_pendente = None
            if pedido.isVisible():
                pedido.mamilo_clicado(vp, u, v)
                return
        cad = None
        sessao = getattr(self, "dyn", None)
        if sessao is not None and (sessao.is_dyn(vp) or (hasattr(self, "_dyn_do_quadro")
                                                         and self._dyn_do_quadro(vp) is not None)):
            # Dinâmica de mama: a lesão cresce sobre o **realce**, não sobre o sinal bruto — no
            # sinal bruto a gordura é tão clara quanto a lesão, e a região vaza pela mama inteira.
            vol, cad = self._volumes_cad(sessao)
            if vol is None:
                return
        elif vp.mpr_plane is not None or not vp.frames or vp.frames[0].is_virtual:
            QMessageBox.information(self, "Segmentar", "Use a série original (não a reconstrução) para segmentar.")
            return
        else:
            uid = self._source_series(vp)
            if uid is None:
                self._seg_sem_resultado("Este quadro não tem série original para crescer a região "
                                        "(agrupamento, imagens-chave ou mamografia).")
                return
            vol = self._volume_for(vp, uid)
            if vol is None:
                self._seg_sem_resultado("O volume 3D desta série não foi montado.")
                return
        p = vp.pixel_to_patient(u - 0.5, v - 0.5)
        if p is None:
            self._seg_sem_resultado("O ponto clicado não tem posição no paciente: clique dentro da imagem.")
            return
        i, j, k = (int(round(x)) for x in vol.patient_to_voxel(p))
        nz, ny, nx = vol.data.shape
        if not (0 <= k < nz and 0 <= j < ny and 0 <= i < nx):
            self._seg_sem_resultado("O ponto clicado caiu fora do volume montado.")
            return
        dlg = SegmentDialog(self, vp, vol, (k, j, i), (u, v), vp.frame_key(), cad=cad)
        self._seg_dialogs = [d for d in getattr(self, "_seg_dialogs", []) if d.isVisible()] + [dlg]
        dlg.show()

    def editar_segmentacao(self, vp, ann):
        """Reabre a janela de uma lesão já guardada (pedido dele: acessar pelo painel de medidas
        e editar). Volta com o método, o limiar, o raio e o mamilo que valiam; "Guardar" atualiza
        a mesma medida. `vp` é o quadro em que a medida está aberta."""
        m = ann.meta or {}
        cad = None
        if str(m.get("method", "")).startswith("realce"):
            sessao = getattr(self, "dyn", None)
            if sessao is None or getattr(sessao, "maps", None) is None:
                # Ele bateu nessa parede quatro vezes no primeiro dia (log de 10/10): em vez de
                # mandar abrir e voltar, oferecer abrir já, com as fases desta lesão escolhidas.
                if not self.perguntar_abrir_dinamica():
                    return None
                from ipe.ui.viewer import dinamica_config as DC
                prev = DC.parametros_iniciais(self.settings) if self.settings is not None else {}
                if m.get("dyn_uids"):
                    prev["uids"] = list(m["dyn_uids"])
                if not self.open_dynamic(previous=prev or None):
                    return None
                sessao = getattr(self, "dyn", None)
                if sessao is None:
                    return None
            vol, cad = self._volumes_cad(sessao)
            if vol is None:
                return None
        else:
            uid = self._source_series(vp)
            vol = self._volume_for(vp, uid) if uid else None
            if vol is None:
                self._seg_sem_resultado("Não consegui montar o volume da série desta medida.")
                return None
        if m.get("semente_mm") is not None:
            p = np.asarray(m["semente_mm"], float)
        else:
            # lesão guardada antes da 0.67: a semente é o ponto do clique, na imagem da medida
            u, v = ann.points[0] if ann.points else (0.0, 0.0)
            p = vp.pixel_to_patient(u - 0.5, v - 0.5)
            if p is None:
                self._seg_sem_resultado("Não achei onde foi o clique desta lesão. Segmente de novo.")
                return None
        i, j, k = (int(round(x)) for x in vol.patient_to_voxel(p))
        nz, ny, nx = vol.data.shape
        if not (0 <= k < nz and 0 <= j < ny and 0 <= i < nx):
            self._seg_sem_resultado("A semente desta lesão caiu fora do volume montado.")
            return None
        uv = tuple(ann.points[0]) if ann.points else (0.0, 0.0)
        dlg = SegmentDialog(self, vp, vol, (k, j, i), uv, ann.frame_key, cad=cad, existente=ann)
        self._seg_dialogs = [d for d in getattr(self, "_seg_dialogs", []) if d.isVisible()] + [dlg]
        dlg.show()
        return dlg

    def perguntar_abrir_dinamica(self) -> bool:
        return QMessageBox.question(
            self, "Editar lesão", "Esta lesão foi medida sobre a dinâmica, e a dinâmica não está "
            "aberta nesta aba.\n\nAbrir a dinâmica agora?") == QMessageBox.Yes

    # ---------------------------------------------------------------- segmentações guardadas
    def carregar_segmentacoes(self) -> int:
        """Desenha as lesões guardadas como elas foram segmentadas, em todas as séries.

        Pedido dele (10/10): *"quando estou salvando a segmentação, ela está 'sumindo' e um
        círculo pequeno fica no lugar"*. A máscara só existia na janela aberta; o que ia para o
        banco era o ponto do clique. Desde a 0.68 a máscara vai junto, na medida (`mascara3d`),
        e volta a cada abertura do exame. Medida apagada leva a máscara junto."""
        import json
        ocultos = O.tipos_ocultos(getattr(self, "settings", None))
        existentes = {o.key for o in self.overlay_objects}
        em_janela = {getattr(getattr(o, "ann", None), "db_id", None) for o in self.overlay_objects}
        em_edicao = set(getattr(self, "_segs_em_edicao", set()))
        vivos, novos = set(), 0
        try:
            recs = self.repo.annotations_for_studies(list(self.study_order))
        except Exception:  # noqa: BLE001
            log.exception("segmentações guardadas")
            return 0
        for r in recs:
            if r.get("kind") != "seg":
                continue
            try:
                d = json.loads(r.get("data") or "{}")
            except ValueError:
                continue
            meta = d.get("meta") or {}
            if not meta.get("mascara3d"):
                continue
            chave = f"segann:{r['id']}"
            vivos.add(chave)
            if chave in existentes or r["id"] in em_janela or r["id"] in em_edicao:
                continue
            cor = tuple(meta.get("cor") or SEG_COLORS[0])
            nome = d.get("text") or "Segmentação"
            try:
                mv = O.MaskVolume.da_meta(meta["mascara3d"], cor, nome)
            except Exception:  # noqa: BLE001
                log.exception("máscara guardada da lesão %s", r["id"])
                continue
            obj = O.OverlayObject(chave, "Segmentação", nome, cor, study_uid=r.get("study_uid") or "")
            obj.volumes = [mv]
            obj.stats = {k: v for k, v in meta.items() if k != "mascara3d"}
            obj.enabled = "Segmentação" not in ocultos
            self.overlay_objects.append(obj)
            novos += 1
        antes = len(self.overlay_objects)
        self.overlay_objects[:] = [o for o in self.overlay_objects
                                   if not o.key.startswith("segann:") or o.key in vivos]
        if novos or len(self.overlay_objects) != antes:
            self._apply_overlays()
        return novos

    def _seg_sem_resultado(self, motivo: str) -> None:
        """Nenhum retorno mudo: se o clique não virou segmentação, a tela diz por quê."""
        log.warning("segmentar: %s", motivo)
        QMessageBox.information(self, "Segmentar", motivo)

    def _volumes_cad(self, sessao):
        """Volume do realce e das classes da dinâmica, montados uma vez só (com barra)."""
        from ipe.imaging.volume import VolumeError
        if getattr(sessao, "_cad", None) is not None:
            r, c = sessao.volumes_cad()
            return r, (r, c)
        dlg = QProgressDialog("Montando os mapas em 3D para medir a lesão…", "Cancelar", 0,
                              sessao.maps.n * 2, self)
        dlg.setWindowTitle("Dinâmica")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        feitos = [0]

        def progresso(_d, _t):
            feitos[0] += 1
            dlg.setValue(feitos[0])
            QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            realce, classes = sessao.volumes_cad(progresso)
        except VolumeError as e:
            dlg.close()
            QMessageBox.information(self, "Medir lesão", str(e))
            return None, None
        except Exception as e:  # noqa: BLE001
            dlg.close()
            log.exception("volumes do CAD")
            QMessageBox.warning(self, "Medir lesão", f"Não foi possível montar os mapas:\n{e}")
            return None, None
        dlg.close()
        return realce, (realce, classes)

    def referencias_da_mama(self, sessao):
        """Pele, mamilo e parede torácica do exame (monta uma vez, com barra e cancelar)."""
        from ipe.imaging.volume import VolumeError
        maps = getattr(sessao, "maps", None)
        if maps is None:
            return None
        if getattr(maps, "_refs_mama", None) is not None:
            return maps._refs_mama
        dlg = QProgressDialog("Procurando o mamilo pela superfície da pele…", "Cancelar", 0,
                              maps.n + 2, self)
        dlg.setWindowTitle("Distância ao mamilo")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)

        def progresso(feito, total):
            dlg.setMaximum(int(total))
            dlg.setValue(int(feito))
            QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            refs = maps.referencias_da_mama(progresso)
        except VolumeError as e:
            dlg.close()
            QMessageBox.information(self, "Distância ao mamilo", str(e))
            return None
        except Exception as e:  # noqa: BLE001
            dlg.close()
            log.exception("referências da mama")
            QMessageBox.warning(self, "Distância ao mamilo", f"Não foi possível medir:\n{e}")
            return None
        dlg.close()
        return refs

    def mamilos_marcados(self, sessao, vol):
        """Os mamilos que ele marcou neste exame (um por mama), guardados na sessão da dinâmica.

        Na primeira vez vêm das lesões já guardadas com mamilo marcado: reabrir o exame não pede
        para marcar de novo.
        """
        from ipe.imaging import mama_distancias as MD
        maps = getattr(sessao, "maps", None)
        dono = maps if maps is not None else sessao
        marcados = getattr(dono, "_mamilos_marcados", None)
        if marcados is None:
            marcados = MD.marcados_do_volume(MD.afim_do_objeto(vol), vol.shape)
            for meta in self.seg_metas():
                if meta.get("mamilo_marcado") and meta.get("mamilo_mm"):
                    marcados.marcar(meta["mamilo_mm"])
            try:
                dono._mamilos_marcados = marcados
            except AttributeError:
                pass
        return marcados

    def seg_metas(self, study_uid: str | None = None) -> list[dict]:
        import json
        study_uid = study_uid or self.study_uid
        out = []
        for r in self.repo.annotations_for_studies([study_uid]):
            if r.get("kind") == "seg":
                try:
                    out.append(json.loads(r.get("data") or "{}").get("meta") or {})
                except ValueError:
                    pass
        return out

    def show_tmtv(self) -> None:
        from ipe.imaging.segment import tmtv
        study = self.active.study_uid if self.active is not None and self.active.study_uid else self.study_uid
        metas = self.seg_metas(study)
        if not metas:
            QMessageBox.information(self, "Segmentações", "Nenhuma segmentação guardada neste exame.\n"
                                    "Use a ferramenta Segmentar 3D e clique em “Guardar”.")
            return
        ml, tlg = tmtv(metas)
        lines = [f"• {m.get('lesion_name') or 'Segmentação'}: {float(m.get('ml') or 0):.2f} mL"
                 + (f", SUVmáx {m['suvmax']:.2f}, TLG {float(m.get('tlg') or 0):.1f}" if m.get("suvmax") is not None
                    else "") for m in metas]
        txt = "\n".join(lines)
        if ml:
            txt += f"\n\nTMTV (volume tumoral metabólico total): {ml:.1f} mL\nTLG total: {tlg:.1f}"
        QMessageBox.information(self, "Segmentações do exame", txt)


class SegmentDialog(QDialog):
    """Resultado da segmentação 3D, com ajuste do limiar e as ações (guardar, lesão, DICOM SEG)."""

    def __init__(self, tab, vp, vol, seed, click_uv, frame_key, cad=None, existente=None):
        super().__init__(tab)
        # `cad`: (volume do realce, volume das classes) quando a lesão é medida sobre a dinâmica.
        self.cad = cad
        self.medidas = None
        self.setWindowTitle("Lesão na dinâmica (CAD)" if cad else "Segmentação 3D")
        self.tab, self.vp, self.vol, self.seed, self.uv, self.frame_key = tab, vp, vol, seed, click_uv, frame_key
        self.modality = (vp.modality or "").upper()
        self.suv = vp.suv_factor
        n = len([o for o in tab.overlay_objects if o.source == "Segmentação"])
        self.color = SEG_COLORS[n % len(SEG_COLORS)]
        self.obj = O.OverlayObject(f"seg-{id(self)}", "Segmentação", f"Segmentação {n + 1}", self.color)
        tab.overlay_objects.append(self.obj)
        from ipe.imaging.segment import METHODS
        self.method = QComboBox()
        for k, lab in METHODS.items():
            if k.startswith("pet") and self.modality != "PT":
                continue
            if k.startswith("realce") != bool(cad):   # realce só na dinâmica, e lá só ele
                continue
            self.method.addItem(lab, k)
        default = "realce_pct" if cad else (
            str(tab.settings.get("segment.pet_method", "pet_pct")) if self.modality == "PT" else "range")
        self.method.setCurrentIndex(max(0, self.method.findData(default)))
        self.lo = QDoubleSpinBox(decimals=2, minimum=-1e6, maximum=1e7)
        self.hi = QDoubleSpinBox(decimals=2, minimum=-1e6, maximum=1e7)
        # 41% é a convenção do PET (SUVmáx); no realce da RM o padrão é outro e tem chave própria,
        # senão um mexe no outro sem ninguém pedir.
        pct0 = float(tab.settings.get("segment.realce_pct", 50)) if cad \
            else float(tab.settings.get("segment.pet_pct", 41))
        self.pct = QDoubleSpinBox(decimals=0, minimum=5, maximum=95, value=pct0)
        self.pct.setSuffix(" %")
        self.abs = QDoubleSpinBox(decimals=2, minimum=0.1, maximum=100, value=float(tab.settings.get("segment.pet_abs", 2.5)))
        self.radius = QDoubleSpinBox(decimals=0, minimum=10, maximum=400, value=60 if cad else 120)
        self.radius.setSuffix(" mm")
        self.limiar = QDoubleSpinBox(decimals=0, minimum=5, maximum=1000, suffix=" %",
                                     value=float(getattr(getattr(tab, "dyn", None), "maps", None)
                                                 and tab.dyn.maps.threshold_pct or 50.0))
        self.limiar.setToolTip("Realce no pico mínimo para o voxel entrar na lesão. É por aqui que se "
                               "aperta ou solta a região, como no CADstream.")
        self.name = QLineEdit(self.obj.label)
        # Editando uma lesão já guardada (painel de medidas): volta com o que valia quando ela
        # foi guardada, e o "Guardar" atualiza a mesma medida em vez de criar outra.
        self.existente = existente
        if existente is not None:
            m = existente.meta or {}
            if existente.db_id:
                # a máscara guardada sai da tela enquanto esta janela mostra a que está sendo editada
                tab._segs_em_edicao = set(getattr(tab, "_segs_em_edicao", set())) | {existente.db_id}
                tab.overlay_objects[:] = [o for o in tab.overlay_objects if o.key != f"segann:{existente.db_id}"]
            if m.get("cor"):
                self.color = tuple(m["cor"])
                self.obj.color = self.color
            self.name.setText(existente.text or self.name.text())
            self.obj.label = self.name.text()
            if m.get("method"):
                self.method.setCurrentIndex(max(0, self.method.findData(m["method"])))
            if m.get("pct") is not None:
                self.pct.setValue(float(m["pct"]))
            if m.get("limiar") is not None:
                self.limiar.setValue(float(m["limiar"]))
            if m.get("raio_mm") is not None:
                self.radius.setValue(float(m["raio_mm"]))
        self.refs = None                 # referências do exame (pele, mamilo, parede)
        self.dist = {}                   # últimas distâncias medidas
        self.distancias_label = QLabel()
        self.distancias_label.setWordWrap(True)
        self.distancias_label.setVisible(False)
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setMinimumWidth(360)
        form = QFormLayout()
        form.addRow("Nome:", self.name)
        form.addRow("Método:", self.method)
        self.row_lo = form.rowCount()
        form.addRow("Mínimo:", self.lo)
        form.addRow("Máximo:", self.hi)
        form.addRow("% do SUVmáx:", self.pct)
        form.addRow("SUV mínimo:", self.abs)
        linha_lim = QHBoxLayout()
        linha_lim.addWidget(self.limiar)
        for texto, passo in (("−", -10.0), ("+", 10.0)):
            b = QPushButton(texto)
            b.setFixedWidth(30)
            b.setToolTip("Aperta a região" if passo > 0 else "Solta a região")
            b.clicked.connect(lambda _=False, p=passo: self._passo_limiar(p))
            linha_lim.addWidget(b)
        linha_lim.addStretch(1)
        form.addRow("Realce mínimo:", linha_lim)
        self._linha_limiar = linha_lim
        # Pedido dele (10/10): "quero poder ajustar o threshold, em uma barra, assim que a
        # segmentação for feita, aumentando ou reduzindo o que está sendo incluído". A barra mexe
        # no mesmo número do campo (% da lesão ou realce mínimo) e a região se refaz sozinha, com
        # um pequeno atraso para não recalcular a cada pixel do arrasto.
        self.barra = QSlider(Qt.Horizontal)
        self.barra.setToolTip("Para a esquerda entra mais tecido; para a direita, menos")
        self.barra.valueChanged.connect(self._barra_mexeu)
        self._t_barra = QTimer(self)
        self._t_barra.setSingleShot(True)
        self._t_barra.setInterval(150)
        self._t_barra.timeout.connect(lambda: self.run(keep_range=True))
        linha_barra = QHBoxLayout()
        self._barra_mais = QLabel("inclui mais")
        self._barra_menos = QLabel("inclui menos")
        for lab in (self._barra_mais, self._barra_menos):
            lab.setStyleSheet("color:#999")
        linha_barra.addWidget(self._barra_mais)
        linha_barra.addWidget(self.barra, 1)
        linha_barra.addWidget(self._barra_menos)
        form.addRow("Limiar:", linha_barra)
        self._linha_barra = linha_barra
        for spin in (self.pct, self.limiar):
            spin.valueChanged.connect(lambda _v: self._ajustar_barra())
        form.addRow("Raio máximo:", self.radius)
        self.form = form
        b_run = QPushButton("Recalcular")
        b_run.clicked.connect(lambda: self.run(keep_range=True))
        b_save = QPushButton("Guardar como medida")
        b_save.setToolTip("Guarda volume e valores no exame (entram no laudo e no TMTV)")
        b_save.clicked.connect(self.save)
        b_les = QPushButton("Guardar e ligar a uma lesão…")
        b_les.clicked.connect(lambda: self.save(link=True))
        b_seg = QPushButton("Salvar como DICOM SEG")
        b_seg.clicked.connect(self.save_dicom)
        self.b_dist = QPushButton("Distância ao mamilo")
        self.b_dist.setToolTip("Mede da borda e do centro da lesão até o mamilo. Com o mamilo "
                               "marcado, sai na hora; sem ele, o programa procura o mamilo pela "
                               "pele (uns 15 s na primeira lesão do exame).")
        self.b_dist.clicked.connect(self.medir_distancias)
        self.b_mamilo = QPushButton("Marcar o mamilo")
        self.b_mamilo.setToolTip("Clique aqui e depois no mamilo, na imagem. A distância sai na "
                                 "hora, a partir do seu ponto, e o ponto vale para as outras "
                                 "lesões da mesma mama neste exame.")
        self.b_mamilo.clicked.connect(self.pedir_mamilo)
        self.b_sc = QPushButton("Salvar captura (SC)…")
        self.b_sc.setToolTip("Grava no exame uma imagem 2×2 da lesão: sagital e coronal em cima, "
                             "axial e curva de realce embaixo, com as medidas no rodapé")
        self.b_sc.clicked.connect(self.salvar_captura)
        b_stl = QPushButton("Superfície 3D (STL)…")
        b_stl.setToolTip("Malha da superfície desta segmentação, para impressão 3D ou planejamento")
        b_stl.clicked.connect(self.save_surface)
        b_close = QPushButton("Descartar")
        b_close.clicked.connect(self.discard)
        row = QHBoxLayout()
        for b in (b_run, b_save, b_les):
            row.addWidget(b)
        row_d = QHBoxLayout()
        row_d.addWidget(self.b_dist)
        row_d.addWidget(self.b_mamilo)
        row_d.addStretch(1)
        row_d.addWidget(self.b_sc)
        row2 = QHBoxLayout()
        row2.addWidget(b_seg)
        row2.addWidget(b_stl)
        row2.addStretch(1)
        row2.addWidget(b_close)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.result)
        lay.addWidget(self.distancias_label)
        lay.addLayout(row)
        if cad is not None:          # as distâncias são da mama: só na dinâmica
            lay.addLayout(row_d)
        lay.addLayout(row2)
        self.method.currentIndexChanged.connect(lambda _i: (self._show_rows(), self.run(keep_range=False)))
        self.res = None
        self.saved_ann = existente
        self._show_rows()
        self.run(keep_range=False)
        if existente is not None and cad is not None and (existente.meta or {}).get("dist_mamilo_mm") is not None:
            mm = (existente.meta or {}).get("mamilo_mm")
            if mm is not None and (existente.meta or {}).get("mamilo_marcado"):
                # volta com o mamilo desta lesão, sem procurar a pele de novo
                self._garantir_refs_marcadas().manual = np.asarray(mm, float)
                self.atualizar_distancias()
            else:
                self.medir_distancias()

    def _passo_limiar(self, passo: float) -> None:
        """Ajuste em passos, como no CADstream: cada toque aperta ou solta a região."""
        alvo = self.pct if self.method.currentData() == "realce_pct" else self.limiar
        alvo.setValue(min(alvo.maximum(), max(alvo.minimum(), alvo.value() + passo)))
        self.run(keep_range=True)

    def _show_rows(self) -> None:
        m = self.method.currentData()
        for w, vis in ((self.lo, m == "range"), (self.hi, m == "range"),
                       (self.pct, m in ("pet_pct", "realce_pct")), (self.abs, m == "pet_abs")):
            w.setVisible(vis)
            lab = self.form.labelForField(w)
            if lab is not None:
                lab.setVisible(vis)
        for i in range(self._linha_limiar.count()):
            it = self._linha_limiar.itemAt(i).widget()
            if it is not None:
                it.setVisible(m == "realce" or (i > 0 and m == "realce_pct"))
        lab = self.form.labelForField(self._linha_limiar)
        if lab is not None:
            lab.setVisible(m == "realce")
        rot = self.form.labelForField(self.pct)
        if rot is not None:
            rot.setText("% do realce da lesão:" if m == "realce_pct" else "% do SUVmáx:")
        com_barra = m in ("realce_pct", "realce", "pet_pct")
        for w in (self.barra, self._barra_mais, self._barra_menos):
            w.setVisible(com_barra)
        lab = self.form.labelForField(self._linha_barra)
        if lab is not None:
            lab.setVisible(com_barra)
        self._ajustar_barra()

    def _alvo_da_barra(self):
        """O número que a barra mexe: % (da lesão ou do SUVmáx) ou o realce mínimo fixo."""
        return self.limiar if self.method.currentData() == "realce" else self.pct

    def _ajustar_barra(self) -> None:
        alvo = self._alvo_da_barra()
        self.barra.blockSignals(True)
        self.barra.setRange(int(alvo.minimum()), int(min(alvo.maximum(), 400)))
        self.barra.setValue(int(round(alvo.value())))
        self.barra.blockSignals(False)

    def _barra_mexeu(self, valor: int) -> None:
        alvo = self._alvo_da_barra()
        alvo.blockSignals(True)
        alvo.setValue(float(valor))
        alvo.blockSignals(False)
        self._t_barra.start()

    def run(self, keep_range: bool = True) -> None:
        from ipe.imaging.segment import segment
        m = self.method.currentData()
        lo = hi = None
        if m == "range" and keep_range and self.res is not None:
            lo, hi = self.lo.value(), self.hi.value()
        if m == "realce":
            lo, hi = self.limiar.value(), None
        try:
            self.res = segment(self.vol, self.seed, m, lo, hi, self.suv, self.pct.value(), self.abs.value(),
                               self.radius.value(), self.modality)
        except Exception as e:  # noqa: BLE001
            log.exception("segmentação")
            self.result.setText(f"Erro: {e}")
            return
        if m == "range":
            self.lo.setValue(self.res.lo)
            self.hi.setValue(self.res.hi)
        # Máscara em mm (0.68): aparece em qualquer série e em qualquer plano do exame, não só
        # nas imagens paralelas à aquisição.
        self.obj.masks = []
        self.obj.volumes = ([O.MaskVolume.do_volume(self.vol, self.res.mask, self.res.offset, self.color,
                                                    self.name.text())] if self.res.voxels else [])
        self.obj.study_uid = self.vp.study_uid or ""
        self.obj.label = self.name.text()
        self.obj.stats = self.res.meta()
        self.obj.version += 1
        self.tab._apply_overlays()
        if self.cad is not None:
            self._mostrar_cad()
            self.atualizar_distancias()
            return
        txt = f"<b>{self.res.summary()}</b>" if self.res.voxels else "<b>Nada segmentado.</b>"
        if self.res.notes:
            txt += "<br><span style='color:#c80'>" + "; ".join(self.res.notes) + "</span>"
        rng = f"faixa usada: {self.res.lo:.2f} a " + ("∞" if not np.isfinite(self.res.hi) else f"{self.res.hi:.2f}")
        txt += f"<br><span style='color:#888'>{self.res.voxels} voxels · {rng}</span>"
        self.result.setText(txt)

    def _mostrar_cad(self) -> None:
        """Os números do CAD da lesão, com os seis padrões em cor — a mesma cor do mapa."""
        from ipe.imaging import cad_mama as C
        from ipe.imaging import colormaps as CM
        from ipe.imaging.dynamic import CLASSES
        realce, classes = self.cad
        self.medidas = C.medir(realce, classes, self.res)
        m = self.medidas
        if not self.res.voxels:
            self.result.setText("<b>Nada segmentado.</b> Baixe o realce mínimo e clique de novo "
                                "em “Recalcular”.")
            return
        # Montado por concatenação: "<b>{}:</b> {}" seria um padrão genérico de tradução,
        # desses que sequestram qualquer outro texto de dois pedaços.
        linhas = ["<b>" + rot + ":</b> " + val for rot, val in m.linhas()]
        if m.percentuais:
            lut = CM.lut("cinetico")
            cores = {CLASSES[c]: tuple(lut[int(255 * (c + 0.5) / 7)]) for c in range(1, 7)}
            tabela = []
            for nome, pct in m.percentuais.items():
                r, g, b = cores.get(nome, (170, 170, 170))
                cor = f"rgb({r},{g},{b})"
                tabela.append("<span style='color:" + cor + "'>■</span> " + nome + f" {pct:.0f}%")
            linhas.append("Padrões: " + " · ".join(tabela))
        if m.avisos:
            linhas.append("<span style='color:#c80'>" + " ".join(m.avisos) + "</span>")
        linhas.append(f"<span style='color:#888'>{self.res.voxels} voxels · realce mínimo "
                      f"{self.res.lo:.0f}%</span>")
        self.result.setText("<br>".join(linhas))

    # ------------------------------------------------------------------ distância ao mamilo
    def _marcados(self):
        sessao = getattr(self.tab, "dyn", None)
        if sessao is None or not hasattr(self.tab, "mamilos_marcados"):
            return None
        return self.tab.mamilos_marcados(sessao, self.vol)

    def _garantir_refs_marcadas(self):
        """Referências sem pele nem parede, só com os mamilos marcados (não monta nada)."""
        from ipe.imaging import mama_distancias as MD
        if self.refs is None:
            self.refs = MD.Referencias.so_marcados(self._marcados() or MD.MamilosMarcados())
        return self.refs

    def _centro_da_lesao(self):
        from ipe.imaging import mama_distancias as MD
        if self.res is None or not self.res.voxels:
            return None
        pontos = MD.superficie_da_lesao(self.res.mask, self.res.offset, MD.afim_do_objeto(self.vol))
        return pontos.mean(axis=0) if len(pontos) else None

    def medir_distancias(self) -> None:
        """Distância da borda (e do centro) da lesão até o mamilo.

        Mamilo marcado nesta mama: sai na hora, do ponto dele. Sem marca: o programa procura o
        mamilo pela pele do exame (monta uma vez, uns 15 s), e o botão Marcar corrige.
        """
        sessao = getattr(self.tab, "dyn", None)
        if self.cad is None or sessao is None:
            return
        if self.refs is None:
            marcados = self._marcados()
            centro = self._centro_da_lesao()
            if marcados is not None and centro is not None and marcados.do_lado(centro) is not None:
                self._garantir_refs_marcadas()
            else:
                refs = self.tab.referencias_da_mama(sessao)
                if refs is None:
                    return
                refs.marcados = marcados
                self.refs = refs
        self.atualizar_distancias()

    def atualizar_distancias(self) -> None:
        """Recalcula e mostra as distâncias (rápido: as referências já estão prontas)."""
        from ipe.imaging import mama_distancias as MD
        if self.refs is None or self.res is None or not self.res.voxels:
            return
        afim = MD.afim_do_objeto(self.vol)
        pontos = MD.superficie_da_lesao(self.res.mask, self.res.offset, afim)
        self.dist = MD.distancias(self.refs, pontos)
        linhas = ["<b>" + rot + ":</b> " + val for rot, val in MD.linhas_mamilo(self.dist)]
        if not linhas:
            self.distancias_label.setVisible(False)
            return
        avisos = [] if self.dist.get("mamilo_manual") else MD.avisos_do_mamilo(self.refs)
        if avisos:
            linhas.append("<span style='color:#c80'>" + " ".join(avisos) + "</span>")
        if not self.dist.get("mamilo_manual"):      # ponto do programa: dizer como corrigir
            linhas.append("<span style='color:#888'>" + MD.TEXTO_MAMILO + "</span>")
        self.distancias_label.setText("<br>".join(linhas))
        self.distancias_label.setVisible(True)

    def pedir_mamilo(self) -> None:
        self.tab._mamilo_pendente = self
        self.tab.status_message.emit("Clique no mamilo, na imagem, com a ferramenta Segmentar.")

    def mamilo_clicado(self, vp, u: float, v: float) -> None:
        """O médico apontou o mamilo: o ponto dele manda sobre o automático."""
        p = vp.pixel_to_patient(u - 0.5, v - 0.5)
        if p is None:
            self.tab.status_message.emit("O ponto clicado não tem posição no paciente.")
            return
        p = np.asarray(p, float)
        refs = self._garantir_refs_marcadas()
        marcados = self._marcados()
        if marcados is not None:
            marcados.marcar(p)                  # vale para as outras lesões desta mama
            if refs.marcados is None:
                refs.marcados = marcados
            refs.manual = None
        else:
            refs.manual = p
        self.atualizar_distancias()
        self.tab.status_message.emit("Mamilo marcado: a distância sai deste ponto, e ele vale para "
                                     "as outras lesões desta mama no exame.")

    def distancias_meta(self) -> dict:
        """O que vai para a medida guardada (laudo e painel de medidas): só o mamilo.

        Pele e peitoral saíram a pedido dele (10/10/2026). O ponto do mamilo vai junto, para a
        edição da lesão voltar com o mamilo que ele marcou."""
        d = self.dist or {}
        out = {}
        for chave, nome in (("mamilo", "dist_mamilo_mm"), ("mamilo_centro", "dist_mamilo_centro_mm")):
            v = d.get(chave)
            if v is not None and np.isfinite(v):
                out[nome] = round(float(v), 1)
        if "mamilo_manual" in d:
            out["mamilo_marcado"] = bool(d["mamilo_manual"])
        ponto = d.get("mamilo_ponto")
        if ponto is not None and out:
            out["mamilo_mm"] = [round(float(x), 2) for x in ponto]
        return out

    def _imagem_de_verdade(self, key):
        """O quadro do mapa da dinâmica não é imagem do banco (SOP vazio): a medida guardada lá
        só valia na sessão. Defeito achado na 0.67 — a lesão do CAD nunca chegava ao banco, e por
        isso não aparecia no painel de medidas nem no laudo. Agora ela fica presa à imagem da
        fase inicial no mesmo corte, que é imagem de verdade e tem a mesma grade de pixels.
        Devolve (frame_key, series_uid) ou None se a chave já é de uma imagem do banco."""
        if self.cad is None or (key and key[0]):
            return None
        maps = getattr(getattr(self.tab, "dyn", None), "maps", None)
        if maps is None:
            return None
        fase = maps.dset.phases[maps.early]
        k = int(np.clip(self.seed[0], 0, len(fase) - 1))
        f = fase[k]
        if not f.sop_uid:
            return None
        return (f.sop_uid, f.frame_index), (f.series_uid or "")

    def params_meta(self) -> dict:
        """Como a lesão foi feita: o bastante para reabrir e editar (semente, limiar, raio) e para
        desenhá-la de novo do jeito que ela é (a máscara em mm, a cor)."""
        k, j, i = self.seed
        p = self.vol.voxel_to_patient(i, j, k)
        out = {"semente_mm": [round(float(x), 2) for x in p], "pct": float(self.pct.value()),
               "limiar": float(self.limiar.value()), "raio_mm": float(self.radius.value()),
               "cor": [int(c) for c in self.color[:3]]}
        if self.res is not None and self.res.voxels:
            out["mascara3d"] = O.MaskVolume.do_volume(self.vol, self.res.mask, self.res.offset,
                                                      self.color).para_meta()
        uids = (getattr(getattr(self.tab, "dyn", None), "params", None) or {}).get("uids") if self.cad else None
        if uids:
            out["dyn_uids"] = list(uids)
        return out

    def save(self, link: bool = False) -> None:
        from ipe.imaging.measure import Annotation
        if self.res is None or not self.res.voxels:
            return
        vp = self.vp
        if self.saved_ann is None:
            f = vp.current_frame()
            key = self.frame_key or vp.frame_key()
            series_uid = f.series_uid if f is not None and f.series_uid else vp.series_uid
            real = self._imagem_de_verdade(key)
            if real is not None:
                key, series_uid = real
            ann = Annotation("seg", key, [self.uv], self.name.text(), study_uid=vp.study_uid,
                             series_uid=series_uid)
            ann.meta = {**self.res.meta(), **(self.medidas.meta() if self.medidas else {}),
                        **self.distancias_meta(), **self.params_meta()}
            vp.annotations.append(ann)
            self.saved_ann = ann
            self.obj.ann = ann          # a janela já desenha esta lesão: o banco não desenha outra
        else:
            keep = {k: v for k, v in (self.saved_ann.meta or {}).items()
                    if k in ("lesion", "lesion_name", "sc_series", "sc_sop")}
            self.saved_ann.meta = {**self.res.meta(), **(self.medidas.meta() if self.medidas else {}),
                                   **self.distancias_meta(), **self.params_meta(), **keep}
            self.saved_ann.text = self.name.text()
        self.obj.ann = self.saved_ann
        vp._store("save", self.saved_ann)
        if self.saved_ann.db_id:
            self.obj.key = f"segann:{self.saved_ann.db_id}"
        vp.update()
        self.tab.status_message.emit(f"Segmentação guardada: {self.res.summary()}")
        if self.cad is not None:
            self.tab.settings.set("segment.realce_pct", self.pct.value())
        elif self.modality == "PT":
            # O método já era lembrado; os dois números, não — ele digitava 41% e o SUV mínimo
            # em cada lesão. Padrão é o último que ele usou, e isso vale para os três.
            self.tab.settings.set("segment.pet_method", self.method.currentData())
            self.tab.settings.set("segment.pet_pct", self.pct.value())
            self.tab.settings.set("segment.pet_abs", self.abs.value())
        if link:
            self.tab.choose_lesion_for(vp, self.saved_ann)
        self.tab.refresh_lesions()

    def save_dicom(self) -> None:
        from ipe.imaging.seg_writer import build_seg
        from ipe.importer.scanner import Importer
        if self.res is None or not self.res.voxels:
            return
        storage = getattr(self.tab, "storage_root", None)
        if storage is None:
            QMessageBox.information(self, "DICOM SEG", "Banco de dados indisponível.")
            return
        try:
            ds = build_seg(self.vol, [(self.res, self.name.text(), self.color)], self.vol.source_path,
                           self.vp.frames)
            tmp = Path(tempfile.mkdtemp(prefix="dv_seg_"))
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            Importer(self.tab.repo.db, storage).import_paths([tmp])
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            from ipe.central.client_repo import upload_if_client
            upload_if_client(self.tab.repo, self.vp.study_uid)
        except Exception as e:  # noqa: BLE001
            log.exception("SEG")
            QMessageBox.warning(self, "DICOM SEG", f"Não foi possível gravar:\n{e}")
            return
        self.tab.status_message.emit("Segmentação guardada no exame como DICOM SEG (série “Segmentação (Ipe)”).")

    def save_surface(self) -> None:
        """A superfície desta segmentação vira malha e arquivo STL."""
        if self.res is None or not self.res.voxels:
            QMessageBox.information(self, "Superfície", "Segmente alguma coisa primeiro.")
            return
        from ipe.ui.surface_dialog import SurfaceDialog
        dlg = SurfaceDialog(self.vol, self.res.mask, self.res.offset,
                            self.name.text() or "Segmentação", self)
        dlg.calcular()
        dlg.exec()

    # ------------------------------------------------------- captura 2×2 (Secondary Capture)
    def dados_da_captura(self):
        """Tudo o que a captura mostra, tirado do que a janela já calculou."""
        from ipe.imaging import colormaps as CM
        from ipe.imaging import mama_distancias as MD
        from ipe.imaging.dynamic import CLASSES
        from ipe.ui.viewer.lesao_captura import DadosCaptura
        sessao = getattr(self.tab, "dyn", None)
        maps = sessao.maps
        # A 2ª fase da dinâmica (a primeira pós-contraste do VIBRANT), a pedido dele — e não a
        # "inicial" calculada pelo tempo, que pode ser outra fase.
        i_fase = 1 if len(maps.dset.phases) > 1 else maps.early
        fase = maps.volume_da_fase(i_fase)
        info = getattr(self.tab, "study_info", {}) or {}
        data = str(info.get("study_date") or "")
        data = f"{data[6:]}/{data[4:6]}/{data[:4]}" if len(data) == 8 else data
        cab = " · ".join(x for x in (info.get("patient_name", ""),
                                      f"ID {info['patient_id']}" if info.get("patient_id") else "",
                                      data, info.get("description", "")) if x)
        m = self.medidas
        linhas = list(m.linhas()) if m is not None else []
        linhas += MD.linhas_mamilo(self.dist or {})
        curva = maps.curva_da_lesao(self.res.mask, self.res.offset)
        tipo = ""
        if curva is not None:
            st = maps.curve_stats(curva)
            partes = [f"Curva tipo {st['type']}" if st.get("type") else "",
                      f"SER {st['ser']:.2f}" if st.get("ser") is not None else "",
                      st.get("cinetica") or ""]
            tipo = " · ".join(x for x in partes if x)
        if self.method.currentData() == "realce_pct":
            lim = f"{self.pct.value():.0f}% do realce da própria lesão"
        else:
            lim = f"realce mínimo {self.res.lo:.0f}%"
        linhas.append(("Limiar da segmentação", lim))
        padroes = []
        if m is not None and m.percentuais:
            lut = CM.lut("cinetico")
            cores = {CLASSES[c]: tuple(int(x) for x in lut[int(255 * (c + 0.5) / 7)][:3])
                     for c in range(1, 7)}
            padroes = [(nome, pct, cores.get(nome, (170, 170, 170)))
                       for nome, pct in m.percentuais.items() if pct > 0]
        nome_fase = maps.dset.labels[i_fase] if i_fase < len(maps.dset.labels) else ""
        rodape = ("Medida semiautomática (Ipê): crescimento de região sobre o realce a "
                  "partir do clique do médico — conferir antes de usar. " + maps.legenda_cinetica())
        if m is not None and m.avisos:
            rodape = " ".join(m.avisos) + " " + rodape
        return DadosCaptura(
            fase=fase, mascara=self.res.mask, offset=self.res.offset, cor=tuple(self.color),
            nome=self.name.text() or "Lesão", cabecalho=cab,
            rotulo_fase=f"Fase {i_fase + 1} · {nome_fase}" if nome_fase else f"Fase {i_fase + 1}",
            linhas=linhas, padroes=padroes, tempos_s=list(maps.dset.times), curva=curva,
            pre=maps.pre, inicial=maps.early, tardia=maps.late, tipo_curva=tipo, rodape=rodape,
            maior_eixo_mm=float(m.maior_3d_mm if m is not None else (self.res.max_diam_mm or 0.0)))

    def perguntar_substituir(self) -> str | None:
        """"substituir", "nova" ou None (cancelou). Separado para poder testar sem clicar."""
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Captura da lesão")
        caixa.setText("Esta lesão já tem uma captura salva no exame.\n\n"
                      "Substituir a anterior pela nova, ou guardar as duas?")
        b_sub = caixa.addButton("Substituir a anterior", QMessageBox.AcceptRole)
        b_nova = caixa.addButton("Criar nova", QMessageBox.ActionRole)
        caixa.addButton("Cancelar", QMessageBox.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is b_sub:
            return "substituir"
        if caixa.clickedButton() is b_nova:
            return "nova"
        return None

    def salvar_captura(self) -> str | None:
        """Grava a captura 2×2 no exame (Secondary Capture). Devolve o UID da série nova.

        A lesão é guardada como medida antes, se ainda não foi: a captura fica ligada a ela
        (`sc_series` na medida), e é isso que permite perguntar, depois de uma edição, se a
        captura nova substitui a anterior."""
        from ipe.imaging.derived import qimage_to_rgb, save_secondary_capture
        from ipe.ui.viewer.lesao_captura import montar
        if self.cad is None or self.res is None or not self.res.voxels:
            QMessageBox.information(self, "Captura da lesão", "Segmente a lesão na dinâmica primeiro.")
            return None
        storage = getattr(self.tab, "storage_root", None)
        if storage is None:
            QMessageBox.information(self, "Captura da lesão", "Banco de dados indisponível.")
            return None
        if self.saved_ann is None or not self.saved_ann.db_id:
            self.save()
        ann = self.saved_ann
        if ann is None:
            return None
        anterior = (ann.meta or {}).get("sc_series")
        if anterior and not self.tab.repo.instances_for_series(anterior):
            anterior = None                   # a captura anterior foi apagada por fora
        escolha = "nova"
        if anterior:
            escolha = self.perguntar_substituir()
            if escolha is None:
                return None
        try:
            img = montar(self.dados_da_captura())
            nome = self.name.text() or "Lesão"
            uid, sops = save_secondary_capture(qimage_to_rgb(img), self.tab.dyn.maps.source_path,
                                               self.tab.repo.db, storage, f"Captura: {nome}"[:64], 960)
        except Exception as e:  # noqa: BLE001
            log.exception("captura da lesão")
            QMessageBox.warning(self, "Captura da lesão", f"Não foi possível gravar a captura:\n{e}")
            return None
        if escolha == "substituir":
            try:
                self.tab.repo.delete_series(anterior, storage)
            except Exception as e:  # noqa: BLE001
                log.exception("apagar a captura anterior")
                QMessageBox.warning(self, "Captura da lesão", "A captura nova foi gravada, mas a "
                                    f"anterior não pôde ser apagada:\n{e}")
        ann.meta = {**(ann.meta or {}), "sc_series": uid, "sc_sop": sops[0] if sops else ""}
        self.vp._store("save", ann)
        try:
            from ipe.central.client_repo import upload_if_client
            upload_if_client(self.tab.repo, self.vp.study_uid)
        except Exception:  # noqa: BLE001
            log.exception("captura da lesão no servidor central")
        recarregar = getattr(self.tab, "recarregar_series", None)
        if recarregar is not None:
            recarregar()
        self.tab.status_message.emit("Captura da lesão salva no exame"
                                     + (" (substituiu a anterior)." if escolha == "substituir" else "."))
        return uid

    def discard(self) -> None:
        self.close()

    def closeEvent(self, e) -> None:  # noqa: N802
        # O que não foi guardado sai da tela; numa edição desistida, volta a máscara do banco.
        if not self.obj.key.startswith("segann:") and self.obj in self.tab.overlay_objects:
            self.tab.overlay_objects.remove(self.obj)
        if self.existente is not None and self.existente.db_id:
            self.tab._segs_em_edicao = set(getattr(self.tab, "_segs_em_edicao", set())) - {self.existente.db_id}
        carregar = getattr(self.tab, "carregar_segmentacoes", None)
        if carregar is not None:
            carregar()
        self.tab._apply_overlays()
        super().closeEvent(e)
