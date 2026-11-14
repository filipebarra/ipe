"""A aba Impressões da janela principal (mixin da MainWindow, separado do `main_window.py` na 0.100.42).

Aqui ficam: a fila de filmes que chegam pela impressora DICOM, abrir, imprimir de novo, mandar ao exame e as regras.

Os métodos continuam sendo da MainWindow (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMessageBox,
)

from ipe.ui.viewer.viewer_tab import ViewerTab

log = logging.getLogger("ipe.ui.main_window")      # o mesmo registro de antes da separação


class ImpressoesMixin:
    """ImpressoesMixin: métodos do ViewerTab separados (mesmos nomes)."""

    # ------------------------------------------------------------ impressões
    def show_prints(self):
        """Abre (ou traz para a frente) a lista de impressões."""
        try:
            return self._show_prints()
        except Exception as e:  # noqa: BLE001
            log.exception("abrindo a lista de impressões")
            QMessageBox.critical(self, "Impressões",
                                 f"Não consegui abrir a lista de impressões:\n{e}\n\n"
                                 "O erro completo está no arquivo de registro (Ajuda ▸ Registro).")
            return None

    def _show_prints(self):
        from ipe.ui.prints_tab import PrintsTab
        if self._prints is None:
            self._prints = PrintsTab(self.repo, self.settings, self.net, self)
            self._prints.open_study.connect(self.open_study)
            self._prints.open_film.connect(self._open_saved_film)
            self._prints.status_message.connect(lambda t: self.statusBar().showMessage(t, 8000))
            self._prints.settings_requested.connect(self.open_print_settings)
            self._prints.release_requested.connect(self.release_held_rows)
            self._prints.identified.connect(self._on_print_identified)
            self._prints.dashboard_requested.connect(self.show_film_dashboard)
        if self.tabs.indexOf(self._prints) < 0:
            self.tabs.addTab(self._prints, "Impressões")
        self._prints.refresh()
        self.tabs.setCurrentWidget(self._prints)
        return self._prints

    def show_film_dashboard(self):
        """Painel de filmes e impressões (0.77): % impressos, tempos, por modalidade e usuário."""
        from ipe.auth import session as S
        if self.meeting is not None or getattr(self, "_privacy_on", False):
            QMessageBox.information(self, "Painel de filmes", "O painel de filmes fica indisponível "
                                    "enquanto os dados do paciente estão ocultos (reunião / Ocultar).")
            return None
        if not S.require("print", self):
            return None
        from ipe.ui.film_dashboard import FilmDashboard
        d = getattr(self, "_film_dashboard", None)
        if d is None:
            d = self._film_dashboard = FilmDashboard(self.repo, self.settings, self)
            d.abrir_filme.connect(self._open_saved_film)
            d.abrir_exame.connect(self.open_study)
        else:
            d.carregar()
        d.show()
        d.raise_()
        d.activateWindow()
        return d

    def open_gsdf(self) -> None:
        """Calibração GSDF: a escala de cinza deste monitor, com os padrões para conferir."""
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.gsdf_dialog import GsdfDialog
        if GsdfDialog(self.settings, self).exec():
            for t in self.all_viewer_tabs():
                for v in t.viewports:
                    v._qimage_key = None
                    v.update()
            self.statusBar().showMessage("Calibração do monitor atualizada.", 6000)

    def open_print_settings(self) -> None:
        """Servidores de impressão, destinos, regras, modelos de folha e montagem automática."""
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.print_settings import PrintSettingsDialog
        PrintSettingsDialog(self.settings, self.net, self, repo=self.repo).exec()
        self._update_net_label()

    def _open_saved_film(self, film_id: int) -> None:
        self.dock_film()
        self.film_composer().load_film(int(film_id))

    def _on_print_received(self, row) -> None:
        """Chegou um filme de alguma modalidade."""
        from ipe.printing import origins as O
        origem = O.job_origin(self.settings, row)
        quem = (origem.name if origem and origem.registered else "") \
            or (row or {}).get("calling_ae") or "uma modalidade"
        folhas = (row or {}).get("sheets", 0)
        if (row or {}).get("juntadas"):
            quem_pac = (row or {}).get("patient_name") or "o mesmo trabalho"
            self.show_notification("Impressão recebida", f"mais uma folha de {quem} juntada a {quem_pac} "
                                                         f"({folhas} folha(s))")
        else:
            self.show_notification("Impressão recebida", f"{folhas} folha(s) de {quem}")
        if origem is not None and not origem.registered:
            self.show_notification("Origem de impressão nova",
                                   f"{origem.calling_ae or '?'} em {origem.remote_host or '?'} "
                                   "ainda não está cadastrada; o trabalho ficou esperando.")
        if self._prints is not None:
            self._prints.refresh()
        self.browser.refresh()
        self._encaminhar_quando_parar(row)

    def _encaminhar_quando_parar(self, row) -> None:
        """0.99.6: com "juntar folhas" ligado, o trabalho espera a janela (padrão 90 s) sem folha nova
        antes de seguir a regra — senão a primeira folha sairia sozinha e as outras viriam depois.
        Cada folha que se junta recomeça a contagem."""
        from ipe.printing import juntar as JUN
        if not row or not JUN.ligado(self.settings) or row.get("source", "scp") != "scp":
            self._auto_forward(row)
            return
        timers = self.__dict__.setdefault("_esperando_juntar", {})
        rid = row.get("id")
        t = timers.get(rid)
        if t is None:
            t = QTimer(self)
            t.setSingleShot(True)

            def soltar(rid=rid) -> None:
                timers.pop(rid, None)
                atual = self.repo.print_job(rid)
                if atual is not None and atual.get("status") == "new":
                    self._auto_forward(atual)
            t.timeout.connect(soltar)
            timers[rid] = t
        t.start(JUN.segundos(self.settings) * 1000)

    def aplicar_modulos(self) -> None:
        """Módulos mudaram: a barra do banco, as portas de impressão e a aba de impressões."""
        from ipe import modules as MOD
        imp = MOD.ligado(self.settings, "impressao")
        hb = getattr(self, "home_bar", None)
        if hb is not None and "prints" in getattr(hb, "buttons", {}):
            hb.set_visible("prints", imp)
        try:
            if getattr(self.net, "print_servers", None) is not None:
                ligado_agora = any(s.running for s in self.net.print_servers)
                if imp or ligado_agora:
                    self.net.start_print_servers()
        except Exception:  # noqa: BLE001
            log.exception("servidores de impressão ao mudar os módulos")
        if not imp and self._prints is not None:
            i = self.tabs.indexOf(self._prints)
            if i >= 0:
                self.tabs.removeTab(i)

    def run_print_cleanup(self) -> int:
        """Limpeza da lista de impressões, pelos critérios de Configurações de impressão ▸ Limpeza."""
        from ipe import modules as M
        if not M.ligado(self.settings, "impressao"):
            return 0
        try:
            from ipe.printing import limpeza as LZ
            n = LZ.automatica(self.repo, self.settings)
        except Exception:  # noqa: BLE001
            log.exception("Limpeza automática das impressões")
            return 0
        if n:
            self.statusBar().showMessage(f"Limpeza automática: {n} trabalho(s) de impressão apagado(s).", 10000)
            if self._prints is not None:
                self._prints.refresh()
        return n

    def _auto_forward(self, row) -> None:
        """Encaminha sozinho quando uma regra manda (ou quando o servidor tem destino fixo).

        Trabalho de origem ainda não cadastrada fica parado na lista, de propósito: o destino
        depende de saber que aparelho mandou.
        """
        ok, motivo = self.forward_row(row)
        if not ok and motivo:
            self.statusBar().showMessage(motivo, 10000)

    def forward_row(self, row, avisar: bool = False) -> tuple[bool, str]:
        """Manda **um** trabalho pelo caminho das regras. Devolve (saiu, motivo de não ter saído).

        É o único caminho de saída: tanto o encaminhamento automático de quem acabou de chegar
        quanto a liberação em lote dos parados passam por aqui, senão existiriam dois jeitos
        diferentes de mandar o mesmo filme.
        """
        if not row:
            return False, ""
        from ipe.printing import held as HELD
        from ipe.printing import jobs as J
        from ipe.printing import origins as O
        from ipe.printing.dispatch import find_destination
        job = J.load(row.get("folder", "")) if row.get("folder") else None
        if job is None:
            return False, ""
        pode, motivo = O.may_forward(self.settings, row)
        if not pode:
            if self._prints is not None:
                self._prints.refresh()
            return False, motivo
        from ipe.printing import arrival
        if arrival.falta_paciente(self.settings, row):
            if self._prints is not None:
                self._prints.refresh()
            return False, ("O OCR não identificou o paciente do filme: ele ficou esperando você "
                           "confirmar em Impressões › Identificar paciente.")
        alvos = HELD.alvos(self.settings, row, job)
        if not alvos:
            return False, ""                        # sem regra: fica esperando você na lista
        aba = self.show_prints()
        saiu = False
        for nome, modelo in alvos:
            dest = find_destination(self.settings, nome)
            if dest is None:
                return False, f"Destino “{nome}” não existe mais; o trabalho ficou na lista."
            enviados, _falhas = aba.send_rows([dict(row, kind="scp")], dest, avisar=avisar,
                                              template=modelo, how="regra")
            saiu = saiu or bool(enviados)
        return saiu, ""

    def _on_print_images(self, info) -> None:
        """A modalidade mandou imagens comuns (não impressão) à porta da impressora: monta o filme
        com todas elas e segue a regra daquele servidor, como um filme impresso.

        O paciente vem nas próprias imagens, então não passa pelo OCR.
        """
        from datetime import datetime

        from ipe.printing import auto_film as AF
        from ipe.printing import held as HELD
        from ipe.printing import origins as O
        info = info or {}
        padrao = AF.config(self.settings)            # grade padrão, sem regra que combine
        try:
            estudos = {e for e, *_ in info.get("images", []) if e}
            filmes = []
            for estudo in estudos:                   # 0.86: cada exame pode cair numa regra diferente
                dados = self.repo.study_info(estudo) or {}
                regra = AF.escolher(self.settings, info.get("calling_ae", ""), info.get("my_ae", ""),
                                    dados.get("modalities", ""), dados.get("description", ""))
                cfg = regra.as_film_cfg() if regra is not None else padrao
                imgs = [x for x in info.get("images", []) if x[0] == estudo]
                filmes += [(e, f, regra, cfg) for e, f in AF.films_from_images(self.repo, imgs, cfg)]
        except Exception:  # noqa: BLE001
            log.exception("Montando o filme das imagens mandadas à impressora")
            return
        from ipe.printing import arrival
        for estudo, filme, regra, cfg in filmes:
            dados = self.repo.study_info(estudo) or {}
            linha = {"calling_ae": info.get("calling_ae", ""), "remote_host": info.get("remote_host", ""),
                     "server": info.get("server", ""), "label": filme.name, "film_size": cfg.paper,
                     "sheets": len(filme.sheets), "received_at": datetime.now(), "source": "scp",
                     "id_source": "exame", "modality": dados.get("modalities", "") or ""}
            # 0.89: OCR na chegada também para o filme montado com as imagens — o nome gravado na
            # imagem é procurado no banco; sem achar, o filme espera você confirmar o paciente
            encaminhar = {"linha": dict(linha, received_at=linha["received_at"].isoformat()),
                          "destino": regra.destination if regra is not None else "",
                          "modelo": regra.template if regra is not None else ""}
            achado, esperar = None, False
            if arrival.ligado(self.settings):
                achado = arrival.identificar_filme(self.repo, filme)
                esperar = achado is None
            if achado is not None:
                filme.paciente = {"patient_name": achado.get("patient_name", ""),
                                  "patient_id": achado.get("patient_id", ""), "id_source": "ocr"}
            elif esperar:
                filme.paciente = {"id_source": "aguardando", "encaminhar": encaminhar}
            nome = (achado or {}).get("patient_name") or dados.get("patient_name", "")
            film_id = self.repo.save_film(filme.name, filme.to_dict(), [estudo], nome)
            if achado is not None or esperar:
                self.repo.set_film_patient(film_id, nome, (achado or {}).get("patient_id", ""),
                                           "ocr" if achado is not None else "aguardando",
                                           {"encaminhar": encaminhar})
            self.show_notification("Imagens recebidas na impressora",
                                   f"Filme montado: {filme.name} ({filme.image_count()} imagem(ns))"
                                   + (" — esperando você confirmar o paciente" if esperar else ""))
            if self._prints is not None:
                self._prints.refresh()
            if esperar:
                self.statusBar().showMessage(
                    "O OCR não identificou o paciente do filme montado com as imagens recebidas: ele "
                    "ficou esperando você confirmar em Impressões › Identificar paciente.", 12000)
                continue
            pode, motivo = O.may_forward(self.settings, linha)
            if not pode:
                self.statusBar().showMessage(motivo, 10000)
                continue
            if regra is not None and regra.destination:      # a regra do Automático já diz para onde
                self._send_film(film_id, regra.destination, regra.template)
                continue
            for destino, modelo in HELD.alvos(self.settings, linha):
                self._send_film(film_id, destino, modelo)

    def _on_print_identified(self, row) -> None:
        """Você confirmou o paciente de um filme recebido: agora ele segue pela regra."""
        row = row or {}
        if row.get("kind") == "film":
            self._liberar_filme_montado(int(row.get("id", 0) or 0))
            return
        if (row.get("status") or "new") != "new" or (row.get("source") or "scp") != "scp":
            return                                  # já saiu (ou não veio da impressora)
        ok, motivo = self.forward_row(row)
        if ok:
            self.statusBar().showMessage("Paciente confirmado; o filme seguiu pela regra.", 8000)
        elif motivo:
            self.statusBar().showMessage(motivo, 10000)
        if self._prints is not None:
            self._prints.refresh()

    def _liberar_filme_montado(self, film_id: int) -> None:
        """Filme montado com imagens recebidas, que esperava o paciente: segue pela regra que valia
        quando chegou (a do Automático, se tinha destino; senão as regras daquele servidor)."""
        from ipe.printing import held as HELD
        from ipe.printing import origins as O
        dados = self.repo.film_data(film_id) or {}
        enc = (dados.get("paciente") or {}).get("encaminhar") or {}
        linha = dict(enc.get("linha") or {})
        if not linha:
            return
        pode, motivo = O.may_forward(self.settings, linha)
        if not pode:
            self.statusBar().showMessage(motivo, 10000)
            return
        alvos = [(enc["destino"], enc.get("modelo", ""))] if enc.get("destino") else HELD.alvos(self.settings, linha)
        for destino, modelo in alvos:
            self._send_film(film_id, destino, modelo)
        self.statusBar().showMessage("Paciente confirmado; o filme seguiu pela regra." if alvos else
                                     "Paciente confirmado. Nenhuma regra manda este filme para lugar "
                                     "nenhum: ele ficou na lista.", 8000)
        if self._prints is not None:
            self._prints.refresh()

    def release_held_rows(self, linhas: list) -> None:
        """Solta em lote os filmes que estavam parados. Um por um, pelo mesmo caminho."""
        enviados = falhas = 0
        for row in linhas or []:
            atual = self.repo.print_job_by_uid(row.get("uid", "")) or row
            try:
                ok, _motivo = self.forward_row(atual)
            except Exception:  # noqa: BLE001 - um filme ruim não pode parar a fila
                log.exception("Liberando o trabalho %s", row.get("uid", ""))
                ok = False
            enviados += 1 if ok else 0
            falhas += 0 if ok else 1
        if self._prints is not None:
            self._prints.held_done(enviados, falhas)

    def open_acervo_report(self) -> None:
        """Relatório do acervo: o que está guardado, em que formato, e o que a compressão renderia."""
        from ipe.ui.acervo_dialog import AcervoDialog
        AcervoDialog(self.repo, self.settings, self.studies_in_use(), self).exec()
        self.browser.refresh()

    def open_densidade(self, tab=None) -> None:
        """Densidade mamária do exame que está na tela. Sem exame aberto, diz isso e não abre nada."""
        aba = tab if isinstance(tab, ViewerTab) else self.aba_atual()
        if not isinstance(aba, ViewerTab):
            QMessageBox.information(self, "Densidade mamária",
                                    "Abra primeiro as imagens: a densidade é medida no que está "
                                    "nos quadros da tela.")
            return
        from ipe.ui.densidade_dialog import DensidadeDialog
        DensidadeDialog(aba, self).exec()

    def studies_in_use(self) -> list:
        """Exames que não podem ser reescritos agora: abertos numa aba ou ainda baixando."""
        uids = set()
        for aba in self.all_viewer_tabs():
            uids.update(getattr(aba, "study_order", None) or [getattr(aba, "study_uid", "")])
        try:
            for j in self.net.active_jobs():
                uids.update(getattr(j, "study_uids", None) or [])
        except Exception:  # noqa: BLE001 - saber o que está baixando é bônus, não pode derrubar
            log.debug("transferências ativas", exc_info=True)
        return sorted(u for u in uids if u)

    def compress_pass(self) -> None:
        """Passagem automática da compressão, em segundo plano. Só roda se estiver ligada."""
        from ipe.core import compress as K
        pol = K.Politica.from_settings(self.settings)
        if not pol.ligada or getattr(self.repo, "remote", False):
            return
        if self._comprimindo:
            return
        self._comprimindo = True
        em_uso = self.studies_in_use()

        def terminou(balanco, err) -> None:
            self._comprimindo = False
            if err is not None:
                log.exception("passagem da compressão", exc_info=err)
                return
            if balanco is not None and balanco.feitos:
                self.statusBar().showMessage(K.resumo(balanco), 10000)
                self.browser.refresh()
        self.net.run_async(lambda: K.run(self.repo, pol, pular_exames=em_uso), terminou)

    def start_central_server(self) -> None:
        """Liga (ou desliga) o servidor central se este computador for o servidor do grupo."""
        from ipe.central.server import CentralServer
        want = self.settings.get("central.mode", "local") == "server"
        if self.central is not None and (not want or self.central.port != int(self.settings.get("central.port", 8043))):
            self.central.stop()
            self.central = None
        if want and self.central is None:
            try:
                srv = CentralServer(self.db, self.repo, self.storage, port=int(self.settings.get("central.port", 8043)),
                                    certfile=self.settings.get("central.certfile", "") or "",
                                    keyfile=self.settings.get("central.keyfile", "") or "")
                srv.on_import = lambda _s: self._refresh_timer.start()
                srv.settings = self.settings
                srv.net = self.net        # 0.100.9: o navegador envia ao PACS pela fila deste computador
                srv.auto = self.auto      # 0.100.10: e pede CAD/IA pela fila de IA deste computador
                srv.start()
                self.central = srv
            except OSError as e:
                QMessageBox.warning(self, "Servidor central", f"Não foi possível ligar o servidor central:\n{e}")
        self._update_net_label()

    def open_central_settings(self) -> None:
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.central_dialog import CentralDialog
        if CentralDialog(self.settings, self).exec():
            self.start_central_server()

    def open_automation(self) -> None:
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.automation_dialog import AutomationDialog
        AutomationDialog(self, self).exec()
        self.browser.refresh()

    def show_notification(self, title: str, text: str) -> None:
        self.statusBar().showMessage(f"{title}: {text}", 12000)
        tray = getattr(self, "tray", None)
        if tray is not None and tray.isVisible():
            tray.showMessage(title, text)
