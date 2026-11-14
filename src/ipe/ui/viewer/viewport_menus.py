"""Menus do quadro (mixin do Viewport, separado do `viewport.py` na 0.100.42).

Aqui ficam: o menu do zoom, digitar o zoom e a janela, o menu do botão direito (ferramentas, medida, BI-RADS,
numeração da coluna, DSA) e as tags DICOM.

Os métodos continuam sendo do Viewport (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import (
    QAction,
)
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox

from ipe.imaging import measure as M
from ipe.imaging.series import Frame, FrameCache, FrameImage  # noqa: F401

from ipe.ui.viewer.annotate import (
    FERRAMENTAS_DE_DESENHO, RASCUNHAVEIS,
)

log = logging.getLogger("ipe.ui.viewer.viewport")      # o mesmo registro de antes da separação


class VpMenusMixin:
    """VpMenusMixin: métodos do ViewerTab separados (mesmos nomes)."""

    def menu_do_zoom(self) -> QMenu:
        """Duplo clique no "Zoom N%" do canto (0.99.45): ajustar, 1:1, valores prontos ou digitar."""
        menu = QMenu(self)
        menu.addAction("Ajustar à janela").triggered.connect(self.fit)
        menu.addAction("1 pixel da imagem = 1 pixel da tela (1:1)").triggered.connect(self.zoom_actual_pixels)
        menu.addSeparator()
        for pct in (50, 150, 200, 300, 400):
            menu.addAction(f"{pct}%").triggered.connect(lambda _=False, f=pct / 100: self.aplicar_zoom("ajuste", f))
        menu.addSeparator()
        menu.addAction("Digitar o zoom…").triggered.connect(self.digitar_zoom)
        return menu

    def aplicar_zoom(self, modo: str, fator: float) -> None:
        """`modo` "ajuste": em relação a ajustar à janela (o número do canto); "pixel": pixels da
        imagem por pixel da tela. A imagem continua centrada onde estava."""
        if modo == "pixel":
            f = self.fit_scale()
            if f <= 0:
                return
            fator = fator / f
        self.quad_idx = -1
        self.anat_lock = self._anat_box_norm = None
        self.state.zoom = float(np.clip(fator, 0.05, 40))
        self.update()
        self.sig.view_changed.emit(self, "zoom")

    def digitar_zoom(self) -> None:
        from ipe.imaging import presets_janela as PJ
        txt, ok = QInputDialog.getText(self, "Zoom", "Zoom (ex.: 150, 150%, 2x, 1:1):",
                                       text=f"{self.state.zoom * 100:.0f}%")
        if not ok:
            return
        z = PJ.ler_zoom(txt)
        if z is None:
            QMessageBox.warning(self, "Zoom", "Digite uma porcentagem (5 a 4000), um fator (2x) ou 1:1.")
            return
        self.aplicar_zoom(*z)

    def digitar_janela(self) -> None:
        """Clicar no "W 400 L 40" e digitar (0.99.22, plano AW item 9)."""
        from ipe.imaging import presets_janela as PJ
        txt, ok = QInputDialog.getText(self, "Janela", "Largura e nível (ex.: 400 40):",
                                       text=f"{self.state.width:.0f} {self.state.level:.0f}")
        if not ok:
            return
        wl = PJ.ler_wl(txt)
        if wl is None:
            QMessageBox.warning(self, "Janela", "Digite dois números: a largura (maior que zero) e o nível.")
            return
        self.set_window(*wl)

    def guardar_janela_atual(self) -> bool:
        """Guarda a janela à vista como preset da modalidade do quadro (0.99.22, item 10)."""
        from ipe.imaging import presets_janela as PJ
        mod = self.modalidade_atual() or ""
        nome, ok = QInputDialog.getText(self, "Guardar a janela atual",
                                        f"Nome do preset ({mod or 'geral'}, W {self.state.width:.0f} "
                                        f"L {self.state.level:.0f}):", text=self.nome_da_janela())
        if not ok or not nome.strip():
            return False
        tecla = PJ.tecla_livre(self.settings, mod) if PJ.tem_lista_propria(self.settings, mod) or \
            (mod and mod != "CT") else None
        teclas = [str(k) for k in range(1, 10)]
        if tecla is None:
            atuais = self.presets_da_janela()
            itens = [f"{k}  {atuais[k][0]}" if k in atuais else f"{k}  (livre)" for k in teclas]
            esc, ok = QInputDialog.getItem(self, "Guardar a janela atual", "Em que tecla?", itens, 0, False)
            if not ok:
                return False
            tecla = esc.split()[0]
        PJ.guardar(self.settings, mod, tecla, nome.strip(), self.state.width, self.state.level)
        return True

    def show_preset_menu(self, global_pos) -> None:
        menu = QMenu(self)
        self._add_preset_actions(menu)
        menu.exec(global_pos)

    def _add_preset_actions(self, menu: QMenu) -> None:
        js = self.janelas_do_arquivo()
        if js:
            tit = QAction("Do arquivo (Switch WL)", menu)
            tit.setEnabled(False)
            menu.addAction(tit)
            for i, (nome, w, l) in enumerate(js):
                act = QAction(f"   {nome}  (W {w:g} / L {l:g})", menu)
                act.triggered.connect(lambda _=False, k=i: self.usar_janela_do_arquivo(k))
                menu.addAction(act)
            menu.addSeparator()
        for key, (name, w, l) in sorted(self.presets_da_janela().items()):
            if not name:
                continue
            act = QAction(f"{key}  {name}  (W {w} / L {l})", menu)
            act.triggered.connect(lambda _=False, kk=key: self.apply_preset(kk))
            menu.addAction(act)
        auto = QAction("0  Automático / do arquivo", menu)
        auto.triggered.connect(lambda: (setattr(self.state, "window_set", False),
                                        self._load_current(), self.update()))
        menu.addAction(auto)
        menu.addSeparator()
        dig = QAction("Digitar a janela…", menu)
        dig.triggered.connect(self.digitar_janela)
        menu.addAction(dig)
        cap = QAction("Guardar a janela atual como preset…", menu)
        cap.setToolTip("Vale para a modalidade deste quadro: RM, mamografia e PET podem ter presets próprios.")
        cap.triggered.connect(self.guardar_janela_atual)
        menu.addAction(cap)

    def abrir_perfil(self, ann):
        """Gráfico do valor ao longo da régua/polilinha (0.99.31)."""
        from ipe.ui.viewer.perfil import PerfilDialog
        d = PerfilDialog(self, ann, self.window())
        self._perfis = [x for x in getattr(self, "_perfis", []) if x is not None] + [d]
        d.show()
        return d

    def show_context_menu(self, global_pos, local_pos: QPointF | None = None) -> None:
        self.build_context_menu(local_pos).exec(global_pos)

    def _aba(self, atributo: str):
        """A aba (ViewerTab) que tem `atributo`, subindo pelos pais; None fora de uma aba."""
        w = self.parentWidget()
        while w is not None and not hasattr(w, atributo):
            w = w.parentWidget()
        return w

    def regioes_do_exame(self) -> set:
        """Regiões do corpo do exame aberto (Tórax, Mama…), pelas regras das aplicações (0.99.78)."""
        tab = self._aba("contexto_do_exame")
        if tab is None:
            return set()
        try:
            return set(tab.contexto_do_exame().regioes)
        except Exception:  # noqa: BLE001
            return set()

    def acoes_de_ferramenta_agrupadas(self, menu: QMenu) -> None:
        """Ferramenta do botão esquerdo em três grupos: navegar, medir e desenhar (0.99.78)."""
        from ipe.ui.viewer.annotate import ferramentas_divididas
        mouse, medidas = ferramentas_divididas()
        desenho = {k: medidas.pop(k) for k in FERRAMENTAS_DE_DESENHO if k in medidas}
        for titulo, itens in (("Navegar", mouse), ("Medir", medidas), ("Desenhar", desenho)):
            if not itens:
                continue
            sub = menu.addMenu(titulo)
            for key, name in itens.items():
                act = QAction(name, sub, checkable=True, checked=(key == self.left_tool))
                act.triggered.connect(lambda _=False, kk=key: self.sig.tool_requested.emit(kk))
                sub.addAction(act)

    def build_context_menu(self, local_pos: QPointF | None = None) -> QMenu:
        """Menu do botão direito (enxugado na 0.99.78).

        Em cima, o que depende do lugar clicado (a medida debaixo do mouse, nódulo, achado BI-RADS,
        eixo de simetria, DSA). Depois imagem-chave e copiar; os ajustes em "Imagem", o que é do quadro
        em "Quadro"; anotações; a ferramenta do botão esquerdo; as tags. O que apaga fica no fim.
        As aplicações de IA (órgãos, coluna…) ficam só nos botões da barra.
        """
        menu = QMenu(self)
        mod = (self.modality or "").upper()
        cinza = self._img is not None and not self._img.is_color
        e_mama = self.mg_spec is not None or mod == "MG"
        if self.render3d is not None:
            self.render3d.add_menu_actions(self, menu)
        target = None
        if local_pos is not None and self._img is not None:
            target = self._annotation_at(self._img_pt(local_pos), self._img_tol())
        if target is not None:
            self._acoes_da_medida(menu, target)
            menu.addSeparator()

        # ---- o que depende do lugar clicado
        regs = None
        if local_pos is not None and self._img is not None and mod == "CT" \
                and self.render3d is None and self.frames and self.plane() is not None:
            regs = self.regioes_do_exame()
            if not regs or "torax" in regs:
                ip_nod = self.widget_to_image(local_pos)
                a_nod = QAction("Nódulo pulmonar aqui (segmentar por clique)…", menu)       # 0.99.62
                a_nod.triggered.connect(lambda: self.sig.nodulo_requested.emit(self, ip_nod.x(), ip_nod.y()))
                menu.addAction(a_nod)
        tab_f = self._aba("fundir_quadro")
        if tab_f is not None and local_pos is not None and cinza and e_mama:
            self._menu_birads(menu, tab_f, self.widget_to_image(local_pos))
        if local_pos is not None and self._img is not None and self.plane() is not None \
                and mod in ("MR", "CT", "PT") and self.mpr_plane is None:
            if regs is None:
                regs = self.regioes_do_exame()
            com_roi = any(a.kind in M.ROI_KINDS and a.frame_key == self.frame_key() for a in self.annotations)
            if (mod == "MR" and "mama" in regs) or self.eixo_manual() is not None or com_roi:
                em = menu.addMenu("Eixo de simetria (ROI espelhada)")          # 0.99.61
                a_eixo = em.addAction("Marcar o eixo aqui (meio do corpo neste ponto)")
                a_eixo.triggered.connect(lambda: self.marcar_eixo(local_pos))
                a_auto = em.addAction("Voltar ao eixo automático")
                a_auto.setEnabled(self.eixo_manual() is not None)
                a_auto.triggered.connect(self.esquecer_eixo)
        if len(self.frames) > 1 and mod in ("XA", "RF", "XRF", "DS"):
            self._menu_dsa(menu.addMenu("Subtração digital (DSA)"))
        if e_mama and cinza and local_pos is not None:
            pt = QPointF(local_pos)
            a_imp = QAction("Achar o implante a partir daqui", menu)
            a_imp.setToolTip("Use quando o programa não achar a prótese sozinho: clique dentro do silicone.")
            a_imp.triggered.connect(lambda: self.blank_implant_at(pt))
            menu.addAction(a_imp)
            if self.implant_mask:
                a_off = QAction("Mostrar o implante como veio do aparelho", menu)
                a_off.triggered.connect(lambda: (self.set_implant_mask(False),
                                                 self.sig.implant_changed.emit(self)))
                menu.addAction(a_off)
        self._menu_numeracao_da_coluna(menu, local_pos)
        if self.is_4d():
            cm = menu.addMenu(f"Cardíaco 4D ({self.cardiac.summary()})")
            cm.addAction("Cine das fases (ciclo parado neste corte)",
                         lambda: self.toggle_cine(phases=True))
            cm.addAction("Fase seguinte", lambda: self.set_cardiac_phase(self.cardiac_where()[1] + 1))
            cm.addAction("Fase anterior", lambda: self.set_cardiac_phase(self.cardiac_where()[1] - 1))
            cm.addSeparator()
            for p in range(self.cardiac.n_phases):
                a = QAction(f"Fase {p + 1}", cm, checkable=True, checked=self.cardiac_where()[1] == p)
                a.triggered.connect(lambda _c=False, q=p: self.set_cardiac_phase(q))
                cm.addAction(a)
        if self.mpr_plane is not None:
            n = len(self.frames)
            a_all = QAction(f"Salvar a reconstrução como série nova ({self.mpr_plane.name}, {n} imagens)", menu)
            a_all.triggered.connect(lambda: self.sig.reconstruction_save_requested.emit(self, False))
            menu.addAction(a_all)
            a_one = QAction("Salvar só esta imagem reconstruída como série nova", menu)
            a_one.triggered.connect(lambda: self.sig.reconstruction_save_requested.emit(self, True))
            menu.addAction(a_one)
        if (self.mpr_plane is not None or self.render3d is not None) and mod == "CT":
            tab = self._aba("alternar_mesa")
            if tab is not None:                               # 0.99.31 (onda A5)
                a_mesa = QAction("Tirar a mesa da TC (MPR e 3D)", menu, checkable=True,
                                 checked=bool(self.settings.get("viewer.tirar_mesa", False))
                                 if self.settings is not None else False)
                a_mesa.toggled.connect(tab.alternar_mesa)
                menu.addAction(a_mesa)
        menu.addSeparator()

        # ---- imagem-chave e cópia
        f_cur = self.current_frame()
        if f_cur is not None and not f_cur.is_virtual:
            is_key = (f_cur.sop_uid, f_cur.frame_index) in self.key_frames
            k_act = QAction("Desmarcar imagem-chave" if is_key else "Marcar imagem-chave ★", menu)
            k_act.triggered.connect(lambda: self.sig.key_toggle_requested.emit(self))
            menu.addAction(k_act)
        if self.frames and self._img is not None:
            cp = QAction("Copiar a imagem (área de transferência)", menu)
            cp.setToolTip("Como está na tela, com as anotações do nível em uso, em boa resolução")
            cp.triggered.connect(lambda: self.sig.copy_requested.emit(self))
            menu.addAction(cp)
        menu.addSeparator()

        # ---- Imagem ▸
        im = menu.addMenu("Imagem")
        self._add_preset_actions(im.addMenu("Janela (presets)"))
        if self._img is None or not self._img.is_color:
            self.add_colormap_actions(im.addMenu("Cor (tabela de cores)"), lembrar=True, principais=True)
        a_inv = QAction("Inverter", im)
        a_inv.triggered.connect(lambda: self.set_invert())
        im.addAction(a_inv)
        from ipe.imaging import filters as _filters
        fmenu = im.addMenu("Filtro da imagem")
        for nome in _filters.ORDER:
            a = QAction(_filters.label(nome), fmenu)
            a.setCheckable(True)
            a.setChecked(self.state.filter == nome)
            a.triggered.connect(lambda _c=False, n=nome: self.set_filter(n))
            fmenu.addAction(a)
        self.add_orientation_actions(im.addMenu("Girar / espelhar"))
        if len(self.frames) > 1 and self.render3d is None:
            mm = im.addMenu("Mosaico de cortes")
            for rc in (None, *self.MOSAICOS):
                a = QAction("Desligado" if rc is None else f"{rc[0]} × {rc[1]}", mm, checkable=True,
                            checked=self.mosaico == rc)
                a.triggered.connect(lambda _c=False, x=rc: self.set_mosaico(x))
                mm.addAction(a)
        im.addSeparator()
        hist = QAction("Histograma da imagem (ou da ROI)…", im)
        hist.triggered.connect(lambda: self.sig.histogram_requested.emit(self))
        hist.setEnabled(cinza)
        im.addAction(hist)
        im.addSeparator()
        for label, fn in (("Ajustar à janela", self.fit), ("Restaurar visualização", self.reset_view)):
            act = QAction(label, im)
            act.triggered.connect(fn)
            im.addAction(act)

        # ---- Quadro ▸
        qm = menu.addMenu("Quadro")
        if tab_f is not None and self.frames and self.render3d is None:
            outros = [v for v in tab_f._shown() if v is not self and v.frames and v.render3d is None]
            if outros:
                fm = qm.addMenu("Fundir este quadro sobre…")              # 0.99.64 (plano AW M6)
                for v in outros:
                    n = tab_f.viewports.index(v) + 1 if v in tab_f.viewports else 0
                    a_f = fm.addAction(f"Quadro {n}: {v.series_label or v.series_uid[-8:]}")
                    a_f.triggered.connect(lambda _=False, alvo=v: tab_f.fundir_quadro(self, alvo))
        refs = QAction("Linhas de corte das outras séries", qm, checkable=True,
                       checked=bool(getattr(self, "_refs_on", True)))
        refs.setToolTip("As linhas coloridas que mostram onde passam os cortes dos outros quadros")
        refs.toggled.connect(self.sig.reflines_toggled.emit)
        qm.addAction(refs)
        grp = QAction("Grupo de sincronização (trocar)", qm)
        grp.triggered.connect(lambda: self.sig.sync_group_requested.emit(self))
        qm.addAction(grp)
        if len(self.frames) > 1:
            a_cine = QAction("Cine liga/desliga", qm)
            a_cine.triggered.connect(self.toggle_cine)
            qm.addAction(a_cine)
        if self.annotations:
            nav = qm.addMenu("Medidas desta série")
            for i, text in self.annotation_summary()[:40]:
                act = nav.addAction(text)
                act.triggered.connect(lambda _=False, k=i: self.go_to(k))

        # ---- Anotações ▸ e ferramenta
        from ipe.ui.viewer import anotacoes as AN
        am = menu.addMenu("Anotações")
        atual = AN.nivel_atual(self.settings) if self.settings is not None else "completa"
        for chave, nome in AN.NIVEIS:
            a = QAction(nome, am, checkable=True, checked=chave == atual)
            a.triggered.connect(lambda _c=False, k=chave: self.sig.anotacoes_requested.emit(k))
            am.addAction(a)
        self.acoes_de_ferramenta_agrupadas(menu.addMenu("Ferramenta do botão esquerdo"))
        tags = QAction("Informações DICOM (tags)…", menu)
        tags.triggered.connect(self.show_tags)
        tags.setEnabled(bool(self.frames) and not self.anonymize)
        menu.addAction(tags)

        # ---- o que apaga, no fim
        menu.addSeparator()
        a_lim = QAction("Apagar medidas deste corte", menu)
        a_lim.triggered.connect(self.delete_frame_annotations)
        menu.addAction(a_lim)
        if self.frames and not self.frames[0].is_virtual and self.mpr_plane is None and self.render3d is None:
            tab = self._aba("apagar_imagem")
            if tab is not None and len(self.frames) > 1:       # 0.99.31 (onda A7)
                a_apagar = QAction("Apagar esta imagem…", menu)
                a_apagar.triggered.connect(lambda: tab.apagar_imagem(self))
                from ipe.auth import session as _S
                a_apagar.setEnabled(_S.can("delete"))
                menu.addAction(a_apagar)
        return menu

    def _acoes_da_medida(self, menu: QMenu, target) -> None:
        """O que se faz com a medida debaixo do mouse."""
        name = M.KINDS.get(target.kind, "medida")
        a_del = QAction(f"Apagar esta medida ({name})", menu)
        a_del.triggered.connect(lambda: self.delete_annotation(target))
        menu.addAction(a_del)
        if target.kind in ("text", "arrow"):
            a_txt = QAction("Editar texto…", menu)
            a_txt.triggered.connect(lambda: self.edit_text(target))
            menu.addAction(a_txt)
        if target.kind in RASCUNHAVEIS and target.frame_key[0] and not (target.meta or {}).get("lesion"):
            a_ras = QAction("Rascunho (não vai ao SR, ao laudo, à planilha nem ao PACS)", menu)
            a_ras.setCheckable(True)
            a_ras.setChecked(M.e_rascunho(target))
            a_ras.toggled.connect(lambda on: self.marcar_rascunho(target, on))
            menu.addAction(a_ras)
        if target.kind in ("line", "ellipse", "rect", "polygon", "tic", "seg") and target.frame_key[0] \
                and not M.e_rascunho(target):
            lid = target.meta.get("lesion") if target.meta else None
            a_les = QAction("Ligar a uma lesão (acompanhamento)…" if lid is None
                            else "Trocar / desligar a lesão…", menu)
            a_les.triggered.connect(lambda: self.sig.lesion_requested.emit(self, target))
            menu.addAction(a_les)
        if target.kind in M.ROI_KINDS and target.frame_key[0]:
            if (target.meta or {}).get("referencia"):
                a_ref = QAction("Deixar de ser a ROI de referência", menu)
                a_ref.triggered.connect(lambda: self.marcar_referencia(None))
            else:
                a_ref = QAction("Usar como ROI de referência (as outras mostram % dela)", menu)
                a_ref.triggered.connect(lambda: self.marcar_referencia(target))
            menu.addAction(a_ref)
        if target.kind in M.ROI_KINDS and self.plane() is not None and target.frame_key == self.frame_key() \
                and not (target.meta or {}).get("contralateral_de"):
            a_esp = QAction("Espelhar no outro lado (razão lesão / contralateral)", menu)
            a_esp.triggered.connect(lambda: self.espelhar_roi(target))
            menu.addAction(a_esp)
        if target.kind in M.ROI_KINDS and self.plane() is not None:
            a_cl = QAction("Clonar esta ROI nos outros quadros (mesma posição no paciente)", menu)
            a_cl.triggered.connect(lambda: self.sig.clone_roi_requested.emit(self, target))
            menu.addAction(a_cl)
        if target.kind in ("line", "polyline") and self._img is not None and not self._img.is_color:
            a_perf = QAction("Perfil de intensidade…", menu)          # 0.99.31 (onda A4)
            a_perf.triggered.connect(lambda: self.abrir_perfil(target))
            menu.addAction(a_perf)
        if target.kind == "tic":
            a_tic = QAction("Mostrar curva tempo-intensidade…", menu)
            a_tic.triggered.connect(lambda: self.sig.tic_requested.emit(self, target))
            menu.addAction(a_tic)

    def _menu_birads(self, menu: QMenu, tab_f, ip_m) -> None:
        """0.99.64 (PV 20): achado BI-RADS por marcadores."""
        mm = menu.addMenu("Achado BI-RADS aqui")
        a_novo = mm.addAction("Novo achado")
        a_novo.triggered.connect(lambda: tab_f.marcar_achado_mama(self, (ip_m.x(), ip_m.y())))
        try:
            from ipe.ui.viewer import marcadores_mama as MMV
            marcas = MMV.marcas_do_exame(tab_f.repo, self.study_uid or tab_f.study_uid)
        except Exception:  # noqa: BLE001
            marcas = {}
        if marcas:
            mm.addSeparator()
            for n, ms in sorted(marcas.items()):
                vistas = "+".join(m.get("vista", "") for m in ms)
                a_n = mm.addAction(f"A{n} (já em {vistas})")
                a_n.triggered.connect(lambda _=False, k=n: tab_f.marcar_achado_mama(self, (ip_m.x(), ip_m.y()), k))
        mm.addSeparator()
        mm.addAction("Tabela dos achados marcados…").triggered.connect(lambda: tab_f.abrir_marcadores_mama())

    def _menu_numeracao_da_coluna(self, menu: QMenu, local_pos) -> None:
        if not any(getattr(o, "source", "") == "Coluna" and o.study_uid in ("", self.study_uid)
                   for o in (getattr(self, "overlays", None) or [])):
            return
        ponto = None
        if local_pos is not None and self._img is not None:
            try:
                u, v = self._img_pt(local_pos)
                ponto = self.pixel_to_patient(u, v)
            except Exception:  # noqa: BLE001
                ponto = None
        rm = menu.addMenu("Numeração da coluna")
        rm.setToolTip("Vértebra de transição, contagem deslocada: renumerar ou dizer qual vértebra é qual.")
        a_aj = QAction("Ajustar a numeração e a vértebra de transição…", rm)
        a_aj.triggered.connect(lambda _=False, p=ponto: self.sig.numeracao_requested.emit(self, p))
        rm.addAction(a_aj)
        rm.addSeparator()
        rm.addAction("Um nível para baixo (L4 vira L5)", lambda: self.sig.renumerar_requested.emit(self, 1))
        rm.addAction("Um nível para cima (L5 vira L4)", lambda: self.sig.renumerar_requested.emit(self, -1))

    def _menu_dsa(self, dm: QMenu) -> None:
        a = QAction("Ligada", dm, checkable=True, checked=bool(self.dsa.get("on")))
        a.triggered.connect(lambda on: self.set_dsa(on=on))
        dm.addAction(a)
        dm.addAction("Usar este quadro como máscara",
                     lambda: self.set_dsa(on=True, mask=self.index, avg=1))
        dm.addAction("Máscara = média dos 3 primeiros quadros",
                     lambda: self.set_dsa(on=True, mask=0, avg=3))
        dm.addSeparator()
        from ipe.imaging.dsa import MODES as _DSA_MODES
        for chave, rotulo in _DSA_MODES.items():
            a = QAction(rotulo, dm, checkable=True, checked=self.dsa.get("mode") == chave)
            a.triggered.connect(lambda _c=False, k=chave: self.set_dsa(mode=k))
            dm.addAction(a)
        a = QAction("Inverter (vasos escuros)", dm, checkable=True,
                    checked=bool(self.dsa.get("invert")))
        a.triggered.connect(lambda on: self.set_dsa(invert=on))
        dm.addAction(a)
        pm = dm.addMenu("Paisagem (anatomia na subtração)")
        atual = float(self.dsa.get("paisagem", 0.0) or 0.0)
        for f in self.PAISAGENS:
            a = QAction("Sem anatomia (subtração pura)" if f == 0 else f"{f * 100:.0f}% da anatomia", pm,
                        checkable=True, checked=abs(f - atual) < 1e-6)
            a.triggered.connect(lambda _c=False, ff=f: self.set_dsa(on=True, paisagem=ff))
            pm.addAction(a)
        dm.addSeparator()
        dm.addAction("Ajustar o deslocamento da máscara…", self.open_dsa_shift)

    def open_dsa_shift(self) -> None:
        """Janelinha com as setas para empurrar a máscara e tirar o fantasma do movimento."""
        from ipe.ui.viewer.dsa_shift import DsaShiftDialog
        DsaShiftDialog(self, self).show()

    def show_tags(self) -> None:
        if not self.frames:
            return
        from ipe.ui.dialogs import TagDialog
        TagDialog(self.frames[self.index].path, self, files_for=self._files_for_scope,
                  on_fixed=self._tags_fixed).exec()

    def _files_for_scope(self, escopo: str) -> list:
        """Arquivos que a correção de tags vai copiar: esta imagem, a série ou o exame inteiro."""
        from pathlib import Path as _Path
        if escopo == "image" or not self.series_uid:
            return [_Path(self.frames[self.index].path)]
        repo = getattr(self.window(), "repo", None)
        if repo is None:
            return [_Path(f.path) for f in self.frames]
        if escopo == "series":
            return [_Path(i["path"]) for i in repo.instances_for_series(self.series_uid)]
        arquivos = []
        for se in repo.series_for_study(self.study_uid or ""):
            arquivos += [_Path(i["path"]) for i in repo.instances_for_series(se.series_uid)]
        return arquivos or [_Path(f.path) for f in self.frames]

    def _tags_fixed(self, arquivos) -> None:
        janela = self.window()
        importar = getattr(janela, "import_fixed_tags", None)
        if importar is not None:
            importar(arquivos)
