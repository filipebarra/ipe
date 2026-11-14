"""Ferramentas de IA e estruturas no visualizador (mixin do ViewerTab, separado do `viewer_tab.py` na 0.100.41).

Aqui ficam: a numeração da coluna, mandar texto ao laudo, o painel Estruturas e o pincel, a difusão, os achados para
revisar, os nódulos, a composição corporal (biometria), a caixa de IA (MedSAM2), as ferramentas de IA por tipo, o fígado
na RM, as tarefas de IA e a segmentação de órgãos.

Os métodos continuam sendo do ViewerTab (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtWidgets import (
    QMessageBox,
)

# LAYOUTS e as tabelas de ferramentas moram na barra (0.100.39); outros módulos ainda os importam daqui
from ipe.ui.viewer.barra import BarraMixin, LAYOUTS, MEASURE_TOOLS, SLAB_CHOICES, TOOL_ICONS, TOOL_SHORT  # noqa: F401

log = logging.getLogger("ipe.ui.viewer.viewer_tab")      # o mesmo registro de antes da separação


class IAMixin:
    """IAMixin: métodos do ViewerTab separados (mesmos nomes)."""

    def objetos_da_coluna(self, vp=None) -> list:
        estudo = getattr(vp, "study_uid", "") or self.study_uid
        return [o for o in self.overlay_objects
                if getattr(o, "source", "") == "Coluna" and o.study_uid in ("", estudo)]

    def guardar_coluna(self, o, estudo: str = "", conferido: bool = False) -> None:
        """Depois de renumerar ou ajustar: o SEG guardado (reabrir vem certo), a tabela das medidas e,
        se ele conferiu, a numeração do exame (aviso no próximo exame do paciente)."""
        from ipe.ai import coluna as COL
        caminho = getattr(o, "caminho", "")
        estudo = estudo or o.study_uid or self.study_uid
        if caminho:
            try:
                COL.salvar_no_seg(caminho, o)
                storage = getattr(self, "storage_root", None)
                if storage is not None and COL.config(self.settings, COL.CHAVE_MEDIR) and \
                        COL.tem_tabela(self.repo, estudo):
                    COL.gravar_tabela(self.repo, self.repo.db, storage, estudo, caminho, obj=o)
            except Exception:  # noqa: BLE001
                log.exception("guardar a numeração da coluna")
        if conferido:
            from ipe.auth import session as S
            try:
                quem = S.get().username or ""
            except Exception:  # noqa: BLE001
                quem = ""
            COL.guardar_conferencia(self.repo, estudo, o.numeracao, quem)

    def _coluna_mudou(self, o=None) -> None:
        """Refaz a tela depois de renumerar/ajustar — **em todas as abas e janelas** com este exame.

        0.99.23.1, relato dele: *"mudei a nomenclatura (L5 sacralizada) mas não mudou nada no viewer"*.
        Cada monitor tem a sua aba, com os seus objetos lidos do SEG; mudar o objeto da aba em que ele
        clicou deixava as outras telas com o nome antigo. E um objeto repetido na mesma aba (o mesmo SEG
        lido duas vezes) desenhava o rótulo velho por cima, porque o primeiro rótulo do lugar ganha."""
        from ipe.ai import coluna as COL
        caminho = getattr(o, "caminho", "") if o is not None else ""
        abas = [self]
        from PySide6.QtWidgets import QApplication
        # a janela principal **desta** aba (com várias janelas vivas — testes, outra sessão —, a primeira
        # da lista podia ser outra)
        for w in [self.window(), *QApplication.topLevelWidgets()]:
            f = getattr(w, "all_viewer_tabs", None)
            if not callable(f):
                continue
            try:
                todas = list(f())
            except Exception:  # noqa: BLE001
                log.exception("abas abertas")
                continue
            if self in todas or w is self.window():
                abas += [t for t in todas if t is not self]
                break
        for t in abas:
            objs = getattr(t, "overlay_objects", None)
            if objs is None:
                continue
            if caminho:
                novo = []
                for x in objs:
                    if getattr(x, "source", "") == "Coluna" and getattr(x, "caminho", "") == caminho:
                        if t is self:
                            if x is o:
                                novo.append(x)
                            continue                 # repetido nesta aba: sai, fica o que mudou
                        try:
                            x = COL.objeto_do_seg(caminho, x.study_uid)
                            x.enabled = True
                        except Exception:  # noqa: BLE001
                            log.exception("reler a coluna em outra aba")
                    novo.append(x)
                if t is self and o not in novo:
                    novo.append(o)
                objs[:] = novo
            if hasattr(t, "_apply_overlays"):
                t._apply_overlays()
            for v in getattr(t, "viewports", []):
                v.update()

    def renumerar_coluna(self, vp, passo: int) -> int:
        """Níveis da coluna ±1 (0.99.2): todos os nomes andam um nível, na tela e no SEG guardado — ao
        reabrir o exame já vem certo. Devolve quantos objetos mudaram. 0.99.23: recusa, dizendo, quando
        um nível sairia da coluna (antes parava em S1 e dava duas S1)."""
        from ipe.ai import coluna as COL
        n = 0
        vistos, mudados = set(), []
        for o in self.objetos_da_coluna(vp):
            chave = getattr(o, "caminho", "") or id(o)
            if chave in vistos:
                continue                              # o mesmo SEG lido duas vezes: renumera um só
            vistos.add(chave)
            try:
                COL.renumerar(o, passo)
            except COL.ForaDaColuna as e:
                self.status_message.emit(f"Não renumerei: {e}.")
                return 0
            self.guardar_coluna(o, getattr(vp, "study_uid", ""))
            mudados.append(o)
            n += 1
        for o in mudados:
            self._coluna_mudou(o)
        if n:
            self.status_message.emit("Níveis da coluna renumerados: " + ("um nível para baixo." if passo > 0
                                                                         else "um nível para cima."))
        return n

    def abrir_numeracao_coluna(self, vp, ponto=None):
        """Botão direito ▸ Numeração da coluna ▸ Ajustar… (0.99.23): a janela abre com a vértebra que
        estava sob o clique."""
        from ipe.ui.viewer.coluna_numeracao import NumeracaoDialog
        objs = self.objetos_da_coluna(vp)
        if not objs:
            self.status_message.emit("Esta aba não tem os níveis da coluna identificados.")
            return None
        o = objs[-1]
        clicada = None
        if ponto is not None:
            for mv in o.volumes:
                if "-" not in str(getattr(mv, "nivel", mv.label)) and mv.contem(ponto, folga=1):
                    clicada = getattr(mv, "nivel", None)
                    break
        dlg = NumeracaoDialog(self, o, clicada=clicada, repo=self.repo, study_uid=o.study_uid or self.study_uid)

        def aplicado():
            self.guardar_coluna(o, o.study_uid or self.study_uid, conferido=True)
            self._coluna_mudou(o)
            self.status_message.emit("Numeração da coluna conferida: " + __import__(
                "ipe.ai.coluna", fromlist=["descrever"]).descrever(o.numeracao) + ".")
        dlg.aplicado.connect(aplicado)
        dlg.laudo.connect(lambda txt: self.mandar_texto_ao_laudo(txt))
        dlg.show()
        self._numeracao_dlg = dlg
        return dlg

    def mandar_texto_ao_laudo(self, texto: str) -> None:
        ok = False
        try:
            ok = bool(hasattr(self, "append_to_report") and self.append_to_report(texto))
        except Exception:  # noqa: BLE001
            log.exception("mandar ao laudo")
        if not ok:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(texto)
            self.status_message.emit("Sem laudo aberto: a frase foi copiada.")

    def abrir_estruturas(self, vp=None):
        """O painel Estruturas (0.99.40): editar, organizar e gravar máscaras (SEG / RTSTRUCT)."""
        from ipe.ui.viewer.estruturas_painel import abrir
        return abrir(self, vp or self.active)

    def pincel_estruturas(self, vp, u: float, v: float, etapa: str) -> None:
        painel = getattr(self, "_estruturas", None)
        try:
            import shiboken6
            vivo = painel is not None and shiboken6.isValid(painel) and painel.isVisible()
        except Exception:  # noqa: BLE001
            vivo = painel is not None
        if not vivo:
            # 0.100.40: o pincel abre o painel sozinho (antes mandava procurar um menu "3D ▸ Estruturas" que não
            # existia com esse nome); a estrutura nova é criada pelo próprio painel no primeiro traço
            if etapa != "ini":
                return
            painel = self.abrir_estruturas(vp)
            if painel.grade is None:
                self.status_message.emit("Pincel: este quadro não tem uma série de cortes (TC, RM, PET); as "
                                         "estruturas são desenhadas sobre uma.")
                return
            self.status_message.emit("Pincel: painel Estruturas aberto; pintando numa estrutura nova.")
        painel.pincel(vp, u, v, etapa)

    def abrir_difusao(self):
        """O painel da difusão (0.99.37): ADC, DWI sintética e a tabela por ROI."""
        from ipe.ui.viewer.difusao_painel import abrir
        return abrir(self)

    def abrir_achados(self, achado_id: int | None = None):
        """Achados de IA (0.99.46): a lista revisável do exame."""
        from ipe.ui.viewer.achados_painel import abrir
        return abrir(self, achado_id if isinstance(achado_id, int) and not isinstance(achado_id, bool) else None)

    def _nodulos_do_ativo(self):
        return self.nodulos_automatico(self.active)

    def nodulos_automatico(self, vp=None, simular: bool = False):
        """Procura nódulos pulmonares na série do quadro (TotalSegmentator lung_nodules)."""
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if vp is None:
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="nodulos")

    def _composicao_do_ativo(self):
        return self.composicao_automatica(self.active)

    def composicao_automatica(self, vp=None, simular: bool = False, perguntar: bool | None = None):
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if vp is None:
            return None
        # 0.99.80: altura, peso e sexo antes da conta (do arquivo, para conferir ou digitar)
        if perguntar is None:
            perguntar = not simular
        if perguntar and not self.pedir_biometria(vp):
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="composicao")

    def pedir_biometria(self, vp=None, sempre: bool = False) -> bool:
        """A janela de altura e peso. False = cancelou. Com "perguntar sempre" desligado, só passa."""
        from ipe.ai import biometria as B
        from ipe.ai import composicao as CP
        from ipe.ui.biometria_dialog import BiometriaDialog
        perguntar = bool(CP.config(self.settings, CP.CHAVE_PERGUNTAR))
        if not perguntar and not sempre:
            return True
        vp = vp or self.active
        f = vp.current_frame() if vp is not None else None
        uid = (vp.study_uid if vp is not None else "") or self.study_uid
        valores = B.ler(self.repo, uid, getattr(f, "path", None))
        d = BiometriaDialog(valores, self, perguntar=perguntar)
        if d.exec() != BiometriaDialog.Accepted:
            return False
        v = d.valores()
        B.guardar(self.repo, uid, v["altura_m"], v["peso_kg"], v["sexo"])
        if d.perguntar() != perguntar and self.settings is not None:
            self.settings.set(CP.CHAVE_PERGUNTAR, d.perguntar())
            self.settings.save()
        return True

    def composicao_botao(self):
        try:
            tem = any(self.repo.achados(u, "composicao") for u in (getattr(self, "study_order", None) or [self.study_uid]))
        except Exception:  # noqa: BLE001
            tem = False
        if tem:
            return self.abrir_achados()
        return self.composicao_automatica(self.active)

    def caixa_ia(self, vp, u0: float, v0: float, u1: float, v1: float, simular: bool = False):
        """0.99.83: a caixa desenhada com "Segmentar pela caixa (IA)" vai ao MedSAM2; a máscara 3D volta na
        janela da Segmentação 3D (volume, eixos, SUV, ligar a uma lesão, gravar a SEG)."""
        from ipe.ai import medsam2 as MS
        from ipe.ui.segmentacao import Segmentacao
        if vp is None or vp.mpr_plane is not None or not vp.frames or vp.frames[0].is_virtual:
            QMessageBox.information(self, MS.TITULO, "Desenhe a caixa na série original (não na reconstrução).")
            return None
        uid = self._source_series(vp)
        vol = self._volume_for(vp, uid) if uid else None
        if vol is None:
            QMessageBox.information(self, MS.TITULO, "O volume desta série não foi montado.")
            return None
        cantos = [vp.pixel_to_patient(u, v) for u, v in ((u0, v0), (u1, v0), (u0, v1), (u1, v1))]
        if any(c is None for c in cantos):
            return None
        caixa = MS.caixa_no_volume(vol, cantos)
        if caixa is None:
            QMessageBox.information(self, MS.TITULO, "A caixa caiu fora do volume (ou ficou pequena demais).")
            return None
        ww, wl = float(vp.state.width or 0), float(vp.state.level or 0)
        janela = (wl - ww / 2, wl + ww / 2) if ww > 0 else (float(np.percentile(vol.data, 1)),
                                                             float(np.percentile(vol.data, 99)))
        storage = getattr(self, "storage_root", None)
        seg = Segmentacao(self, self.repo, self.settings, storage, vp.study_uid or self.study_uid, uid,
                          cache=self.cache, simular=simular, tipo="medsam2")
        seg.trabalho.tarefas_proprias = [MS.tarefa(caixa, janela)]
        seg.trabalho.vol_pronto = vol
        frame_key = vp.frame_key()
        uv = ((u0 + u1) / 2, (v0 + v1) / 2)

        def pronto(saida, msg):
            if not seg.janela_viva():
                return
            self.status_message.emit(msg)
            if saida is None or saida.get("medsam2") is None:
                QMessageBox.information(self, MS.TITULO, msg)
                return
            from ipe.ui.viewer.onco import SegmentDialog
            res = MS.resultado(vol, saida["medsam2"], caixa, vp.suv_factor, (vp.modality or ""))
            dlg = SegmentDialog(self, vp, vol, res.seed, uv, frame_key, pronto=res)
            self._seg_dialogs = [d for d in getattr(self, "_seg_dialogs", []) if d.isVisible()] + [dlg]
            dlg.show()
        seg.terminou.connect(pronto)
        seg.iniciar()
        return seg

    def ferramenta_ia(self, tipo: str, vp=None, simular: bool = False):
        """0.99.77: roda uma IA do contrato comum (enfisema, Genant…) na série do quadro."""
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if vp is None:
            return None
        if tipo == "carga_pet":                 # 0.99.88: os órgãos saem da TC do PET/CT, a conta é no PET
            from ipe.ai import carga_pet as CP
            serie, motivo = CP.escolher_serie(self.repo, vp.study_uid or self.study_uid, self.settings)
            if not serie:
                self.status_message.emit(f"Carga tumoral: {motivo}.")
                return None
            alvo = next((v for v in self.viewports if v.series_uid == serie and v.frames), None)
            if alvo is None:
                alvo = vp
                self.load_series_into(vp, serie)
            vp = alvo
        if tipo == "flames":                    # 0.100.25: roda no FLAIR do exame, esteja ou não no quadro
            from ipe.ai import flames as FL
            linha = self._series_row(getattr(vp, "series_uid", "") or "")
            if linha is None or not FL.e_flair(linha.description or ""):
                serie, motivo = FL.escolher_serie(self.repo, vp.study_uid or self.study_uid, self.settings)
                if not serie:
                    QMessageBox.information(self, FL.TITULO, f"Lesões no FLAIR: {motivo}.")
                    return None
                alvo = next((v for v in self.viewports if v.series_uid == serie and v.frames), None)
                if alvo is None:
                    alvo = vp
                    self.load_series_into(vp, serie)
                vp = alvo
        return self.segmentar_orgaos(vp, simular=simular, tipo=tipo)

    def ferramenta_ia_botao(self, tipo: str):
        """O botão: com achados desta IA no exame, abre a revisão; sem, roda."""
        try:
            tem = any(self.repo.achados(u, tipo) for u in (getattr(self, "study_order", None) or [self.study_uid]))
        except Exception:  # noqa: BLE001
            tem = False
        if tem:
            return self.abrir_achados()
        return self.ferramenta_ia(tipo, self.active)

    def _figado_rm_do_ativo(self):
        return self.figado_rm_automatico(self.active)

    def figado_rm_automatico(self, vp=None, simular: bool = False):
        """Fígado na RM (0.99.49): a IA roda na série anatômica escolhida pela regra (o fígado vem dela) e
        mede nos mapas do aparelho. O quadro ativo só decide o exame."""
        from ipe.ai import figado_rm as FR
        from ipe.core.i18n import tr
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if vp is None:
            return None
        uid = vp.study_uid or self.study_uid
        serie, motivo = FR.escolher_serie(self.repo, uid, self.settings)
        alvo = vp
        if serie and serie != vp.series_uid:
            alvo = next((v for v in self.viewports if v.series_uid == serie), None)
            if alvo is None:
                alvo = vp
                self.load_series_into(vp, serie)
        elif not serie:
            self.status_message.emit(tr(f"Fígado na RM: {motivo} — uso a série do quadro ativo."))
        return self.segmentar_orgaos(alvo, simular=simular, tipo="figado_rm")

    def figado_rm_botao(self):
        try:
            tem = any(self.repo.achados(u, "figado_rm") for u in (getattr(self, "study_order", None) or [self.study_uid]))
        except Exception:  # noqa: BLE001
            tem = False
        if tem:
            return self.abrir_achados()
        return self.figado_rm_automatico(self.active)

    def nodulos_botao(self):
        """O botão: com achados no exame, abre a lista; sem, procura na série do quadro ativo."""
        try:
            tem = any(self.repo.achados(u, "nodulos") for u in (getattr(self, "study_order", None) or [self.study_uid]))
        except Exception:  # noqa: BLE001
            tem = False
        if tem:
            return self.abrir_achados()
        return self.nodulos_automatico(self.active)

    def achados_mudaram(self) -> None:
        p = getattr(self, "achados_painel", None)
        if p is not None:
            try:
                p.recarregar()
            except RuntimeError:
                self.achados_painel = None

    def abrir_tarefas_ia(self):
        """A janela "Tarefas de IA" (0.99.32): uma só para o programa todo."""
        from ipe.ui.tarefas_ia import abrir
        return abrir(self.window())

    def segmentar_orgaos(self, vp, simular: bool = False, tipo: str = "abdome"):
        """Quadro ▸ botão direito ▸ Segmentar órgãos abdominais (0.98) ou Identificar vértebras e discos
        (tipo="coluna", 0.99.2): a série do quadro vai para o TotalSegmentator; ao terminar, o resultado
        entra nas sobreposições desta aba."""
        from ipe.ui.segmentacao import Segmentacao, carregar_na_aba
        f = vp.current_frame() if vp is not None else None
        storage = getattr(self, "storage_root", None)
        if f is None or not f.series_uid or storage is None:
            return None
        seg = Segmentacao(self, self.repo, self.settings, storage, vp.study_uid or self.study_uid,
                          f.series_uid, cache=self.cache, simular=simular, tipo=tipo)
        net, repo, settings = getattr(self, "net", None), self.repo, self.settings

        def pronto(saida, msg):
            if not seg.janela_viva():
                # 0.99.34: o exame foi fechado enquanto rodava. O resultado já está gravado no exame
                # (aparece ao abrir de novo); só falta mandar aos destinos de CAD/IA.
                if saida is not None and saida.get("ferramenta") and net is not None:
                    try:
                        from ipe.ai import ferramentas as FE
                        from ipe.automation import destinos as DEST
                        mod = FE.modulo(saida["ferramenta"])
                        DEST.enviar(net, repo, seg.trabalho.study_uid, saida.get("series"),
                                    mod.config(settings, mod.CHAVE_DESTINOS), mod.TITULO)
                    except Exception:  # noqa: BLE001
                        log.exception("enviar os achados aos destinos (exame fechado)")
                    return
                if saida is not None and tipo in ("abdome", "coluna") and net is not None:
                    try:
                        from ipe.ai import coluna as COL
                        from ipe.ai import totalseg as TS
                        from ipe.automation import destinos as DEST
                        destinos = (COL.config(settings, COL.CHAVE_DESTINOS) if tipo == "coluna"
                                    else TS.config(settings, TS.CHAVE_DESTINOS))
                        DEST.enviar(net, repo, seg.trabalho.study_uid, saida.get("series"), destinos,
                                    "Níveis da coluna" if tipo == "coluna" else "Órgãos abdominais")
                    except Exception:  # noqa: BLE001
                        log.exception("enviar a segmentação aos destinos (exame fechado)")
                return
            if saida is not None and tipo == "cefalometria":
                carregar_na_aba(self, saida)
                self.status_message.emit(msg)
                self.abrir_cefalometria(saida.get("cefalometria"), automatica=True)
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None and tipo == "linfonodos":
                carregar_na_aba(self, saida)
                from ipe.ai import linfonodos as LN
                self.overlay_objects[:] = [o for o in self.overlay_objects if o.source != LN.FONTE_OVERLAY]
                self.overlay_objects.append(saida["mapa"])
                self.marcos_linfonodais = saida["linfonodos"]
                if hasattr(self, "_apply_overlays"):
                    self._apply_overlays()
                self.status_message.emit(msg)
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None and saida.get("ferramenta") == "synthsr":   # 0.100.23: sai uma série, não achados
                self.recarregar_series()
                self.status_message.emit(msg.split("\n")[0])
                nova = saida.get("nova_serie")
                if nova and QMessageBox.question(
                        self, seg.titulo, msg + "\n\nMostrar a série nova no quadro ativo?") == QMessageBox.Yes:
                    alvo = self.active or vp
                    if alvo is not None:
                        self.load_series_into(alvo, nova)
                return
            if saida is not None and saida.get("ferramenta"):          # 0.99.46: IAs do contrato comum
                carregar_na_aba(self, saida)
                from ipe.ai import ferramentas as FE
                from ipe.automation import destinos as DEST
                mod = FE.modulo(saida["ferramenta"])
                if mod is not None and DEST.enviar(self.net, self.repo, seg.trabalho.study_uid, saida.get("series"),
                                                   mod.config(self.settings, mod.CHAVE_DESTINOS), mod.TITULO):
                    msg += " Enviado também aos destinos escolhidos em Configurações ▸ CAD/IA."
                self.status_message.emit(msg)
                self.abrir_achados()
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None and tipo == "neuro":
                carregar_na_aba(self, saida)
                self.status_message.emit(msg)
                self.abrir_neuro(saida.get("neuro"), automatica=True)
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None:
                carregar_na_aba(self, saida)
                from ipe.ai import coluna as COL
                from ipe.ai import totalseg as TS
                from ipe.automation import destinos as DEST
                destinos = (COL.config(self.settings, COL.CHAVE_DESTINOS) if tipo == "coluna"
                            else TS.config(self.settings, TS.CHAVE_DESTINOS))
                if DEST.enviar(self.net, self.repo, seg.trabalho.study_uid, saida.get("series"), destinos,
                               "Níveis da coluna" if tipo == "coluna" else "Órgãos abdominais"):
                    msg += " Enviada também aos destinos escolhidos em Preferências ▸ CAD/IA."
                self.status_message.emit(msg)
                QMessageBox.information(self, seg.titulo, msg)
            elif msg != "Segmentação cancelada.":
                QMessageBox.warning(self, seg.titulo, msg)
            else:
                self.status_message.emit(msg)
        seg.terminou.connect(pronto)
        seg.iniciar()
        return seg
