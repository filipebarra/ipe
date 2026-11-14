"""Mamografia e protocolos em etapas no visualizador (mixin do ViewerTab, separado do `viewer_tab.py` na 0.100.41).

Aqui ficam: os protocolos de exibição em etapas (passar, gravar a tela como etapa), o modo mamografia (etapas,
quadrantes, enquadre, sincronia entre as mamas, tomossíntese e espessura, contraste/CEM, cortes-chave, marcadores,
densidade) e o implante (as cópias sem silicone).

Os métodos continuam sendo do ViewerTab (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer

from ipe.imaging.volume import MPRPlane
from ipe.ui.viewer.viewport import Viewport
# LAYOUTS e as tabelas de ferramentas moram na barra (0.100.39); outros módulos ainda os importam daqui
from ipe.ui.viewer.barra import BarraMixin, LAYOUTS, MEASURE_TOOLS, SLAB_CHOICES, TOOL_ICONS, TOOL_SHORT  # noqa: F401

log = logging.getLogger("ipe.ui.viewer.viewer_tab")      # o mesmo registro de antes da separação


class MamografiaMixin:
    """MamografiaMixin: métodos do ViewerTab separados (mesmos nomes)."""

    # ================================================================ mamografia
    def _apply_protocolo_etapas(self, mods: set) -> bool:
        """Protocolo de exibição com etapas (0.88): abre na etapa 1 — nesta tela, ou no pedaço dela
        que cabe a este monitor quando o exame foi repartido."""
        from ipe.ui.viewer import etapas as E
        proto = E.achar(self.settings, mods, self.study_info.get("description", ""))
        if proto is None:
            return False
        try:
            return E.iniciar(self, proto, self.monitor_idx, self.mg_telas)
        except Exception:  # noqa: BLE001
            log.exception("protocolo com etapas %r", proto.get("name"))
            self.exib = None
            return False

    def etapa_passo(self, d: int = 1) -> None:
        from ipe.ui.viewer import etapas as E
        E.passo(self, d)

    def gravar_tela_como_etapa(self) -> None:
        """Pergunta em que protocolo e com que nome, e grava a tela como etapa."""
        from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
                                       QRadioButton)

        from ipe.ui.viewer import etapas as E
        from ipe.ui.viewer import hanging as H
        etapa = E.gravar_tela(self)
        mods = sorted({s.modality for s in self.series if s.study_uid == self.study_uid and s.modality})
        mod = next((m for m in mods if m not in ("SR", "PR", "KO", "SEG")), mods[0] if mods else "")
        desc = self.study_info.get("description", "") or ""
        dlg = QDialog(self)
        dlg.setWindowTitle("Gravar a tela como etapa")
        proto = QComboBox()
        novo = f"{mod} — {desc}".strip(" —") or "Novo protocolo"
        atual = self.exib.nome if self.exib is not None else ""
        for p in H.protocols(self.settings):
            if p.get("modality", "").upper() == mod.upper():
                proto.addItem(p.get("name", ""), p.get("name", ""))
        proto.addItem(f"Novo protocolo: {novo}", "__novo__")
        proto.setCurrentIndex(max(0, proto.findData(atual)))
        nome = QLineEdit(f"Etapa {len(self.exib.steps) + 1}" if self.exib is not None else "Etapa 1")
        acrescentar = QRadioButton("Acrescentar como etapa nova")
        acrescentar.setChecked(True)
        substituir = QRadioButton("Substituir a etapa que está na tela")
        substituir.setEnabled(self.exib is not None)
        f = QFormLayout(dlg)
        f.addRow("Protocolo:", proto)
        f.addRow("Nome da etapa:", nome)
        f.addRow(acrescentar)
        f.addRow(substituir)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        self._dlg_gravar = dlg
        if not dlg.exec():
            return
        etapa["name"] = nome.text().strip() or "Etapa"
        alvo = proto.currentData()
        nome_proto = novo if alvo == "__novo__" else alvo
        trocar = self.exib.indice if (substituir.isChecked() and self.exib is not None
                                      and self.exib.nome == nome_proto) else None
        gravado = E.salvar_etapa(self.settings, etapa, nome_proto, mod, desc if alvo == "__novo__" else "",
                                 trocar)
        indice = trocar if trocar is not None else len(gravado["steps"]) - 1
        self.exib = E.Sessao(gravado, self.monitor_idx, self.mg_telas)
        self.exib.indice = indice
        E.sincronizar_barra(self)
        self.status_message.emit(f"Etapa “{etapa['name']}” gravada em “{nome_proto}” "
                                 f"({len(gravado['steps'])} etapa(s)).")

    def editar_protocolos(self) -> None:
        from ipe.ui.viewer import etapas as E
        from ipe.ui.viewer import hanging as H
        from ipe.ui.viewer.protocolos_editor import ProtocolosDialog
        if not ProtocolosDialog(self.settings, self).exec() or self.exib is None:
            return
        p = next((x for x in H.protocols(self.settings) if x.get("name") == self.exib.nome), None)
        if p is None or not H.tem_etapas(p):
            E.encerrar(self)
            return
        i = self.exib.indice
        self.exib = E.Sessao(p, self.monitor_idx, self.mg_telas)
        E.aplicar_etapa(self, min(i, len(self.exib.steps) - 1), propagar=False)

    def plano_no_quadro(self, vp: Viewport, uid: str, nome: str, frames: list | None = None,
                        chave: str | None = None, rotulo: str = "") -> bool:
        """Reconstrói o plano `nome` da série no quadro, **sem perguntar nada** (é o protocolo que
        pede, ao abrir o exame). Volume acima do limite de memória fica de fora, com aviso.
        `frames`/`chave`: de uma fase da dinâmica (0.90)."""
        vol = self._volume_for(vp, uid, perguntar=False, frames=frames, chave=chave)
        if vol is None:
            self.status_message.emit(f"Reconstrução {nome}: o volume desta série não coube no limite de "
                                     "memória (Preferências ▸ Desempenho) ou não forma volume.")
            return False
        plane = next((MPRPlane(vol, ax) for ax in (0, 1, 2) if MPRPlane(vol, ax).name == nome), None)
        if plane is None:
            return False
        center = None
        if vp._img is not None:
            h, w = vp._img.pixels.shape[:2]
            center = vp.pixel_to_patient(w / 2, h / 2)
        if center is None:
            center = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        width, level, win_set = vp.state.width, vp.state.level, vp.state.window_set
        vp.mpr_plane = plane
        vp.study_uid = study_uid
        vp.modality = s.modality if s else ""
        vp.key_frames = self.key_set
        vp.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), rotulo or f"{plane.name} (reconstrução)",
                      self.study_infos.get(study_uid, self.study_info), start_index=plane.index_for_point(center))
        if win_set:
            vp.set_window(width, level, emit=False)
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        return True

    def _apply_mg_protocol(self) -> bool:
        from ipe.imaging.mammo import find_mg_protocol
        proto = find_mg_protocol(self.settings, self.study_info.get("description", ""))
        if proto is None:
            log.info("mamografia: nenhum protocolo combina com %r",
                     self.study_info.get("description", ""))
            return False
        try:
            if self.start_mg(proto):
                return True
            log.info("mamografia: protocolo %r não subiu (sem imagens com lado reconhecido)",
                     proto.get("name"))
            return False
        except Exception as e:  # noqa: BLE001
            log.warning("protocolo de mamografia falhou: %s", e)
            self.mg_session = None
            return False

    def start_mg(self, proto: dict, propagar: bool = True) -> bool:
        """Levanta o modo mamografia com este protocolo — e nos outros monitores do conjunto.

        Os monitores são uma estação só: trocar de protocolo numa tela troca em todas, senão o
        arranjo deixa de ser um arranjo.
        """
        from ipe.ui.viewer.mammo_view import MgSession
        s = MgSession(self, proto)
        if not s.has_images():
            return False
        self.mg_session = s
        self.hanging_name = proto.get("name", "")
        s.apply_step(0)
        if propagar:
            for t in self.irmaos():
                t.start_mg(proto, propagar=False)
        return True

    def mg_step(self, i: int, propagar: bool = True) -> None:
        """Vai para a etapa `i` — **em todos os monitores do conjunto**, ao mesmo tempo."""
        if self.mg_session is None:
            return
        self.mg_session.apply_step(i)
        self._sync_mg_bar()
        if propagar:
            for t in self.irmaos():
                if t.mg_session is not None:
                    t.mg_step(i, propagar=False)

    def mg_next(self, d: int = 1) -> None:
        if self.mg_session is None and getattr(self, "exib", None) is not None:
            self.etapa_passo(d)                       # 0.88: protocolo com etapas de TC, RM…
            return
        if self.mg_session is None:
            from ipe.imaging.mammo import find_mg_protocol
            p = find_mg_protocol(self.settings, self.study_info.get("description", ""))
            if p is not None and self.start_mg(p):
                return
            # Desde a 0.65 quem chama isto são as setas ← →. Num exame que não é mamografia a
            # seta não tem o que fazer, e avisar a cada toque seria ruído: o aviso fica para
            # quando o exame **é** MG e o que falta é o protocolo.
            if "MG" in (self.study_info.get("modalities") or ""):
                self.status_message.emit("Sem protocolo de mamografia para este exame.")
            return
        self.mg_step(self.mg_session.step + d)

    def fase_passo(self, d: int = 1) -> None:
        """Próxima/anterior fase da dinâmica no quadro ativo (as setas deixaram de fazer isso)."""
        vp = self.active
        if vp is None or not getattr(vp, "phases", None):
            self.status_message.emit("Este quadro não tem fases: não é uma dinâmica.")
            return
        vp.set_phase(vp.phase + d, wrap=True)

    def close_mg(self) -> None:
        self.mg_session = None
        for v in self.viewports:
            v.mg_cell = None
            v.align_edge = None
            v.update()
        self._sync_mg_bar()

    def _sync_mg_bar(self) -> None:
        if hasattr(self, "mg_bar"):
            self.mg_bar.sync()

    def mg_cells(self, vp):
        """O quadro e, no protocolo de mamografia com zoom junto, os outros quadros de mamografia."""
        if vp is None:
            return []
        out = [vp]
        s = self.mg_session
        if s is not None and s.proto.get("sync_zoom", True) and vp.mg_cell is not None:
            out += [v for v in self._shown() if v is not vp and v.mg_cell is not None and v.frames]
        return out

    def mg_quadrant(self, vp, idx: int) -> None:
        """Zoom no quadrante da mama (posterior/anterior × superior/inferior) e, no protocolo, nos outros
        quadros — cada um no seu próprio quadrante, já que a parede torácica troca de lado."""
        for t in self.mg_cells(vp):
            t.zoom_to_anat_quadrant(idx)
            t.quad_idx = idx

    def _enquadre_pendente(self, _vp=None) -> None:
        """Um quadro mudou de tamanho: refaz o enquadramento da mamografia, **do conjunto**.

        Junta os pedidos num disparo só (a montagem do layout redimensiona todos os quadros, um
        atrás do outro) e refaz o grupo inteiro, para as duas mamas continuarem na mesma escala.
        """
        t = getattr(self, "_timer_enquadre", None)
        if t is None:
            t = self._timer_enquadre = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(50)
            t.timeout.connect(self._refazer_enquadre)
        t.start()

    def _refazer_enquadre(self) -> None:
        s = self.mg_session
        if s is None:
            for vp in self.viewports:
                lock = getattr(vp, "anat_lock", None)
                if lock and lock[0] == "mama":
                    vp.enquadrar_na_mama(None, lock[2])
            return
        s.enquadrar(so_pendentes=True)

    def mg_enquadrar(self) -> None:
        """Reenquadra a mamografia da tela (Alt+Q / botão "Mama no quadro").

        O protocolo já enquadra ao abrir cada etapa; isto é o modo manual de reserva, para depois
        de mexer no zoom à mão — e funciona também sem protocolo, quadro por quadro.
        """
        s = self.mg_session
        if s is not None:
            modo = s.enquadrar()
            from ipe.imaging import mammo as M
            self.status_message.emit(f"Enquadrado: {M.ENQUADRES.get(modo, modo)}")
            return
        feitos = 0
        for vp in self.viewports:
            if vp._img is not None and (vp.modality or "").upper() == "MG" and vp.enquadrar_na_mama():
                feitos += 1
        if feitos:
            self.status_message.emit(f"Mama enquadrada em {feitos} quadro(s).")
        else:
            self.status_message.emit("Não achei a mama nos quadros desta tela.")

    def mg_quadrant_cycle(self, vp, d: int = 1) -> None:
        """Cada clique vai para o próximo: posterior+superior → posterior+inferior → imagem inteira."""
        from ipe.ui.viewer.mammo_view import QUAD_NAMES
        if vp is None or vp._img is None:
            return
        n = len(QUAD_NAMES)
        cur = vp.quad_idx if vp.state.zoom > 1.05 else -1
        new = (cur + 1 + d) % (n + 1) - 1
        self.mg_quadrant(vp, new)
        self.status_message.emit("Zoom: imagem inteira" if new < 0
                                 else f"Zoom: quadrante {QUAD_NAMES[new]}")

    def mg_sync_view(self, vp, kind: str) -> None:
        """Zoom/pan num quadro de mamografia: com o botão de sincronia **Zoom e pan** ligado, os outros
        mostram o mesmo lugar da mama (espelhado na outra mama, e valendo para 2D, tomossíntese e
        recombinada). Desligado, cada quadro anda sozinho — como nos outros exames (0.97.1). A opção
        do protocolo ("Zoom por quadrante em todos os quadros juntos") vale só para o zoom por
        quadrante (Q)."""
        if kind not in ("zoom", "pan") or vp is None or vp.mg_cell is None:
            return
        if self.mg_session is None or not self.hub.sync_zoom or getattr(self, "_mg_syncing", False):
            return
        ponto = vp.anat_center()
        if ponto is None:
            return
        self._mg_syncing = True
        try:
            outros = [t for t in self.hub.viewports(self) if t is not vp and t.mg_cell is not None and t.frames]
            for t in outros:
                if t._img is None:
                    continue
                t.show_anat(ponto[0], ponto[1], vp.state.zoom,
                            lock=getattr(vp, "anat_lock", None) is not None)
                t.quad_idx = vp.quad_idx
        finally:
            self._mg_syncing = False

    def mg_toggle_tomo(self) -> None:
        vp = self.active
        if self.mg_session is None or vp is None or getattr(vp, "mg_spec", None) is None:
            self.status_message.emit("2D / tomo: só nos quadros do protocolo de mamografia.")
            return
        self.mg_session.toggle_tomo(vp)

    def mg_toggle_cem(self) -> None:
        vp = self.active
        if self.mg_session is None or vp is None or getattr(vp, "mg_spec", None) is None:
            self.status_message.emit("Baixa energia ⇄ recombinada: só nos quadros do protocolo de mamografia.")
            return
        self.mg_session.toggle_rec(vp)

    def mg_set_inverter_mama(self, on: bool) -> int:
        """PV 17: inverte só a mama (fundo preto) nos quadros de mamografia (ou no ativo, fora do protocolo)."""
        self.mg_inverter_mama = bool(on)
        a = getattr(self.mg_bar, "a_inv", None)
        if a is not None and a.isChecked() != bool(on):
            a.blockSignals(True)
            a.setChecked(bool(on))
            a.blockSignals(False)
        alvos = [v for v in self._shown() if v.frames and (v.mg_cell is not None or (v.modality or "").upper() == "MG")]
        if not alvos and self.active is not None:
            alvos = [self.active]
        achou = sum(1 for v in alvos if v.set_inverter_mama(on))
        if on and achou < len(alvos):
            self.status_message.emit(f"Não achei a mama em {len(alvos) - achou} quadro(s): ficaram como estavam.")
        return achou

    def mg_corte_chave(self) -> bool:
        """PV 18: o corte da tomo (ou a imagem) do quadro ativo como imagem-chave; diz qual corte e a espessura."""
        vp = self.active
        f = vp.current_frame() if vp is not None else None
        if f is None:
            return False
        self.toggle_key_image()
        on = (f.sop_uid, f.frame_index) in self.key_set
        rng = getattr(vp, "tomo_range", None)
        if on and rng and rng[0] <= vp.index < rng[1]:
            k, n = vp.index - rng[0] + 1, rng[1] - rng[0]
            slab = int(getattr(vp, "tomo_slab", 1) or 1)
            extra = f", espessura de {slab} cortes" if slab > 1 else ""
            self.status_message.emit(f"Corte {k} de {n} da tomossíntese marcado como imagem-chave ★{extra}.")
        return on

    def mg_proximo_chave(self, d: int = 1) -> bool:
        """Vai ao próximo (d = 1) ou anterior (d = −1) corte marcado ★ no quadro ativo — a tomo tem dezenas de
        cortes, e procurar a estrela rolando é perder tempo."""
        vp = self.active
        if vp is None or not vp.frames:
            return False
        marcados = [i for i, f in enumerate(vp.frames) if (f.sop_uid, f.frame_index) in self.key_set]
        if not marcados:
            self.status_message.emit("Nenhum corte marcado ★ neste quadro.")
            return False
        alvo = next((i for i in marcados if i > vp.index), marcados[0]) if d > 0 else \
            next((i for i in reversed(marcados) if i < vp.index), marcados[-1])
        vp.go_to(alvo)
        rng = getattr(vp, "tomo_range", None)
        if rng and rng[0] <= alvo < rng[1]:
            self.status_message.emit(f"Corte ★ {alvo - rng[0] + 1} de {rng[1] - rng[0]}.")
        return True

    def marcar_achado_mama(self, vp, ip, numero: int | None = None):
        """0.99.64 (PV 20): marca o achado no ponto, para a tabela e o laudo BI-RADS."""
        from ipe.ui.viewer import marcadores_mama as MMV
        ann = MMV.marcar(self, vp, ip, numero)
        dlg = getattr(self, "_marcadores_dlg", None)
        if ann is not None and dlg is not None and dlg.isVisible():
            dlg.recarregar()
        return ann

    def abrir_marcadores_mama(self):
        from ipe.ui.viewer.marcadores_mama import MarcadoresDialog
        vp = self.active
        d = MarcadoresDialog(self, (vp.study_uid if vp is not None and vp.study_uid else None) or self.study_uid)
        self._marcadores_dlg = d
        d.show()
        return d

    def mg_densidade(self) -> None:
        """Densidade das imagens que estão na tela. A janela lê os quadros visíveis desta aba."""
        from ipe.ui.densidade_dialog import DensidadeDialog
        DensidadeDialog(self, self).exec()

    def mg_set_implant(self, on: bool) -> None:
        """Implante "apagado" em todos os quadros de mamografia (ou no ativo, fora do protocolo)."""
        self.mg_implant = on
        a = getattr(self.mg_bar, "a_implant", None)
        if a is not None and a.isChecked() != on:
            a.blockSignals(True)
            a.setChecked(on)
            a.blockSignals(False)
        targets = [v for v in self._shown() if v.frames and (v.mg_cell is not None or (v.modality or "") == "MG")]
        if not targets and self.active is not None:
            targets = [self.active]
        for v in targets:
            v.set_implant_mask(on)
        if on:
            self.salvar_implante([v for v in targets if v.implant_found])
            found = sum(1 for v in targets if v.implant_found)
            motivos = [v.implant_motivo for v in targets if not v.implant_found and getattr(v, "implant_motivo", "")]
            if found and motivos and found + len(motivos) == len(targets):
                self.status_message.emit(f"Implante corrigido em {found} quadro(s); nos outros {len(motivos)} não "
                                         f"procurei: {motivos[0]}.")
            elif not found and motivos and len(motivos) == len(targets):
                self.status_message.emit(f"Não procurei o implante: {motivos[0]}. Se houver prótese, clique com "
                                         "o botão direito dentro do silicone → “Achar o implante a partir daqui”.")
            elif found == len(targets):
                self.status_message.emit(f"Implante corrigido em {found} quadro(s).")
            elif found:
                self.status_message.emit(
                    f"Implante corrigido em {found} de {len(targets)} quadro(s). Nos outros, clique com o "
                    "botão direito dentro do silicone → “Achar o implante a partir daqui”.")
            else:
                self.status_message.emit(
                    "Não achei a prótese sozinho. Clique com o botão direito dentro do silicone → "
                    "“Achar o implante a partir daqui”.")
        else:
            self.status_message.emit("Implante mostrado como veio do aparelho.")

    def _implant_changed(self, vp) -> None:
        """Alguém apagou (ou mostrou) o implante num quadro pelo botão direito."""
        self.mg_implant = bool(vp.implant_mask)
        a = getattr(self.mg_bar, "a_implant", None)
        if a is not None and a.isChecked() != self.mg_implant:
            a.blockSignals(True)
            a.setChecked(self.mg_implant)
            a.blockSignals(False)
        if vp.implant_mask:
            self.status_message.emit("Implante corrigido neste quadro." if vp.implant_found
                                     else "Não consegui separar a prótese a partir desse ponto — "
                                          "tente um ponto mais no meio do silicone.")
            if vp.implant_found:
                self.salvar_implante([vp])


    def salvar_implante(self, vps: list) -> None:
        """Implante apagado na tela: confere se a imagem sem silicone já está no banco e, se não
        estiver, grava (0.97.1). Grava o que está na tela — com a prótese achada aqui, inclusive
        a do clique "a partir daqui". Em segundo plano; a tela não espera."""
        from ipe.automation import implante as IMP
        storage = getattr(self, "storage_root", None)
        if storage is None or self.repo is None or not IMP.config(self.settings, IMP.CHAVE_SALVAR_BOTAO):
            return
        pedidos = []
        for v in vps:
            f = v.current_frame()
            if f is None or f.is_virtual or not f.path or v.in_tomo() or not v.study_uid:
                continue
            info = v._implant_info(so_cache=True)
            if info is None:
                continue
            pedidos.append((v.study_uid, f.path, f.sop_uid, info[2].copy(), f.series_uid))
        if not pedidos:
            return
        repo, db = self.repo, self.repo.db

        def trabalho():
            return [IMP.salvar_uma(repo, db, storage, *p[:4]) for p in pedidos]

        def pronto(res, err) -> None:
            if err is not None:
                log.warning("salvar a imagem sem implante: %s", err)
                self.status_message.emit(f"Não consegui salvar a imagem sem o silicone: {err}")
                return
            novas = sum(1 for r in res if r == "salva")
            ja = sum(1 for r in res if r == "já estava salva")
            if novas:
                from ipe.automation import destinos as DEST
                por_estudo: dict = {}
                for p, r in zip(pedidos, res):
                    if r == "salva":
                        por_estudo.setdefault(p[0], set()).add(IMP.serie_da_copia(p[4]))
                for est, series in por_estudo.items():
                    DEST.enviar(self.net, self.repo, est, sorted(series),
                                IMP.config(self.settings, IMP.CHAVE_DESTINOS), "Sem implante")
            if novas:
                self.status_message.emit(f"Imagem sem o silicone salva no banco ({novas}"
                                         + (f"; {ja} já estava(m) salva(s)" if ja else "") + ").")
            elif ja:
                self.status_message.emit("A imagem sem o silicone já estava salva no banco.")
            self.implante_salvo.emit(novas)

        if self.net is not None:
            self.net.run_async(trabalho, pronto)
        else:
            try:
                pronto(trabalho(), None)
            except Exception as e:  # noqa: BLE001
                pronto(None, e)

    def mg_set_slab(self, n: int | None = None, mode: str | None = None) -> None:
        """Espessura da tomossíntese (em cortes). n = -1: próxima da lista; None: mantém (troca só o modo)."""
        from ipe.ui.viewer.mammo_view import SLAB_STEPS
        cur = getattr(self, "mg_slab", 1)
        if n == -1:
            n = SLAB_STEPS[(SLAB_STEPS.index(cur) + 1) % len(SLAB_STEPS)] if cur in SLAB_STEPS else SLAB_STEPS[0]
        elif n is None:
            n = cur
        self.mg_slab = n
        if mode:
            self.mg_slab_mode = mode
        mode = getattr(self, "mg_slab_mode", "mip")
        tomo = [v for v in self._shown() if getattr(v, "mg_tomo", False)]
        if not tomo:
            self.status_message.emit("Espessura: só nos quadros com tomossíntese (role até os cortes da tomo).")
        for v in tomo:
            v.set_tomo_slab(n, mode)
        btn = getattr(self.mg_bar, "slab_btn", None)
        if btn is not None:
            btn.setText("Espessura: fina ▾" if n == 1 else f"Espessura: {n} cortes {'MIP' if mode == 'mip' else 'média'} ▾")
        if tomo:
            self.status_message.emit("Tomossíntese: corte fino." if n == 1 else
                                     f"Tomossíntese: espessura de {n} cortes ({'MIP' if mode == 'mip' else 'média'}).")


    def edit_mg_protocols(self) -> None:
        from ipe.ui.viewer.mammo_view import MgProtocolsDialog
        if MgProtocolsDialog(self.settings, self).exec() and self.mg_session is not None:
            from ipe.imaging.mammo import mg_protocols
            name = self.mg_session.proto.get("name")
            p = next((x for x in mg_protocols(self.settings) if x.get("name") == name), None)
            if p is not None:
                step = self.mg_session.step
                self.mg_session.proto = p
                self.mg_session.apply_step(min(step, max(0, len(self.mg_session.steps) - 1)))
            else:
                self._sync_mg_bar()
